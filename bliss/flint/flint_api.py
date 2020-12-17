# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
"""Module providing the Flint API exposed as RPC"""

from __future__ import annotations
from typing import Dict
from typing import Sequence
from typing import Tuple
from typing import List
from typing import Union
from typing import TextIO
from typing import NamedTuple
from typing import Optional

import sys
import types
import logging
import importlib
import itertools
import functools
import numpy
import marshal

from silx.gui import qt
import bliss
from bliss.flint.helper import plot_interaction, scan_info_helper
from bliss.controllers.lima import roi as lima_roi
from bliss.flint.helper import model_helper
from bliss.flint.model import scan_model
from bliss.flint.model import plot_model
from bliss.flint.model import plot_item_model
from bliss.flint.model import plot_state_model
from bliss.flint.model import flint_model
from bliss.common import event
from bliss.flint import config
from bliss.flint.widgets.custom_plot import CustomPlot

_logger = logging.getLogger(__name__)


class Request(NamedTuple):
    """Store information about a request."""

    plot: qt.QWidget
    request_id: str
    selector: plot_interaction.Selector


class MultiplexStreamToCallback(TextIO):
    """Multiplex a stream to another stream and sockets"""

    def __init__(self, stream_output):
        self.__listener = None
        self.__stream = stream_output

    def write(self, s):
        if self.__listener is not None:
            self.__listener(s)
        self.__stream.write(s)

    def flush(self):
        self.__stream.flush()

    def has_listener(self):
        return self.__listener is not None

    def set_listener(self, listener):
        self.__listener = listener


def _aswritablearray(data):
    """Returns a writable numpy array. Create a copy if the array is in read-only.

    Numpy array from the network looks to be non-writable.

    This should be fixed in the RPC layer.
    """
    if data is None:
        return None
    data = numpy.asarray(data)
    if not data.flags.writeable:
        data = numpy.array(data)
    return data


