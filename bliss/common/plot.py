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

from typing import List

import numpy
import functools

from bliss import current_session, is_bliss_shell, global_map
from bliss.common.protocols import Scannable
from bliss.common.utils import get_matching_names, is_pattern
from bliss.scanning.scan_display import ScanDisplay

from bliss.flint.client import plots as flint_plots
from bliss.flint.client import proxy as flint_proxy

from bliss.flint.client.proxy import FLINT_LOGGER
from bliss.flint.client.proxy import FLINT_OUTPUT_LOGGER  # noqa: F401


__all__ = [
    "plot",
    "plot_curve",
    "plot_image",
    "plot_scatter",
    "plot_image_with_histogram",
    "plot_image_stack",
    "get_plotted_counters",
    "meshselect",
    "plotinit",
    "plotselect",
]

get_flint = flint_proxy.get_flint
check_flint = flint_proxy.check_flint
attach_flint = flint_proxy.attach_flint
reset_flint = flint_proxy.close_flint
close_flint = flint_proxy.close_flint
restart_flint = flint_proxy.restart_flint


def _create_plot(
    plot_class,
    data=None,
    name=None,
    existing_id=None,
    selected=False,
    closeable=True,
    **kwargs,
):
    flint = flint_proxy.get_flint()
    plot = flint.get_plot(
        plot_class,
        name=name,
        unique_name=existing_id,
        selected=selected,
        closeable=closeable,
    )
    if data is not None:
        plot.plot(data=data, **kwargs)
    return plot


plot_curve = functools.partial(_create_plot, flint_plots.CurvePlot)
plot_scatter = functools.partial(_create_plot, flint_plots.ScatterPlot)
plot_image = functools.partial(_create_plot, flint_plots.ImagePlot)
plot_image_with_histogram = functools.partial(
    _create_plot, flint_plots.HistogramImagePlot
)
plot_image_stack = functools.partial(_create_plot, flint_plots.ImageStackPlot)


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


### plotselect etc.


def plotinit(*counters):
    """
    Select counter(s) to use for the next scan display. Does not affect the current display.

    Args:
        counters: String, alias, object identifying an object providing data to
            record. It can be a counter name, a counter, an axis, an alias.
    """
    scan_display = current_session.scan_display
    if len(counters) == 0:
        channel_names = None
    else:
        channel_names = get_channel_names(*counters)
    scan_display.next_scan_displayed_channels = channel_names


def plotselect(*counters):
    """
    Select counter(s) to use for:
    * alignment (bliss/common/scans.py:_get_selected_counter_name())
    * scan display (tool binded with F5)
    * flint

    Args:
        counters: String, alias, object identifying an object providing data to
            record. It can be a counter name, a counter, an axis, an alias.
    """
    scan_display = ScanDisplay()
    channel_names = get_channel_names(*counters)
    scan_display.displayed_channels = channel_names

    if flint_proxy.check_flint():
        flint = flint_proxy.get_flint(mandatory=False)
        # Make it safe
        if flint is not None:
            try:
                plot_id = flint.get_default_live_scan_plot("curve")
                if plot_id is not None:
                    flint.set_displayed_channels(plot_id, channel_names)
            except:
                FLINT_LOGGER.error("Error while executing plotselect", exc_info=True)


def meshselect(*counters):
    """
    Select counter(s) to use for scatter :
    * alignment (bliss/common/scans.py:_get_selected_counter_name())
    * flint display (bliss/flint/plot1d.py)
    """
    if flint_proxy.check_flint():
        channel_names = get_channel_names(*counters)
        flint = flint_proxy.get_flint(mandatory=False)
        # Make it safe
        if flint is not None:
            plot_id = flint.get_default_live_scan_plot("scatter")
            if plot_id is not None:
                flint.set_displayed_channels(plot_id, channel_names)


def get_plotted_counters():
    """
    Returns names of displayed counters.
    """
    scan_display = ScanDisplay()
    return scan_display.displayed_channels


def get_next_plotted_counters():
    """
    Returns names of counters that will be plotted for the next scan.
    """
    scan_display = current_session.scan_display
    displayed_channels = scan_display.next_scan_displayed_channels
    if displayed_channels is None:
        return []
    else:
        return displayed_channels


def display_motor(
    axis, scan=None, position=None, marker_id=None, label="", silent=True
):
    if scan is None:
        scan = current_session.scans[-1]
    scan_display_params = ScanDisplay()
    if is_bliss_shell() and scan_display_params.motor_position:
        try:
            channel_name = get_channel_name(axis)
        except ValueError:
            if not silent:
                print(
                    "The object %s have no obvious channel. Plot marker skiped."
                    % (axis,)
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
                if marker_id is None:
                    marker_name = channel_name
                else:
                    marker_name = channel_name + "_" + marker_id
                plot.update_axis_marker(marker_name, channel_name, position, text=label)


def get_channel_names(*objs) -> List[str]:
    """
    Returns a list of channel names.

    Arguments:
        objs: This can be axis or counter objects, plus channel names or channel
              names with escape chars like `*` or `?`.
    Result:
        A list of channel names, without validation (it could not exists).
    """
    all_objects: List[str] = []
    result: List[str] = []
    for obj in objs:
        # An object could contain many channels?
        channel_names: List[str] = []
        if isinstance(obj, str):
            if is_pattern(obj):
                if len(all_objects) == 0:
                    all_objects += [
                        "axis:" + n for n in global_map.get_axes_names_iter()
                    ]
                    all_objects += [c.fullname for c in global_map.get_counters_iter()]
                channel_names = get_matching_names([obj], all_objects)[obj]
            else:
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
        for c in channel_names:
            if c not in result:
                result.append(c)
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
    """Return the first plot object of type `plot_type` showing the
    `channel_item` from Flint live scan view.

    Arguments:
        channel_item: must be a channel
        plot_type: can be `"image"`, `"curve"`, `"scatter"`, `"mca"`
        as_axes: If true, reach a plot with this channel as X-axes (curves and
                 scatters), or Y-axes (scatter)
        wait: wait for plot to be shown
    Return:
        The expected plot, else None
    """
    # check that flint is running
    if not flint_proxy.check_flint():
        if not silent:
            print("Flint is not started")
        return None

    if scan is None:
        scan = current_session.scans[-1]

    flint = flint_proxy.get_flint()
    if wait:
        flint.wait_end_of_scans()
    try:
        channel_name = get_channel_name(channel_item)
    except ValueError:
        print("The object %s have no obvious channel." % (channel_item,))
        return None

    plot_id = flint.get_live_scan_plot(channel_name, plot_type, as_axes=as_axes)

    if plot_type == "curve":
        return flint_plots.CurvePlot(flint=flint, plot_id=plot_id)
    elif plot_type == "scatter":
        return flint_plots.ScatterPlot(flint=flint, plot_id=plot_id)
    elif plot_type == "mca":
        return flint_plots.McaPlot(flint=flint, plot_id=plot_id)
    elif plot_type == "image":
        return flint_plots.ImagePlot(flint=flint, plot_id=plot_id)
    else:
        print("Argument plot_type uses an invalid value: '%s'." % plot_type)
