# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common.task_utils import *
import gevent
import gevent.event
import math
from bliss.common import log

class Input(object):
    def __init__(self, controller, config):
        log.debug("On Input")
        #log.debug("  config type is: %s" % type(config))
        #log.debug("  controller type is: %s" % type(controller))
        self.__controller = controller
        self.__channel = config['channel']
        self.__name = config["name"]
        self.__config = config

        # lists of custom attr and commands
        self.__custom_methods_list = list()
        self.__custom_attributes_dict = dict()

    @property
    def controller(self):
        return self.__controller

    @property
    def channel(self):
        return self.__channel

    @property
    def name(self):
        return self.__name

    @property
    def config(self):
        return self.__config

    def read(self):
        log.debug("On Input:read")
        return self.controller.read_input(self)

    def state(self):
        log.debug("On Input:state")
        return self.controller.state_input(self)

    def _add_custom_method(self, method, name, types_info=(None, None)):
        setattr(self, name, method)
        self.__custom_methods_list.append((name, types_info))

class Output(object):
    def __init__(self, controller, config):
        log.debug("On Output")
        self.__controller = controller
	self.__channel = config['channel']
        self.__name = config["name"]
        self.__limits = (config.get("low_limit"), config.get("high_limit"))
        self.__setpoint_task = None
        self.__setpoint_event = gevent.event.Event()
        self.__deadband = float(config["deadband"])
        self.__setpoint_event.set()
        self.__config = config
        self.__stopped = 0
        self.__mode = 0
        # if defined as  self.deadband, attribute available from the instance
        # if defined as  self.__deadband, not available.
        #     in that case, use of decorator property offers it (read only) to world

        self._rampval = None
        self._dwellval = None
        self._stepval = None

        # lists of custom attr and commands
        self.__custom_methods_list = list()
        self.__custom_attributes_dict = dict()

    @property
    def controller(self):
        return self.__controller

    @property
    def channel(self):
        return self.__channel

    @property
    def name(self):
        return self.__name

    @property
    def config(self):
        return self.__config

    @property
    def limits(self):
        return self.__limits

    @property
    def deadband(self):
        return self.__deadband

    def read(self):
        log.debug("On Output:read")
        return self.controller.read_output(self)

    def ramp(self, new_setpoint=None, wait=False, **kwargs):
        log.debug( "On Output:ramp %s" % new_setpoint)
        self.__mode = 1
        return self._ramp(new_setpoint, wait, **kwargs)

    def set(self, new_setpoint=None, wait=False, **kwargs):
        log.debug( "On Output:set %s" % new_setpoint)
        self.__mode = 0
        return self._ramp(new_setpoint, wait, **kwargs)

    def _ramp(self, new_setpoint=None, wait=False, **kwargs):
        log.debug( "On Output:_ramp %s" % new_setpoint)
        if new_setpoint is not None:
            ll, hl = self.limits
            if ll is not None and new_setpoint < ll:
                raise RuntimeError("Invalid setpoint `%f', below low limit (%f)" % (new_setpoint, ll))
            if hl is not None and new_setpoint > hl:
                raise RuntimeError("Invalid setpoint `%f', above high limit (%f)" % (new_setpoint, hl))

            self.__setpoint_task = self._start_setpoint(new_setpoint,**kwargs)
            self.__setpoint_task.link(self.__setpoint_done)

            if wait:
                self.wait()
        else:
            return self.controller.get_setpoint(self)

    def wait(self):
        log.debug("On Output:wait")
        print "On Output:wait"
	try:
            self.__setpoint_event.wait()
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        print "On Output: stop"
        if self.__setpoint_task and not self.__setpoint_task.ready():
            self.__setpoint_task.kill()
            #added lines
            self.__setpoint_event.set()
            self.__stopped = 1
            ##
        self.controller.setpoint_stop(self)

    def abort(self):
        print "On Output: abort"
        if self.__setpoint_task and not self.__setpoint_task.ready():
            self.__setpoint_task.kill()
            #added lines
            self.__setpoint_event.set()
            self.__stopped = 1
            ##
        self.controller.setpoint_abort(self)

    def __setpoint_done(self, task):
        log.debug("On Output:__setpoint_done")
        print "On Output:__setpoint_done"
        try:
            try:
                task.get()
            except Exception:
                sys.excepthook(*sys.exc_info())
	finally:
            if self.__stopped == 0:
               self.__setpoint_event.set()
            self.__stopped = 0


    @task
    def _do_setpoint(self, setpoint, **kwargs):
        log.debug("On Output:_do_setpoint : mode = %s" % (self.__mode))
        if self.__mode == 1:
           self.controller.start_ramp(self, setpoint, **kwargs)
        else :
           self.controller.set(self, setpoint, **kwargs)

        while self.controller._setpoint_state(self, self.__deadband) == 'RUNNING':
            gevent.sleep(0.02)

    def _start_setpoint(self, setpoint, **kwargs):
        log.debug("On Output:_start_setpoint")
        print "On Output:_start_setpoint"
        self.__setpoint_event.clear()
        # the "task" decorator automatically turns a function into a gevent coroutine,
        # and adds a 'wait' keyword argument, whose value is True by default;
        # setting wait to False returns the coroutine object
        return self._do_setpoint(setpoint, wait=False, **kwargs)

    def state(self):
        log.debug("On Output:state")
        return self.controller.state_output(self)

    def rampval(self, new_ramp=None):
        log.debug("On Output:rampval: %s " % (new_ramp))
        """
        Setting/reading the setpoint ramp value (for ramping in degC/hr)

        """
        if new_ramp:
           self._rampval = new_ramp
        else:
           return self._rampval

    def stepval(self, new_step=None):
        log.debug("On Output:stepval: %s " % (new_step))
        """
        Setting/reading the setpoint step value (for ramping in degC/hr)

        """
        if new_step:
           self._stepval = new_step
        else:
           return self._stepval

    def dwellval(self, new_dwell=None):
        log.debug("On Output:setpoint dwell: %s " % (new_dwell))
        """
        Setting/reading the setpoint dwell value (for step mode ramping)

        """
        if new_dwell:
           self._dwellval = new_dwell
        else:
           return self._dwellval

    def _add_custom_method(self, method, name, types_info=(None, None)):
        setattr(self, name, method)
        self.__custom_methods_list.append((name, types_info))


