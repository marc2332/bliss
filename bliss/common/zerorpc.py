# Use absolute_import
from __future__ import absolute_import

# Patch msgpack
import msgpack_numpy
msgpack_numpy.patch()

# Ignore annoying ZMQ bug log messages
from zerorpc.gevent_zmq import logger as _logger
_logger.setLevel('CRITICAL')
del _logger

# Expose everything from zerorpc
from zerorpc import *
