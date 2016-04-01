from bliss.common.task_utils import *
import gevent
import gevent.event
import math
from bliss.common import log

class TInput(object):
    def __init__(self, controller, config):
        log.info("On TInput")
        log.info("  config type is: %s" % type(config))
        log.info("  controller type is: %s" % type(controller))
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
        log.info("On TInput:read")
        return self.controller.read_tinput(self)

    def state(self):
        log.info("On TInput:state")
        return self.controller.state_tinput(self)

class TOutput(object):
    def __init__(self, controller, config):
        log.info("On TOutput")
        self.__controller = controller
	self.__channel = config['channel']
        self.__name = config["name"]
        self.__limits = (config.get("low_limit"), config.get("high_limit"))
        self.__setpoint_task = None
        self.__setpoint_event = gevent.event.Event()
        self.deadband = float(config["deadband"])
        self.__setpoint_event.set()
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

    @property
    def limits(self):
        return self.__limits

    def read(self):
        log.info("On TOutput:read")
        return self.controller.read_toutput(self)

    def setpoint(self, new_setpoint=None, wait=False):
        log.info("On TOutput:setpoints")
        print "On TOutput:setpoints"
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
        log.info("On TOutput:wait")
        print "On TOutput:wait"
	try:
            self.__setpoint_event.wait()
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        if self.__setpoint_task and not self.__setpoint_task.ready():
            self.__setpoint_task.kill()
        self.controller.setpoint_stop()

    def __setpoint_done(self, task):
        log.info("On TOutput:__setpoint_done")
        print "On TOutput:__setpoint_done"
        try:
            try:
                task.get()
            except Exception:
                sys.excepthook(*sys.exc_info())        
	finally: 
            self.__setpoint_event.set()
	

    @task
    def _do_setpoint(self, setpoint):
        log.info("On TOutput:_do_setpoint")
        print "On TOutput:_do_setpoint"
        self.controller.set_setpoint(self, setpoint)
        
        while self.controller.setpoint_state(self, self.deadband) == 'RUNNING':
            gevent.sleep(0.02)

    def _start_setpoint(self, setpoint):
        log.info("On TOutput:_start_setpoint")
        print "On TOutput:_start_setpoint"
        self.__setpoint_event.clear()
        # the "task" decorator automatically turns a function into a gevent coroutine,
        # and adds a 'wait' keyword argument, whose value is True by default;
        # setting wait to False returns the coroutine object
        return self._do_setpoint(setpoint, wait=False)
        
    def state(self):
        log.info("On TOutput:state")
        return self.controller.state_toutput(self)

class TCtrlLoop(object):
    def __init__(self, controller, config):
        log.info("On TCtrlLoop")
        self.__controller = controller
	self.__name = config["name"]
        self.__config = config
        self.__input = None 
        self.__output = None 

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


class TController(object):
    def __init__(self, config, inputs, outputs, loops):
        log.info("on TController")
        self.__config = config
        self._objects = dict()

        for name, cfg in inputs:
            log.info("  input name: %s" % (name))
            log.info("  input config: %s" % (cfg))
            self._objects[name] = TInput(self, cfg)
        for name, cfg in outputs:
            log.info("  output name: %s" % (name))
            log.info("  output config: %s" % (cfg))
            self._objects[name] = TOutput(self, cfg)
        for name, cfg in loops:
            log.info("  loops name: %s" % (name))
            log.info("  loops config: %s" % (cfg))
            self._objects[name] = TCtrlLoop(self, cfg)

    @property
    def config(self):
        return self.__config

    def get_object(self, name):
        log.info("TController:get_object: %s" % (name))
        return self._objects.get(name)
        
    def read(self, tinput):
        log.info("TController:read: %s" % (tinput))
        raise NotImplementedError
 
    def set_setpoint(self, toutput, sp):
        """Send the command to start setting a setpoint"""
        log.info("TController:set_setpoint: %s" % (toutput))
        raise NotImplementedError

    def get_setpoint(self, toutput):
        """Return current setpoint

        Returned value is None if not setpoint is set
        """
        log.info("TController:get_setpoint: %s" % (toutput))
        raise NotImplementedError

    def state_input(self,tinput):
        """Return a string representing state of an 'inputs' object.

        One of:
        - READY
        - RUNNING
        - ALARM
        - FAULT
        """
        log.info("TController:state_input:" )
        raise NotImplementedError

    def state_output(self,toutput):
        """Return a string representing state of an 'outputs' object.

        One of:
        - READY
        - RUNNING
        - ALARM
        - FAULT
        """
        log.info("TController:state_output:" )
        raise NotImplementedError

    def setpoint_state(self, toutput, deadband):
        """Return a string representing the setpoint state

        One of:
        - READY
        - RUNNING
        - ALARM
        - FAULT
        """
        log.info("TController:setpoint_state: %s" % (toutput))
        mysp = self.get_setpoint(toutput)
        if (mysp == None) :
            return "READY"
        if math.fabs(self.read_toutput(toutput) - mysp) <= deadband:
            return "READY"
        else:
            return "RUNNING"
    
