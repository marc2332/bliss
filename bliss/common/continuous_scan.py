try:
    from collections import OrderedDict
except ImportError:
    from ordereddict import OrderedDict
import gevent
from louie import dispatcher
import time

class Scan(object):
  def __init__(self, acq_chain, dm, scan_info=None):
    self.scan_dm = dm
    self.acq_chain = acq_chain
    self.scan_info = scan_info if scan_info else dict()

  def prepare(self):
    self.acq_chain.prepare(self.scan_dm, self.scan_info)

  def start(self):
    self.acq_chain.start()


class AcquisitionMaster(object):
    #SAFE, FAST = (0, 1)
    def __init__(self, device, name, type): #, trigger_mode=AcquisitionMaster.FAST):
        self.__device = device
        self.__name = name
        self.__type = type
        self.__slaves = list()
        self.__triggers = list()
        #self.__trigger_mode = trigger_mode
    @property
    def device(self):
        return self.__device
    @property
    def name(self):
        return self.__name
    @property
    def type(self):
        return self.__type
    @property
    def slaves(self):
        return self.__slaves
    def _prepare(self):
        return self.prepare()
    def prepare(self):
        raise NotImplementedError
    def start(self):
        raise NotImplementedError
    def trigger_ready(self):
        return True
    def trigger(self):
        raise NotImplementedError
    def trigger_slaves(self):
        try:
            if not all([task.ready() for _, task in self.__triggers]):
                invalid_slaves = list()
                for slave, task in self.__triggers:
                    if not task.ready():
                        invalid_slaves.append(slave)
                        task.kill(RuntimeError("Previous trigger is not done, aborting"))
                    else:
                        task.kill()
                raise RuntimeError("Aborted due to bad triggering on slaves: %s" % invalid_slaves)
        finally:
            self.__triggers = list()

        for slave in self.slaves:
            self.__triggers.append((slave, gevent.spawn(slave._trigger)))

class AcquisitionDevice(object):
    def __init__(self, device, name, type):
        self.__device = device
        self.__name = name
        self.__type = type
        self._reading_task = None
    @property
    def device(self):
        return self.__device
    @property
    def name(self):
        return self.__name
    @property
    def type(self):
        return self.__type
    def _prepare(self):
        if not self._check_ready():
            raise RuntimeError("Last reading task is not finished.")
        return self.prepare()
    def prepare(self):
        raise NotImplementedError
    def start(self):
        raise NotImplementedError
    def trigger_ready(self):
        return True
    def _check_ready(self):
        if self._reading_task:
          return self._reading_task.ready()
        return True
    def _trigger(self):
        self.trigger()
        if self._check_ready():
            dispatcher.send("start", self)
            self._reading_task = gevent.spawn(self.reading)
    def trigger(self):
        raise NotImplementedError
    def reading(self):
        pass
    def wait_reading(self):
        return self._reading_task.get() if self._reading_task is not None else True

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
    self._devices_tree = list()

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


  def _get_devices_tree(self):
    devices_list = [(self._get_level(device), device) for device in self.devices.iterkeys()]
    devices_list.sort(reverse=True)

    tree = list()
    for level, device in devices_list:
      node_dict = dict()
      tree.append((level, node_dict)) 
      node = self.device_nodes[device]
      if node.acq_device:
        node_dict['acq_device'] = node.acq_device
      if node.master:
        node_dict['master'] = node.master
      parent_device = self.devices[device]
      node_dict['parent'] = self.device_nodes.get(parent_device)
    return tree


  def _execute(self, func_name):
    tasks = list()
    prev_level = None

    for level, node_dict in self._devices_tree:
      if prev_level != level:
        prev_level = level
        gevent.joinall(tasks)
        tasks = []
      acq_device = node_dict.get('acq_device')
      master = node_dict.get('master')
      if acq_device is not None:
        func = getattr(acq_device, func_name)
        tasks.append(gevent.spawn(func))
      if master is not None:
        func = getattr(master, func_name)
        tasks.append(gevent.spawn(func))

    gevent.joinall(tasks)
    

  def prepare(self, dm, scan_info):
    self._devices_tree = self._get_devices_tree() 

    for master, acq_devs in self.acq_devs_by_master.iteritems():
       del master.slaves[:]
       for acq_dev in acq_devs:
         node = self.device_nodes[acq_dev.device]
         if node.master:
             master.slaves.append(node.master)
         if node.acq_device:
             master.slaves.append(node.acq_device)
    
    dm_prepare_task = gevent.spawn(dm.prepare, scan_info, self._devices_tree)

    self._execute("_prepare")

    dm_prepare_task.join()

    
  def start(self):
    self._execute("start")
    for master, acq_devs in self.acq_devs_by_master.iteritems():
        for acq_dev in acq_devs:
            acq_dev.wait_reading()
            dispatcher.send("end", acq_dev)
