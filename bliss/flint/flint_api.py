# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
"""Module providing the Flint API exposed as RPC"""

from __future__ import annotations
from typing import Dict
from typing import TextIO

import sys
import socket
import logging
import itertools
import functools
import collections

import gevent.event

from silx.gui import qt
from silx.gui import plot as silx_plot
from silx.gui.plot.items.roi import RectangleROI

from bliss.flint.helper.plot_interaction import PointsSelector, ShapeSelector
from bliss.flint.widgets.roi_selection_widget import RoiSelectionWidget
from bliss.flint.helper import model_helper
from bliss.flint.model import plot_model
from bliss.flint.model import plot_item_model
from bliss.flint.model import flint_model

_logger = logging.getLogger(__name__)


class MultiplexStreamToSocket(TextIO):
    """Multiplex a stream to another stream and sockets"""

    def __init__(self, stream_output):
        self.__sockets = []
        self.__stream = stream_output

    def write(self, s):
        if len(self.__sockets) > 0:
            data = s.encode("utf-8")
            sockets = list(self.__sockets)
            for socket in sockets:
                try:
                    socket.send(data)
                except:
                    _logger.debug("Error while sending output", exc_info=True)
                    self.__sockets.remove(socket)
        self.__stream.write(s)

    def flush(self):
        self.__stream.flush()

    def add_listener(self, address):
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect(tuple(address))
        self.__sockets.append(client)


class FlintApi:
    """Flint interface, meant to be exposed through an RPC server."""

    # FIXME: Everything relative to GUI should be removed in order to only provide
    # RPC functions

    _id_generator = itertools.count()

    def __init__(self, flintModel: flint_model.FlintState):
        self.__flintModel = flintModel
        self.plot_dict: Dict[object, qt.QWidget] = {}
        self.plot_title: Dict[object, str] = {}
        self.data_event = collections.defaultdict(dict)
        self.selector_dict = collections.defaultdict(list)
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

    # Plot management

    def add_plot(self, cls_name, name=None):
        plot_id = self.create_new_id()
        if not name:
            name = "Plot %d" % plot_id
        new_tab_widget = self.__flintModel.mainWindow().createTab(name)
        qt.QVBoxLayout(new_tab_widget)
        cls = getattr(silx_plot, cls_name)
        plot = cls(new_tab_widget)
        self.plot_dict[plot_id] = plot
        self.plot_title[plot_id] = name
        new_tab_widget.layout().addWidget(plot)
        plot.show()
        return plot_id

    def get_plot_name(self, plot_id):
        return self.plot_title[plot_id]

    def remove_plot(self, plot_id):
        plot = self.plot_dict.pop(plot_id)
        plotParent = plot.parent()
        window = self.__flintModel.mainWindow()
        window.removeTab(plotParent)
        plot.close()

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

    def _get_plot_widget(self, plot_id, expect_silx_api=True):
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

        return self.plot_dict[plot_id]

    # User interaction

    def select_shapes(self, plot_id, initial_shapes=(), timeout=None):
        plot = self._get_plot_widget(plot_id)
        dock = self._create_roi_dock_widget(plot, initial_shapes)
        roi_widget = dock.widget()
        done_event = gevent.event.AsyncResult()

        roi_widget.selectionFinished.connect(
            functools.partial(self._selection_finished, done_event=done_event)
        )

        try:
            return done_event.get(timeout=timeout)
        finally:
            plot.removeDockWidget(dock)

    def _selection_finished(self, selections, done_event=None):
        shapes = []
        try:
            shapes = [
                dict(
                    origin=select.getOrigin(),
                    size=select.getSize(),
                    label=select.getLabel(),
                    kind=select._getKind(),
                )
                for select in selections
            ]
        finally:
            done_event.set_result(shapes)

    def _create_roi_dock_widget(self, plot, initial_shapes):
        roi_widget = RoiSelectionWidget(plot)
        dock = qt.QDockWidget("ROI selection")
        dock.setWidget(roi_widget)
        plot.addTabbedDockWidget(dock)
        for shape in initial_shapes:
            kind = shape["kind"]
            if kind == "Rectangle":
                roi = RectangleROI()
                roi.setGeometry(origin=shape["origin"], size=shape["size"])
                roi.setLabel(shape["label"])
                roi_widget.add_roi(roi)
            else:
                raise ValueError("Unknown shape of type {}".format(kind))
        dock.show()
        return dock

    def _selection(self, plot_id, cls, *args):
        # Instanciate selector
        plot = self._get_plot_widget(plot_id)
        selector = cls(plot)
        # Save it for future cleanup
        self.selector_dict[plot_id].append(selector)
        # Run the selection
        queue = gevent.queue.Queue()
        selector.selectionFinished.connect(queue.put)
        selector.start(*args)
        positions = queue.get()
        return positions

    def select_points(self, plot_id, nb):
        return self._selection(plot_id, PointsSelector, nb)

    def select_shape(self, plot_id, shape):
        return self._selection(plot_id, ShapeSelector, shape)

    def clear_selections(self, plot_id):
        for selector in self.selector_dict.pop(plot_id):
            selector.reset()
