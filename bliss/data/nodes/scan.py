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
from bliss.config.streaming import DataStream


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


class Scan(DataNodeContainer):
    _NODE_TYPE = "scan"
    EVENT_TYPE_KEY = b"__EVENT__"
    END_EVENT = b"END"
    EXCEPTION_KEY = b"__EXCEPTION__"

    def __init__(self, name, create=False, **keys):
        DataNodeContainer.__init__(self, self._NODE_TYPE, name, create=create, **keys)
        self._event = DataStream(f"{self.db_name}_data", connection=self.db_connection)

    def end(self, exception=None):
        if self.new_node:
            db_name = self.db_name
            # to avoid to have multiple modification events
            with settings.pipeline(self._event, self._info) as p:
                end_timestamp = time.time()
                end_time = datetime.datetime.fromtimestamp(end_timestamp)
                new_info = {
                    "end_time": end_time,
                    "end_time_str": end_time.strftime("%a %b %d %H:%M:%S %Y"),
                    "end_timestamp": end_timestamp,
                }
                self._info.update(new_info)
                new_info.pop("end_time")
                new_info[self.EVENT_TYPE_KEY] = self.END_EVENT
                new_info[self.EXCEPTION_KEY] = str(exception)
                self._event.add(new_info)

    def decode_raw_events(self, events):
        if events:
            first_index, raw_dict = events[0]
            first_index = int(first_index.split(b"-")[0])
            exception_str = raw_dict.get(self.EXCEPTION_KEY, b"None")
            if exception_str == b"None":
                exception_str = ""
            else:
                exception_str = exception_str.decode()
            event_type = raw_dict.get(self.EVENT_TYPE_KEY, b"")
            return EventData(
                first_index=first_index,
                data=event_type.decode(),
                description=exception_str,
            )
        else:
            return EventData()

    def _get_db_names(self):
        db_names = super()._get_db_names()
        db_names.append(self.db_name + "_data")
        return db_names


def get_data_from_nodes(pipeline, *nodes_and_start_index):
    scan_channel_get_data_func = dict()  # { channel_name: function }
    scan_image_get_view = dict()
    for node, start_index in nodes_and_start_index:
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
                scan_channel_get_data_func[channel_name] = chan.get(start_index, -1)
            finally:
                chan.db_connection = saved_db_connection
        elif node.type == "lima":
            scan_image_get_view[node.fullname] = node.get(start_index, -1)

    result = pipeline.execute()

    for i, (channel_name, get_data_func) in enumerate(
        scan_channel_get_data_func.items()
    ):
        yield channel_name, get_data_func(result[i])
    for channel_name, view in scan_image_get_view.items():
        yield channel_name, view
