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

from bliss.config.settings import BaseSetting, pipeline


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


class DataStreamReaderStopHandler:
    """Allows DataStreamReader consumers to be stopped gracefully
    """

    def __init__(self):
        self._reader = None

    def attach(self, reader):
        if reader is self._reader:
            return
        elif self._reader is not None:
            raise RuntimeError("Already attached to a reader")
        else:
            self._reader = reader

    def detach(self):
        self._reader = None

    def stop(self):
        if self._reader is not None:
            self._reader.stop_consumers()


class DataStreamReader:
    """The class can be used to retreive the data from
    several data streams at once.
    
    Safest to use as a context manager:

        with DataStreamReader(...) as reader:
            ...
    
    Can also be used without context, but don't forget
    to close the reader when you are done:

        reader = DataStreamReader(...)
        ...
        reader.close()

    Consume events as follows:

        for stream, events in reader:
            for index, value in events:
                ...
    """

    @enum.unique
    class State(enum.IntEnum):
        """Writer states:
        * IDLE: consumer stopped or stop was requested
        * WAITING: consumer is waiting for new events
        * YIELDING: consumer is processing an event or no
                    consumer has been started yet
        """

        IDLE = enum.auto()
        WAITING = enum.auto()
        YIELDING = enum.auto()

    def __init__(self, count=None, block=0, stop_handler=None, stream_status=None):
        """
        :param int count: read this many items from the streams
                          at once (None: no restriction)
        :param int block: number of milliseconds to wait for stream
                          items (None: wait indefinitly)
        :param DataStreamReaderStopHandler stop_handler: for gracefully stopping
        :param dict stream_status: active streams from another reader
        """
        self._block = block
        self._count = count
        self.__synchro_stream = None
        self._read_task = None
        self._queue = gevent.queue.Queue()
        self._cnx = None
        self._streams = dict()
        if stream_status:
            self._active_streams = dict(stream_status)
        else:
            self._active_streams = {}
        if not isinstance(stop_handler, DataStreamReaderStopHandler):
            stop_handler = DataStreamReaderStopHandler()
        stop_handler.attach(self)
        self.stop_handler = stop_handler
        self._state_changed = gevent.event.Event()
        self._state = self.State.YIELDING

    @property
    def _state(self):
        return self.__state

    @_state.setter
    def _state(self, state):
        self.__state = state
        self._state_changed.set()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.stop()

    def stop(self):
        """Stop reader and consumers
        """
        self.stop_consumers()
        self.stop_read_task()

    def stop_consumers(self):
        """Stop consumers gracefully
        """
        self._queue.put(StopIteration)

    def _start_read_task(self):
        """Start the stream reading loop (spawn when not already spawned)
        """
        if not self._read_task:
            self._read_task = gevent.spawn(self._read_task_main)

    def stop_read_task(self):
        """Stop the stream reading loop (greenlet)
        """
        if not self._read_task:
            return
        self._publish_synchro_event({"end": 1})
        self._state = self.State.IDLE
        try:
            self._read_task.get()
            self._read_task = None
        finally:
            self._synchro_stream.clear()

    @property
    def _synchro_stream(self):
        """The read synchronization stream (created when missing)
        """
        if self.__synchro_stream is not None:
            return self.__synchro_stream
        if not self._streams:
            return None
        cnxs = set(adict["stream"]._cnx() for adict in self._streams.values())
        if len(cnxs) != 1:
            raise TypeError("All streams must have the same redis connection")
        else:
            cnx = cnxs.pop()
            if self._cnx is None:
                self._cnx = cnx
                self.__synchro_stream = DataStream(
                    uuid.uuid1().bytes, maxlen=16, connection=cnx
                )
                return self.__synchro_stream
            elif cnx != self._cnx:
                raise TypeError("All streams must have the same redis connection")

    def _publish_synchro_event(self, value):
        """Add an event the read synchronization stream
        """
        synchro_stream = self._synchro_stream
        if synchro_stream is None:
            return
        with pipeline(self._synchro_stream):
            self._synchro_stream.add(value)
            self._synchro_stream.ttl(60)

    def add_streams(self, *streams, first_index="$", priority=0):
        """Add data streams to the reader.

        :param `*streams`: DataStream objects
        :param str first_index: 
        :param int priority: read priority
        """
        for stream in streams:
            self._streams.setdefault(
                stream.name,
                {"stream": stream, "first_index": first_index, "priority": priority},
            )
        self._publish_synchro_event({"added streams": 1})
        self._start_read_task()

    def remove_stream(self, *streams):
        """Remove data streams from the reader.

        :param `*streams`: DataStream objects
        """
        for stream in streams:
            self._streams.pop(stream.name, None)
        self._publish_synchro_event({"remove streams": 1})

    def remove_match_streams(self, stream_name_pattern):
        """Remove data streams from the reader.

        :param str stream_name_pattern:
        """
        names = [
            name for name in self._streams if fnmatch.fnmatch(name, stream_name_pattern)
        ]
        for name in names:
            self._streams.pop(name, None)
        self._publish_synchro_event({"remove streams": 1})

    def _read_active_streams(self):
        """Get data from the active streams
        :returns list(2-tuple): list((name, events))
                                name: name of the stream
                                events: list((index, value)))
        """
        if not self._active_streams:
            return []
        xdict = {
            k: v["first_index"]
            for k, v in sorted(
                self._active_streams.items(), key=lambda item: item[1]["priority"]
            )
        }
        return self._cnx.xread(xdict, count=self._count, block=self._block)

    @contextmanager
    def _read_task_context(self):
        try:
            self._active_streams[self._synchro_stream.name] = {
                "first_index": 0,
                "priority": -1,
            }
            yield
        except StopIteration:
            pass
        except Exception as e:
            self._queue.put(e)  # Stop consumers with exception
        finally:
            self.stop_consumers()  # Stop consumers gracefully
            self._active_streams.pop(self._synchro_stream.name, None)

    def _read_task_main(self):
        """Main reading loop
        """
        with self._read_task_context():
            stop_flag = False
            while not stop_flag:
                stop_flag = self._block != 0
                for name, events in self._read_active_streams():
                    if name == self._synchro_stream.name:
                        # These events are for internal use
                        # and will not be queued for consumption
                        self._process_synchro_event(events)
                        # Do no queue other stream events and read again
                        stop_flag = False
                        break
                    else:
                        # Queue stream events and progress the read pointer
                        adict = self._active_streams[name.decode()]
                        self._queue.put((adict["stream"], events))
                        adict["first_index"] = events[-1][0]
                        gevent.idle()

                # Wait until stopped (or stop requested) or consumers
                # waiting for new item
                while self._state not in (self.State.WAITING, self.State.IDLE):
                    self._state_changed.clear()
                    self._state_changed.wait()

                if stop_flag:
                    # Stop the reader loop if there are
                    # no more synchronization events.
                    first_index = self._active_streams[self._synchro_stream.name][
                        "first_index"
                    ]
                    stop_flag = not self._synchro_stream.range(
                        from_index=stream_incr_index(first_index), count=1
                    )

    def _process_synchro_event(self, events):
        """Process events from the synchronization stream.
        Events: add streams, remove streams or end
        """
        for index, value in events:
            end = value.get(b"end")
            if end:
                raise StopIteration  # stop reader loop
        self._active_streams[self._synchro_stream.name]["first_index"] = index
        self._update_active_streams()

    def _update_active_streams(self):
        """Add/remove streams from the active streams
        """
        for stream_name, parameters in self._streams.items():
            self._active_streams.setdefault(stream_name, parameters)
        inactive_streams = (
            self._active_streams.keys()
            - self._streams.keys()
            - {self._synchro_stream.name}
        )
        for name in inactive_streams:
            self._active_streams.pop(name)

    def __iter__(self):
        """Consumer streams events.
        yield (stream, list((index, value)))
        """
        try:
            self._state = self.State.WAITING
            # if no stream and don't want to wait
            # add a StopIteration in the Queue
            if not self._streams and self._block is None:
                self._queue.put(StopIteration)

            for item in self._queue:
                if isinstance(item, Exception):
                    raise item
                self._state = self.State.YIELDING
                yield item
                self._state = self.State.WAITING
        finally:
            self._state = self.State.IDLE
