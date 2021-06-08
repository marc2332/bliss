# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
"""
Provides plot helper class to deal with flint proxy.
"""

import typing
from typing import Union
from typing import Optional

import numpy
import gevent
import marshal
import inspect

from . import proxy
from bliss.common import event


class BasePlot(object):

    # Name of the corresponding silx widget
    WIDGET = NotImplemented

    # Available name to identify this plot
    ALIASES = []

    # Name of the method to add data to the plot
    METHOD = NotImplemented

    # The possible dimensions of the data to plot
    DATA_DIMENSIONS = NotImplemented

    # Single / Multiple data handling
    MULTIPLE = NotImplemented

    # Data input number for a single representation
    DATA_INPUT_NUMBER = NotImplemented

    def __init__(self, flint, plot_id, register=False):
        """Describe a custom plot handled by Flint.
        """
        self._plot_id = plot_id
        self._flint = flint
        self._xlabel = None
        self._ylabel = None
        self._init()
        if flint is not None:
            self._register(flint, plot_id, register)

    def _init(self):
        """Allow to initialize extra attributes in a derived class, without
        redefining the constructor"""
        pass

    class RemotePlot:
        """This class is serialized method by method and executed inside the Flint context"""

        def set_data(self, method, *names, **kwargs):
            data_dict = self.data()
            widget = self.widget()
            args = tuple(data_dict[name] for name in names)
            widget_method = getattr(widget, method)
            # Plot
            widget_method(*args, **kwargs)

        def update_data(self, field, data):
            data_dict = self.data()
            data_dict[field] = data

        def remove_data(self, field):
            data_dict = self.data()
            data_dict[field]

        def get_data(self, field=None):
            data_dict = self.data()
            if field is None:
                return data_dict
            else:
                return data_dict.get(field, [])

        def deselect_data(self, *names):
            widget = self.widget()
            legend = " -> ".join(names)
            widget.remove(legend)

        def clear_data(self):
            data_dict = self.data()
            widget = self.widget()
            data_dict.clear()
            widget.clear()

        def show_intensity_histogram(self, show: bool):
            widget = self.widget()
            widget.getIntensityHistogramAction().setVisible(show)

        def get_data_range(self):
            widget = self.widget()
            return widget.getDataRange()

    def _register(self, flint, plot_id, register):
        """Register everything needed remotely"""
        self.__remote = self._remotifyClass(self.RemotePlot, register=register)
        if register:
            self._init_plot()

    def _remote_plot(self):
        return self.__remote

    def _init_plot(self):
        """Inherits it to custom the plot initialization"""
        if self._xlabel is not None:
            self.submit("setGraphXLabel", self._xlabel)
        if self._ylabel is not None:
            self.submit("setGraphYLabel", self._ylabel)

    @property
    def title(self):
        return self._title

    @title.setter
    def title(self, txt):
        self._title = str(txt)
        self.submit("setGraphTitle", self._title)

    @property
    def xlabel(self):
        return self._xlabel

    @xlabel.setter
    def xlabel(self, txt):
        self._xlabel = str(txt)
        self.submit("setGraphXLabel", self._xlabel)

    @property
    def ylabel(self):
        return self._ylabel

    @ylabel.setter
    def ylabel(self, txt):
        self._ylabel = str(txt)
        self.submit("setGraphYLabel", self._ylabel)

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

    def focus(self):
        """Set the focus on this plot"""
        self._flint.set_plot_focus(self._plot_id)

    def export_to_logbook(self):
        """Set the focus on this plot"""
        self._flint.export_to_logbook(self._plot_id)

    # Data handling

    def upload_data(self, field, data):
        """
        Update data as an identifier into the server side

        Argument:
            field: Identifier in the targeted plot
            data: Data to upload
        """
        return self.__remote.update_data(field, data)

    def upload_data_if_needed(self, field, data):
        """Upload data only if it is a numpy array or a list
        """
        if isinstance(data, (numpy.ndarray, list)):
            self.__remote.update_data(field, data)
            return field
        else:
            return data

    def add_single_data(self, field, data):
        data = numpy.array(data)
        if (
            self.DATA_DIMENSIONS is not None
            and self.DATA_DIMENSIONS is not NotImplemented
        ):
            # FIXME: Testing the data here have no meaning
            # Because this only upload the data but do not describe how it will be used
            if data.ndim not in self.DATA_DIMENSIONS:
                raise ValueError(
                    "Data dimension must be in {} (got {})".format(
                        self.DATA_DIMENSIONS, data.ndim
                    )
                )
        return self.upload_data(field, data)

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
            self.upload_data(field, value)
        # Return data dict
        return data_dict

    def remove_data(self, field):
        self.__remote.remove_data(field)

    def select_data(self, *names, **kwargs):
        # FIXME: This have to be moved per plot widget
        if "legend" not in kwargs and self.METHOD.startswith("add"):
            kwargs["legend"] = " -> ".join(names)
        self.__remote.set_data(self.METHOD, *names, **kwargs)

    def deselect_data(self, *names):
        self.__remote.deselect_data(*names)

    def clear_data(self):
        self.__remote.clear_data()

    def get_data(self, field=None):
        return self.__remote.get_data(field=field)

    def get_data_range(self):
        """Returns the current data range used by this plot"""
        return self.__remote.get_data_range()

    # Plotting

    def plot(self, data, **kwargs):
        fields = list(self.add_data(data))
        names = fields[: self.DATA_INPUT_NUMBER]
        self.select_data(*names, **kwargs)

    # Clean up

    def is_open(self) -> bool:
        """Returns true if the plot is still open in the linked Flint
        application"""
        try:
            return self._flint.is_plot_exists(self._plot_id)
        except Exception:
            # The proxy is maybe dead
            return False

    def close(self):
        self._flint.remove_plot(self.plot_id)

    # Interaction

    def _wait_for_user_selection(self, request_id):
        """Wait for a user selection and clean up result in case of error"""
        proxy.FLINT_LOGGER.warning("Waiting for selection in Flint window.")
        flint = self._flint
        results = gevent.queue.Queue()
        event.connect(flint._proxy, request_id, results.put)
        try:
            result = results.get()
            return result
        except Exception:
            try:
                flint.cancel_request(request_id)
            except Exception:
                proxy.FLINT_LOGGER.debug(
                    "Error while canceling the request", exc_info=True
                )
                pass
            proxy.FLINT_LOGGER.warning("Plot selection cancelled. An error occurred.")
            raise
        except KeyboardInterrupt:
            try:
                flint.cancel_request(request_id)
            except Exception:
                proxy.FLINT_LOGGER.debug(
                    "Error while canceling the request", exc_info=True
                )
                pass
            proxy.FLINT_LOGGER.warning("Plot selection cancelled by bliss user.")
            raise

    def select_shapes(
        self,
        initial_selection: typing.Optional[typing.List[typing.Any]] = None,
        kinds: typing.Union[str, typing.List[str]] = "rectangle",
    ):
        """
        Request user selection of shapes.

        `initial_selection` is a list of ROIs from `bliss.controllers.lima.roi`.

        It also supports key-value dictionary for simple rectangle.
        In this case, the dictionary contains "kind" (which is "Rectangle"),
        and "label", "origin" and "size" which are tuples of 2 floats.

        Arguments:
            initial_selection: List of shapes already selected.
            kinds: List or ROI kind which can be created (for now, "rectangle"
                (described as a dict), "lima-rectangle", "lima-arc",
                "lima-vertical-profile",
                "lima-horizontal-profile")
        """
        flint = self._flint
        request_id = flint.request_select_shapes(
            self._plot_id, initial_selection, kinds=kinds
        )
        result = self._wait_for_user_selection(request_id)
        return result

    def select_points(self, nb):
        flint = self._flint
        request_id = flint.request_select_points(self._plot_id, nb)
        return self._wait_for_user_selection(request_id)

    def select_shape(self, shape):
        flint = self._flint
        request_id = flint.request_select_shape(self._plot_id, shape)
        return self._wait_for_user_selection(request_id)

    def _remotifyClass(self, remoteClass, register=True):
        class RemoteProxy:
            pass

        proxy = RemoteProxy()
        methods = inspect.getmembers(remoteClass, predicate=inspect.isfunction)
        for name, func in methods:
            handle = self._remotifyFunc(func, register=register)
            setattr(proxy, name, handle)

        return proxy

    def _remotifyFunc(self, func, register=True):
        """Make a function callable remotely"""
        method_id = func.__qualname__
        plot_id = self._plot_id
        if register:
            if func.__closure__:
                raise TypeError("Only function without closure are supported.")
            serialized_func = marshal.dumps(func.__code__)
            self._flint.register_custom_method(plot_id, method_id, serialized_func)

        def handler(*args, **kwargs):
            return self._flint.run_custom_method(plot_id, method_id, args, kwargs)

        return handler

    def _set_colormap(
        self,
        lut: Optional[str] = None,
        vmin: Optional[Union[float, str]] = None,
        vmax: Optional[Union[float, str]] = None,
        normalization: Optional[str] = None,
        gamma_normalization: Optional[float] = None,
        autoscale: Optional[bool] = None,
        autoscale_mode: Optional[str] = None,
    ):
        """
        Allows to setup the default colormap of this plot.

        Arguments:
            lut: A name of a LUT. At least the following names are supported:
                 `"gray"`, `"reversed gray"`, `"temperature"`, `"red"`, `"green"`,
                 `"blue"`, `"jet"`, `"viridis"`, `"magma"`, `"inferno"`, `"plasma"`.
            vmin: Can be a float or "`auto"` to set the min level value
            vmax: Can be a float or "`auto"` to set the max level value
            normalization: Can be on of `"linear"`, `"log"`, `"arcsinh"`,
                           `"sqrt"`, `"gamma"`.
            gamma_normalization: float defining the gamma normalization.
                                 If this argument is defined the `normalization`
                                 argument is ignored
            autoscale: If true, the auto scale is set for min and max
                       (vmin and vmax arguments are ignored)
            autoscale_mode: Can be one of `"minmax"` or `"3stddev"`
        """
        flint = self._flint
        flint.set_plot_colormap(
            self._plot_id,
            lut=lut,
            vmin=vmin,
            vmax=vmax,
            normalization=normalization,
            gammaNormalization=gamma_normalization,
            autoscale=autoscale,
            autoscaleMode=autoscale_mode,
        )


