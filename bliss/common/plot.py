# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Bliss plotting interface
========================

Bliss plotting is done through a silx-based application called **flint**.

This Qt application is started automatically when a new plot is created.

This interface supports several types of plot:

- **curve plot**:

  * plotting one or several 1D data as curves
  * Optional x-axis data can be provided
  * the plot is created using ``plot_curve``

- **scatter plot**:

  * plotting one or several scattered data
  * each scatter is a group of three 1D data of same length
  * the plot is created using ``plot_scatter``

- **image plot**:

  * plot one or several image on top of each other
  * the image order can be controlled using a depth parameter
  * the plot is created using ``plot_image``

- **image + histogram plot**:

  * plot a single 2D image (greyscale or colormap)
  * two histograms along the X and Y dimensions are displayed
  * the plot is created using ``plot_image_with_histogram``

- **curve list plot**:

  * plot a single list of 1D data as curves
  * a slider and an envelop view are provided
  * the plot is created using ``plot_curve_list``
  * this widget is not integrated yet!

- **image stack plot**:

  * plot a single stack of image
  * a slider is provided to browse the images
  * the plot is created using ``plot_image_stack``

An extra helper called ``plot`` is provided to automatically infer
a suitable type of plot from the data provided.

Basic interface
---------------

All the above functions provide the same interface. They take the data
as an argument and return a plot:

    >>> from bliss.common.plot import *

    >>> plot(mydata, name="My plot")
    ImagePlot(plot_id=1, flint_pid=17450)

Extra keyword arguments are forwarded to silx:

    >>> p = plot(mydata, xlabel='A', ylabel='b')

From then on, all the interaction with the corresponding plot window goes
through the plot object. For instance, it provides a ``plot`` method
to add and display extra data:

    >>> p.plot(some_extra_data, yaxis='right')


Advanced interface
------------------

For a finer control over the plotted data, the data management is
separated from the plot management. In order to add more data to
the plot, use the following interface:

    >>> p.add_data(cos_data, field='cos')

This data is now identified using its field, ``'cos'``. A dict or
a structured numpy array can also be provided. In this case,
the fields of the provided data structure are used as identifiers:

    >>> p.add_data({'cos': cos_data, 'sin': sin_data})

The plot selection is then done through the ``select_data`` method.
For a curve plot, the expected arguments are the names of the data
to use for X and Y:

    >>> p.select_data('sin', 'cos')

Again, the extra keyword arguments will be forwarded to silx:

    >>> p.select_data('sin', 'cos', color='green', symbol='x')

The curve can then be deselected:

    >>> p.deselect_data('sin', 'cos')

And the data can be cleared:

    >>> p.clear_data()


Plot interaction
----------------

In order to interact with a given plot, several methods are provided.

The ``select_points`` method allows the user to select a given number of point
on the corresponding plot using their mouse.

    >>> a, b, c = p.select_points(3)
    # Blocks until the user selects the 3 points
    >>> a
    (1.2, 3.4)

The ``select_shape`` methods allows the user to select a given shape on the
corresponding plot using their mouse. The available shapes are:

- ``'rectangle'``: rectangle selection
- ``'line'``: line selection
- ``'hline'``: horizontal line selection
- ``'vline'``: vertical line selection
- ``'polygon'``: polygon selection

The return values are shown in the following example:

   >>> topleft, bottomright = p.select_shape('rectangle')
   >>> start, stop = p.select_shape('line')
   >>> left, right = p.select_shape('hline')
   >>> bottom, top = p.select_shape('vline')
   >>> points = p.select_shape('polygon')
