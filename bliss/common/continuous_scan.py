from bliss.common.data_manager import DataManager
from collections import OrderedDict
import gevent

class Scan(object):
  def __init__(self, dm=None):
    self.dm = dm
    self.acq_chain = None

  def set_acquisition_chain(self, acq_chain):
    self.acq_chain = acq_chain

  def prepare(self):
    if not self.dm:
        raise RuntimeError("No data manager.")
   
    self.scan_dm = DataManager(self.dm)

    self.acq_chain.prepare(self.scan_dm)

  def start(self):
    self.acq_chain.start()


class AcquisitionMaster(object):
    def __init__(self, device):
        self.__device = device
        self.__slaves = list()
    @property
    def device(self):
        return self.__device
    @property
    def slaves(self):
        return self.__slaves
    def prepare(self):
        raise NotImplementedError
    def start(self):
        raise NotImplementedError


class AcquisitionDevice(object):
    def __init__(self, device):
        self.__device = device
    @property
    def device(self):
        return self.__device
    def prepare(self):
        raise NotImplementedError
    def start(self):
        raise NotImplementedError


class _Node:
    def __init__(self, acq_device=None, master=None):
        self.acq_device = acq_device
        self.master = master
    def __repr__(self):
        return "DeviceNode <master:%s, acq_device:%s>" % (self.master, self.acq_device)


class AcquisitionChain(object):
  def __init__(self):
    self.acq_devs_by_master = OrderedDict()
    self.devices = dict()
    self.device_nodes = dict()


  def add(self, master, acq_device):
    self.devices.setdefault(master.device, None)
    master_device = self.devices.setdefault(acq_device.device, master.device)
    if master_device != master.device:
      if master_device is None:
        self.devices[acq_device.device] = master.device
      else:
        for old_master, acq_devs in self.acq_devs_by_master.iteritems():
            if acq_device in acq_devs:
                raise RuntimeError("Cannot add acquisition device %s to multiple masters, current master is %s" % (acq_device, old_master))
    # devices = { cam1: mono, cam2: cam1, c0: timer, c1: timer }
    self.acq_devs_by_master.setdefault(master, []).append(acq_device)
    self.device_nodes.setdefault(acq_device.device, _Node()).acq_device = acq_device
    self.device_nodes.setdefault(master.device, _Node()).master = master
    # device_nodes = { mono: (emotionmaster, None), cam1: (limamaster, limaacqdev), cam2: (None,limaacqdev), c0: (None, diodeacqdev), c1: (None, diodeacqdev), timer: (timermaster, None) }


  def _get_level(self, device, count=0):
    d = self.devices.get(device)
    if d is not None:
      return self._get_level(d, count + 1)
    else:
      return count


  def _execute(self, func_name, devices_list):
    tasks = list()
    prev_level = None

    for level, device in devices_list:
      if prev_level != level:
        prev_level = level
        gevent.joinall(tasks)
        tasks = []
      node = self.device_nodes[device]
      if node.acq_device is not None:
        func = getattr(node.acq_device, func_name)
        tasks.append(gevent.spawn(func))
      if node.master is not None:
        func = getattr(node.master, func_name)
        tasks.append(gevent.spawn(func))

    gevent.joinall(tasks)
    

  def prepare(self, dm):
    self.devices_list = [(self._get_level(device), device) for device in self.devices.iterkeys()]
    self.devices_list.sort(reverse=True)

    prepare_task = gevent.spawn(dm.prepare)

    for master, acq_devs in self.acq_devs_by_master.iteritems():
       del master.slaves[:]
       for acq_dev in acq_devs:
         node = self.device_nodes[acq_dev.device]
         if node.master:
             master.slaves.append(node.master)
         if node.acq_device:
             master.slaves.append(node.acq_device)

    self._execute("prepare", self.devices_list)

    prepare_task.join()

    
  def start(self):
    self._execute("start", self.devices_list)
    
