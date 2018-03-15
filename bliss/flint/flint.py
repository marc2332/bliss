# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

# Imports
import os
import sys
import types
import logging
import platform
import tempfile
import warnings
import itertools
import contextlib
import collections

import numpy
import gevent
import gevent.event
import zerorpc
import msgpack_numpy
import gevent.monkey
from concurrent.futures import Future

from bliss.data.scan import watch_session_scans
from bliss.flint.executor import QtExecutor
from bliss.flint.executor import concurrent_to_gevent
from bliss.flint.executor import qt_safe
from bliss.flint.executor import create_queue_from_qt_signal
from bliss.flint.executor import disconnect_queue_from_qt_signal
from bliss.config.conductor.client import get_default_connection

try:
    from PyQt4.QtCore import pyqtRemoveInputHook
except ImportError:
    from PyQt5.QtCore import pyqtRemoveInputHook

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from silx.gui import plot as silx_plot
    from silx.gui import qt

from .interaction import PointsSelector, ShapeSelector

# Globals

msgpack_numpy.patch()
pyqtRemoveInputHook()
Thread = gevent.monkey.get_original('threading', 'Thread')
Event = gevent.monkey.get_original('threading', 'Event')


# Gevent functions

@contextlib.contextmanager
def safe_rpc_server(obj):
    with tempfile.NamedTemporaryFile(delete=False) as f:
        url = 'ipc://{}'.format(f.name)
        server = zerorpc.Server(obj)
        try:
            server.bind(url)
            task = gevent.spawn(server.run)
            try:
                yield task, url
            finally:
                task.kill()
                task.join()
        finally:
            server.close()


@contextlib.contextmanager
def maintain_value(key, value):
    beacon = get_default_connection()
    redis = beacon.get_redis_connection()
    redis.lpush(key, value)
    try:
        yield
    finally:
        redis.lrem(key, value)


def background_task(flint, stop):
    key = "flint:{}:{}".format(platform.node(), os.getpid())
    stop = concurrent_to_gevent(stop)
    with safe_rpc_server(flint) as (task, url):
        with maintain_value(key, url):
            gevent.wait([stop, task], count=1)


# Flint interface

def qt_safe_class(cls=None, ignore=()):
    """Use a decorator to make a class qt safe.

    All the methods (except those explicitely ignored) are patched
    to run in the qt thread.
    """
    def decorator(cls):
        for name in dir(cls):
            if name in ignore:
                continue
            method = getattr(cls, name)
            if not isinstance(method, types.MethodType):
                continue
            setattr(cls, name, qt_safe(method))
        return cls
    if cls is None:
        return decorator
    return decorator(cls)


