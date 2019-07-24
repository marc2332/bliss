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


def data_from_pipeline(data, shape=None, dtype=None):
    if len(shape) == 0:
        return numpy.array(data, dtype=dtype)
    else:
        a = numpy.array([pickle.loads(x) for x in data])
        try:
            a = a.astype(dtype)
            # a.shape = (-1,) + shape
            return a
        except ValueError:
            shape = (len(a), numpy.max([len(x) for x in a]))
            arr = numpy.full(shape, numpy.nan, dtype=dtype)
            for i, d in enumerate(a):
                arr[i][0 : len(d)] = d
            return arr


def data_from_bytes(data, shape=None, dtype=None):
    if isinstance(data, redis.client.Pipeline):
        return functools.partial(data_from_pipeline, shape=shape, dtype=dtype)

    try:
        return pickle.loads(data)
    except pickle.UnpicklingError:
        return float(data)


class ChannelDataNode(DataNode):
    def __init__(self, name, **keys):
        shape = keys.pop("shape", None)
        dtype = keys.pop("dtype", None)
        unit = keys.pop("unit", None)
        alias = keys.pop("alias", None)
        fullname = keys.pop("fullname", None)
        info = keys.pop("info", dict())
        if keys.get("create", False):
            if shape is not None:
                info["shape"] = shape
            if dtype is not None:
                info["dtype"] = dtype
            info["has_alias"] = alias is not None
            info["alias"] = alias or "None"
            info["fullname"] = fullname
            info["unit"] = unit

        DataNode.__init__(self, "channel", name, info=info, **keys)

        self._queue = None

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
        self._create_queue()

        if to_index is None:
            return self._queue.get(from_index, from_index, cnx=self.db_connection)
        else:
            return self._queue.get(from_index, to_index, cnx=self.db_connection)

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
    def alias(self):
        return self.info.get("alias")

    @property
    def fullname(self):
        return self.info.get("fullname")

    @property
    def alias_or_name(self):
        if self.has_alias:
            return self.alias
        else:
            return self.name

    @property
    def alias_or_fullname(self):
        if self.has_alias:
            return self.alias
        else:
            return self.fullname

    @property
    def has_alias(self):
        return self.info.get("has_alias")

    @property
    def unit(self):
        return self.info.get("unit")

    def _get_db_names(self):
        db_names = DataNode._get_db_names(self)
        db_names.append(self.db_name + "_data")
        return db_names
