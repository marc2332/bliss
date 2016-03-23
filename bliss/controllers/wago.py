from bliss.common.measurement import CounterBase, AverageMeasurement
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

  def __call__(self, *args, **kwargs):
    return self
  
  def read(self, acq_time=0):
    meas = AverageMeasurement()
    for reading in meas(acq_time):
      data = self.parent._cntread(acq_time)
      if isinstance(self.cntname, str):
        data = data[self.parent.cnt_dict[self.cntname]]
      reading.value = data
    return meas.average

  def gain(self, gain=None, name=None):
    name = name or self.cntname
    try:
      name = [x for x in self.parent.counter_gain_names if str(name) in x][0]
    except:
      #raise RuntimeError("Cannot find %s in the %s mapping" % (name, self.parent.name))
      return None

    if gain:
      valarr = [False]*3
      valarr[gain-1] = True 
      self.parent.set(name,valarr)
    else:
      valarr = self.parent.get(name)
      if isinstance(valarr, list) and True in valarr:
        return (valarr.index(True)+1)
      else:
        return 0


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
    self.cnt_gain_names = []
    
    try:
      self.counter_gain_names = config_tree["counter_gain_names"].replace(" ","").split(',')
    except:
      pass

    try:
      self.cnt_names = config_tree["counter_names"].replace(" ","").split(',')
    except:
      pass
    else:
      for i, name in enumerate(self.cnt_names):
        self.cnt_dict[name] = i
        add_property(self, name, WagoCounter(self, name, i))

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


