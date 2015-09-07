from treelib import Tree
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
    def _start(self):
      return self.start()
    def trigger_ready(self):
        return True
    def _trigger(self):
        return self.trigger()
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
    HARDWARE,SOFTWARE = range(2)
    def __init__(self, device, name, data_type,
                 trigger_type = SOFTWARE):
        self.__device = device
        self.__name = name
        self.__type = data_type
        self._reading_task = None
        self._trigger_type = trigger_type

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

    def _start(self):
      if self._trigger_type == AcquisitionDevice.HARDWARE:
        self.start()
        self._reading_task = gevent.spawn(self.reading)
        dispatcher.send("start", self)

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

class AcquisitionChain(object):
  def __init__(self):
      self._tree = Tree()
      self._root_node = self._tree.create_node("acquisition chain","root")
      self._device_to_node = dict()

  def add(self, master, slave):
      slave_node = self._tree.get_node(slave)
      master_node = self._tree.get_node(master)
      if slave_node is not None and isinstance(slave,AcquisitionDevice):
          if(slave_node.bpointer is not self._root_node and 
             master_node is not slave_node.bpointer):
              raise RuntimeError("Cannot add acquisition device %s to multiple masters, current master is %s" % (slave, slave_node._bpointer))
          else:                 # user error, multiple add, ignore for now
              return

      if master_node is None:
          master_node = self._tree.create_node(tag=master.name,identifier=master,parent="root")
      if slave_node is None:
          slave_node = self._tree.create_node(tag=slave.name,identifier=slave,parent=master)
      else:
          self._tree.move_node(slave_node,master_node)

  def _execute(self, func_name):
    tasks = list()

    prev_level = None
    for dev in reversed(list(self._tree.expand_tree(mode=Tree.WIDTH))[1:]):
        node = self._tree.get_node(dev)
        level = self._tree.depth(node)
        if prev_level != level:
            gevent.joinall(tasks)
            tasks = list()
        func = getattr(dev, func_name)
        tasks.append(gevent.spawn(func))
    gevent.joinall(tasks)
    

  def prepare(self, dm, scan_info):
    #self._devices_tree = self._get_devices_tree()  
    for master in (x for x in self._tree.expand_tree() if isinstance(x,AcquisitionMaster)):
        del master.slaves[:]
        for dev in self._tree.get_node(master).fpointer:
            master.slaves.append(dev)

    dm_prepare_task = gevent.spawn(dm.prepare, scan_info, self._tree)

    self._execute("_prepare")

    dm_prepare_task.join()

    
  def start(self):
    self._execute("_start")
    for acq_dev in (x for x in self._tree.expand_tree() if isinstance(x,AcquisitionDevice)):
        acq_dev.wait_reading()
        dispatcher.send("end", acq_dev)
