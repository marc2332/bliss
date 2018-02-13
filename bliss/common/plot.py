import subprocess
import gevent
import gevent.event
from bliss.scanning import scan as scan_module
from bliss.config.channels import Channel
import uuid

FLINT_PROCESS = None
FLINT_CHANNEL = None
FLINT_READY = gevent.event.Event()

class Plot(object):
    def __init__(self, session_id):
        self.channel = Channel("flint:%s:%s" % (session_id, id(self)), callback=self.channel_update)
        self.connected = gevent.event.Event()

    def channel_update(self, event):
        if event == 'connected':
            self.connected.set()

    def display(self, data_or_scan_obj):
        self.channel.value = { "event":"data", "data":(self.channel.name, data_or_scan_obj) }


def flint_channel_update(event):
    if event == 'connected':
        FLINT_READY.set()

def plot(data_or_scan_obj=None):
    """Plot data (numpy array) or scan object

    If data_or_scan_obj is None, open user interface with tree
    """
    scan_saving = scan_module.ScanSaving()
    session_name = scan_saving.session
    session_id = uuid.uuid1()
    
    global FLINT_PROCESS
    if FLINT_PROCESS is None:
        global FLINT_CHANNEL
        FLINT_PROCESS = subprocess.Popen('flint -s %s:%s' % (session_name, session_id), shell=True)
        FLINT_CHANNEL = Channel("flint:%s" % session_id, callback=flint_channel_update)    
 
    FLINT_READY.wait()

    p = Plot(session_id)
    # notify flint there is a new plot
    FLINT_CHANNEL.value = p.channel.name

    p.connected.wait()

    return p 
 
