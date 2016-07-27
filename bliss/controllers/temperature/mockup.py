# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.controllers.temp import Controller
import random
import time
import math
from bliss.common import log

from bliss.common.utils import object_method
from bliss.common.utils import object_attribute_get
from bliss.common.utils import object_attribute_set

DEGREE_PER_SECOND=0.5
""" all channels will start at this temperature """
INITIAL_TEMP=random.random()*10-random.random()*10

class mockup(Controller):
    __material = "Hg"

    def __init__(self, config, *args):
        #log.info("On mockup ")
        #for arg in args :
        #   log.info("  argument: %s" % (arg))
        Controller.__init__(self, config, *args)

        self.setpoints = dict()
        self.setpointramp = dict()

    def initialize(self):
        # host becomes mandatory
        log.debug("mockup: initialize ")
        self.host = self.config.get("host",str)
        print "host is: %s" % self.host

    def initialize_input(self, tinput):
        log.debug("mockup: initialize_input: %s" % (tinput))

    def initialize_output(self, toutput):
        log.debug("mockup: initialize_output: %s" % (toutput))

    def initialize_loop(self, tloop):
        log.debug("mockup: initialize_loop: %s" % (tloop))

    def read_input(self, tinput):
        """Reading on a Input object

        Returned value is None if not setpoint is set
        """
        channel = tinput.config.get("channel",str)
        log.debug("mockup: read input: %s" % (channel))
        sp = self.setpoints.setdefault(channel, {"setpoint":None, \
                                                     "temp": INITIAL_TEMP, \
                                                     "target":None, \
                                                     "end_time":0 })
        if sp["setpoint"] is not None and time.time() > sp["end_time"]:
            sp["temp"] = sp["setpoint"]
            sp["setpoint"] = None

        if sp["setpoint"] is not None:
            elapsed_time = time.time()-sp["t0"]
            sp["temp"] = +sp["sign"]*(elapsed_time*DEGREE_PER_SECOND)

        log.info("mockup: read input: returns: %s" % (sp["temp"]))
        return sp["temp"]

    def read_output(self, toutput):
        """Reading on a TOutput object
        Returned value is None if not setpoint is set
        """
        channel = toutput.config.get("channel",str)
        log.debug("mockup: read output: %s" % (channel))
        sp = self.setpoints.setdefault(channel, {"setpoint":None,
                                                 "temp": INITIAL_TEMP,
                                                 "end_time":0 })
        if sp["setpoint"] is not None and time.time() > sp["end_time"]:
            sp["temp"] = sp["setpoint"]
            sp["setpoint"] = None

        if sp["setpoint"] is not None:
            elapsed_time = time.time()-sp["t0"]
            sp["temp"] = sp["start_temp"] + sp["sign"]*(elapsed_time*DEGREE_PER_SECOND)

        log.info("mockup: read output: returns: %s" % (sp["temp"]))
        return sp["temp"]

    def set(self, toutput, sp, **kwargs):
        """Setting a setpoint as quickly as possible

        """
        if kwargs.has_key("ramp"):
           toutput.rampval(kwargs["ramp"])
        if kwargs.has_key("dwell"):
           toutput.dwellval(kwargs["dwell"])
        if kwargs.has_key("step"):
           toutput.stepval(kwargs["step"])
        channel = toutput.config.get("channel",str)
        log.debug("mockup: set %s on channel %s" % (sp,channel))
        #print kwargs
        start_temp = self.read_output(toutput)
        delta = sp-start_temp
        start_time = time.time()
        self.setpoints[channel].update({ "setpoint":sp, \
                                               "t0":start_time, \
                                             "sign":math.copysign(1, delta), \
                                       "start_temp":start_temp , \
 				          "target":sp})

        #simulate we reached the setpoint
        self.setpoints[channel]["end_time"] = start_time
        self.setpoints[channel]["temp"] = sp

    def start_ramp(self, toutput, sp, **kwargs):
        """Doing a ramp on a Output object

        """
        if kwargs.has_key("ramp"):
           toutput.rampval(kwargs["ramp"])
        if kwargs.has_key("dwell"):
           toutput.dwellval(kwargs["dwell"])
        if kwargs.has_key("step"):
           toutput.stepval(kwargs["step"])
        channel = toutput.config.get("channel",str)
        log.debug("mockup: start_ramp %s on channel %s" % (sp,channel))
        #print kwargs
        start_temp = self.read_output(toutput)
        delta = sp-start_temp
        start_time = time.time()
        self.setpoints[channel].update({ "setpoint":sp, \
                                               "t0":start_time, \
                                             "sign":math.copysign(1, delta), \
                                       "start_temp":start_temp, \
                                           "target":sp})
        # calculate when setpoint will be reached
        delta_time = math.fabs(delta) / DEGREE_PER_SECOND
        self.setpoints[channel]["end_time"]=start_time+delta_time



    def get_setpoint(self, toutput):
        """Get the setpoint value on a Output object

        Returned value is None if not setpoint is set
        """
        channel = toutput.config.get("channel",str)
        log.debug("mockup: get_setpoint %s" % (channel))
        try:
            log.info("mockup: get_setpoint: returns %s" % (self.setpoints[channel]["target"]))
            return self.setpoints[channel]["target"]
        except KeyError:
            pass

    def state_input(self, tinput):
        """Get the status of a Input object

        """
        log.debug("mockup: state Input")
        print "host is %s" %self.host
        return "READY"

    def state_output(self, toutput):
        """Get the status of a Output object

        """
        log.debug("mockup: state Output")
        log.debug("mockup: ramp : %s" % toutput.rampval())
        log.debug("mockup: step : %s" % toutput.stepval())
        log.debug("mockup: dwell : %s" % toutput.dwellval())
        log.debug("mockup: host : %s" % self.host)       
        return "READY"


    def setpoint_stop(self, toutput):
        """Stopping the setpoint on an Output object

        """
        channel = toutput.config.get("channel",str)
        log.debug("mockup: stop: %s" % (channel))
        sp = self.setpoints.setdefault(channel, {"setpoint":None, "temp": INITIAL_TEMP, "end_time":0 })
        sp["setpoint"]=None

    def setpoint_abort(self, toutput):
        """Aborting the setpoint on an Output object

        """
        channel = toutput.config.get("channel",str)
        log.debug("mockup: abort: %s" % (channel))
        self.setpoint_stop(toutput)

    def on(self, tloop):
        """
        Starting the regulation on a Loop
        """
        log.debug("mockup: on: starting regulation between input:%s and output:%s" % (
                tloop.input.channel,tloop.output.channel))
        print "Mockup: regulation on"
        log.debug("mockup: P: %s" % (tloop.Pval()))
        log.debug("mockup: I: %s" % (tloop.Ival()))
        log.debug("mockup: D: %s" % (tloop.Dval()))


    def off(self, tloop):
        """
        Stopping the regulation on a Loop object
        """
        log.debug("mockup: off: stopping regulation between input:%s and output:%s" % (
                tloop.input.channel,tloop.output.channel))
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
        return ("%s : %s" % (time.asctime(), str) )

    """
    Custom commands and Attributes
    """
    # Custom Command
    @object_method(types_info=("str", "str"))
    def get_double_str(self, tinput, value):
        return value + "_" + value

    # Custom Attribute
    @object_attribute_get(type_info=("str"))
    def get_material(self, tinput):
        return self.__material

    @object_attribute_set(type_info=("str"))
    def set_material(self, tinput, value):
        self.__material = value

