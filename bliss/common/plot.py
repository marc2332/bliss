"""Interface with flint."""

# Imports

import os
import sys
import uuid
import itertools
import subprocess

import gevent
import gevent.event

from bliss.config.channels import Channel
from bliss.scanning import scan as scan_module
from bliss.config.conductor.client import get_default_connection

# Globals

FLINT_PROCESS = None
FLINT_CHANNEL = None
FLINT_READY = gevent.event.Event()


class Plot(object):

    # Count the plots
    gen = itertools.count(1)

    def __init__(self, session_id, name=None):
        self.connected = gevent.event.Event()
        index = next(self.gen)
        self.name = name or "Plot {}".format(index)
        self.channel = Channel(
            "flint:%s:%s:%s" % (session_id, id(self), self.name),
            callback=self.channel_update)

    def channel_update(self, event):
        if event == 'connected':
            self.connected.set()

    def display(self, data_or_scan_obj):
        self.channel.value = {
            "event": "data",
            "data": (self.channel.name, data_or_scan_obj)}


def flint_channel_update(event):
    if event == 'connected':
        FLINT_READY.set()


def plot(data_or_scan_obj=None, name=None):
    """Plot data (numpy array) or scan object

    If data_or_scan_obj is None, open user interface with tree
    """
    scan_saving = scan_module.ScanSaving()
    session_name = scan_saving.session
    session_id = uuid.uuid1()

    global FLINT_PROCESS
    if FLINT_PROCESS is None:
        global FLINT_CHANNEL
        env = dict(os.environ)
        connection = get_default_connection()
        beacon_host = '{}:{}'.format(connection._host, connection._port)
        env['BEACON_HOST'] = beacon_host
        print(beacon_host)
        FLINT_PROCESS = subprocess.Popen(
            [sys.executable, '-m',
             'bliss.flint',
             '-s', '%s:%s' % (session_name, session_id)],
            env=env)
        FLINT_CHANNEL = Channel(
            "flint:%s" % session_id, callback=flint_channel_update)

    FLINT_READY.wait()

    p = Plot(session_id, name=name)
    # notify flint there is a new plot
    FLINT_CHANNEL.value = p.channel.name

    p.connected.wait()

    if data_or_scan_obj is not None:
        p.display(data_or_scan_obj)

    return p