# Plot classes


class Plot1D(BasePlot):

    # Name of the corresponding silx widget
    WIDGET = "silx.gui.plot.Plot1D"

    # Available name to identify this plot
    ALIASES = ["curve", "plot1d"]

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

    def update_user_data(
        self, unique_name: str, channel_name: str, ydata: Optional[numpy.ndarray]
    ):
        """Add user data to a live plot.

        It will define a curve in the plot using the y-data provided and the
        x-data from the parent item (defined by the `channel_name`)

        The key `unique_name` + `channel_name` is unique. So if it already
        exists the item will be updated.

        Arguments:
            unique_name: Name of this item in the property tree
            channel_name: Name of the channel that will be used as parent for
                this item. If this parent item does not exist, it is created
                but set hidden.
            ydata: Y-data for this item. If `None`, if the item already exists,
                it is removed from the plot
        """
        if ydata is not None:
            ydata = numpy.asarray(ydata)
        self._flint.update_user_data(self._plot_id, unique_name, channel_name, ydata)

    def set_xaxis_scale(self, value):
        """
        Set the X-axis scale of this plot.

        Argument:
            value: One of "linear" or "log"
        """
        assert value in ("linear", "log")
        flint = self._flint
        flint.run_method(self._plot_id, "setXAxisLogarithmic", [value == "log"], {})

    def set_yaxis_scale(self, value):
        """
        Set the Y-axis scale of this plot.

        Argument:
            value: One of "linear" or "log"
        """
        assert value in ("linear", "log")
        flint = self._flint
        flint.run_method(self._plot_id, "setYAxisLogarithmic", [value == "log"], {})


