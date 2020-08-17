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
        """Single item (npoints!=1) or sequence (npoints!=1)
        """
        return self._data

    @property
    def sequence(self):
        """Sequence of items
        """
        if self.npoints == 1:
            return [self.data]
        else:
            return self.data

    @property
    def array(self):
        """numpy.ndarray
        """
        return numpy.asarray(self.sequence)

    @property
    def npoints(self):
        return self._npoints

    @data.setter
    def data(self, value):
        if isinstance(value, numpy.ndarray):
            if value.size == 0:
                npoints = 0
            elif self.ndim == value.ndim:
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
        self._npoints = self.decode_npoints(raw)
        self._data = self.generic_decode(raw[self.DATA_KEY])

    @classmethod
    def decode_npoints(cls, raw):
        return cls.decode_integral(raw[cls.NPOINTS_KEY])

    @classmethod
    def merge(cls, events):
        """Merging means stack individual event data.
        The description is assumed to be the same for
        all events (not checked).

        :param list((index, raw)) events:
        :returns ChannelDataEvent:
        """
        data = []
        description = {}
        dtype = None
        for i, (index, raw) in enumerate(events):
            ev = cls(raw=raw)
            if i == 0:
                dtype = ev.dtype
                description = ev.description
            if ev.npoints == 1:
                data.append(ev.data)
            else:
                data.extend(ev.data)
        data = cls.as_array(data, dtype)
        description["shape"] = data.shape[1:]
        description["dtype"] = dtype
        return cls(data, description)

    @staticmethod
    def as_array(sequence, dtype):
        """Convert a sequence of sequences to a numpy array.
        Pad with NaN's when sequences have unequal size.

        :param Sequence sequence:
        :param dtype:
        :returns numpy.ndarray:
        """
        try:
            return numpy.asarray(sequence, dtype=dtype)
        except ValueError:
            # Sequences have unequal length
            shape = (len(sequence), numpy.max([len(x) for x in sequence]))
            arr = numpy.full(shape, numpy.nan, dtype=dtype)
            for src, dest in zip(sequence, arr):
                dest[: len(src)] = src
            return arr
