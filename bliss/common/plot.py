"""Interface with flint."""

# Imports

import os
import sys
import numpy
import platform
import subprocess
from collections import OrderedDict

import zerorpc
import msgpack_numpy

from bliss.config.channels import Channel
from bliss.scanning import scan as scan_module
from bliss.config.conductor.client import get_default_connection

__all__ = ['plot', 'plot_curve', 'plot_curve_list', 'plot_image',
           'plot_scatter', 'plot_single_image', 'plot_image_stack']

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


def get_flint(pid=None):
    # Make sure flint is running
    if pid is None:
        pid = get_flint_process()
    # Get redis connection
    beacon = get_default_connection()
    redis = beacon.get_redis_connection()
    # Current URL
    key = "flint:{}:{}".format(platform.node(), pid)
    url = redis.brpoplpush(key, key, timeout=3000)
    # Return flint proxy
    proxy = zerorpc.Client(url)
    proxy._pid = pid
    return proxy


# Simple Qt interface

class QtInterface(object):
    """Isolate the qt interface of the plot windows
    from the flint interface."""

    def __init__(self, interface, submit):
        for key in interface:
            wrapper = self._make_wrapper(submit, key)
            setattr(self, key, wrapper)

    @staticmethod
    def _make_wrapper(submit, key):
        def wrapper(*args, **kwargs):
            return submit(key, *args, **kwargs)

        wrapper.__name__ = key
        return wrapper


# Base plot class

class BasePlot(object):

    # Name of the corresponding silx widget
    WIDGET = NotImplemented

    # Name of the method to add data to the plot
    METHOD = NotImplemented

    # The possible dimensions of the data to plot
    DATA_DIMENSIONS = NotImplemented

    # Single / Multiple data handling
    MULTIPLE = NotImplemented

    # Data input number for a single representation
    DATA_INPUT_NUMBER = NotImplemented

    def __init__(self, name=None, existing_id=None, flint_pid=None):
        self._flint = get_flint(pid=flint_pid)
        # Create plot window
        if existing_id is None:
            self._plot_id = self._flint.add_window(self.WIDGET)
        else:
            self._plot_id = existing_id
        # Create qt interface
        interface = self._flint.get_interface(self._plot_id)
        self.qt = QtInterface(interface, self.submit)
        # Set plot title
        self._name = name or "Plot {}".format(self._plot_id)
        if existing_id is None or name is not None:
            self.qt.setWindowTitle(self._name)

    def __repr__(self):
        return '{}(plot_id={}, flint_pid={})'.format(
            self.__class__.__name__, self.plot_id, self.flint_pid)

    def submit(self, method, *args, **kwargs):
        return self._flint.run_method(self.plot_id, method, args, kwargs)

    # Properties

    @property
    def flint_pid(self):
        return self._flint._pid

    @property
    def plot_id(self):
        return self._plot_id

    # Data handling

    def add_single_data(self, field, data):
        data = numpy.array(data)
        if data.ndim not in self.DATA_DIMENSIONS:
            raise ValueError(
                'Data dimension must be in {} (got {})'
                .format(self.DATA_DIMENSIONS, data.ndim))
        return self._flint.add_data(self._plot_id, field, data)

    def add_data(self, data, default_field='default'):
        # Get fields
        if isinstance(data, dict):
            fields = list(data)
        else:
            fields = numpy.array(data).dtype.fields
        # Single data
        if fields is None:
            data_dict = OrderedDict([(default_field, data)])
        # Multiple data
        else:
            data_dict = OrderedDict((field, data[field]) for field in fields)
        # Send data
        for field, value in data_dict.items():
            self.add_single_data(field, value)
        # Return data dict
        return data_dict

    def remove_data(self, field):
        return self._flint.remove_data(self._plot_id, field)

    def select_data(self, *names, **kwargs):
        return self._flint.select_data(
            self._plot_id, self.METHOD, names, kwargs)

    def deselect_data(self, *names):
        return self._flint.deselect_data(self._plot_id, names)

    def clear_data(self):
        return self._flint.clear_data(self._plot_id)

    def get_data(self):
        return self._flint.get_data(self._plot_id)

    # Plotting

    def plot(self, data, **kwargs):
        fields = list(self.add_data(data))
        names = fields[:self.DATA_INPUT_NUMBER]
        self.select_data(*names, **kwargs)

    # Clean up

    def close(self):
        self._flint.remove_window(self.plot_id)

    # Interaction

    def select_points(self, nb):
        return self._flint.select_points(self._plot_id, nb)

    def select_shape(self, shape):
        return self._flint.select_shape(self._plot_id, shape)

    def clear_selections(self):
        return self._flint.clear_selections(self._plot_id)

    # Instanciation

    @classmethod
    def instanciate(cls, data=None, name=None, existing_id=None,
                    flint_pid=None, **kwargs):
        plot = cls(name=name, existing_id=existing_id, flint_pid=flint_pid)
        if data is not None:
            plot.plot(data=data, **kwargs)
        return plot


