# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import time
import datetime
import pickle
from bliss.common.measurement import BaseCounter
from bliss.common.axis import Axis
from bliss.data.node import DataNodeContainer
from bliss.config import settings


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
    def __init__(self, name, create=False, **keys):
        DataNodeContainer.__init__(self, "scan", name, create=create, **keys)
        self._info._write_type_conversion = pickle_dump
        if self.new_node:
            with settings.pipeline(self._struct, self._info) as p:
                self._info["start_time"]
                self._info["start_time_str"]
                self._info["start_timestamp"]

                self._struct.start_time, self._struct.start_time_str, self._struct.start_timestamp = (
                    self._info._read_type_conversion(x) for x in p.execute()
                )

    def end(self):
        if self.new_node:
            db_name = self.db_name
            # to avoid to have multiple modification events
            with settings.pipeline(self._struct, self._info) as p:
                end_timestamp = time.time()
                end_time = datetime.datetime.fromtimestamp(end_timestamp)
                self._struct.end_time = end_time
                self._struct.end_time_str = end_time.strftime("%a %b %d %H:%M:%S %Y")
                self._struct.end_timestamp = end_timestamp
                self._info["end_time"] = end_time
                self._info["end_time_str"] = end_time.strftime("%a %b %d %H:%M:%S %Y")
                self._info["end_timestamp"] = end_timestamp
                p.publish(f"__scans_events__:{db_name}", "END")


def get_counter_names(scan):
    """
    Return a list of counter names
    """
    return [node.name for node in scan.nodes.values() if node.type == "channel"]


def get_data(scan):
    """
    Return a dictionary of { channel_name: numpy array }
    """

    class DataContainer(dict):
        def __info__(self):
            return f"DataContainer use [counter],[motor] or {self.keys()}"

        def __getitem__(self, key):
            if isinstance(key, BaseCounter):
                return super().__getitem__(key.fullname)
            elif isinstance(key, Axis):
                return super().__getitem__(f"axis:{key.name}")

            try:
                return super().__getitem__(key)
            except KeyError as er:
                match_value = [
                    (fullname, data)
                    for fullname, data in self.items()
                    if key in fullname.split(":")
                ]
                if len(match_value) == 1:
                    return match_value[0][1]
                elif len(match_value) > 1:
                    raise KeyError(
                        f"Ambiguous key **{key}**, there is several match ->",
                        [x[0] for x in match_value],
                    )
                else:
                    raise er

    connection = scan.node.db_connection
    pipeline = connection.pipeline()
    data = DataContainer()
    nodes_and_index = [(node, 0) for node in scan.nodes.values()]
    for channel_name, channel_data in get_data_from_nodes(pipeline, *nodes_and_index):
        data[channel_name] = channel_data
    return data


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
