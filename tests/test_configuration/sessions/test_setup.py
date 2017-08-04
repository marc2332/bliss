import random
from bliss.common.measurement import CounterBase

class TestCounter(CounterBase):
    def read(self):
        return random.random()*1000.

diode = TestCounter(None, 'diode')

