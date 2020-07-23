# --encoding: utf-8--
from random import randint, random
import time

from tango.server import run
from tango.server import Device
from tango.server import attribute
from tango import DevState


DevStates = (
    DevState.ALARM,
    DevState.CLOSE,
    DevState.CLOSE,
    DevState.FAULT,
    DevState.EXTRACT,
    DevState.MOVING,
    DevState.ON,
    DevState.OFF,
    DevState.OPEN,
    DevState.INSERT,
    DevState.INIT,
    DevState.STANDBY,
    DevState.UNKNOWN,
)


def randstate():
    """Returns a random tango state"""
    return DevStates[randint(0, len(DevStates) - 1)]


class SimulationMachInfo(Device):
    Auto_Mode_Time = attribute(fget=lambda _: randint(0, 3), dtype=int)
    Auto_Mode_Time_Str = attribute(
        fget=lambda _: time.asctime(time.localtime()), dtype=str
    )
    Automatic_Mode = attribute(fget=lambda _: randint(0, 1), dtype=bool)
    Close_Delivery_Time = attribute(fget=lambda _: randint(0, 1000), dtype=int)
    EXP_Itlk_State = attribute(fget=randstate)
    FE_Itlk_State = attribute(fget=randstate)

    FE_State = attribute(fget=lambda _: "", dtype=str)
    Gap_Opened = attribute(fget=lambda _: randint(0, 1), dtype=bool)
    HQPS_Itlk_State = attribute(fget=randstate)
    Mode = attribute(fget=lambda _: randint(0, 3), dtype=int)
    Open_Close_counter = attribute(fget=lambda _: randint(100, 1000), dtype=int)
    PSS_Itlk_State = attribute(fget=randstate)
    SR_Current = attribute(fget=lambda _: randint(0, 200), dtype=float)
    SR_Filling_Mode = attribute(fget=lambda _: "7/8 multibunch", dtype=str)
    SR_Lifetime = attribute(fget=lambda _: randint(10000, 70000), dtype=float)
    SR_Mode = attribute(fget=lambda _: randint(1, 3), dtype=int)
    SR_Operator_Mesg = attribute(
        fget=lambda _: "You are in Simulated Machine", dtype=str
    )
    SR_Refill_Countdown = attribute(fget=lambda _: randint(0, 160), dtype=float)
    SR_Single_Bunch_Current = attribute(fget=lambda _: random() * 2, dtype=float)
    UHV_Valve2_State = attribute(fget=randstate)
    UHV_Valve_State = attribute(fget=randstate)

    def __init__(self, *args, **kwargs):
        Device.__init__(self, *args, **kwargs)
        self.set_state(DevState.ON)


if __name__ == "__main__":
    run((SimulationMachInfo,))
