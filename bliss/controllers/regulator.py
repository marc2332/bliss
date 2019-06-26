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

controller:
    class: mockup
    module: mockup
    host: lid42
    inputs:
        - 
            name: thermo_sample
            channel: A
            unit: deg
            tango_server: temp1
        - 
            name: sensor
            channel: B
            tango_server: temp1
        
        - 
            name: regdiode
            device: $diode
            unit: Volt
            tango_server: temp1

    outputs: 
        -
            name: heater
            channel: A 
            unit: Volt
            low_limit: 0.0          # <== device value [unit] corresponding to the min power.
            high_limit: 100.0       # <== device value [unit] corresponding to the max power.
            ramprate: 0.0           # <== ramprate to reach the output value [unit/s].
            equilibrium_value: 50.  # <== special parameter for mockup output: value for output device that compensate the energy loss of the system [unit].
            heating_rate: 10.0      # <== special parameter for mockup output: heating capability of device at 100% of its power [deg/s].
            #lookuptable: 
            #    0 : 0
            #    .1 : 10
            #    .9 : 100
            #    1 : 1000
            tango_server: temp1
        
        -
            name: heater2
            channel: B 
            unit: Volt
            low_limit: 10.0          # <== device value [unit] corresponding to the min power.
            high_limit: 150.0       # <== device value [unit] corresponding to the max power.
            ramprate: 10.0           # <== ramprate to reach the output value [unit/s].
            equilibrium_value: 80.  # <== special parameter for mockup output: value for output device that compensate the energy loss of the system [unit].
            heating_rate: 20.0      # <== special parameter for mockup output: heating capability of device at 100% of its power [deg/s].
            tango_server: temp1

    ctrl_loops:
        -
            name: sample_regulation
            input: $thermo_sample
            output: $heater
            P: 0.5
            I: 0.3
            D: 0.0
            low_limit: 0.0          # <== low limit of the PID output value (min power). Usaually equal to 0 or -1.
            high_limit: 1.0          # <== high limit of the PID output value (max power). Usaually equal to 1.
            frequency: 10.0
            deadband: 0.4
            deadband_time: 1.5
            ramprate: 4.0           # <== ramprate to reach the setpoint value [input_unit/s]
            tango_server: temp1
        
        -
            name: sample_regulation2
            input: $sensor
            output: $heater2
            P: 0.7
            I: 0.4
            D: 0.01
            low_limit: -1.0          # <== low limit of the PID output value (min power). Usaually equal to 0 or -1.
            high_limit: 1.0          # <== high limit of the PID output value (max power). Usaually equal to 1.
            frequency: 20.0
            deadband: 0.5
            deadband_time: 2.0
            ramprate: 5.0           # <== ramprate to reach the setpoint value [input_unit/s]
            tango_server: temp1


