# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.controllers.regulator import Controller
from bliss.common.regulation import ExternalInput, ExternalOutput

import time
import gevent

from bliss.common.logtools import log_debug

from simple_pid import PID

# DEFAULT INITIAL PARAMETERS
DEGREE_PER_SECOND = 1.0
INITIAL_TEMP = 0.0
INITIAL_OUTPUT_VALUE = 0.0


class MyDevice:
    """ Fake device that simulates any device which is not a standard Bliss object.
        This device will be used as a custom Input or Output by a SoftLoop.
    """

    def __init__(self, name="FakeDevice", config=None):
        self.name = name
        self.current_temp = 1.  # deg

        # live temp simulator attributes
        self.cooling_rate = 1.  # deg per sec
        self.heating_rate = 0.  # deg per sec
        self._cool_down_task = None
        self._stop_cool_down_event = gevent.event.Event()
        self._cool_down_task_frequency = 20.0

    def __del__(self):
        self.close()

    def close(self):
        self._stop_cooling()

    def get_current_temp(self):
        """ read the current temperature (like a sensor) """
        self._start_cooling()
        return self.current_temp

    def get_heating_rate(self):
        return self.heating_rate

    def set_heating_rate(self, heating_rate):
        """ set the current heating rate (like an heater output) """
        self.heating_rate = heating_rate

    def _start_cooling(self):
        if not self._cool_down_task:
            self._stop_cool_down_event.clear()
            self._cool_down_task = gevent.spawn(self._cooling_task)

    def _stop_cooling(self):
        if self._cool_down_task is not None:
            self._stop_cool_down_event.set()
            with gevent.Timeout(2.0):
                self._cool_down_task.join()

    def _cooling_task(self):
        last_time = time.time()
        while not self._stop_cool_down_event.is_set():

            gevent.sleep(1. / self._cool_down_task_frequency)

            now = time.time()
            dt = now - last_time
            last_time = now

            self.current_temp = max(
                0.,
                self.current_temp
                + self.get_heating_rate() * dt
                - self.cooling_rate * dt,
            )


class MySensorBindToAxis(ExternalInput):
    """ An Input that returns a value which depends on the position of an axis """

    def __init__(self, name, config):
        super().__init__(config)
        self.axis = config["linked_axis"]
        self.device.get_heating_rate = lambda: self.axis.position / 10

    def read(self):
        """ returns the input device value (in input unit) """

        log_debug(self, "read")

        return self.device.get_current_temp()

    def state(self):
        """ returns the input device state """

        log_debug(self, "state")
        return "READY"


class MyCustomInput(ExternalInput):
    """ Interface to handle an arbitrary device as a regulation Input """

    def __init__(self, name, config):
        super().__init__(config)

    def read(self):
        """ returns the input device value (in input unit) """

        log_debug(self, "MyCustomInput:read")

        return self.device.get_current_temp()

    def state(self):
        """ returns the input device state """

        log_debug(self, "MyCustomInput:state")
        return "READY"


class MyCustomOutput(ExternalOutput):
    """ Interface to handle an arbitrary device as a regulation Output """

    def __init__(self, name, config):
        super().__init__(config)

    def read(self):
        """ returns the output device value (in output unit) """

        log_debug(self, "MyCustomOutput:read")
        return self.device.get_heating_rate()

    def state(self):
        """ returns the output device state """

        log_debug(self, "MyCustomOutput:state")
        return "READY"

    def _set_value(self, value):
        """ Set the value for the output. Value is expressed in output unit """

        log_debug(self, "MyCustomOutput:_set_value %s" % value)

        self.device.set_heating_rate(value)


