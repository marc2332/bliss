# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.controllers.regulator import Controller, SoftController
from bliss.common.regulation import Input, Output, Loop

import random
import time
import math
import gevent

from bliss.common.utils import object_method, object_method_type
from bliss.common.utils import object_attribute_get, object_attribute_type_get
from bliss.common.utils import object_attribute_set, object_attribute_type_set
from bliss.common.logtools import log_info, log_debug


# DEFAULT INITIAL PARAMETERS
DEGREE_PER_SECOND = 1.0
INITIAL_TEMP = 0.0
INITIAL_POWER = 0.0


# ======= FOR TESTINGS =================
# from bliss.controllers.regulator import RegPlot
# s = sample_regulation
# plt = RegPlot(s)
# plt.start()
# s.setpoint = 20.


class MyDevice:
    """ Fake device that simulates any complex device which is not a standard Bliss object.
        This device will be used as a Custom Input or Output by a SoftRegulation controller.
    """

    def __init__(self, name="FakeDevice"):
        self.name = name
        self.value = 0

    def get_value(self):
        return self.value

    def set_value(self, value):
        self.value = value


class MyCustomInput(Input):
    def __init__(self, name, config):
        super().__init__(None, config)

        self.device = MyDevice()

    def read(self):
        """ returns the input device value (in input unit) """

        log_debug(self, "MyCustomInput:read")
        return self.device.get_value()

    def state(self):
        """ returns the input device state """

        log_debug(self, "MyCustomInput:state")
        return "READY"


class MyCustomOutput(Output):
    def __init__(self, name, config):
        super().__init__(None, config)

        self.device = MyDevice()

    def read(self):
        """ returns the input device value (in input unit) """

        log_debug(self, "MyCustomOutput:read")
        return self.device.get_value()

    def state(self):
        """ returns the input device state """

        log_debug(self, "MyCustomOutput:state")
        return "READY"

    def _set_value(self, value):
        """ Set the value for the output. Value is expressed in output unit """

        log_debug(self, "MyCustomOutput:_set_value %s" % value)

        if None not in self._limits:
            value = max(value, self._limits[0])
            value = min(value, self._limits[1])

        self.device.set_value(value)


class Mockup(SoftController):
    """ Simulate a soft controller. 
        The PID regulation is handled by the software (see 'SoftController' class)
        The ramping cmds (on setpoint or output power) are handled by the software (see 'Ramp' and 'OutputRamp' classes)

        This mockup starts a 'dummy_output_task' that simulates a natural cool down of the system if the current value of the output
        is inferior to the 'equilibrium_value'. It means that:
         - the value of the input device will increase if output value > 'equilibrium_value'
         - the value of the input device will decrease if output value < 'equilibrium_value'
         - the value of the input device will stay stable if output value = 'equilibrium_value'
    """

    __material = "Hg"

    def __init__(self, config, *args):

        SoftController.__init__(self, config, *args)

        self.dummy_output_tasks = {}
        self._stop_dummy_events = {}  # gevent.event.Event()
        self.dummy_output_task_frequency = 20.0

    def __del__(self):
        for sde in self._stop_dummy_events.values():
            sde.set()

        # self._stop_dummy_event.set()
        super().__del__()

    def initialize(self):
        # host becomes mandatory
        log_debug(self, "mockup: initialize ")
        self.host = self.config.get("host", str)

    def initialize_input(self, tinput):
        log_debug(self, "mockup: initialize_input: %s" % (tinput))

        tinput._attr_dict["value"] = INITIAL_TEMP
        tinput._attr_dict["last_read_time"] = 0.0

    def initialize_output(self, toutput):
        log_debug(self, "mockup: initialize_output: %s" % (toutput))

        toutput._attr_dict["value"] = INITIAL_POWER
        toutput._attr_dict["equilibrium_value"] = toutput.config.get(
            "equilibrium_value", 0.3
        )
        toutput._attr_dict["heating_rate"] = toutput.config.get(
            "heating_rate", DEGREE_PER_SECOND
        )

    def initialize_loop(self, tloop):
        log_debug(self, "mockup: initialize_loop: %s" % (tloop))

        self.dummy_output_tasks[tloop.name] = None
        self._stop_dummy_events[tloop.name] = gevent.event.Event()

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

    def start_regulation(self, tloop):
        """ Starts the regulation loop """

        if not self.dummy_output_tasks[tloop.name]:
            self.dummy_output_tasks[tloop.name] = gevent.spawn(
                self._do_dummy_output_task, tloop
            )

        super().start_regulation(tloop)

    def _do_dummy_output_task(self, tloop):
        """ Simulates a system that naturally cool down if not heated by the output device.
            The output device value must be > 'equilibrium_value' to compensate energy loss of the system.
        """

        self._stop_dummy_events[tloop.name].clear()
        tloop.input._attr_dict["last_read_time"] = time.time()

        while not self._stop_dummy_events[tloop.name].is_set():
            tnow = time.time()
            dt = tnow - tloop.input._attr_dict["last_read_time"]
            tloop.input._attr_dict["last_read_time"] = tnow

            fac = (
                tloop.output._attr_dict["value"]
                - tloop.output._attr_dict["equilibrium_value"]
            )
            # convert output value (in device unit) to its corresponding power_value (which is in range [0,1])
            # to apply a ponderation factor on heating/cooling.
            fac = tloop.output.get_unit2power(fac)
            dtemp = dt * tloop.output._attr_dict["heating_rate"] * fac

            tloop.input._attr_dict["value"] += dtemp

            gevent.sleep(1. / self.dummy_output_task_frequency)

    """
    Custom commands and Attributes
    """

    @object_method_type(types_info=("str", "str"), type=Input)
    def get_double_str(self, tinput, value):
        return value + "_" + value

    # Custom Attribute
    @object_attribute_type_get(type_info=("str"), type=Output)
    def get_material(self, toutput):
        return self.__material

    @object_attribute_type_set(type_info=("str"), type=Output)
    def set_material(self, toutput, value):
        self.__material = value
