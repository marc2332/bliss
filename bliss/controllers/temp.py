# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common.task_utils import *
import gevent
import gevent.event
import math
from bliss.common import log
from bliss.common.temperature import *
from bliss.common.utils import set_custom_members



class Controller(object):
    def __init__(self, config, inputs, outputs, loops):
        #log.info("on Controller")
        self.__config = config
        self._objects = dict()
        self._inputs = dict()
        self._outputs = dict()
        self._loops = dict()
        self.__dictramp = dict()

        for name, cfg in inputs:
            log.debug("  input name: %s" % (name))
            log.debug("  input config: %s" % (cfg))
            self._objects[name] = Input(self, cfg)
            self._inputs[name] = Input(self, cfg)

            # For custom attributes and commands.
            set_custom_members(self, self._inputs[name])
            set_custom_members(self, self._objects[name])

        for name, cfg in outputs:
            log.debug("  output name: %s" % (name))
            log.debug("  output config: %s" % (cfg))
            self._objects[name] = Output(self, cfg)
            self._outputs[name] = Output(self, cfg)
            self.__dictramp.setdefault(self._outputs[name].channel,{"ramp":None, "step":None, "dwell":None})

            # For custom attributes and commands.
            set_custom_members(self, self._outputs[name])
            set_custom_members(self, self._objects[name])

        for name, cfg in loops:
            log.debug("  loops name: %s" % (name))
            log.debug("  loops config: %s" % (cfg))
            self._objects[name] = Loop(self, cfg)
            self._loops [name] = Loop(self, cfg)

            # For custom attributes and commands.
            set_custom_members(self, self._loops[name])
            set_custom_members(self, self._objects[name])


    @property
    def config(self):
        return self.__config

    @property
    def dictramp(self):
        return self.__dictramp

    def get_object(self, name):
        log.info("Controller:get_object: %s" % (name))
        #it is used by Loop class
        return self._objects.get(name)

    def _set_rampval(self,toutput,ramp):
        """Sets the setpoint ramp value

        """
        log.info("Controller:set_rampval: %s " % (toutput))
        #print toutput.channel
        #print self.__dictramp
        self.__dictramp[toutput.channel]["ramp"]=ramp
        #print self.__dictramp

    def _get_rampval(self,toutput):
        """Gets the setpoint ramp value

        """
        log.info("Controller:get_rampval: %s " % (toutput))
        #print toutput.channel
        #print self.__dictramp
        return self.__dictramp[toutput.channel]["ramp"]

    def _set_stepval(self,toutput,step):
        """Sets the setpoint step value

        """
        log.info("Controller:set_stepval: %s " % (toutput))
        self.__dictramp[toutput.channel]["step"]=step

    def _get_stepval(self,toutput):
        """Gets the setpoint step value

        """
        log.info("Controller:get_stepval: %s " % (toutput))
        return self.__dictramp[toutput.channel]["step"]

    def _set_dwellval(self,toutput,dwell):
        """Sets the setpoint dwell value

        """
        log.info("Controller:set_dwellval: %s " % (toutput))
        self.__dictramp[toutput.channel]["dwell"]=dwell

    def _get_dwellval(self,toutput):
        """Gets the setpoint dwell value

        """
        log.info("Controller:get_dwellval: %s " % (toutput))
        return self.__dictramp[toutput.channel]["dwell"]

    def read_input(self, tinput):
        log.info("Controller:read_input: %s" % (tinput))
        raise NotImplementedError

    def read_output(self, toutput):
        log.info("Controller:read_output: %s" % (toutput))
        raise NotImplementedError

    def start_ramp(self, toutput, sp, **kwargs):
        """Send the command to start ramping to a setpoint"""
        log.info("Controller:start_ramp: %s" % (toutput))
        raise NotImplementedError

    def set(self, toutput, sp, **kwargs):
        """Send the command to set a setpoint as quickly as possible"""
        log.info("Controller:set: %s" % (toutput))
        raise NotImplementedError

    def get_setpoint(self, toutput):
        """Return current setpoint

        Returned value is None if not setpoint is set
        """
        log.info("Controller:get_setpoint: %s" % (toutput))
        raise NotImplementedError

    def state_input(self,tinput):
        """Return a string representing state of an 'inputs' object.

        One of:
        - READY
        - RUNNING
        - ALARM
        - FAULT
        """
        log.info("Controller:state_input:" )
        raise NotImplementedError

    def state_output(self,toutput):
        """Return a string representing state of an 'outputs' object.

        One of:
        - READY
        - RUNNING
        - ALARM
        - FAULT
        """
        log.info("Controller:state_output:" )
        raise NotImplementedError

    def _setpoint_state(self, toutput, deadband):
        """Return a string representing the setpoint state

        One of:
        - READY
        - RUNNING
        - ALARM
        - FAULT

           It can be used as it is or overloaded with custom code
        """
        log.info("Controller:setpoint_state: %s" % (toutput))
        mysp = self.get_setpoint(toutput)
        if (mysp == None) :
            return "READY"
        if math.fabs(self.read_output(toutput) - mysp) <= deadband:
            return "READY"
        else:
            return "RUNNING"

    def setpoint_stop(self,toutput):
        """Stops the setpoint

        """
        log.info("Controller:setpoint_stop")
        raise NotImplementedError

    def setpoint_abort(self,toutput):
        """Aborts the setpoint

        """
        log.info("Controller:setpoint_stop")
        raise NotImplementedError

    def on(self,tloop):
        """Starts the regulation on the loop
        """
        log.info("Controller:on:" )
        raise NotImplementedError

    def off(self,tloop):
        """Stops the regulation on the loop
        """
        log.info("Controller:on:" )
        raise NotImplementedError

    def Wraw(self, str):
        """A string to write to the controller
        """
        log.info("Controller:Wraw:" )
        raise NotImplementedError

    def Rraw(self):
        """Reading the controller
        """
        log.info("Controller:Rraw:" )
        raise NotImplementedError

    def WRraw(self):
        """Write then Reading the controller
        """
        log.info("Controller:WRraw:" )
        raise NotImplementedError