"""
import itertools

from bliss.common.regulation import Input, Output, Loop, ExternalInput, ExternalOutput
from bliss.common.utils import set_custom_members
from bliss.common import session
from bliss.common.logtools import log_debug, log_info

from simple_pid import PID
import gevent
import time

from bliss.common.plot import plot, draw_manager

# state_enum = [READY/RUNNING/ALARM/FAULT]


class Controller:
    """
    Regulation controller base class

    The 'Controller' class should be inherited by controller classes that are linked to an hardware 
    which have internal PID regulation functionnalities and ramping functionnalities (on setpoint or output power value) .
    
    If you want to use functionnalities of the hardware for the ramping, you have to implement the ramping methods in your controller child class. 
    If the ramping methods are not implemented in the child class, Loops associated to the controller will automatically use soft ramping methods 
    when setting the setpoint value or the output power (see 'Ramp' and 'OutputRamp' objects).
    The ramping methods are:
        - start_ramp / stop_ramp
        - set_ramprate / get_ramprate
        - start_output_ramp / stop_output_ramp
        - set_output_ramprate / get_output_ramprate

    """

    def __init__(self, config):
        self.__config = config
        self.__name = config.get("name")
        self._objects = {}

    def create_object(self, node_type_name, object_class, cfg):

        # --- standard input or output or loop
        if "channel" in cfg.keys() or "input" in cfg.keys():
            new_obj = object_class(self, cfg)

            # handle loops with custom input/output
            if node_type_name == "LOOP":
                if not isinstance(cfg["input"], Input):
                    raise TypeError(
                        f"the object {cfg['input'].__class__} associated to the '{cfg['name']}' Loop is not of the type Input !"
                    )

                if not isinstance(cfg["output"], Output):
                    raise TypeError(
                        f"the object {cfg['output'].__class__} associated to the '{cfg['name']}' Loop is not of the type Output !"
                    )

                if cfg["input"].controller is None:
                    cfg["input"]._controller = self
                    self.register_object(cfg["input"])

                if cfg["output"].controller is None:
                    cfg["output"]._controller = self
                    self.register_object(cfg["output"])

        # --- external input or output
        elif "device" in cfg.keys():
            if node_type_name == "INPUT":
                new_obj = ExternalInput(self, cfg)

            elif node_type_name == "OUTPUT":
                new_obj = ExternalOutput(self, cfg)

        self.register_object(new_obj)

        return new_obj

    def register_object(self, new_obj):

        # print(f"=== REGISTER object: {new_obj.name}, {new_obj} ")

        # --- initialize the new object
        if isinstance(new_obj, Input):
            new_obj.load_base_config()
            self.initialize_input(new_obj)
        elif isinstance(new_obj, Output):
            new_obj.load_base_config()
            self.initialize_output(new_obj)
        elif isinstance(new_obj, Loop):
            new_obj.load_base_config()
            self.initialize_loop(new_obj)
        # else:
        #    print(f"=== WARNING: unknown object: {new_obj.name}, {type(new_obj)}")

        # --- store the new object
        self._objects[new_obj.name] = new_obj

        # --- For custom attributes and commands.
        set_custom_members(self, new_obj)

    @property
    def name(self):
        return self.__name

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
        log_info(self, "Controller:get_object: %s" % (name))
        # it is used by Loop class
        return self._objects.get(name)

    # ====== init methods =========================

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

    # ====== get methods =========================

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

    # ====== set methods =========================

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

    # ====== raw methods =========================

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

    # ====== PID methods =========================

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
        log_info(self, "Controller:get_pid_range: %s %s" % (tloop))
        raise NotImplementedError

    def set_pid_range(self, tloop, pid_range):
        """
        Set the PID range (PID output value limits)
        """
        log_info(self, "Controller:set_pid_range: %s %s" % (tloop, pid_range))
        raise NotImplementedError

    def start_regulation(self, tloop):
        """
        Starts the regulation process.
        Does NOT start the ramp, use 'start_ramp' to do so.
        Raises NotImplementedError if not defined by inheriting class

        Args: 
           tloop:  Loop class type object
        """
        log_info(self, "Controller:start_regulation: %s" % (tloop))
        raise NotImplementedError

    def stop_regulation(self, tloop):
        """
        Stops the regulation process.
        Does NOT stop the ramp, use 'stop_ramp' to do so.
        Raises NotImplementedError if not defined by inheriting class

        Args: 
           tloop:  Loop class type object
        """
        log_info(self, "Controller:stop_regulation: %s" % (tloop))
        raise NotImplementedError

    # ====== setpoint methods =========================

    def set_setpoint(self, tloop, sp, **kwargs):
        """
        Set the current setpoint (target value).
        Does NOT start the PID process, use 'start_regulation' to do so.
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

    # ====== setpoint ramping methods =========================

    def start_ramp(self, tloop, sp, **kwargs):
        """
        Start ramping to a setpoint
        Does NOT start the PID process, use 'start_regulation' to do so.
        Raises NotImplementedError if not defined by inheriting class

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
        Does NOT stop the PID process, use 'stop_regulation' to do so.
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object
        """
        log_info(self, "Controller:stop_ramp: %s" % (tloop))
        raise NotImplementedError

    def get_working_setpoint(self, tloop):
        """
        Get the current working setpoint (during a ramping process)
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object

        Returns:
           (float) working setpoint value (in tloop.input unit).
        """
        log_info(self, "Controller:get_working_setpoint: %s" % (tloop))
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

    # ====== output ramping methods =========================

    def start_output_ramp(self, toutput, value, **kwargs):
        """
        Start ramping on the output
        Raises NotImplementedError if not defined by inheriting class

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

    def get_output_working_setpoint(self, toutput):
        """
        Get the current working setpoint of the output (during a ramping process)
        Raises NotImplementedError if not defined by inheriting class

        Args:
           toutput:  Output class type object

        Returns:
           (float) Output working setpoint value (in toutput unit).
        """
        log_info(self, "Controller:get_output_working_setpoint: %s" % (toutput))
        raise NotImplementedError

    def output_is_ramping(self, toutput):
        """
        Get the output ramping status.
        Raises NotImplementedError if not defined by inheriting class

        Args:
           toutput:  Output class type object

        Returns:
           (bool) True if ramping, else False.
        """
        log_info(self, "Controller:output_is_ramping: %s" % (toutput))
        raise NotImplementedError

    def set_output_ramprate(self, toutput, rate):
        """
        Set the output ramp rate
        Raises NotImplementedError if not defined by inheriting class

        Args:
           toutput:  Output class type object 
           rate:     ramp rate (in output unit per second)
        """
        log_info(self, "Controller:set_output_ramprate: %s %s" % (toutput, rate))
        raise NotImplementedError

    def get_output_ramprate(self, toutput):
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

    # ====== others ===================================

    def _f(self):
        pass


class SoftController(Controller):
    """
    Software regulation controller base class.
    It implements a PID regulation process based on the 'simple_pid' python module.

    A SoftController should be used when the hardware does not have an internal PID regulation
    or when we want to override the internal PID regulation of the hardware.
    
    If you want to use functionnalities of the hardware for the ramping, you have to implement the ramping methods in your controller child class. 
    If the ramping methods are not implemented in the child class, Loops associated to the controller will automatically use soft ramping methods 
    when setting the setpoint value or the output power (see 'Ramp' and 'OutputRamp' objects).
    The ramping methods are:
        - start_ramp / stop_ramp
        - set_ramprate / get_ramprate
        - set_dwell / get_dwell
        - set_step / get_step
        - start_output_ramp / stop_output_ramp
        - set_output_ramprate / get_output_ramprate

    """

    def __init__(self, config):

        super().__init__(config)

        self.pids = {}
        self.tasks = {}
        self._stop_events = {}

    def create_object(self, node_type_name, object_class, cfg):

        if node_type_name == "LOOP":
            name = cfg["name"]
            self.pids[name] = PID(
                Kp=1.0,
                Ki=0.0,
                Kd=0.0,
                setpoint=0.0,
                sample_time=0.01,
                output_limits=(0.0, 1.0),
                auto_mode=True,
                proportional_on_measurement=False,
            )

            self.tasks[name] = None
            self._stop_events[name] = gevent.event.Event()

        new_obj = super().create_object(node_type_name, object_class, cfg)

        return new_obj

    def __del__(self):
        for se in self._stop_events.values():
            se.set()

    def set_kp(self, tloop, kp):
        """
        Set the PID P value
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object 
           kp
        """
        log_info(self, "Controller:set_kp: %s %s" % (tloop, kp))
        self.pids[tloop.name].Kp = kp

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
        return self.pids[tloop.name].Kp

    def set_ki(self, tloop, ki):
        """
        Set the PID I value
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object 
           ki
        """
        log_info(self, "Controller:set_ki: %s %s" % (tloop, ki))
        self.pids[tloop.name].Ki = ki

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
        return self.pids[tloop.name].Ki

    def set_kd(self, tloop, kd):
        """
        Set the PID D value
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object 
           kd
       """
        log_info(self, "Controller:set_kd: %s %s" % (tloop, kd))
        self.pids[tloop.name].Kd = kd

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
        return self.pids[tloop.name].Kd

    def get_sampling_frequency(self, tloop):
        """
        Get the sampling frequency (PID)
        Raises NotImplementedError if not defined by inheriting class

        Args: 
           tloop:  Loop class type object
        Returns:
           the PID sampling frequency [Hz]
        """
        log_info(self, "Controller:get_sampling_frequency: %s" % (tloop))
        return 1. / self.pids[tloop.name].sample_time

    def set_sampling_frequency(self, tloop, value):
        """
        Set the sampling frequency (PID)
        Raises NotImplementedError if not defined by inheriting class

        Args: 
           tloop: Loop class type object
           value: the PID sampling frequency [Hz]
        """
        log_info(self, "Controller:set_sampling_frequency: %s %s" % (tloop, value))
        self.pids[tloop.name].sample_time = 1. / value

    def get_pid_range(self, tloop):
        """
        Get the PID range (PID output value limits)
        """
        log_info(self, "Controller:get_pid_range: %s" % (tloop))
        return self.pids[tloop.name].output_limits

    def set_pid_range(self, tloop, pid_range):
        """
        Set the PID range (PID output value limits)
        """
        log_info(self, "Controller:set_pid_range: %s %s" % (tloop, pid_range))
        self.pids[tloop.name].output_limits = pid_range[0:2]

    def start_regulation(self, tloop):
        """
        Starts the regulation loop
        Raises NotImplementedError if not defined by inheriting class

        Args: 
           tloop:  Loop class type object
        """
        log_info(self, "Controller:start_regulation: %s" % (tloop))

        if not self.tasks[tloop.name]:
            self.tasks[tloop.name] = gevent.spawn(self._do_regulation, tloop)

    def stop_regulation(self, tloop):
        """
        Stops the regulation loop
        Raises NotImplementedError if not defined by inheriting class

        Args: 
           tloop:  Loop class type object
        """
        log_info(self, "Controller:stop_regulation: %s" % (tloop))
        self._stop_events[tloop.name].set()

    def set_setpoint(self, tloop, sp, **kwargs):
        """
        Set the current setpoint (target value)
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object
           sp:     setpoint (in loop.input unit)
           **kwargs: auxilliary arguments
        """
        log_info(self, "Controller:set_setpoint: %s %s" % (tloop, sp))
        self.pids[tloop.name].setpoint = sp

    def get_setpoint(self, tloop):
        """
        Get the current setpoint (target value)
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object

        Returns:
           (float) setpoint value (in loop.input unit)
        """
        log_info(self, "Controller:get_setpoint: %s" % (tloop))
        return self.pids[tloop.name].setpoint

    def apply_proportional_on_measurement(self, tloop, enable):
        """
        To eliminate overshoot in certain types of systems, 
        the proportional term can be calculated directly on the measurement instead of the error.

        Args:
           tloop:  Loop class type object
           enable: True or False
        """
        log_info(
            self,
            "Controller:apply_proportional_on_measurement: %s %s" % (tloop, enable),
        )
        self.pids[tloop.name].proportional_on_measurement = bool(enable)

    def _do_regulation(self, tloop):

        self._stop_events[tloop.name].clear()

        while not self._stop_events[tloop.name].is_set():

            input_value = tloop.input.read()
            power_value = self.pids[tloop.name](input_value)

            if not tloop.is_in_idleband():
                tloop.output.set_power(power_value)

            # store data history
            outval = tloop.output.get_working_setpoint()
            tloop._store_history_data(input_value, outval, tloop.setpoint)

            gevent.sleep(self.pids[tloop.name].sample_time)


class RegPlot:
    """ Useful tool to plot the regulation (Loop) parameters over time (input_value, setpoint_value, output_value) 
        Based on flint/silx modules

        usage:  plt = RegPlot( myloop )
                plt.start()
                ...
                plt.stop()
    """

    def __init__(self, tloop, dpi=80):

        self.loop = tloop

        self.task = None
        self._stop_event = gevent.event.Event()
        self.sleep_time = 0.1

        # Declare a CurvePlot (see bliss.common.plot)
        self.fig = plot(data=None, name=tloop.name)

        self.fig.set_plot_dpi(dpi)
        self.fig.submit("adjustSize")

    def close(self):
        self.stop()
        # close flint tab
        pass

    def start(self):
        if not self.task:
            self.task = gevent.spawn(self.run)
        # else:
        #    self.stop()
        #    self.task = gevent.spawn(self.run)

    def stop(self):
        self._stop_event.set()
        # self.task.join()
        # self.clear()

    def run(self):

        self._stop_event.clear()

        # t_start = time.time()

        self.fig.submit("setGraphXLabel", "Time (s)")
        self.fig.submit(
            "setGraphYLabel",
            f"Processed value ({self.loop.input.config.get('unit','')})",
        )
        self.fig.submit(
            "setGraphYLabel",
            f"Output ({self.loop.output.config['unit']})",
            axis="right",
        )
        self.fig.submit("setGraphGrid", which=True)

        while not self._stop_event.is_set():

            with draw_manager(self.fig):

                self.fig.add_data(self.loop.history_data["time"], field="time")
                self.fig.add_data(self.loop.history_data["input"], field="Input")
                self.fig.add_data(self.loop.history_data["output"], field="Output")
                self.fig.add_data(self.loop.history_data["setpoint"], field="Setpoint")

                # self.fig.add_data(self.loop.history_data['input2'], field='Input2')
                # self.fig.add_data(self.loop.history_data['output2'], field='Output2')
                # self.fig.add_data(self.loop.history_data['setpoint2'], field='Setpoint2')

                dbp = [
                    x + self.loop.deadband for x in self.loop.history_data["setpoint"]
                ]
                dbm = [
                    x - self.loop.deadband for x in self.loop.history_data["setpoint"]
                ]
                self.fig.add_data(dbp, field="Deadband_high")
                self.fig.add_data(dbm, field="Deadband_low")

                # Update curves plot (refreshes the plot widget)
                # select_data takes all kwargs of the associated plot methode (e.g. silx => addCurve(kwargs) )
                self.fig.select_data(
                    "time", "Setpoint", color="blue", linestyle="-", z=2
                )
                self.fig.select_data("time", "Input", color="red", linestyle="-", z=2)
                self.fig.select_data(
                    "time", "Output", color="green", linestyle="-", yaxis="right", z=2
                )
                self.fig.select_data(
                    "time", "Deadband_high", color="blue", linestyle="--", z=2
                )
                self.fig.select_data(
                    "time", "Deadband_low", color="blue", linestyle="--", z=2
                )

                # self.fig.select_data('time', 'Setpoint2', color='blue', linestyle ='--', z=2)
                # self.fig.select_data('time', 'Input2', color='red', linestyle ='--', z=2)
                # self.fig.select_data('time', 'Output2', color='green', linestyle ='--', yaxis='right', z=2)

            # dt = time.time() - t0
            # gevent.sleep(max(self.sleep_time - dt, 0.01))
            gevent.sleep(self.sleep_time)
