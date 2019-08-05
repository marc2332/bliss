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
import tblib


def encode_tb_exception(exception):
    """This encoder allow to encode an exception altogether with it's traceback.

    It allow to serialize an exception with it's traceback. Complex objects
    from the traceback are removed. But it make the result already useful, with
    file name and line number.
    """
    if not isinstance(exception, BaseException):
        TypeError("Unsupported encoding for non-exception")

    traceback_dict = None
    if exception.__traceback__:
        traceback_dict = tblib.Traceback(exception.__traceback__).to_dict()
    return pickle.dumps((exception, traceback_dict))


def decode_tb_exception(serialized):
    """This decoder allow to decode an exception encoded with `encode_tb_exception``.

    It allow to serialize an exception with it's traceback. Complex objects
    from the traceback are removed. But it make the result already useful, with
    file name and line number.
    """
    exception, traceback_dict = pickle.loads(serialized)
    if traceback_dict is not None:
        traceback = tblib.Traceback.from_dict(traceback_dict)
        exception = exception.with_traceback(traceback.as_traceback())
    return exception


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

    def register_tb_exception(self, exttype=-1):
        """
        Register exception serialization without losing the traceback.

        The serialization it-self is done using pickle.

        Complex objects from the traceback are removed. But it could make the
        result already useful.

        It have to be used before `register_pickle`, else exception will be
        serialized by pickle, and then without the traceback.
        """
        self.register_ext_type(
            encode_tb_exception, decode_tb_exception, exttype=exttype
        )

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