class ScatterView(BasePlot):

    # Name of the corresponding silx widget
    WIDGET = "silx.gui.plot.ScatterView"

    # Available name to identify this plot
    ALIASES = ["scatter"]

    # Name of the method to add data to the plot
    METHOD = "addScatter"

    # The dimension of the data to plot
    DATA_DIMENSIONS = (1,)

    # Single / Multiple data handling
    MULTIPLE = True

    # Data input number for a single representation
    DATA_INPUT_NUMBER = 3

    def _init(self):
        # Make it public
        self.set_colormap = self._set_colormap


class Plot2D(BasePlot):

    # Name of the corresponding silx widget
    WIDGET = "silx.gui.plot.Plot2D"

    # Available name to identify this plot
    ALIASES = ["image", "plot2d"]

    # Name of the method to add data to the plot
    METHOD = "addImage"

    # The dimension of the data to plot
    DATA_DIMENSIONS = 2, 3

    # Single / Multiple data handling
    MULTIPLE = True

    # Data input number for a single representation
    DATA_INPUT_NUMBER = 1

    def _init(self):
        # Make it public
        self.set_colormap = self._set_colormap

    def _init_plot(self):
        super(ImagePlot, self)._init_plot()
        self.submit("setKeepDataAspectRatio", True)
        self._remote_plot().show_intensity_histogram(True)

    def select_mask(self, initial_mask: numpy.ndarray = None, directory: str = None):
        """Request a mask image from user selection.

        Argument:
            initial_mask: An initial mask image, else None
            directory: Directory used to import/export masks

        Return:
            A numpy array containing the user mask image
        """
        flint = self._flint
        request_id = flint.request_select_mask_image(
            self._plot_id, initial_mask, directory=directory
        )
        return self._wait_for_user_selection(request_id)


