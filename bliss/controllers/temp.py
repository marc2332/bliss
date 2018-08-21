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
    outputs:
        -
            name: heater            <- mandatory
            low_limit: 10           <- recommended (default: None)
            high_limit: 200         <- recommended (default: None)
            deadband: 0.1           <- recommended (default: None)

    ctrl_loops:
        -
            name: sample_regulation <- mandatory
            input: $thermo_sample   <- mandatory
            output: $heater         <- mandatory
"""

from bliss.common import log
from bliss.common.temperature import *
from bliss.common.utils import set_custom_members


class Controller(object):
    """
    Temperature controller base class
    """

    def __init__(self, config, inputs, outputs, loops):
        # log.info("on Controller")
        self.__config = config
        self._objects = dict()
        self._inputs = dict()
        self._outputs = dict()
        self._loops = dict()

        self.initialize()

        for name, cfg in inputs:
            log.debug("  input name: %s" % (name))
            log.debug("  input config: %s" % (cfg))
            self._objects[name] = Input(self, cfg)
            self._inputs[name] = Input(self, cfg)

            # For custom attributes and commands.
            set_custom_members(self, self._inputs[name])
            set_custom_members(self, self._objects[name])

            # input object is got from call of get_object
            # and not as self._objects[name]
            self.initialize_input(self.get_object(name))

        for name, cfg in outputs:
            log.debug("  output name: %s" % (name))
            log.debug("  output config: %s" % (cfg))
            self._objects[name] = Output(self, cfg)
            self._outputs[name] = Output(self, cfg)

            # output object is got from call of get_object
            # and not as self._objects[name]
            self.initialize_output(self.get_object(name))

            # For custom attributes and commands.
            set_custom_members(self, self._outputs[name])
            set_custom_members(self, self._objects[name])

        for name, cfg in loops:
            log.debug("  loops name: %s" % (name))
            log.debug("  loops config: %s" % (cfg))
            self._objects[name] = Loop(self, cfg)
            self._loops[name] = Loop(self, cfg)

            # Loop object is got from call of get_object
            # and not as self._objects[name]
            self.initialize_loop(self.get_object(name))

            # For custom attributes and commands.
            set_custom_members(self, self._loops[name])
            set_custom_members(self, self._objects[name])

    @property
    def config(self):
        """
        returns the config structure
        """
        return self.__config

    def get_object(self, name):
        """
        get object by name

        Args:
           name:  name of an object

        Returns:
           the object
        """
        log.info("Controller:get_object: %s" % (name))
        # it is used by Loop class
        return self._objects.get(name)

    def initialize(self):
        """ 
        Initializes the controller.
        """
        pass

    def initialize_input(self, tinput):
        """
        Initializes an Input class type object

        Args:
           tinput:  Input class type object          
        """
        pass

    def initialize_output(self, toutput):
        """
        Initializes an Output class type object

        Args:
           toutput:  Output class type object          
        """
        pass

    def initialize_loop(self, tloop):
        """
        Initializes a Loop class type object

        Args:
           tloop:  Loop class type object          
        """
        pass

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

    def set_ramprate(self, toutput, rate):
        """
        Sets the ramp rate
           Raises NotImplementedError if not defined by inheriting class

        Args:
           toutput:  Output class type object 
           rate:     ramp rate
       """
        log.info("Controller:set_ramprate: %s" % (toutput))
        raise NotImplementedError

    def read_ramprate(self, toutput):
        """
        Reads the ramp rate
           Raises NotImplementedError if not defined by inheriting class

        Args:
           toutput:  Output class type object 
        
        Returns:
           ramp rate
        """
        log.info("Controller:read_ramprate: %s" % (toutput))
        raise NotImplementedError

    def set_dwell(self, toutput, dwell):
        """
        Sets the dwell value (for ramp stepping mode)
           Raises NotImplementedError if not defined by inheriting class

        Args:
           toutput:  Output class type object 
           dwell
       """
        log.info("Controller:set_dwell: %s" % (toutput))
        raise NotImplementedError

    def read_dwell(self, toutput):
        """
        Reads the dwell value (for ramp stepping mode)
           Raises NotImplementedError if not defined by inheriting class

        Args:
           toutput:  Output class type object 
        
        Returns:
           dwell value
        """
        log.info("Controller:read_dwell: %s" % (toutput))
        raise NotImplementedError

    def set_step(self, toutput, step):
        """
        Sets the step value (for ramp stepping mode)
           Raises NotImplementedError if not defined by inheriting class

        Args:
           toutput:  Output class type object 
           step
       """
        log.info("Controller:set_step: %s" % (toutput))
        raise NotImplementedError

    def read_step(self, toutput):
        """
        Reads the dwell value (for ramp stepping mode)
           Raises NotImplementedError if not defined by inheriting class

        Args:
           toutput:  Output class type object 
        
        Returns:
           step value
        """
        log.info("Controller:read_step: %s" % (toutput))
        raise NotImplementedError

    def set_kp(self, tloop, kp):
        """
        Sets the PID P value
           Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object 
           kp
       """
        log.info("Controller:set_kp: %s" % (toutput))
        raise NotImplementedError

    def read_kp(self, tloop):
        """
        Reads the PID P value
           Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object 
        
        Returns:
           kp value
        """
        log.info("Controller:read_kp: %s" % (toutput))
        raise NotImplementedError

    def set_ki(self, tloop, ki):
        """
        Sets the PID I value
           Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object 
           ki
       """
        log.info("Controller:set_ki: %s" % (toutput))
        raise NotImplementedError

    def read_ki(self, tloop):
        """
        Reads the PID I value
           Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object 
        
        Returns:
           ki value
        """
        log.info("Controller:read_ki: %s" % (toutput))
        raise NotImplementedError

    def set_kd(self, tloop, kd):
        """
        Sets the PID D value
           Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object 
           kd
       """
        log.info("Controller:set_kd: %s" % (toutput))
        raise NotImplementedError

    def read_kd(self, tloop):
        """
        Reads the PID D value
           Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Output class type object 
        
        Returns:
           kd value
        """
        log.info("Controller:read_kd: %s" % (toutput))
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
           (float) setpoint value. Must be None if not setpoint is set
        """
        log.info("Controller:get_setpoint: %s" % (toutput))
        raise NotImplementedError

    def state_input(self, tinput):
        """
        Return a string representing state of an 'inputs' object.
           Raises NotImplementedError if not defined by inheriting class

        Args:
           tinput:  Input class type object

        Returns:
           object state string. This is one of READY/RUNNING/ALARM/FAULT
        """
        log.info("Controller:state_input:")
        raise NotImplementedError

    def state_output(self, toutput):
        """
        Return a string representing state of an 'outputs' object.
           Raises NotImplementedError if not defined by inheriting class

        Args:
           toutput:  Output class type object

        Returns:
           object state string. This is one of READY/RUNNING/ALARM/FAULT
        """
        log.info("Controller:state_output:")
        raise NotImplementedError

    def _f(self):
        pass

    def setpoint_stop(self, toutput):
        """
        Stops the setpoint
           Raises NotImplementedError if not defined by inheriting class

        Args:
           toutput:  Output class type object
        """
        log.info("Controller:setpoint_stop")
        raise NotImplementedError

    def setpoint_abort(self, toutput):
        """
	Aborts the setpoint (emergency stop)
           Raises NotImplementedError if not defined by inheriting class

        Args:
           toutput:  Output class type object
        """
        log.info("Controller:setpoint_stop")
        raise NotImplementedError

    def on(self, tloop):
        """
        Starts the regulation on the loop
           Raises NotImplementedError if not defined by inheriting class

        Args: 
           tloop:  Loop class type object
        """
        log.info("Controller:on:")
        raise NotImplementedError

    def off(self, tloop):
        """
        Stops the regulation on the loop
           Raises NotImplementedError if not defined by inheriting class

        Args: 
           tloop:  Loop class type object
        """
        log.info("Controller:on:")
        raise NotImplementedError

    def Wraw(self, str):
        """
        A string to write to the controller
           Raises NotImplementedError if not defined by inheriting class

        Args:
           str:  the string to write
        """
        log.info("Controller:Wraw:")
        raise NotImplementedError

    def Rraw(self):
        """
        Reading the controller
           Raises NotImplementedError if not defined by inheriting class

        returns:
           response from the controller
        """
        log.info("Controller:Rraw:")
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
        log.info("Controller:WRraw:")
        raise NotImplementedError