class Loop(object):
    def __init__(self, controller, config):
        log.debug("On Loop")
        self.__controller = controller
	self.__name = config["name"]
        self.__config = config
        self.__input  = controller.get_object(config["input"][1:])
        self.__output = controller.get_object(config["output"][1:])
        self._Pval = None
        self._Ival = None
        self._Dval = None

        # lists of custom attr and commands
        self.__custom_methods_list = list()
        self.__custom_attributes_dict = dict()

    @property
    def controller(self):
        return self.__controller

    @property
    def name(self):
        return self.__name

    @property
    def config(self):
        return self.__config

    @property
    def input(self):
        return self.__input

    @property
    def output(self):
        return self.__output

    def set(self, new_setpoint=None, wait=False,**kwargs):
        log.debug(("On Loop: set %s") % new_setpoint)
        return self.__output.set(new_setpoint, wait, **kwargs)

    def ramp(self, new_setpoint=None, wait=False,**kwargs):
        log.debug(("On Loop: ramp %s") % new_setpoint)
        return self.__output.ramp(new_setpoint, wait, **kwargs)

    def stop(self):
        log.debug("On Loop: stop")
        self.__output.stop()

    def on(self):
        log.debug("On Loop: on")
        self.controller.on(self)

    def off(self):
        log.debug("On Loop: off")
        self.controller.off(self)


    def Pval(self, new_Pval=None):
        log.debug("On Loop: Pval (PID): ")
        """
        Setting/reading the P value (for PID)

        """
        if new_Pval:
           self._Pval = new_Pval
        else:
           return self._Pval

    def Ival(self, new_Ival=None):
        log.debug("On Loop: Ival (PID): ")
        """
        Setting/reading the I value (for PID)

        """
        if new_Ival:
           self._Ival = new_Ival
        else:
           return self._Ival

    def Dval(self, new_Dval=None):
        log.debug("On Loop: Dval (PID): ")
        """
        Setting/reading the D value (for PID)

        """
        if new_Dval:
           self._Dval = new_Dval
        else:
           return self._Dval



    def _add_custom_method(self, method, name, types_info=(None, None)):
        setattr(self, name, method)
        self.__custom_methods_list.append((name, types_info))



