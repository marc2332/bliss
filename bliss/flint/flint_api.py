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

import sys
import logging
import itertools
import functools
import collections
import numpy

import gevent.event

from silx.gui import qt
from silx.gui import plot as silx_plot
import bliss
from bliss.flint.helper import plot_interaction, scan_info_helper
from bliss.controllers.lima import roi as lima_roi
from bliss.flint.helper import model_helper
from bliss.flint.model import plot_model
from bliss.flint.model import plot_item_model
from bliss.flint.model import flint_model
from bliss.common import event
from bliss.flint import config

_logger = logging.getLogger(__name__)


class CustomPlot(NamedTuple):
    """Store information to a plot created remotly and providing silx API."""

    plot: qt.QWidget
    tab: qt.QWidget
    title: str


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


class FlintApi:
    """Flint interface, meant to be exposed through an RPC server."""

    _id_generator = itertools.count()

    def __init__(self, flintModel: flint_model.FlintState):
        self.__requestCount = -1
        """Number of requests already created"""

        self.__requests: Dict[str, Request] = {}
        """Store the current requests"""

        self.__flintModel = flintModel
        # FIXME: _custom_plots should be owned by flint model or window
        self._custom_plots: Dict[object, CustomPlot] = {}
        self.data_event = collections.defaultdict(dict)
        self.data_dict = collections.defaultdict(dict)

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
        manager = self.__flintModel.mainManager()
        manager.updateBlissSessionName(session_name)

    def set_tango_metadata_name(self, name: str):
        manager = self.__flintModel.mainManager()
        manager.setTangoMetadataName(name)

    def get_session_name(self):
        model = self.__flintModel
        return model.blissSessionName()

    def wait_data(self, master, plot_type, index):
        ev = (
            self.data_event[master]
            .setdefault(plot_type, {})
            .setdefault(index, gevent.event.Event())
        )
        ev.wait(timeout=3)

    def get_live_scan_data(self, channel_name):
        scan = self.__flintModel.currentScan()
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
            plot = widget.plotModel()
            if plot is None:
                continue
            if not isinstance(plot, plot_class):
                continue
            return f"live:{iwidget}"

        # FIXME: If nothing found, a default plot should be created
        return None

    def get_live_scan_plot(
        self, channel_name: str, plot_type: str, as_axes: bool = False
    ):
        """Returns the identifier of a plot according to few constraints.
        """
        plot_class = self.__get_plot_class_by_kind(plot_type)
        workspace = self.__flintModel.workspace()
        for iwidget, widget in enumerate(workspace.widgets()):
            if not hasattr(widget, "scan"):
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
        plot = self._get_plot_widget(plot_id, expect_silx_api=True)
        method = getattr(plot, method)
        return method(*args, **kwargs)

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
        widget = self._get_plot_widget(plot_id, expect_silx_api=False, custom_plot=True)
        if widget is None:
            raise Exception("Widget %s not found" % plot_id)
        count = 0
        for item in widget._silxPlot().getItems():
            # Business items contains Flint in the name
            if "Flint" in str(type(item)):
                count += 1
        return count

    def test_active(self, plot_id, qaction: str = None):
        """Debug purpose function to simulate a click on an activable element.

        Arguments:
            plot_id:  The plot to interact with
            qaction: The action which will be processed. It have to be a
                children of the plot and referenced as it's object name.
        """
        plot = self._get_plot_widget(plot_id, expect_silx_api=True)
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
        plot = self._get_plot_widget(plot_id, expect_silx_api=True)
        from silx.gui.utils.testutils import QTest

        widget = plot.getWidgetHandle()
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

    # Plot management

    def is_plot_exists(self, plot_id) -> bool:
        if isinstance(plot_id, str) and plot_id.startswith("live:"):
            try:
                self._get_live_plot_widget(plot_id)
                return True
            except ValueError:
                return False
        else:
            return plot_id in self._custom_plots

    def add_plot(
        self,
        cls_name: str,
        name: str = None,
        selected: bool = False,
        closeable: bool = True,
    ):
        """Create a new custom plot based on the `silx` API.

        The plot will be created in a new tab on Flint.

        Arguments:
            cls_name: A class name defined by silx. Can be one of "PlotWidget",
                "PlotWindow", "Plot1D", "Plot2D", "ImageView", "StackView",
                "ScatterView".
            name: Name of the plot as displayed in the tab header. It is not a
                unique name.
            selected: If true (not the default) the plot became the current
                displayed plot.
            closeable: If true (default), the tab can be closed manually

        Returns:
            A plot_id
        """
        plot_id = self.create_new_id()
        if not name:
            name = "Plot %d" % plot_id
        new_tab_widget = self.__flintModel.mainWindow().createTab(
            name, selected=selected, closeable=closeable
        )
        # FIXME: Hack to know how to close the widget
        new_tab_widget._plot_id = plot_id
        qt.QVBoxLayout(new_tab_widget)
        cls = getattr(silx_plot, cls_name)
        plot = cls(new_tab_widget)
        self._custom_plots[plot_id] = CustomPlot(plot, new_tab_widget, name)
        new_tab_widget.layout().addWidget(plot)
        plot.show()
        return plot_id

    def get_plot_name(self, plot_id):
        if isinstance(plot_id, str) and plot_id.startswith("live:"):
            widget = self._get_live_plot_widget(plot_id)
            return widget.windowTitle()
        return self._custom_plots[plot_id].title

    def remove_plot(self, plot_id):
        custom_plot = self._custom_plots.pop(plot_id)
        window = self.__flintModel.mainWindow()
        window.removeTab(custom_plot.tab)
        custom_plot.plot.close()

    def get_interface(self, plot_id):
        plot = self._get_plot_widget(plot_id)
        names = dir(plot)
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
            unique_name: Name of the marker to edit
            plot_id: Identifier of the plot
            channel_name: Name of the channel which is used as an axis by this
                marker
            position: Position in this axis. If the position is None or not
                finite, the marker is removed (or not created)
            text: A text label  for the marker
        """
        plot = self._get_plot_widget(plot_id, expect_silx_api=False)
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

    def update_data(self, plot_id, field, data):
        self.data_dict[plot_id][field] = data

    def remove_data(self, plot_id, field):
        del self.data_dict[plot_id][field]

    def get_data(self, plot_id, field=None):
        if field is None:
            return self.data_dict[plot_id]
        else:
            return self.data_dict[plot_id].get(field, [])

    def select_data(self, plot_id, method, names, kwargs):
        plot = self._get_plot_widget(plot_id)
        # Hackish legend handling
        if "legend" not in kwargs and method.startswith("add"):
            kwargs["legend"] = " -> ".join(names)
        # Get the data to plot
        args = tuple(self.data_dict[plot_id][name] for name in names)
        method = getattr(plot, method)
        # Plot
        method(*args, **kwargs)

    def deselect_data(self, plot_id, names):
        plot = self._get_plot_widget(plot_id)
        legend = " -> ".join(names)
        plot.remove(legend)

    def clear_data(self, plot_id):
        del self.data_dict[plot_id]
        plot = self._get_plot_widget(plot_id)
        plot.clear()

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

        if not data.flags.writeable:
            # Image from the network should be writable
            # FIXME: this should be fixed on our RPC
            data = numpy.array(data)

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

    def _get_plot_widget(self, plot_id, expect_silx_api=True, custom_plot=False):
        # FIXME: Refactor it, it starts to be ugly
        if isinstance(plot_id, str) and plot_id.startswith("live:"):
            widget = self._get_live_plot_widget(plot_id)
            if not expect_silx_api:
                return widget
            if not hasattr(widget, "_silxPlot"):
                raise ValueError(
                    f"The widget associated to '{plot_id}' do not provide a silx API"
                )
            return widget._silxPlot()

        if not expect_silx_api:
            raise ValueError(
                f"The widget associated to '{plot_id}' only provides a silx API"
            )

        if custom_plot:
            return self._custom_plots[plot_id]
        return self._custom_plots[plot_id].plot

    # API to custom default live plots

    def set_displayed_channels(self, plot_id, channel_names):
        """Enforce channels to be displayed.

        - If a channel was not part of the plot, an item is added
        - If a channel was hidden, it become visible
        - If a channel is in the plot but not part of this list, it is removed
        """
        widget = self._get_plot_widget(plot_id, expect_silx_api=False, custom_plot=True)
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

        A shape is described as a ROI object from `bliss.controllers.lima.roi`.

        Arguments:
            plot_id: Identifier of the plot
            initial_shapes: A list of shapes describing the current selection.
            timeout: A timeout to enforce the user to do a selection
            kinds: List or ROI kind which can be created (for now, "rectangle",
                "arc", "rectangle-vertical-profile", "rectangle-horizontal-profile")

        Return:
            This method returns an event name which have to be registered to
            reach the result.

            The event event is list of shapes describing the selection
        """
        plot = self._get_plot_widget(plot_id, expect_silx_api=True)
        selector = plot_interaction.ShapesSelector(plot)
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
        plot = self._get_plot_widget(plot_id, expect_silx_api=True)
        selector = plot_interaction.PointsSelector(plot)
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
        plot = self._get_plot_widget(plot_id, expect_silx_api=True)
        selector = plot_interaction.ShapeSelector(plot)
        selector.setShapeSelection(shape)
        return self.__request_selector(plot_id, selector)

    def request_select_mask_image(
        self, plot_id, initial_mask: numpy.ndarray = None, timeout=None
    ) -> str:
        """
        Request a shape selection in a specific plot and return the selection.

        A shape is described by a dictionary containing "origin", "size", "kind" (which is "Rectangle), and "label".

        Arguments:
            plot_id: Identifier of the plot
            initial_mask: A 2d boolean array, or None
            timeout: A timeout to enforce the user to do a selection

        Return:
            This method returns an event name which have to be registered to
            reach the result.

            The event is a numpy.array describing the selection
        """
        plot = self._get_plot_widget(plot_id, expect_silx_api=True)
        selector = plot_interaction.MaskImageSelector(plot)
        if initial_mask is not None:
            selector.setInitialMask(initial_mask, copy=False)
        selector.setTimeout(timeout)
        return self.__request_selector(plot_id, selector)

    def __request_selector(self, plot_id, selector: plot_interaction.Selector) -> str:
        custom_plot = self._get_plot_widget(plot_id, custom_plot=True)

        # Set the focus as an user input is requested
        if isinstance(custom_plot, CustomPlot):
            plot = custom_plot.plot
            # Set the focus as an user input is requested
            window = self.__flintModel.mainWindow()
            window.setFocusOnPlot(custom_plot.tab)
        else:
            window = self.__flintModel.mainWindow()
            window.setFocusOnLiveScan()
            plot = custom_plot

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
