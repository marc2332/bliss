# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.config.streaming import DataStream
from bliss.data.node import DataNode
from bliss.data.events import EventData
import numpy
import redis
import functools
import pickle

# Default length of published channels
CHANNEL_MAX_LEN = 2048


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
    raw_data = numpy.array(data)
    try:
        return raw_data.astype(dtype)
    except ValueError:
        return rectify_data(raw_data, dtype=dtype)


class ChannelDataNode(DataNode):
    _NODE_TYPE = "channel"
    DATA_KEY = b"data"
    DESCRIPTION_KEY = b"description"
    BLOCK_SIZE = b"block_size"

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
        self._last_index = None

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
        self._queue = DataStream(
            "%s_data" % self.db_name,
            connection=self.db_connection,
            maxlen=CHANNEL_MAX_LEN,
        )
        self._last_index = 1  # redis can't starts at 0

    def store(self, event_dict, cnx=None):
        self._create_queue()

        data = event_dict.get("data")
        shape = event_dict["description"]["shape"]
        dtype = event_dict["description"]["dtype"]

        if type(data) is numpy.ndarray:
            if len(shape) == data.ndim:
                block_size = 1
                bytes_data = data.dumps()
            else:
                block_size = len(data)
                if block_size == 1:
                    bytes_data = data[0].dumps()
                else:
                    bytes_data = data.dumps()
        elif type(data) not in (list, tuple):
            block_size = 1
            event_dict["description"]["type"] = "x"
            bytes_data = pickle.dumps(data)
        else:
            block_size = len(data)
            data = numpy.array(data, dtype=dtype)
            if block_size == 1:
                bytes_data = data[0].dumps()
            else:
                bytes_data = data.dumps()
        desc_pickled = pickle.dumps(event_dict["description"])

        self._queue.add(
            {
                self.DATA_KEY: bytes_data,
                self.DESCRIPTION_KEY: desc_pickled,
                self.BLOCK_SIZE: block_size,
            },
            id=self._last_index,
            cnx=cnx,
        )
        self._last_index += block_size

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
            redis_index = from_index + 1  # redis starts at 1
            raw_data = self._queue.range(
                redis_index, redis_index, cnx=self.db_connection
            )
            data = self.raw_to_data(from_index, raw_data)
            return data[0]
        else:
            if to_index < 0:
                to_index = "+"  # means stream end
            else:
                to_index += 1
            redis_first_index = from_index + 1
            raw_data = self._queue.range(
                redis_first_index, to_index, cnx=self.db_connection
            )
            if isinstance(raw_data, list):
                return self.raw_to_data(from_index, raw_data)
            else:
                # pipeline case from get_data
                # should return the conversion fonction
                def raw_to_data(raw_data):
                    return self.raw_to_data(from_index, raw_data)

                return raw_to_data

    def raw_to_data(self, from_index, raw_datas):
        """
        transform internal Stream into data
        raw_datas -- should be the return of xread or xrange.
        """
        event_data = self.decode_raw_events(raw_datas)
        first_index = event_data.first_index
        if first_index < 0:
            return []
        if first_index != from_index:
            raise RuntimeError(
                "Data is not anymore available first_index:"
                f"{first_index} request_index:{from_index}"
            )
        return event_data.data

    def decode_raw_events(self, events):
        """
        transform internal Stream into data
        raw_datas -- should be the return of xread or xrange.
        """
        data = list()
        descriptions = list()
        first_index = -1
        shape = None
        dtype = None
        block_size = 0
        for i, (index, raw_data) in enumerate(events):
            description = pickle.loads(raw_data[ChannelDataNode.DESCRIPTION_KEY])
            block_size = int(raw_data[ChannelDataNode.BLOCK_SIZE])
            data_type = description.get("type")
            if i == 0:
                first_index = int(index.split(b"-")[0]) - 1
                shape = description["shape"]
                dtype = description["dtype"]
            if data_type == "x":
                tmp_data = pickle.loads(raw_data[ChannelDataNode.DATA_KEY])
                data.append(tmp_data)
            else:
                tmp_array = pickle.loads(raw_data[ChannelDataNode.DATA_KEY])
                if block_size > 1:
                    data.extend(tmp_array)
                else:
                    data.append(tmp_array)
            descriptions.append(description)
        if data:
            data = data_from_pipeline(data, shape=shape, dtype=dtype)
        else:
            data = numpy.array([])
        return EventData(
            first_index=first_index,
            data=data,
            description=descriptions,
            block_size=block_size,
        )

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
        # fetching last event
        # using last index as old queue-len
        raw_event = self._queue.rev_range(count=1)
        if not raw_event:
            return 0
        event_data = self.decode_raw_events(raw_event)
        return event_data.first_index + event_data.block_size

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
