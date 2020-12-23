# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common.greenlet_utils import AllowKill
from bliss.data.node import DataNodeContainer
from bliss.data.events import Event, EventType, EventData, EndScanEvent
from bliss.config import settings


class ScanNode(DataNodeContainer):
    _NODE_TYPE = "scan"

    def __init__(self, name, **kwargs):
        super().__init__(self._NODE_TYPE, name, **kwargs)
        self._sync_stream = self._create_stream("data")

    @property
    def dataset(self):
        return self.parent

    def end(self, exception=None):
        """Publish END event in Redis
        """
        if not self.new_node:
            return
        # to avoid to have multiple modification events
        # TODO: what does the comment above mean?
        with settings.pipeline(self._sync_stream, self._info):
            event = EndScanEvent()
            add_info = {
                "end_time": event.time,
                "end_time_str": event.strftime,
                "end_timestamp": event.timestamp,
            }
            self._info.update(add_info)
            self._sync_stream.add_event(event)

    def decode_raw_events(self, events):
        """Decode raw stream data

        :param list((index, raw)) events:
        :returns EventData:
        """
        if not events:
            return None
        first_index = self._streamid_to_idx(events[0][0])
        ev = EndScanEvent.merge(events)
        return EventData(
            first_index=first_index, data=ev.TYPE.decode(), description=ev.exception
        )

    def get_db_names(self, **kw):
        db_names = super().get_db_names(**kw)
        db_names.append(self.db_name + "_data")
        return db_names

    def get_settings(self):
        return super().get_settings() + [self._sync_stream]

    def _subscribe_stream(self, stream_suffix, reader, first_index=None, **kw):
        """Subscribe to a particular stream associated with this node.

        :param str stream_suffix: stream to add is "{db_name}_{stream_suffix}"
        :param DataStreamReader reader:
        :param str or int first_index: Redis stream index (None is now)
        """
        if stream_suffix == "data":
            # Lower priority than all other streams
            kw["priority"] = 1
        super()._subscribe_stream(stream_suffix, reader, first_index=first_index, **kw)

    def _subscribe_all_streams(self, reader, first_index=None, **kw):
        """Subscribe to all associated streams of this node.

        :param DataStreamReader reader:
        :param **kw: see DataNodeContainer
        """
        super()._subscribe_all_streams(reader, first_index=first_index, **kw)
        self._subscribe_stream(
            "data", reader, first_index=0, create=True, ignore_excluded=True
        )

    def _iter_data_stream_events(
        self,
        reader,
        events,
        include_filter=None,
        exclude_children=None,
        first_index=None,
        yield_events=False,
    ):
        """
        :param DataStreamReader reader:
        :param list(2-tuple) events:
        :param include_filter: only these nodes are included (all by default)
        :param exclude_children: ignore children of these nodes recursively
        :param str or int first_index: Redis stream index (None is now)
        :param bool yield_events: yield Event or DataNode
        :yields Event:
        """
        data = self.decode_raw_events(events)
        if data is None:
            return
        if yield_events and self._included(include_filter):
            with AllowKill():
                yield Event(type=EventType.END_SCAN, node=self, data=data)
        # Stop reading events from this node's streams
        # and the streams of its children
        reader.remove_matching_streams(f"{self.db_name}*")


def get_data_from_nodes(pipeline, *nodes):
    scan_channel_get_data_func = dict()  # { channel_name: function }
    scan_image_get_view = dict()
    for node in nodes:
        if node.type == "channel":
            chan = node
            channel_name = chan.fullname

            try:
                saved_db_connection = chan.db_connection
                chan.db_connection = pipeline
                # append channel name and get all data from channel;
                # as it is in a Redis pipeline, .get() returns the
                # conversion function only - data will be received
                # after .execute()
                scan_channel_get_data_func[channel_name] = chan.get(0, -1)
            finally:
                chan.db_connection = saved_db_connection
        elif node.type == "lima":
            scan_image_get_view[node.fullname] = node.get(0, -1)

    result = pipeline.execute()

    for i, (channel_name, get_data_func) in enumerate(
        scan_channel_get_data_func.items()
    ):
        yield channel_name, get_data_func(result[i])
    for channel_name, view in scan_image_get_view.items():
        yield channel_name, view
