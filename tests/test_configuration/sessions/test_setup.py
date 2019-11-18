import random
from bliss import current_session
from bliss.shell.standard import *
from bliss.common.counter import SamplingCounter
import numpy
import gevent
from bliss.common.event import dispatcher
from bliss.scanning import scan
import math
from tests.conftest import get_open_ports

# deactivate automatic Flint startup
scan.ScanDisplay().auto = False

load_script("script1")

SESSION_NAME = current_session.name

# Do not remove this print (used in tests)
print("TEST_SESSION INITIALIZED")
#
