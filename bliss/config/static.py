import os
import yaml
import weakref
from .conductor.client import Client

def load_cfg(filename):
    cfg_string = Client.get_config_file(filename)
    return yaml.load(cfg_string)

def load_cfg_fromstring(cfg_string):
   return yaml.load(cfg_string)

def get_config(base_path='',timeout=30.):
    path2file = Client.get_config_db_files(base_path = base_path,
                                           timeout = timeout)
    config = Config(path2file)
    return config

class Config(object):
    NAME_KEY = 'name'
    USER_TAG_KEY = 'user_tag'
    NAMESPACE_CONVERSION = {}

    class Node(dict):
        def __init__(self,parent = None,namespace = None,filename = None) :
            super(Config.Node, self).__init__()
            self._parent = parent
            self._filename = filename
            self._namespace = namespace

        def __repr__(self) :
            value = super(Config.Node,self).__repr__()
            return 'filename:<%s>,namespace:<%s>,%s' % (self.get_filename(),
                                                        self.get_namespace(),
                                                        value)

        def get_filename(self) :
            _,filename = self.get_node_filename()
            return filename

        def get_node_filename(self):
            if self._filename is not None:
                return self,self._filename
            elif self._parent is not None:
                return self._parent.get_node_filename()
            else:
                return None,None

        def get_namespace(self) :
            _,namespace = self.get_node_namespace()
            return namespace

        def get_node_namespace(self) :
            if self._namespace is not None:
                return self,self._namespace
            elif self._parent is not None:
                return self._parent.get_node_namespace()
            else:
                return None,None

        def get_parent(self) :
            return self._parent

    def __init__(self,path2file):
        self._name2node = weakref.WeakValueDictionary()
        self._usertag2node = {}
        self._root_node = self.Node()
        self._name2instance = {}
        self._name2cache = {}

        for path,file_content in path2file:
            base_path,file_name = os.path.split(path)
            path_node,namespace = self._get_or_create_path_node(base_path,file_name)
            d = yaml.load(file_content)
            parent = self.Node(path_node,namespace,path)
            if isinstance(d, list):
                child_list = self._pars_list(d,parent)
		parent[id(child_list)] = child_list
            else:
                self._pars(d,parent)
            self._create_index(parent)
            
            children = path_node.get(namespace)
            
            if isinstance(children,list):
                children.append(parent)
            elif children is not None:
                path_node[namespace] = [children,parent]
            else:
                path_node[namespace] = parent

    @property
    def names_list(self):
        return self._name2node.keys()

    ##@brief return the config node with it's name
    #
    def get_config(self, name):
        return self._name2node.get(name)

    ##@brief return an instance with it's name
    #
    def get(self,name):
        # '$' means the item is a reference
        name = name.lstrip('$')
        instance_object = self._name2instance.get(name)
        if instance_object is None: # we will create it
            config_node = self.get_config(name)
            if config_node is None:
                raise RuntimeError("Object %s doesn't exist in config")
            namespace = config_node.get_namespace()
            module_name = self.NAMESPACE_CONVERSION.get(namespace,namespace)
            try:
                m = __import__('bliss.config.plugins.%s' % (module_name),None,None,
                               'bliss.config.plugins.%s' % (module_name))
            except ImportError:
                raise RuntimeError("Couldn't import plugins.%s" % module_name)
            else:
                try:
                    cache_func = getattr(m,'create_object_from_cache')
                except AttributeError: 
                    pass
                else:
                    cache_object = self._name2cache.pop(name,None)
                    if cache_object is not None:
                        instance_object = cache_func(name,cache_object)

                if instance_object is None:
                    try:
                        func = getattr(m,'create_objects_from_config_node')
                    except AttributeError:
                        raise RuntimeError("Module %s doesn't have create_objects_from_config_node function" % module)
                    else:
                        name2itemsAndname2itemcache = func(config_node)
                        if len(name2itemsAndname2itemcache) == 2:
                            name2items = name2itemsAndname2itemcache[0]
                            name2itemcache = name2itemsAndname2itemcache[1]
                            self._name2cache.update(name2itemcache)
                        else:
                            name2items = name2itemsAndname2itemcache

                        instance_object = name2items.get(name)
                        self._name2instance.update(name2items)
                else:
                    self._name2instance[name]=instance_object
        return instance_object

    def _get_or_create_path_node(self,base_path,file_name):
        path = os.path.normpath(base_path)
        sp_path = path.split(os.path.sep)
        if file_name.startswith('__root__'): sp_path.pop(-1)
        node = self._root_node
        has_namespace = True
        for p in sp_path[:-1]:
            try:
                child = node.get(p)
                has_namespace = True
            except AttributeError: # in case of file split
                for subnode in node:
                    file_name = subnode.get_filename()
                    if file_name.find(p) > -1:
                        child = subnode
                        has_namespace = False
                        break
            if child is None:
                child = self.Node()
                node[p] = child
            node = child
        return node,has_namespace and sp_path[-1] or None

    def _create_index(self,node) :
        name = node.get(self.NAME_KEY)
        if name is not None and not name.startswith("$"):
            if name in self._name2node:
                pass    # should raise an error name duplicate
            else:
                self._name2node[name] = node

        user_tags = node.get(self.USER_TAG_KEY)
        if user_tags is not None:
            if not isinstance(user_tags,list):
                user_tags = [user_tags]
            for tag in user_tags:
                l = self._usertag2node.get(tag)
                if l is None:
                    self._usertag2node[tag] = weakref.WeakSet([node])
                else:
                    l.add(node)

    def _pars_list(self,l,parent):
        r_list = []
        for value in l:
            if isinstance(value,dict):
                node = self.Node(parent = parent)
                self._pars(value,node)
                self._create_index(node)
                r_list.append(node)
            elif isinstance(value,list):
                child_list = self._pars_list(value)
                r_list.append(child_list)
            else:
                r_list.append(value)
        return r_list

    def _pars(self,d,parent) :
        for key,value in d.iteritems():
            if isinstance(value,dict):
                node = self.Node(parent = parent)
                self._pars(value,node)
                self._create_index(node)
                parent[key] = node
            elif isinstance(value,list):
                parent[key] = self._pars_list(value,parent)
            else:
                parent[key] = value
