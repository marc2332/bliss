# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from gevent import Timeout, sleep

from bliss.common.tango import DeviceProxy, DevFailed

from bliss.common.shutter import BaseShutter

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


class tango_shutter(BaseShutter):
    def __init__(self, name, config):
        tango_uri = config.get("uri")
        self.__name = name
        self.__config = config
        self.__control = DeviceProxy(tango_uri)
        self._frontend = "FrontEnd" in self.__control.info().dev_class
        self._mode = False

    @property
    def name(self):
        """A unique name"""
        return self.__name

    @property
    def config(self):
        """Config of shutter"""
        return self.__config

    @property
    def state(self):
        try:
            s = self._tango_state
            if s == "OPEN":
                return self.OPEN
            elif s == "CLOSE":
                return self.CLOSED
            else:
                return self.OTHER
        except DevFailed:
            raise RuntimeError(
                "Shutter {}: Communication error with {}".format(
                    self.__name, self.__control.dev_name()
                )
            )
            return self.UNKNOWN

    @property
    def _tango_state(self):
        return str(self.__control.state())

    @property
    def state_string(self):
        s = self.state
        if s in [self.OPEN, self.CLOSED, self.UNKNOWN]:
            return self.STATE2STR.get(s, self.STATE2STR[self.UNKNOWN])
        else:
            return self._tango_state + ":\t" + self._tango_status

    @property
    def _tango_status(self):
        return str(self.__control.status())

    def open(self):
        state = self._tango_state
        if state == "STANDBY":
            raise RuntimeError("Cannot open shutter in STANDBY state")
        if state == "OPEN":
            # user log message: shutter already open
            return
        if state == "CLOSE":
            try:
                self.__control.open()
                self._wait("OPEN", 5)
            except:
                raise RuntimeError("Cannot open shutter")
        else:
            raise RuntimeError("Trouble opening shutter: " + self.state_string)
        return

    def close(self):
        state = self._tango_state
        if state == "OPEN" or state == "RUNNING":
            try:
                self.__control.close()
                self._wait("CLOSE", 5)
            except:
                raise RuntimeError("Cannot close shutter")
        else:
            raise RuntimeError("Trouble closing shutter: " + str(self.state_string))

    def set_automatic(self):
        if not self._frontend:
            raise NotImplementedError("Not a Front End shutter")

        # try to set to automatic if manual mode only.
        if self._mode == "MANUAL":
            s = self._tango_state
            if s == "CLOSE" or s == "OPEN":
                try:
                    self.__control.automatic()
                    self._wait_mode(mode="AUTOMATIC")
                except:
                    raise RuntimeError("Cannot set automatic mode closing")
            else:
                ## TODO some user log message
                pass

    def set_manual(self):
        if not self._frontend:
            raise NotImplementedError("Not a Front End shutter")

        # try to set to manual if automatic mode only.
        if self._mode == "AUTOMATIC":
            s = self._tango_state
            if s == "CLOSE" or s == "RUNNING":
                try:
                    self.__control.manual()
                    self._wait_mode(mode="MANUAL")
                except:
                    raise RuntimeError("Cannot set manual mode closing")
            else:
                pass
                # TODO some user log message

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
            while self._tango_state != state:
                sleep(1)
            # TODO: user log message with new state

    def _wait_mode(self, mode, timeout=3):
        with Timeout(timeout):
            while self.get_closing_mode() != mode:
                sleep(1)
            # TODO: user log message with new mode

    def __enter__(self):
        self.open()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
