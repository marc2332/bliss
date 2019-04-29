# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

""" Tango Device Server for Musst

Multipurpose Unit for Synchronisation, Sequencing and Triggering
"""


__all__ = ["Musst", "main"]

# tango imports
import sys
import tango
from tango import DebugIt
from tango.server import run
from tango.server import Device
from tango.server import attribute, command
from tango.server import class_property, device_property
from tango import AttrQuality, AttrWriteType, DispLevel, DevState
from tango.server import get_worker

# Additional import
from bliss.controllers.musst import musst as musst_ctrl


class Musst(Device):

    # -----------------
    # Device Properties
    # -----------------
    url = device_property(
        dtype=str,
        doc="* `enet://<host>:<port>` for NI ENET adapter\n"
        "* `prologix://<host>:<port>` for prologix adapter",
    )
    pad = device_property(dtype=int, default_value=0, doc="primary address")
    sad = device_property(dtype=int, default_value=0, doc="secondary address")
    timeout = device_property(dtype=float, default_value=1., doc="socket timeout")
    tmo = device_property(dtype=int, default_value=13, doc="gpib time limit")
    eot = device_property(dtype=int, default_value=1)
    eos = device_property(dtype=str, default_value="\n")
    name = device_property(dtype=str, default_value="musst")

    # ----------
    # Attributes
    # ----------
    @attribute(label="Current Event Buffer", dtype=int)
    def EventBuffer(self):
        return int(self._musst.EBUFF)

    @EventBuffer.write
    def EventBuffer(self, ebuff):
        self._musst.EBUFF = ebuff

    @attribute(label="TimeBase Frequency", dtype=str)
    def TimeBaseFrequency(self):
        return self.__frequency_conversion[self._musst.TMRCFG]

    @TimeBaseFrequency.write
    def TimeBaseFrequency(self, tmrcfg):
        self._musst.TMRCFG = tmrcfg

    # ---------------
    # General methods
    # ---------------
    def __init__(self, *args, **kwargs):
        self._musst = None
        Device.__init__(self, *args, **kwargs)

        self._musst2tangostate = {
            musst_ctrl.NOPROG_STATE: tango.DevState.OFF,
            musst_ctrl.BADPROG_STATE: tango.DevState.UNKNOWN,
            musst_ctrl.IDLE_STATE: tango.DevState.ON,
            musst_ctrl.RUN_STATE: tango.DevState.RUNNING,
            musst_ctrl.BREAK_STATE: tango.DevState.STANDBY,
            musst_ctrl.STOP_STATE: tango.DevState.STANDBY,
            musst_ctrl.ERROR_STATE: tango.DevState.FAULT,
        }

        self._musststate2string = {
            musst_ctrl.NOPROG_STATE: "No Program loaded in Musst",
            musst_ctrl.BADPROG_STATE: "Musst has a bad program loaded",
            musst_ctrl.IDLE_STATE: "Musst program loaded in idle state",
            musst_ctrl.RUN_STATE: "Musst is running program",
            musst_ctrl.BREAK_STATE: "Musst progam at breakpoint",
            musst_ctrl.STOP_STATE: "Musst program stopped",
            musst_ctrl.ERROR_STATE: "Musst has an error condition",
        }

        self.__frequency_conversion = {
            musst_ctrl.F_1KHZ: "1KHZ",
            musst_ctrl.F_10KHZ: "10KHZ",
            musst_ctrl.F_100KHZ: "100KHZ",
            musst_ctrl.F_1MHZ: "1MHZ",
            musst_ctrl.F_10MHZ: "10MHZ",
            musst_ctrl.F_50MHZ: "50MHZ",
        }

    def init_device(self):
        Device.init_device(self)
        kwargs = {
            "gpib_url": self.url,
            "gpib_pad": self.pad,
            "gpib_timeout": self.timeout,
            "gpib_eos": self.eos,
        }
        self._musst = musst_ctrl(self.name, kwargs)
        self.create_dynamic_attributes()

    def always_executed_hook(self):
        pass

    def delete_device(self):
        pass

    # ------------------
    # Dynamics Attributes methods
    # ------------------
    @DebugIt()
    def create_dynamic_attributes(self):
        var_list = self._musst.LISTVAR
        add = False
        for line in var_list.splitlines():
            if add == True:
                name, type, var = line.split()
                if type == "FLOAT":
                    print("adding float variable attribute ", var)
                    floatVarAttr = tango.Attr(var, tango.DevDouble, tango.READ_WRITE)
                    self.add_attribute(
                        floatVarAttr,
                        Musst.read_floatVarAttr,
                        Musst.write_floatVarAttr,
                        None,
                    )
                elif type == "UNSIGNED":
                    print("adding unsigned variable attribute ", var)
                    longVarAttr = tango.Attr(var, tango.DevLong, tango.READ_WRITE)
                    self.add_attribute(
                        longVarAttr,
                        Musst.read_longVarAttr,
                        Musst.write_longVarAttr,
                        None,
                    )
            elif line == "Scalars:":
                add = True

    @DebugIt()
    def read_floatVarAttr(self, attr):
        worker = get_worker()
        value = worker.execute(self.__read_DynAttr, attr)
        attr.set_value(float(value))

    @DebugIt()
    def write_floatVarAttr(self, attr):
        self._musst.set_variable(attr.get_name(), float(attr.get_write_value()))

    @DebugIt()
    def read_longVarAttr(self, attr):
        worker = get_worker()
        value = worker.execute(self.__read_DynAttr, attr)
        attr.set_value(int(value))

    @DebugIt()
    def write_longVarAttr(self, attr):
        self._musst.set_variable(attr.get_name(), int(attr.get_write_value()))

    def __read_DynAttr(self, attr):
        return self._musst.get_variable(attr.get_name())

    # --------
    # Commands
    # --------

    @command(dtype_out="DevState", doc_out="Device state")
    @DebugIt()
    def dev_state(self):
        return self._musst2tangostate[self._musst.STATE]

    @command(dtype_out="str", doc_out="Device status")
    @DebugIt()
    def dev_status(self):
        return self._musststate2string[self._musst.STATE]

    @command
    @DebugIt()
    def clear(self):
        self._musst.CLEAR

    @command(
        dtype_in="str",
        doc_in="program name or a program label where the execution start",
    )
    @DebugIt()
    def run(self, entry=""):
        self._musst.run(entry)

    @command(
        dtype_in=int, doc_in="If time is specified, the counters run for that time"
    )
    @DebugIt()
    def ct(self, time=None):
        self._musst.run(time)

    @command
    @DebugIt()
    def abort(self):
        self._musst.ABORT

    @command
    @DebugIt()
    def cont(self):
        self._musst.CONT

    @command
    @DebugIt()
    def reset(self):
        self._musst.RESET

    @command(dtype_in=str, doc_in="Program filename")
    def load(self, fname):
        file = open(fname)
        self._musst.upload_program(file.read())
        self.create_dynamic_attributes()

    @command(dtype_out=str, doc_out="List the current program")
    @DebugIt()
    def list(self):
        return self._musst.LIST

    @command(dtype_out=str, doc_out="Returns the list of installed daughter boards")
    @DebugIt()
    def dbinfo(self):
        return self._musst.DBINFO

    @command(dtype_out=str, doc_out="Query module configuration")
    @DebugIt()
    def info(self):
        return self._musst.INFO

    @command(dtype_out=str, doc_out="Query exit or stop code")
    @DebugIt()
    def retcode(self):
        return self._musst.RETCODE

    @command
    @DebugIt()
    def varinit(self):
        self._musst.VARINIT


# ----------
# Run server
# ----------


def main():
    from tango import GreenMode
    from tango.server import run

    run([Musst], green_mode=GreenMode.Gevent)


if __name__ == "__main__":
    main()
