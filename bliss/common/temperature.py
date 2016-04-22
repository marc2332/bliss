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

class Output(object):
    def __init__(self, controller, config):
        log.debug("On Output")
        self.__controller = controller
	self.__channel = config['channel']
        self.__name = config["name"]
        self.__limits = (config.get("low_limit"), config.get("high_limit"))
        self.__setpoint_task = None
        self.__setpoint_event = gevent.event.Event()
        self.deadband = float(config["deadband"])
        self.__setpoint_event.set()
        self.__config = config
        self.__stopped = 0

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

    def read(self):
        log.debug("On Output:read")
        return self.controller.read_output(self)

    def setpoint(self, new_setpoint=None, wait=False):
        log.debug( "On Output:setpoints %s" % new_setpoint)
        print "On Output:setpoints"
        if new_setpoint:
            ll, hl = self.limits
            if ll is not None and new_setpoint < ll:
                raise RuntimeError("Invalid setpoint `%f', below low limit (%f)" % (new_setpoint, ll))
            if hl is not None and new_setpoint > hl:
                raise RuntimeError("Invalid setpoint `%f', above high limit (%f)" % (new_setpoint, hl))
            
            self.__setpoint_task = self._start_setpoint(new_setpoint)
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
    def _do_setpoint(self, setpoint):
        log.debug("On Output:_do_setpoint")
        print "On Output:_do_setpoint"
        self.controller.set_setpoint(self, setpoint)
        
        while self.controller.setpoint_state(self, self.deadband) == 'RUNNING':
            gevent.sleep(0.02)

    def _start_setpoint(self, setpoint):
        log.debug("On Output:_start_setpoint")
        print "On Output:_start_setpoint"
        self.__setpoint_event.clear()
        # the "task" decorator automatically turns a function into a gevent coroutine,
        # and adds a 'wait' keyword argument, whose value is True by default;
        # setting wait to False returns the coroutine object
        return self._do_setpoint(setpoint, wait=False)
        
    def state(self):
        log.debug("On Output:state")
        return self.controller.state_output(self)

class Loop(object):
    def __init__(self, controller, config):
        log.debug("On Loop")
        self.__controller = controller
	self.__name = config["name"]
        self.__config = config
        self.__input  = controller.get_object(config["input"][1:])
        self.__output = controller.get_object(config["output"][1:])

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

    def setpoint(self, new_setpoint=None, wait=False):
        log.debug(("On Loop: setpoint %s") % new_setpoint)
        self.__output.setpoint(new_setpoint, wait)

    def stop(self):
        log.debug("On Loop: stop") 
        self.__output.stop()


