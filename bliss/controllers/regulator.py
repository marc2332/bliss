# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Controller class

Class to be inherited by regulation controllers

Example of .yml file for a mockup temperature controller
with the mandatory fields:


    class: mockup
    module: mockup
    host: lid42
    inputs:
        - 
            name: thermo_sample
            channel: A
            unit: deg
        - 
            name: sensor
            channel: B

    outputs: 
        -
            name: heater
            channel: A 
            unit: Volt
            low_limit: 0.0          # <-- minimum device value [unit]
            high_limit: 100.0       # <-- maximum device value [unit]
            ramprate: 0.0           # <-- ramprate to reach the output value [unit/s].

    ctrl_loops:
        -
            name: sample_regulation
            input: $thermo_sample
            output: $heater
            P: 0.5
            I: 0.3
            D: 0.0
            low_limit: 0.0          # <-- low limit of the PID output value. Usaually equal to 0 or -1.
            high_limit: 1.0         # <-- high limit of the PID output value. Usaually equal to 1.
            frequency: 10.0
            deadband: 0.4
            deadband_time: 1.5
            ramprate: 4.0           # <-- ramprate to reach the setpoint value [input_unit/s]


"""

from bliss.common.regulation import Input, Output, Loop
from bliss.common.utils import set_custom_members
from bliss.common.logtools import log_info
from gevent import lock


class Controller:
    """
    Regulation controller base class

    The 'Controller' class should be inherited by controller classes that are linked to an hardware 
    which has internal PID regulation functionnalities and optionally ramping functionnalities (on setpoint or output value) .
    
    If controller hardware does not have ramping capabilities, the Loop objects associated to the controller will automatically use a SoftRamp.

    """

    def __init__(self, config):
        self.__config = config
        self.__name = config.get("name")
        self._objects = {}

        self.__lock = lock.RLock()
        self.__initialized_obj = {}
        self.__hw_controller_initialized = False

    def add_object(self, node_type_name, object_class, cfg):
        """ creates an instance of the object and add it to the controller.  Called by regulation plugin. """

        new_obj = object_class(self, cfg)

        # --- store the new object
        self._objects[new_obj.name] = new_obj

        # --- For custom attributes and commands.
        set_custom_members(self, new_obj, self.init_obj)  # really needed ???????

        return new_obj

    def init_obj(self, obj):
        """ Initialize objects under the controller. Called by @lazy_init. """

        with self.__lock:

            # ========= INIT HW, DEVICE AND CHILD DEVICE IF ANY =======================

            if not self.__hw_controller_initialized:
                self.initialize_controller()
                self.__hw_controller_initialized = True

            if self.__initialized_obj.get(obj):
                return

            if isinstance(obj, Loop):

                self.__initialized_obj[obj] = True

                if not self.__initialized_obj.get(obj.input):
                    self.__initialized_obj[obj.input] = True
                    obj.input.load_base_config()
                    self.initialize_input(obj.input)

                if not self.__initialized_obj.get(obj.output):
                    self.__initialized_obj[obj.output] = True
                    obj.output.load_base_config()
                    self.initialize_output(obj.output)

                obj.load_base_config()
                self.initialize_loop(obj)

            else:
                self.__initialized_obj[obj] = True
                obj.load_base_config()
                if isinstance(obj, Input):
                    self.initialize_input(obj)
                elif isinstance(obj, Output):
                    self.initialize_output(obj)

            # =========  INIT ALL DEVICES ATTACHED TO THE CONTROLLER ==================
            # if self.__hw_controller_initialized:
            #     return
            # else:
            #     self.__hw_controller_initialized = True

            #     self.initialize_controller()
            #     print("============= controller_hw INITIALIZED")

            #     for obj in self._objects.values():

            #         # --- initialize the object
            #         obj.load_base_config()
            #         if isinstance(obj, Input):
            #             self.initialize_input(obj)
            #         elif isinstance(obj, Output):
            #             self.initialize_output(obj)
            #         elif isinstance(obj, Loop):
            #             self.initialize_loop(obj)

            #         print(f"============= {obj.name} INITIALIZED")

    @property
    def name(self):
        return self.__name

    @property
    def config(self):
        """
        returns the config node
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
        log_info(self, "Controller:get_object: %s" % (name))
        return self._objects.get(name)

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

    # ------ init methods ------------------------

    def initialize_controller(self):
        """ 
        Initializes the controller (including hardware).
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

    # ------ get methods ------------------------

    def read_input(self, tinput):
        """
        Reads an Input class type object
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tinput:  Input class type object 

        Returns:
           read value  (in input unit)    
        """
        log_info(self, "Controller:read_input: %s" % (tinput))
        raise NotImplementedError

    def read_output(self, toutput):
        """
        Reads an Output class type object
        Raises NotImplementedError if not defined by inheriting class

        Args:
           toutput:  Output class type object 

        Returns:
           read value (in output unit)         
        """
        log_info(self, "Controller:read_output: %s" % (toutput))
        raise NotImplementedError

    def state_input(self, tinput):
        """
        Return a string representing state of an Input object.
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tinput:  Input class type object

        Returns:
           object state string. This is one of READY/RUNNING/ALARM/FAULT
        """
        log_info(self, "Controller:state_input: %s" % (tinput))
        raise NotImplementedError

    def state_output(self, toutput):
        """
        Return a string representing state of an Output object.
        Raises NotImplementedError if not defined by inheriting class

        Args:
           toutput:  Output class type object

        Returns:
           object state string. This is one of READY/RUNNING/ALARM/FAULT
        """
        log_info(self, "Controller:state_output: %s" % (toutput))
        raise NotImplementedError

    # ------ raw methods ------------------------

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
           answer from the controller
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
           answer from the controller
        """
        log_info(self, "Controller:WRraw:")
        raise NotImplementedError

    # ------ PID methods ------------------------

    def set_kp(self, tloop, kp):
        """
        Set the PID P value
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object 
           kp: the kp value
        """
        log_info(self, "Controller:set_kp: %s %s" % (tloop, kp))
        raise NotImplementedError

    def get_kp(self, tloop):
        """
        Get the PID P value
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object 
        
        Returns:
           kp value
        """
        log_info(self, "Controller:get_kp: %s" % (tloop))
        raise NotImplementedError

    def set_ki(self, tloop, ki):
        """
        Set the PID I value
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object 
           ki: the ki value
        """
        log_info(self, "Controller:set_ki: %s %s" % (tloop, ki))
        raise NotImplementedError

    def get_ki(self, tloop):
        """
        Get the PID I value
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object 
        
        Returns:
           ki value
        """
        log_info(self, "Controller:get_ki: %s" % (tloop))
        raise NotImplementedError

    def set_kd(self, tloop, kd):
        """
        Set the PID D value
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object 
           kd: the kd value
        """
        log_info(self, "Controller:set_kd: %s %s" % (tloop, kd))
        raise NotImplementedError

    def get_kd(self, tloop):
        """
        Reads the PID D value
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Output class type object 
        
        Returns:
           kd value
        """
        log_info(self, "Controller:get_kd: %s" % (tloop))
        raise NotImplementedError

    def start_regulation(self, tloop):
        """
        Starts the regulation process.
        It must NOT start the ramp, use 'start_ramp' to do so.
        Raises NotImplementedError if not defined by inheriting class

        Args: 
           tloop:  Loop class type object
        """
        log_info(self, "Controller:start_regulation: %s" % (tloop))
        raise NotImplementedError

    def stop_regulation(self, tloop):
        """
        Stops the regulation process.
        It must NOT stop the ramp, use 'stop_ramp' to do so.
        Raises NotImplementedError if not defined by inheriting class

        Args: 
           tloop:  Loop class type object
        """
        log_info(self, "Controller:stop_regulation: %s" % (tloop))
        raise NotImplementedError

    # ------ setpoint methods ------------------------

    def set_setpoint(self, tloop, sp, **kwargs):
        """
        Set the current setpoint (target value).
        It must NOT start the PID process, use 'start_regulation' to do so.
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object
           sp:     setpoint (in tloop.input unit)
           **kwargs: auxilliary arguments
        """
        log_info(self, "Controller:set_setpoint: %s %s" % (tloop, sp))
        raise NotImplementedError

    def get_setpoint(self, tloop):
        """
        Get the current setpoint (target value)
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object

        Returns:
           (float) setpoint value (in tloop.input unit).
        """
        log_info(self, "Controller:get_setpoint: %s" % (tloop))
        raise NotImplementedError

    # ------ setpoint ramping methods ------------------------

    def start_ramp(self, tloop, sp, **kwargs):
        """
        Start ramping to a setpoint
        It must NOT start the PID process, use 'start_regulation' to do so.
        Raises NotImplementedError if not defined by inheriting class

        Replace 'Raises NotImplementedError' by 'pass' if the controller has ramping but doesn't have a method to explicitly starts the ramping.
        Else if this function returns 'NotImplementedError', then the Loop 'tloop' will use a SoftRamp instead.

        Args:
           tloop:  Loop class type object
           sp:       setpoint (in tloop.input unit)
           **kwargs: auxilliary arguments
        """
        log_info(self, "Controller:start_ramp: %s %s" % (tloop, sp))
        raise NotImplementedError

    def stop_ramp(self, tloop):
        """
        Stop the current ramping to a setpoint
        It must NOT stop the PID process, use 'stop_regulation' to do so.
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object
        """
        log_info(self, "Controller:stop_ramp: %s" % (tloop))
        raise NotImplementedError

    def is_ramping(self, tloop):
        """
        Get the ramping status.
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object

        Returns:
           (bool) True if ramping, else False.
        """
        log_info(self, "Controller:is_ramping: %s" % (tloop))
        raise NotImplementedError

    def set_ramprate(self, tloop, rate):
        """
        Set the ramp rate
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object
           rate:   ramp rate (in input unit per second)
        """
        log_info(self, "Controller:set_ramprate: %s %s" % (tloop, rate))
        raise NotImplementedError

    def get_ramprate(self, tloop):
        """
        Get the ramp rate
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object
        
        Returns:
           ramp rate (in input unit per second)
        """
        log_info(self, "Controller:get_ramprate: %s" % (tloop))
        raise NotImplementedError

    def set_dwell(self, tloop, dwell):
        """
        Set the dwell value (for ramp stepping mode)
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object
           dwell
       """
        log_info(self, "Controller:set_dwell: %s %s" % (tloop, dwell))
        raise NotImplementedError

    def get_dwell(self, tloop):
        """
        Get the dwell value (for ramp stepping mode)
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object
        
        Returns:
           dwell value
        """
        log_info(self, "Controller:get_dwell: %s" % (tloop))
        raise NotImplementedError

    def set_step(self, tloop, step):
        """
        Set the step value (for ramp stepping mode)
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object 
           step
       """
        log_info(self, "Controller:set_step: %s %s" % (tloop, step))
        raise NotImplementedError

    def get_step(self, tloop):
        """
        Get the dwell value (for ramp stepping mode)
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object 
        
        Returns:
           step value
        """
        log_info(self, "Controller:get_step: %s" % (tloop))
        raise NotImplementedError

    # ------ others ------------------------------

    def _f(self):
        pass

    def set_in_safe_mode(self, toutput):
        """
        Set the output in a safe mode (like stop heating)
        Raises NotImplementedError if not defined by inheriting class

        Args:
           toutput:  Output class type object 
        """
        log_info(self, "Controller:set_in_safe_mode: %s" % (toutput))
        raise NotImplementedError

    # ------ soft regulation only ??? ------------------------

    def get_sampling_frequency(self, tloop):
        """
        Get the sampling frequency (PID)
        Raises NotImplementedError if not defined by inheriting class

        Args: 
           tloop:  Loop class type object
        """
        log_info(self, "Controller:get_sampling_frequency: %s" % (tloop))
        raise NotImplementedError

    def set_sampling_frequency(self, tloop, value):
        """
        Set the sampling frequency (PID)
        Raises NotImplementedError if not defined by inheriting class

        Args: 
           tloop: Loop class type object
           value: the sampling frequency [Hz] 
        """
        log_info(self, "Controller:set_sampling_frequency: %s %s" % (tloop, value))
        raise NotImplementedError

    def get_pid_range(self, tloop):
        """
        Get the PID range (PID output value limits)
        """
        log_info(self, "Controller:get_pid_range: %s" % (tloop))
        raise NotImplementedError

    def set_pid_range(self, tloop, pid_range):
        """
        Set the PID range (PID output value limits)
        """
        log_info(self, "Controller:set_pid_range: %s %s" % (tloop, pid_range))
        raise NotImplementedError

    def set_output_value(self, toutput, value):
        """
        Set the value on the Output device.
        Raises NotImplementedError if not defined by inheriting class

        Args:
           toutput: Output class type object 
           value: value for the output device (in output unit)      
        """
        log_info(self, "Controller:set_output_value: %s %s" % (toutput, value))
        raise NotImplementedError

    def start_output_ramp(self, toutput, value, **kwargs):  # required by Output obj
        """
        Start ramping on the output
        Raises NotImplementedError if not defined by inheriting class

        Replace 'Raises NotImplementedError' by 'pass' if the controller has output ramping but doesn't have a method to explicitly starts the output ramping.
        Else if this function returns 'NotImplementedError', then the output 'toutput' will use a SoftRamp instead.

        Args:
           toutput:  Output class type object 
           value:    target value for the output ( in output unit )
           **kwargs: auxilliary arguments
        """
        log_info(self, "Controller:start_output_ramp: %s %s" % (toutput, value))
        raise NotImplementedError

    def stop_output_ramp(self, toutput):
        """
        Stop the current ramping on the output
        Raises NotImplementedError if not defined by inheriting class

        Args:
           toutput:  Output class type object 
        """
        log_info(self, "Controller:stop_output_ramp: %s" % (toutput))
        raise NotImplementedError

    def is_output_ramping(self, toutput):
        """
        Get the output ramping status.
        Raises NotImplementedError if not defined by inheriting class

        Args:
           toutput:  Output class type object

        Returns:
           (bool) True if ramping, else False.
        """
        log_info(self, "Controller:is_output_ramping: %s" % (toutput))
        raise NotImplementedError

    def set_output_ramprate(self, toutput, rate):  # required by Output obj
        """
        Set the output ramp rate
        Raises NotImplementedError if not defined by inheriting class

        Args:
           toutput:  Output class type object 
           rate:     ramp rate (in output unit per second)
        """
        log_info(self, "Controller:set_output_ramprate: %s %s" % (toutput, rate))
        raise NotImplementedError

    def get_output_ramprate(self, toutput):  # required by Output obj
        """
        Get the output ramp rate
        Raises NotImplementedError if not defined by inheriting class

        Args:
           toutput:  Output class type object 
        
        Returns:
           ramp rate (in output unit per second)
        """
        log_info(self, "Controller:get_output_ramprate: %s" % (toutput))
        raise NotImplementedError
