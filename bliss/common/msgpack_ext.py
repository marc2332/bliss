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
        self._ext_decoder = collections.OrderedDict()
        self._object_hook_decoder = []

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
            exttype = len(self._ext_decoder)
        if exttype in self._ext_decoder:
            ValueError("ExtType %d already used" % exttype)
        self._encoder.append((encoder, exttype))
        self._ext_decoder[exttype] = decoder

    def register_object_hook(self, encoder, decoder):
        """Register an encoder and a decoder that can convert a python object
        into data which can be serialized by msgpack.

        Args:
            encoder: Function encoding a data into a data serializable by msgpack
            decoder: Function decoding a python structure provided by msgpack
            into an usable data.
        """
        self._encoder.append((encoder, None))
        self._object_hook_decoder.append(decoder)

    def register_numpy(self, exttype=-1):
        """
        Register msgpack_numpy as a codec.
        """
        self.register_object_hook(msgpack_numpy.encode, msgpack_numpy.decode)

    def register_pickle(self, exttype=-1):
        """
        Register pickle as a codec.
        """
        self.register_ext_type(pickle.dumps, pickle.loads, exttype=exttype)

    def _default(self, obj):
        for encoder, exttype in self._encoder:
            try:
                result = encoder(obj)
            except TypeError:
                continue
            if exttype is not None:
                return msgpack.ExtType(exttype, result)
            else:
                return result
        raise TypeError("Unknown type: %r" % (obj,))

    def _ext_hooks(self, code, data):
        decoder = self._ext_decoder.get(code, None)
        if decoder is not None:
            obj = decoder(data)
            return obj
        return msgpack.ExtType(code, data)

    def _object_hook(self, data):
        for decoder in self._object_hook_decoder:
            try:
                result = decoder(data)
            except TypeError:
                continue
            if data is not result:
                # In case the input is not the same as the output
                # let say the result was found
                break
        else:
            return data

        return result

    def packb(self, o, use_bin_type=0):
        """Pack object `o` and return packed bytes."""
        return msgpack.Packer(use_bin_type=use_bin_type, default=self._default).pack(o)

    def Unpacker(self, raw=True, max_buffer_size=0) -> msgpack.Unpacker:
        """Streaming unpacker."""
        return msgpack.Unpacker(
            raw=raw,
            max_buffer_size=max_buffer_size,
            ext_hook=self._ext_hooks,
            object_hook=self._object_hook,
        )
