# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import sys
import tango

from bliss.tango.servers import TgGevent
from bliss.controllers.temperature.eurotherm import nanodac


class _CallableRead:
    def __init__(self, obj, name):
        self.__obj = obj
        self.__name = name

    def __call__(self, attr):
        attr.set_value(getattr(self.__obj, self.__name)())


class _CallableWrite:
    def __init__(self, obj, name):
        self.__obj = obj
        self.__name = name

    def __call__(self, attr):
        value = attr.get_write_value()
        o_property = getattr(self.__obj, self.__name, value)
        o_property(value)


class Nanodac(tango.Device_4Impl):
    def __init__(self, *args):
        tango.Device_4Impl.__init__(self, *args)
        self.init_device()

    def init_device(self):
        self.set_state(tango.DevState.ON)
        self.get_device_properties(self.get_device_class())
        self._nanodac = TgGevent.get_proxy(
            nanodac.nanodac, "server", {"controller_ip": self.controller_ip}
        )
        self._ramp1 = TgGevent.get_proxy(self._nanodac.get_soft_ramp, 1)
        self._ramp2 = TgGevent.get_proxy(self._nanodac.get_soft_ramp, 2)
        self._c1 = TgGevent.get_proxy(self._nanodac.get_channel, 1)
        self._c2 = TgGevent.get_proxy(self._nanodac.get_channel, 2)
        self._c3 = TgGevent.get_proxy(self._nanodac.get_channel, 3)
        self._c4 = TgGevent.get_proxy(self._nanodac.get_channel, 4)

    def __getattr__(self, name):
        if name.startswith("read_") or name.startswith("write_"):
            try:
                _, mod_name, attr_name = name.split("_")
                mod = getattr(self, "_%s" % mod_name)
            except ValueError:
                _, main_mod_name, mod_name, attr_name = name.split("_")
                main_mod = getattr(self, "_%s" % main_mod_name)
                main_mod = main_mod.get_base_obj()
                mod = TgGevent.get_proxy(getattr, main_mod, mod_name)

            if name.startswith("read_"):
                func = _CallableRead(mod, attr_name)
            else:
                func = _CallableWrite(mod, attr_name)
            self.__dict__[name] = func
            return func

        raise AttributeError("Nanodac has no attribute %s" % name)

    def stop(self):
        self._ramp.stop()


class NanodacClass(tango.DeviceClass):
    #    Class Properties
    class_property_list = {}

    #    Device Properties
    device_property_list = {
        "controller_ip": [tango.DevString, "Ethernet ip address", []]
    }
    #    Command definitions
    cmd_list = {"stop": [[tango.DevVoid, ""], [tango.DevVoid, ""]]}

    #    Attribute definitions
    attr_list = {
        # Ramp1
        "ramp1_slope": [[tango.DevDouble, tango.SCALAR, tango.READ_WRITE]],
        "ramp1_workingsp": [[tango.DevDouble, tango.SCALAR, tango.READ]],
        "ramp1_targetsp": [[tango.DevDouble, tango.SCALAR, tango.READ_WRITE]],
        "ramp1_pv": [[tango.DevDouble, tango.SCALAR, tango.READ]],
        "ramp1_pid_derivativetime": [[tango.DevDouble, tango.SCALAR, tango.READ_WRITE]],
        "ramp1_pid_integraltime": [[tango.DevDouble, tango.SCALAR, tango.READ_WRITE]],
        "ramp1_pid_proportionalband": [
            [tango.DevDouble, tango.SCALAR, tango.READ_WRITE]
        ],
        # Ramp2
        "ramp2_slope": [[tango.DevDouble, tango.SCALAR, tango.READ_WRITE]],
        "ramp2_workingsp": [[tango.DevDouble, tango.SCALAR, tango.READ]],
        "ramp2_targetsp": [[tango.DevDouble, tango.SCALAR, tango.READ_WRITE]],
        "ramp2_pv": [[tango.DevDouble, tango.SCALAR, tango.READ]],
        "ramp2_pid_derivativetime": [[tango.DevDouble, tango.SCALAR, tango.READ_WRITE]],
        "ramp2_pid_integraltime": [[tango.DevDouble, tango.SCALAR, tango.READ_WRITE]],
        "ramp2_pid_proportionalband": [
            [tango.DevDouble, tango.SCALAR, tango.READ_WRITE]
        ],
        # Channel 1
        "c1_pv": [[tango.DevDouble, tango.SCALAR, tango.READ]],
        "c1_pv2": [[tango.DevDouble, tango.SCALAR, tango.READ]],
        "c1_type": [[tango.DevString, tango.SCALAR, tango.READ]],
        "c1_lintype": [[tango.DevString, tango.SCALAR, tango.READ]],
        # Channel 2
        "c2_pv": [[tango.DevDouble, tango.SCALAR, tango.READ]],
        "c2_pv2": [[tango.DevDouble, tango.SCALAR, tango.READ]],
        "c2_type": [[tango.DevString, tango.SCALAR, tango.READ]],
        "c2_lintype": [[tango.DevString, tango.SCALAR, tango.READ]],
        # Channel 3
        "c3_pv": [[tango.DevDouble, tango.SCALAR, tango.READ]],
        "c3_pv2": [[tango.DevDouble, tango.SCALAR, tango.READ]],
        "c3_type": [[tango.DevString, tango.SCALAR, tango.READ]],
        "c3_lintype": [[tango.DevString, tango.SCALAR, tango.READ]],
        # Channel 4
        "c4_pv": [[tango.DevDouble, tango.SCALAR, tango.READ]],
        "c4_pv2": [[tango.DevDouble, tango.SCALAR, tango.READ]],
        "c4_type": [[tango.DevString, tango.SCALAR, tango.READ]],
        "c4_lintype": [[tango.DevString, tango.SCALAR, tango.READ]],
    }


def main():
    try:
        py = tango.Util(sys.argv)
        py.add_TgClass(NanodacClass, Nanodac, "Nanodac")
        U = tango.Util.instance()
        U.server_init()
        U.server_run()
    except:
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
