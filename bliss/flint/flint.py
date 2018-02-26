# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

# Imports
import os
import sys
import tempfile
import warnings
import itertools
import contextlib

import gevent
import zerorpc
import msgpack_numpy
import gevent.monkey
from concurrent.futures import Future

from bliss.flint.executor import concurrent_to_gevent
from bliss.flint.executor import submit_to_qt_application
from bliss.config.conductor.client import get_default_connection

try:
    from PyQt4.QtCore import pyqtRemoveInputHook
except ImportError:
    from PyQt5.QtCore import pyqtRemoveInputHook

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from silx.gui.plot.PlotWindow import PlotWindow
    from silx.gui import qt

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
    key = "flint:%s" % os.getpid()
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

    def run_method(self, key, method, args, kwargs):
        window = self.window_dict[key]
        method = getattr(window, method)
        return self._submit(method, *args, **kwargs)

    def add_window(self):
        wid = next(self._id_generator)
        window = self._submit(PlotWindow, self.mdi_area)
        self._submit(self.mdi_area.addSubWindow, window)
        self._submit(window.show)
        self.window_dict[wid] = window
        return wid

    def remove_window(self, wid):
        window = self.window_dict.pop(wid)
        self._submit(self.mdi_area.removeSubWindow, window)


# Main execution

def main():
    qapp = qt.QApplication(sys.argv)
    win = qt.QMainWindow()
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
