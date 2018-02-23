"""Interface with flint."""

# Imports

import os
import sys
import uuid
import numpy
import itertools
import subprocess

import zerorpc
import msgpack_numpy

from bliss.config.channels import Channel
from bliss.scanning import scan as scan_module
from bliss.config.conductor.client import get_default_connection

# Globals

msgpack_numpy.patch()
FLINT_PROCESS = None
FLINT_OBJECT = None


class Plot(object):

    # Count the plots
    _id_generator = itertools.count(1)

    def __init__(self, name=None):
        index = next(self._id_generator)
        self._name = name or "Plot {}".format(index)
        self._flint = get_flint()
        self._flint.add_window(self._name)
        self.setWindowTitle(self._name)

    def _submit(self, method, *args, **kwargs):
        return self._flint.run_method(self._name, method, *args, **kwargs)

    def __getattr__(self, key):

        def wrapper(*args, **kwargs):
            return self._submit(key, *args, **kwargs)

        wrapper.__name__ = key
        return wrapper


def get_beacon_config():
    beacon = get_default_connection()
    return '{}:{}'.format(beacon._host, beacon._port)


def get_flint():
    beacon = get_default_connection()
    redis = beacon.get_redis_connection()
    session_id = uuid.uuid1()
    key = "flint:%s" % session_id

    global FLINT_PROCESS
    if FLINT_PROCESS is None:
        env = dict(os.environ)
        env['BEACON_HOST'] = get_beacon_config()
        FLINT_PROCESS = subprocess.Popen(
            [sys.executable, '-m',
             'bliss.flint',
             '-s', str(session_id)],
            env=env)

    global FLINT_OBJECT
    if FLINT_OBJECT is None:
        url = redis.brpoplpush(key, key)
        FLINT_OBJECT = zerorpc.Client(url)

    return FLINT_OBJECT


def plot(data, name=None):
    plot = Plot(name=name)
    add_data_to_plot(plot, data)
    return plot


def add_data_to_plot(plot, data):
    if data.ndim == 1:
        xs = numpy.arange(len(data))
        if data.dtype.fields is None:
            plot.addCurve(xs, data)
        else:
            for field in data.dtype.fields:
                plot.addCurve(xs, data[field], legend=field)
        return
    raise NotImplementedError
