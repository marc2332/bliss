# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2017 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import liboxford800
from liboxford800 import ls_oxford800
from .oxford import Base


def get_cryo(func):
    def f(self, *args, **kwargs):
        cryo = liboxford800.get_handle(self._cryoname)
        if cryo is None:
            raise RuntimeError("Could not find oxford cryostream %r" % self._cryoname)
        return func(self, cryo, *args, **kwargs)

    return f


class Handler(object):
    def __init__(self, cryoname):
        self._loop = liboxford800.loop()
        self._cryoname = cryoname

    def __dir__(self):
        l = [
            "read_temperature",
            "ramp",
            "plat",
            "plat",
            "hold",
            "turbo",
            "resume",
            "pause",
            "restart",
            "end",
            "cool",
            "state_output",
            "status",
        ]
        cryo = liboxford800.get_handle(self._cryoname)
        if cryo is not None:
            l.extend(cryo.__dir__())
        return l

    def __getattr__(self, name):
        cryo = liboxford800.get_handle(self._cryoname)
        if cryo is not None:
            return getattr(cryo, name)
        raise AttributeError(name)

    @get_cryo
    def read_temperature(self, cryo):
        cryo.wait_new_status()
        return cryo.Sample_temp

    @get_cryo
    def ramp(self, cryo, ramp, sp):
        return cryo.ramp(ramp, sp)

    @get_cryo
    def plat(self, cryo, duration):
        return cryo.plat(duration)

    @get_cryo
    def hold(self, cryo):
        return cryo.hold()

    @get_cryo
    def turbo(self, cryo, flow):
        cryo.turbo(flow)

    @get_cryo
    def resume(self, cryo):
        cryo.resume()

    @get_cryo
    def pause(self, cryo):
        cryo.pause()

    @get_cryo
    def restart(self, cryo):
        cryo.restart()

    @get_cryo
    def end(self, cryo, rate):
        cryo.end(rate)

    @get_cryo
    def cool(self, cryo, temp=None):
        if temp is None:
            cryo.wait_new_status()
            return cryo.Set_temp
        else:
            cryo.cool(temp)

    @get_cryo
    def state_output(self, cryo):
        cryo.wait_new_status()
        return (cryo.Run_mode, cryo.Phase_id)

    @get_cryo
    def status(self, cryo):
        return cryo.__repr__()


class Oxford800(Base):
    """
    Cryostream 800 controller.

    The only configuration parameter you need to fill
    if you have several cryostream 800 on the local network is *cryoname*.
    *cryoname* could be the name of the cryostream on the network or is ip address.
    """

    def __init__(self, config, *args):
        handler = Handler(config.get("cryoname"))
        Base.__init__(self, handler, config, *args)

    def __repr__(self):
        return self._oxford.status()

    def state_output(self, toutput):
        mode, phase = self._oxford.state_output()
        mode_enum = mode[0]
        phase_enum = phase[0]
        return {
            0: "RUNNING",
            1: "ALARM",
            2: "READY",
            3: "RUNNING",
            5: "READY",
            6: "FAULT",
        }.get(mode_enum, "UNKNOWN")