"""

# Imports

import os
import sys
import numpy
import psutil
import subprocess
from contextlib import contextmanager
import gevent

from bliss.comm import rpc
from bliss import current_session
from bliss.config.conductor.client import get_default_connection
from bliss.flint.config import get_flint_key

try:
    from bliss.flint import poll_patch
except ImportError:
    poll_patch = None

import logging


FLINT_LOGGER = logging.getLogger("flint")
FLINT_OUTPUT_LOGGER = logging.getLogger("flint.output")
# Disable the flint output
FLINT_OUTPUT_LOGGER.disabled = True


__all__ = [
    "plot",
    "plot_curve",
    "plot_curve_list",
    "plot_image",
    "plot_scatter",
    "plot_image_with_histogram",
    "plot_image_stack",
]

# Globals

FLINT = {"process": None, "proxy": None, "greenlet": None}

# Connection helpers


def get_beacon_config():
    beacon = get_default_connection()
    return "{}:{}".format(beacon._host, beacon._port)


def check_flint(session_name):
    """Check if an existing Flint process is running and attached to session_name.

    Returns:
        The process object from psutil.
    """
    pid = FLINT.get("process")
    if pid is not None and psutil.pid_exists(pid):
        return psutil.Process(pid)

    beacon = get_default_connection()
    redis = beacon.get_redis_connection()

    # get existing flint, if any
    pattern = get_flint_key(pid="*")
    for key in redis.scan_iter(pattern):
        key = key.decode()
        pid = int(key.split(":")[-1])
        if psutil.pid_exists(pid):
            value = redis.lindex(key, 0).split()[0]
            if value.decode() == session_name:
                return psutil.Process(pid)
        else:
            redis.delete(key)
    return None


def log_process_output_to_logger(process, stream_name, logger, level):
    """Log the stream output of a process into a logger until the stream is
    closed.

    Args:
        process: A process object from subprocess or from psutil modules.
        stream_name: One of "stdout" or "stderr".
        logger: A logger from logging module
        level: A value of logging
    """
    if hasattr(process, stream_name):
        # process come from subprocess, and was pipelined
        stream = getattr(process, stream_name)
    else:
        # process output was not pipelined.
        # Try to open a linux stream
        stream_id = 1 if stream_name == "stdout" else 2
        try:
            path = f"/proc/{process.pid}/fd/{stream_id}"
            stream = open(path)
        except:
            FLINT_LOGGER.debug("Error while opening path %s", path, exc_info=True)
            FLINT_LOGGER.warning("Flint %s can't be attached.", stream_name)
            return
    try:
        while not stream.closed:
            line = stream.readline()
            try:
                line = line.decode()
            except:
                pass
            if not line:
                break
            logger._log(level, "%s", line)
    except RuntimeError:
        # Process was terminated
        pass


def start_flint():
    """ Start the flint application in a subprocess.

    Returns:
        The process object"""
    FLINT_LOGGER.warning("Flint starting...")
    env = dict(os.environ)
    env["BEACON_HOST"] = get_beacon_config()
    if poll_patch is not None:
        poll_patch.set_ld_preload(env)

    # Imported here to avoid cyclic dependency
    from bliss.scanning.scan import ScanDisplay

    scan_display = ScanDisplay()
    args = [sys.executable, "-m", "bliss.flint"]
    args.extend(scan_display.extra_args)
    process = subprocess.Popen(
        args,
        env=env,
        start_new_session=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return process


def _attach_flint(process):
    """Attach a flint process, make a RPC proxy and bind Flint to the current
    session and return the FLINT proxy.
    """
    pid = process.pid
    FLINT_LOGGER.debug("Attach flint PID: %d...", pid)
    beacon = get_default_connection()
    redis = beacon.get_redis_connection()
    try:
        session_name = current_session.name
    except AttributeError:
        raise RuntimeError("No current session, cannot attach flint")

    # Current URL
    key = get_flint_key(pid)
    value = redis.brpoplpush(key, key, timeout=30)
    if value is None:
        raise ValueError(
            f"flint: cannot retrieve Flint RPC server address from pid '{pid}`"
        )
    url = value.decode().split()[-1]

    # Return flint proxy
    FLINT_LOGGER.debug("Creating flint proxy...")
    proxy = rpc.Client(url)
    proxy.set_session(session_name)
    proxy._pid = pid

    FLINT.update({"proxy": proxy, "process": pid})

    greenlets = FLINT["greenlet"]
    if greenlets is not None:
        for g in greenlets:
            if g is not None:
                g.kill()

    g1 = gevent.spawn(
        log_process_output_to_logger,
        process,
        "stdout",
        FLINT_OUTPUT_LOGGER,
        logging.INFO,
    )
    g2 = gevent.spawn(
        log_process_output_to_logger,
        process,
        "stderr",
        FLINT_OUTPUT_LOGGER,
        logging.ERROR,
    )
    greenlets = (g1, g2)
    FLINT["greenlet"] = greenlets

    return proxy


def attach_flint(pid):
    """ attach to an external flint process, make a RPC proxy and bind Flint to the current session and return the FLINT proxy """
    process = psutil.Process(pid)
    proxy = _attach_flint(process)
    FLINT_LOGGER.debug("Flint proxy initialized")
    return proxy


def get_flint(start_new=False):
    """ get the running flint proxy or create one.
        use 'start_new=True' to force starting a new flint subprocess (which will be the new current one)"""

    process = None

    try:
        session_name = current_session.name
    except AttributeError:
        raise RuntimeError("No current session, cannot get flint")

    # Get redis connection
    if start_new:
        process = start_flint()
    else:
        # Did we run our flint?
        process = check_flint(session_name)
        if process is not None:
            # Was it already connected?
            if FLINT["process"] == process.pid:
                return FLINT["proxy"]
        else:
            process = start_flint()

    proxy = _attach_flint(process)
    FLINT_LOGGER.debug("Flint proxy initialized")
    return proxy


def reset_flint():
    proxy = FLINT.get("proxy")
    if proxy is not None:
        proxy.close()
    FLINT["proxy"] = None
    FLINT["process"] = None
    FLINT["greenlet"] = None


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
        if flint_pid:
            self._flint = attach_flint(flint_pid)
        else:
            self._flint = get_flint()

        # Create plot window
        if existing_id is None:
            self._plot_id = self._flint.add_plot(self.WIDGET, name)
        else:
            self._plot_id = existing_id

        # Create qt interface
        interface = self._flint.get_interface(self._plot_id)
        self.qt = QtInterface(interface, self.submit)

    def __repr__(self):
        return "{}(plot_id={!r}, flint_pid={!r}, name={!r})".format(
            self.__class__.__name__, self.plot_id, self.flint_pid, self.name
        )

    def submit(self, method, *args, **kwargs):
        return self._flint.run_method(self.plot_id, method, args, kwargs)

    # Properties

    @property
    def flint_pid(self):
        return self._flint._pid

    @property
    def plot_id(self):
        return self._plot_id

    @property
    def name(self):
        return self._flint.get_plot_name(self._plot_id)

    # Data handling

    def add_single_data(self, field, data):
        data = numpy.array(data)
        if data.ndim not in self.DATA_DIMENSIONS:
            raise ValueError(
                "Data dimension must be in {} (got {})".format(
                    self.DATA_DIMENSIONS, data.ndim
                )
            )
        return self._flint.update_data(self._plot_id, field, data)

    def add_data(self, data, field="default"):
        # Get fields
        if isinstance(data, dict):
            fields = list(data)
        else:
            fields = numpy.array(data).dtype.fields
        # Single data
        if fields is None:
            data_dict = dict([(field, data)])
        # Multiple data
        else:
            data_dict = dict((field, data[field]) for field in fields)
        # Send data
        for field, value in data_dict.items():
            self.add_single_data(field, value)
        # Return data dict
        return data_dict

    def remove_data(self, field):
        return self._flint.remove_data(self._plot_id, field)

    def select_data(self, *names, **kwargs):
        return self._flint.select_data(self._plot_id, self.METHOD, names, kwargs)

    def deselect_data(self, *names):
        return self._flint.deselect_data(self._plot_id, names)

    def clear_data(self):
        return self._flint.clear_data(self._plot_id)

    def get_data(self):
        return self._flint.get_data(self._plot_id)

    # Plotting

    def plot(self, data, **kwargs):
        fields = list(self.add_data(data))
        names = fields[: self.DATA_INPUT_NUMBER]
        self.select_data(*names, **kwargs)

    # Clean up

    def close(self):
        self._flint.remove_plot(self.plot_id)

    # Interaction

    def select_shapes(self, initial_selection=()):
        return self._flint.select_shapes(self._plot_id, initial_selection, timeout=None)

    def select_points(self, nb):
        return self._flint.select_points(self._plot_id, nb)

    def select_shape(self, shape):
        return self._flint.select_shape(self._plot_id, shape)

    def clear_selections(self):
        return self._flint.clear_selections(self._plot_id)

    # Instanciation

    @classmethod
    def instanciate(
        cls, data=None, name=None, existing_id=None, flint_pid=None, **kwargs
    ):
        plot = cls(name=name, existing_id=existing_id, flint_pid=flint_pid)
        if data is not None:
            plot.plot(data=data, **kwargs)
        return plot


# Plot classes


class CurvePlot(BasePlot):

    # Name of the corresponding silx widget
    WIDGET = "Plot1D"

    # Name of the method to add data to the plot
    METHOD = "addCurve"

    # The dimension of the data to plot
    DATA_DIMENSIONS = (1,)

    # Single / Multiple data handling
    MULTIPLE = True

    # Data input number for a single representation
    DATA_INPUT_NUMBER = 2

    # Specialized x data handling

    def plot(self, data, **kwargs):
        # Add data
        data_dict = self.add_data(data)
        # Get x field
        x = kwargs.pop("x", None)
        x_field = x if isinstance(x, str) else "x"
        # Get provided x
        if x_field in data_dict:
            x = data_dict[x_field]
        # Get default x
        elif x is None:
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
    WIDGET = "Plot1D"

    # Name of the method to add data to the plot
    METHOD = "addScatter"

    # The dimension of the data to plot
    DATA_DIMENSIONS = (1,)

    # Single / Multiple data handling
    MULTIPLE = True

    # Data input number for a single representation
    DATA_INPUT_NUMBER = 3


class CurveListPlot(BasePlot):

    # Name of the corresponding silx widget
    WIDGET = "CurvesView"

    # Name of the method to add data to the plot
    METHOD = None

    # The dimension of the data to plot
    DATA_DIMENSIONS = (2,)

    # Single / Multiple data handling
    MULTIPLE = False

    # Data input number for a single representation
    DATA_INPUT_NUMBER = 1


class ImagePlot(BasePlot):

    # Name of the corresponding silx widget
    WIDGET = "Plot2D"

    # Name of the method to add data to the plot
    METHOD = "addImage"

    # The dimension of the data to plot
    DATA_DIMENSIONS = 2, 3

    # Single / Multiple data handling
    MULTIPLE = True

    # Data input number for a single representation
    DATA_INPUT_NUMBER = 1


class HistogramImagePlot(BasePlot):

    # Name of the corresponding silx widget
    WIDGET = "ImageView"

    # Name of the method to add data to the plot
    METHOD = "setImage"

    # The dimension of the data to plot
    DATA_DIMENSIONS = (2,)

    # Single / Multiple data handling
    MULTIPLE = False

    # Data input number for a single representation
    DATA_INPUT_NUMBER = 1


class ImageStackPlot(BasePlot):

    # Name of the corresponding silx widget
    WIDGET = "StackView"

    # Name of the method to add data to the plot
    METHOD = "setStack"

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
plot_image_with_histogram = HistogramImagePlot.instanciate
plot_image_stack = ImageStackPlot.instanciate


def default_plot(data=None, **kwargs):
    kwargs["data"] = data
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
            default_plot(data=data[field], **kwargs) for field in data.dtype.fields
        )
    # Not recognized
    raise ValueError("Not recognized data")


# Alias
plot = default_plot


# Plotting: multi curves draw context manager


@contextmanager
def draw_manager(plot):
    try:
        # disable the silx auto_replot to avoid refreshing the GUI for each curve plot (when calling plot.select_data(...) )
        plot.submit("setAutoReplot", False)
        yield
    except AssertionError:
        # ignore eventual AssertionError raised by the rpc com
        pass
    finally:
        # re-enable the silx auto_replot
        plot.submit("setAutoReplot", True)
