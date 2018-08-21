# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.controllers.temp import Controller
from bliss.common.temperature import Input, Output, Loop

import random
import time
import math
from bliss.common import log

from bliss.common.utils import object_method, object_method_type
from bliss.common.utils import object_attribute_get, object_attribute_type_get
from bliss.common.utils import object_attribute_set, object_attribute_type_set

DEGREE_PER_SECOND = 0.5
""" all channels will start at this temperature """
INITIAL_TEMP = 0


class mockup(Controller):
    __material = "Hg"

    def __init__(self, config, *args):
        # log.info("On mockup ")
        # for arg in args :
        #   log.info("  argument: %s" % (arg))
        Controller.__init__(self, config, *args)

        self.setpoints = dict()
        self.setpointramp = dict()

    def initialize(self):
        # host becomes mandatory
        log.debug("mockup: initialize ")
        self.host = self.config.get("host", str)

    def initialize_input(self, tinput):
        log.debug("mockup: initialize_input: %s" % (tinput))

    def initialize_output(self, toutput):
        log.debug("mockup: initialize_output: %s" % (toutput))
        toutput._attr_dict["ramprate"] = None
        toutput._attr_dict["dwell"] = None
        toutput._attr_dict["step"] = None

    def initialize_loop(self, tloop):
        log.debug("mockup: initialize_loop: %s" % (tloop))
        tloop._attr_dict["kp"] = None
        tloop._attr_dict["ki"] = None
        tloop._attr_dict["kd"] = None

    def read_input(self, tinput):
        """Reading on a Input object

        Returned value is None if not setpoint is set
        """
        channel = tinput.config.get("channel", str)
        log.debug("mockup: read input: %s" % (channel))
        sp = self.setpoints.setdefault(
            channel,
            {"setpoint": None, "temp": INITIAL_TEMP, "target": None, "end_time": 0},
        )
        if sp["setpoint"] is not None and time.time() > sp["end_time"]:
            sp["temp"] = sp["setpoint"]
            sp["setpoint"] = None

        if sp["setpoint"] is not None:
            elapsed_time = time.time() - sp["t0"]
            sp["temp"] = +sp["sign"] * (elapsed_time * DEGREE_PER_SECOND)

        log.info("mockup: read input: returns: %s" % (sp["temp"]))
        return sp["temp"]

    def read_output(self, toutput):
        """Reading on a TOutput object
        Returned value is None if not setpoint is set
        """
        channel = toutput.config.get("channel", str)
        log.debug("mockup: read output: %s" % (channel))
        sp = self.setpoints.setdefault(
            channel, {"setpoint": None, "temp": INITIAL_TEMP, "end_time": 0}
        )
        if sp["setpoint"] is not None and time.time() > sp["end_time"]:
            sp["temp"] = sp["setpoint"]
            sp["setpoint"] = None

        if sp["setpoint"] is not None:
            elapsed_time = time.time() - sp["t0"]
            sp["temp"] = sp["start_temp"] + sp["sign"] * (
                elapsed_time * DEGREE_PER_SECOND
            )

        log.info("mockup: read output: returns: %s" % (sp["temp"]))
        return sp["temp"]

    def set_ramprate(self, toutput, rate):
        """ sets the ramp rate """
        toutput._attr_dict["ramprate"] = rate

    def read_ramprate(self, toutput):
        """ reads the ramp rate """
        return toutput._attr_dict["ramprate"]

    def set_step(self, toutput, step):
        """ sets the step value """
        toutput._attr_dict["step"] = step

    def read_step(self, toutput):
        """ reads the step value """
        return toutput._attr_dict["step"]

    def set_dwell(self, toutput, dwell):
        """ sets the dwell value """
        toutput._attr_dict["dwell"] = dwell

    def read_dwell(self, toutput):
        """ reads the dwell value """
        return toutput._attr_dict["dwell"]

    def set_kp(self, tloop, kp):
        """ sets the kp value """
        tloop._attr_dict["kp"] = kp

    def read_kp(self, tloop):
        """ reads the kp value """
        return tloop._attr_dict["kp"]

    def set_ki(self, tloop, ki):
        """ sets the ki value """
        tloop._attr_dict["ki"] = ki

    def read_ki(self, tloop):
        """ reads the ki value """
        return tloop._attr_dict["ki"]

    def set_kd(self, tloop, kd):
        """ sets the kd value """
        tloop._attr_dict["kd"] = kd

    def read_kd(self, tloop):
        """ reads the kd value """
        return tloop._attr_dict["kd"]

    def set(self, toutput, sp, **kwargs):
        """Setting a setpoint as quickly as possible

        """
        if kwargs.has_key("ramp"):
            self.set_ramprate(toutput, kwargs["ramp"])
        if kwargs.has_key("dwell"):
            self.set_dwell(toutput, kwargs["dwell"])
        if kwargs.has_key("step"):
            self.set_step(toutput, kwargs["step"])
        channel = toutput.config.get("channel", str)
        log.debug("mockup: set %s on channel %s" % (sp, channel))
        # print kwargs
        start_temp = self.read_output(toutput)
        delta = sp - start_temp
        start_time = time.time()
        self.setpoints[channel].update(
            {
                "setpoint": sp,
                "t0": start_time,
                "sign": math.copysign(1, delta),
                "start_temp": start_temp,
                "target": sp,
            }
        )

        # simulate we reached the setpoint
        self.setpoints[channel]["end_time"] = start_time
        self.setpoints[channel]["temp"] = sp

    def start_ramp(self, toutput, sp, **kwargs):
        """Doing a ramp on a Output object

        """
        if kwargs.has_key("ramp"):
            self.set_ramprate(toutput, kwargs["ramp"])
        if kwargs.has_key("dwell"):
            self.set_dwell(toutput, kwargs["dwell"])
        if kwargs.has_key("step"):
            self.set_step(toutput, kwargs["step"])
        channel = toutput.config.get("channel", str)
        log.debug("mockup: start_ramp %s on channel %s" % (sp, channel))
        # print kwargs
        start_temp = self.read_output(toutput)
        delta = sp - start_temp
        start_time = time.time()
        self.setpoints[channel].update(
            {
                "setpoint": sp,
                "t0": start_time,
                "sign": math.copysign(1, delta),
                "start_temp": start_temp,
                "target": sp,
            }
        )
        # calculate when setpoint will be reached
        delta_time = math.fabs(delta) / DEGREE_PER_SECOND
        self.setpoints[channel]["end_time"] = start_time + delta_time

    def get_setpoint(self, toutput):
        """Get the setpoint value on a Output object

        Returned value is None if not setpoint is set
        """
        channel = toutput.config.get("channel", str)
        log.debug("mockup: get_setpoint %s" % (channel))
        try:
            log.info(
                "mockup: get_setpoint: returns %s" % (self.setpoints[channel]["target"])
            )
            return self.setpoints[channel]["target"]
        except KeyError:
            pass

    def state_input(self, tinput):
        """Get the status of a Input object

        """
        log.debug("mockup: state Input")
        return "READY"

    def state_output(self, toutput):
        """Get the status of a Output object

        """
        log.debug("mockup: state Output")
        log.debug("mockup: ramp : %s" % self.read_ramprate(toutput))
        log.debug("mockup: step : %s" % self.read_step(toutput))
        log.debug("mockup: dwell : %s" % self.read_dwell(toutput))
        log.debug("mockup: host : %s" % self.host)
        return "READY"

    def setpoint_stop(self, toutput):
        """Stopping the setpoint on an Output object

        """
        channel = toutput.config.get("channel", str)
        log.debug("mockup: stop: %s" % (channel))
        sp = self.setpoints.setdefault(
            channel, {"setpoint": None, "temp": INITIAL_TEMP, "end_time": 0}
        )
        sp["setpoint"] = None

    def setpoint_abort(self, toutput):
        """Aborting the setpoint on an Output object

        """
        channel = toutput.config.get("channel", str)
        log.debug("mockup: abort: %s" % (channel))
        self.setpoint_stop(toutput)

    def on(self, tloop):
        """
        Starting the regulation on a Loop
        """
        log.debug(
            "mockup: on: starting regulation between input:%s and output:%s"
            % (
                tloop.input.config.get("channel", str),
                tloop.output.config.get("channel", str),
            )
        )
        print "Mockup: regulation on"
        log.debug("mockup: P: %s" % (tloop.kp()))
        log.debug("mockup: I: %s" % (tloop.ki()))
        log.debug("mockup: D: %s" % (tloop.kd()))

    def off(self, tloop):
        """
        Stopping the regulation on a Loop object
        """
        log.debug(
            "mockup: off: stopping regulation between input:%s and output:%s"
            % (
                tloop.input.config.get("channel", str),
                tloop.output.config.get("channel", str),
            )
        )
        print "Mockup: regulation off"

    def Wraw(self, str):
        """
        Writing to the controller
        """
        log.debug("mockup: writeraw: %s" % (str))

    def Rraw(self):
        """
        Reading the controller
        """
        log.debug("mockup: readraw: ")
        return time.asctime()

    def WRraw(self, str):
        """
        Writing then Reading the controller
        """
        log.debug("mockup: writeraw: %s" % (str))
        return "%s : %s" % (time.asctime(), str)

    """
    Custom commands and Attributes
    """
    # Custom Command
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
