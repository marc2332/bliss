# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common.greenlet_utils import AllowKill
from bliss.data.node import DataNodeContainer
from bliss.data.nodes.channel import ChannelDataNode
from bliss.data.nodes.lima import LimaImageChannelDataNode
from bliss.config.streaming_events import StreamEvent
from bliss.data.events import (
    Event,
    EventType,
    EventData,
    EndScanEvent,
    PreparedScanEvent,
)
from bliss.config import settings
from bliss.common.utils import update_node_info


class ScanNode(DataNodeContainer):
    _NODE_TYPE = "scan"

    _EVENT_TYPE_MAPPING = {
        EndScanEvent.TYPE.decode("ascii"): EventType.END_SCAN,
        PreparedScanEvent.TYPE.decode("ascii"): EventType.PREPARED_SCAN,
    }
    """Mapping from event name to EventType
    """

    def __init__(self, name, **kwargs):
        super().__init__(self._NODE_TYPE, name, **kwargs)
        self._end_stream = self._create_stream("end")
        self._prepared_stream = self._create_stream("prepared")
        # Register to priority as the following way: NEW DATA > PREPARED > NEW NODE > END
        self._register_stream_priority(self._end_stream.name, 3)
        self._register_stream_priority(self._prepared_stream.name, 1)

    @property
    def dataset(self):
        return self.parent

    def prepared(self, scan_info):
        """Publish PREPARED event in Redis
        """
        if not self.new_node:
            return
        # to avoid to have multiple modification events
        # TODO: what does the comment above mean?
        with settings.pipeline(self._prepared_stream, self._info):
            event = PreparedScanEvent()
            update_node_info(self, scan_info)
            self._prepared_stream.add_event(event)

    def end(self, scan_info, exception=None):
        """Publish END event in Redis
        """
        if not self.new_node:
            return
        # to avoid to have multiple modification events
        # TODO: what does the comment above mean?
        with settings.pipeline(self._end_stream, self._info):
            event = EndScanEvent()
            scan_info["end_time"] = event.time
            scan_info["end_time_str"] = event.strftime
            scan_info["end_timestamp"] = event.timestamp
            update_node_info(self, scan_info)
            self._end_stream.add_event(event)

    def decode_raw_events(self, events):
        """Decode raw stream data

        :param list((index, raw)) events:
        :returns EventData:
        """
        if not events:
            return None

        assert len(events) == 1  # Else you are about to lose events
        event = events[0]
        timestamp, raw_data = event
        first_index = self._streamid_to_idx(timestamp)
        ev = StreamEvent.factory(raw_data)
        data = type(ev).TYPE.decode()
        return EventData(first_index=first_index, data=data, description=ev.description)

    def get_db_names(self, **kw):
        db_names = super().get_db_names(**kw)
        db_names.append(self._end_stream.name)
        db_names.append(self._prepared_stream.name)
        return db_names

    def get_settings(self):
        return super().get_settings() + [self._end_stream, self._prepared_stream]

    def _subscribe_streams(self, reader, first_index=None, **kw):
        """Subscribe to all associated streams of this node.

        :param DataStreamReader reader:
        :param **kw: see DataNodeContainer
        """
        super()._subscribe_streams(reader, first_index=first_index, **kw)
        suffix = self._end_stream.name.rsplit("_", 1)[-1]
        self._subscribe_stream(
            suffix, reader, first_index=0, create=True, ignore_excluded=True
        )
        suffix = self._prepared_stream.name.rsplit("_", 1)[-1]
        self._subscribe_stream(
            suffix, reader, first_index=0, create=True, ignore_excluded=True
        )

    def get_stream_event_handler(self, stream):
        """
        :param DataStream stream:
        :returns callable:
        """
        if stream.name == self._end_stream.name:
            return self._iter_data_stream_events
        elif stream.name == self._prepared_stream.name:
            return self._iter_data_stream_events
        return super(ScanNode, self).get_stream_event_handler(stream)

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
        for event in events:
            data = self.decode_raw_events([event])
            if data is None:
                return
            if yield_events and self._included(include_filter):
                with AllowKill():
                    kind = data.data
                    event_id = self._EVENT_TYPE_MAPPING[kind]
                    event = Event(type=event_id, node=self, data=data)
                    yield event
                    if event_id is EventType.END_SCAN:
                        # Stop reading events from this node's streams
                        # and the streams of its children
                        reader.remove_matching_streams(f"{self.db_name}*")


def get_data_from_nodes(pipeline, *nodes):
    scan_channel_get_data_func = dict()  # { channel_name: function }
    scan_image_get_view = dict()
    for node in nodes:
        if isinstance(node, LimaImageChannelDataNode):
            scan_image_get_view[node.fullname] = node.get(0, -1)
        elif isinstance(node, ChannelDataNode):
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

    result = pipeline.execute()

    for i, (channel_name, get_data_func) in enumerate(
        scan_channel_get_data_func.items()
    ):
        yield channel_name, get_data_func(result[i])
    for channel_name, view in scan_image_get_view.items():
        yield channel_name, view
