import time

class Reading(object):
    __slots__ = ['value']
    def __init__(self):
      self.value = 0

class AverageMeasurement(object):
    __slots__ = ['__average']

    def __init__(self):
        self.__average = 0

    @property
    def average(self):
        return self.__average

    def __call__(self, acq_time):
        self.__average = 0
        npts = 0
        t0 = time.time()
        while True:
            last_acq_start_time = time.time()
            reading = Reading()
            yield reading
            npts += 1
            self.__average += (reading.value - self.__average) / float(npts)
            if acq_time is not None:
                last_acq_time = time.time() - last_acq_start_time
                acq_time -= last_acq_time
                if acq_time < last_acq_time:
                    break
            else:
                break

class CounterBase(object):
    def __init__(self, name):
        self.__name = name

    @property
    def name(self):
        return self.__name

    def read(self, count_time=None):
        raise NotImplementedError


