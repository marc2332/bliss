import random
from bliss.common.measurement import CounterBase
import numpy
import gevent

class TestCounter(CounterBase):
    def read(self):
        return random.random()*1000.

class TestScanGaussianCounter(CounterBase):
    def __init__(self, name, npts, center=0, stddev=1, cnt_time=0.1):
      CounterBase.__init__(self, None, name)
     
      self.data = numpy.random.normal(center, stddev, npts)
      self.i = 0
      self.cnt_time = cnt_time

    def read(self):
      gevent.sleep(self.cnt_time)
      x = self.data[self.i]
      self.i += 1
      return x

diode = TestCounter(None, 'diode')

