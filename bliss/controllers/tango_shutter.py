# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Tango shutter is used to control frontend or safety shutter or a valve.
Some commands/attributes (like automatic/manual) are only implemented in the
front end device server, set by the _frontend variable.

example yml file:
-
  # front end shutter
  class: TangoShutter
  name: frontend
  uri: //orion:10000/fe/master/id30

-
  # safety shutter
  class: TangoShutter
  name: safshut
  uri: id30/bsh/1
"""

from enum import Enum
from gevent import Timeout, sleep
from bliss.common.shutter import BaseShutter, BaseShutterState
from bliss.common.tango import DeviceProxy, DevFailed
from bliss.common.logtools import log_warning


TangoShutterState = Enum(
    "TangoShutterState",
    dict(
        {
            "MOVING": "Moving",
            "DISABLE": "Hutch not searched",
            "STANDBY": "Wait for permission",
            "RUNNING": "Automatic opening",
        },
        **{item.name: item.value for item in BaseShutterState},
    ),
)


class TangoShutter(BaseShutter):
    """ Handle Tango frontend or safety shutter or a valve"""

    def __init__(self, name, config):
        tango_uri = config.get("uri")
        self.__name = name
        self.__config = config
        self.__control = DeviceProxy(tango_uri)
        self._frontend = None
        self._mode = None
        self._init_type()

    def _init_type(self):
        self._frontend = "FrontEnd" in self.__control.info().dev_class

    @property
    def frontend(self):
        """ Check if the device is a front end type
        Returns:
            (bool): True if it is a front end, False otherwise
        """
        if self._frontend is None:
            self._init_type()
        return self._frontend

    @property
    def name(self):
        """A unique name"""
        return self.__name

    @property
    def config(self):
        """Config of shutter"""
        return self.__config

    @property
    def _tango_state(self):
        """ Read the tango state. Available PyTango states: 'ALARM', 'CLOSE',
            'DISABLE', 'EXTRACT', 'FAULT', 'INIT', 'INSERT', 'MOVING', 'OFF',
            'ON', 'OPEN', 'RUNNING', 'STANDBY', 'UNKNOWN'.
        Returns:
            (str): The state from the device server.
        """
        return self.__control.state().name

    @property
    def _tango_status(self):
        """ Read the status.
        Returns:
            (str): Complete state from the device server.
        """
        return self.__control.status()

    @property
    def state(self):
        """ Read the state.
        Returns:
            (enum): state as enum
        Raises:
            RuntimeError: If DevFailed from the device server
        """
        try:
            state = self._tango_state
            if "CLOSE" in state:
                return TangoShutterState.CLOSED
            return TangoShutterState.__members__[state]
        except DevFailed:
            raise RuntimeError(f"Communication error with {self.__control.dev_name()}")

    @property
    def state_string(self):
        """Return state as combined string
        Returns
            (tuple): state as string, tango status
        """
        return self.state.value, self._tango_status

    def open(self, timeout=60):
        """Open
        Args:
            (float): Timeout [s] to wait until execution finished
        Raises:
            RuntimeError: Cannot execute if device in wrong state
        """
        state = self.state
        if state.name in ("OPEN", "RUNNING"):
            log_warning(self, "Already open, command ignored")
        if state == TangoShutterState.CLOSED:
            try:
                self.__control.open()
                self._wait(TangoShutterState.OPEN, timeout)
            except RuntimeError as err:
                print(err)
                raise
        else:
            raise RuntimeError(f"Cannot open: {state.value}")

    def close(self, timeout=60):
        """Close
        Args:
            (float): Timeout [s] to wait until execution finished
        Raises:
            RuntimeError: Cannot execute if device in wrong state
        """
        state = self.state
        if state == TangoShutterState.CLOSED:
            log_warning(self, "Already closed, command ignored")
        elif state.name in ("OPEN", "RUNNING"):
            try:
                self.__control.close()
                self._wait(TangoShutterState.CLOSED, timeout)
            except RuntimeError as err:
                print(err)
                raise
        else:
            raise RuntimeError(f"Cannot close: {state.value}")

    @property
    def mode(self):
        """ Get the opening mode.
        Raises:
            NotImplementedError: Not a Frontend shutter
        """
        if not self.frontend:
            raise NotImplementedError("Not a Frontend shutter")

        try:
            _mode = self.__control.automatic_mode
        except AttributeError:
            _mode = None
        self._mode = "AUTOMATIC" if _mode else "MANUAL" if _mode is False else "UNKNOWN"
        return self._mode

    @mode.setter
    def mode(self, mode):
        """Set the frontend opening mode
        Args:
            mode (str): MANUAL or AUTOMATIC
        Raises: NotImplementedError: Not a Fronend shutter.
        """
        if not self.frontend:
            raise NotImplementedError("Not a Frontend shutter")

        try:
            if mode == "MANUAL":
                self.__control.manual()
            elif mode == "AUTOMATIC":
                self.__control.automatic()
            self._wait_mode(mode=mode)
        except DevFailed:
            raise RuntimeError(f"Cannot set {mode} opening")

    def _wait(self, state, timeout=3):
        """Wait execution to finish
        Args:
            (enum): state
            (float): timeout [s].
        Raises:
            RuntimeError: Execution timeout.
        """
        with Timeout(timeout, RuntimeError("Execution timeout")):
            while self.state != state:
                sleep(1)

    def _wait_mode(self, mode, timeout=3):
        with Timeout(timeout, RuntimeError(f"Cannot set {mode} opening")):
            while self.mode != mode:
                sleep(1)

    def __enter__(self):
        self.open()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
