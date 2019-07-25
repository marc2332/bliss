# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
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
import itertools
from gevent import lock
from bliss.common.temperature import Input, Output, Loop
from bliss.common.utils import set_custom_members
from bliss.common.logtools import *
from bliss.config.channels import Cache


class Controller:
    """
    Temperature controller base class
    """

    def __init__(self, config, inputs, outputs, loops):
        self.__config = config
        self.__name = config.get("name")
        self.__initialized_hw = Cache(self, "initialized", default_value=False)
        self._objects = {}
        self.__initialized_hw_obj = {}
        self.__initialized_obj = {}
        self.__lock = lock.RLock()

        for name, klass, cfg in itertools.chain(inputs, outputs, loops):
            log_debug(self, f"  {klass.__name__} name: {name}")
            log_debug(self, f"  {klass.__name__} config: {cfg}")
            new_obj = klass(self, cfg)

            self._objects[name] = new_obj

            if new_obj.controller is self:
                set_custom_members(self, new_obj, self._initialize_obj)

    @property
    def name(self):
        return self.__name

    @property
    def config(self):
        """
        returns the config structure
        """
        return self.__config

    @property
    def inputs(self):
        return self._object_filter(Input)

    @property
    def outputs(self):
        return self._object_filter(Output)

    @property
    def loops(self):
        return self._object_filter(Loop)

    def _object_filter(self, class_type):
        return {
            name: obj
            for name, obj in self._objects.items()
            if isinstance(obj, class_type)
        }

    def get_object(self, name):
        """
        get object by name

        Args:
           name:  name of an object

        Returns:
           the object
        """
        log_info(self, "Controller:get_object: %s" % (name))
        # it is used by Loop class
        return self._objects.get(name)

    def _init(self):
        self.initialize()

        for name, obj in self._objects.items():
            if obj.controller is not self:
                continue
            obj_initialized = Cache(obj, "initialized", default_value=0)
            self.__initialized_hw_obj[obj] = obj_initialized
            self.__initialized_obj[obj] = False

    def _initialize_obj(self, obj, *args, **kwargs):
        with self.__lock:
            if self.__initialized_obj[obj]:
                return

            if not self.__initialized_hw.value:
                self.initialize_hardware()
                self.__initialized_hw.value = True

            if isinstance(obj, Input):
                self.initialize_input(obj)
                hw_init_func = self.initialize_input_hardware
            elif isinstance(obj, Output):
                self.initialize_output(obj)
                hw_init_func = self.initialize_output_hardware
            elif isinstance(obj, Loop):
                self.initialize_loop(obj)
                hw_init_func = self.initialize_loop_hardware

            obj_initialized = self.__initialized_hw_obj[obj]
            if not obj_initialized.value:
                hw_init_func(obj)
                obj_initialized.value = 1

            self.__initialized_obj[obj] = True

    def initialize_hardware(self):
        """
        Initializes the controller hardware
        (only once, by the first client)
        """
        pass

    def initialize(self):
        """
        Initializes the controller.
        """
        pass

    def initialize_input_hardware(self, tinput):
        pass

    def initialize_input(self, tinput):
        """
        Initializes an Input class type object

        Args:
           tinput:  Input class type object
        """
        pass

    def initialize_output_hardware(self, toutput):
        pass

    def initialize_output(self, toutput):
        """
        Initializes an Output class type object

        Args:
           toutput:  Output class type object
        """
        pass

    def initialize_loop_hardware(self, tloop):
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
        log_info(self, "Controller:read_input: %s" % (tinput))
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
        log_info(self, "Controller:read_output: %s" % (toutput))
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
        log_info(self, "Controller:start_ramp: %s" % (toutput))
        raise NotImplementedError

    def set_ramprate(self, toutput, rate):
        """
        Sets the ramp rate
           Raises NotImplementedError if not defined by inheriting class

        Args:
           toutput:  Output class type object
           rate:     ramp rate
       """
        log_info(self, "Controller:set_ramprate: %s" % (toutput))
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
        log_info(self, "Controller:read_ramprate: %s" % (toutput))
        raise NotImplementedError

    def set_dwell(self, toutput, dwell):
        """
        Sets the dwell value (for ramp stepping mode)
           Raises NotImplementedError if not defined by inheriting class

        Args:
           toutput:  Output class type object
           dwell
       """
        log_info(self, "Controller:set_dwell: %s" % (toutput))
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
        log_info(self, "Controller:read_dwell: %s" % (toutput))
        raise NotImplementedError

    def set_step(self, toutput, step):
        """
        Sets the step value (for ramp stepping mode)
           Raises NotImplementedError if not defined by inheriting class

        Args:
           toutput:  Output class type object
           step
       """
        log_info(self, "Controller:set_step: %s" % (toutput))
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
        log_info(self, "Controller:read_step: %s" % (toutput))
        raise NotImplementedError

    def set_kp(self, tloop, kp):
        """
        Sets the PID P value
           Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object
           kp
       """
        log_info(self, "Controller:set_kp: %s" % (tloop))
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
        log_info(self, "Controller:read_kp: %s" % (tloop))
        raise NotImplementedError

    def set_ki(self, tloop, ki):
        """
        Sets the PID I value
           Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object
           ki
       """
        log_info(self, "Controller:set_ki: %s" % (tloop))
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
        log_info(self, "Controller:read_ki: %s" % (tloop))
        raise NotImplementedError

    def set_kd(self, tloop, kd):
        """
        Sets the PID D value
           Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object
           kd
       """
        log_info(self, "Controller:set_kd: %s" % (tloop))
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
        log_info(self, "Controller:read_kd: %s" % (toutput))
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
        log_info(self, "Controller:set: %s" % (toutput))
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
        log_info(self, "Controller:get_setpoint: %s" % (toutput))
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
        log_info(self, "Controller:state_input:")
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
        log_info(self, "Controller:state_output:")
        raise NotImplementedError

    def setpoint_stop(self, toutput):
        """
        Stops the setpoint task
           Raises NotImplementedError if not defined by inheriting class

        Args:
           toutput:  Output class type object
        """
        log_info(self, "Controller:setpoint_stop")
        raise NotImplementedError

    def setpoint_abort(self, toutput):
        """
	Aborts the setpoint task (emergency stop)
           Raises NotImplementedError if not defined by inheriting class

        Args:
           toutput:  Output class type object
        """
        log_info(self, "Controller:setpoint_stop")
        raise NotImplementedError

    def on(self, tloop):
        """
        Starts the regulation on the loop
           Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object
        """
        log_info(self, "Controller:on:")
        raise NotImplementedError

    def off(self, tloop):
        """
        Stops the regulation on the loop
           Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object
        """
        log_info(self, "Controller:on:")
        raise NotImplementedError

    def Wraw(self, str):
        """
        A string to write to the controller
           Raises NotImplementedError if not defined by inheriting class

        Args:
           str:  the string to write
        """
        log_info(self, "Controller:Wraw:")
        raise NotImplementedError

    def Rraw(self):
        """
        Reading the controller
           Raises NotImplementedError if not defined by inheriting class

        returns:
           response from the controller
        """
        log_info(self, "Controller:Rraw:")
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
        log_info(self, "Controller:WRraw:")
        raise NotImplementedError
