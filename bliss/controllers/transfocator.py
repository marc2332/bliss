from bliss.common.task_utils import *
from bliss.common import dispatcher
from bliss.common import wrapper
import tf_control

class transfocator:
   def __init__(self, name, config):
       wago_ip = config["controller_ip"]
       lenses = int(config["lenses"])
       pinhole = int(config["pinhole"])

       self.__control = tf_control.TfControl(wago_ip, lenses, pinhole, 3) # 3s. exec timeout
       wrapper.wrap_methods(self.__control, self)