class Mockup(Controller):
    """ Simulate a regulation controller. 
        The PID regulation is handled by the controller hardware (simulated).

        This mockup starts '_cool_down_tasks' that simulates a natural cool down of the temperatures measured by the inputs.
        The cooling rate is defined by the special pararmeter 'cooling_rate' associated to the inputs.

        Also the task simulates the effect of the output devices on the temperatures measured by the inputs.
        The outputs have an 'heating_rate' parameter that defines how much the outputs will heat and make the temperatures rising.
        The increase of temperatures is proportional to 'heating_rate * output_power' with output_power in range [0,1].

    """

    def __init__(self, config):

        super().__init__(config)

        # attributes to simulate the behaviour of the controller hardware

        self._cool_down_tasks = {}
        self._stop_cool_down_events = {}
        self._cool_down_task_frequency = 20.0

        self._pid_tasks = {}
        self._stop_pid_events = {}

        self.dummy_output_tasks = {}
        self._stop_dummy_events = {}
        self.dummy_output_task_frequency = 20.0

        self.pids = {}

    def __del__(self):
        self.close()

    def close(self):

        for spe in self._stop_pid_events.values():
            spe.set()

        for sde in self._stop_cool_down_events.values():
            sde.set()

        with gevent.Timeout(2.0):
            gevent.joinall(self._pid_tasks.values())

        with gevent.Timeout(2.0):
            gevent.joinall(self._cool_down_tasks.values())

    def initialize_controller(self):
        # host becomes mandatory
        log_debug(self, "mockup: initialize ")
        self.host = self.config.get("host", str)

        # simulate the PID processes handled by the controller hardware
        for loop_node in self.config.get("ctrl_loops", []):
            loop_name = loop_node.get("name")
            self.pids[loop_name] = PID(
                Kp=1.0,
                Ki=0.0,
                Kd=0.0,
                setpoint=0.0,
                sample_time=0.01,
                output_limits=(0.0, 1.0),
                auto_mode=True,
                proportional_on_measurement=False,
            )

    def initialize_input(self, tinput):
        log_debug(self, "mockup: initialize_input: %s" % (tinput))

        tinput._attr_dict["value"] = INITIAL_TEMP
        tinput._attr_dict["last_cool_time"] = 0.0

        tinput._attr_dict["cooling_rate"] = tinput.config.get("cooling_rate", 1.0)

    def initialize_output(self, toutput):
        log_debug(self, "mockup: initialize_output: %s" % (toutput))

        toutput._attr_dict["value"] = INITIAL_OUTPUT_VALUE

        toutput._attr_dict["heating_rate"] = toutput.config.get(
            "heating_rate", DEGREE_PER_SECOND
        )

    def initialize_loop(self, tloop):
        log_debug(self, "mockup: initialize_loop: %s" % (tloop))

    def set_kp(self, tloop, kp):
        """
        Set the PID P value
        Raises NotImplementedError if not defined by inheriting class

        Args:
            tloop:  Loop class type object 
            kp: the kp value
        """
        log_debug(self, "Controller:set_kp: %s %s" % (tloop, kp))

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
        log_debug(self, "Controller:get_kp: %s" % (tloop))

        return self.pids[tloop.name].Kp

    def set_ki(self, tloop, ki):
        """
        Set the PID I value
        Raises NotImplementedError if not defined by inheriting class

        Args:
            tloop:  Loop class type object 
            ki: the ki value
        """
        log_debug(self, "Controller:set_ki: %s %s" % (tloop, ki))

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
        log_debug(self, "Controller:get_ki: %s" % (tloop))

        return self.pids[tloop.name].Ki

    def set_kd(self, tloop, kd):
        """
        Set the PID D value
        Raises NotImplementedError if not defined by inheriting class

        Args:
            tloop:  Loop class type object 
            kd: the kd value
        """
        log_debug(self, "Controller:set_kd: %s %s" % (tloop, kd))

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
        log_debug(self, "Controller:get_kd: %s" % (tloop))

        return self.pids[tloop.name].Kd

    def get_sampling_frequency(self, tloop):
        """
        Get the sampling frequency (PID)
        Raises NotImplementedError if not defined by inheriting class

        Args: 
            tloop:  Loop class type object
        """
        log_debug(self, "Controller:get_sampling_frequency: %s" % (tloop))

        return 1. / self.pids[tloop.name].sample_time

    def set_sampling_frequency(self, tloop, value):
        """
        Set the sampling frequency (PID)
        Raises NotImplementedError if not defined by inheriting class

        Args: 
            tloop: Loop class type object
            value: the sampling frequency [Hz] 
        """
        log_debug(self, "Controller:set_sampling_frequency: %s %s" % (tloop, value))

        self.pids[tloop.name].sample_time = 1. / value

    def get_pid_range(self, tloop):
        """
        Get the PID range (PID output value limits)
        """
        log_debug(self, "Controller:get_pid_range: %s" % (tloop))

        return self.pids[tloop.name].output_limits

    def set_pid_range(self, tloop, pid_range):
        """
        Set the PID range (PID output value limits)
        """
        log_debug(self, "Controller:set_pid_range: %s %s" % (tloop, pid_range))

        self.pids[tloop.name].output_limits = pid_range

    def start_regulation(self, tloop):
        """
        Starts the regulation process.
        Does NOT start the ramp, use 'start_ramp' to do so.
        Raises NotImplementedError if not defined by inheriting class

        Args: 
            tloop:  Loop class type object
        """
        log_debug(self, "Controller:start_regulation: %s" % (tloop))

        self._start_cooling(tloop)

        if self._stop_pid_events.get(tloop.name) is None:
            self._stop_pid_events[tloop.name] = gevent.event.Event()

        if not self._pid_tasks.get(tloop.name):
            self._stop_pid_events[tloop.name].clear()
            self._pid_tasks[tloop.name] = gevent.spawn(self._pid_task, tloop)

    def stop_regulation(self, tloop):
        """
        Stops the regulation process.
        Does NOT stop the ramp, use 'stop_ramp' to do so.
        Raises NotImplementedError if not defined by inheriting class

        Args: 
            tloop:  Loop class type object
        """
        log_debug(self, "Controller:stop_regulation: %s" % (tloop))

        if self._pid_tasks.get(tloop.name) is not None:
            self._stop_pid_events[tloop.name].set()
            with gevent.Timeout(2.0):
                self._pid_tasks[tloop.name].join()

    def read_input(self, tinput):
        """Reading on a Input object"""
        log_debug(self, "mockup:read_input: %s" % (tinput))
        return tinput._attr_dict["value"]

    def read_output(self, toutput):
        """Reading on a Output object"""
        log_debug(self, "mockup:read_output: %s" % (toutput))
        return toutput._attr_dict["value"]

    def set_output_value(self, toutput, value):
        """ set output value """
        log_debug(self, "mockup:set_output_value: %s %s" % (toutput, value))
        toutput._attr_dict["value"] = value

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
        log_debug(self, "Controller:set_setpoint: %s %s" % (tloop, sp))

        self.pids[tloop.name].setpoint = sp

    def get_setpoint(self, tloop):
        """
        Get the current setpoint (target value)
        Raises NotImplementedError if not defined by inheriting class

        Args:
            tloop:  Loop class type object

        Returns:
            (float) setpoint value (in tloop.input unit).
        """
        log_debug(self, "Controller:get_setpoint: %s" % (tloop))

        return self.pids[tloop.name].setpoint

    def _start_cooling(self, tloop):
        if self._stop_cool_down_events.get(tloop.name) is None:
            self._stop_cool_down_events[tloop.name] = gevent.event.Event()

        if not self._cool_down_tasks.get(tloop.name):
            self._stop_cool_down_events[tloop.name].clear()
            self._cool_down_tasks[tloop.name] = gevent.spawn(self._cooling_task, tloop)

    def _stop_cooling(self, tloop):
        if self._cool_down_tasks.get(tloop.name) is not None:
            self._stop_cool_down_events[tloop.name].set()
            with gevent.Timeout(2.0):
                self._cool_down_tasks[tloop.name].join()

    def _cooling_task(self, tloop):

        tloop.input._attr_dict["last_cool_time"] = time.time()

        while not self._stop_cool_down_events[tloop.name].is_set():

            # compute elapsed time since last call
            tnow = time.time()
            dt = tnow - tloop.input._attr_dict["last_cool_time"]
            tloop.input._attr_dict["last_cool_time"] = tnow

            # compute how much the temperature has naturally decreased because of the physical system losses
            cooling = dt * tloop.input._attr_dict["cooling_rate"]

            # compute how much the temperature has increased because of the output device effect
            if not None in tloop.output.limits:
                power = (tloop.output._attr_dict["value"] - tloop.output.limits[0]) / (
                    tloop.output.limits[1] - tloop.output.limits[0]
                )
            else:
                power = tloop.output._attr_dict["value"]

            heating = dt * tloop.output._attr_dict["heating_rate"] * power

            # update temperature value
            tloop.input._attr_dict["value"] += heating - cooling
            tloop.input._attr_dict["value"] = max(-273, tloop.input._attr_dict["value"])

            gevent.sleep(1. / self._cool_down_task_frequency)

    def _pid_task(self, tloop):

        # simulate the PID processes handled by the controller hardware

        while not self._stop_pid_events[tloop.name].is_set():

            input_value = tloop.input.read()
            power_value = self.pids[tloop.name](input_value)

            output_value = tloop._get_power2unit(power_value)

            if not tloop.is_in_idleband():
                tloop.output.set_value(output_value)

            gevent.sleep(self.pids[tloop.name].sample_time)
