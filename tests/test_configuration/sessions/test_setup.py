import random
from bliss.common.scans import *
from bliss.common.measurement import SamplingCounter
from bliss.common.session import get_current
import numpy
import gevent

class TestScanGaussianCounter(SamplingCounter):
    def __init__(self, name, npts, center=0, stddev=1, cnt_time=0.1):
      SamplingCounter.__init__(self, name, None)
     
      self.data = numpy.random.normal(center, stddev, npts)
      self.i = 0
      self.cnt_time = cnt_time

    def read(self):
      gevent.sleep(self.cnt_time)
      x = self.data[self.i]
      self.i += 1
      return x

load_script("script1")

SESSION_NAME = get_current().name

# Do not remove this print (used in tests)
print 'TEST_SESSION INITIALIZED'
#
