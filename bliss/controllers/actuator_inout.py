from bliss.common import Actuator
import ast

class actuator_inout(Actuator):
   def __init__(self, name, config):
       Actuator.__init__(self)

       self.ctrl = config["controller"]
       self.key_in = config['actuator_state_in']
       self.key_out = config['actuator_state_out']
       self.key_cmd = config['actuator_cmd']
       try:
          inout = config['actuator_inout']
          self.inout = ast.literal_eval(inout)
       except:
           self.inout = {"in":1, "out":0}

   def _set_in(self):
       self.ctrl.set(self.key_cmd, self.inout["in"])

   def _set_out(self):
       self.ctrl.set(self.key_cmd, self.inout["out"])

   def _is_in(self):
       return self.ctrl.get(self.key_in)

   def _is_out(self):
       return self.ctrl.get(self.key_out)
