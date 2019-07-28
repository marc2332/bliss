import random
from bliss import current_session
from bliss.common.standard import *
from bliss.common.measurement import SamplingCounter
import numpy
import gevent
from bliss.common.event import dispatcher
from bliss.scanning import scan
import math

# deactivate automatic Flint startup
scan.ScanDisplay().auto = False

load_script("script1")

SESSION_NAME = current_session.name

# Do not remove this print (used in tests)
print("TEST_SESSION INITIALIZED")
#
