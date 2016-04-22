from bliss.controllers.temp import Controller
import random
import time
import math
from bliss.common import log

DEGREE_PER_SECOND=0.5
""" all channels will start at this temperature """
INITIAL_TEMP=random.random()*10-random.random()*10

class mockup(Controller):
   def __init__(self, *args):
       #log.info("On mockup ")
       #for arg in args :
       #   log.info("  argument: %s" % (arg))
       Controller.__init__(self, *args)

       self.setpoints = dict()

   def read_input(self, tinput):
       """Reading on a Input object

       Returned value is None if not setpoint is set
       """
       channel = tinput.config.get("channel",str)
       log.debug("mockup: read input: %s" % (channel))
       sp = self.setpoints.setdefault(channel, {"setpoint":None, "temp": INITIAL_TEMP, "end_time":0 })
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
       sp = self.setpoints.setdefault(channel, {"setpoint":None, "temp": INITIAL_TEMP, "end_time":0 })
       if sp["setpoint"] is not None and time.time() > sp["end_time"]:
           sp["temp"] = sp["setpoint"]
           sp["setpoint"] = None
       if sp["setpoint"] is not None:    
           elapsed_time = time.time()-sp["t0"]
           sp["temp"] = sp["start_temp"] + sp["sign"]*(elapsed_time*DEGREE_PER_SECOND)
       log.info("mockup: read output: returns: %s" % (sp["temp"]))      
       return sp["temp"]
  
   def set_setpoint(self, toutput, sp):
       """Doing a setpoint on a Output object

       """
       channel = toutput.config.get("channel",str)
       log.debug("mockup: set_setpoint %s " % (channel))
       start_temp = self.read_output(toutput)
       delta = sp-start_temp
       start_time = time.time()
       self.setpoints[channel].update({ "setpoint":sp, "t0":start_time, "sign":math.copysign(1, delta), "start_temp":start_temp })
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
           log.info("mockup: get_setpoint: returns %s" % (self.setpoints[channel]["setpoint"]))
           return self.setpoints[channel]["setpoint"]
       except KeyError:
           pass

   def state_input(self,tinput):
       """Get the status of a Input object

       """
       log.debug("mockup: state Input")
       return "READY"

   def state_output(self,toutput):
       """Get the status of a Output object

       """
       log.debug("mockup: state Output")
       return "READY"

   def setpoint_stop(self,toutput):
       """Stopping the setpoint

       """
       channel = toutput.config.get("channel",str)
       log.debug("mockup: stop: %s" % (channel))
       sp = self.setpoints.setdefault(channel, {"setpoint":None, "temp": INITIAL_TEMP, "end_time":0 })
       sp["setpoint"]=None
