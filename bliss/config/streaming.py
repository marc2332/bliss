# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import gevent
import uuid
import enum
import fnmatch
from contextlib import contextmanager

from bliss.config.settings import BaseSetting


class DataStream(BaseSetting):
    """
    This object is base on redis stream, it is similar to python set
    with a dict for each entry.
    """

    def __init__(self, name, connection=None, maxlen=None, approximate=True):
        super().__init__(name, connection, None, None)
        self._maxlen = maxlen  # maximumn len of the stream
        self._approximate = approximate

    def __len__(self):
        return self.connection.xlen(self.name)

    def add(self, fields, id="*", maxlen=None, approximate=None, cnx=None):
        """
        Add one event to the stream
        fileds -- is a dictionary
        id -- if equal to '*' means generate a id to append this stream
              if id != '*' must be managed by external application to have it uniq.
              (Read Redis Doc)
        maxlen -- if left to None with use the maxlen passed in the constructor.
                  if maxlen != None the stream will be truncated to this value.
        approximate -- mean if the maxlen is accurate or not. accurate == slow.
        """
        connection = self.connection if cnx is None else cnx
        maxlen = maxlen if maxlen is not None else self._maxlen
        approximate = approximate if approximate is not None else self._approximate
        return connection.xadd(
            self.name, fields, id=id, maxlen=maxlen, approximate=approximate
        )

    def remove(self, *indexes):
        """
        Remove some events using their index.
        """
        for index in indexes:
            self.connection.xdel(self.name, index)

    def range(self, from_index="-", to_index="+", count=None, cnx=None):
        """
        Read stream values.
        from_index -- minimum index (default `-` first one)
        to_index -- maximumn index (default '+' last one)
        count -- maximum number of return values.

        return a list tuple with (index,dict_values)
        """
        if cnx is None:
            connection = self.connection
        else:
            connection = cnx
        return connection.xrange(self.name, min=from_index, max=to_index, count=count)

    def rev_range(self, from_index="+", to_index="-", count=None):
        """
        Read stream values.
        from_index -- maximum index (default `+` last one)
        to_index -- minimum index (default '-' first one)
        count -- maximum number of return values.

        return a list tuple with (index,dict_values)
        """
        return self.connection.xrevrange(
            self.name, max=from_index, min=to_index, count=count
        )


def stream_incr_index(index):
    """ 
    increments to the next index
    expect a byte string with either
    int == b'10' or
    timestamps-int == b'1575038143700-3'
    """
    indexs = index.split(b"-")
    indexs[-1] = b"%d" % (int(indexs[-1]) + 1)
    return b"-".join(indexs)


def stream_decr_index(index):
    """
    decrements to the previous index
    expect a byte string with either
    int == b'10' or
    timestamps-int == b'1575038143700-3'
    """
    indexs = index.split(b"-")
    last_index_part = int(indexs[-1]) - 1
    if last_index_part < 0:
        indexs.pop(-1)
        indexs[0] = b"%d" % (int(indexs[0]) - 1)
    else:
        indexs[-1] = b"%d" % last_index_part
    return b"-".join(indexs)


class StreamStopReadingHandler:
    """
    This class is handler to gently stop stream reading.
    It has to be passed when creating the **stream_setting_read**
    context
    """

    def __init__(self):
        self._reader = None

    def stop(self):
        if self._reader:
            self._reader.close()


