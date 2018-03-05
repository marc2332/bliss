# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

# Imports
import os
import sys
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
            yield task, url
        finally:
            task.kill()
            task.join()
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

    def __init__(self, main_window, mdi_area):
        self.mdi_area = mdi_area
        self.main_window = main_window
        self.main_index = next(self._id_generator)
        self.window_dict = {self.main_index: self.main_window}
        self.selector_dict = collections.defaultdict(list)
        self.data_dict = collections.defaultdict(dict)

    def run_method(self, key, method, args, kwargs):
        window = self.window_dict[key]
        method = getattr(window, method)
        return self._submit(method, *args, **kwargs)

    # Window management

    def add_window(self, cls_name):
        wid = next(self._id_generator)
        cls = getattr(plot, cls_name)
        window = self._submit(cls, self.mdi_area)
        self._submit(self.mdi_area.addSubWindow, window)
        self._submit(window.show)
        self.window_dict[wid] = window
        return wid

    def remove_window(self, wid):
        window = self.window_dict.pop(wid)
        parent = self._submit(window.parent)
        self._submit(parent.close)

    def get_interface(self, wid):
        window = self.window_dict[wid]
        names = self._submit(dir, window)
        return [name for name in names
                if not name.startswith('_')
                if callable(getattr(window, name))]

    # Data management

    def add_data(self, wid, field, data):
        self.data_dict[wid][field] = data

    def remove_data(self, wid, field):
        del self.data_dict[wid][field]

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


# Main execution

def main():
    qapp = qt.QApplication(sys.argv)
    win = qt.QMainWindow()
    title = 'Flint (PID={})'.format(os.getpid())
    win.setWindowTitle(title)
    mdi_area = qt.QMdiArea(win)
    win.setCentralWidget(mdi_area)
    win.show()

    stop = Future()
    flint = Flint(win, mdi_area)
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
