import random
from bliss.common.standard import *
from bliss.common.measurement import SamplingCounter
from bliss.common.session import get_current
import numpy
import gevent
from bliss.common.event import dispatcher
from bliss.scanning import scan
import math

# deactivate automatic Flint startup
scan.ScanDisplay().auto = False

load_script("script1")

SESSION_NAME = get_current().name

# Do not remove this print (used in tests)
print("TEST_SESSION INITIALIZED")
#
