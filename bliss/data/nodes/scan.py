# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import time
import datetime
import pickle
from bliss.data.node import DataNodeContainer
from bliss.data.events import EventData
from bliss.config import settings
from bliss.config import streaming_events


def _transform_dict_obj(dict_object):
    return_dict = dict()
    for key, value in dict_object.items():
        return_dict[key] = _transform(value)
    return return_dict


def _transform_iterable_obj(iterable_obj):
    return_list = list()
    for value in iterable_obj:
        return_list.append(_transform(value))
    return return_list


def _transform_obj_2_name(obj):
    return obj.name if hasattr(obj, "name") else obj


def _transform(var):
    if isinstance(var, dict):
        var = _transform_dict_obj(var)
    elif isinstance(var, (tuple, list)):
        var = _transform_iterable_obj(var)
    else:
        var = _transform_obj_2_name(var)
    return var


def pickle_dump(var):
    var = _transform(var)
    return pickle.dumps(var)


class EndScanEvent(streaming_events.EndEvent):

    TYPE = b"END_SCAN"


class Scan(DataNodeContainer):
    _NODE_TYPE = "scan"

    def __init__(self, name, create=False, **keys):
        DataNodeContainer.__init__(self, self._NODE_TYPE, name, create=create, **keys)
        self._sync_stream = self.create_associated_stream("data")

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
        for index, raw in events:
            event = streaming_events.StreamEvent.factory(raw)
            if isinstance(event, EndScanEvent):
                first_index = int(index.split(b"-")[0])
                return EventData(
                    first_index=first_index,
                    data=event.TYPE.decode(),
                    description=event.exception,
                )

    def _get_db_names(self):
        db_names = super()._get_db_names()
        db_names.append(self.db_name + "_data")
        return db_names

    def subscribe_initial_streams(self, reader, yield_data=False, first_index=0):
        """Subscribe to a minimal amount of streams so
        we can eventually get all nodes and events.

        :param DataStreamReader reader:
        :param bool yield_data:
        """
        # Subscribe to the children *_data streams
        if yield_data:
            self.subscribe_existing_children_streams(
                "data", reader, include_parent=False, first_index=0
            )

        # This is where the new node events are published:
        super().subscribe_initial_streams(reader, first_index=first_index)

        # Always subscribe to the scan's data stream
        self.subscribe_stream("data", reader, first_index=0)

    def subscribe_stream(self, stream_suffix, reader, **kw):
        """Subscribe to a stream with a particular name,
        associated with this node.

        :param str stream_suffix: stream to add is "{db_name}_{stream_suffix}"
        :param DataStreamReader reader:
        """
        if stream_suffix == "data":
            # Default priority is 1
            kw["priority"] = 1
        super().subscribe_stream(stream_suffix, reader, **kw)


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
