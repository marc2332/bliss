# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
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
import contextlib
import gevent
import logging

import bliss
from bliss.comm import rpc
from bliss import current_session, is_bliss_shell, global_map
from bliss.config.conductor.client import get_default_connection
from bliss.flint.config import get_flint_key
from bliss.common import event
from bliss.flint import config as flint_config
from bliss.config.settings import HashSetting
from typing import List
from bliss.common.protocols import Scannable


try:
    from bliss.flint import poll_patch
except ImportError:
    poll_patch = None

FLINT_LOGGER = logging.getLogger("flint")
FLINT_OUTPUT_LOGGER = logging.getLogger("flint.output")
# Disable the flint output
FLINT_OUTPUT_LOGGER.setLevel(logging.INFO)
FLINT_OUTPUT_LOGGER.disabled = True


__all__ = [
    "plot",
    "plot_curve",
    "plot_curve_list",
    "plot_image",
    "plot_scatter",
    "plot_image_with_histogram",
    "plot_image_stack",
    "get_plotted_counters",
    "meshselect",
    "plotinit",
    "plotselect",
]

# Globals

FLINT = {"process": None, "proxy": None, "greenlet": None}

# Connection helpers


def get_beacon_config():
    beacon = get_default_connection()
    return "{}:{}".format(beacon._host, beacon._port)


def check_flint() -> bool:
    """
    Returns true if a Flint application from the current session is alive.
    """
    proxy = get_flint(creation_allowed=False)
    return proxy is not None


def _get_flint_pid_from_redis(session_name):
    """Check if an existing Flint process is running and attached to session_name.

    Returns:
        The process object from psutil.
    """
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
                return pid
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
    was_openned = False
    if hasattr(process, stream_name):
        # process come from subprocess, and was pipelined
        stream = getattr(process, stream_name)
    else:
        # process output was not pipelined.
        # Try to open a linux stream
        stream_id = 1 if stream_name == "stdout" else 2
        try:
            path = f"/proc/{process.pid}/fd/{stream_id}"
            stream = open(path, "r")
            was_openned = True
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
            if line[-1] == "\n":
                line = line[:-1]
            logger.log(level, "%s", line)
    except RuntimeError:
        # Process was terminated
        pass
    if stream is not None and was_openned and not stream.closed:
        stream.close()


def log_socket_output_to_logger(socket, logger, level):
    """Log the socket content into a logger until the socket is
    closed.

    Args:
        process: A process object from subprocess or from psutil modules.
        stream_name: One of "stdout" or "stderr".
        logger: A logger from logging module
        level: A value of logging
    """
    conn = None
    try:
        while True:
            conn, _address = socket.accept()
            while True:
                data = conn.recv(512)
                if not data:
                    break
                line = data.decode("utf-8")
                if len(line) >= 1 and line[-1] == "\n":
                    line = line[:-1]
                logger.log(level, "%s", line)
    except RuntimeError:
        pass
    if conn is not None:
        conn.close()


def _start_flint():
    """ Start the flint application in a subprocess.

    Returns:
        The process object"""

    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY", ""):
        FLINT_LOGGER.error(
            "DISPLAY environment variable have to be defined to launch Flint"
        )
        raise RuntimeError("DISPLAY environment variable is not defined")

    FLINT_LOGGER.warning("Flint starting...")
    env = dict(os.environ)
    env["BEACON_HOST"] = get_beacon_config()
    # NOTE: Mitigate problem on machines with many cores (>=32)
    #       Flint uses an incredible amount of CPU without this limitation
    # FIXME: Understand the problem properly
    env["OMP_NUM_THREADS"] = "4"
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
    for _ in range(3):
        value = redis.brpoplpush(key, key, timeout=5)
        if value is not None:
            break
    if value is None:
        raise ValueError(
            f"flint: cannot retrieve Flint RPC server address from pid '{pid}`"
        )
    url = value.decode().split()[-1]

    # Return flint proxy
    FLINT_LOGGER.debug("Creating flint proxy...")
    proxy = rpc.Client(url, timeout=3)

    remote_bliss_version = proxy.get_bliss_version()
    if bliss.release.version != remote_bliss_version:
        FLINT_LOGGER.warning(
            "Bliss and Flint version do not match (bliss version %s, flint version: %s).",
            bliss.release.version,
            remote_bliss_version,
        )
        FLINT_LOGGER.warning("You should restart Flint.")

    proxy.set_session(session_name)
    proxy._pid = pid

    FLINT.update({"proxy": proxy, "process": pid})

    greenlets = FLINT["greenlet"]
    if greenlets is not None:
        gevent.killall(greenlets)
    FLINT["greenlet"] = None
    FLINT["callbacks"] = None

    if hasattr(process, "stdout"):
        # process which comes from subprocess, and was pipelined
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
        FLINT["greenlet"] = (g1, g2)

    else:
        # Else we can use RPC events
        def stdout_callbacks(s):
            FLINT_OUTPUT_LOGGER.info("%s", s)

        def stderr_callbacks(s):
            FLINT_OUTPUT_LOGGER.error("%s", s)

        event.connect(proxy, "flint_stdout", stdout_callbacks)
        event.connect(proxy, "flint_stderr", stderr_callbacks)

        FLINT["callbacks"] = (stdout_callbacks, stderr_callbacks)

        try:
            proxy.register_output_listener()
        except:
            # FIXME: This have to be fixed or removed
            # See: https://gitlab.esrf.fr/bliss/bliss/issues/1249
            FLINT_LOGGER.error(
                "Error while connecting to stdout logs from Flint (issue #1249)"
            )
            FLINT_LOGGER.debug("Backtrace", exc_info=True)

    return proxy


