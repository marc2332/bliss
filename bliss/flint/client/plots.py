# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
"""
Provides plot helper class to deal with flint proxy.
"""

import numpy
import typing
import gevent

from . import proxy
from bliss.common import event


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

    def __init__(self, flint, plot_id):
        """Describe a custom plot handled by Flint.
        """
        self._plot_id = plot_id
        self._flint = flint
        self._xlabel = None
        self._ylabel = None
        if flint is not None:
            self._init_plot()

    def _init_plot(self):
        """Inherits it to custom the plot initialization"""
        if self._xlabel is not None:
            self.submit("setGraphXLabel", self._xlabel)
        if self._ylabel is not None:
            self.submit("setGraphYLabel", self._ylabel)

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
        event.connect(flint, request_id, results.put)
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
        use_dict_as_result=True,
    ):
        """
        Request user selection of shapes.

        `initial_selection` is a list of ROIs from `bliss.controllers.lima.roi`.

        For compatibility, a rectangle ROI still can be described as a key-value
        dictionary. It contains "kind" (which is "Rectangle"), and "label",
            "origin" and "size" which are tuples of 2 floats.

        Arguments:
            initial_selection: List of shapes already selected.
            kinds: Kind of shapes the user can create
            use_dict_as_result: If True, rectangle ROIs are passed as a
                dictionary for compatibility. If false, a list of `bliss.controllers.lima.roi`
                only is always returned.
        """
        from bliss.controllers.lima import roi as lima_roi

        flint = self._flint

        if initial_selection is not None:
            initial_selection = list(initial_selection)
            # Retro compatibility
            for i, roi in enumerate(initial_selection):
                if not isinstance(roi, dict):
                    continue
                kind = roi["kind"].lower()
                assert kind == "rectangle"
                x, y = map(int, map(round, roi["origin"]))
                w, h = map(int, map(round, roi["size"]))
                name = roi.get["label"]
                roi = lima_roi.Roi(x, y, w, h, name)
                initial_selection[i] = roi

        request_id = flint.request_select_shapes(
            self._plot_id, initial_selection, kinds=kinds
        )
        result = self._wait_for_user_selection(request_id)

        if use_dict_as_result:
            # Retro compatibility
            for i, roi in enumerate(result):
                if not type(roi) == lima_roi.Roi:
                    continue
                roi = dict(
                    kind="Rectangle",
                    origin=(roi.x, roi.y),
                    size=(roi.width, roi.height),
                    label=roi.name,
                )
                result[i] = roi

        return result

    def select_points(self, nb):
        flint = self._flint
        request_id = flint.request_select_points(self._plot_id, nb)
        return self._wait_for_user_selection(request_id)

    def select_shape(self, shape):
        flint = self._flint
        request_id = flint.request_select_shape(self._plot_id, shape)
        return self._wait_for_user_selection(request_id)


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


class McaPlot(CurvePlot):
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

    def _init_plot(self):
        super(ImagePlot, self)._init_plot()
        self.submit("setKeepDataAspectRatio", True)

    def select_mask(self, initial_mask: numpy.ndarray = None):
        """Request a mask image from user selection.

        Argument:
            initial_mask: An initial mask image, else None
        Return:
            A numpy array containing the user mask image
        """
        flint = self._flint
        request_id = flint.request_select_mask_image(self._plot_id, initial_mask)
        return self._wait_for_user_selection(request_id)


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