class CurveStack(BasePlot):
    # Name of the corresponding silx widget
    WIDGET = "bliss.flint.custom_plots.curve_stack.CurveStack"

    # Available name to identify this plot
    ALIASES = ["curvestack"]

    # Name of the method to add data to the plot
    METHOD = "setData"

    # Single / Multiple data handling
    MULTIPLE = False

    # Data input number for a single representation
    DATA_INPUT_NUMBER = 1

    def set_data(self, curves, x=None, reset_zoom=None):
        """
        Set the data displayed in this plot.

        Arguments:
            curves: The data of the curves (first dim is curve index, second dim
                    is the x index)
            x: Mapping of the real X axis values to use
            reset_zoom: If True force reset zoom, else the user selection is
                        applied
        """
        data_field = self.upload_data_if_needed("data", curves)
        x_field = self.upload_data_if_needed("x", x)
        self._remote_plot().set_data(
            self.METHOD, data_field, x_field, resetZoom=reset_zoom
        )


class TimeCurvePlot(BasePlot):
    # Name of the corresponding silx widget
    WIDGET = "bliss.flint.custom_plots.time_curve_plot.TimeCurvePlot"

    # Available name to identify this plot
    ALIASES = ["timecurveplot"]

    # Name of the method to add data to the plot
    METHOD = "appendData"

    # Single / Multiple data handling
    MULTIPLE = False

    # Data input number for a single representation
    DATA_INPUT_NUMBER = 1

    def select_x_axis(self, name: str):
        """
        Select the x-axis to use

        Arguments:
            name: Name of the data to use as x-axis
        """
        self.submit("setXName", name)

    def select_x_duration(self, second: int):
        """
        Select the x-axis duration in second

        Arguments:
            second: Amount of seconds displayed in the x-axis
        """
        self.submit("setXDuration", second)

    def select_curve(self, name, **kwargs):
        """
        Append the data displayed in this plot.

        Arguments:
            name: Name of the data to use as y-axis
            kwargs: Associated style (see `addCurve` from silx plot)
        """
        self.submit("selectCurve", name, **kwargs)

    def set_data(self, **kwargs):
        """
        Set the data displayed in this plot.

        Arguments:
            kwargs: Name of the data associated to the new numpy array to use
        """
        self.submit("setData", **kwargs)

    def append_data(self, **kwargs):
        """
        Append the data displayed in this plot.

        Arguments:
            kwargs: Name of the data associated to the numpy array to append
        """
        self.submit("appendData", **kwargs)


class ImageView(BasePlot):

    # Name of the corresponding silx widget
    WIDGET = "silx.gui.plot.ImageView"

    # Available name to identify this plot
    ALIASES = ["imageview", "histogramimage"]

    # Name of the method to add data to the plot
    METHOD = "setImage"

    # The dimension of the data to plot
    DATA_DIMENSIONS = (2,)

    # Single / Multiple data handling
    MULTIPLE = False

    # Data input number for a single representation
    DATA_INPUT_NUMBER = 1


class StackView(BasePlot):

    # Name of the corresponding silx widget
    WIDGET = "silx.gui.plot.StackView"

    # Available name to identify this plot
    ALIASES = ["stack", "imagestack"]

    # Name of the method to add data to the plot
    METHOD = "setStack"

    # The dimension of the data to plot
    DATA_DIMENSIONS = 3, 4

    # Single / Multiple data handling
    MULTIPLE = False

    # Data input number for a single representation
    DATA_INPUT_NUMBER = 1


class LiveCurvePlot(Plot1D):

    WIDGET = None

    ALIASES = ["curve"]


class LiveImagePlot(Plot2D):

    WIDGET = None

    ALIASES = ["image"]


class LiveScatterPlot(Plot1D):

    WIDGET = None

    ALIASES = ["scatter"]


class LiveMcaPlot(Plot1D):

    WIDGET = None

    ALIASES = ["mca"]


class LiveOneDimPlot(Plot1D):

    WIDGET = None

    ALIASES = ["onedim"]


CUSTOM_CLASSES = [
    Plot1D,
    Plot2D,
    ScatterView,
    ImageView,
    StackView,
    CurveStack,
    TimeCurvePlot,
]

LIVE_CLASSES = [
    LiveCurvePlot,
    LiveImagePlot,
    LiveScatterPlot,
    LiveMcaPlot,
    LiveOneDimPlot,
]

# For compatibility
CurvePlot = Plot1D
ImagePlot = Plot2D
ScatterPlot = ScatterView
HistogramImagePlot = ImageView
ImageStackPlot = StackView