def attach_flint(pid):
    """Attach to an external flint process, make a RPC proxy and bind Flint to
    the current session and return the FLINT proxy
    """
    if not psutil.pid_exists(pid):
        raise psutil.NoSuchProcess(pid, "Flint PID %s does not exist" % pid)
    process = psutil.Process(pid)
    proxy = _attach_flint(process)
    FLINT_LOGGER.debug("Flint proxy initialized")
    return proxy


def get_flint(start_new=False, creation_allowed=True):
    """Get the running flint proxy or create one.

    Arguments:
        start_new: If true, force starting a new flint subprocess (which will be
            the new current one)
        creation_allowed: If false, a new application will not be created.
    """
    try:
        session_name = current_session.name
    except AttributeError:
        raise RuntimeError("No current session, cannot get flint")

    check_redis = True
    if not start_new:
        FLINT_LOGGER.debug("Check cache")

        pid = FLINT.get("process")
        if pid is not None and psutil.pid_exists(pid):
            proxy = FLINT.get("proxy")
            if proxy is not None:
                try:
                    remote_session_name = proxy.get_session_name()
                except Exception:
                    FLINT_LOGGER.error("Error while reaching Flint API. Restart Flint.")
                    FLINT_LOGGER.debug("Backtrace", exc_info=True)
                else:
                    if session_name == remote_session_name:
                        return proxy

                # Do not use this Redis PID if is is already this one
                pid_from_redis = _get_flint_pid_from_redis(session_name)
                check_redis = pid_from_redis != pid

    if check_redis:
        pid = _get_flint_pid_from_redis(session_name)
        if pid is not None:
            try:
                return attach_flint(pid)
            except:
                FLINT_LOGGER.error(
                    "Impossible to attach Flint to the already existing PID %s", pid
                )
                raise

    if not creation_allowed:
        return None

    process = _start_flint()
    try:
        proxy = _attach_flint(process)
    except Exception:
        reset_flint()
        FLINT["proxy"] = None
        FLINT["process"] = None
        if hasattr(process, "stdout"):
            FLINT_LOGGER.error(
                "Flint can't start. You can enable the logs with the following line."
            )
            FLINT_LOGGER.error("    SCAN_DISPLAY.flint_output_enabled = True")
            FLINT_OUTPUT_LOGGER.error("---STDOUT---")
            print(type(log_process_output_to_logger))
            log_process_output_to_logger(
                process, "stdout", FLINT_OUTPUT_LOGGER, logging.ERROR
            )
            FLINT_OUTPUT_LOGGER.error("---STDERR---")
            log_process_output_to_logger(
                process, "stderr", FLINT_OUTPUT_LOGGER, logging.ERROR
            )
        raise

    FLINT_LOGGER.debug("Flint proxy initialized")
    proxy.wait_started()
    FLINT_LOGGER.debug("Flint proxy ready")
    return proxy