@qt_safe_class(ignore=('set_session', 'new_scan_data'))
class Flint:
    """Flint interface, meant to be exposed through an RPC server."""

    _id_generator = itertools.count()

    # Legacy
    _submit = staticmethod(lambda fn, *args, **kwargs: fn(*args, **kwargs))

    def __init__(self, parent_tab):
        self.parent_tab = parent_tab
        self.main_index = next(self._id_generator)
        self.plot_dict = {self.main_index: parent_tab}
        self.selector_dict = collections.defaultdict(list)
        self.data_dict = collections.defaultdict(dict)
        self.scans_watch_task = None
        self._session_name = None

        self.live_scan_mdi_area = self.new_tab("Live scan", qt.QMdiArea)
        self.live_scan_plots_dict = dict()

        self.set_title()

    def set_title(self, session_name=None):
        window = self.parent_tab.window()
        if not session_name:
            session = "no session attached."
        else:
            session = "attached to '%s`" % session_name
        title = 'Flint (PID={}) - {}'.format(os.getpid(), session)
        window.setWindowTitle(title)

    def get_session(self):
        return self._session_name

    def set_session(self, session_name):
        if session_name == self._session_name:
            return

        if self.scans_watch_task:
            self.scans_watch_task.kill()

        ready_event = gevent.event.Event()
        self.scans_watch_task = watch_session_scans(
            session_name, self.new_scan, self.new_scan_child, self.new_scan_data,
            ready_event=ready_event, wait=False)
        ready_event.wait()

        self._session_name = session_name
        self.set_title(session_name)

    def new_scan(self, scan_info):
        # show tab
        self.parent_tab.setCurrentIndex(0)

        # delete plots and free data
        for _, plots in self.live_scan_plots_dict.iteritems():
            for plot_type in ('0d', '1d', '2d'):
                for plot in plots[plot_type]:
                    self.plot_dict.pop(plot.plot_id, None)
                    self.data_dict.pop(plot.plot_id, None)
                    plot.close()
        for win in self.live_scan_mdi_area.subWindowList():
            win.close()
        self.live_scan_plots_dict = dict()

        # create new windows
        for master, channels in scan_info['acquisition_chain'].iteritems():
            scalars = channels['scalars']
            spectra = channels['spectra']
            images = channels['images']

            scalars_plot_win = silx_plot.Plot1D()
            scalars_plot_win.plot_id = master+"_0d"
            self.plot_dict[scalars_plot_win.plot_id] = scalars_plot_win
            self.live_scan_plots_dict[master] = {
                '0d': [scalars_plot_win],
                '1d': [],
                '2d': []}
            self.live_scan_mdi_area.addSubWindow(scalars_plot_win)
            scalars_plot_win.setWindowTitle(master+' -> scalar counters')
 
            if not scalars:
                scalars_plot_win.hide()
            else:
                scalars_plot_win.show()

            for spectrum in spectra:
                # spectrum_win = silx_plot.CurvesView)
                spectrum_win = silx_plot.Plot1D()
                spectrum_win.plot_id = master+"_1d"
                self.plot_dict[spectrum_win.plot_id] = spectrum_win
                self.live_scan_plots_dict[master]['1d'].append(spectrum_win)
                self.live_scan_mdi_area.addSubWindow(spectrum_win)
                spectrum_win.setWindowTitle(master+' -> '+spectrum+' spectrum')
                spectrum_win.show()

            for image in images:
                image_win = silx_plot.Plot2D()
                image_win.plot_id = master+"_2d"
                self.plot_dict[image_win.plot_id] = image_win
                self.live_scan_plots_dict[master]['2d'].append(image_win)
                self.live_scan_mdi_area.addSubWindow(image_win)
                image_win.setWindowTitle(master+' -> '+image+' image')
                image_win.show()

        self.live_scan_mdi_area.tileSubWindows()

    def new_scan_child(self, scan_info, data_channel):
        pass

    def new_scan_data(self, data_type, master_name, data):
        last_data = data["data"]
        if data_type in ('1d', '2d'):
            last_data = last_data[-1]
        
        return self.safe_new_scan_data(data_type, master_name, data, last_data)

    def safe_new_scan_data(self, data_type, master_name, data, last_data):
        if data_type == '0d':
            master_channels = data["master_channels"]

            plot = self.live_scan_plots_dict[master_name]["0d"][0]

            try:
                x_channel_name = master_channels[0]
            except IndexError:
                x_channel_name = None
            for channel_name, channel_data in last_data.iteritems():
                self.update_data(plot.plot_id, channel_name, channel_data)
                if channel_name not in master_channels:
                    x = last_data[x_channel_name]
                    y = channel_data
                    dlen = min(len(x), len(y))
                    if dlen > 0:
                        plot.addCurve(
                            x[:dlen], y[:dlen],
                            legend='%s -> %s' % (x_channel_name, channel_name))
        elif data_type == '1d':
            spectrum_data = last_data 
            channel_name = data["channel_name"]
            plot = self.live_scan_plots_dict[master_name]["1d"][data["channel_index"]]
            self.update_data(plot.plot_id, channel_name, spectrum_data)
            if spectrum_data.ndim == 1:
                length, = spectrum_data.shape
                x = numpy.arange(length)
                y = spectrum_data
            else:
                # assuming ndim == 2
                x = spectrum_data[0]
                y = spectrum_data[1]
            plot.addCurve(x, y, legend=channel_name)
        elif data_type == '2d':
            plot = self.live_scan_plots_dict[master_name]["2d"][data["channel_index"]]
            channel_name = data["channel_name"]
            image_data = last_data
            self.update_data(plot.plot_id, channel_name, image_data)
            plot.addImage(image_data, legend=channel_name)

    def new_tab(self, label, widget=qt.QWidget):
        widget = widget()
        self.parent_tab.addTab(widget, label)
        return widget

    def run_method(self, key, method, args, kwargs):
        plot = self.plot_dict[key]
        method = getattr(plot, method)
        return method(*args, **kwargs)

    # Plot management

    def add_plot(self, cls_name, name=None):
        plot_id = next(self._id_generator)
        if not name:
            name = 'Plot %d' % plot_id
        new_tab_widget = self.new_tab(name)
        qt.QVBoxLayout(new_tab_widget)
        cls = getattr(silx_plot, cls_name)
        plot = cls(new_tab_widget)
        self.plot_dict[plot_id] = plot
        new_tab_widget.layout().addWidget(plot)
        plot.show()
        return plot_id

    def get_plot_name(self, plot_id):
        parent = self.plot_dict[plot_id].parent()
        if isinstance(parent, qt.QMdiArea):
            label = parent.windowTitle()
        else:
            index = self.parent_tab.indexOf(parent)
            label = self.parent_tab.tabText(index)
        return label

    def remove_plot(self, plot_id):
        plot = self.plot_dict.pop(plot_id)
        parent = plot.parent()
        index = self.parent_tab.indexOf(parent)
        self.parent_tab.removeTab(index)
        plot.close()

    def get_interface(self, plot_id):
        plot = self.plot_dict[plot_id]
        names = dir(plot)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return [name for name in names
                    if not name.startswith('_')
                    if callable(getattr(plot, name))]

    # Data management

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
        plot = self.plot_dict[plot_id]
        # Hackish legend handling
        if 'legend' not in kwargs and method.startswith('add'):
            kwargs['legend'] = ' -> '.join(names)
        # Get the data to plot
        args = tuple(self.data_dict[plot_id][name] for name in names)
        method = getattr(plot, method)
        # Plot
        method(*args, **kwargs)

    def deselect_data(self, plot_id, names):
        plot = self.plot_dict[plot_id]
        legend = ' -> '.join(names)
        plot.remove(legend)

    def clear_data(self, plot_id):
        del self.data_dict[plot_id]
        plot = self.plot_dict[plot_id]
        plot.clear()

    # User interaction

    def _selection(self, plot_id, cls, *args):
        # Instanciate selector
        plot = self.plot_dict[plot_id]
        selector = cls(plot)
        # Save it for future cleanup
        self.selector_dict[plot_id].append(selector)
        # Run the selection
        selector.start(*args)
        queue = create_queue_from_qt_signal(selector.selectionFinished)
        try:
            positions, = queue.get()
        finally:
            disconnect_queue_from_qt_signal(queue)
        return positions

    def select_points(self, plot_id, nb):
        return self._selection(plot_id, PointsSelector, nb)

    def select_shape(self, plot_id, shape):
        return self._selection(plot_id, ShapeSelector, shape)

    def clear_selections(self, plot_id):
        for selector in self.selector_dict.pop(plot_id):
            selector.reset()


