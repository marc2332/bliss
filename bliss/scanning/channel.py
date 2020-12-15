# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import functools
from bliss.common.event import dispatcher
from bliss import global_map
import numpy


class AcquisitionChannelList(list):
    def update(self, values_dict):
        """Update all channels and emit the new_data event

        Input:

           values_dict - { channel_name: value, ... }
        """
        for channel in self:
            if channel.short_name in values_dict:
                channel.emit(values_dict[channel.short_name])
            elif channel.fullname in values_dict:
                channel.emit(values_dict[channel.fullname])

    def update_from_iterable(self, iterable):
        for i, channel in enumerate(self):
            channel.emit(iterable[i])

    def update_from_array(self, array):
        for i, channel in enumerate(self):
            channel.emit(array[:, i])


class AcquisitionChannel:
    def __init__(
        self,
        name,
        dtype,
        shape,
        description=None,
        reference=False,
        unit=None,
        data_node_type="channel",
    ):
        self.__name = name
        self.__dtype = dtype
        self.__shape = shape
        self.__unit = unit
        self.__reference = reference
        self.__description = {"reference": reference}
        self.__data_node_type = data_node_type
        self.__node = None

        if isinstance(description, dict):
            self.__description.update(description)

    @property
    def name(self):
        """If the `name` from the constructor is "A:B" this returns:
            - "A:B"  (when B has no alias)
            - "C"    (when B has alias "C" and A != "axis")
            - "A:C"  (when B has alias "C" and A == "axis")
        """
        prefix, _, last_part = self.__name.rpartition(":")
        alias = global_map.aliases.get(last_part)
        if alias:
            if prefix == "axis":
                return f"{prefix}:{alias.name}"
            else:
                return alias.name
        else:
            return self.__name

    @property
    def short_name(self):
        """If the `name` from the constructor is "A:B" this returns:
            - "B"   (when B has no alias)
            - "C"   (when B has alias "C")
        """
        _, _, last_part = self.name.rpartition(":")
        return last_part

    @property
    def fullname(self):
        """If the `name` from the constructor is "A:B" this returns:
            - "A:B"     (when B has no alias)
            - "A:C"     (when B has alias "C")
        """
        prefix, _, last_part = self.__name.rpartition(":")
        alias = global_map.aliases.get(last_part)
        if alias:
            return f"{prefix}:{alias.name}"
        else:
            return self.__name

    @property
    def description(self):
        return self.__description

    @property
    def reference(self):
        return self.__reference

    @property
    def data_node_type(self):
        return self.__data_node_type

    @property
    def dtype(self):
        return self.__dtype

    @dtype.setter
    def dtype(self, value):
        self.__dtype = value

    @property
    def shape(self):
        return self.__shape

    @shape.setter
    def shape(self, value):
        self.__shape = value

    @property
    def unit(self):
        return self.__unit

    @property
    def data_node(self):
        return self.__node

    @data_node.setter
    def data_node(self, node):
        self.__node = node

    def emit(self, data):
        if not self.reference:
            data = self._check_and_reshape(data)
            if data.size == 0:
                return
        self.__description["dtype"] = self.dtype
        self.__description["shape"] = self.shape
        self.__description["unit"] = self.unit
        data_dct = {
            "name": self.fullname,
            "description": self.__description,
            "data": data,
        }
        dispatcher.send("new_data", self, data_dct)

    def _check_and_reshape(self, data):
        ndim = len(self.shape)
        data = numpy.array(data, dtype=self.dtype)

        # Empty data
        if data.size == 0:
            return numpy.empty((0,) + self.shape)

        # Invalid dimensions
        if data.ndim not in (ndim, ndim + 1):
            raise ValueError(
                "Data should either be of {} or {} dimensions".format(ndim, ndim + 1)
            )

        # Single point case
        if data.ndim == ndim and data.shape != self.shape:
            raise ValueError(
                "Single point of shape {} does not match expected shape {}".format(
                    data.shape, self.shape
                )
            )

        # Block case
        if data.ndim == ndim + 1 and data.shape[1:] != self.shape:
            raise ValueError(
                "Multiple points of shape {} does not match expected shape {}".format(
                    data.shape[1:], self.shape
                )
            )

        # Permissive reshaping
        data.shape = (-1,) + self.shape
        return data


def duplicate_channel(source, name=None, conversion=None, dtype=None):
    name = source.name if name is None else name
    dtype = source.dtype if dtype is None else dtype
    dest = AcquisitionChannel(
        name,
        dtype,
        source.shape,
        source.description,
        source.reference,
        source.unit,
        source.data_node_type,
    )

    def callback(data_dct, sender=None, signal=None):
        data = data_dct["data"]
        if conversion is not None:
            data = conversion(data)
        dest.emit(data)

    # Louie does not seem to like closure...
    dest._callback = callback

    connect = lambda: dispatcher.connect(callback, "new_data", source)
    connect.__name__ = "connect_" + name
    cleanup = lambda: dispatcher.disconnect(callback, "new_data", source)
    cleanup.__name__ = "cleanup_" + name
    return dest, connect, cleanup


def attach_channels(channels_source, emitter_channel):
    """
    Attaching a channel means that channel data
    is captured by the destination channel, which will re-emit it
    together with its own channel data.
    """

    def new_emitter(data, channel_source=None):
        channel_source._current_data = data

    for channel_source in channels_source:
        if hasattr(channel_source, "_final_emit"):
            raise RuntimeError("Channel %s is already attached to another channel")
        # replaced the final emit data with one which store
        # the current data
        channel_source._final_emit = channel_source.emit
        channel_source.emit = functools.partial(
            new_emitter, channel_source=channel_source
        )
        channel_source._current_data = None

    emitter_method = emitter_channel.emit

    def dual_emiter(data):
        for channel_source in channels_source:
            source_data = channel_source._current_data
            if len(data) > 1:
                try:
                    iter(source_data)
                except TypeError:
                    l = [source_data]
                else:
                    l = list(source_data)
                source_data = numpy.array(l * len(data), dtype=channel_source.dtype)
            channel_source._final_emit(source_data)
        emitter_method(data)

    emitter_channel.emit = dual_emiter
