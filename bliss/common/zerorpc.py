# Use absolute_import

import pickle

# Patch msgpack
import msgpack_numpy

# Add fallback pickle packing
_msgpack_numpy_encode = msgpack_numpy.encode


def _pickle_fallback_encoding(obj, chain=None):
    robj = _msgpack_numpy_encode(obj, chain=chain)
    if robj is obj:  # try to pickle
        return {b"<pickled>": True, b"data": pickle.dumps(obj)}
    else:
        return robj


_msgpack_numpy_decode = msgpack_numpy.decode


def _pickle_fallback_decode(obj, chain=None):
    if obj.get(b"<pickled>") is True:
        return pickle.loads(obj[b"data"])
    else:
        return _msgpack_numpy_decode(obj, chain=chain)


# replace patched encode decode
msgpack_numpy.encode = _pickle_fallback_encoding
msgpack_numpy.decode = _pickle_fallback_decode
msgpack_numpy.patch()

# Ignore annoying ZMQ bug log messages
from zerorpc.gevent_zmq import logger as _logger

_logger.setLevel("CRITICAL")
del _logger

# Expose everything from zerorpc
from zerorpc import *