class FlintApi:
    """Flint interface, meant to be exposed through an RPC server."""

    _id_generator = itertools.count()

    def __init__(self, flintModel: flint_model.FlintState):
        self.__requestCount = -1
        """Number of requests already created"""

        self.__requests: Dict[str, Request] = {}
        """Store the current requests"""

        self.__flintModel = flintModel

        self.stdout = MultiplexStreamToCallback(sys.stdout)
        sys.stdout = self.stdout
        self.stderr = MultiplexStreamToCallback(sys.stderr)
        sys.stderr = self.stderr

    def get_bliss_version(self) -> str:
        """Returns the bliss version"""
        return bliss.release.version

    def get_flint_api_version(self) -> int:
        """Returns the flint API version"""
        return config.FLINT_API_VERSION

    def register_output_listener(self):
        """Register output listener to ask flint to emit signals for stdout and
        stderr.
        """
        if self.stdout.has_listener():
            return
        self.stdout.set_listener(self.__stdout_to_events)
        self.stderr.set_listener(self.__stderr_to_events)

    def __stdout_to_events(self, s):
        event.send(self, "flint_stdout", s)

    def __stderr_to_events(self, s):
        event.send(self, "flint_stderr", s)

    def create_new_id(self):
        return next(self._id_generator)

    def set_session(self, session_name):
        self.wait_started()
        manager = self.__flintModel.mainManager()
        manager.updateBlissSessionName(session_name)

    def set_tango_metadata_name(self, name: str):
        manager = self.__flintModel.mainManager()
        manager.setTangoMetadataName(name)

    def get_session_name(self):
        model = self.__flintModel
        return model.blissSessionName()

    def get_live_scan_data(self, channel_name):
        scan = self.__flintModel.currentScan()
        if isinstance(scan, scan_model.ScanGroup):
            scan = scan.subScans()[-1]
        if scan is None:
            raise RuntimeError("No scan available")
        channel = scan.getChannelByName(channel_name)
        if channel is None:
            raise ValueError(f"Channel {channel_name} is not part of this scan")
        data = channel.data()
        if data is None:
            # Just no data
            return None
        return data.array()

    def __get_widget_class_by_kind(self, plot_type: str):
        if plot_type == "image":
            from bliss.flint.widgets.image_plot import ImagePlotWidget

            return ImagePlotWidget
        elif plot_type == "mca":
            from bliss.flint.widgets.mca_plot import McaPlotWidget

            return McaPlotWidget
        raise ValueError(f"Unknown widget for plot type '{plot_type}'")

    def __get_plot_class_by_kind(self, plot_type: str):
        assert plot_type in ["scatter", "image", "curve", "mca"]
        plot_classes = {
            "scatter": plot_item_model.ScatterPlot,
            "image": plot_item_model.ImagePlot,
            "mca": plot_item_model.McaPlot,
            "curve": plot_item_model.CurvePlot,
        }
        return plot_classes[plot_type]

    def get_default_live_scan_plot(self, plot_type):
        """Returns the identifier of the default plot according it's type.

        Basically returns the first plot of this kind.

        Returns `None` is nothing found
        """
        plot_class = self.__get_plot_class_by_kind(plot_type)
        workspace = self.__flintModel.workspace()
        for iwidget, widget in enumerate(workspace.widgets()):
            if not hasattr(widget, "scan") or not hasattr(widget, "plotModel"):
                # Skip widgets which does not display scans (like profile)
                # FIXME: Use interface to flag classes
                continue
            plot = widget.plotModel()
            if plot is None:
                continue
            if not isinstance(plot, plot_class):
                continue
            return f"live:{iwidget}"

        # FIXME: If nothing found, a default plot should be created
        return None

    def get_live_plot_detector(
        self, detector_name: str, plot_type: str, create: bool = True
    ):
        """Returns the widget used for a specific detector and plot type.

        Arguments:
            detector_name: Name of the detector
            plot_type: "image" or "mca"
            create: If true, the plot is created if not found.
        """
        if plot_type not in ["image", "mca"]:
            return TypeError(f"Unexpected plot kind '{plot_type}' for detector plot")
        widget_class = self.__get_widget_class_by_kind(plot_type)
        workspace = self.__flintModel.workspace()
        for iwidget, widget in enumerate(workspace.widgets()):
            if not hasattr(widget, "scan") or not hasattr(widget, "plotModel"):
                # Skip widgets which does not display scans (like profile)
                # FIXME: Use interface to flag classes
                continue
            if not hasattr(widget, "scan") or not hasattr(widget, "deviceName"):
                # Skip widgets which does not display scans (like profile)
                # FIXME: Use interface to flag classes
                continue
            if not isinstance(widget, widget_class):
                continue
            if widget.deviceName() != detector_name:
                continue
            return f"live:{iwidget}"

        if create:
            # The widget was not found, we can create it
            # scan = monitoring.StaticImageScan(None, channel_name)
            manager = self.__flintModel.mainManager()
            plot_class = self.__get_plot_class_by_kind(plot_type)
            plot = plot_class()
            plot.setDeviceName(detector_name)
            scan = None
            manager.updateWidgetsWithPlots(scan, [plot], True, None)
            iwidget = len(workspace.widgets()) - 1
            return f"live:{iwidget}"

        raise ValueError(
            f"A dedicated {plot_type} widget for the detector {detector_name} is not available"
        )

    def get_live_scan_plot(
        self, channel_name: str, plot_type: str, as_axes: bool = False
    ):
        """Returns the identifier of a plot according to few constraints.
        """
        plot_class = self.__get_plot_class_by_kind(plot_type)
        workspace = self.__flintModel.workspace()
        for iwidget, widget in enumerate(workspace.widgets()):
            if not hasattr(widget, "scan") or not hasattr(widget, "plotModel"):
                # Skip widgets which does not display scans (like profile)
                # FIXME: Use interface to flag classes
                continue
            scan = widget.scan()
            if scan is None:
                continue
            channel = scan.getChannelByName(channel_name)
            if channel is None:
                continue
            plot = widget.plotModel()
            if plot is None:
                continue
            if not isinstance(plot, plot_class):
                continue
            if as_axes:
                found = model_helper.isChannelUsedAsAxes(plot, channel)
            else:
                found = model_helper.isChannelDisplayedAsValue(plot, channel)
            if found:
                return f"live:{iwidget}"

        # FIXME: Here we could create a specific plot
        raise ValueError("The channel '%s' is not part of any plots" % channel_name)

    def wait_end_of_scans(self):
        scanManager = self.__flintModel.scanManager()
        scanManager.wait_end_of_scans()

    def wait_started(self):
        """Wait for the end of the initialization at startup of the application.
        """
        manager = self.__flintModel.mainManager()
        manager.waitFlintStarted()

    def run_method(self, plot_id, method, args, kwargs):
        plot = self._get_plot_widget(plot_id)
        silxPlot = plot._silxPlot()
        method = getattr(silxPlot, method)
        return method(*args, **kwargs)

    def run_custom_method(self, plot_id, method_id, args, kwargs):
        """Run a registered method from a custom plot.
        """
        plot = self._get_plot_widget(plot_id, live_plot=False)
        return plot.runMethod(method_id, args, kwargs)

    def register_custom_method(self, plot_id, method_id, serialized_method):
        """Register a method to a custom plot.
        """
        plot = self._get_plot_widget(plot_id, live_plot=False)
        code = marshal.loads(serialized_method)
        method = types.FunctionType(code, globals(), "deserialized_function")
        plot.registerMethod(method_id, method)

    def ping(self, msg=None, stderr=False):
        """Debug function to check writing on stdout/stderr remotely."""
        if stderr:
            stream = sys.stderr
        else:
            stream = sys.stdout
        if msg is None:
            msg = "PONG"
        stream.write("%s\n" % msg)
        stream.flush()

    def test_count_displayed_items(self, plot_id):
        """Debug purpose function to count number of displayed items in a plot
        widget."""
        widget = self._get_plot_widget(plot_id)
        if widget is None:
            raise Exception("Widget %s not found" % plot_id)
        count = 0
        for item in widget._silxPlot().getItems():
            # Business items contains Flint in the name
            if "Flint" in str(type(item)):
                count += 1
        return count

    def test_displayed_channel_names(self, plot_id):
        """Debug purpose function to returns displayed channels from a live plot widget."""
        widget = self._get_plot_widget(plot_id, custom_plot=False)
        if widget is None:
            raise Exception("Widget %s not found" % plot_id)
        plot = widget.plotModel()
        if plot is None:
            return []
        return model_helper.getChannelNamesDisplayedAsValue(plot)

    def test_active(self, plot_id, qaction: str = None):
        """Debug purpose function to simulate a click on an activable element.

        Arguments:
            plot_id:  The plot to interact with
            qaction: The action which will be processed. It have to be a
                children of the plot and referenced as it's object name.
        """
        plot = self._get_plot_widget(plot_id)
        action: qt.QAction = plot.findChild(qt.QAction, qaction)
        action.trigger()

    def test_mouse(
        self,
        plot_id,
        mode: str,
        position: Tuple[int, int],
        relative_to_center: bool = True,
    ):
        """Debug purpose function to simulate a mouse click in the center of the
        plot.

        Arguments:
            plot_id:  The plot to interact with
            mode: One of 'click', 'press', 'release', 'move'
            position: Expected position of the mouse
            relative_to_center: If try the position is relative to center
        """
        plot = self._get_plot_widget(plot_id)
        silxPlot = plot._silxPlot()
        from silx.gui.utils.testutils import QTest

        widget = silxPlot.getWidgetHandle()
        assert relative_to_center is True
        rect = qt.QRect(qt.QPoint(0, 0), widget.size())
        base = rect.center()
        position = base + qt.QPoint(position[0], position[1])
        modifier = qt.Qt.KeyboardModifiers()
        if mode == "click":
            QTest.mouseClick(widget, qt.Qt.LeftButton, modifier, position)
        elif mode == "press":
            QTest.mousePress(widget, qt.Qt.LeftButton, modifier, position)
        elif mode == "release":
            QTest.mouseRelease(widget, qt.Qt.LeftButton, modifier, position)
        elif mode == "release":
            QTest.mouseMove(widget, position)

    def test_log_error(self, msg):
        """Debug purpose function to log a message into the default logging
        system"""
        _logger.error("%s", msg)

    # Plot management

    def is_plot_exists(self, plot_id) -> bool:
        if isinstance(plot_id, str) and plot_id.startswith("live:"):
            try:
                self._get_live_plot_widget(plot_id)
                return True
            except ValueError:
                return False
        else:
            window = self.__flintModel.mainWindow()
            custom_plot = window.customPlot(plot_id)
            return custom_plot is not None

    def add_plot(
        self,
        class_name: str,
        name: str = None,
        selected: bool = False,
        closeable: bool = True,
        unique_name: str = None,
    ) -> str:
        """Create a new custom plot based on the `silx` API.

        The plot will be created in a new tab on Flint.

        Arguments:
            class_name: A class to display a plot. Can be one of:
                "silx.gui.plot.Plot1D", "silx.gui.plot.Plot2D",
                "silx.gui.plot.ImageView", "silx.gui.plot.StackView",
                "silx.gui.plot.ScatterView".
            name: Name of the plot as displayed in the tab header. It is not a
                unique name.
            selected: If true (not the default) the plot became the current
                displayed plot.
            closeable: If true (default), the tab can be closed manually
            unique_name: Unique name for this new plot

        Returns:
            A plot_id
        """
        if unique_name is None:
            unique_name = "custom_plot:%d" % self.create_new_id()
        if not name:
            name = "%s" % unique_name

        def get_class(class_name):
            try:
                module_name, class_name = class_name.rsplit(".", 1)
                module = importlib.import_module(module_name)
                class_obj = getattr(module, class_name)
                return class_obj
            except Exception:
                _logger.debug(
                    "Error while reaching class name '%s'", class_name, exc_info=True
                )
                raise ValueError("Unknown class name %s" % class_name)

        class_obj = get_class(class_name)
        window = self.__flintModel.mainWindow()
        plot = class_obj(parent=window)
        window.createCustomPlot(
            plot, name, unique_name, selected=selected, closeable=closeable
        )
        return unique_name

    def get_plot_name(self, plot_id):
        widget = self._get_plot_widget(plot_id)
        if isinstance(widget, CustomPlot):
            return widget.name()
        else:
            return widget.windowTitle()

    def remove_plot(self, plot_id):
        window = self.__flintModel.mainWindow()
        return window.removeCustomPlot(plot_id)

    def get_interface(self, plot_id):
        plot = self._get_plot_widget(plot_id)
        silxPlot = plot._silxPlot()
        names = dir(silxPlot)
        # Deprecated attrs
        removes = ["DEFAULT_BACKEND"]
        for r in removes:
            if r in names:
                names.remove(r)
        return [
            name
            for name in names
            if not name.startswith("_")
            if callable(getattr(plot, name))
        ]

    # Data management

    def update_axis_marker(
        self, plot_id, unique_name: str, channel_name: str, position: float, text: str
    ):
        """Update the location of an axis marker in a plot.

        Arguments:
            plot_id: Identifier of the plot
            unique_name: Name of the marker to edit
            channel_name: Name of the channel which is used as an axis by this
                marker
            position: Position in this axis. If the position is None or not
                finite, the marker is removed (or not created)
            text: A text label  for the marker
        """
        plot = self._get_plot_widget(plot_id, custom_plot=False)
        model = plot.plotModel()
        if model is None:
            raise Exception("No model linked to this plot")

        with model.transaction():
            # Clean up previous item
            for i in list(model.items()):
                if isinstance(i, plot_item_model.AxisPositionMarker):
                    if i.unique_name() == unique_name:
                        model.removeItem(i)
                        break
            # Create the new marker
            if position is not None and numpy.isfinite(position):
                item = plot_item_model.AxisPositionMarker(model)
                ref = plot_model.ChannelRef(item, channel_name)
                item.initProperties(unique_name, ref, position, text)
                model.addItem(item)

    def update_user_data(
        self, plot_id, unique_name: str, channel_name: str, ydata: numpy.array
    ):
        """Add user data to a live plot.

        It will define a curve in the plot using the y-data provided and the
        x-data from the parent item (defined by the `channel_name`)

        The key `unique_name` + `channel_name` is unique. So if it already
        exists the item will be updated.

        Arguments:
            plot_id: Identifier of the plot
            unique_name: Name of this item in the property tree
            channel_name: Name of the channel that will be used as parent for
                this item. If this parent item does not exist, it is created
                but set hidden.
            ydata: Y-data for this item. If `None`, if the item already exists,
                it is removed from the plot
        """
        ydata = _aswritablearray(ydata)
        plot = self._get_plot_widget(plot_id, custom_plot=False)
        model = plot.plotModel()
        if model is None:
            raise Exception("No model linked to this plot")

        scan = plot.scan()
        if scan is None:
            raise Exception("No scan linked to this plot")

        channel = scan.getChannelByName(channel_name)
        if channel is None:
            raise Exception("Channel name '%s' does not exists")

        with model.transaction():
            # Get the item on which attach the user item
            for parentItem in list(model.items()):
                if not isinstance(parentItem, plot_item_model.CurveItem):
                    continue
                channelRef = parentItem.yChannel()
                if channelRef is None:
                    continue
                if channelRef.name() != channel_name:
                    continue
                break
            else:
                parentItem = None

            # Search for previous user item
            if parentItem is not None:
                for userItem in list(model.items()):
                    if not isinstance(userItem, plot_state_model.UserValueItem):
                        continue
                    if not userItem.isChildOf(parentItem):
                        continue
                    if userItem.name() != unique_name:
                        continue
                    break
                else:
                    userItem = None
            else:
                userItem = None

            if userItem is not None:
                if ydata is not None:
                    userItem.setYArray(ydata)
                else:
                    model.removeItem(userItem)
            else:
                if ydata is not None:
                    if parentItem is None:
                        parentItem, _updated = model_helper.createCurveItem(
                            model, channel, yAxis="left"
                        )
                        # It was not there before, so hide it
                        parentItem.setVisible(False)

                    userItem = plot_state_model.UserValueItem(model)
                    userItem.setName(unique_name)
                    userItem.setYArray(ydata)
                    userItem.setSource(parentItem)
                    model.addItem(userItem)
                else:
                    # Nothing to do
                    pass

    def start_image_monitoring(self, channel_name, tango_address):
        """Start monitoring of an image from a Tango detector.

        The widget used to display result of the image scan for this detector
        will be used to display the monitoring of the camera.

        Arguments:
            channel_name: Identifier of the channel in Redis. It is used to
                find the right plot in Flint.
            tango_address: Address of the Lima Tango server
        """
        from .manager import monitoring

        scan = monitoring.MonitoringScan(None, channel_name, tango_address)
        manager = self.__flintModel.mainManager()
        plots = scan_info_helper.create_plot_model(scan.scanInfo(), scan)
        manager.updateWidgetsWithPlots(scan, plots, True, None)
        scan.startMonitoring()

    def stop_image_monitoring(self, channel_name):
        """Stop monitoring of an image from a Tango detector.

        Arguments:
            channel_name: Identifier of the channel in Redis. It is used to
                find the right plot in Flint.
        """
        plot_id = self.get_live_scan_plot(channel_name, "image")
        if plot_id is None:
            raise RuntimeError("The channel name is not part of any widget")
        from .manager import monitoring

        plot = self._get_live_plot_widget(plot_id)
        scan = plot.scan()
        if not isinstance(scan, monitoring.MonitoringScan):
            raise RuntimeError("Unexpected scan type %s" % type(scan))

        scan.stopMonitoring()

    def set_static_image(self, channel_name, data):
        """Update the displayed image data relative to a channel name.

        This can be use to display a custom image to a detector, in case
        the processing was done in BLISS side.
        """
        from .manager import monitoring

        data = _aswritablearray(data)
        scan = monitoring.StaticImageScan(None, channel_name)
        manager = self.__flintModel.mainManager()
        plots = scan_info_helper.create_plot_model(scan.scanInfo(), scan)
        manager.updateWidgetsWithPlots(scan, plots, True, None)
        scan.setData(data)

    def _get_live_plot_widget(self, plot_id):
        if not isinstance(plot_id, str) or not plot_id.startswith("live:"):
            raise ValueError(f"'{plot_id}' is not a valid plot_id")

        workspace = self.__flintModel.workspace()
        try:
            iwidget = int(plot_id[5:])
            if iwidget < 0:
                raise ValueError()
        except Exception:
            raise ValueError(f"'{plot_id}' is not a valid plot_id")
        widgets = list(workspace.widgets())
        if iwidget >= len(widgets):
            raise ValueError(f"'{plot_id}' is not anymore available")
        widget = widgets[iwidget]
        return widget

    def _get_plot_widget(self, plot_id: str, live_plot=None, custom_plot=None):
        """Get a plot widget (widget while hold a plot) from this `plot_id`

        Arguments:
            plot_id: Id of a plot
            live_plot: If this filter is set, a live plot is returned only if
                       it's set to True
            custom_plot: If this filter is set, a custom plot is returned only
                         if it's set to True
        """
        if live_plot in [None, True]:
            if isinstance(plot_id, str) and plot_id.startswith("live:"):
                widget = self._get_live_plot_widget(plot_id)
                return widget
        if custom_plot in [None, True]:
            window = self.__flintModel.mainWindow()
            customPlot = window.customPlot(plot_id)
            if customPlot is not None:
                return customPlot
        return None

    # API to custom default live plots

    def set_displayed_channels(self, plot_id, channel_names):
        """Enforce channels to be displayed.

        - If a channel was not part of the plot, an item is added
        - If a channel was hidden, it become visible
        - If a channel is in the plot but not part of this list, it is removed
        """
        widget = self._get_plot_widget(plot_id)
        if widget is None:
            raise ValueError("Widget %s not found" % plot_id)

        plot = widget.plotModel()
        if plot is None:
            raise ValueError("Widget %s is not linked to any plot model" % plot_id)

        scan = widget.scan()
        model_helper.updateDisplayedChannelNames(plot, scan, channel_names)

    # User interaction

    def __create_request_id(self):
        self.__requestCount += 1
        return "flint_api_request_%d" % self.__requestCount

    def request_select_shapes(
        self,
        plot_id,
        initial_shapes: Sequence[lima_roi._BaseRoi] = (),
        kinds: Union[str, List[str]] = "rectangle",
        timeout=None,
    ) -> str:
        """
        Request a shape selection in a specific plot and return the selection.

        A shape is described as a ROI object from `bliss.controllers.lima.roi`,
        or a dictionary for shapes.

        Arguments:
            plot_id: Identifier of the plot
            initial_shapes: A list of shapes describing the current selection.
            timeout: A timeout to enforce the user to do a selection
            kinds: List or ROI kind which can be created (for now, "rectangle"
                   (described as a dict), "lima-rectangle", "lima-arc",
                   "lima-vertical-profile", "lima-horizontal-profile")

        Return:
            This method returns an event name which have to be registered to
            reach the result. The event result is list of shapes describing the
            selection.
        """
        plot = self._get_plot_widget(plot_id)
        silxPlot = plot._silxPlot()
        selector = plot_interaction.ShapesSelector(silxPlot)
        if isinstance(kinds, str):
            kinds = [kinds]
        selector.setKinds(kinds)
        selector.setInitialShapes(initial_shapes)
        selector.setTimeout(timeout)
        return self.__request_selector(plot_id, selector)

    def request_select_points(self, plot_id, nb: int) -> str:
        """
        Request the selection of points.

        Arguments:
            plot_id: Identifier of the plot
            nb: Number of points requested

        Return:
            This method returns an event name which have to be registered to
            reach the result.

            The event result is list of points describing the selection. A point
            is defined by a tuple of 2 floats (x, y). If nothing is selected an
            empty sequence is returned.
        """
        plot = self._get_plot_widget(plot_id)
        silxPlot = plot._silxPlot()
        selector = plot_interaction.PointsSelector(silxPlot)
        selector.setNbPoints(nb)
        return self.__request_selector(plot_id, selector)

    def request_select_shape(self, plot_id, shape: str) -> str:
        """
        Request the selection of a single shape.

        Arguments:
            plot_id: Identifier of the plot
            shape: The kind of shape requested ("rectangle", "line", "polygon",
                "hline", "vline")

        Return:
            This method returns an event name which have to be registered to
            reach the result.

            The event result is a list of points describing the selected shape.
            A point is defined by a tuple of 2 floats (x, y). If nothing is
            selected an empty sequence is returned.
        """
        plot = self._get_plot_widget(plot_id)
        silxPlot = plot._silxPlot()
        selector = plot_interaction.ShapeSelector(silxPlot)
        selector.setShapeSelection(shape)
        return self.__request_selector(plot_id, selector)

    def request_select_mask_image(
        self,
        plot_id,
        initial_mask: numpy.ndarray = None,
        timeout=None,
        directory: str = None,
    ) -> str:
        """
        Request a shape selection in a specific plot and return the selection.

        A shape is described by a dictionary containing "origin", "size", "kind" (which is "Rectangle), and "label".

        Arguments:
            plot_id: Identifier of the plot
            initial_mask: A 2d boolean array, or None
            timeout: A timeout to enforce the user to do a selection
            directory: Directory used to import/export masks

        Return:
            This method returns an event name which have to be registered to
            reach the result.

            The event is a numpy.array describing the selection
        """
        plot = self._get_plot_widget(plot_id)
        silxPlot = plot._silxPlot()
        selector = plot_interaction.MaskImageSelector(silxPlot)
        initial_mask = _aswritablearray(initial_mask)
        if initial_mask is not None:
            selector.setInitialMask(initial_mask, copy=False)
        if directory:
            selector.setDirectory(directory)
        selector.setTimeout(timeout)
        return self.__request_selector(plot_id, selector)

    def __request_selector(self, plot_id, selector: plot_interaction.Selector) -> str:
        plot = self._get_plot_widget(plot_id)

        # Set the focus as an user input is requested
        window = self.__flintModel.mainWindow()
        if isinstance(plot, CustomPlot):
            # Set the focus as an user input is requested
            window.setFocusOnPlot(plot)
        else:
            window = self.__flintModel.mainWindow()
            window.setFocusOnLiveScan()

        request_id = self.__create_request_id()
        request = Request(plot, request_id, selector)
        self.__requests[request_id] = request

        # Start the task
        selector.selectionFinished.connect(
            functools.partial(self.__request_validated, request_id)
        )
        selector.start()
        return request_id

    def cancel_request(self, request_id):
        """
        Stop the `request_id` selection.

        As result the selection is removed and the user can't have anymore
        feedback.
        """
        request = self.__requests.pop(request_id, None)
        if request is not None:
            request.selector.stop()

    def clear_request(self, request_id):
        """
        Clear the `request_id` selection.

        This selection still have to be completed by the user.
        """
        request = self.__requests.get(request_id)
        if request is not None:
            request.selector.reset()

    def __request_validated(self, request_id: str):
        """Callback when the request is validated"""
        request = self.__requests.pop(request_id, None)
        if request is not None:
            selector = request.selector
            event.send(self, request_id, selector.selection())
            request.selector.stop()

    def close_application(self):
        """Close flint"""
        window = self.__flintModel.mainWindow()
        window.close()

    def set_window_focus(self):
        """Set the focus to the Flint window"""
        window = self.__flintModel.mainWindow()
        window.activateWindow()
        window.setFocus(qt.Qt.OtherFocusReason)

    def set_plot_focus(self, plot_id):
        """Set the focus on a plot"""
        widget = self._get_plot_widget(plot_id)
        if widget is None:
            raise ValueError("Widget %s not found" % plot_id)
        model = self.__flintModel
        window = model.mainWindow()
        if isinstance(widget, CustomPlot):
            window.setFocusOnPlot(widget)
        else:
            window.setFocusOnLiveScan()
            widget.show()
            widget.raise_()
            widget.setFocus(qt.Qt.OtherFocusReason)

    def set_plot_colormap(
        self,
        plot_id,
        lut: Optional[str] = None,
        vmin: Optional[Union[float, str]] = None,
        vmax: Optional[Union[float, str]] = None,
        normalization: Optional[str] = None,
        gammaNormalization: Optional[float] = None,
        autoscale: Optional[bool] = None,
        autoscaleMode: Optional[str] = None,
    ):
        """
        Allows to setup the default colormap of a widget.
        """
        widget = self._get_plot_widget(plot_id)
        if not hasattr(widget, "defaultColormap"):
            raise TypeError("Widget %s does not expose a colormap" % plot_id)

        colormap = widget.defaultColormap()
        if lut is not None:
            colormap.setName(lut)
        if vmin is not None:
            if vmin == "auto":
                vmin = None
            colormap.setVMin(vmin)
        if vmax is not None:
            if vmax == "auto":
                vmax = None
            colormap.setVMax(vmax)
        if normalization is not None:
            colormap.setNormalization(normalization)
        if gammaNormalization is not None:
            colormap.setGammaNormalizationParameter(gammaNormalization)
            colormap.setNormalization("gamma")
        if autoscale is not None:
            if autoscale:
                colormap.setVRange(None, None)
        if autoscaleMode is not None:
            colormap.setAutoscaleMode(autoscaleMode)

    def export_to_logbook(self, plot_id):
        """Export a plot to the logbook if available"""
        widget = self._get_plot_widget(plot_id, custom_plot=False)
        if widget is None:
            raise ValueError("Widget %s not found" % plot_id)
        if not hasattr(widget, "logbookAction"):
            raise RuntimeError("This widget do not allow export to logbook")
        action = widget.logbookAction()
        if not action.isEnabled():
            raise RuntimeError("Logbook action is not enabled")
        action.trigger()

    def get_workspace(self) -> str:
        """Returns the current used workspace"""
        workspace = self.__flintModel.workspace()
        return workspace.name()

    def load_workspace(self, name: str) -> bool:
        """Load a workspace by it's name.

        Raises a ValueError is the name is not an available workspace

        Returns true if it was successfully loaded.
        """
        manager = self.__flintModel.mainManager()
        wmanager = manager.workspaceManager()
        if not wmanager.isWorkspace(name):
            raise ValueError("Workspace '%s' does not exist" % name)
        wmanager.loadWorkspace(name)
        return self.get_workspace() == name
