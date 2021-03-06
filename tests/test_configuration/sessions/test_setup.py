import random
from bliss import current_session
from bliss.shell.standard import *
from bliss.common.counter import SamplingCounter
import numpy
import gevent
from bliss.common.event import dispatcher
from bliss.scanning.scan_display import ScanDisplay
import math
from bliss.common.utils import get_open_ports
from bliss.shell.standard import goto_custom, find_position

# deactivate automatic Flint startup
ScanDisplay().auto = False

load_script("script1")

SESSION_NAME = current_session.name

# Do not remove this print (used in tests)
print("TEST_SESSION INITIALIZED")
#


def special_com(x, y):
    return numpy.average(x, weights=y)


def find_special():
    return find_position(special_com)


def goto_special():
    return goto_custom(special_com)
