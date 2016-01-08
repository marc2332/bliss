from bliss.common.measurement import CounterBase
from bliss.common.utils import add_property
import wago_client

class WagoCounter(CounterBase):
  def __init__(self, parent, name, index=None):

    if index is None:
      CounterBase.__init__(self, name)
    else:
      CounterBase.__init__(self, parent.name+'.'+name)
    self.index = index
    self.parent = parent
    self.cntname = name

  def read(self, acq_time=None):
    data = self.parent._cntread(acq_time)
    if isinstance(self.cntname, str):
      return data[self.parent.cnt_dict[self.cntname]]
    return data

class wago(object):
  def __init__(self, name, config_tree):

    self.name = name
    self.wago_ip = config_tree["controller_ip"]
    self.controller = None
    self.mapping = ""
    mapping = []
    for module in config_tree["mapping"]:
      module_type = module["type"]
      logical_names = module["logical_names"]
      mapping.append("%s,%s" % (module_type, logical_names))
    self.mapping = "\n".join(mapping)

    self.cnt_dict = {}
    self.cnt_names = []
    try:
      idx = 0
      self.cnt_names = config_tree["counter_names"].replace(" ","").split(',')
      for i in self.cnt_names:
        self.cnt_dict[i] = idx
        self.__counter = WagoCounter(self, i, idx)
        def wc_counter(*args):
          return self.__counter
        add_property(self, i, wc_counter)
        idx += 1
    except:
      pass

  def connect(self):
    self.controller = wago_client.connect(self.wago_ip)
    self.controller.set_mapping(self.mapping)

  def _safety_check(self, *args):
    return True

  def set(self, *args, **kwargs):
    if not self._safety_check(*args):
      return
    if self.controller is None:
      self.connect()
    return self.controller.set(*args, **kwargs)

  def get(self, *args, **kwargs):
    if self.controller is None:
      self.connect()
    return self.controller.get(*args, **kwargs)

  @property
  def counters(self):
    return WagoCounter(self,self.cnt_names)

  def _cntread(self, acq_time=None):
    return self.get(*self.cnt_names)

    

