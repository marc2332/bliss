# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import absolute_import

import sys
import tango
from tango import GreenMode
from tango.server import Device
from tango.server import device_property
from tango.server import attribute, command
from bliss.config import static


class Multiplexer(Device):
    multiplexer_name = device_property(dtype="str")

    def __init__(self, *args, **kwargs):
        Device.__init__(self, *args, **kwargs)
        self.__multiplexer = None
        self.init_device()

    def init_device(self):
        Device.init_device(self)
        self.set_state(tango.DevState.FAULT)
        self.get_device_properties(self.get_device_class())
        config = static.get_config()
        self.__multiplexer = config.get(self.multiplexer_name)
        self.__multiplexer.load_program()
        self.set_state(tango.DevState.ON)

    @attribute(dtype=("str",), max_dim_x=1024, label="Output list")
    def outputs(self):
        return self.__multiplexer.getOutputList()

    @attribute(dtype=("str",), max_dim_x=2048, label="Output status")
    def outputs_status(self):
        returnList = []
        for item in self.__multiplexer.getGlobalStat().iteritems():
            returnList.extend(item)
        return returnList

    @attribute(dtype=("str",), max_dim_x=2048, label="Output key and name")
    def outputs_key_name(self):
        returnList = []
        for item in self.__multiplexer.getKeyAndName().iteritems():
            returnList.extend(item)
        return returnList

    @attribute(dtype=("str",), max_dim_x=32, label="Opiom programs")
    def opiom_prog(self):
        returnList = []
        for id, val in self.__multiplexer.getOpiomProg().iteritems():
            returnList.append("%s : %s" % (id, val))
        return returnList

    @attribute(dtype=bool, label="Debug flag")
    def debug(self):
        return self.__multiplexer.getDebug()

    @debug.setter
    def debug(self, flag):
        self.__multiplexer.setDebug(flag)

    @command(dtype_in=("str",))
    def switch(self, values):
        self.__multiplexer.switch(*values)

    @command(dtype_in=("str",), dtype_out="str")
    def raw_com(self, values):
        return self.__multiplexer.raw_com(*values) or ""

    @command(dtype_in="str", dtype_out=("str",))
    def getPossibleOutputValues(self, output_key):
        return self.__multiplexer.getPossibleValues(output_key)

    @command(dtype_in="str", dtype_out="str")
    def getOutputStat(self, output_key):
        return self.__multiplexer.getOutputStat(output_key)

    @command(dtype_in="str")
    def storeCurrentStat(self, stat):
        self.__multiplexer.storeCurrentStat(stat)

    @command(dtype_in="str")
    def restoreStat(self, stat):
        self.__multiplexer.restoreStat(stat)

    @command(dtype_out=("str",))
    def getSavedStats(self):
        return self.__multiplexer.getSavedStats()

    @command(dtype_in="str")
    def removeSavedStat(self, stat):
        self.__multiplexer.rmStat(stat)

    @command
    def dumpOpiomSource(self):
        self.__multiplexer.dumpOpiomSource()


def main(args=None, **kwargs):
    from tango.server import run

    kwargs["green_mode"] = kwargs.get("green_mode", GreenMode.Gevent)
    return run((Multiplexer,), args=args, **kwargs)


if __name__ == "__main__":
    main()
