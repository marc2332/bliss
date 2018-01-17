# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import time
import datetime
import numpy
import pickle

from bliss.data.node import DataNodeContainer, is_zerod


def _transform_dict_obj(dict_object):
    return_dict = dict()
    for key, value in dict_object.iteritems():
        return_dict[key] = _transform(value)
    return return_dict


def _transform_iterable_obj(iterable_obj):
    return_list = list()
    for value in iterable_obj:
        return_list.append(_transform(value))
    return return_list


def _transform_obj_2_name(obj):
    return obj.name if hasattr(obj, 'name') else obj


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
        DataNodeContainer.__init__(self, 'scan', name, create=create, **keys)
        self.__create = create
        if create:
            start_time_stamp = time.time()
            start_time = datetime.datetime.fromtimestamp(start_time_stamp)
            self._data.start_time = start_time
            self._data.start_time_str = start_time.strftime(
                "%a %b %d %H:%M:%S %Y")
            self._data.start_time_stamp = start_time_stamp
        self._info._write_type_conversion = pickle_dump

    def end(self):
        if self.__create:
            end_time_stamp = time.time()
            end_time = datetime.datetime.fromtimestamp(end_time_stamp)
            self._data.end_time = end_time
            self._data.end_time_str = end_time.strftime("%a %b %d %H:%M:%S %Y")
            self._data.end_time_stamp = end_time_stamp


def get_data(scan):
    """
    Return a numpy structured arrays

    tips: to get the list of channels (data.dtype.names)
          to get datas of a channel data["channel_name"]

    """
    dtype = list()
    chanlist = list()
    max_channel_len = 0
    connection = scan.node.db_connection
    pipeline = connection.pipeline()
    for device, node in scan.nodes.iteritems():
        if node.type == 'channel':
            channel_name = node.name
            chan = node
            # append channel name and get all data from channel;
            # as it is in a Redis pipeline, get returns the
            # conversion function only - data will be received
            # after .execute()
            chanlist.append((channel_name,
                             chan.get(0, -1, cnx=pipeline)))

    result = pipeline.execute()

    structured_array_dtype = []
    for i, (channel_name, get_data_func) in enumerate(chanlist):
        channel_data = get_data_func(result[i])
        result[i] = channel_data
        structured_array_dtype.append(
            (channel_name, channel_data.dtype, channel_data.shape[1:]))

    max_channel_len = max((len(values) for values in result))

    data = numpy.zeros(max_channel_len, dtype=structured_array_dtype)

    for i, (channel_name, _) in enumerate(chanlist):
        data[channel_name] = result[i]

    return data
