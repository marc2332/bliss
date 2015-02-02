class CounterBase(object):
    def __init__(self, name):
        self.__name = name

    @property
    def name(self):
        return self.__name

    def read(self, count_time=None):
        raise NotImplementedError


