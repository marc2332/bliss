from bliss.common.task_utils import cleanup, error_cleanup, task
from bliss.common.measurement import CounterBase, AverageMeasurement
import PyTango.gevent
import time
import numpy

class tango_keithley(CounterBase):
    def __init__(self, name, config):
        CounterBase.__init__(self, name)
        tango_uri = config["uri"]
        self.__control = PyTango.gevent.DeviceProxy(tango_uri)

    def read(self, acq_time=0):
        meas = AverageMeasurement()
        for reading in meas(acq_time):
            self.__control.MeasureSingle()
            self.__control.WaitAcq()
            reading.value = self.__control.ReadData
            if isinstance(reading.value,  numpy.ndarray):
              reading.value = reading.value[0]
        return meas.average

    def autorange(self, autorange_on=None):
        if autorange_on is None:
            return self.__control.autorange   
        else:
            self.__control.autorange = autorange_on

