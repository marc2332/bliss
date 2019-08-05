# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Context manager for msgpack, plus serialization extensions.
"""

import collections
import msgpack
import msgpack_numpy
import pickle


class MsgpackContext(object):
    """Manage a state of encoder/decoder for msgpack."""

    def __init__(self):
        self._encoder = []
        self._decoder = collections.OrderedDict()

    def register_ext_type(self, encoder, decoder, exttype=-1):
        """"Register an encoder and a decoder with an ExtType.

        If you use many times `register_ext_type`, the encoding process is done
        in the same order until an encoder is compatible.

        Args:
            encoder: Function encoding a data into a serializable data.
            decoder: Function decoding a serialized data into a usable data.
            exttype: Specify the ext type number to use. By default (-1) pick
                an available value.

        """
        if exttype == -1:
            exttype = len(self._encoder)
        if exttype in self._decoder:
            ValueError("ExtType %d already used" % exttype)
        self._encoder.append(encoder)
        self._decoder[exttype] = decoder

    def register_numpy(self, exttype=-1):
        """
        Register msgpack_numpy as a codec.
        """
        self.register_ext_type(
            msgpack_numpy.encode, msgpack_numpy.decode, exttype=exttype
        )

    def register_pickle(self, exttype=-1):
        """
        Register pickle as a codec.
        """
        self.register_ext_type(pickle.dumps, pickle.loads, exttype=exttype)

    def _default(self, obj):
        for exttype, encoder in enumerate(self._encoder):
            try:
                result = encoder(obj)
                return msgpack.ExtType(exttype, result)
            except TypeError:
                continue
        raise TypeError("Unknown type: %r" % (obj,))

    def _ext_hooks(self, code, data):
        if code in self._decoder:
            decoder = self._decoder[code]
            obj = decoder(data)
            return obj
        return msgpack.ExtType(code, data)

    def packb(self, o, use_bin_type=0):
        """Pack object `o` and return packed bytes."""
        return msgpack.Packer(use_bin_type=use_bin_type, default=self._default).pack(o)

    def Unpacker(self, raw=True, max_buffer_size=0) -> msgpack.Unpacker:
        """Streaming unpacker."""
        return msgpack.Unpacker(
            raw=raw, max_buffer_size=max_buffer_size, ext_hook=self._ext_hooks
        )
