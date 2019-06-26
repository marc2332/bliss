# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Classes implemented with the regulation Controller (hardware or software)

    The regulation is a process that:
    1) reads a value from an input device 
    2) takes a target value (setpoint) and compare it to the current input value (processed value)
    3) computes an output value sent to an output device which has an effect on the processed value
    4) back to step 1) and loop forever so that the processed value reaches the target value and stays stable around that target value.  

    The regulation Loop has:
    -one input: an Input object to read the processed value (ex: temperature sensor)
    -one output: an Output object which has an effect on the processed value (ex: cooling device)

    The regulation is automaticaly started by setting a new setpoint (Loop.setpoint = target_value).
    The regulation is handled by the associated controller.

    The controller could be an hardware controller (see regulator.Controller) or a software controller
    (see regulator.SoftController).

    The Loop has a ramp object. If loop.ramprate != 0 then any new setpoint cmd (using Loop.setpoint)
    will use a ramp to reach that value (HW if available else a soft_ramp).

    The Output has a ramp object. If loop.output.ramprate != 0 then any new value sent to the output (using Loop.output.set_power)
    will use a ramp to reach that value (HW if available else a soft_ramp).
    
"""

import math
import time
import gevent
import gevent.event

from bliss.common.logtools import log_debug, log_info
from bliss.common.utils import with_custom_members, autocomplete_property
from bliss.common.measurement import SamplingCounter, counter_namespace

from bliss.common.soft_axis import SoftAxis
from bliss.common.axis import Axis, AxisState


class DeviceCounter(SamplingCounter):
    """ Implements access to counter object for
        Input and Output type objects
    """

    def __init__(self, name, parent):
        SamplingCounter.__init__(
            self, name, parent, unit=parent.config.get("unit", "N/A")
        )
        self.parent = parent

    def read(self):
        data = self.parent.read()
        return data


class RegulationCounter(SamplingCounter):
    """ Implements access to counter object for
        Loop type objects
    """

    def __init__(self, name, parent):
        SamplingCounter.__init__(
            self, name, parent, unit=parent.input.config.get("unit", "N/A")
        )
        self.parent = parent

    def read(self):
        data = self.parent.setpoint
        return data


@with_custom_members
class Input:
    """ Implements the access to an input device which is accessed via the regulation controller (like a sensor plugged on a channel of the controller)
    """

    def __init__(self, controller, config):
        """ Constructor """

        self._controller = controller
        self._name = config["name"]
        self._config = config

        # useful attribute for a temperature controller writer
        self._attr_dict = {}

    def load_base_config(self):
        """ Load from the config the values for the standard parameters """

        pass

    @property
    def controller(self):
        """ Returns the associated regulation controller """

        return self._controller

    @property
    def name(self):
        """ returns the Input name """

        return self._name

    @property
    def config(self):
        """ returns the Input config """

        return self._config

    @property
    def counter(self):
        """ returns the counter object """

        return DeviceCounter(self.name, self)

    @property
    def counters(self):
        """Standard counter namespace."""

        return counter_namespace([self.counter])

    def read(self):
        """ returns the input device value (in input unit) """

        log_debug(self, "Input:read")
        return self._controller.read_input(self)

    def state(self):
        """ returns the input device state """

        log_debug(self, "Input:state")
        return self._controller.state_input(self)


class ExternalInput(Input):
    """ Implements the access to an external input device (i.e. not accessed via the regulation controller itself, like an axis or a counter)
        Managed devices are objects of the type:
         - Axis
         - SamplingCounter
    """

    def __init__(self, controller, config):
        super().__init__(controller, config)

        self.device = config["device"]

    def read(self):
        """ returns the input device value (in input unit) """

        log_debug(self, "ExternalInput:read")

        if isinstance(self.device, Axis):
            return self.device.position
        elif isinstance(self.device, SamplingCounter):
            return self.device.read()
        else:
            raise NotImplementedError

    def state(self):
        """ returns the input device state """

        log_debug(self, "ExternalInput:state")

        if isinstance(self.device, Axis):
            return self.device.state
        elif isinstance(self.device, SamplingCounter):
            return "READY"
        else:
            raise NotImplementedError


@with_custom_members
class Output:
    """ Implements the access to an output device which is accessed via the regulation controller (like an heater plugged on a channel of the controller)
    
        The Output has a ramp object. 
        If ramprate != 0 then any new value sent to the output (using Output.set_power)
        will use a ramp to reach that value (hardware ramping if available, else a software ramp).

    """

    def __init__(self, controller, config):
        """ Constructor """

        self._controller = controller
        self._name = config["name"]
        self._config = config

        self._ramp = OutputRamp(self)

        # useful attribute for a temperature controller writer
        self._attr_dict = {}

    def load_base_config(self):
        """ Load from the config the value for the standard parameters """

        self._limits = (
            self._config.get("low_limit", None),
            self._config.get("high_limit", None),
        )
        self.ramprate = self._config.get("ramprate", 0.0)

    @property
    def controller(self):
        """ Return the associated regulation controller """

        return self._controller

    @property
    def name(self):
        """ Return the Output name """

        return self._name

    @property
    def config(self):
        """ Return the Output config """

        return self._config

    @property
    def counter(self):
        """ Return the counter object """

        return DeviceCounter(self.name, self)

    @property
    def counters(self):
        """Standard counter namespace """

        return counter_namespace([self.counter])

    @property
    def limits(self):
        """ Return the limits of the ouput device (in output unit). 
            The low limit corresponds to 0% power on output.
            The high limit corresponds to 100% power on output.
        """

        return self._limits

    @autocomplete_property
    def ramp(self):
        """ Get the ramp object """

        return self._ramp

    @property
    def ramprate(self):
        """ Get ramprate (in output unit per second) """

        log_debug(self, "Output:get_ramprate")
        return self._ramp.rate

    @ramprate.setter
    def ramprate(self, value):
        """ Set ramprate (in output unit per second) """

        log_debug(self, "Output:set_ramprate: %s" % (value))
        self._ramp.rate = value

    def state(self):
        """ Return the state of the output device"""

        log_debug(self, "Output:state")
        return self._controller.state_output(self)

    def read(self):
        """ Return the current value of the output device (in output unit) """

        log_debug(self, "Output:read")
        return self._controller.read_output(self)

    def set_power(self, power_value):
        """ Set 'power_value' as new target and start ramping to this target (no ramping if ramprate==0).
            The power value is the value returned by the PID algorithm.
            Depending on the hardware or on the controller type (HW Controller or SoftController), 
            it may be necessary to convert the power value into output device units (see 'get_power2unit').
        """

        log_debug(self, "Output:set_power %s" % power_value)
        value = self.get_power2unit(power_value)

        if None not in self._limits:
            value = max(value, self._limits[0])
            value = min(value, self._limits[1])

        self._ramp.start(value)

    def _set_value(self, value):
        """ Set the value for the output. Value is expressed in output unit """

        log_debug(self, "Output:_set_value %s" % value)

        self._controller.set_output_value(self, value)

    def get_power2unit(self, power_value):
        """ Convert a power value into a value expressed in output units.
            The power value is the value returned by the PID algorithm.
            Depending on the hardware or on the controller type (HW Controller or SoftController), 
            it may be necessary to convert the power value into output device units. 
        """

        if (None in self._limits) or (self._limits[1] == self._limits[0]):
            return power_value
        else:
            value = power_value * (self._limits[1] - self._limits[0]) + self._limits[0]
            return value

    def get_unit2power(self, value):
        """ Convert an output value expressed in output units into a power value.
            The power value is the value returned by the PID algorithm.
            Depending on the hardware or on the controller type (HW Controller or SoftController), 
            it may be necessary to convert the power value into output device units. 
        """

        if (None in self._limits) or (self._limits[1] == self._limits[0]):
            return value
        else:
            power_value = (value - self._limits[0]) / (
                self._limits[1] - self._limits[0]
            )
            return power_value

    def get_working_setpoint(self):
        """
        Get the current working setpoint (during a ramping process on the Output)
        """

        log_debug(self, "Output:get_working_setpoint")
        return self._ramp.get_working_setpoint()

    def is_ramping(self):
        """
        Get the ramping status.
        """

        log_debug(self, "Output:is_ramping")
        return self._ramp.is_ramping()

    def _add_custom_method(self, method, name, types_info=(None, None)):
        """ Necessary to add custom methods to this class """

        setattr(self, name, method)
        self.__custom_methods_list.append((name, types_info))


class ExternalOutput(Output):
    """ Implements the access to an external output device (i.e. not accessed via the regulation controller itself, like an axis or a counter)
        Managed devices are objects of the type:
         - Axis

        The Output has a ramp object. 
        If ramprate != 0 then any new value sent to the output (using Output.set_power)
        will use a ramp to reach that value (hardware ramping if available, else a software ramp).

    """

    def __init__(self, controller, config):
        super().__init__(controller, config)

        self.device = config["device"]
        self.mode = config.get("mode", "relative")

    def state(self):
        """ Return the state of the output device"""

        log_debug(self, "ExternalOutput:state")

        if isinstance(self.device, Axis):
            return self.device.state
        else:
            raise NotImplementedError

    def read(self):
        """ Return the current value of the output device (in output unit) """

        log_debug(self, "ExternalOutput:read")

        if isinstance(self.device, Axis):
            return self.device.position
        else:
            raise NotImplementedError

    def _set_value(self, value):
        """ Set the value for the output. Value is expressed in output unit """

        log_debug(self, "ExternalOutput:_set_value %s" % value)

        if None not in self._limits:
            value = max(value, self._limits[0])
            value = min(value, self._limits[1])

        if isinstance(self.device, Axis):
            if self.mode == "relative":
                self.device.rmove(value)
            elif self.mode == "absolute":
                self.device.move(value)
        else:
            raise NotImplementedError


@with_custom_members
class Loop:
    """ Implements the access to the regulation loop 

        The regulation is the PID process that:
        1) reads a value from an input device 
        2) takes a target value (setpoint) and compare it to the current input value (processed value)
        3) computes an output value sent to an output device which has an effect on the processed value
        4) back to step 1) and loop forever so that the processed value reaches the target value and stays stable around that target value.  

        The Loop has:
        -one input: an Input object to read the processed value (ex: temperature sensor)
        -one output: an Output object which has an effect on the processed value (ex: cooling device)

        The regulation is automaticaly started by setting a new setpoint (Loop.setpoint = target_value).
        The regulation is handled by the associated controller.

        The controller could be an hardware controller (see regulator.Controller) or a software controller
        (see regulator.SoftController).

        The Loop has a ramp object. If loop.ramprate != 0 then any new setpoint cmd (using Loop.setpoint)
        will use a ramp to reach that value (HW if available else a soft_ramp).

        The Output has a ramp object. If loop.output.ramprate != 0 then any new value sent to the output (using Loop.output.set_power)
        will use a ramp to reach that value (HW if available else a soft_ramp).

    """

    def __init__(self, controller, config):
        """ Constructor """

        self._controller = controller
        self._name = config["name"]
        self._config = config
        self._input = config.get("input")
        self._output = config.get("output")

        self._ramp = Ramp(self)

        # useful attribute for a temperature controller writer
        self._attr_dict = {}

        self._deadband = 0.001
        self._deadband_time = 1.0
        self._deadband_idle_factor = 0.5
        self._in_deadband = False
        self._time_enter_deadband = None

        self._first_scan_move = True

        self._wait_mode = "ramp"  # "deadband"

        self._history_size = 100
        self.clear_history_data()

    def clear_history_data(self):
        self._history_start_time = time.time()
        self.history_data = {
            "input": [],
            "output": [],
            "setpoint": [],
            "time": [],
        }  # , 'input2':[], 'output2':[], 'setpoint2':[]}
        self._history_counter = 0

    def _store_history_data(self, yval, outval, setpoint):

        # xval = time.time() - self._history_start_time
        xval = self._history_counter
        self._history_counter += 1

        self.history_data["time"].append(xval)
        self.history_data["input"].append(yval)
        self.history_data["output"].append(outval)
        self.history_data["setpoint"].append(setpoint)

        # self.history_data['input2'].append(self.input.read())
        # self.history_data['output2'].append(self.output.read())
        # self.history_data['setpoint2'].append(self.setpoint)

        for data in self.history_data.values():
            dx = len(data) - self._history_size
            if dx > 0:
                for i in range(dx):
                    data.pop(0)

    def load_base_config(self):
        """ Load from the config the values for the standard parameters """

        self.kp = self._config.get("P", 1.0)
        self.ki = self._config.get("I", 0.0)
        self.kd = self._config.get("D", 0.0)

        self.deadband = self._config.get("deadband", 1.e-3)
        self.deadband_time = self._config.get("deadband_time", 1.0)
        self.sampling_frequency = self._config.get("frequency", 50.)
        self.ramprate = self._config.get("ramprate", 0.0)

        self._wait_mode = self._config.get("wait_mode", "ramp")

        self.pid_range = (
            self._config.get("low_limit", 0.0),
            self._config.get("high_limit", 1.0),
        )

        # self.dwell = self._config.get("dwell",None)
        # self.step = self._config.get("step",None)

    @autocomplete_property
    def controller(self):
        """ Return the associated regulation controller """

        return self._controller

    @property
    def name(self):
        """ Return the loop name """

        return self._name

    @property
    def config(self):
        """ Return the loop config """

        return self._config

    @property
    def counter(self):
        """ Return the counter object """

        return RegulationCounter(self.name, self)

    @property
    def counters(self):
        """ Standard counter namespace """

        return counter_namespace(
            [self.input.counter, self.output.counter, self.counter]
        )

    @autocomplete_property
    def input(self):
        """ Return the input object """

        if not isinstance(self._input, Input):  # <==== ?????
            self._input = self._input()
        return self._input

    @autocomplete_property
    def output(self):
        """ Return the output object """

        if not isinstance(self._output, Output):  # <==== ?????
            self._output = self._output()
        return self._output

    @property
    def kp(self):
        """
        Get the P value (for PID)
        """

        log_debug(self, "Loop:get_kp")
        return self._controller.get_kp(self)

    @kp.setter
    def kp(self, value):
        """
        Set the P value (for PID)
        """

        log_debug(self, "Loop:set_kp: %s" % (value))
        self._controller.set_kp(self, value)

    @property
    def ki(self):
        """
        Get the I value (for PID)
        """

        log_debug(self, "Loop:get_ki")
        return self._controller.get_ki(self)

    @ki.setter
    def ki(self, value):
        """
        Set the I value (for PID)
        """

        log_debug(self, "Loop:set_ki: %s" % (value))
        self._controller.set_ki(self, value)

    @property
    def kd(self):
        """
        Get the D value (for PID)
        """

        log_debug(self, "Loop:get_kd")
        return self._controller.get_kd(self)

    @kd.setter
    def kd(self, value):
        """
        Set the D value (for PID)
        """

        log_debug(self, "Loop:set_kd: %s" % (value))
        self._controller.set_kd(self, value)

    @property
    def setpoint(self):
        """
        Get the current setpoint (target value) (in input unit)
        """

        log_debug(self, "Loop:get_setpoint")
        return self._controller.get_setpoint(self)

    @setpoint.setter
    def setpoint(self, value):
        """
        Set the new setpoint (target value, in input unit) and start regulation process (if not running already) (w/wo ramp) to reach this setpoint
        """

        log_debug(self, "Loop:set_setpoint: %s" % (value))

        self._in_deadband = False  # see self.axis_state()

        self._start_regulation()
        self._ramp.start(value)

    @autocomplete_property
    def ramp(self):
        """ Get the ramp object """

        return self._ramp

    @property
    def ramprate(self):
        """ Get ramprate (in input unit per second) """

        log_debug(self, "Loop:get_ramprate")
        return self._ramp.rate

    @ramprate.setter
    def ramprate(self, value):
        """ Set ramprate (in input unit per second) """

        log_debug(self, "Loop:set_ramprate: %s" % (value))
        self._ramp.rate = value

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

    @property
    def sampling_frequency(self):
        """
        Get the sampling frequency (PID) [Hz]
        """

        log_debug(self, "Loop:get_sampling_frequency")
        return self._controller.get_sampling_frequency(self)

    @sampling_frequency.setter
    def sampling_frequency(self, value):
        """
        Set the sampling frequency (PID) [Hz]
        """

        log_debug(self, "Loop:set_sampling_frequency: %s" % (value))
        self._controller.set_sampling_frequency(self, value)

    @property
    def pid_range(self):
        """
        Get the PID range (PID output value limits).

        Usually, the PID range must be:
        - [ 0, 1] for uni-directionnal 'moves' on the output (like heating more or less) 
        - [-1, 1] for bi-directionnal 'moves' on the output (like heating/cooling or relative moves with a motor axis).

        The PID value is the value returned by the PID algorithm.
        Depending on the hardware or on the controller type (HW Controller or SoftController), 
        it may be necessary to convert the PID value into output device units (see 'Output.set_power')

        """

        log_debug(self, "Loop:get_pid_range")
        return self._controller.get_pid_range(self)

    @pid_range.setter
    def pid_range(self, value):
        """
        Set the PID range (PID output value limits).

        Usually, the PID range must be:
        - [ 0, 1] for uni-directionnal 'moves' on the output (like heating more or less) 
        - [-1, 1] for bi-directionnal 'moves' on the output (like heating/cooling or relative moves with a motor axis).

        The PID value is the value returned by the PID algorithm.
        Depending on the hardware or on the controller type (HW Controller or SoftController), 
        it may be necessary to convert the PID value into output device units (see 'Output.set_power')
        """

        log_debug(self, "Loop:set_pid_range: %s" % (value,))
        self._controller.set_pid_range(self, value)

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

    def apply_proportional_on_measurement(self, enable):
        """
        To eliminate overshoot in certain types of systems, 
        the proportional term can be calculated directly on the measurement instead of the error.
        Available for 'SoftController' only.
        """

        log_info(self, "Loop:apply_proportional_on_measurement: %s" % (enable,))
        self._controller.apply_proportional_on_measurement(self, enable)

    def stop(self):
        """ Stop the regulation and ramping (if any) """

        log_debug(self, "Loop:stop")
        self._ramp.stop()
        self._controller.stop_regulation(self)

    def abort(self):
        """ Stop the regulation and ramping (if any) and set power on output device to zero """

        log_debug(self, "Loop:abort")
        self._ramp.stop()
        self._controller.stop_regulation(self)
        time.sleep(0.5)  # wait for the regulation to be stopped
        self.output.set_power(0.)

    def _start_regulation(self):
        """ Start the regulation loop """

        log_debug(self, "Loop:start_regulation")
        self._controller.start_regulation(self)

    def get_working_setpoint(self):
        """
        Get the current working setpoint (during a ramping process)
        """

        log_debug(self, "Loop:get_working_setpoint")
        return self._ramp.get_working_setpoint()

    def is_ramping(self):
        """
        Get the ramping status.
        """

        log_debug(self, "Loop:is_ramping")
        return self._ramp.is_ramping()

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

    # ===== Soft Axis Methods =======================

    def get_axis(self):
        """ Return a SoftAxis object that makes the Loop scanable """

        sa = SoftAxis(
            self.name,
            self,
            position="axis_position",
            move="axis_move",
            stop="axis_stop",
            state="axis_state",
            low_limit=float("-inf"),
            high_limit=float("+inf"),
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
        self.setpoint = self.input.read()

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

        if self._wait_mode in ["ramp", 0]:

            if self.is_ramping():
                return AxisState("MOVING")
            else:
                return AxisState("READY")

        else:

            if self._first_scan_move:
                return AxisState("READY")

            # NOT IN DEADBAND
            if not self.is_in_deadband():

                # print("NOT IN DEADBAND:","_in_deadband = ",self._in_deadband )
                self._time_enter_deadband = None
                self._in_deadband = False
                return AxisState("MOVING")

            # IN DEADBAND
            else:

                if not self._in_deadband:
                    # print( "ENTER DEADBAND" )

                    self._in_deadband = True
                    self._time_enter_deadband = time.time()
                    return AxisState("MOVING")
                else:

                    dt = time.time() - self._time_enter_deadband

                    if dt >= self.deadband_time:
                        # print("IN DEADBAND: READY")
                        return AxisState("READY")
                    else:
                        # print("IN DEADBAND: WAITING")
                        return AxisState("MOVING")

    # ================================================


class Ramp:
    """ Implements the access to the ramping process of a Loop (Hard or Soft) """

    def __init__(self, boss):
        """ Constructor """

        self._boss = boss  # <= can be a Loop or an Output

        # useful attribute for a temperature controller writer
        self._attr_dict = {}

        # === SOFT RAMP ATTRIBUTES =====

        self.target_value = None
        self.new_target_value = None
        self._wrk_setpoint = None

        self._rate = 0.0
        self.task = None
        self._stop_event = gevent.event.Event()
        self.use_soft_ramp = None
        self._poll_time = 0.02

        self.start_time = None
        self.start_value = None
        self.direction = None

    def __del__(self):
        self._stop_event.set()

    @property
    def boss(self):
        """ returns the ramp owner """

        log_debug(self, "Ramp:get_boss")
        return self._boss

    # ==== SETUP METHODS ===============
    @property
    def poll_time(self):
        """ Get the polling time (sleep time) used by the ramping task loop """

        log_debug(self, "Ramp:get_poll_time")
        return self._poll_time

    @poll_time.setter
    def poll_time(self, value):
        """ Set the polling time (sleep time) used by the ramping task loop """

        log_debug(self, "Ramp:set_poll_time: %s" % (value))
        self._poll_time = value

    # ==== SPECIFIC METHODS (i.e. overwritten in OutputRamp) =======================
    @property
    def rate(self):
        """ Get ramprate (in input unit per second) """

        log_debug(self, "Ramp:get_rate")
        try:
            return self._boss._controller.get_ramprate(self._boss)
        except NotImplementedError:
            return self._rate

    @rate.setter
    def rate(self, value):
        """ Set ramprate (in input unit per second) """

        log_debug(self, "Ramp:set_rate: %s" % (value))
        self._rate = value
        try:
            self._boss._controller.set_ramprate(self._boss, value)
        except NotImplementedError:
            pass

    def is_ramping(self):
        """
        Get the ramping status.
        """

        log_debug(self, "Ramp:is_ramping")

        if (
            self.use_soft_ramp is None
        ):  # case where 'Loop.setpoint = new_sp' => 'Ramp.start(new_sp)' was never called previously.

            return False

        elif self.use_soft_ramp:

            if not self.task:
                return False
            else:
                return True

        else:
            return self._boss._controller.is_ramping(self._boss)

    def _start_hw_ramp(self, value):
        # value is in input unit
        log_debug(self, "Ramp:_start_hw_ramp: %s" % (value))
        self._boss._controller.start_ramp(self._boss, value)

    def _stop_hw_ramp(self):
        log_debug(self, "Ramp:_stop_hw_ramp")
        self._boss._controller.stop_ramp(self._boss)

    def _set_working_setpoint(self, value):
        """ Set the intermediate setpoint (i.e. working_setpoint) during a ramping process (called by the soft ramp only).
            Value is in input units.
        """

        log_debug(self, "Ramp:_set_working_setpoint: %s" % (value))
        self._wrk_setpoint = value
        self._boss._controller.set_setpoint(self._boss, value)

    def get_working_setpoint(self):
        """ Get the current working setpoint (set by the hard or soft ramping process ).
            Value is in input units.
        """

        if (
            self.use_soft_ramp is None
        ):  # case where 'Loop.setpoint = new_sp' => 'Ramp.start(new_sp)' was never called previously.
            return self._boss.setpoint

        elif self.use_soft_ramp:
            return self._wrk_setpoint

        else:
            return self._boss._controller.get_working_setpoint(self._boss)

    def _get_current_value(self):
        """ Return the current value of the loop.input (in input unit) """

        log_debug(self, "Ramp:_get_current_value")
        return self._boss._input.read()

    # === RAMPING CONTROL METHODS ===================

    def start(self, value):
        """ Start the ramping process to target_value """

        # value is in input unit for Loop.ramp
        # value is in output unit for Output.ramp

        log_debug(self, "Ramp:start")
        self.new_target_value = value

        try:
            self.use_soft_ramp = False
            self._start_hw_ramp(value)
        except NotImplementedError:
            self.use_soft_ramp = True
            self._start_soft_ramp()

    def stop(self):
        """ Stop the ramping process """

        log_debug(self, "Ramp:stop")

        try:
            self._stop_hw_ramp()
        except NotImplementedError:
            if self.task:
                self._stop_event.set()
                self.task.join()

    def _start_soft_ramp(self):
        log_debug(self, "Ramp:_start_soft_ramp")

        if not self._rate:
            self._set_working_setpoint(self.new_target_value)
        elif not self.task:
            self.task = gevent.spawn(self._do_ramping)

    def _calc_ramp(self):
        # new_target_value, target_value, start_value in input unit for Loop.ramp and in output unit for Output.ramp
        if self.new_target_value != self.target_value:

            self.start_time = time.time()
            self.start_value = self._get_current_value()

            if self.new_target_value >= self.start_value:
                self.direction = 1
            else:
                self.direction = -1

            self.target_value = self.new_target_value

    def _do_ramping(self):

        self._stop_event.clear()

        while not self._stop_event.is_set():

            self._calc_ramp()

            gevent.sleep(self._poll_time)

            dt = time.time() - self.start_time
            if (
                self._rate == 0
            ):  # DEALS WITH THE CASE WHERE THE USER SET THE RAMPRATE TO ZERO WHILE A RUNNING RAMP HAS BEEN STARTED WITH A RAMPRATE!=0
                self._set_working_setpoint(self.target_value)
                break
            else:
                value = self.start_value + self.direction * self._rate * dt

            if self.direction == 1 and value <= self.target_value:

                self._set_working_setpoint(value)

            elif self.direction == -1 and value >= self.target_value:

                self._set_working_setpoint(value)

            else:
                self._set_working_setpoint(self.target_value)
                break


class OutputRamp(Ramp):
    """ Implements the access to the ramping process of an Output (Hard or Soft) """

    def __init__(self, boss):
        """ Constructor """

        super().__init__(boss)

    # ==== SPECIFIC METHODS =============================
    @property
    def rate(self):
        """ Get ramprate (in output unit per second) """

        log_debug(self, "OutputRamp:get_rate")
        try:
            return self._boss._controller.get_output_ramprate(self._boss)
        except NotImplementedError:
            return self._rate

    @rate.setter
    def rate(self, value):
        """ set ramprate (in output unit per second )"""

        log_debug(self, "OutputRamp:set_rate: %s" % (value))
        self._rate = value
        try:
            self._boss._controller.set_output_ramprate(self._boss, value)
        except NotImplementedError:
            pass

    def is_ramping(self):
        """
        Get the output ramping status.
        """

        log_debug(self, "OutputRamp:is_ramping")

        if (
            self.use_soft_ramp is None
        ):  # case where 'Loop.setpoint = new_sp' => 'Ramp.start(new_sp)' was never called previously.

            return False

        elif self.use_soft_ramp:

            if not self.task:
                return False
            else:
                return True

        else:
            return self._boss._controller.output_is_ramping(self._boss)

    def _start_hw_ramp(self, value):
        # value is in output unit
        log_debug(self, "OutputRamp:_start_hw_ramp: %s" % (value))
        self._boss._controller.start_output_ramp(self._boss, value)

    def _stop_hw_ramp(self):
        log_debug(self, "OutputRamp:_stop_hw_ramp")
        self._boss._controller.stop_output_ramp(self._boss)

    def _set_working_setpoint(self, value):
        """ Set the intermediate setpoint (i.e. working_setpoint) during a output ramping process (called by the soft ramp only).
            Value is in output units.
        """

        log_debug(self, "OutputRamp:_set_working_setpoint: %s" % (value))
        self._wrk_setpoint = value
        self._boss._set_value(value)

    def get_working_setpoint(self):
        """ Get the current working setpoint (set by the hard or soft output ramping process ).
            Value is in output units.
        """

        log_debug(self, "OutputRamp:_get_working_setpoint")

        if (
            self.use_soft_ramp is None
        ):  # case where 'Output.set_power = new_pwr' => 'Ramp.start(new_pwr)' was never called previously.
            return self._boss.read()

        elif self.use_soft_ramp:
            return self._wrk_setpoint

        else:
            return self._boss._controller.get_output_working_setpoint(self._boss)

    def _get_current_value(self):
        """ Return the current value of the loop.output (in output unit) """

        log_debug(self, "OutputRamp:_get_current_value")
        return self._boss.read()