class QtLogHandler(logging.Handler):

    def __init__(self, log_widget):
        logging.Handler.__init__(self)

        self.log_widget = log_widget
        self.executor = QtExecutor()

    def emit(self, record):
        record = self.format(record)
        self.executor.submit(self.log_widget.appendPlainText, record)


# Main execution

def main():
    qapp = qt.QApplication(sys.argv)
    win = qt.QMainWindow()
    tabs = qt.QTabWidget(win)
    win.setCentralWidget(tabs)
    log_dock = qt.QDockWidget("Log output", win)
    log_widget = qt.QPlainTextEdit(log_dock)
    log_widget.setReadOnly(True)
    log_dock.setWidget(log_widget)
    win.addDockWidget(qt.Qt.BottomDockWidgetArea, log_dock)
    # resize window to 70% of available screen space
    win.resize(qt.QDesktopWidget().availableGeometry(win).size() * 0.7)
    win.show()

    logger = logging.getLogger()
    handler = QtLogHandler(log_widget)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s - %(levelname)s: %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    def handle_exception(exc_type, exc_value, exc_traceback, logger=logger):
        logger.critical(
            "Uncaught exception",
            exc_info=(exc_type, exc_value, exc_traceback))
    sys.excepthook = handle_exception

    stop = Future()
    flint = Flint(tabs)
    thread = Thread(
        target=background_task,
        args=(flint, stop))
    thread.start()
    try:
        qapp.exec_()
    finally:
        stop.set_result(None)
        thread.join(1.)


if __name__ == '__main__':
    main()
