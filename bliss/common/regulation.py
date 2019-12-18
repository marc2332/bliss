# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
This module implements the classes allowing the control of regulation processes and associated hardware

    The regulation is a process that:
    1) reads a value from an input device 
    2) takes a target value (setpoint) and compare it to the current input value (processed value)
    3) computes an output value sent to an output device which has an effect on the processed value
    4) back to step 1) and loop forever so that the processed value reaches the target value and stays stable around that target value.  

    The regulation Loop has:
    -one input: an Input object to read the processed value (ex: temperature sensor)
    -one output: an Output object which has an effect on the processed value (ex: cooling device)

    The regulation is automaticaly started by setting a new setpoint (Loop.setpoint = target_value).
    The Loop object implements methods to manage the PID algorithm that performs the regulation.
    A Loop object is associated to one Input and one Output.

    The Loop object has a ramp object. If loop.ramprate != 0 then any new setpoint cmd (using Loop.setpoint)
    will use a ramp to reach that value (HW ramp if available else a 'SoftRamp').

    The Output object has a ramp object. If loop.output.ramprate != 0 then any new value sent to the output
    will use a ramp to reach that value (HW ramp if available else a 'SoftRamp').
    
    Depending on the hardware capabilities we can distinguish two main cases.

    1) Hardware regulation:

        A physical controller exists and the input and output devices are connected to the controller.
        In that case, a regulation Controller object must be implemented by inheriting from the Controller base class (bliss.controllers.regulator).
        The inputs and ouputs attached to that controller are defined through the YML configuration file.

            ---------------------------------------------- YML file example ------------------------------------------------------------------------    

            -
                class: Mockup                  # <-- the controller class inheriting from 'bliss.controllers.regulator.Controller'
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
                        low_limit:  0.0          # <-- minimum device value [unit] 
                        high_limit: 100.0        # <-- maximum device value [unit]
                        ramprate: 0.0            # <-- ramprate to reach the output value [unit/s]
            
                ctrl_loops:
                    -
                        name: sample_regulation
                        input: $thermo_sample
                        output: $heater
                        P: 0.5
                        I: 0.2
                        D: 0.0
                        low_limit: 0.0           # <-- low limit of the PID output value. Usaually equal to 0 or -1.
                        high_limit: 1.0          # <-- high limit of the PID output value. Usaually equal to 1.
                        frequency: 10.0
                        deadband: 0.05
                        deadband_time: 1.5
                        ramprate: 1.0            # <-- ramprate to reach the setpoint value [input_unit/s]
                        wait_mode: deadband
             
            ----------------------------------------------------------------------------------------------------------------------------------------

    2) Software regulation

        Input and Output devices are not always connected to a regulation controller.
        For example, it may be necessary to regulate a temperature by moving a cryostream on a stage (axis).

        Any 'SamplingCounter' can be interfaced as an input (ExternalInput) and any 'Axis' as an input or output (ExternalOutput).
        Devices which are not standard Bliss objects can be interfaced by implementing a custom input or output class inheriting from the Input/Output classes.

        To perform the regulation with this kind of inputs/outputs not attached to an hardware regulation controller, users must define a SoftLoop.
        The SoftLoop object inherits from the Loop class and implements its own PID algorithm (using the 'simple_pid' Python module). 

            ---------------------------------------------- YML file example ------------------------------------------------------------------------

            -   
                class: MyCustomInput     # <-- a custom input defined by the user and inheriting from the ExternalInput class
                package: bliss.controllers.temperature.mockup  # <-- the module where the custom class is defined
                plugin: bliss
                name: custom_input
                unit: eV
                        
            
            -   
                class: MyCustomOutput    # <-- a custom output defined by the user and inheriting from the ExternalOutput class
                package: bliss.controllers.temperature.mockup  # <-- the module where the custom class is defined
                plugin: bliss
                name: custom_output
                unit: eV
                low_limit: 0.0           # <-- minimum device value [unit]
                high_limit: 100.0        # <-- maximum device value [unit]
                ramprate: 0.0            # <-- ramprate to reach the output value [unit/s]
            
            
            - 
                class: Input             # <-- value of key 'class' could be 'Input' or 'ExternalInput', the object will be an ExternalInput
                name: diode_input          
                device: $diode           # <-- a SamplingCounter
                unit: mm
            
            
            -
                class: Output            # <-- value of key 'class' could be 'Output' or 'ExternalOutput', the object will be an ExternalOutput
                name: robz_output        
                device: $robz            # <-- an axis
                unit: mm
                low_limit: 0.0           # <-- minimum device value [unit]
                high_limit: 100.0        # <-- minimum device value [unit]
                ramprate: 0.0            # <-- ramprate to reach the output value [unit/s]
                
            
            - 
                class: Loop              # <-- value of key 'class' could be 'Loop' or 'SoftLoop', the object will be a SoftLoop
                name: soft_regul
                input: $custom_input
                output: $robz_output
                P: 0.5
                I: 0.2
                D: 0.0
                low_limit: 0.0            # <-- low limit of the PID output value. Usaually equal to 0 or -1.
                high_limit: 1.0           # <-- high limit of the PID output value. Usaually equal to 1.
                frequency: 10.0
                deadband: 0.05
                deadband_time: 1.5
                ramprate: 1.0       

                ------------------------------------------------------------------------------------------------------------------------------------

    
        Note: a SoftLoop can use an Input or Output defined in a regulation controller section.
        For example the 'soft_regul' loop could define 'thermo_sample' as its input.  
    
