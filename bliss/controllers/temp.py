# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Controller class

Class to be inherited by temperature controllers

Example of .yml file for a mockup temperature controller
with the mandatory fields:

controller:
    class: mockup                   <- mandatory
    host: lid269
    inputs:
        -
            name: thermo_sample     <- mandatory
            channel: A              <- mandatory
    outputs:
        -
            name: heater            <- mandatory
            channel: B              <- mandatory
            low_limit: 10           <- mandatory
            high_limit: 200         <- mandatory
            deadband: 0.1           <- mandatory

    ctrl_loops:
        -
            name: sample_regulation <- mandatory
            input: $thermo_sample   <- mandatory
            output: $heater         <- mandatory
"""

from bliss.common.task_utils import *
import gevent
import gevent.event
import math
from bliss.common import log
from bliss.common.temperature import *
from bliss.common.utils import set_custom_members



class Controller(object):
    """
    Temperature controller base class
    """

    def __init__(self, config, inputs, outputs, loops):
        #log.info("on Controller")
        self.__config = config
        self._objects = dict()
        self._inputs = dict()
        self._outputs = dict()
        self._loops = dict()
        self.__dictramp = dict()

        self.initialize()

        for name, cfg in inputs:
            log.debug("  input name: %s" % (name))
            log.debug("  input config: %s" % (cfg))
            self._objects[name] = Input(self, cfg)
            self._inputs[name] = Input(self, cfg)

            # For custom attributes and commands.
            set_custom_members(self, self._inputs[name])
            set_custom_members(self, self._objects[name])

            self.initialize_input(self._inputs[name])

        for name, cfg in outputs:
            log.debug("  output name: %s" % (name))
            log.debug("  output config: %s" % (cfg))
            self._objects[name] = Output(self, cfg)
            self._outputs[name] = Output(self, cfg)

            self.initialize_output(self._outputs[name])

            # For custom attributes and commands.
            set_custom_members(self, self._outputs[name])
            set_custom_members(self, self._objects[name])

        for name, cfg in loops:
            log.debug("  loops name: %s" % (name))
            log.debug("  loops config: %s" % (cfg))
            self._objects[name] = Loop(self, cfg)
            self._loops [name] = Loop(self, cfg)

            self.initialize_loop(self._loops[name])

            # For custom attributes and commands.
            set_custom_members(self, self._loops[name])
            set_custom_members(self, self._objects[name])


    @property
    def config(self):
        """
        returns the config structure
        """
        return self.__config

    @property
    def dictramp(self):
        return self.__dictramp

    def get_object(self, name):
        """
        get object by name

        Args:
           name:  name of an object

        Returns:
           the object
        """
        log.info("Controller:get_object: %s" % (name))
        #it is used by Loop class
        return self._objects.get(name)

    def initialize(self):
        """ 
        Initializes the controller.
        """
        pass

    def initialize_input(self,tinput):
        """
        Initializes an Input class type object
           Raises NotImplementedError if not defined by inheriting class

        Args:
           tinput:  Input class type object          
        """
        log.info("Controller:initialize_input: %s" % (tinput))
        raise NotImplementedError 

    def initialize_output(self,toutput):
        """
        Initializes an Output class type object
           Raises NotImplementedError if not defined by inheriting class

        Args:
           toutput:  Output class type object          
        """
        log.info("Controller:initialize_output: %s" % (toutput))
        raise NotImplementedError 

    def initialize_loop(self,tloop):
        """
        Initializes a Loop class type object
           Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object          
        """
        log.info("Controller:initialize_loop: %s" % (tloop))
        raise NotImplementedError 

    def read_input(self, tinput):
        """
        Reads an Input class type object
           Raises NotImplementedError if not defined by inheriting class

        Args:
           tinput:  Input class type object 

        Returns:
           read value         
        """
        log.info("Controller:read_input: %s" % (tinput))
        raise NotImplementedError

    def read_output(self, toutput):
        """
        Reads an Onput class type object
           Raises NotImplementedError if not defined by inheriting class

        Args:
           toutput:  Output class type object 

        Returns:
           read value         
        """
        log.info("Controller:read_output: %s" % (toutput))
        raise NotImplementedError

    def start_ramp(self, toutput, sp, **kwargs):
        """
        Send the command to start ramping to a setpoint
           Raises NotImplementedError if not defined by inheriting class

        Args:
           toutput:  Output class type object 
           sp:       setpoint
           **kwargs: auxilliary arguments
        """
        log.info("Controller:start_ramp: %s" % (toutput))
        raise NotImplementedError

    def set(self, toutput, sp, **kwargs):
        """
        Send the command to go to a setpoint as quickly as possible
           Raises NotImplementedError if not defined by inheriting class

        Args:
           toutput:  Output class type object 
           sp:       setpoint
           **kwargs: auxilliary arguments
        """
        log.info("Controller:set: %s" % (toutput))
        raise NotImplementedError

    def get_setpoint(self, toutput):
        """
        Return current setpoint
           Raises NotImplementedError if not defined by inheriting class

        Args:
           toutput:  Output class type object 

        Returns:
           setpoint value. Must be None if not setpoint is set
        """
        log.info("Controller:get_setpoint: %s" % (toutput))
        raise NotImplementedError

    def state_input(self,tinput):
        """
        Return a string representing state of an 'inputs' object.
           Raises NotImplementedError if not defined by inheriting class

        Args:
           tinput:  Input class type object

        Returns:
           object state string. This is one of READY/RUNNING/ALARM/FAULT
        """
        log.info("Controller:state_input:" )
        raise NotImplementedError

    def state_output(self,toutput):
        """
        Return a string representing state of an 'outputs' object.
           Raises NotImplementedError if not defined by inheriting class

        Args:
           toutput:  Output class type object

        Returns:
           object state string. This is one of READY/RUNNING/ALARM/FAULT
        """
        log.info("Controller:state_output:" )
        raise NotImplementedError

    def _setpoint_state(self, toutput, deadband):
        """
        Return a string representing the setpoint state of an Output class type object.
        If a setpoint is set (by ramp or by direct setting) on an ouput, the status
        will be RUNNING until it is in the deadband.
        Method called by Output class type object.

        Args:
           toutput:  Output class type object
           deadband: deadband attribute of toutput.
       
        Returns:
           object state string. This is one of READY/RUNNING/ALARM/FAULT

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
        """
        Stops the setpoint
           Raises NotImplementedError if not defined by inheriting class

        Args:
           toutput:  Output class type object
        """
        log.info("Controller:setpoint_stop")
        raise NotImplementedError

    def setpoint_abort(self,toutput):
        """
	Aborts the setpoint (emergency stop)
           Raises NotImplementedError if not defined by inheriting class

        Args:
           toutput:  Output class type object
        """
        log.info("Controller:setpoint_stop")
        raise NotImplementedError

    def on(self,tloop):
        """
        Starts the regulation on the loop
           Raises NotImplementedError if not defined by inheriting class

        Args: 
           tloop:  Loop class type object
        """
        log.info("Controller:on:" )
        raise NotImplementedError

    def off(self,tloop):
        """
        Stops the regulation on the loop
           Raises NotImplementedError if not defined by inheriting class

        Args: 
           tloop:  Loop class type object
        """
        log.info("Controller:on:" )
        raise NotImplementedError

    def Wraw(self, str):
        """
        A string to write to the controller
           Raises NotImplementedError if not defined by inheriting class

        Args:
           str:  the string to write
        """
        log.info("Controller:Wraw:" )
        raise NotImplementedError

    def Rraw(self):
        """
        Reading the controller
           Raises NotImplementedError if not defined by inheriting class

        returns:
           response from the controller
        """
        log.info("Controller:Rraw:" )
        raise NotImplementedError

    def WRraw(self, str):
        """
        Write then Reading the controller
           Raises NotImplementedError if not defined by inheriting class

        Args:
           str:  the string to write
        returns:
           response from the controller
        """
        log.info("Controller:WRraw:" )
        raise NotImplementedError




