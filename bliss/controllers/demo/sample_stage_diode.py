import fabio
from bliss.common.counter import SoftCounter, SamplingMode
import numpy
import os
from bliss.controllers.counter import counter_namespace


class SampleStageDiode:
    def __init__(self, name, config):
        self.img = fabio.open(
            os.path.join(os.path.dirname(__file__), "esrf.edf.gz")
        ).data
        self.img = numpy.flipud(self.img)
        self.scale = .001  # mm/px
        self.dim1, self.dim2 = self.img.shape
        self.offset1 = int(self.dim1 / 2)
        self.offset2 = int(self.dim2 / 2)
        self.axis1 = config["axis1"]
        self.axis2 = config["axis2"]

        self.counter = SoftCounter(
            self, "read", name="fluo_signal", mode=SamplingMode.SINGLE
        )

    @property
    def counters(self):
        return counter_namespace([self.counter])

    def read(self):
        pos1 = int(self.axis1.dial / self.scale + self.offset1)
        pos2 = int(self.axis2.dial / self.scale + self.offset2)
        if pos1 >= self.dim1 or pos1 < 0 or pos2 >= self.dim2 or pos2 < 0:
            return numpy.random.rand() * 10
        else:
            return self.img[pos1, pos2] + numpy.random.rand() * 10
