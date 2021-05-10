# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Tango shutter is used to control frontend or safety shutter or a valve.
Some commands/attributes (like automatic/manual) are only implemented in the
front end device server, set by the _frontend variable.

Example yml file:

.. code-block::

    -
      # front end shutter
      class: TangoShutter
      name: frontend
      uri: //orion:10000/fe/master/id42
    
    -
      # safety shutter
      class: TangoShutter
      name: safshut
      uri: id42/bsh/1
"""

from enum import Enum
from gevent import Timeout, sleep
from bliss import global_map
from bliss.common.shutter import BaseShutter, BaseShutterState
from bliss.common.tango import DeviceProxy, DevFailed
from bliss.common.logtools import log_warning, user_print
from bliss.config.channels import Channel
from bliss.common import event


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
        global_map.register(self, children_list=[self.__control], tag=f"Shutter:{name}")
        self._frontend = None
        self._mode = None
        self._init_type()

        self._state_channel = Channel(
            f"{name}:state", default_value="UNKNOWN", callback=self._state_changed
        )

    def _init_type(self):
        self._frontend = "FrontEnd" in self.__control.info().dev_class

    @property
    def proxy(self):
        return self.__control

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

    def _state_changed(self, stat):
        """Send a signal when state changes"""
        event.send(self, "state", stat)

    @property
    def state_string(self):
        """Return state as combined string.

        Returns
            (tuple): state as string, tango status
        """
        return self.state.value, self._tango_status

    def __info__(self):
        return self._tango_status.rstrip("\n")

    def open(self, timeout=60):
        """Open
        Args:
            (float): Timeout [s] to wait until execution finished
        Raises:
            RuntimeError: Cannot execute if device in wrong state
        """
        state = self.state

        if state.name in ("OPEN", "RUNNING"):
            log_warning(self, f"{self.name} already open, command ignored")
        elif state == TangoShutterState.DISABLE:
            log_warning(self, f"{self.name} disabled, command ignored")
        elif state == TangoShutterState.CLOSED:
            try:
                self.__control.open()
                self._wait(TangoShutterState.OPEN, timeout)
                user_print(f"{self.name} was {state.name} and is now {self.state.name}")
            except RuntimeError as err:
                raise
        else:
            raise RuntimeError(
                f"Cannot open {self.name}, current state is: {state.value}"
            )

    def close(self, timeout=60):
        """Close
        Args:
            (float): Timeout [s] to wait until execution finished
        Raises:
            RuntimeError: Cannot execute if device in wrong state
        """
        state = self.state
        if state == TangoShutterState.CLOSED:
            log_warning(self, f"{self.name} already closed, command ignored")
        elif state == TangoShutterState.DISABLE:
            log_warning(self, f"{self.name} disabled, command ignored")
        elif state.name in ("OPEN", "RUNNING"):
            try:
                self.__control.close()
                self._wait(TangoShutterState.CLOSED, timeout)
                user_print(f"{self.name} was {state.name} and is now {self.state.name}")
            except RuntimeError as err:
                raise
        else:
            raise RuntimeError(
                f"Cannot close {self.name}, current state is: {state.value}"
            )

    @property
    def mode(self):
        """
        Get or set the opening mode of the FrontEnd.
        state is read from tango attribute: `automatic_mode`.
        Only available for FrontEnd shutters.

        Parameters:
            mode: (str): 'MANUAL' or 'AUTOMATIC'

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
        if not self.frontend:
            raise NotImplementedError("Not a Frontend shutter")

        try:
            if mode == "MANUAL":
                self.__control.manual()
            elif mode == "AUTOMATIC":
                self.__control.automatic()
            else:
                raise RuntimeError(f"Unknown mode: {mode}")

            self._wait_mode(mode=mode)
        except DevFailed as df_err:
            raise RuntimeError(f"Cannot set {mode} opening") from df_err

    def reset(self):
        """Reset
        Args:
        Raises:
            RuntimeError: Cannot execute
        """
        self.__control.Reset()

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
            self._state_changed(self.state)

    def _wait_mode(self, mode, timeout=3):
        """
        Wait until set mode is equal to read mode.
        """
        with Timeout(timeout, RuntimeError(f"Cannot set {mode} opening mode")):

            # FE tango server feature: 'automatic_mode' goes True even
            # if it's not allowed (ex: MDT)
            # It switches back to False after ~1 second.
            # So this method can return without error even if AUTOMATIC
            # mode is not set properly.
            sleep(2)  # to be removed when FE tango server will be fixed.

            while self.mode != mode:
                # print(f"{self.mode} != {mode}")    # to be removed when FE tango server will be fixed.
                sleep(0.2)

            # for i in range(100):                   # to be removed when FE tango server will be fixed.
            #     print(f"{self.mode} =?  {mode}")   # to be removed when FE tango server will be fixed.
            #     sleep(0.05)                        # to be removed when FE tango server will be fixed.

    def __enter__(self):
        self.open()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
