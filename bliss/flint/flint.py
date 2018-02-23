# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
"""
Usage: flint (-s | --session) <sid>
       flint (-h | --help)
Options:
    -s, --session                 Follow data from session.
    -h, --help                    Show this screen.
"""

# Imports

import os
import docopt
import tempfile
import warnings
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

PLOTS = dict()
GEVENT_PLOTS = dict()
FLINT_CHANNEL = None


# Gevent functions

@contextlib.contextmanager
def safe_rpc_server(obj):
    with tempfile.NamedTemporaryFile() as f:
        url = 'ipc://{}'.format(f.name)
        server = zerorpc.Server(obj)
        try:
            server.bind(url)
            os.chmod(f.name, 0o700)
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
        redis.rpop(key)


def background_task(flint, session_id, stop):
    key = "flint:%s" % session_id
    stop = concurrent_to_gevent(stop)
    with safe_rpc_server(flint) as (task, url):
        with maintain_value(key, url):
            gevent.wait([stop, task], count=1)


# Flint interface

class Flint:

    _submit = staticmethod(submit_to_qt_application)

    def __init__(self, main_window, mdi_area):
        self.mdi_area = mdi_area
        self.main_window = main_window
        self.window_dict = {}
        self.window_dict[0] = main_window

    def run_method(self, key, method, *args, **kwargs):
        window = self.window_dict[key]
        method = getattr(window, method)
        return self._submit(method, *args, **kwargs)

    def add_window(self, key):
        window = self._submit(PlotWindow, self.mdi_area)
        self._submit(self.mdi_area.addSubWindow, window)
        self._submit(window.show)
        self.window_dict[key] = window


# Main execution

def main():
    try:
        # Parse arguments, use file docstring as a parameter definition
        arguments = docopt.docopt(__doc__)
        session_id = arguments['<sid>']
    except docopt.DocoptExit as e:
        print(e.message)
        return

    qapp = qt.QApplication([])
    win = qt.QMainWindow()
    mdi_area = qt.QMdiArea(win)
    win.setCentralWidget(mdi_area)
    win.show()

    stop = Future()
    flint = Flint(win, mdi_area)
    thread = Thread(
        target=background_task,
        args=(flint, session_id, stop))
    thread.start()
    try:
        qapp.exec_()
    finally:
        stop.set_result(None)
        thread.join(1.)


if __name__ == '__main__':
    main()
