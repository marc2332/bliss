from bliss.common.task_utils import *
from bliss.common.event import dispatcher
import time
import socket
"""
Fast shutter, controlled by IcePAP. If the home switch is active, the shutter
is open.
Configuration:
class: fshutter
name: fshut
fshutter_mot: $fshut_mot  #reference to the icepap motor
musst:  $musst            #reference to the musst object (if any)
step: 0.25                #relative move to open/close the shutter, if no musst
shift: 580                #shift in icepap steps from the home search position
                           to set as 0.
icepap_steps: 500         #icepap steps to move when external trigger received
"""
class fshutter:
   def __init__(self, name, config):
      self.fshutter_mot = config["fshutter_mot"]

      try:
         self.musst = config["musst"]
         try:
            self.icepap_steps = config["icepap_steps"]
         except:
            self.icepap_steps = 500
      except:
         self.musst = None
         self.step = config["step"]
         self.icepap_steps = self.fshutter_mot.steps_per_unit*self.step
      
      self.shift = config["shift"]/self.fshutter_mot.steps_per_unit

      self.enastate = None
      self.state()
       

   def state(self):
      enastate = self.enastate
      if self.musst:
         return "CLOSED" if self.musst.putget("?VAL CH1") == 0 else "OPENED"
      else:
         if enastate:
            self.disable()
         if self.fshutter_mot.state().READY:
            if self.fshutter_mot.state().HOME:
               if enastate:
                  self.enable(self.icepap_steps)
               return "OPENED"
            else:
               if enastate:
                  self.enable(self.icepap_steps)
               return "CLOSED"
         else:
            if enastate:
               self.enable(self.icepap_steps)
            return "UNKNOWN"
   
   def _toggle_state_icepap(self):
      self.disable()
      self.fshutter_mot.rmove(self.step, wait=True)
      self.enable()

   def _toggle_state(self):
      self.enable(self.icepap_steps)
      if self.musst:
         btrig = self.musst.putget("?BTRIG")
         self.musst.putget("#BTRIG %d" % (1-btrig))
         dispatcher.send('state', self, 'MOVING')
         while self.fshutter_mot.state().MOVING:
            time.sleep(0.01)

   def msopen(self):
      state = self.state()
      if state == "CLOSED":
         # already closed 
         return
      self._toggle_state()
      dispatcher.send('state', self, self.state())

   def msclose(self):
      state = self.state()
      if state == "OPENED":
         # already open 
         return
      self._toggle_state()
      dispatcher.send('state', self, self.state())

   def open(self):
      state = self.state()
      print "shutter is %s" % state

      if state == "OPENED":
         # already open 
         return
       
      self._toggle_state_icepap()
      new_state = self.state()
      dispatcher.send('state', self, new_state)
      print "now is %s" % new_state

   def close(self):
      state = self.state()
      print "shutter state is %s" % state

      if state == "CLOSED":
         # already closed
         return

      self._toggle_state_icepap()
      new_state = self.state()
      dispatcher.send('state', self, new_state)
      print "now is %s" % new_state

   def _icepap_query(self, cmd_str):
      """Send directly to Icepap controller"""
      motor_address = self.fshutter_mot.address
      controller_host = self.fshutter_mot.controller.host
      s = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
      s.connect((controller_host, 5000))
      if not cmd_str.endswith("\n"):
         cmd_str += "\n"
      s.sendall(cmd_str % motor_address)
      return s.recv(1024)
       
   def _cfg(self, up, down):
      return self._icepap_query("#%%d:shcfg %d %d" % (up, down)) 
   
   def disable(self):
      self.enastate = False
      return self._cfg(0, 0)

   def enable(self, steps=500):
      self.enastate = True
      return self._cfg(steps, steps)

   @task
   def home(self):
       def home_cleanup():
           self.fshutter_mot.set_velocity(self.fshutter_mot.velocity(from_config=True)) 
           self.enable(self.icepap_steps)

       with cleanup(home_cleanup):
         self.disable()
         if self.musst:
            self.musst.putget("#BTRIG 0")
         self.fshutter_mot.home(0)
         self.fshutter_mot.move(self.shift)
         self.fshutter_mot.position(0)
         self.fshutter_mot.dial(0)
         self.fshutter_mot.move(0)

         
         if self.musst:
            self.musst.putget("#ABORT")
            self.musst.putget("#CH CH1 0")
         time.sleep(1)
         self.enable()

       dispatcher.send('state', self, self.state())

