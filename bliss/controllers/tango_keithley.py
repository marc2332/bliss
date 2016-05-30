from bliss.common.task_utils import cleanup, error_cleanup, task
from bliss.common.measurement import CounterBase
import PyTango.gevent
import time
import numpy

class tango_keithley(CounterBase):
    def __init__(self, name, config):
        CounterBase.__init__(self, name)
        tango_uri = config["uri"]
        self.__control = PyTango.gevent.DeviceProxy(tango_uri)

    def read(self):
        self.__control.MeasureSingle()
        self.__control.WaitAcq()
        value = self.__control.ReadData
        if isinstance(value,  numpy.ndarray):
            value = value[0]
        return value

    def autorange(self, autorange_on=None):
        if autorange_on is None:
            return self.__control.autorange   
        else:
            self.__control.autorange = autorange_on

