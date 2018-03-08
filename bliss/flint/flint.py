# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

# Imports
import os
import sys
import logging
import platform
import tempfile
import warnings
import itertools
import contextlib
import collections

import gevent
import zerorpc
import msgpack_numpy
import gevent.monkey
from concurrent.futures import Future

from bliss.data.scan import watch_session_scans
from bliss.flint.executor import QtExecutor
from bliss.flint.executor import concurrent_to_gevent
from bliss.flint.executor import submit_to_qt_application
from bliss.flint.executor import create_queue_from_qt_signal
from bliss.flint.executor import disconnect_queue_from_qt_signal
from bliss.config.conductor.client import get_default_connection

try:
    from PyQt4.QtCore import pyqtRemoveInputHook
except ImportError:
    from PyQt5.QtCore import pyqtRemoveInputHook

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from silx.gui import plot
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

class Flint:

    _id_generator = itertools.count()
    _submit = staticmethod(submit_to_qt_application)

    def __init__(self, parent_tab):
        self.parent_tab = parent_tab
        self.main_index = next(self._id_generator)
        self.window_dict = {self.main_index: parent_tab}
        self.selector_dict = collections.defaultdict(list)
        self.data_dict = collections.defaultdict(dict)
        self.scans_watch_task = None

        self.live_scan_mdi_area = self.new_tab("Live scan", qt.QMdiArea)
        self.live_scan_plots_dict = dict()
       
    def set_session(self, session_name):
        self.scans_watch_task = watch_session_scans(session_name, self.new_scan, self.new_scan_child, self.new_scan_data, wait=False)

    def new_scan(self, scan_info):
        # show tab
        self._submit(self.parent_tab.setCurrentIndex, 0)

        # delete windows and free data
        for _, plots in self.live_scan_plots_dict.iteritems():
            for plot_type in ('0d', '1d', '2d'):
                for plot in plots[plot_type]:
                    self.window_dict.pop(plot.plot_id, None)
                    self.data_dict.pop(plot.plot_id, None)
                    self._submit(plot.close)
        for win in self.live_scan_mdi_area.subWindowList():
            self._submit(win.close)
        self.live_scan_plots_dict = dict()
 
        # create new windows
        for master, channels in scan_info['acquisition_chain'].iteritems():
            scalars = channels['scalars']
            spectra = channels['spectra']
            images = channels['images']

            scalars_plot_win = self._submit(silx_plot.Plot1D)
            scalars_plot_win.plot_id = master+"_0d"
            self.window_dict[scalars_plot_win.plot_id] = (scalars_plot_win, None)
            self.live_scan_plots_dict[master] = { '0d': [scalars_plot_win], '1d':[], '2d':[] }
            self._submit(self.live_scan_mdi_area.addSubWindow, scalars_plot_win)
            self._submit(scalars_plot_win.setWindowTitle, master+' -> scalar counters')
            logging.info("%s", scalars)
            if not scalars:
                self._submit(scalars_plot_win.hide)
            else:
                self._submit(scalars_plot_win.show)

            for spectrum in spectra:
                #spectrum_win = self._submit(silx_plot.CurvesView)
                spectrum_win = self._submit(silx_plot.Plot1D)
                spectrum_win.plot_id = master+"_1d"
                self.window_dict[spectrum_win.plot_id] = (spectrum_win, None)
                self.live_scan_plots_dict[master]['1d'].append(spectrum_win)
                self._submit(self.live_scan_mdi_area.addSubWindow, spectrum_win)
                self._submit(spectrum_win.setWindowTitle, master+' -> '+spectrum+' spectrum')
                self._submit(spectrum_win.show)
            
            for image in images:
                image_win = self._submit(silx_plot.Plot2D)
                image_win.plot_id = master+"_2d"
                self.window_dict[image_win.plot_id] = (image_win, None)
                self.live_scan_plots_dict[master]['2d'].append(image_win)
                self._submit(self.live_scan_mdi_area.addSubWindow, image_win)
                self._submit(image_win.setWindowTitle, master+' -> '+image+' image')
                self._submit(image_win.show)

        self._submit(self.live_scan_mdi_area.tileSubWindows)

    def new_scan_child(self, scan_info, data_channel):
        pass

    def new_scan_data(self, data_type, master_name, data):
        if data_type == '0d':
            master_channels = data["master_channels"]
            data = data["data"]

            plot = self.live_scan_plots_dict[master_name]["0d"][0]

    def new_tab(self, label, widget=qt.QWidget):
        widget = self._submit(widget)
        self._submit(self.parent_tab.addTab, widget, label)
        return widget

    def run_method(self, key, method, args, kwargs):
        window = self.window_dict[key]
        method = getattr(window, method)
        return self._submit(method, *args, **kwargs)

    # Window management
    def add_window(self, cls_name, name=None):
        wid = next(self._id_generator)
        if not name:
            name = 'Plot %d' % wid
        new_tab_widget = self.new_tab(name)
        self._submit(qt.QVBoxLayout, new_tab_widget)
        cls = getattr(plot, cls_name)
        window = self._submit(cls, new_tab_widget)
        self.window_dict[wid] = window
        self._submit(self._submit(new_tab_widget.layout).addWidget, window)
        self._submit(window.show)
        return wid

    def remove_window(self, wid):
        window = self.window_dict.pop(wid)
        index = self._submit(self.parent_tab.indexOf, self._submit(window.parent))
        self._submit(self.parent_tab.removeTab, index)
        self._submit(window.close)

    def get_interface(self, wid):
        window = self.window_dict[wid]
        names = self._submit(dir, window)

        # Factorize the calls
        def wrapper():
            return [name for name in names
                    if not name.startswith('_')
                    if callable(getattr(window, name))]

        return self._submit(wrapper)

    # Data management

    def add_data(self, wid, field, data):
        self.data_dict[wid][field] = data

    def remove_data(self, wid, field):
        del self.data_dict[wid][field]

    def get_data(self, wid):
        return self.data_dict[wid]

    def select_data(self, wid, method, names, kwargs):
        window = self.window_dict[wid]
        # Hackish legend handling
        if 'legend' not in kwargs and method.startswith('add'):
            kwargs['legend'] = ' -> '.join(names)
        # Get the data to plot
        args = tuple(self.data_dict[wid][name] for name in names)
        method = getattr(window, method)
        # Plot
        self._submit(method, *args, **kwargs)

    def deselect_data(self, wid, names):
        window = self.window_dict[wid]
        legend = ' -> '.join(names)
        self._submit(window.remove, legend)

    def clear_data(self, wid):
        del self.data_dict[wid]
        window = self.window_dict[wid]
        self._submit(window.clear)

    # User interaction

    def _selection(self, wid, cls, *args):
        # Instanciate selector
        window = self.window_dict[wid]
        selector = self._submit(cls, window)
        # Save it for future cleanup
        self.selector_dict[wid].append(selector)
        # Run the selection
        self._submit(selector.start, *args)
        queue = create_queue_from_qt_signal(selector.selectionFinished)
        try:
            positions, = queue.get()
        finally:
            disconnect_queue_from_qt_signal(queue)
        return positions

    def select_points(self, wid, nb):
        return self._selection(wid, PointsSelector, nb)

    def select_shape(self, wid, shape):
        return self._selection(wid, ShapeSelector, shape)

    def clear_selections(self, wid):
        for selector in self.selector_dict.pop(wid):
            self._submit(selector.reset)


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
    title = 'Flint (PID={})'.format(os.getpid())
    win.setWindowTitle(title)
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
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s: %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    
    def handle_exception(exc_type, exc_value, exc_traceback):
        logger.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))
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