def reset_flint():
    proxy = FLINT.get("proxy")
    if proxy is not None:
        proxy.close()
    FLINT["proxy"] = None
    FLINT["process"] = None
    greenlets = FLINT["greenlet"]
    if greenlets is not None:
        gevent.killall(greenlets)
    FLINT["greenlet"] = None
    FLINT["callbacks"] = None


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

    def __init__(
        self,
        name=None,
        existing_id=None,
        flint_pid=None,
        closeable: bool = False,
        selected: bool = False,
    ):
        """Create a new custom plot based on the `silx` API.

        The plot will be created i a new tab on Flint.

        Arguments:
            existing_id: If set, the plot proxy will try to use an already
                exising plot, instead of creating a new one
            flint_pid: A specific Flint PID can be specified, else the default
                one is used
            name: Name of the plot as displayed in the tab header. It is not a
                unique name.
            selected: If true (not the default) the plot became the current
                displayed plot.
            closeable: If true (not the default), the tab can be closed manually
        """
        if flint_pid:
            self._flint = attach_flint(flint_pid)
        else:
            self._flint = get_flint()

        # Create plot window
        if existing_id is None:
            self._plot_id = self._flint.add_plot(
                cls_name=self.WIDGET, name=name, selected=selected, closeable=closeable
            )
        else:
            self._plot_id = existing_id

    def __repr__(self):
        try:
            # Protect problems on RPC
            name = self._flint.get_plot_name(self._plot_id)
        except Exception:
            name = None
        return "{}(plot_id={!r}, flint_pid={!r}, name={!r})".format(
            self.__class__.__name__, self.plot_id, self.flint_pid, name
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

    def _wait_for_user_selection(self, request_id):
        """Wait for a user selection and clean up result in case of error"""
        FLINT_LOGGER.warning("Waiting for selection in Flint window.")
        flint = self._flint
        results = gevent.queue.Queue()
        event.connect(flint, request_id, results.put)
        try:
            result = results.get()
            return result
        except Exception:
            flint.cancel_request(request_id)
            FLINT_LOGGER.warning("Plot selection cancelled. An error orrured.")
            raise
        except KeyboardInterrupt:
            flint.cancel_request(request_id)
            FLINT_LOGGER.warning("Plot selection cancelled by bliss user.")
            raise

    def select_shapes(self, initial_selection=()):
        flint = self._flint
        request_id = flint.request_select_shapes(self._plot_id, initial_selection)
        return self._wait_for_user_selection(request_id)

    def select_points(self, nb):
        flint = self._flint
        request_id = flint.request_select_points(self._plot_id, nb)
        return self._wait_for_user_selection(request_id)

    def select_shape(self, shape):
        flint = self._flint
        request_id = flint.request_select_shape(self._plot_id, shape)
        return self._wait_for_user_selection(request_id)

    # Instanciation

    @classmethod
    def instanciate(
        cls,
        data=None,
        name=None,
        existing_id=None,
        flint_pid=None,
        selected=False,
        closeable=False,
        **kwargs,
    ):
        plot = cls(
            name=name,
            existing_id=existing_id,
            flint_pid=flint_pid,
            closeable=closeable,
            selected=selected,
        )
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

    def update_axis_marker(
        self, unique_name: str, channel_name, position: float, text: str
    ):
        """Mark a location in a specific axis in this plot"""
        self._flint.update_axis_marker(
            self._plot_id, unique_name, channel_name, position, text
        )


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


class McaPlot(BasePlot):
    pass


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


def clean_up_user_data():
    """Helper to clean up the data stored in Redis and used by Flint.

    Flint should be able to deal with durty data, but in case of stronger
    problem this could help a lot (for example if the layout is really broken).

    As result all the saved user preferences will be lost.
    """
    session_name = current_session.name
    key = flint_config.get_workspace_key(session_name)

    beacon = get_default_connection()
    redis = beacon.get_redis_connection()

    # get existing flint, if any
    pattern = f"{key}*"
    for key in redis.scan_iter(pattern):
        key = key.decode()
        redis.delete(key)


@contextlib.contextmanager
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


### plotselect etc.


def plotinit(*counters):
    """
    Select counter(s) to use for the next scan display.

    Args:
        counters: String, alias, object identifying an object providing data to
            record. It can be a counter name, a counter, an axis, an alias.
    """
    from bliss.scanning.scan import ScanDisplay

    sd = ScanDisplay()
    channel_names = get_channel_names(*counters)
    sd.init_next_scan_meta(channel_names)


def plotselect(*counters):
    """
    Select counter(s) to use for:
    * alignment (bliss/common/scans.py:_get_selected_counter_name())
    * flint display (bliss/flint/plot1d.py)
    Saved as a HashSetting with '<session_name>:plot_select' key.

    Args:
        counters: String, alias, object identifying an object providing data to
            record. It can be a counter name, a counter, an axis, an alias.
    """

    plot_select = HashSetting("%s:plot_select" % current_session.name)
    channel_names = get_channel_names(*counters)
    counter_names = dict()
    for channel_name in channel_names:
        fullname = channel_name  # should be like: <controller.counter>
        counter_names[fullname] = "Y1"
    plot_select.set(counter_names)

    if check_flint():
        channel_names = get_channel_names(*counters)
        flint = get_flint()
        plot_id = flint.get_default_live_scan_plot("curve")
        if plot_id is not None:
            flint.set_displayed_channels(plot_id, channel_names)


def meshselect(*counters):
    """
    Select counter(s) to use for scatter :
    * alignment (bliss/common/scans.py:_get_selected_counter_name())
    * flint display (bliss/flint/plot1d.py)
    Saved as a HashSetting with '<session_name>:plot_select' key.
    """
    if check_flint():
        channel_names = get_channel_names(*counters)
        flint = get_flint()
        plot_id = flint.get_default_live_scan_plot("scatter")
        if plot_id is not None:
            flint.set_displayed_channels(plot_id, channel_names)


def get_plotted_counters():
    """
    Returns names of plotted counters as a list (get list from a HashSetting
    with '<session_name>:plot_select' key).
    """
    plot_select = HashSetting("%s:plot_select" % current_session.name)

    plotted_cnt_list = list()

    for cnt_name in plot_select.get_all():
        plotted_cnt_list.append(cnt_name)

    return plotted_cnt_list


def display_motor(axis, scan=None, position=None, label="", silent=True):
    from bliss.scanning.scan import ScanDisplay

    if scan is None:
        scan = current_session.scans[-1]
    scan_display_params = ScanDisplay()
    if is_bliss_shell() and scan_display_params.motor_position:
        try:
            channel_name = get_channel_name(axis)
        except ValueError:
            print(
                "The object %s have no obvious channel. Plot marker skiped." % (axis,)
            )
            channel_name = None
        if channel_name is not None:
            try:
                plot = get_plot(
                    axis, plot_type="curve", as_axes=True, scan=scan, silent=silent
                )
            except ValueError as e:
                if not silent:
                    raise e
                return

            if plot is not None:
                if position is None:
                    position = axis.position
                    if label == "":
                        label = "current\n" + str(position)
                plot.update_axis_marker(
                    channel_name, channel_name, position, text=label
                )


def get_channel_names(*objs) -> List[str]:
    """
    ?? returns a list containing aqc-channels names produced by provieded objects??
    # FIXME: For now only counters and axis are supported.
    """
    result: List[str] = []
    for obj in objs:
        # An object could contain many channels?
        channel_names: List[str] = []
        if isinstance(obj, str):
            alias = global_map.aliases.get(obj)
            if alias is not None:
                channel_names = get_channel_names(alias)
            else:
                channel_names = [obj]
        elif isinstance(obj, Scannable):
            channel_names = ["axis:%s" % obj.name]
        elif hasattr(obj, "fullname"):
            # Assume it's a counter
            channel_names = [obj.fullname]
        else:
            # FIXME: Add a warning
            pass
        result.extend(channel_names)
    return result


def get_channel_name(channel_item):
    """Return a channel name from a bliss object, else raises an exception

    If you are lucky the result is what you expect.

    Argument:
        channel_item: A bliss object which could have a channel during a scan.

    Return:
        A channel name identifying this object in scan data acquisition
    """
    if isinstance(channel_item, str):
        return channel_item
    if isinstance(channel_item, Scannable):
        return "axis:%s" % channel_item.name
    if hasattr(channel_item, "fullname"):
        return channel_item.fullname
    if hasattr(channel_item, "image"):
        return channel_item.image.fullname
    if hasattr(channel_item, "counter"):
        return channel_item.counter.fullname
    raise ValueError("Can't find channel name from object %s" % channel_item)

    # TODO: Why is this logic different than in get_channel_names?


def get_plot(
    channel_item, plot_type, scan=None, as_axes=False, wait=False, silent=False
):
    """Return the first plot object of type 'plot_type' showing the
    'channel_item' from Flint live scan view.

    Argument:
        channel_item: must be a channel
        plot_type: can be "image", "curve", "scatter", "mca"

    Keyword argument:
        as_axes (defaults to False): If true, reach a plot with this channel as
            X-axes (curves ans scatters), or Y-axes (scatter)
        wait (defaults to False): wait for plot to be shown

    Return:
        The expected plot, else None
    """
    # check that flint is running
    if not check_flint():
        if not silent:
            print("Flint is not started")
        return None

    if scan is None:
        scan = current_session.scans[-1]

    flint = get_flint()
    if wait:
        flint.wait_end_of_scans()
    try:
        channel_name = get_channel_name(channel_item)
    except ValueError:
        print("The object %s have no obvious channel." % (channel_item,))
        return None

    plot_id = flint.get_live_scan_plot(channel_name, plot_type, as_axes=as_axes)

    if plot_type == "curve":
        return CurvePlot(existing_id=plot_id)
    elif plot_type == "scatter":
        return ScatterPlot(existing_id=plot_id)
    elif plot_type == "mca":
        return McaPlot(existing_id=plot_id)
    elif plot_type == "image":
        return ImagePlot(existing_id=plot_id)
    else:
        print("Argument plot_type uses an invalid value: '%s'." % plot_type)
