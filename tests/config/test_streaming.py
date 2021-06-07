# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import gevent
import gevent.event
import random
from bliss.config import streaming
from bliss.config.settings import get_redis_proxy


@pytest.mark.parametrize("wait_all_created", [False, True])
def test_data_stream(wait_all_created, beacon):
    nstreams = 0
    stream_created = gevent.event.Event()
    start_streaming = gevent.event.Event()

    def publisher_main(nevents):
        """Create stream and publish nevents
        """
        nonlocal nstreams, stream_created, start_streaming
        stream = streaming.DataStream(f"stream_{nevents}", create=True)
        nstreams += 1
        stream_created.set()
        start_streaming.wait()

        # Stream events
        data = list(range(nevents))
        for i in data:
            stream.add({"data": i})
            gevent.sleep(random.random() / 1000)
        assert len(stream) == nevents

        # Read all events
        events = stream.range()
        sdata = [int(ev[b"data"]) for _, ev in events]
        assert sdata == data

        # Get single event
        for i in range(nevents):
            assert stream.get_sequence_index(i) == events[i]
        assert stream.get_sequence_index(nevents) == (None, {})
        for i in range(-1, -nevents - 1, -1):
            assert stream.get_sequence_index(i) == events[i]
        assert stream.get_sequence_index(-nevents - 1) == (None, {})

        # Read all events in reversed order
        events = stream.rev_range()
        sdata = [int(ev[b"data"]) for _, ev in events]
        assert sdata == list(reversed(data))

        # Read all events (block=0: wait indefinitely for new events)
        for _, events in stream.connection.xread({stream.name: 0}, block=0):
            sdata = [int(ev[b"data"]) for _, ev in events]
            assert sdata == data

    def subscriber_main(lst, wait_all_created=False):
        """Read for all streams in batch and verify data
        """
        nonlocal nstreams, stream_created, start_streaming
        streams_to_read = {
            f"stream_{nevents}": 0 for nevents in sorted(lst, reverse=True)
        }
        if wait_all_created:
            while nstreams != len(streams_to_read):
                stream_created.clear()
                stream_created.wait()
        start_streaming.set()

        data = {}
        connection = get_redis_proxy()
        while True:
            order = []
            # block=0: wait indefinitely for new events
            for stream_name, events in connection.xread(streams_to_read, block=0):
                if not events:
                    continue
                nevents = int(stream_name.split(b"_")[1])
                lst = data.setdefault(nevents, [])
                for _, value in events:
                    lst.append(int(value[b"data"]))
                streams_to_read[stream_name.decode()] = events[-1][0]
                order.append(nevents)
            assert order == sorted(order, reverse=True), "read order not preserved"
            if len(data) == len(streams_to_read):
                if all(nevents == len(lst) for nevents, lst in data.items()):
                    break  # all data has been published
        assert len(data) == len(streams_to_read), "not all streams are read"
        for nevents, lst in data.items():
            assert list(range(nevents)) == lst, "stream data incomplete"

    # Start the publishers and subscribers
    lst = list(range(10, 100, 10))
    if wait_all_created:
        publishers = [gevent.spawn(publisher_main, nevents) for nevents in lst]
        subscribers = [
            gevent.spawn(subscriber_main, lst, wait_all_created) for _ in range(5)
        ]
    else:
        start_streaming.set()
        subscribers = [
            gevent.spawn(subscriber_main, lst, wait_all_created) for _ in range(5)
        ]
        publishers = [gevent.spawn(publisher_main, nevents) for nevents in lst]

    # Wait until all subscribers recieved and verified
    # the data of all streams
    try:
        with gevent.Timeout(10):
            gevent.joinall(subscribers)
            for g in subscribers:
                g.get()
    finally:
        greenlets = publishers + subscribers
        gevent.killall(greenlets)
        gevent.joinall(greenlets)
        for g in greenlets:
            g.get()


