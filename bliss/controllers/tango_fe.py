from bliss.common.task_utils import cleanup, error_cleanup, task
from bliss.common.measurement import CounterBase
import PyTango.gevent
import time

class tango_fe(CounterBase):
    def __init__(self, name, config):
        CounterBase.__init__(self, name)
        tango_uri = config.get("uri")
        self.__control = PyTango.gevent.DeviceProxy(tango_uri)
        self.attribute = config.get("attr_name")

    def read(self, acq_time=None):
        try:
            return self.__control.read_attribute(self.attribute).value
        except:
            return 0