"""

import time
import gevent
import gevent.event
import enum

from bliss import current_session
from bliss import global_map
from bliss.common.logtools import log_debug
from bliss.common.utils import with_custom_members, autocomplete_property
from bliss.common.counter import SamplingCounter
from bliss.controllers.counter import SamplingCounterController, counter_namespace

from bliss.common.soft_axis import SoftAxis
from bliss.common.axis import Axis, AxisState

from simple_pid import PID
from bliss.common.plot import plot

import functools


def lazy_init(func):
    @functools.wraps(func)
    def func_wrapper(self, *args, **kwargs):
        self.controller.init_obj(self)
        return func(self, *args, **kwargs)

    return func_wrapper


@with_custom_members
class Input(SamplingCounterController):
    """ Implements the access to an input device which is accessed via the regulation controller (like a sensor plugged on a channel of the controller)
    """

    def __init__(self, controller, config):
        """ Constructor """

        super().__init__(name=config["name"])

        self._controller = controller
        self._config = config

        # useful attribute for a temperature controller writer
        self._attr_dict = {}

        self.add_counter(SamplingCounter, self.name, unit=config.get("unit", "N/A"))

    def read_all(self, *counters):
        return [self.read()]

    # ----------- BASE METHODS -----------------------------------------

    def load_base_config(self):
        """ Load from the config the values of the standard parameters """

        # below the parameters that may requires communication with the controller

        pass

    @property
    def controller(self):
        """ Return the associated regulation controller """

        return self._controller

    @property
    def config(self):
        """ Return the Input config """

        return self._config

    # ----------- METHODS THAT A CHILD CLASS MUST CUSTOMIZE ------------------

    @lazy_init
    def read(self):
        """ Return the input device value (in input unit) """

        log_debug(self, "Input:read")
        return self._controller.read_input(self)

    @lazy_init
    def state(self):
        """ Return the input device state """

        log_debug(self, "Input:state")
        return self._controller.state_input(self)


class ExternalInput(Input):
    """ Implements the access to an external input device (i.e. not accessed via the regulation controller itself, like an axis or a counter)
        Managed devices are objects of the type:
         - Axis
         - SamplingCounter
    """

    def __init__(self, config):
        super().__init__(None, config)

        self.device = config.get("device")
        self.load_base_config()

    def __close__(self):
        if self.device not in current_session.env_dict.values():
            try:
                self.device.__close__()
            except Exception:
                pass

    # ----------- METHODS THAT A CHILD CLASS SHOULD CUSTOMIZE ------------------

    def read(self):
        """ Return the input device value (in input unit) """

        log_debug(self, "ExternalInput:read")

        if isinstance(self.device, Axis):
            return self.device.position
        elif isinstance(self.device, SamplingCounter):
            return self.device.read()
        else:
            raise TypeError(
                "the associated device must be an 'Axis' or a 'SamplingCounter'"
            )

    def state(self):
        """ Return the input device state """

        log_debug(self, "ExternalInput:state")

        if isinstance(self.device, Axis):
            return self.device.state
        elif isinstance(self.device, SamplingCounter):
            return "READY"
        else:
            raise TypeError(
                "the associated device must be an 'Axis' or a 'SamplingCounter'"
            )


@with_custom_members
class Output(SamplingCounterController):
    """ Implements the access to an output device which is accessed via the regulation controller (like an heater plugged on a channel of the controller)
    
        The Output has a ramp object. 
        If ramprate != 0 then any new value sent to the output
        will use a ramp to reach that value (hardware ramping if available, else a software ramp).

    """

    def __init__(self, controller, config):
        """ Constructor """

        super().__init__(name=config["name"])

        self._controller = controller
        self._config = config

        self._ramp = SoftRamp(self.read, self._set_value)
        self._use_soft_ramp = None

        self._limits = (
            self._config.get("low_limit", None),
            self._config.get("high_limit", None),
        )

        # useful attribute for a temperature controller writer
        self._attr_dict = {}

        self.add_counter(SamplingCounter, self.name, unit=config.get("unit", "N/A"))

    def read_all(self, *counters):
        return [self.read()]

    # ----------- BASE METHODS -----------------------------------------

    def load_base_config(self):
        """ Load from the config the value of the standard parameters """

        # below the parameters that may requires communication with the controller

        if self._config.get("ramprate") is not None:
            self.ramprate = self._config.get("ramprate")

    @property
    def controller(self):
        """ Return the associated regulation controller """

        return self._controller

    @property
    def config(self):
        """ Return the Output config """

        return self._config

    @property
    def limits(self):
        """ Return the limits of the ouput device (in output unit)
        """

        return self._limits

    @autocomplete_property
    def ramp(self):
        """ Get the ramp object """

        return self._ramp

    def set_value(self, value):
        """ Set 'value' as new target and start ramping to this target (no ramping if ramprate==0).
        """

        log_debug(self, "Output:set_value %s" % value)

        if self._limits[0] is not None:
            value = max(value, self._limits[0])

        if self._limits[1] is not None:
            value = min(value, self._limits[1])

        self._start_ramping(value)

    def _add_custom_method(self, method, name, types_info=(None, None)):
        """ Necessary to add custom methods to this class """

        setattr(self, name, method)
        self.__custom_methods_list.append((name, types_info))

    # ----------- METHODS THAT A CHILD CLASS SHOULD CUSTOMIZE ------------------

    @lazy_init
    def state(self):
        """ Return the state of the output device"""

        log_debug(self, "Output:state")
        return self._controller.state_output(self)

    @lazy_init
    def read(self):
        """ Return the current value of the output device (in output unit) """

        log_debug(self, "Output:read")
        return self._controller.read_output(self)

    @property
    @lazy_init
    def ramprate(self):
        """ Get ramprate (in output unit per second) """

        log_debug(self, "Output:get_ramprate")

        try:
            return self._controller.get_output_ramprate(self)
        except NotImplementedError:
            return self._ramp.rate

    @ramprate.setter
    @lazy_init
    def ramprate(self, value):
        """ Set ramprate (in output unit per second) """

        log_debug(self, "Output:set_ramprate: %s" % (value))

        self._ramp.rate = value
        try:
            self._controller.set_output_ramprate(self, value)
        except NotImplementedError:
            pass

    @lazy_init
    def is_ramping(self):
        """
        Get the ramping status.
        """

        log_debug(self, "Output:is_ramping")

        if (
            self._use_soft_ramp is None
        ):  # case where '_start_ramping' was never called previously.
            return False

        elif self._use_soft_ramp:

            return self._ramp.is_ramping()

        else:
            return self._controller.is_output_ramping(self)

    @lazy_init
    def set_in_safe_mode(self):
        try:
            return self._controller.set_in_safe_mode(self)

        except NotImplementedError:

            # if self.limits[0] is not None:
            #     self.set_value(self.limits[0])
            # else:
            #     self.set_value(0)

            pass

    @lazy_init
    def _set_value(self, value):
        """ Set the value for the output. Value is expressed in output unit """

        # lasy_init not required here because this method is called by a method with the @lasy_init

        log_debug(self, "Output:_set_value %s" % value)

        self._controller.set_output_value(self, value)

    @lazy_init
    def _start_ramping(self, value):
        """ Start the ramping process to target_value """

        # lasy_init not required here because this method is called by a method with the @lasy_init

        log_debug(self, "Output:_start_ramping %s" % value)

        try:
            self._use_soft_ramp = False
            self._controller.start_output_ramp(self, value)
        except NotImplementedError:
            self._use_soft_ramp = True
            self._ramp.start(value)

    @lazy_init
    def _stop_ramping(self):
        """ Stop the ramping process """

        log_debug(self, "Output:_stop_ramping")

        if self._use_soft_ramp is None:
            self._controller.stop_output_ramp(self)
        elif self._use_soft_ramp:
            self._ramp.stop()
        else:
            self._controller.stop_output_ramp(self)


class ExternalOutput(Output):
    """ Implements the access to an external output device (i.e. not accessed via the regulation controller itself, like an axis)
        Managed devices are objects of the type:
         - Axis

        The Output has a ramp object. 
        If ramprate != 0 then any new value sent to the output
        will use a ramp to reach that value (hardware ramping if available, else a software ramp).

    """

    def __init__(self, config):
        super().__init__(None, config)

        self.device = config.get("device")
        self.mode = config.get("mode", "relative")
        self.load_base_config()

    def __close__(self):
        if self.device not in current_session.env_dict.values():
            try:
                self.device.__close__()
            except Exception:
                pass

    # ----------- BASE METHODS -----------------------------------------

    @property
    def ramprate(self):
        """ Get ramprate (in output unit per second) """

        log_debug(self, "ExternalOutput:get_ramprate")

        return self._ramp.rate

    @ramprate.setter
    def ramprate(self, value):
        """ Set ramprate (in output unit per second) """

        log_debug(self, "ExternalOutput:set_ramprate: %s" % (value))

        self._ramp.rate = value

    def is_ramping(self):
        """
        Get the ramping status.
        """

        log_debug(self, "ExternalOutput:is_ramping")

        return self._ramp.is_ramping()

    def _start_ramping(self, value):
        """ Start the ramping process to target_value """

        log_debug(self, "ExternalOutput:_start_ramping %s" % value)

        self._ramp.start(value)

    def _stop_ramping(self):
        """ Stop the ramping process """

        log_debug(self, "ExternalOutput:_stop_ramping")

        self._ramp.stop()

    # ----------- METHODS THAT A CHILD CLASS SHOULD CUSTOMIZE ------------------

    def state(self):
        """ Return the state of the output device"""

        log_debug(self, "ExternalOutput:state")

        if isinstance(self.device, Axis):
            return self.device.state
        else:
            raise TypeError("the associated device must be an 'Axis'")

    def read(self):
        """ Return the current value of the output device (in output unit) """

        log_debug(self, "ExternalOutput:read")

        if isinstance(self.device, Axis):
            return self.device.position
        else:
            raise TypeError("the associated device must be an 'Axis'")

    def _set_value(self, value):
        """ Set the value for the output. Value is expressed in output unit """

        log_debug(self, "ExternalOutput:_set_value %s" % value)

        if isinstance(self.device, Axis):
            if self.mode == "relative":
                self.device.rmove(value)
            elif self.mode == "absolute":
                self.device.move(value)
        else:
            raise TypeError("the associated device must be an 'Axis'")

    def set_in_safe_mode(self):
        pass


@with_custom_members
class Loop(SamplingCounterController):
    """ Implements the access to the regulation loop 

        The regulation is the PID process that:
        1) reads a value from an input device.
        2) takes a target value (setpoint) and compare it to the current input value (processed value).
        3) computes an output value  and send it to an output device which has an effect on the processed value.
        4) back to step 1) and loop forever so that the processed value reaches the target value and stays stable around that target value.  

        The Loop has:
        -one input: an Input object to read the processed value (ex: temperature sensor).
        -one output: an Output object which has an effect on the processed value (ex: cooling device).

        The regulation is automaticaly started by setting a new setpoint (Loop.setpoint = target_value).
        The Loop object implements methods to manage the PID algorithm that performs the regulation.
        A Loop object is associated to one Input and one Output.

        The Loop has a ramp object. If loop.ramprate != 0 then any new setpoint cmd
        will use a ramp to reach that value (HW if available else a soft_ramp).

        The loop output has a ramp object. If loop.output.ramprate != 0 then any new value sent to the output
        will use a ramp to reach that value (HW if available else a soft_ramp).

    """

    @enum.unique
    class WaitMode(enum.IntEnum):
        RAMP = 1
        DEADBAND = 2

    def __init__(self, controller, config):
        """ Constructor """

        super().__init__(name=config["name"])

        self._controller = controller
        self._config = config
        self._input = config.get("input")
        self._output = config.get("output")

        self._ramp = SoftRamp(self.input.read, self._set_setpoint)
        self._use_soft_ramp = None

        # useful attribute for a temperature controller writer
        self._attr_dict = {}

        self._deadband = 0.1
        self._deadband_time = 1.0
        self._deadband_idle_factor = 0.5
        self._in_deadband = False
        self._time_enter_deadband = None

        self._first_scan_move = True

        self._wait_mode = self.WaitMode.RAMP

        self._history_size = 100
        self.clear_history_data()

        self.reg_plot = None

        self.add_counter(SamplingCounter, self.name, unit=config.get("unit", "N/A"))

    # ----------- BASE METHODS -----------------------------------------

    def read_all(self, *counters):
        return [self.setpoint]

    ##--- CONFIG METHODS
    def load_base_config(self):
        """ Load from the config the values of the standard parameters """

        self.deadband = self._config.get("deadband", 0.1)
        self.deadband_time = self._config.get("deadband_time", 1.0)
        self.wait_mode = self._config.get("wait_mode", "ramp")

        # below the parameters that may requires communication with the controller

        if self._config.get("P") is not None:
            self.kp = self._config.get("P")
        if self._config.get("I") is not None:
            self.ki = self._config.get("I")
        if self._config.get("D") is not None:
            self.kd = self._config.get("D")

        if self._config.get("frequency") is not None:
            self.sampling_frequency = self._config.get("frequency")

        if self._config.get("ramprate") is not None:
            self.ramprate = self._config.get("ramprate")

        if (self._config.get("low_limit") is not None) and (
            self._config.get("low_limit") is not None
        ):
            self.pid_range = (
                self._config.get("low_limit"),
                self._config.get("high_limit"),
            )

    ##--- MAIN ATTRIBUTES
    @autocomplete_property
    def controller(self):
        """ Return the associated regulation controller """

        return self._controller

    @property
    def config(self):
        """ Return the loop config """

        return self._config

    # @property
    @autocomplete_property
    def counters(self):
        """ Standard counter namespace """

        all_counters = (
            list(self.input.counters)
            + list(self.output.counters)
            + [self._counters[self.name]]
        )

        return counter_namespace(all_counters)

    @autocomplete_property
    def input(self):
        """ Return the input object """

        return self._input

    @autocomplete_property
    def output(self):
        """ Return the output object """

        return self._output

    @autocomplete_property
    def ramp(self):
        """ Get the ramp object """

        return self._ramp

    ##--- DEADBAND METHODS
    @property
    def deadband(self):
        """ Get the deadband value (in input unit). 
            The regulation is considered stable if input value is in the range: setpoint +/- deadband
            for a time >= deadband_time.
        """

        log_debug(self, "Loop:get_deadband")
        return self._deadband

    @deadband.setter
    def deadband(self, value):
        """ Set the deadband value (in input unit). 
            The regulation is considered stable if input value is in the range: setpoint +/- deadband
            for a time >= deadband_time.
        """

        log_debug(self, "Loop:set_deadband: %s" % (value))
        self._deadband = value

    @property
    def deadband_time(self):
        """ Get the deadband_time value (s). 
            The regulation is considered stable if input value is in the range: setpoint +/- deadband 
            for a time >= deadband_time.
        """

        log_debug(self, "Loop:get_deadband_time")
        return self._deadband_time

    @deadband_time.setter
    def deadband_time(self, value):
        """ Set the deadband_time value (s). 
            The regulation is considered stable if input value is in the range: setpoint +/- deadband
            for a time >= deadband_time.
        """

        log_debug(self, "Loop:set_deadband_time: %s" % (value))
        self._deadband_time = value

    @property
    def deadband_idle_factor(self):
        """ Get the deadband_idle_factor value (%). 
            The regulation (PID process) won't send a command to the Output if the 
            processed value is in the range: setpoint +/- deadband_idle_factor*deadband.
        """

        log_debug(self, "Loop:get_deadband_idle_factor")
        return self._deadband_idle_factor * 100.

    @deadband_idle_factor.setter
    def deadband_idle_factor(self, value):
        """ Set the deadband_idle_factor value (%) 
            The regulation (PID process) won't send a command to the Output if the 
            processed value is in the range: setpoint +/- deadband_idle_factor*deadband.
        """

        log_debug(self, "Loop:set_deadband_idle_factor: %s" % (value))
        value = max(min(value, 100), 0)
        self._deadband_idle_factor = value / 100.

    def is_in_deadband(self):

        current_value = self.input.read()

        if (current_value < self.setpoint - self.deadband) or (
            current_value > self.setpoint + self.deadband
        ):
            return False
        else:
            return True

    def is_in_idleband(self):

        current_value = self.input.read()

        if (
            current_value < self.setpoint - self.deadband * self._deadband_idle_factor
        ) or (
            current_value > self.setpoint + self.deadband * self._deadband_idle_factor
        ):
            return False
        else:
            return True

    ##--- DATA HISTORY METHODS
    def clear_history_data(self):
        self._history_start_time = time.time()
        self.history_data = {"input": [], "output": [], "setpoint": [], "time": []}

        self._history_counter = 0

    def _store_history_data(self):

        xval = time.time() - self._history_start_time
        # xval = self._history_counter
        self._history_counter += 1

        self.history_data["time"].append(xval)
        self.history_data["input"].append(self.input.read())
        self.history_data["output"].append(self.output.read())
        self.history_data["setpoint"].append(self.setpoint)

        for data in self.history_data.values():
            dx = len(data) - self._history_size
            if dx > 0:
                for i in range(dx):
                    data.pop(0)

    @property
    def history_size(self):
        """
        Get the size of the buffer that stores the latest data (input_value, output_value, working_setpoint)
        """

        log_debug(self, "Loop:get_history_size")
        return self._history_size

    @history_size.setter
    def history_size(self, value):
        """
        Set the size of the buffer that stores the latest data (input_value, output_value, working_setpoint)
        """

        log_debug(self, "Loop:set_history_size: %s" % (value,))
        self._history_size = value

    ##--- CTRL METHODS
    @property
    def setpoint(self):
        """
        Get the current setpoint (target value) (in input unit)
        """

        log_debug(self, "Loop:get_setpoint")
        return self._get_setpoint()

    @setpoint.setter
    def setpoint(self, value):
        """
        Set the new setpoint (target value, in input unit) and start regulation process (if not running already) (w/wo ramp) to reach this setpoint
        """

        log_debug(self, "Loop:set_setpoint: %s" % (value))

        self._in_deadband = False  # see self.axis_state()

        self._start_regulation()
        self._start_ramping(value)

    def stop(self):
        """ Stop the regulation and ramping (if any) """

        log_debug(self, "Loop:stop")

        self._stop_ramping()
        self._stop_regulation()

    def abort(self):
        """ Stop the regulation and ramping (if any) and set output device to minimum value """

        log_debug(self, "Loop:abort")

        self._stop_ramping()
        self._stop_regulation()
        time.sleep(0.5)  # wait for the regulation to be stopped
        self.output.set_in_safe_mode()

    ##--- SOFT AXIS METHODS: makes the Loop object scannable (ex: ascan(loop, ...) )
    @property
    def axis(self):
        """ Return a SoftAxis object that makes the Loop scanable """

        sa = SoftAxis(
            self.input.name,
            self,
            position="axis_position",
            move="axis_move",
            stop="axis_stop",
            state="axis_state",
            low_limit=float("-inf"),
            high_limit=float("+inf"),
            tolerance=self.deadband,
        )

        return sa

    def axis_position(self):
        """ Return the input device value as the axis position """

        return self.input.read()

    def axis_move(self, pos):
        """ Set the Loop setpoint value as if moving an axis to a position """

        self._first_scan_move = False
        self.setpoint = pos

    def axis_stop(self):
        """ Set the setpoint to the current input device value as if stopping a move on an axis """

        self._first_scan_move = True

    def axis_state(self):
        """ Return the current state of the Loop as if it was an axis.
            Two modes (self._wait_mode) are available, the 'ramp' mode or the 'deadband' mode.
            
            - In 'ramp' mode, the axis is 'MOVING' if a ramping process is alive,
              else it is considered as 'READY'.

            - In 'deadband' mode, the axis is 'READY' if the current input value is
              in the deadband interval for a time >= 'deadband_time',
              else it is considered as 'MOVING'.

        """

        # Standard axis states:
        # MOVING : 'Axis is moving'
        # READY  : 'Axis is ready to be moved (not moving ?)'
        # FAULT  : 'Error from controller'
        # LIMPOS : 'Hardware high limit active'
        # LIMNEG : 'Hardware low limit active'
        # HOME   : 'Home signal active'
        # OFF    : 'Axis is disabled (must be enabled to move (not ready ?))'

        if self._wait_mode == self.WaitMode.RAMP:

            if self.is_ramping():
                return AxisState("MOVING")
            else:
                return AxisState("READY")

        else:

            if self._first_scan_move:
                return AxisState("READY")

            # NOT IN DEADBAND
            if not self.is_in_deadband():

                self._time_enter_deadband = None
                self._in_deadband = False
                return AxisState("MOVING")

            # IN DEADBAND
            else:

                if not self._in_deadband:

                    self._in_deadband = True
                    self._time_enter_deadband = time.time()
                    return AxisState("MOVING")

                else:

                    dt = time.time() - self._time_enter_deadband

                    if dt >= self.deadband_time:
                        return AxisState("READY")
                    else:
                        return AxisState("MOVING")

    @property
    def wait_mode(self):
        """ Get the waiting mode used during a scan to determine if the regulation as reached a scan point (see scan 'READY' state).
            <WaitMode.RAMP    : 1>  : READY when the loop has finished to ramp to the scan point.
            <WaitMode.DEADBAND: 2>  : READY when the processed value is in the 'deadband' around the scan point for a time >= 'deadband_time'.
        """

        log_debug(self, "Loop:get_deadband")
        return self._wait_mode

    @wait_mode.setter
    def wait_mode(self, value):
        """ Set the waiting mode used during a scan to determine if the regulation as reached a scan point (see scan 'READY' state).
            <WaitMode.RAMP    : 1>  : READY when the loop has finished to ramp to the scan point.
            <WaitMode.DEADBAND: 2>  : READY when the processed value is in the 'deadband' around the scan point for a time >= 'deadband_time'.
        """

        log_debug(self, "Loop:set_deadband: %s" % (value))

        if isinstance(value, int):
            self._wait_mode = self.WaitMode(value)
        elif isinstance(value, str):
            if value.lower() in ["deadband", "2"]:
                self._wait_mode = self.WaitMode(2)
            else:
                self._wait_mode = self.WaitMode(1)

    def _get_power2unit(self, value):
        """ Convert a power value into a value expressed in output units.
            The power value is the value returned by the PID algorithm.
        """

        xmin, xmax = self.pid_range
        ymin, ymax = self.output.limits

        if None in (ymin, ymax) or (ymin == ymax):
            return value
        else:
            a = (ymax - ymin) / (xmax - xmin)
            b = ymin - a * xmin
            return value * a + b

    # ----------- METHODS THAT A CHILD CLASS SHOULD CUSTOMIZE ------------------

    @property
    @lazy_init
    def kp(self):
        """
        Get the P value (for PID)
        """

        log_debug(self, "Loop:get_kp")
        return self._controller.get_kp(self)

    @kp.setter
    @lazy_init
    def kp(self, value):
        """
        Set the P value (for PID)
        """

        log_debug(self, "Loop:set_kp: %s" % (value))
        self._controller.set_kp(self, value)

    @property
    @lazy_init
    def ki(self):
        """
        Get the I value (for PID)
        """

        log_debug(self, "Loop:get_ki")
        return self._controller.get_ki(self)

    @ki.setter
    @lazy_init
    def ki(self, value):
        """
        Set the I value (for PID)
        """

        log_debug(self, "Loop:set_ki: %s" % (value))
        self._controller.set_ki(self, value)

    @property
    @lazy_init
    def kd(self):
        """
        Get the D value (for PID)
        """

        log_debug(self, "Loop:get_kd")
        return self._controller.get_kd(self)

    @kd.setter
    @lazy_init
    def kd(self, value):
        """
        Set the D value (for PID)
        """

        log_debug(self, "Loop:set_kd: %s" % (value))
        self._controller.set_kd(self, value)

    @property
    @lazy_init
    def sampling_frequency(self):
        """
        Get the sampling frequency (PID) [Hz]
        """

        log_debug(self, "Loop:get_sampling_frequency")
        return self._controller.get_sampling_frequency(self)

    @sampling_frequency.setter
    @lazy_init
    def sampling_frequency(self, value):
        """
        Set the sampling frequency (PID) [Hz]
        """

        log_debug(self, "Loop:set_sampling_frequency: %s" % (value))
        self._controller.set_sampling_frequency(self, value)

    @property
    @lazy_init
    def pid_range(self):
        """
        Get the PID range (PID output value limits).

        Usually, the PID range must be:
        - [ 0, 1] for uni-directionnal 'moves' on the output (like heating more or less) 
        - [-1, 1] for bi-directionnal 'moves' on the output (like heating/cooling or relative moves with a motor axis).

        The PID value is the value returned by the PID algorithm.
        """

        log_debug(self, "Loop:get_pid_range")
        return self._controller.get_pid_range(self)

    @pid_range.setter
    @lazy_init
    def pid_range(self, value):
        """
        Set the PID range (PID output value limits).

        Usually, the PID range must be:
        - [ 0, 1] for uni-directionnal 'moves' on the output (like heating more or less) 
        - [-1, 1] for bi-directionnal 'moves' on the output (like heating/cooling or relative moves with a motor axis).

        The PID value is the value returned by the PID algorithm.
        """

        log_debug(self, "Loop:set_pid_range: %s" % (value,))
        self._controller.set_pid_range(self, value)

    @property
    @lazy_init
    def ramprate(self):
        """ Get ramprate (in input unit per second) """

        log_debug(self, "Loop:get_ramprate")

        try:
            return self._controller.get_ramprate(self)
        except NotImplementedError:
            return self._ramp.rate

    @ramprate.setter
    @lazy_init
    def ramprate(self, value):
        """ Set ramprate (in input unit per second) """

        log_debug(self, "Loop:set_ramprate: %s" % (value))

        self._ramp.rate = value
        try:
            self._controller.set_ramprate(self, value)
        except NotImplementedError:
            pass

    @lazy_init
    def is_ramping(self):
        """
        Get the ramping status.
        """

        log_debug(self, "Loop:is_ramping")

        if (
            self._use_soft_ramp is None
        ):  # case where '_start_ramping' was never called previously.
            return False

        elif self._use_soft_ramp:

            return self._ramp.is_ramping()

        else:
            return self._controller.is_ramping(self)

    @lazy_init
    def _get_setpoint(self):
        """ get the current setpoint """

        log_debug(self, "Loop:_get_setpoint")

        return self._controller.get_setpoint(self)

    @lazy_init
    def _set_setpoint(self, value):
        """ set the current setpoint """

        log_debug(self, "Loop:_set_setpoint %s" % value)
        self._controller.set_setpoint(self, value)

    @lazy_init
    def _start_regulation(self):
        """ Start the regulation loop """

        log_debug(self, "Loop:_start_regulation")

        self._controller.start_regulation(self)

    @lazy_init
    def _stop_regulation(self):
        """ Stop the regulation loop """

        log_debug(self, "Loop:_stop_regulation")

        self._controller.stop_regulation(self)

    @lazy_init
    def _start_ramping(self, value):
        """ Start the ramping to setpoint value """

        log_debug(self, "Loop:_start_ramping %s" % value)

        try:
            self._use_soft_ramp = False
            self._controller.start_ramp(self, value)
        except NotImplementedError:
            self._use_soft_ramp = True
            self._ramp.start(value)

    @lazy_init
    def _stop_ramping(self):
        """ Stop the ramping """

        log_debug(self, "Loop:_stop_ramping")

        if self._use_soft_ramp is None:
            self._controller.stop_ramp(self)
        elif self._use_soft_ramp:
            self._ramp.stop()
        else:
            self._controller.stop_ramp(self)

    @property
    def plot(self):
        if not self.reg_plot:
            self.reg_plot = RegPlot(self)
        self.reg_plot.start()
        return self.reg_plot


class SoftLoop(Loop):
    """ Implements the software regulation loop.

        A SoftLoop should be used when there is no hardware to handle the PID regulation
        or when we want to override the internal PID regulation of the hardware.

        The regulation is the PID process that:
        1) reads a value from an input device.
        2) takes a target value (setpoint) and compare it to the current input value (processed value).
        3) computes an output value and send it to an output device which has an effect on the processed value.
        4) back to step 1) and loop forever so that the processed value reaches the target value and stays stable around that target value.  

        The Loop has:
        -one input: an Input object to read the processed value (ex: temperature sensor).
        -one output: an Output object which has an effect on the processed value (ex: cooling device).

        The regulation is automaticaly started by setting a new setpoint (Loop.setpoint = target_value).
        The regulation is handled by the software and is based on the 'simple_pid' python module.

        The Loop has a ramp object. If loop.ramprate != 0 then any new setpoint cmd
        will use a ramp to reach that value (HW if available else a soft_ramp).

        The Output has a ramp object. If loop.output.ramprate != 0 then any new value sent to the output
        will use a ramp to reach that value (HW if available else a soft_ramp).

    """

    def __init__(self, config):
        super().__init__(None, config)

        self.pid = PID(
            Kp=1.0,
            Ki=0.0,
            Kd=0.0,
            setpoint=0.0,
            sample_time=0.01,
            output_limits=(0.0, 1.0),
            auto_mode=True,
            proportional_on_measurement=False,
        )

        self.task = None
        self._stop_event = gevent.event.Event()

        self._pid_output_value = None

        self.load_base_config()

    def __close__(self):
        self._stop_event.set()
        for obj in [self._input, self._output]:
            if obj not in current_session.env_dict.values():
                try:
                    obj.__close__()
                except Exception:
                    pass

    @property
    def kp(self):
        """
        Get the P value (for PID)
        """

        log_debug(self, "SoftLoop:get_kp")
        return self.pid.Kp

    @kp.setter
    def kp(self, value):
        """
        Set the P value (for PID)
        """

        log_debug(self, "SoftLoop:set_kp: %s" % (value))
        self.pid.Kp = value

    @property
    def ki(self):
        """
        Get the I value (for PID)
        """

        log_debug(self, "SoftLoop:get_ki")
        return self.pid.Ki

    @ki.setter
    def ki(self, value):
        """
        Set the I value (for PID)
        """

        log_debug(self, "SoftLoop:set_ki: %s" % (value))
        self.pid.Ki = value

    @property
    def kd(self):
        """
        Get the D value (for PID)
        """

        log_debug(self, "SoftLoop:get_kd")
        return self.pid.Kd

    @kd.setter
    def kd(self, value):
        """
        Set the D value (for PID)
        """

        log_debug(self, "SoftLoop:set_kd: %s" % (value))
        self.pid.Kd = value

    @property
    def sampling_frequency(self):
        """
        Get the sampling frequency (PID) [Hz]
        """

        log_debug(self, "SoftLoop:get_sampling_frequency")
        return 1. / self.pid.sample_time

    @sampling_frequency.setter
    def sampling_frequency(self, value):
        """
        Set the sampling frequency (PID) [Hz]
        """

        log_debug(self, "SoftLoop:set_sampling_frequency: %s" % (value))
        self.pid.sample_time = 1. / value

    @property
    def pid_range(self):
        """
        Get the PID range (PID output value limits).

        Usually, the PID range must be:
        - [ 0, 1] for uni-directionnal 'moves' on the output (like heating more or less) 
        - [-1, 1] for bi-directionnal 'moves' on the output (like heating/cooling or relative moves with a motor axis).

        The PID value is the value returned by the PID algorithm.
        """

        log_debug(self, "SoftLoop:get_pid_range")
        return self.pid.output_limits

    @pid_range.setter
    def pid_range(self, value):
        """
        Set the PID range (PID output value limits).

        Usually, the PID range must be:
        - [ 0, 1] for uni-directionnal 'moves' on the output (like heating more or less) 
        - [-1, 1] for bi-directionnal 'moves' on the output (like heating/cooling or relative moves with a motor axis).

        The PID value is the value returned by the PID algorithm.
        """

        log_debug(self, "SoftLoop:set_pid_range: %s" % (value,))
        self.pid.output_limits = value[0:2]

    @property
    def ramprate(self):
        """ Get ramprate (in input unit per second) """

        log_debug(self, "SoftLoop:get_ramprate")

        return self._ramp.rate

    @ramprate.setter
    def ramprate(self, value):
        """ Set ramprate (in input unit per second) """

        log_debug(self, "SoftLoop:set_ramprate: %s" % (value))

        self._ramp.rate = value

    def is_ramping(self):
        """
        Get the ramping status.
        """

        log_debug(self, "SoftLoop:is_ramping")

        return self._ramp.is_ramping()

    def apply_proportional_on_measurement(self, enable):
        """
        To eliminate overshoot in certain types of systems, 
        the proportional term can be calculated directly on the measurement instead of the error.
        """

        log_debug(self, "SoftLoop:apply_proportional_on_measurement: %s" % (enable,))
        self.pid.proportional_on_measurement = bool(enable)

    def _get_setpoint(self):
        """
        Get the current setpoint (target value) (in input unit)
        """

        log_debug(self, "SoftLoop:_get_setpoint")
        return self.pid.setpoint

    def _set_setpoint(self, value):
        """
        For internal use only! Users must use the property only: 'Loop.setpoint = xxx'
        Set the current setpoint (target value) (in input unit)
        """

        log_debug(self, "SoftLoop:_set_setpoint")
        self.pid.setpoint = value

    def _start_regulation(self):
        """ Start the regulation loop """

        log_debug(self, "SoftLoop:_start_regulation")

        if not self.task:
            self.task = gevent.spawn(self._do_regulation)

    def _stop_regulation(self):
        """ Stop the regulation loop """

        log_debug(self, "SoftLoop:_stop_regulation")

        self._stop_event.set()

    def _start_ramping(self, value):
        """ Start the ramping to setpoint value """

        log_debug(self, "SoftLoop:_start_ramping %s" % value)

        self._ramp.start(value)

    def _stop_ramping(self):
        """ Stop the ramping """

        log_debug(self, "SoftLoop:_stop_ramping")

        self._ramp.stop()

    def _do_regulation(self):

        self._stop_event.clear()

        while not self._stop_event.is_set():

            input_value = self.input.read()
            power_value = self.pid(input_value)

            output_value = self._get_power2unit(power_value)

            self._pid_output_value = output_value

            if not self.is_in_idleband():
                self.output.set_value(output_value)

            gevent.sleep(self.pid.sample_time)


class SoftRamp:
    """ Implements the ramping process associate """

    def __init__(self, get_value_func, set_value_func):
        """ Constructor 
        
            - get_value_func: a callable that returns the current value of the variable to be ramped 

            - set_value_func: a callable that sets the current value of the variable to be ramped 

        """

        self._get_value_func = get_value_func
        self._set_value_func = set_value_func

        # useful attribute for a temperature controller writer
        self._attr_dict = {}

        # --- SOFT RAMP ATTRIBUTES -----

        self._rate = 0.0
        self._poll_time = 0.02

        self.target_value = None
        self.new_target_value = None
        self._wrk_setpoint = None

        self.task = None
        self._stop_event = gevent.event.Event()

        self.start_time = None
        self.start_value = None
        self.direction = None

    def __del__(self):
        self._stop_event.set()

    @property
    def poll_time(self):
        """ Get the polling time (sleep time) used by the ramping task loop """

        log_debug(self, "SoftRamp:get_poll_time")
        return self._poll_time

    @poll_time.setter
    def poll_time(self, value):
        """ Set the polling time (sleep time) used by the ramping task loop """

        log_debug(self, "SoftRamp:set_poll_time: %s" % (value))
        self._poll_time = value

    @property
    def rate(self):
        """ Get ramprate (in input unit per second) """

        log_debug(self, "SoftRamp:get_rate")

        return self._rate

    @rate.setter
    def rate(self, value):
        """ Set ramprate (in input unit per second) """

        log_debug(self, "SoftRamp:set_rate: %s" % (value))
        self._rate = value

    def start(self, value):
        """ Start the ramping process to target_value """

        log_debug(self, "SoftRamp:start %s" % value)
        self.new_target_value = value

        if not self._rate:
            self._set_working_point(self.new_target_value)
        elif not self.task:
            self.task = gevent.spawn(self._do_ramping)

    def stop(self):
        """ Stop the ramping process """

        log_debug(self, "SoftRamp:stop")

        if self.task:
            self._stop_event.set()
            self.task.join()

    def is_ramping(self):
        """
        Get the ramping status.
        """

        log_debug(self, "SoftRamp:is_ramping")

        # if not self.task:
        #    return False
        # else:
        #    return True

        return bool(self.task)

    def _set_working_point(self, value):
        """ Set the intermediate point (during a ramping process).
        """

        log_debug(self, "SoftRamp:_set_working_point: %s" % (value))
        self._wrk_setpoint = value
        self._set_value_func(value)

    def _calc_ramp(self):
        """ computes the ramp line (start_value, target_value, direction) """

        if self.new_target_value != self.target_value:

            self.start_time = time.time()
            self.start_value = self._get_value_func()

            if self.new_target_value >= self.start_value:
                self.direction = 1
            else:
                self.direction = -1

            self.target_value = self.new_target_value

    def _do_ramping(self):
        """ performs the step by step ramping """

        self._stop_event.clear()

        while not self._stop_event.is_set():

            self._calc_ramp()

            gevent.sleep(self._poll_time)

            if (
                self._rate == 0
            ):  # DEALS WITH THE CASE WHERE THE USER SET THE RAMPRATE TO ZERO WHILE A RUNNING RAMP HAS BEEN STARTED WITH A RAMPRATE!=0
                self._set_working_point(self.target_value)
                break
            else:
                dt = time.time() - self.start_time
                value = self.start_value + self.direction * self._rate * dt

            if self.direction == 1 and value <= self.target_value:

                self._set_working_point(value)

            elif self.direction == -1 and value >= self.target_value:

                self._set_working_point(value)

            else:
                self._set_working_point(self.target_value)
                break


class RegPlot:
    """ A plotting tool for the regulation Loop
        Plots the regulation Loop parameters over time (input_value, setpoint_value, output_value) 
        Based on flint/silx modules

        usage:  plt = RegPlot( myloop )
                plt.start()
                ...
                plt.stop()
    """

    def __init__(self, tloop):

        self.loop = tloop

        self.task = None
        self._stop_event = gevent.event.Event()
        self.sleep_time = 0.1

    def create_plot(self):
        # print("==== CREATE PLOT")
        # Declare a CurvePlot (see bliss.common.plot)
        self.fig = plot(data=None, name=self.loop.name, closeable=True, selected=True)

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

    def is_plot_active(self):
        try:
            return self.fig._flint.get_plot_name(self.fig.plot_id)
        except:
            return False

    # def close(self):
    #     self.stop()
    #     # close flint tab
    #     pass

    def start(self):
        if not self.is_plot_active():
            self.create_plot()

        if not self.task:
            # print("==== START TASK")
            self.loop.clear_history_data()
            self.task = gevent.spawn(self.run)

    def stop(self):
        self._stop_event.set()

    def run(self):

        self._stop_event.clear()

        while not self._stop_event.is_set() and self.is_plot_active():

            # t0 = time.time()

            try:
                # update data history
                self.loop._store_history_data()

                self.fig.submit("setAutoReplot", False)

                self.fig.add_data(self.loop.history_data["time"], field="time")
                self.fig.add_data(self.loop.history_data["input"], field="Input")
                self.fig.add_data(self.loop.history_data["output"], field="Output")
                self.fig.add_data(self.loop.history_data["setpoint"], field="Setpoint")

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

                self.fig.submit("setAutoReplot", True)

            except:  # Exception as e:
                # print(f"!!! In RegPlot.run: {type(e).__name__}: {e} !!!")
                pass

            # dt = time.time() - t0
            # st = max(0.01, self.sleep_time - dt)
            # gevent.sleep(st)

            gevent.sleep(self.sleep_time)

        # print("==== plot task has finished")
