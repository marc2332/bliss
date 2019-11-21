# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.config.settings import QueueSetting
from bliss.data.node import DataNode
import numpy
import redis
import functools
import pickle


def data_to_bytes(data):
    if isinstance(data, numpy.ndarray):
        return data.dumps()
    else:
        return str(data).encode()


def rectify_data(raw_data, dtype=None):
    """
    raw_data: list of numpy arrays (or numpy array of type object with min. shape (1,1))
    
    returns a numpy array of dtype containing all data if raw_data
    in a rectangular structure filled with numpy.nan where nessessary
    """
    if dtype is None:
        dtype = [0].dtype
    shape = (len(raw_data), numpy.max([len(x) for x in raw_data]))
    new_data = numpy.full(shape, numpy.nan, dtype=dtype)
    for i, d in enumerate(raw_data):
        new_data[i][0 : len(d)] = d
    return new_data


def data_from_pipeline(data, shape=None, dtype=None):
    if shape is not None and len(shape) == 0:
        return numpy.array(data, dtype=dtype)
    else:
        raw_data = numpy.array([pickle.loads(x) for x in data])
        try:
            return raw_data.astype(dtype)
        except ValueError:
            return rectify_data(raw_data, dtype=dtype)


def data_from_bytes(data, shape=None, dtype=None):
    if isinstance(data, redis.client.Pipeline):
        return functools.partial(data_from_pipeline, shape=shape, dtype=dtype)

    try:
        return pickle.loads(data)
    except (pickle.UnpicklingError, KeyError):
        if dtype is not None:
            try:
                t = numpy.dtype(dtype)
                return dtype(numpy.array(data, dtype=t))
            except TypeError:
                pass
        return float(data)


class ChannelDataNode(DataNode):
    _NODE_TYPE = "channel"

    def __init__(self, name, **keys):
        shape = keys.pop("shape", None)
        dtype = keys.pop("dtype", None)
        unit = keys.pop("unit", None)
        fullname = keys.pop("fullname", None)
        info = keys.pop("info", dict())
        if keys.get("create", False):
            if shape is not None:
                info["shape"] = shape
            if dtype is not None:
                info["dtype"] = dtype
            info["fullname"] = fullname
            info["unit"] = unit

        DataNode.__init__(self, self._NODE_TYPE, name, info=info, **keys)

        self._queue = None

    def _create_struct(self, db_name, name, node_type):
        # fix the channel name
        fullname = self._info["fullname"]
        if fullname:
            if fullname.endswith(f":{name}"):
                # no alias, name must be fullname
                name = fullname
            elif fullname.startswith("axis:"):
                name = f"axis:{name}"
        return super()._create_struct(db_name, name, node_type)

    def _create_queue(self):
        if self._queue is not None:
            return

        self._queue = QueueSetting(
            "%s_data" % self.db_name,
            connection=self.db_connection,
            read_type_conversion=functools.partial(
                data_from_bytes, shape=self.shape, dtype=self.dtype
            ),
            write_type_conversion=data_to_bytes,
        )

    def store(self, event_dict):
        self._create_queue()

        data = event_dict.get("data")
        self.info.update(event_dict["description"])
        shape = event_dict["description"]["shape"]

        if len(shape) == data.ndim:
            self._queue.append(data)
        else:
            self._queue.extend(data)

    def get(self, from_index, to_index=None):
        """
        returns a data slice of the node.
        
        if to_index is not provided: 
        returns a numpy array containing the data
        
        if to_index is provided:
        returns a list of numpy arrays
        """
        self._create_queue()

        if to_index is None:
            return self._queue.get(from_index, from_index, cnx=self.db_connection)
        else:
            return self._queue.get(from_index, to_index, cnx=self.db_connection)

    def get_as_array(self, from_index, to_index=None):
        """
        returns a data slice of the node as numpy array.
        if nessessary numpy.nan is inserted shape data as 
        `rectangular` arrray.
        """
        raw_data = self.get(from_index, to_index)
        if type(raw_data) == numpy.ndarray:
            return raw_data
        try:
            return numpy.array(raw_data).astype(self.dtype)
        except ValueError:
            return rectify_data(raw_data, dtype=self.dtype)

    def __len__(self):
        self._create_queue()
        return len(self._queue)

    @property
    def shape(self):
        return self.info.get("shape")

    @property
    def dtype(self):
        return self.info.get("dtype")

    @property
    def fullname(self):
        return self.info.get("fullname")

    @property
    def short_name(self):
        _, _, short_name = self.name.rpartition(":")
        return short_name

    @property
    def unit(self):
        return self.info.get("unit")

    def _get_db_names(self):
        db_names = super()._get_db_names()
        db_names.append(self.db_name + "_data")
        return db_names
