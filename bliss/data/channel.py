# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.config.settings import QueueSetting
from bliss.data.node import DataNode
import numpy
import redis
import functools
import cPickle

def data_to_bytes(data):
    if isinstance(data, numpy.ndarray):
        return data.dumps()
    else:
        return data

def data_from_pipeline(data, shape=None, dtype=None):
    if len(shape) == 0:
        return numpy.array(data, dtype=dtype)
    else:
        a = numpy.array([numpy.loads(x) for x in data], dtype=dtype)
        a.shape = (-1,)+shape
        return a

def data_from_bytes(data, shape=None, dtype=None):
    if isinstance(data, redis.client.Pipeline):
        return functools.partial(data_from_pipeline, shape=shape, dtype=dtype)

    try:
        return numpy.loads(data)
    except cPickle.UnpicklingError:
        return float(data)

class ChannelDataNode(DataNode):
    def __init__(self, name, **keys):
        shape = keys.pop('shape', None)
        dtype = keys.pop('dtype', None)

        DataNode.__init__(self, 'channel', name, **keys)
    
        if keys.get('create', False):
            if shape is not None:
                self.info["shape"] = shape
            if dtype is not None:
                self.info["dtype"] = dtype

        cnx = self.db_connection
        self._queue = QueueSetting("%s_data" % self.db_name, connection=cnx,
                                   read_type_conversion=functools.partial(data_from_bytes, shape=shape, dtype=dtype),
                                   write_type_conversion=data_to_bytes)

    def store(self, signal, event_dict, cnx=None):
        if signal == "new_data":
            data = event_dict.get("data")
            channel = event_dict.get("channel")
            if len(channel.shape) == data.ndim:
                self._queue.append(data, cnx=cnx)
            else:
                self._queue.extend(data, cnx=cnx)

    def get(self, from_index, to_index=None, cnx=None):
        if to_index is None:
            return self._queue.get(from_index, from_index, cnx=cnx)
        else:
            return self._queue.get(from_index, to_index, cnx=cnx)

    def __len__(self, cnx=None):
        return self._queue.__len__(cnx=cnx)

    @property
    def shape(self):
        return self.info.get("shape")

    @property
    def dtype(self):
        return self.info.get("dtype")

    def _get_db_names(self):
        db_names = DataNode._get_db_names(self)
        db_names.append(self.db_name+"_data")
        return db_names
