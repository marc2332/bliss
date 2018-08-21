# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common.tango import DeviceProxy


class tango_transfocator:
    def __init__(self, name, config):
        tango_uri = config.get("uri")
        self.__control = None
        try:
            self.__control = DeviceProxy(tango_uri)
        except PyTango.DevFailed, traceback:
            last_error = traceback[-1]
            print "%s: %s" % (tango_uri, last_error["desc"])
            self.__control = None
        else:
            try:
                self.__control.ping()
            except PyTango.ConnectionFailed:
                self.__control = None
                raise RuntimeError("Connection error")

    def status_read(self):
        return self.__control.ShowLenses

    def tfin(self, lense):
        self.__control.LenseIn(lense)

    def tfout(self, lense):
        self.__control.LenseOut(lense)

    def tfstatus_set(self, stat):
        self.__control.TfStatus = stat
