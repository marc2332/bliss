from bliss.common.measurement import CounterBase, AverageMeasurement
import random
import time

class simulation_diode(CounterBase):
    def __init__(self, name, config):
        CounterBase.__init__(self, name)

    def read(self, acq_time=None):
        meas = AverageMeasurement()
        for reading in meas(acq_time):
            if acq_time > 0.01:
                time.sleep(0.01) # simulate hw reading
            reading.value = random.randint(-100,100)
        return meas.average
