# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import numpy
from bliss.config import streaming_events


__all__ = ["ChannelDataEvent"]


class ChannelDataEvent(streaming_events.StreamEvent):
    TYPE = b"CHANNELDATA"
    DATA_KEY = b"__DATA__"
    DESC_KEY = b"__DESC__"
    NPOINTS_KEY = b"__NPOINTS__"

    def init(self, data, description):
        """
        :param Any data:
        :param dict description:
        """
        self.description = description
        self.data = data

    @property
    def shape(self):
        return self.description["shape"]

    @property
    def ndim(self):
        return len(self.shape)

    @property
    def dtype(self):
        return self.description["dtype"]

    @property
    def data(self):
        """Sequence of items when npoints>1, else an item.
        An item can be itself a sequence.
        """
        return self._data

    @property
    def npoints(self):
        return self._npoints

    @data.setter
    def data(self, value):
        if isinstance(value, numpy.ndarray):
            if self.ndim == value.ndim:
                # Only one data point provided
                npoints = 1
            else:
                # Each element is a new data point
                npoints = len(value)
                if npoints == 1:
                    value = value[0]
        elif isinstance(value, (list, tuple)):
            # Each element is a new data point
            npoints = len(value)
            value = numpy.array(value, dtype=self.dtype)
            if npoints == 1:
                value = value[0]
        else:
            # Only one data point provided
            npoints = 1
        self._data = value
        self._npoints = npoints

    def _encode(self):
        raw = super()._encode()
        raw[self.DESC_KEY] = self.generic_encode(self.description)
        raw[self.NPOINTS_KEY] = self.encode_integral(self._npoints)
        raw[self.DATA_KEY] = self.generic_encode(self._data)
        return raw

    def _decode(self, raw):
        super()._decode(raw)
        self.description = self.generic_decode(raw[self.DESC_KEY])
        self._npoints = self.decode_integral(raw[self.NPOINTS_KEY])
        self._data = self.generic_decode(raw[self.DATA_KEY])
