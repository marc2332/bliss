# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
"""Module providing the Flint API exposed as RPC"""

from __future__ import annotations
from typing import Dict
from typing import Sequence
from typing import Tuple
from typing import Optional
from typing import TextIO
from typing import NamedTuple

import sys
import socket
import logging
import itertools
import functools
import collections

import gevent.event

from silx.gui import qt
from silx.gui import plot as silx_plot
from bliss.flint.helper import plot_interaction
from bliss.flint.helper import model_helper
from bliss.flint.model import plot_model
from bliss.flint.model import plot_item_model
from bliss.flint.model import flint_model
from bliss.common import event

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


class MultiplexStreamToSocket(TextIO):
    """Multiplex a stream to another stream and sockets"""

    def __init__(self, stream_output):
        self.__sockets = []
        self.__stream = stream_output

    def write(self, s):
        if len(self.__sockets) > 0:
            data = s.encode("utf-8")
            sockets = list(self.__sockets)
            for sock in sockets:
                try:
                    sock.send(data)
                except:
                    _logger.debug("Error while sending output", exc_info=True)
                    self.__sockets.remove(sock)
        self.__stream.write(s)

    def flush(self):
        self.__stream.flush()

    def add_listener(self, address):
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect(tuple(address))
        self.__sockets.append(client)


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

        self.stdout = MultiplexStreamToSocket(sys.stdout)
        sys.stdout = self.stdout
        self.stderr = MultiplexStreamToSocket(sys.stderr)
        sys.stderr = self.stderr

    def add_output_listener(self, stdout_address, stderr_address):
        """Add socket based listeners to receive stdout and stderr from flint
        """
        self.stdout.add_listener(stdout_address)
        self.stderr.add_listener(stderr_address)

    def create_new_id(self):
        return next(self._id_generator)

    def set_session(self, session_name):
        manager = self.__flintModel.mainManager()
        manager.updateBlissSessionName(session_name)

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
            raise Exception("No scan available")
        channel = scan.getChannelByName(channel_name)
        if channel is None:
            raise Exception(f"Channel {channel_name} is not part of this scan")
        data = channel.data()
        if data is None:
            # Just no data
            return None
        return data.array()

    def get_live_scan_plot(self, channel_name, plot_type, as_axes=False):
        assert plot_type in ["scatter", "image", "curve", "mca"]

        plot_class = {
            "scatter": plot_item_model.ScatterPlot,
            "image": plot_item_model.ImagePlot,
            "mca": plot_item_model.McaPlot,
            "curve": plot_item_model.CurvePlot,
        }[plot_type]

        scan = self.__flintModel.currentScan()
        if scan is None:
            raise Exception("No scan displayed")

        channel = scan.getChannelByName(channel_name)
        if channel is None:
            raise Exception(
                "The channel '%s' is not part of the current scan" % channel_name
            )

        workspace = self.__flintModel.workspace()
        for iwidget, widget in enumerate(workspace.widgets()):
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
        raise Exception("The channel '%s' is not part of any plots" % channel_name)

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

    def test_mouse(
        self,
        plot_id,
        mode: str,
        position: Tuple[int, int],
        relative_to_center: bool = True,
    ):
        """Debug purpose function to simulate a mouse click in the center of the
        plot

        Arguments:
            plot_id:  The plot to interact with
            mode: One of 'click', 'press', 'release', 'move'
            position: Expected position of the mouse
            relative_to_center: If try the position is relative to center
        """
        plot = self._get_plot_widget(plot_id, expect_silx_api=True)
        from silx.gui.utils.testutils import QTest

        widget = plot.getWidgetHandle()
        assert relative_to_center == True
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

    def add_plot(self, cls_name, name=None):
        plot_id = self.create_new_id()
        if not name:
            name = "Plot %d" % plot_id
        new_tab_widget = self.__flintModel.mainWindow().createTab(name)
        qt.QVBoxLayout(new_tab_widget)
        cls = getattr(silx_plot, cls_name)
        plot = cls(new_tab_widget)
        self._custom_plots[plot_id] = CustomPlot(plot, new_tab_widget, name)
        new_tab_widget.layout().addWidget(plot)
        plot.show()
        return plot_id

    def get_plot_name(self, plot_id):
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

    def update_motor_marker(
        self, plot_id, channel_name: str, position: float, text: str
    ):
        plot = self._get_plot_widget(plot_id, expect_silx_api=False)
        model = plot.plotModel()
        if model is None:
            raise Exception("No model linked to this plot")

        with model.transaction():
            # Clean up previous items
            for i in list(model.items()):
                if isinstance(i, plot_item_model.MotorPositionMarker):
                    model.removeItem(i)
            # Create the new indicator
            item = plot_item_model.MotorPositionMarker(model)
            ref = plot_model.ChannelRef(item, channel_name)
            item.initProperties(ref, position, text)
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

    def _get_plot_widget(self, plot_id, expect_silx_api=True, custom_plot=False):
        # FIXME: Refactor it, it starts to be ugly
        if isinstance(plot_id, str) and plot_id.startswith("live:"):
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

    # User interaction

    def __create_request_id(self):
        self.__requestCount += 1
        return "flint_api_request_%d" % self.__requestCount

    def request_select_shapes(
        self, plot_id, initial_shapes: Sequence[Dict] = (), timeout=None
    ) -> str:
        """
        Request a shape selection in a specific plot and return the selection.

        A shape is described by a dictionary containing "origin", "size", "kind" (which is "Rectangle), and "label".

        Arguments:
            plot_id: Identifier of the plot
            initial_shapes: A list of shapes describing the current selection. Only Rectangle are supported.
            timeout: A timeout to enforce the user to do a selection

        Return:
            This method returns an event name which have to be registered to
            reach the result.

            The event event is list of shapes describing the selection
        """
        plot = self._get_plot_widget(plot_id, expect_silx_api=True)
        selector = plot_interaction.ShapesSelector(plot)
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
        """Callback when the request is validaed"""
        request = self.__requests.pop(request_id, None)
        if request is not None:
            selector = request.selector
            event.send(self, request_id, selector.selection())
            request.selector.stop()
