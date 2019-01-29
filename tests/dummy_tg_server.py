# --encoding: utf-8--
import time
from tango.server import run
from tango.server import Device
from tango.server import attribute, command
from tango import AttrWriteType


class Dummy(Device):
    position = attribute()
    velocity = attribute(
        fget="read_velocity", fset="write_velocity", access=AttrWriteType.READ_WRITE
    )
    acceleration = attribute(
        fget="read_acceleration",
        fset="write_acceleration",
        access=AttrWriteType.READ_WRITE,
    )

    def __init__(self, *args, **kwargs):
        Device.__init__(self, *args, **kwargs)

        self.vel = 0
        self.acc = 0

    def read_position(self):
        return 1.4

    def read_velocity(self):
        return self.vel

    def write_velocity(self, vel):
        self.vel = vel

    def read_acceleration(self):
        return self.acc

    def write_acceleration(self, acc):
        self.acc = acc

    @command(dtype_out=str)
    def string1(self):
        return "café"


if __name__ == "__main__":
    run((Dummy,))
