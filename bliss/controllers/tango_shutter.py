# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from gevent import Timeout, sleep

from bliss.common.tango import DeviceProxy, DevFailed

"""
Tango shutter is used to control both front end and safetry shutter.
Some commands/attributes (like atomatic/manual) are only implemented in the
front end device server, set by the _frontend variable.

example yml file:

-
  #front end shutter
  class: tango_shutter
  name: frontend
  uri: //orion:10000/fe/id/30

-
  #safety shutter
  class:tango_shutter
  name: safshut
  uri: id30/bsh/1
"""


class tango_shutter:
    def __init__(self, name, config):
        tango_uri = config.get("uri")
        self.name = name
        self.__control = DeviceProxy(tango_uri)
        self._frontend = "FrontEnd" in self.__control.info().dev_class
        self._mode = False

    def get_status(self):
        print(self.__control.status())

    def get_state(self):
        return str(self.__control.state())

    def open(self):
        state = self.get_state()
        if state == "STANDBY":
            raise RuntimeError("Cannot open shutter in STANDBY state")
        if state == "CLOSE":
            try:
                self.__control.open()
                self._wait("OPEN", 5)
            except:
                raise RuntimeError("Cannot open shutter")
        else:
            print(self.__control._status())

    def close(self):
        state = self.get_state()
        if state == "OPEN" or state == "RUNNING":
            try:
                self.__control.close()
                self._wait("CLOSE", 5)
            except:
                raise RuntimeError("Cannot close shutter")
        else:
            self.get_status()

    def set_automatic(self):
        if not self._frontend:
            raise NotImplementedError("Not a Front End shutter")

        # try to set to automatic if manual mode only.
        if self._mode == "MANUAL":
            state = self.get_state()
            if state == "CLOSE" or state == "OPEN":
                try:
                    self.__control.automatic()
                    self._wait_mode(mode="AUTOMATIC")
                except:
                    raise RuntimeError("Cannot set automatic mode closing")
            else:
                self.get_status()

    def set_manual(self):
        if not self._frontend:
            raise NotImplementedError("Not a Front End shutter")

        # try to set to manual if automatic mode only.
        if self._mode == "AUTOMATIC":
            state = self.get_state()
            if state == "CLOSE" or state == "RUNNING":
                try:
                    self.__control.manual()
                    self._wait_mode(mode="MANUAL")
                except:
                    raise RuntimeError("Cannot set manual mode closing")
            else:
                self.get_status()

    def get_closing_mode(self):
        if not self._frontend:
            raise NotImplementedError("Not a Front End shutter")
        try:
            _mode = self.__control.automatic_mode
        except Exception:
            _mode = None
        self._mode = "AUTOMATIC" if _mode else "MANUAL" if _mode == False else "UNKNOWN"
        return self._mode

    def _wait(self, state, timeout=3):
        with Timeout(timeout):
            while self.get_state() != state:
                sleep(1)

    def _wait_mode(self, mode, timeout=3):
        with Timeout(timeout):
            while self.get_closing_mode() != mode:
                sleep(1)

    def __repr__(self):
        try:
            return self.__control.status()
        except DevFailed:
            return "Shutter {}: Communication error with {}".format(
                self.name, self.__control.dev_name()
            )

    def __enter__(self):
        self.open()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