@contextmanager
def stream_setting_read(
    count=None, block=0, stream_stop_reading_handler=None, stream_status=None
):
    streams = {} if stream_status is None else stream_status

    class Read:
        State = enum.Enum("Stat", "IDLE WAITING YIELDING")

        def __init__(self):
            self._synchro_stream = None
            self._read_task = None
            self._queue = gevent.queue.Queue()
            self._cnx = None
            self._streams = dict()
            self._wait_event = gevent.event.Event()
            self._state = self.State.YIELDING

        def __del__(self):
            self.close()

        def close(self):
            if not self._read_task:
                self._queue.put(StopIteration)
                return
            self._synchro_stream.add({"end": 1})
            self._state = self.State.IDLE
            self._wait_event.set()
            try:
                self._read_task.get()
            finally:
                self._synchro_stream.clear()

        def add_streams(self, *streams, first_index="$", priority=0):
            if not streams:
                return
            prev_cnx = self._cnx
            cnxs = set(stream._cnx() for stream in streams)
            if len(cnxs) != 1:
                raise TypeError("All streams must have the same redis connection")
            else:
                cnx = cnxs.pop()
                if prev_cnx is None:
                    self._cnx = cnx
                    # start read task
                    self._synchro_stream = DataStream(
                        uuid.uuid1().bytes, maxlen=16, connection=cnx
                    )
                elif cnx != prev_cnx:
                    raise TypeError("All streams must have the same redis connection")
            for stream in streams:
                self._streams.setdefault(
                    stream.name,
                    {
                        "stream": stream,
                        "first_index": first_index,
                        "priority": priority,
                    },
                )
            self._synchro_stream.add({"added streams": 1})
            if not self._read_task:
                self._read_task = gevent.spawn(self._raw_read)

        def remove_stream(self, *streams):
            for stream in streams:
                self._streams.pop(stream.name, None)
            self._synchro_stream.add({"remove stream": 1})

        def remove_match_streams(self, stream_name_pattern):
            streams_name = [
                name
                for name in self._streams
                if fnmatch.fnmatch(name, stream_name_pattern)
            ]
            for name in streams_name:
                self._streams.pop(name, None)
            self._synchro_stream.add({"remove_match_streams": 1})

        def _raw_read(self):
            try:
                streams[self._synchro_stream.name] = {"first_index": 0, "priority": -1}
                name_to_stream = {}
                stop_flag = False
                while not stop_flag:
                    stop_flag = block != 0
                    for name, events in self._cnx.xread(
                        {
                            k: v["first_index"]
                            for k, v in sorted(
                                streams.items(), key=lambda item: item[1]["priority"]
                            )
                        },
                        count=count,
                        block=block,
                    ):
                        if name == self._synchro_stream.name:  # internal
                            for index, ev in events:
                                end = ev.get(b"end")
                                if end:
                                    raise StopIteration  # exit
                            streams[self._synchro_stream.name]["first_index"] = index
                            # add new streams
                            name_to_stream = dict()
                            for stream_name, parameters in self._streams.items():
                                name_to_stream[stream_name.encode()] = parameters[
                                    "stream"
                                ]
                                streams.setdefault(stream_name, parameters)
                            # remove old streams
                            to_delete_streams = (
                                streams.keys()
                                - self._streams.keys()
                                - {self._synchro_stream.name}
                            )
                            for delete_name in to_delete_streams:
                                streams.pop(delete_name)
                            stop_flag = False
                            break
                        self._queue.put((name_to_stream[name], events))
                        last_index, _ = events[-1]
                        streams[name.decode()]["first_index"] = last_index
                        gevent.idle()

                    while self._state not in (self.State.WAITING, self.State.IDLE):
                        self._wait_event.clear()
                        self._wait_event.wait()

                    if stop_flag:
                        # check if there is new synchronization events.
                        first_index = streams[self._synchro_stream.name]["first_index"]
                        stop_flag = not self._synchro_stream.range(
                            from_index=stream_incr_index(first_index), count=1
                        )
            except StopIteration:
                pass
            except Exception as e:
                self._queue.put(e)
            finally:
                self._queue.put(StopIteration)
                streams.pop(self._synchro_stream.name, None)

        def __iter__(self):
            """
            iteration over streams event 
            yield stream,index,ev
            """
            try:
                self._state = self.State.WAITING
                self._wait_event.set()
                # if no stream and don't want to wait
                # add a StopIteration in the Queue
                if not self._streams and block is None:
                    self._queue.put(StopIteration)

                for event in self._queue:
                    if isinstance(event, Exception):
                        raise event
                    self._state = self.State.YIELDING
                    yield event
                    self._state = self.State.WAITING
                    self._wait_event.set()
            finally:
                self._state = self.State.IDLE
                self._wait_event.set()

    try:
        read_handler = Read()
        if stream_stop_reading_handler is not None and isinstance(
            stream_stop_reading_handler, StreamStopReadingHandler
        ):
            stream_stop_reading_handler._reader = read_handler
        yield read_handler
    finally:
        read_handler.close()
