# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Classes implemented with temperature Controller
"""

import math

import gevent
import gevent.event
from bliss.common import session
from bliss.common.task import task
from bliss.common.logtools import LogMixin
from bliss.common.utils import with_custom_members
from bliss.common.measurement import SamplingCounter, counter_namespace


class TempControllerCounter(SamplingCounter):
    """ Implements access to counter object for
        Input and Output type objects
    """

    def __init__(self, name, parent):
        SamplingCounter.__init__(
            self, name, parent, unit=parent.config.get("unit", None)
        )
        self.parent = parent

    def read(self):
        data = self.parent.read()
        return data


@with_custom_members
class Input(LogMixin):
    """ Implements the access to temperature sensors
    """

    def __init__(self, controller, config):
        """ Constructor """
        # log.debug("  config type is: %s" % type(config))
        # log.debug("  controller type is: %s" % type(controller))
        self.__controller = controller
        self.__name = config["name"]
        self.__config = config

        session.get_current().map.register(
            self, parents_list=[controller, "counters"], tag=f"{self.name}"
        )

        # useful attribute for a temperature controller writer
        self._attr_dict = {}

    @property
    def controller(self):
        """ Returns the temperature controller """
        return self.__controller

    @property
    def name(self):
        """ returns the sensor name """
        return self.__name

    @property
    def config(self):
        """ returns the sensor config """
        return self.__config

    @property
    def counter(self):
        """ returns the counter object """
        return TempControllerCounter(self.name, self)

    @property
    def counters(self):
        """Standard counter namespace."""
        return counter_namespace([self.counter])

    def read(self):
        """ returns the sensor value """
        self._logger.debug("On Input:read")
        return self.controller.read_input(self)

    def state(self):
        """ returns the sensor state """
        self._logger.debug("On Input:state")
        return self.controller.state_input(self)


@with_custom_members
class Output(LogMixin):
    """ Implements the access to temperature heaters """

    def __init__(self, controller, config):
        """ Constructor """
        self.__controller = controller
        self.__name = config["name"]
        try:
            self.__limits = (config.get("low_limit"), config.get("high_limit"))
        except:
            self.__limits = (None, None)
        self.__setpoint_task = None
        self.__setpoint_event_poll = 0.02
        try:
            self.__deadband = float(config["deadband"])
        except:
            self.__deadband = None
        self.__config = config
        self.__ramping = 0
        self.__mode = 0
        # if defined as  self.deadband, attribute available from the instance
        # if defined as  self.__deadband, not available.
        #     in that case, use of decorator property offers it (read only) to world

        # useful attribute for a temperature controller writer
        self._attr_dict = {}

        session.get_current().map.register(
            self, parents_list=[controller, "counters"], tag=f"{self.name}"
        )

    @property
    def controller(self):
        """ returns the temperature controller """
        return self.__controller

    @property
    def name(self):
        """ returns the heater name """
        return self.__name

    @property
    def config(self):
        """ returns the heater config """
        return self.__config

    @property
    def limits(self):
        """ returns the limits for the heater temperature setting """
        return self.__limits

    @property
    def deadband(self):
        """ returns the deadband acceptable for the heater temperature setting.
            After a ramp or a set, the setpoint is considered to be reached
            only if heater value is within the deadband.
            While the setpoint is not reached, a wait will block on it."""
        return self.__deadband

    @property
    def counter(self):
        """ returns the counter object """
        return TempControllerCounter(self.name, self)

    @property
    def counters(self):
        """Standard counter namespace."""
        return counter_namespace([self.counter])

    def read(self):
        """ returns the heater value """
        self._logger.debug("On Output:read")
        return self.controller.read_output(self)

    def ramp(self, new_setpoint=None, wait=False, **kwargs):
        """ Starts a ramp on an output.
            - if no setpoint is provided, returns the present setpoint value
            - by default does not wait.
            - it is possible to provide kwargs arguments

            The related controller methods to be filled are:
            - get_setpoint
            - setpoint_stop
            - setpoint_abort
            - start_ramp
        """
        self._logger.debug("On Output:ramp %s" % new_setpoint)
        self.__mode = 1
        return self._ramp(new_setpoint, wait, **kwargs)

    def set(self, new_setpoint=None, wait=False, **kwargs):
        """ Sets as quickly as possible a temperature.
            - if no setpoint is provided, returns the present setpoint value
            - by default does not wait.
            - it is possible to provide kwargs arguments

            The related controller methods to be filled are:
            - get_setpoint
            - setpoint_stop
            - setpoint_abort
            - set
        """
        self._logger.debug("On Output:set %s" % new_setpoint)
        self.__mode = 0
        return self._ramp(new_setpoint, wait, **kwargs)

    def _ramp(self, new_setpoint=None, wait=False, **kwargs):
        """ starts the ramp tasks.
        """
        self._logger.debug("On Output:_ramp %s" % new_setpoint)
        if new_setpoint is not None:
            ll, hl = self.limits
            if ll is not None and new_setpoint < ll:
                raise RuntimeError(
                    "Invalid setpoint `%f', below low limit (%f)" % (new_setpoint, ll)
                )
            if hl is not None and new_setpoint > hl:
                raise RuntimeError(
                    "Invalid setpoint `%f', above high limit (%f)" % (new_setpoint, hl)
                )

            self.__setpoint_task = self._start_setpoint(new_setpoint, **kwargs)

            if wait:
                self.wait()
        else:
            return self.controller.get_setpoint(self)

    def wait(self):
        """ Waits on a setpoint task
        """
        self._logger.debug("On Output:wait")
        try:
            self.__setpoint_task.get()
        except KeyboardInterrupt:
            self.stop()

    def _setpoint_state(self, deadband=None):
        """
        Return a string representing the setpoint state of an Output class type object.
        If a setpoint is set (by ramp or by direct setting) on an ouput, the status
        will be RUNNING until it is in the deadband.
        This RUNNING state is used by the ramping event loop in the case a user wants
        to block on the Output ramp method (wait=True)

        If deadband is None, returns immediately READY

        Args:
           toutput:  Output class type object
           deadband: deadband attribute of toutput.

        Returns:
           object state string: READY/RUNNING from [READY/RUNNING/ALARM/FAULT]

        """
        deadband = self.deadband if deadband is None else deadband
        self._logger.debug("On output:_setpoint_state: %s" % (deadband))
        if deadband is None:
            return "READY"
        mysp = self.controller.get_setpoint(self)
        if mysp is None:
            return "READY"
        if math.fabs(self.controller.read_output(self) - mysp) <= deadband:
            return "READY"
        else:
            return "RUNNING"

    def stop(self):
        """ Stops a setpoint task.
            Calls the controller method setpoint_stop
        """
        self._logger.debug("On Output: stop")
        if self.__setpoint_task and not self.__setpoint_task.ready():
            self.__setpoint_task.kill()
        self.controller.setpoint_stop(self)

    def abort(self):
        """ Aborts a setpoint task.
            Calls the controller method setpoint_abort
        """
        self._logger.debug("On Output: abort")
        if self.__setpoint_task and not self.__setpoint_task.ready():
            self.__setpoint_task.kill()
        self.controller.setpoint_abort(self)

    def rampstate(self):
        """
        Returns the setpoint state:

        - RUNNING: means that output object read value
          is outside setpoint deadband
        - READY: inside the deadband
        """
        if self.__ramping == 1:
            return "RUNNING"
        else:
            return "READY"

    def _do_setpoint(self, setpoint):
        """ Subtask launching the setpoint
            Polls until setpoint is reached
            Is a gevent coroutine
        """
        self._logger.debug("On Output:_do_setpoint : mode = %s" % (self.__mode))
        try:
            while self._setpoint_state() == "RUNNING":
                gevent.sleep(self.__setpoint_event_poll)
        finally:
            self.__ramping = 0

    def _start_setpoint(self, setpoint, **kwargs):
        """ launches the coroutine doing the setpoint
        """
        self._logger.debug("On Output:_start_setpoint")
        sync_event = gevent.event.Event()

        @task
        def setpoint_task(setpoint):
            sync_event.set()
            if self.__mode == 1:
                self.controller.start_ramp(self, setpoint, **kwargs)
            else:
                self.controller.set(self, setpoint, **kwargs)
            self.__ramping = 1
            self._do_setpoint(setpoint)

        sp_task = setpoint_task(setpoint, wait=False)
        sync_event.wait()
        return sp_task

    def state(self):
        """ returns the the state of a heater """
        self._logger.debug("On Output:state")
        return self.controller.state_output(self)

    def pollramp(self, new_poll=None):
        """
        Setting/reading the polling time (in seconds) in the event loop waiting
        for setpoint being reached (== read value inside the deadband)
        default is 0.02 sec
        """
        if new_poll:
            self.__setpoint_event_poll = new_poll
        else:
            return self.__setpoint_event_poll

    def ramprate(self, new_ramp=None):
        """
        Setting/reading the setpoint ramp rate value

        """
        self._logger.debug("On Output:ramprate: %s " % (new_ramp))
        if new_ramp:
            self.controller.set_ramprate(self, new_ramp)
        else:
            return self.controller.read_ramprate(self)

    def step(self, new_step=None):
        """
        Setting/reading the setpoint step value (for step mode ramping)

        """
        self._logger.debug("On Output:step: %s " % (new_step))
        if new_step:
            self.controller.set_step(self, new_step)
        else:
            return self.controller.read_step(self)

    def dwell(self, new_dwell=None):
        """
        Setting/reading the setpoint dwell value (for step mode ramping)

        """
        self._logger.debug("On Output:setpoint dwell: %s " % (new_dwell))
        if new_dwell:
            self.controller.set_dwell(self, new_dwell)
        else:
            return self.controller.read_dwell(self)

    def _add_custom_method(self, method, name, types_info=(None, None)):
        """ necessary to add custom methods to this class """
        setattr(self, name, method)
        self.__custom_methods_list.append((name, types_info))


@with_custom_members
class Loop(LogMixin):
    """ Implements the access to temperature regulation loop """

    def __init__(self, controller, config):
        """ Constructor """
        self.__controller = controller
        self.__name = config["name"]
        self.__config = config
        self.__input = controller.get_object(config["input"][1:])
        self.__output = controller.get_object(config["output"][1:])
        self._Pval = None
        self._Ival = None
        self._Dval = None

        # useful attribute for a temperature controller writer
        self._attr_dict = {}

        session.get_current().map.register(
            self,
            parents_list=[controller],
            children_list=[self.__input, self.__output],
            tag=f"{self.name}",
        )

    @property
    def controller(self):
        """ returns the temperature controller """
        return self.__controller

    @property
    def name(self):
        """ returns the loop name """
        return self.__name

    @property
    def config(self):
        """ returns the loop config """
        return self.__config

    @property
    def input(self):
        """ returns the loop input object """
        return self.__input

    @property
    def output(self):
        """ returns the loop output object """
        return self.__output

    def set(self, new_setpoint=None, wait=False, **kwargs):
        """ same as a call to the the method set on its output object """
        self._logger.debug(("On Loop: set %s") % new_setpoint)
        return self.__output.set(new_setpoint, wait, **kwargs)

    def ramp(self, new_setpoint=None, wait=False, **kwargs):
        """ same as the call to the method ramp on its output object """
        self._logger.debug(("On Loop: ramp %s") % new_setpoint)
        return self.__output.ramp(new_setpoint, wait, **kwargs)

    def stop(self):
        """ same as the call to the method stop on its output object """
        self._logger.debug("On Loop: stop")
        self.__output.stop()

    def on(self):
        """ Sets the regulation on
            - call to the method 'on' of the controller
        """
        self._logger.debug("On Loop: on")
        self.controller.on(self)

    def off(self):
        """ Sets the regulation off
            - call to the method 'off' of the controller
        """
        self._logger.debug("On Loop: off")
        self.controller.off(self)

    def kp(self, new_kp=None):
        """
        Setting/reading the P value (for PID)

        """
        self._logger.debug("On Loop: kp (PID): ")
        if new_kp:
            self.controller.set_kp(self, new_kp)
        else:
            return self.controller.read_kp(self)

    def ki(self, new_ki=None):
        """
        Setting/reading the I value (for PID)

        """
        self._logger.debug("On Loop: ki (PID): ")
        if new_ki:
            self.controller.set_ki(self, new_ki)
        else:
            return self.controller.read_ki(self)

    def kd(self, new_kd=None):
        """
        Setting/reading the D value (for PID)

        """
        self._logger.debug("On Loop: kd (PID): ")
        if new_kd:
            self.controller.set_kd(self, new_kd)
        else:
            return self.controller.read_kd(self)
