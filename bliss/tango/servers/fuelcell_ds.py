# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Tango device server fuel cell.

It allows reading fuel cell parameters

"""


import inspect

from tango import DevState, CmdArgType, AttrWriteType, AttrDataFormat
from tango.server import Device, attribute, command, device_property, get_worker

from bliss.config.static import get_config
from bliss.controllers.id31.fuelcell import FuelCell as _FuelCell
from bliss.controllers.id31.fuelcell import Ptc, Fcs, Attr


_TYPE_MAP = {
    bool: CmdArgType.DevBoolean,
    str: CmdArgType.DevString,
    int: CmdArgType.DevLong,
    float: CmdArgType.DevDouble,
    "feedback": CmdArgType.DevString,
    "fuse_status": CmdArgType.DevLong,
}


def read(self, attr):
    value = get_worker().execute(getattr, self.fuelcell, attr.get_name())
    attr.set_value(value)


def write(self, attr):
    value = attr.get_write_value()
    value = get_worker().execute(setattr, self.fuelcell, attr.get_name(), value)


def fuelcell_device(klass):
    for member_name in dir(_FuelCell):
        member = getattr(_FuelCell, member_name)
        if inspect.isdatadescriptor(member):
            if isinstance(member, Attr):
                wwrite = (
                    AttrWriteType.READ_WRITE if member.encode else AttrWriteType.READ
                )
                cfg = dict(unit=member.unit if member.unit else "")
                attr_info = [
                    [_TYPE_MAP[member.decode], AttrDataFormat.SCALAR, wwrite],
                    cfg,
                ]
                klass.TangoClassClass.attr_list[member_name] = attr_info
                setattr(klass, "read_" + member_name, read)
                if wwrite == AttrWriteType.READ_WRITE:
                    fname = "write_" + member_name
                    if not hasattr(klass, fname):
                        setattr(klass, fname, write)
    return klass


@fuelcell_device
class FuelCell(Device):

    url = device_property(dtype=str, doc="fuell cell hostname")
    name = device_property(dtype=str, default_value=None)

    def init_device(self):
        Device.init_device(self)
        try:
            if self.name:
                config = get_config()
                self.fuelcell = config.get(self.name)
            else:
                self.fuelcell = _FuelCell("Fuel Cell", dict(tcp=dict(url=self.url)))
            self.set_state(DevState.ON)
            self.set_status("Ready!")
        except Exception as e:
            self.set_state(DevState.FAULT)
            self.set_status("Error:\n" + str(e))

    # ----------
    # Commands
    # ----------

    @command(dtype_in=[int], doc_in=Ptc.timescan.__doc__)
    def timescan(self, par_list):
        self.fuelcell.ptc.timescan(*par_list)

    @command(dtype_in=[str], doc_in=Ptc.cv.__doc__)
    def cv(self, par_list):
        if len(par_list) < 7:
            raise RuntimeError("not enough parameters")
        channel = par_list[0]
        start = float(par_list[1])
        stop = float(par_list[2])
        margin1 = float(par_list[3])
        margin2 = float(par_list[4])
        speed = float(par_list[5])
        sweeps = int(par_list[6])

        self.fuelcell.ptc.cv(channel, start, stop, margin1, margin2, speed, sweeps)

    @command(doc_in=Ptc.stop.__doc__)
    def stop(self):
        self.fuelcell.ptc.stop()

    def write_vsense(self, value):
        self.fuelcell.ptc.set_vsense_feedback(value)

    def write_current(self, value):
        self.fuelcell.ptc.set_current_feedback(value)


def main():
    from tango import GreenMode
    from tango.server import run
    import logging

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(threadName)s %(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    run([FuelCell], green_mode=GreenMode.Gevent)


if __name__ == "__main__":
    main()
