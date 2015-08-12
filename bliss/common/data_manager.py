from louie import dispatcher
from bliss.config.conductor import client
from bliss.config.settings import Struct,QueueSetting,HashObjSetting
import collections

factory_class = {}
def register(node_type,klass):
    factory_class[node_type] = klass

def get_node(name, node_type = None, parent = None, connection = client.get_cache(db=1),create=False):
    data = Struct(name, connection=connection)
    if node_type is None:
        node_type = data.node_type
        if node_type is None:       # node has been deleted
            return None

    klass = factory_class.get(node_type)
    if klass is None:
        return _Node(node_type, name, parent, connection = connection,create = create)
    else:
        return klass(name, parent = parent, connection = connection,create = create)

def Node(*args,**kwargs):
    kwargs['create']=True
    return _Node(*args, **kwargs)

class _Node(object):
    default_time_to_live = 24*3600 # 1 day

    def __init__(self,node_type,name,parent = None,connection=client.get_cache(db=1), create=False):
        db_name = '%s:%s' % (parent.db_name(),name) if parent else name
        self._data = Struct(db_name,
                            connection=connection)
        children_queue_name = '%s_children_list' % db_name
        self._children = QueueSetting(children_queue_name,
                                      connection=connection)
        info_hash_name = '%s_info' % db_name
        self._info = HashObjSetting(info_hash_name,
                                    connection=connection)
        if create:
            self._data.name = name
            self._data.db_name = db_name
            self._data.node_type = node_type
            if parent: 
                self._data.parent = parent.db_name()
                parent.add_children(self)

    def db_name(self):
        return self._data.db_name

    def name(self):
        return self._data.name

    def add_children(self,*child):
        if len(child) > 1:
            self._children.extend([c.db_name() for c in child])
        else:
            self._children.append(child[0].db_name())

    def parent(self):
        parent_name = self._data.parent
        if parent_name:
            parent = get_node(parent_name)
            if parent is None:  # clean
                del self._data.parent
            return parent

    #@brief iter over children
    #@return an iterator
    #@param from_id start child index
    #@param to_id last child index
    def children(self,from_id = 0,to_id = -1):
        for child_name in self._children.get(from_id,to_id) :
            new_child = get_node(child_name)
            if new_child is not None:
                yield new_child
            else:
                self._children.remove(child_name) # clean

    def last_child(self) :
        return get_node(self._children.get(-1))

    def set_info(self,key,values):
        self._info[keys] = values
        if self._ttl > 0:
            self._info.ttl(self._ttl)

    def info_iteritems(self):
        return self._info.iteritems()

    def info_get(self,name):
        return self._info.get(name)

    def data_update(self,keys):
        self._data.update(keys)

    def set_ttl(self):
        redis_conn = client.get_cache(db=1)
	redis_conn.expire(self.db_name(), _Node.default_time_to_live)
	self._children.ttl(_Node.default_time_to_live)
	self._info.ttl(_Node.default_time_to_live)
        parent = self.parent()
	if parent:
	   parent.set_ttl()

    def store(self, *args):
        pass


class Container(object):
    def __init__(self, name, parent=None):
        self.root_node = parent.node if parent is not None else None
        self.__name = name
        self.node = Node("container", self.__name, parent=self.root_node)


class ScanRecorder(object):
    def __init__(self, name="scan", parent=None, scan_info=None):
        self.__path = None
        self.root_node = parent.node if parent is not None else None
        self.nodes = dict()
	
        if parent:
            key = self.root_node.db_name() 
            run_number = client.get_cache(db=1).hincrby(key, "%s_last_run_number" % name, 1)
        else:
            run_number = client.get_cache(db=1).incrby("%s_last_run_number" % name, 1)
	self.__name = '%s_%d' % (name, run_number)
        self.node = Node("scan", self.__name, parent=self.root_node)
      
    @property
    def name(self):
        return self.__name
    @property
    def path(self):
        return self.__path
    def set_path(self, path):
        self.__path = path

    def _acq_device_event(self, event_dict=None, signal=None, sender=None):
        print 'received', signal, 'from', sender, ":", event_dict
        if signal == 'end':
            for node in self.nodes.itervalues():
                node.set_ttl()
            self.node.set_ttl()
        node = self.nodes[sender]
        if event_dict is not None:
            node.store(event_dict) 

    def prepare(self, scan_info, devices_tree):
        parent_node = self.node
        prev_level = 0
        self.nodes = dict()
        
        devices_tree = list(sorted(devices_tree))
        for level, device_node in devices_tree:
            if prev_level != level:
                prev_level = level
                parent_node = self.nodes[device_node["parent"].master]

            acq_device = device_node.get("acq_device")
            if acq_device:
                self.nodes[acq_device] = get_node(acq_device.name, acq_device.type,
                                                  parent_node,create = True) 
                for signal in ('start', 'end', 'new_ref'):
                    dispatcher.connect(self._acq_device_event, signal, acq_device)
            master = device_node.get("master")
            if master:
                self.nodes[master] = get_node(master.name, master.type,
                                              parent_node,create = True)
        print self.nodes 



