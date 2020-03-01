# --encoding: utf-8--
from tango.server import run
from tango.server import Device
from tango.server import attribute, command
from tango import AttrWriteType
from tango import DevState


class Dummy(Device):
    position = attribute(format="%3.2f", unit="mm")

    velocity = attribute(
        fget="read_velocity", fset="write_velocity", access=AttrWriteType.READ_WRITE
    )

    acceleration = attribute(
        fget="read_acceleration",
        fset="write_acceleration",
        access=AttrWriteType.READ_WRITE,
    )

    powers = attribute(
        fget="read_powers",
        access=AttrWriteType.READ,
        dtype=[float],
        max_dim_x=3,
        format="%6.3f",
    )

    def __init__(self, *args, **kwargs):
        Device.__init__(self, *args, **kwargs)

        # Forced at init as not read from config.
        # In real undu, they are read from ID DS.
        self.vel = 5
        self.acc = 125

        # shutter state
        self.set_state(DevState.CLOSE)

    def read_position(self):
        return 1.4078913

    def read_velocity(self):
        return self.vel

    def write_velocity(self, vel):
        self.vel = vel

    def read_acceleration(self):
        return self.acc

    def write_acceleration(self, acc):
        self.acc = acc

    def read_powers(self):
        # current and max powers
        return [0.136, 1.1]

    @command(dtype_out=str)
    def string1(self):
        return "café"

    ###for tango_shutter
    @command()
    def open(self):
        self.set_state(DevState.OPEN)

    @command()
    def close(self):
        self.set_state(DevState.CLOSE)

    @command(dtype_out=str)
    def status(self):
        return "Some Text " + str(self.get_state())

    @command(dtype_in="DevVarLongArray")
    def DevSerSetParameter(self, _):
        pass

    @command(dtype_in=int)
    def DevSerFlush(self, _):
        pass

    @command(dtype_in="DevVarCharArray")
    def DevSerWriteChar(self, _):
        pass

    @command(dtype_in=int, dtype_out="DevVarCharArray")
    def DevSerReadNBinData(self, size):
        return b" " * size


if __name__ == "__main__":
    run((Dummy,))
