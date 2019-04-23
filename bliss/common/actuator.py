# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import gevent
from .event import dispatcher
import enum


@enum.unique
class ActuatorState(enum.IntEnum):
    """ Actuator States Class """

    UNKNOWN = 0
    IN = 1
    OUT = 2
    MOVING = 3


class AbstractActuator:
    """ Abstract Actuator """

    def __init__(self, set_in=None, set_out=None, is_in=None, is_out=None, check=True):
        self.__in = False
        self.__out = False
        if any((set_in, set_out, is_in, is_out)):
            self._set_in = set_in
            self._set_out = set_out
            self._is_in = is_in
            self._is_out = is_out
        self._check = check

    def __repr__(self):
        return self.state

    def set_in(self, timeout=None):
        """ Set the actuator in position IN
        Args:
           timeout (float): timeout [s] after which the action is not
                            completed, if check set
        Raises:
           Timeout: timeout (if check the position asked)
        """
        # this is to know which command was asked for,
        # in case we don't have a return (no 'self._is_in' or out)
        self.__in = True
        self.__out = False

        if self._check:
            try:
                with gevent.Timeout(timeout, "Timeout while setting IN"):
                    while True:
                        self._set_in()
                        if self.is_in():
                            break
                        else:
                            gevent.sleep(0.5)
            finally:
                dispatcher.send("state", self, self.state)

    def set_out(self, timeout=None):
        """ Set the actuator in position OUT
        Args:
           timeout (float): timeout [s] after which the action is not
                            completed, if check set
        Raises:
           Timeout: timeout (if check the position asked)
        """
        self.__out = True
        self.__in = False

        if self._check:
            try:
                with gevent.Timeout(timeout, "Timeout while setting OUT"):
                    while True:
                        self._set_out()
                        if self.is_out():
                            break
                        else:
                            gevent.sleep(0.5)
            finally:
                dispatcher.send("state", self, self.state)

    def is_in(self):
        """ Check if the actuator is in position IN.
        Returns:
            (bool): True if IN, False otherwise
        """
        if self._is_in is not None:
            ret = self._is_in()
            if ret is not None:
                return self._is_in()
        else:
            if self._is_out is not None:
                ret = self._is_out()
                if ret is not None:
                    return not self._is_out()
        return self.__in

    def is_out(self):
        """ Check if the actuator is in position OUT.
        Returns:
            (bool): True if OUT, False otherwise
        """
        if self._is_out is not None:
            ret = self._is_out()
            if ret is not None:
                return self._is_out()
        else:
            if self._is_in is not None:
                ret = self._is_in()
                if ret is not None:
                    return not self._is_in()
        return self.__out

    def toggle(self, timeout=None):
        """ Toggle between IN/OUT
        Args:
           timeout (float): timeout [s] after which the action is not
                            completed, if check set
        Raises:
           Timeout: timeout (if check the position asked)
        """
        if self.is_in():
            self.set_out(timeout)
        elif self.is_out():
            self.set_in(timeout)

    @property
    def state(self):
        """ Get the state of the actuator
        Returns:
            (str): The state of the actuator
        """
        state = ActuatorState.UNKNOWN
        if self.is_in():
            state += ActuatorState.IN
        if self.is_out():
            state += ActuatorState.OUT
        for st in ActuatorState:
            if state == st:
                return st.name
        return ActuatorState.UNKNOWN.name

    """ Sometimes it is more natural to use open/close than set_in/set_out """

    def close(self, timeout=None):
        """ Open means beam after the actuator
        """
        self.set_out(timeout)

    def open(self, timeout=None):
        """ Close means no beam after the actuator
        """

        self.set_in(timeout)

    """ Context manager methods """

    def __enter__(self):
        self.set_in()

    def __exit__(self, *args):
        self.set_out()
