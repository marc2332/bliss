# --encoding: utf-8--
from tango.server import run
from tango.server import Device
from tango.server import attribute, command
from tango import AttrWriteType, AttrQuality
from tango import DevState

"""
Test Tango device server to simulate:
* Undulator DS
* Shutter DS
* Serial line DS ?
* VacGauge DS
"""


class Dummy(Device):

    # Undulator attributes
    position = attribute(format="%3.2f", unit="mm")
    u23a_position = attribute(format="%3.2f", unit="mm")
    power = attribute(format="%3.2f")
    maxpower = attribute(format="%3.2f")
    powerdensity = attribute(format="%3.2f")
    maxpowerdensity = attribute(format="%3.2f")
    firstvelocity = attribute(format="%3.2f")
    none_attr = attribute(format="%3.2f")

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

    UndulatorNames = attribute(
        fget="read_UndulatorNames", access=AttrWriteType.READ, dtype=[str], max_dim_x=2
    )
    UndulatorRevolverCarriage = attribute(
        fget="read_UndulatorRevolverCarriage",
        access=AttrWriteType.READ,
        dtype=[bool],
        max_dim_x=2,
    )
    UndulatorStates = attribute(
        fget="read_UndulatorStates",
        access=AttrWriteType.READ,
        dtype=["DevState"],
        max_dim_x=2,
    )

    # Vacuum gauge attibutes
    pressure = attribute(format="%6.2f", unit="mBar", access=AttrWriteType.READ)

    def __init__(self, *args, **kwargs):
        Device.__init__(self, *args, **kwargs)

        self._emulate_device = None

        # Forced at init as not read from config.
        # In real undu, they are read from ID DS.
        self.vel = 5
        self.acc = 125

        # set invalid quality to return numpy.nan
        self.none_attr.set_quality(AttrQuality.ATTR_INVALID)

        # shutter state
        self.set_state(DevState.CLOSE)

    def read_UndulatorNames(self):
        return ["U23a", "U27b"]

    def read_UndulatorStates(self):
        return [self.get_state(), self.get_state()]

    def read_UndulatorRevolverCarriage(self):
        return [False, False]

    def read_position(self):
        if self.get_state() == DevState.DISABLE:
            raise RuntimeError("DISABLED")
        return 1.4078913

    def read_u23a_position(self):
        return self.read_position()

    def read_power(self):
        return 0

    def read_maxpower(self):
        return 0

    def read_none_attr(self):
        return None

    def read_powerdensity(self):
        return 0

    def read_maxpowerdensity(self):
        return 0

    def read_firstvelocity(self):
        return self.vel

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

    # VacGauge attributes
    def read_pressure(self):
        return 0.000000012345678

    #
    @command(dtype_out=str)
    def string1(self):
        return "café"

    @command(dtype_in=bool)
    def setDisabled(self, disable):
        if disable:
            self.set_state(DevState.DISABLE)
        else:
            self.set_state(DevState.STANDBY)

    # for tango_shutter
    @command()
    def open(self):
        self.set_state(DevState.OPEN)

    @command()
    def close(self):
        self.set_state(DevState.CLOSE)

    @command(dtype_out=str)
    def status(self):
        return "Some Text " + str(self.get_state())

    @command(dtype_in=str)
    def emulate_device(self, dev):
        self._emulate_device = dev

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
    def DevSerReadChar(self, _):
        if self._emulate_device == "opiom":
            return b"OPIOM\r\n"
        else:
            return b" "

    @command(dtype_in=int, dtype_out="DevVarCharArray")
    def DevSerReadNBinData(self, size):
        return b" " * size


if __name__ == "__main__":
    run((Dummy,))
