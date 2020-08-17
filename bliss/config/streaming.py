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
import time
import logging
from contextlib import contextmanager
from bliss.config.settings import BaseSetting, pipeline
from bliss.config import streaming_events

logger = logging.getLogger(__name__)


class CustomLogger(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        return "[{}] {}".format(str(self.extra), msg), kwargs


class DataStream(BaseSetting):
    """
    This object is base on redis stream, it is similar to python set
    with a dict for each entry.

    Redis stream ID (index): different formats
        - "<millisecondsTime>-<sequenceNumber>"
        - "<millisecondsTime>"
        - millisecondsTime
    millisecondsTime: time since the epoch
    sequenceNumber: positive integer (in case the same time)
    examples: '1575038143700-0', '1575038143700-3', 1575038143700, 0, '0'
    """

    def __init__(self, name, connection=None, maxlen=None, approximate=True):
        """
        :param str name:
        :param connection:
        :param int maxlen: maximumn len of the stream (None: unlimited)
        :param bool approximate:
        """
        super().__init__(name, connection, None, None)
        self._maxlen = maxlen
        self._approximate = approximate

    def __str__(self):
        try:
            n = len(self)
        except TypeError:
            # TODO: Redis bug (xlen returns sometimes Pipeline)
            n = "nan"
        return f"{self.__class__.__name__}({self.name}, {n}/{self._maxlen})"

    def __len__(self):
        return self.connection.xlen(self.name)

    def add(self, fields, id="*", maxlen=None, approximate=None, cnx=None):
        """
        Add one event to the stream
        fields -- is a dictionary
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

    def add_event(self, ev, **kw):
        """
        :param StreamEvent ev:
        :param `**kw`: see `add`
        """
        self.add(ev.encode(), **kw)

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

    def rev_range(self, from_index="+", to_index="-", count=None, cnx=None):
        """
        Read stream values.
        from_index -- maximum index (default `+` last one)
        to_index -- minimum index (default '-' first one)
        count -- maximum number of return values.

        return a list tuple with (index,dict_values)
        """
        if cnx is None:
            connection = self.connection
        else:
            connection = cnx
        return connection.xrevrange(
            self.name, max=from_index, min=to_index, count=count
        )

    def has_new_data(self, last_index):
        """Has new data after a certain index?

        :param str, bytes or int last_index:
        :returns bool:
        """
        from_index = self.stream_incr_index(last_index)
        return bool(self.range(from_index=from_index, count=1))
        # return len(self.range(from_index=last_index, count=2)) == 2

    def get_stream_index(self, idx):
        """Get item using stream ID

        :param str, bytes or int index: b'1575038143700-3'
        :returns 2-tuple: stream ID, raw dict
        """
        events = self.range(from_index=idx, to_index=idx, count=1)
        if events:
            return events[0]
        else:
            return None, {}

    def get_sequence_index(self, idx):
        """Get item using the sequence index

        :param int idx:
        :returns 2-tuple: stream ID, raw dict
        """
        if idx >= 0:
            count = idx + 1
            events = self.range(count=count)
        else:
            count = -idx
            events = self.rev_range(count=count)
        if len(events) == count:
            return events[-1]
        else:
            return None, {}

    @staticmethod
    def stream_incr_index(index):
        """Next stream index (which may not exist)

        :param str, bytes or int index: b'1575038143700-3'
        :returns bytes: b'1575038143700-4'
        """
        if isinstance(index, str):
            index = index.encode()
        elif not isinstance(index, bytes):
            index = b"%d" % index
        indexs = index.split(b"-")
        indexs[-1] = b"%d" % (int(indexs[-1]) + 1)
        return b"-".join(indexs)

    def stream_decr_index(self, index):
        """Previous stream index (which may not exist)

        :param str, bytes or int index: b'1575038143700-3'
        :returns bytes: b'1575038143700-2'
        """
        if isinstance(index, str):
            index = index.encode()
        elif not isinstance(index, bytes):
            index = b"%d" % index
        indexs = index.split(b"-")
        seq_num = int(indexs[-1]) - 1
        if seq_num < 0:
            from_index = int(indexs[0]) - 1  # 1 millisecond back
            lst = self.rev_range(from_index=index, to_index=from_index, count=2)
            if len(lst) == 2:
                return lst[-1][0]
            else:
                return b"%d" % from_index
        else:
            indexs[-1] = b"%d" % seq_num
            return b"-".join(indexs)

    def before_last_index(self):
        """Stream ID just before the last index (may not exist)

        :returns bytes: None when not events in stream
        """
        events = self.rev_range(count=1)
        if events:
            return self.stream_decr_index(events[0][0])
        else:
            return None

    @staticmethod
    def now_index():
        """Data stream index corresponding to now.

        :returns int: time since the epoch in milliseconds
        """
        return int(time.time() * 1000)


class DataStreamReaderStopHandler:
    """Allows a DataStreamReader consumer to be stopped gracefully
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
            self._reader.stop_consumer()


class DataStreamReader:
    """This class receives data from several streams and
    creates one queue of events over which you can iterate.
    
    Safest to use as a context manager:

        with DataStreamReader(...) as reader:
            ...
    
    Can also be used without context, but don't forget
    to close the reader when you are done:

        reader = DataStreamReader(...)
        ...
        reader.close()

    Consume events as follows (only one consumer allowed):

        for stream, events in reader:
            for index, raw in events:
                ...

    Streams can be added and removed by the consumer.
    At least one stream must be added before starting
    the consumer.
    """

    @enum.unique
    class ConsumerState(enum.IntEnum):
        """Writer states:
        * WAITING: consumer is waiting for a new event
        * YIELDING: consumer is processing an event
        * IDLE: consumer stopped or stop was requested
        """

        WAITING = enum.auto()
        YIELDING = enum.auto()
        IDLE = enum.auto()

    # Raw events for the synchronization stream
    SYNC_END = streaming_events.EndEvent().encode()
    SYNC_EVENT = streaming_events.StreamEvent().encode()

    def __init__(self, wait=True, timeout=None, stop_handler=None, active_streams=None):
        """
        :param bool wait: stop reading when no new events (timeout ignored)
                          or keep waiting (with timeout)
        :param num timeout: in seconds (None: never timeout)
        :param DataStreamReaderStopHandler stop_handler: for gracefully stopping
        :param dict active_streams: active streams from another reader
        """
        self._has_consumer = False
        self._cnx = None
        self._logger = CustomLogger(logger, self)

        # Mapping: stream name (str) -> stream info (dict)
        # Streams add/removed by the consumer
        self._streams = {}
        # Streams being actively read
        if active_streams:
            self._active_streams = active_streams
        else:
            self._active_streams = {}

        # Synchronization mechanism (state, event and stream)
        # to ensure that all streams added by the consumer
        # are being checked for new events at least once
        # and stream priorities are being respected
        self.__synchro_stream = None
        self._consumer_state_changed = gevent.event.Event()
        self._consumer_state = self.ConsumerState.YIELDING
        # State as if we are consuming events

        # For the reader greenlet
        self._read_task = None
        self._queue = gevent.queue.Queue()
        if wait:
            # xread wait's for new events
            if timeout is None:
                # one xread call: always yield something (no timeout)
                self._block = 0
            elif timeout:
                # one xread call: yield nothing when no event within x milliseconds
                self._block = int(timeout * 1000 + 0.5)
            else:
                raise ValueError("Zero timeout is not supported")
            self._wait = True
        else:
            # one xread call: yield nothing when no events
            self._block = None
            self._wait = False
        # one xread call: yield at most x events (None: no limit)
        self._count = None

        # Object that allows stopping the consumer gracefully
        if not isinstance(stop_handler, DataStreamReaderStopHandler):
            stop_handler = DataStreamReaderStopHandler()
        stop_handler.attach(self)
        self.stop_handler = stop_handler

    def __str__(self):
        streams = f"{len(self._active_streams)}/{len(self._streams)} streams active"
        consumer = f"{self._consumer_state.name} consumer"
        return f"{self.__class__.__name__}({streams}, {consumer})"

    @property
    def _consumer_state(self):
        return self.__consumer_state

    @_consumer_state.setter
    def _consumer_state(self, state):
        self.__consumer_state = state
        self._consumer_state_changed.set()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        """Stop reader and consumer
        """
        self.stop_consumer()
        self.stop_read_task()

    def stop_consumer(self):
        """Stop consumer gracefully
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
        self._publish_synchro_event(end=True)
        self._consumer_state = self.ConsumerState.IDLE
        # State as if we the consumer already finished
        try:
            self._read_task.get()
            self._read_task = None
        finally:
            self._synchro_stream.clear()

    @property
    def _synchro_stream(self):
        """The read synchronization stream (created when missing).
        This data stream is for internal use only (i.e. not meant for consumer).
        """
        if self.__synchro_stream is not None:
            return self.__synchro_stream
        if not self._streams:
            return None

        # Get the connection shared by all streams
        cnxs = set(adict["stream"]._cnx() for adict in self._streams.values())
        if len(cnxs) != 1:
            raise TypeError("All streams must have the same redis connection")
        cnx = cnxs.pop()
        if self.connection is None:
            self._cnx = cnx
        elif cnx != self.connection:
            raise TypeError("All streams must have the same redis connection")

        # Create the synchronization stream
        self.__synchro_stream = DataStream(str(uuid.uuid1()), maxlen=16, connection=cnx)
        return self.__synchro_stream

    @property
    def connection(self):
        return self._cnx

    def _publish_synchro_event(self, end=False):
        """Add an event the read synchronization stream
        """
        synchro_stream = self._synchro_stream
        if synchro_stream is None:
            return
        with pipeline(synchro_stream):
            if end:
                self._logger.debug("SYNC_END")
                synchro_stream.add(self.SYNC_END)
            else:
                self._logger.debug("SYNC_EVENT")
                synchro_stream.add(self.SYNC_EVENT)
            synchro_stream.ttl(60)

    @contextmanager
    def _update_streams_context(self):
        """Publish synchronization event (and start reader loop)
        if the number of streams are modified within the context.
        """
        nbefore = len(self._streams)
        try:
            yield
        finally:
            nafter = len(self._streams)
            if nafter != nbefore:
                self._publish_synchro_event()
                self._start_read_task()

    def check_stream_connection(self, stream):
        """Make sure all streams share the same connection
        :param DataStream stream:
        :raises TypeError: not the same connection
        """
        if self.connection is None:
            self._cnx = stream.connection
        elif self.connection is not stream.connection:
            raise TypeError("All streams must have the same redis connection")

    def add_streams(self, *streams, first_index=None, priority=0, **info):
        """Add data streams to the reader.

        :param `*streams`: DataStream objects
        :param str or int first_index: Redis stream ID to start reading from
                                       (None: only new events)
        :param int priority: data from streams with a lower priority is never
                             yielded as long as higher priority streams have
                             data. Lower number means higher priority.
        :param dict info: additional stream info
        """
        if priority < 0:
            raise ValueError("Priority must be a positive number")
        with self._update_streams_context():
            for stream in streams:
                if stream.name in self._streams:
                    continue
                self._logger.debug(f"ADD STREAM {stream.name}")
                self.check_stream_connection(stream)
                sinfo = self._compile_stream_info(
                    stream, first_index=first_index, priority=priority, **info
                )
                self._streams[stream.name] = sinfo

    def add_named_streams(self, *names, stream_kwargs=None, add_kwargs=None):
        """Add data streams to the reader (create when non-existing).

        :param `*names`: DataStream names
        :param dict stream_kwargs: for DataStream instantiation
        :param dict add_kwargs: passed to `add_streams`
        """
        if stream_kwargs is None:
            stream_kwargs = {}
        if add_kwargs is None:
            add_kwargs = {}
        streams = (
            DataStream(name, connection=self.connection, **stream_kwargs)
            for name in names
        )
        self.add_streams(*streams, **add_kwargs)

    def remove_streams(self, *streams):
        """Remove data streams from the reader.

        :param `*streams`: DataStream objects
        """
        with self._update_streams_context():
            for stream in streams:
                self._streams.pop(stream.name, None)

    def remove_matching_streams(self, stream_name_pattern):
        """Remove data streams from the reader.

        :param str stream_name_pattern:
        """
        with self._update_streams_context():
            for name in list(self._streams.keys()):
                if fnmatch.fnmatch(name, stream_name_pattern):
                    self._streams.pop(name, None)

    def get_stream_info(self, stream, key, default=None):
        """
        :param DataStream or str stream:
        :return Any: None when missing
        """
        if isinstance(stream, DataStream):
            stream = stream.name
        info = self._streams.get(stream, {})
        return info.get(key, default)

    @staticmethod
    def _compile_stream_info(stream, first_index=None, priority=0, **extra):
        """
        :param DataStream stream:
        :param str or int first_index: Redis stream ID to start reading from
                                       (None: only new events)
        :param int priority: order of streams when reading them in batch
        :param `**extra`: extra stream info to be stored
        """
        if first_index is None:
            first_index = "$"
        fixed = {"stream": stream, "first_index": first_index, "priority": priority}
        extra.update(fixed)
        return extra

    def reset_first_index(self, first_index=None):
        """
        :param str or int first_index: Redis stream ID to start reading from
                                       (None: only new events)
        """
        if self._has_consumer:
            raise RuntimeError("Cannot reset the index while consuming events")
        self._consumer_state = self.ConsumerState.YIELDING
        # State as if we are consuming events
        if first_index is None:
            first_index = "$"
        for info in self._streams.values():
            info["first_index"] = first_index
        self._publish_synchro_event()
        self._start_read_task()

    def _read_active_streams(self, priority_threshold=None):
        """Get data from the active streams

        :param int priority_threshold: read only from this priority or higher
        :returns list(2-tuple): list((name, events))
                                name: name of the stream
                                events: list((index, raw)))
        """
        if not self._active_streams:
            return []
        # Map stream name to index from which to read:
        streams_to_read = sorted(
            self._active_streams.items(), key=lambda item: item[1]["priority"]
        )
        if priority_threshold is None:
            streams_to_read = {k: v["first_index"] for k, v in streams_to_read}
        else:
            streams_to_read = {
                k: v["first_index"]
                for k, v in streams_to_read
                if v["priority"] <= priority_threshold
            }
        # first_index: yield events with stream ID larger then this
        # block=None: yield nothing when no events
        # block=0: always yield something (no timeout)
        # blocks>0: yield nothing when no event within x milliseconds
        # count: yield at most x events in one read operation
        return self.connection.xread(
            streams_to_read, count=self._count, block=self._block
        )

    @contextmanager
    def _read_task_context(self):
        """Start/stop the synchronization stream and exception
        handling for the the reader task.
        """
        try:
            if self._synchro_stream is None:
                raise RuntimeError(
                    "Add at least once stream before iterating over the events"
                )
            sinfo = self._compile_stream_info(
                self._synchro_stream, first_index=0, priority=-1
            )
            self._active_streams[self._synchro_stream.name] = sinfo
            yield
        except (StopIteration, gevent.GreenletExit, KeyboardInterrupt):
            pass
        except Exception as e:
            self._queue.put(e)  # Stop consumer with exception
            raise
        finally:
            self.stop_consumer()  # Stop consumer gracefully
            self._active_streams.pop(self._synchro_stream.name, None)

    @property
    def _synchro_index(self):
        """The last index read from the synchronization stream
        """
        return self._active_streams[self._synchro_stream.name]["first_index"]

    @_synchro_index.setter
    def _synchro_index(self, value):
        self._active_streams[self._synchro_stream.name]["first_index"] = value

    def has_new_synchro_events(self):
        """The synchronization stream has unread events
        """
        return self._synchro_stream.has_new_data(self._synchro_index)

    def _read_task_main(self):
        """Main reading loop. The loop ends when there are no more
        synchronization stream events or on SYNC_END.
        """
        with self._read_task_context():
            keep_reading = True
            synchro_name = self._synchro_stream.name
            while keep_reading:
                # When not waiting for new events (wait=False)
                # will stop reading after reading all current
                # events, unless the synchro stream has events
                # (see further)
                keep_reading = self._wait

                # When wait=True: wait indefinitely when no events
                self._logger.debug("READING ...")
                lst = self._read_active_streams()
                read_priority = None
                for name, events in lst:
                    name = name.decode()
                    sinfo = self._active_streams[name]
                    if read_priority is None:
                        read_priority = sinfo["priority"]
                    if sinfo["priority"] > read_priority:
                        # Lower priority streams are never read until
                        # while higher priority streams have unread data
                        keep_reading = True
                        self._logger.debug(f"SKIP {name}: {len(events)} events")
                        break
                    self._logger.debug(f"PROCESS {name}: {len(events)} events")
                    if name == synchro_name:
                        self._process_synchro_events(events)
                        keep_reading = True
                    else:
                        self._process_consumer_events(sinfo, events)
                        gevent.idle()
                self._logger.debug("READING DONE.")

                # Keep reading when active streams are modified
                # by the consumer. This ensures that all streams
                # are read at least once.
                self._wait_no_consuming()
                if not keep_reading:
                    keep_reading = self.has_new_synchro_events()

    def _wait_no_consuming(self):
        """Wait until the consumer is not processing an event
        (which can result in adding/removing streams).

        If you yield to the gevent loop, you'll need to call
        this again if you want to ensure streams are fixed.
        """
        while self._consumer_state == self.ConsumerState.YIELDING:
            self._consumer_state_changed.clear()
            self._consumer_state_changed.wait()

    def _process_synchro_events(self, events):
        """Process events from the synchronization stream.
        Possible events are add stream, remove stream or end.

        :param list events: list((index, raw)))
        """
        index = self._synchro_index
        for index, raw in events:
            if streaming_events.EndEvent.istype(raw):
                # stop reader loop (does not stop consumer)
                self._logger.debug("STOP reading event")
                raise StopIteration
        self._synchro_index = index
        self._update_active_streams()

    def _log_events(self, task, stream, events):
        if self._logger.getEffectiveLevel() > logging.DEBUG:
            return
        content = "\n ".join(
            [f"{raw[b'__EVENT__']}: {raw.get(b'db_name')}" for idx, raw in events]
        )
        self._logger.debug(f"{task} {stream.name}:\n {content}")

    def _process_consumer_events(self, sinfo, events):
        """Queue stream events and progress the index
        for the next read operation.

        :param dict sinfo: stream info
        :param list events: list((index, raw)))
        """
        self._log_events("QUEUE", sinfo["stream"], events)
        self._queue.put((sinfo["stream"], events))
        sinfo["first_index"] = events[-1][0]

    def _update_active_streams(self):
        """Synchronize the consumer defined streams with
        the streams that are being actively read.
        """
        for stream_name, stream_info in self._streams.items():
            self._active_streams.setdefault(stream_name, stream_info)
        inactive_streams = (
            self._active_streams.keys()
            - self._streams.keys()
            - {self._synchro_stream.name}
        )
        for name in inactive_streams:
            self._active_streams.pop(name)

    def __iter__(self):
        """Iterate over the serialized stream events (this is the consumer).

        yields (stream, list((index, raw))): index is the stream ID (bytes) and
                                               raw is the event data (dict)
        """
        try:
            if self._has_consumer:
                raise RuntimeError("Only one consumer allowed")
            self._has_consumer = True
            self._consumer_state = self.ConsumerState.WAITING
            # if no stream and don't want to wait
            # add a StopIteration in the Queue
            if not self._streams and not self._wait:
                self._queue.put(StopIteration)

            self._logger.debug("CONSUMING ...")
            for item in self._queue:
                if isinstance(item, Exception):
                    raise item
                self._log_events("QUEUE", item[0], item[1])
                self._consumer_state = self.ConsumerState.YIELDING
                yield item
                self._consumer_state = self.ConsumerState.WAITING
        finally:
            self._consumer_state = self.ConsumerState.IDLE
            self._has_consumer = False