# Plot classes

class CurvePlot(BasePlot):

    # Name of the corresponding silx widget
    WIDGET = 'Plot1D'

    # Name of the method to add data to the plot
    METHOD = 'addCurve'

    # The dimension of the data to plot
    DATA_DIMENSIONS = 1,

    # Single / Multiple data handling
    MULTIPLE = True

    # Data input number for a single representation
    DATA_INPUT_NUMBER = 2

    # Specialized x data handling

    def plot(self, data, **kwargs):
        # Add data
        data_dict = self.add_data(data)
        # Get x field
        x = kwargs.pop('x', None)
        x_field = x if isinstance(x, str) else 'x'
        # Get default x
        if x is None and x_field not in data_dict:
            key = next(iter(data_dict))
            length, = data_dict[key].shape
            x = numpy.arange(length)
        # Add x data
        if x is not None:
            self.add_single_data(x_field, x)
        # Plot all curves
        for field in data_dict:
            if field != x_field:
                self.select_data(x_field, field, **kwargs)


class ScatterPlot(BasePlot):

    # Name of the corresponding silx widget
    WIDGET = 'Plot1D'

    # Name of the method to add data to the plot
    METHOD = 'addScatter'

    # The dimension of the data to plot
    DATA_DIMENSIONS = 1,

    # Single / Multiple data handling
    MULTIPLE = True

    # Data input number for a single representation
    DATA_INPUT_NUMBER = 3


class CurveListPlot(BasePlot):

    # Name of the corresponding silx widget
    WIDGET = 'CurvesView'

    # Name of the method to add data to the plot
    METHOD = None

    # The dimension of the data to plot
    DATA_DIMENSIONS = 2,

    # Single / Multiple data handling
    MULTIPLE = False

    # Data input number for a single representation
    DATA_INPUT_NUMBER = 1


class ImagePlot(BasePlot):

    # Name of the corresponding silx widget
    WIDGET = 'Plot2D'

    # Name of the method to add data to the plot
    METHOD = 'addImage'

    # The dimension of the data to plot
    DATA_DIMENSIONS = 2, 3

    # Single / Multiple data handling
    MULTIPLE = True

    # Data input number for a single representation
    DATA_INPUT_NUMBER = 1


class SingleImagePlot(BasePlot):

    # Name of the corresponding silx widget
    WIDGET = 'ImageView'

    # Name of the method to add data to the plot
    METHOD = 'setImage'

    # The dimension of the data to plot
    DATA_DIMENSIONS = 2,

    # Single / Multiple data handling
    MULTIPLE = False

    # Data input number for a single representation
    DATA_INPUT_NUMBER = 1


class ImageStackPlot(BasePlot):

    # Name of the corresponding silx widget
    WIDGET = 'StackView'

    # Name of the method to add data to the plot
    METHOD = 'setStack'

    # The dimension of the data to plot
    DATA_DIMENSIONS = 3, 4

    # Single / Multiple data handling
    MULTIPLE = False

    # Data input number for a single representation
    DATA_INPUT_NUMBER = 1


# Plot helpers

plot_curve = CurvePlot.instanciate
plot_curve_list = CurveListPlot.instanciate
plot_scatter = ScatterPlot.instanciate
plot_image = ImagePlot.instanciate
plot_single_image = SingleImagePlot.instanciate
plot_image_stack = ImageStackPlot.instanciate


def default_plot(data=None, **kwargs):
    kwargs['data'] = data
    # No data available
    if data is None:
        return plot_curve(**kwargs)
    # Assume a dict of curves
    if isinstance(data, dict):
        return plot_curve(**kwargs)
    data = numpy.array(data)
    # Unstructured data
    if data.dtype.fields is None:
        # Assume a single curve
        if data.ndim == 1:
            return plot_curve(**kwargs)
        # Assume a single image
        if data.ndim == 2:
            return plot_image(**kwargs)
        # Assume a colored image
        if data.ndim == 3 and data.shape[2] in (3, 4):
            return plot_image(**kwargs)
        # Assume an image stack
        if data.ndim == 3:
            return plot_image_stack(**kwargs)
    # Assume a single struct of curves
    if data.ndim == 0:
        return plot_curve(**kwargs)
    # A list of struct
    if data.ndim == 1:
        # Assume multiple curves
        if all(data[field].ndim == 1 for field in data.dtype.fields):
            return plot_curve(**kwargs)
        # Assume multiple plots
        return tuple(
                default_plot(data=data[field], **kwargs)
                for field in data.dtype.fields)
    # Not recognized
    raise ValueError('Not recognized data')


# Alias
plot = default_plot
