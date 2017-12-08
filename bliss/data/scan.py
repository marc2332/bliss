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

from bliss.data.node import DataNode


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


class Scan(DataNode):
    def __init__(self, name, create=False, **keys):
        DataNode.__init__(self, 'scan', name, create=create, **keys)
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
        if node.type() == 'zerod':
            for channel_name in node.channels_name():
                chan = node.get_channel(
                    channel_name, check_exists=False, cnx=pipeline)
                chanlist.append(channel_name)
                chan.get(0, -1)       # all data
                dtype.append((channel_name, 'f8'))

    result = pipeline.execute()
    max_channel_len = max((len(values) for values in result))
    data = numpy.zeros(max_channel_len, dtype=dtype)
    for channel_name, values in zip(chanlist, result):
        a = data[channel_name]
        nb_data = len(values)
        a[0:nb_data] = values[0:nb_data]
    return data
