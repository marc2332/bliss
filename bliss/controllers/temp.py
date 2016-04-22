from bliss.common.task_utils import *
import gevent
import gevent.event
import math
from bliss.common import log
from bliss.common.temperature import *



class Controller(object):
    def __init__(self, config, inputs, outputs, loops):
        #log.info("on Controller")
        self.__config = config
        self._objects = dict()
        self._inputs = dict()
        self._outputs = dict()
        self._loops = dict()

        for name, cfg in inputs:
            log.debug("  input name: %s" % (name))
            log.debug("  input config: %s" % (cfg))
            self._objects[name] = Input(self, cfg)
            self._inputs[name] = Input(self, cfg)
        for name, cfg in outputs:
            log.debug("  output name: %s" % (name))
            log.debug("  output config: %s" % (cfg))
            self._objects[name] = Output(self, cfg)
            self._outputs[name] = Output(self, cfg)
        for name, cfg in loops:
            log.debug("  loops name: %s" % (name))
            log.debug("  loops config: %s" % (cfg))
            self._objects[name] = Loop(self, cfg)
            self._loops [name] = Loop(self, cfg)


    @property
    def config(self):
        return self.__config

    def get_object(self, name):
        log.info("Controller:get_object: %s" % (name))
        return self._objects.get(name)
        
    def read(self, tinput):
        log.info("Controller:read: %s" % (tinput))
        raise NotImplementedError
 
    def set_setpoint(self, toutput, sp):
        """Send the command to start setting a setpoint"""
        log.info("Controller:set_setpoint: %s" % (toutput))
        raise NotImplementedError

    def get_setpoint(self, toutput):
        """Return current setpoint

        Returned value is None if not setpoint is set
        """
        log.info("Controller:get_setpoint: %s" % (toutput))
        raise NotImplementedError

    def state_input(self,tinput):
        """Return a string representing state of an 'inputs' object.

        One of:
        - READY
        - RUNNING
        - ALARM
        - FAULT
        """
        log.info("Controller:state_input:" )
        raise NotImplementedError

    def state_output(self,toutput):
        """Return a string representing state of an 'outputs' object.

        One of:
        - READY
        - RUNNING
        - ALARM
        - FAULT
        """
        log.info("Controller:state_output:" )
        raise NotImplementedError

    def setpoint_state(self, toutput, deadband):
        """Return a string representing the setpoint state

        One of:
        - READY
        - RUNNING
        - ALARM
        - FAULT
        """
        log.info("Controller:setpoint_state: %s" % (toutput))
        mysp = self.get_setpoint(toutput)
        if (mysp == None) :
            return "READY"
        if math.fabs(self.read_output(toutput) - mysp) <= deadband:
            return "READY"
        else:
            return "RUNNING"
 
    def setpoint_stop(self,toutput):
        """Stops the setpoint

        """
        log.info("Controller:setpoint_stop") 