class DataStreamTestPublishers:
    """This class implements a pub/sub model to
    test the data stream pub/sub implementation in BLISS.

    Spawning one publisher (DataStream) spawns a cascade
    of others who generate events (DATA, NEW and END).
    """

    def __init__(self, nmaxpub=10):
        """
        :param int nmaxpub: maximum allowed publishers to ensure
                            publishing is finite
        """
        self.npub = 0
        self.nmaxpub = nmaxpub
        self.events_types = ["DATA"] * 100 + ["NEW"] * 5 + ["END"] * 1
        self.publishers = {}
        self.published_data = {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        greenlets = list(self.publishers.values())
        if any(greenlets):
            gevent.killall(greenlets)
            gevent.joinall(greenlets)
            raise RuntimeError("Publishers are still running")
        else:
            for p in greenlets:
                p.get()

    def _next_stream_name(self):
        if self.npub == self.nmaxpub:
            return None
        else:
            self.npub += 1
            return f"pub{self.npub}"

    def _publish_event(self, stream, event):
        """
        :param DataStream stream:
        :param dict event:
        """
        if event["type"] in ("DATA", "END"):
            lst = self.published_data.setdefault(stream.name, [])
            lst.append(event["data"])
        stream.add(event)

    def _publisher_main(self, stream_name):
        """Main loop of a publisher which creates a stream
        and adds (random) events to it until the END event.

        :param str stream_name:
        """
        try:
            stream = streaming.DataStream(stream_name, create=True)
            idata = 0
            while True:
                gevent.sleep(random.random() / 1000)
                etype = random.choice(self.events_types)
                if etype == "DATA":
                    event = {"type": "DATA", "data": idata}
                    self._publish_event(stream, event)
                    idata += 1
                elif etype == "NEW" or etype == "END":
                    new_stream_name = self.spawn_publisher()
                    if new_stream_name:
                        event = {"type": "NEW", "data": new_stream_name}
                        self._publish_event(stream, event)
                    if etype == "END":
                        event = {"type": "END", "data": -1}
                        self._publish_event(stream, event)
                        break
                else:
                    event = {"type": etype}
                    self._publish_event(stream, event)
        except (KeyboardInterrupt, gevent.GreenletExit):
            pass

    def spawn_publisher(self):
        """Launch a new publisher (unless the maximum publishers is reached)
        """
        stream_name = self._next_stream_name()
        if not stream_name:
            return None
        self.publishers[stream_name] = gevent.spawn(self._publisher_main, stream_name)
        return stream_name

    def process_events(self, first_stream_name, reader, overhead=0):
        """Consume stream events from the reader and validate data

        :param str first_stream_name:
        :param DataStreamReader reader:
        :param num overhead: overhead when processing one event
        """
        data = {}
        nend = 0
        reader.add_named_streams(
            first_stream_name, add_kwargs={"priority": 1, "first_index": 0}
        )
        for stream, events in reader:
            for index, event in events:
                gevent.sleep(overhead)
                event = {k.decode(): v.decode() for k, v in event.items()}
                arr = data.setdefault(stream.name, [])
                if event["type"] == "DATA":
                    arr.append(int(event["data"]))
                elif event["type"] == "END":
                    arr.append(int(event["data"]))
                    nend += 1
                elif event["type"] == "NEW":
                    stream_name = event["data"]
                    reader.add_named_streams(stream_name, add_kwargs={"first_index": 0})
                else:
                    raise RuntimeError("Unknown event")
            if nend == self.nmaxpub:
                reader.stop_handler.stop()
        assert data == self.published_data
        for lst in data.values():
            assert lst.pop(-1) == -1
            assert lst == list(range(len(lst)))


@pytest.mark.parametrize("with_overhead", [False, True])
def test_stream_reader(with_overhead, beacon):
    if with_overhead:
        nmaxpub = 3
        overhead = 0.01
        timeout = 60
    else:
        nmaxpub = 100
        overhead = 0
        timeout = 60
    with DataStreamTestPublishers(nmaxpub=nmaxpub) as publishers:
        # Read during publishing
        reader = streaming.DataStreamReader(wait=True)
        try:
            with gevent.Timeout(timeout):
                # Start publishing
                first_stream_name = publishers.spawn_publisher()
                # Read and verify published data during publishing
                # TODO: adding an overhead breaks the data reader
                publishers.process_events(first_stream_name, reader, overhead=overhead)
                # Read and verify published data again
                reader.reset_first_index(0)
                publishers.process_events(first_stream_name, reader)
        finally:
            reader.close()
        # Read after publishing
        with gevent.Timeout(5):
            with streaming.DataStreamReader(wait=False) as reader:
                publishers.process_events(first_stream_name, reader)
