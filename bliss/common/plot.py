"""Interface with flint."""

# Imports

import os
import sys
import uuid
import numpy
import subprocess

import zerorpc
import msgpack_numpy

from bliss.config.channels import Channel
from bliss.scanning import scan as scan_module
from bliss.config.conductor.client import get_default_connection

# Globals

msgpack_numpy.patch()
FLINT_PROCESS = None


# Connection helpers

def get_beacon_config():
    beacon = get_default_connection()
    return '{}:{}'.format(beacon._host, beacon._port)


def get_flint_process():
    global FLINT_PROCESS
    if FLINT_PROCESS is not None and FLINT_PROCESS.poll() is None:
        return FLINT_PROCESS.pid
    env = dict(os.environ)
    env['BEACON_HOST'] = get_beacon_config()
    args = [sys.executable, '-m', 'bliss.flint']
    FLINT_PROCESS = subprocess.Popen(args, env=env, close_fds=True)
    return FLINT_PROCESS.pid


def get_flint():
    # Make sure flint is running
    pid = get_flint_process()
    # Get redis connection
    beacon = get_default_connection()
    redis = beacon.get_redis_connection()
    # Current URL
    key = "flint:%s" % pid
    url = redis.brpoplpush(key, key, timeout=3000)
    # Return flint proxy
    proxy = zerorpc.Client(url)
    proxy._pid = pid
    return proxy


# Plotting

class Plot(object):

    def __init__(self, name=None, existing_id=None, flint=None):
        if flint is None:
            self._flint = get_flint()
        # Create plot window
        if existing_id is None:
            self._plot_id = self._flint.add_window()
        else:
            self._plot_id = existing_id
        # Set plot title
        self._name = name or "Plot {}".format(self._plot_id)
        if existing_id is None or name is not None:
            self.setWindowTitle(self._name)

    def __getattr__(self, key):

        def wrapper(*args, **kwargs):
            return self._submit(key, *args, **kwargs)

        wrapper.__name__ = key
        return wrapper

    def __repr__(self):
        return '{}(plot_id={}, flint_pid={})'.format(
            self.__class__.__name__, self.plot_id, self.flint_pid)

    def _submit(self, method, *args, **kwargs):
        return self._flint.run_method(self.plot_id, method, args, kwargs)

    # Properties

    @property
    def flint_pid(self):
        return self._flint._pid

    @property
    def plot_id(self):
        return self._plot_id

    # Plot helpers

    def plot(self, data, legend=None):
        if data.ndim == 1:
            xs = numpy.arange(len(data))
            if data.dtype.fields is None:
                self._submit('addCurve', xs, data, legend=legend)
            else:
                for field in data.dtype.fields:
                    self._submit('addCurve', xs, data[field], legend=field)
            return
        raise NotImplementedError

    def close(self):
        self._flint.remove_window(self.plot_id)


def plot(data=None, name=None):
    plot = Plot(name=name)
    if data is not None:
        plot.plot(data)
    return plot
