import os
import yaml
import weakref
if not hasattr(weakref, "WeakSet"):
    import weakrefset
    weakref.WeakSet = weakrefset.WeakSet
from .conductor import client

CONFIG = None

def load_cfg(filename):
    cfg_string = client.get_config_file(filename)
    return yaml.load(cfg_string)

def load_cfg_fromstring(cfg_string):
   return yaml.load(cfg_string)

def get_config(base_path='',timeout=3.):
    global CONFIG
    if CONFIG is None:
        CONFIG = Config(base_path, timeout)
    return CONFIG


class Config(object):
    NAME_KEY = 'name'
    USER_TAG_KEY = 'user_tag'

    class Node(dict):
        def __init__(self,config,parent = None,filename = None) :
            dict.__init__(self)
            self._parent = parent
            self._config = weakref.ref(config)
            config._create_file_index(self,filename)

        def __hash__(self):
            return id(self)

        @property
        def filename(self) :
            return self.get_node_filename()[1]

        @property
        def parent(self):
            return self._parent

        @property
        def children(self):
            return self.get('__children__')

        @property
        def plugin(self):
            """Return plugin name"""
            plugin = self.get("plugin")
            if plugin is None:
              if self._parent is not None:
                  return self._parent.plugin
              else:
                  return None
            else:
                return plugin

        def get_node_filename(self) :
            config = self._config()
            filename = config._node2file.get(self)
            if filename is not None:
                return self,filename
            elif self._parent is not None:
                return self._parent.get_node_filename()
            else:
                return None,None
 
        def get_inherited(self,key):
            value = self.get(key)
            if value is None and self._parent:
                return self._parent.get_inherited(key)
            return value

        def pprint(self,indent=1, depth = None) :
            self._pprint(self,0,indent,0,depth)
        
        @staticmethod
        def _pprint(node,cur_indet,indent,cur_depth,depth) :
            cfg = node._config()
            space = ' ' * cur_indet
            print '%s{ filename: %r' % (space,cfg._node2file.get(node))
            dict_space = ' ' * (cur_indet + 2)
            for k,v in node.iteritems():
                print '%s%s:' % (dict_space,k),
                if isinstance(v,Config.Node) :
                    print
                    Config.Node._pprint(v,cur_indet + indent,indent,
                                        cur_depth + 1,depth)
                elif isinstance(v,list):
                    list_ident = cur_indet + indent
                    list_space = ' ' * list_ident
                    print '\n%s[' % list_space
                    for item in v:
                        if isinstance(item,Config.Node) :
                            print
                            Config.Node._pprint(item,list_ident + indent,indent,
                                                cur_depth + 1,depth)
                        else:
                            print item
                    print '%s]' % list_space
                else:
                    print v
            print '%s}' % space

        def __repr__(self):
            config = self._config()
            value = dict.__repr__(self)
            filename = config._node2file.get(self)
            return 'filename:<%s>,plugin:%r,%s' % (filename,
                                                   self.get("plugin"),
                                                   value)

    def __init__(self, base_path, timeout=3):
        self._name2node = weakref.WeakValueDictionary()
        self._usertag2node = {}
        self._root_node = Config.Node(self)
        self._name2instance = {}
        self._name2cache = {}
        self._node2file = weakref.WeakKeyDictionary()
        self._file2node = {}
        self._base_path = base_path
       
        self.reload(timeout=timeout)

    def reload(self, base_path=None, timeout=3):
        if base_path is None:
            base_path = self._base_path

        self._clear_instances()

        path2file = client.get_config_db_files(base_path = base_path,
                                               timeout = timeout)

        for path, file_content in path2file:
            base_path, file_name = os.path.split(path)
            fs_node, fs_key = self._get_or_create_path_node(base_path)

            d = yaml.load(file_content)
            is_init_file = False
            if file_name.startswith('__init__'):
                _,last_path = os.path.split(base_path)
                is_init_file = not last_path.startswith('@')

            if is_init_file:
                if not fs_key:
                    parents = self._root_node
                else:
                    parents = fs_node.get(fs_key)

                if isinstance(parents,list):
                    new_node = self.Node(self,fs_node,path)
                    for n in parents:
                        n._parent = new_node
                    new_node['__children__'] = parents
                    parents = new_node
                elif parents:
                    new_node = self.Node(self,fs_node,path)
                    parents._parent = new_node
                    new_node['__children__'] = [parents]
                    parents = new_node
                elif parents is None:
                    parents = self.Node(self,fs_node,path)
                    parents['__children__'] = []
                else:
                    parents['__children__'] = []
                    self._create_file_index(parents,path)
                if not fs_key:
                    self._root_node = parents
                else:
                    fs_node[fs_key] = parents
                # do not accept a list in case of __init__ file
                self._parse(d,parents)
                continue
            else:
                if isinstance(d,list):
                    parents = []
                    for item in d:
                        local_parent = Config.Node(self,fs_node,path)
                        self._parse(item,local_parent)
                        self._create_index(local_parent)
                        parents.append(local_parent)
                else:
                    parents = Config.Node(self,fs_node,path)
                    self._parse(d,parents)
                    self._create_index(parents)
            
            children = fs_node.get(fs_key)
            
            if isinstance(children,list):
                if isinstance(parents,list):
                    children.extend(parents)
                else:
                    children.append(parents)
            elif children is not None:
                #check if this node is __init__
                children_node = children.get('__children__')
                if isinstance(children_node,list): # it's an init node
                    if isinstance(parents,list):
                        for p in parents:
                            p._parent = children
                            children_node.append(p)
                    else:
                        parents._parent = children
                        children_node.append(parents)
                else:
                    if isinstance(parents,list):
                        parents.append(children)
                        fs_node[fs_key] = parents
                    else:
                        fs_node[fs_key] = [children,parents]
            else:
                fs_node[fs_key] = parents

    @property
    def names_list(self):
        return self._name2node.keys()

    @property
    def root(self):
        return self._root_node

    def _create_file_index(self,node,filename) :
        if filename:
            self._node2file[node] = filename
            weak_set = self._file2node.get(filename)
            if weak_set is None:
                weak_set = weakref.WeakSet()
                self._file2node[filename] = weak_set
            weak_set.add(node)

    def _get_or_create_path_node(self, base_path):
        node = self._root_node
        sp_path = base_path.split(os.path.sep)
        if sp_path[-1].startswith('@'): sp_path.pop()
            
        for i,p in enumerate(sp_path[:-1]):
            if p.startswith('@'):
                rel_init_path = os.path.join(*sp_path[:i + 1])
                init_path = os.path.join(rel_init_path,'__init__.yml')
                for c in self._file2node.get(init_path,[]):
                    child = c
                    break
            else:
                try:
                    child = node.get(p)
                except AttributeError:
                    #because it's a list and we need a dict (reparent)
                    gp = node[0].parent
                    parent = self.Node(self,gp)
                    for c in node:
                        c._parent = parent
                    gp[sp_path[i - 1]] = gp
                    node = gp
                    child = None

            if child is None:
                child = Config.Node(self,node)
                node[p] = child
            node = child

        sp_path = [x for x in sp_path if not x.startswith('@')]

        return node, sp_path and sp_path[-1]

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
                raise RuntimeError("Object '%s` doesn't exist in config" % name)

            module_name = config_node.plugin

            m = __import__('bliss.config.plugins.%s' % (module_name),fromlist=[None])

            if hasattr(m, "create_object_from_cache"):
                cache_object = self._name2cache.pop(name,None)
                if cache_object is not None:
                    cache_func = getattr(m,'create_object_from_cache')
                    instance_object = cache_func(self, name, cache_object)
                    self._name2instance[name] = instance_object
                
            if instance_object is None:
                func = getattr(m,'create_objects_from_config_node')
                name2itemsAndname2itemcache = func(self, config_node)
                if len(name2itemsAndname2itemcache) == 2:
                    name2items = name2itemsAndname2itemcache[0]
                    name2itemcache = name2itemsAndname2itemcache[1]
                    self._name2cache.update(name2itemcache)
                else:
                    name2items = name2itemsAndname2itemcache
                self._name2instance.update(name2items)
                instance_object = name2items.get(name)

        return instance_object

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

    def _parse_list(self,l,parent):
        r_list = []
        for value in l:
            if isinstance(value,dict):
                node = Config.Node(self,parent)
                self._parse(value,node)
                self._create_index(node)
                r_list.append(node)
            elif isinstance(value,list):
                child_list = self._parse_list(value)
                r_list.append(child_list)
            else:
                r_list.append(value)
        return r_list

    def _parse(self,d,parent) :
        for key,value in d.iteritems():
            if isinstance(value,dict):
                node = Config.Node(self,parent = parent)
                self._parse(value,node)
                self._create_index(node)
                parent[key] = node
            elif isinstance(value,list):
                parent[key] = self._parse_list(value,parent)
            else:
                parent[key] = value

    def _clear_instances(self):
        self._name2instance = dict()
        self._name2cache = dict()

