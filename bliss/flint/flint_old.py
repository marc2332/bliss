# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
"""
Usage: flint (-s | --session) <name>
       flint (-h | --help)
Options:
    -s, --session                 Follow data from session.
    -h, --help                    Show this screen.
"""

# Imports

import docopt
import warnings
import functools

import numpy
import gevent
import gevent.monkey

from bliss.config.channels import Channel
from bliss.data.node import DataNodeIterator, _get_or_create_node, is_zerod

try:
    from PyQt4.QtCore import pyqtRemoveInputHook
except ImportError:
    from PyQt5.QtCore import pyqtRemoveInputHook

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from silx.gui.plot.PlotWindow import PlotWindow
    from silx.gui import qt

# Globals

pyqtRemoveInputHook()

Queue = gevent.monkey.get_original("Queue", "Queue")
QueueEmpty = gevent.monkey.get_original("Queue", "Empty")
start_new_thread = gevent.monkey.get_original("thread", "start_new_thread")

PLOTS = dict()
GEVENT_PLOTS = dict()
FLINT_CHANNEL = None


# Helpers

def copy_data(scan_node, zerod, zerod_index):
    channel_name = zerod.name
    data_channel = zerod
    from_index = zerod_index.get(channel_name, 0)
    data = data_channel.get(from_index, -1)
    zerod_index[channel_name] = from_index + len(data)


def watch_data(scan_node):
    zerod_index = dict()
    scan_data_iterator = DataNodeIterator(scan_node)
    walk = scan_data_iterator.walk_events(filter="channel")
    for event_type, event_data in walk:
        if not is_zerod(event_data):
            continue
        zerod = event_data
        if event_type in (scan_data_iterator.NEW_CHILD_EVENT,
                          scan_data_iterator.NEW_DATA_IN_CHANNEL_EVENT):
            copy_data(scan_node, zerod, zerod_index)


def plot_update(event, plot_channel_name=None):
    if event == 'connected':
        return
    EVENTS_QUEUE.put(event)


def flint_channel_update(plot_channel_name):
    if plot_channel_name == 'connected':
        return

    # new plot
    plot_update_cb = functools.partial(
        plot_update, plot_channel_name=plot_channel_name)
    c = Channel(plot_channel_name, callback=plot_update_cb)
    c._plot_update_cb = plot_update_cb
    c.value = "connected"

    EVENTS_QUEUE.put({"event": "new_plot", "data": plot_channel_name})

    GEVENT_PLOTS[plot_channel_name] = c


def watch_session(session_name, session_id=None):
    if session_id:
        global FLINT_CHANNEL
        FLINT_CHANNEL = Channel(
            "flint:%s" % session_id, callback=flint_channel_update)
        FLINT_CHANNEL.value = "connected"

    session_node = _get_or_create_node(session_name, node_type='session')
    if session_node is not None:
        data_iterator = DataNodeIterator(session_node)

        watch_data_task = None
        for scan_node in data_iterator.walk_from_last(filter='scan'):
            if watch_data_task:
                watch_data_task.kill()
            EVENTS_QUEUE.put({"event": "new_scan", "data": None})
            watch_data_task = gevent.spawn(watch_data, scan_node)


def plot_data(window, data):
    if data.ndim == 1:
        xs = numpy.arange(len(data))
        if data.dtype.fields is None:
            window.addCurve(xs, data)
        else:
            for field in data.dtype.fields:
                window.addCurve(xs, data[field], legend=field)
        return
    raise NotImplementedError


# Main execution

def main():
    try:
        # Parse arguments, use file docstring as a parameter definition
        arguments = docopt.docopt(__doc__)
        session_name = arguments['<name>']
    except docopt.DocoptExit as e:
        print(e.message)
    else:
        global qapp
        qapp = qt.QApplication([])
        win = qt.QMainWindow()
        mdi_area = qt.QMdiArea(win)
        win.setCentralWidget(mdi_area)
        win.show()

        try:
            session_name, session_id = session_name.split(":")
        except ValueError:
            session_id = None

        global EVENTS_QUEUE
        EVENTS_QUEUE = Queue()

        def process_queue(mdi=mdi_area):
            while True:
                try:
                    ev = EVENTS_QUEUE.get_nowait()
                except QueueEmpty:
                    return
                else:
                    if ev['event'] == 'new_plot':
                        plot_channel_name = ev['data']
                        title = plot_channel_name.split(':')[-1]
                        plot_window = PlotWindow(mdi)
                        plot_window.setWindowTitle(title)
                        PLOTS[plot_channel_name] = plot_window
                        mdi.addSubWindow(plot_window)
                        plot_window.show()
                    elif ev['event'] == 'data':
                        plot_channel_name, data = ev['data']
                        plot_window = PLOTS[plot_channel_name]
                        plot_data(plot_window, data)
                    elif ev['event'] == 'scan':
                        plot_channel_name, scan_node_name = ev['data']
                        plot_window = PLOTS[plot_channel_name]

        events_processing = qt.QTimer()
        events_processing.setInterval(10)
        events_processing.timeout.connect(process_queue)
        events_processing.start()

        start_new_thread(watch_session, (session_name, session_id))

        qapp.exec_()


if __name__ == '__main__':
    main()
