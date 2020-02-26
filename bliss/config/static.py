# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Bliss static configuration

The next example will require a running bliss configuration server and
assumes the following YAML_ configuration is present:

.. literalinclude:: examples/config/motion.yml
    :language: yaml
    :caption: ./motion_example.yml

Accessing the configured elements from python is easy

.. code-block:: python
    :emphasize-lines: 1,4,7,11,18

    >>> from bliss.config.static import get_config

    >>> # access the bliss configuration object
    >>> config = get_config()

    >>> # see all available object names
    >>> config.names_list
    ['mock1', 'slit1', 's1f', 's1b', 's1u', 's1d', 's1vg', 's1vo', 's1hg', 's1ho']

    >>> # get a hold of motor 's1vo' configuration
    >>> s1u_config = config.get_config('s1u')
    >>> s1u_config
    Node([('name', 's1u')])
    >>> s1vo_config['velocity']
    500

    >>> # get a hold of motor 's1vo'
    >>> s1vo = config.get('s1vo')
    >>> s1vo
    <bliss.common.axis.Axis at 0x7f94de365790>
    >>> s1vo.position
    0.0

"""

import os
import gc
import re
import operator
import weakref
import collections
import types

import yaml
from yaml.loader import Reader, Scanner, Parser, Composer, SafeConstructor, Resolver

from bliss.config.conductor import client
from bliss.config import channels

CONFIG = None


def _find_dict(name, d):
    if d.get("name") == name:
        return d
    for key, value in d.items():
        if isinstance(value, dict):
            sub_dict = _find_dict(name, value)
        elif isinstance(value, list):
            sub_dict = _find_list(name, value)
        else:
            continue

        if sub_dict is not None:
            return sub_dict


def _find_list(name, l):
    for value in l:
        if isinstance(value, dict):
            sub_dict = _find_dict(name, value)
        elif isinstance(value, list):
            sub_dict = _find_list(name, value)
        else:
            continue
        if sub_dict is not None:
            return sub_dict


def _find_subconfig(d, path):
    _NotProvided = type("_NotProvided", (), {})()
    path = path.copy()
    key = path.pop(0)
    sub = d.get(key, _NotProvided)
    if sub == _NotProvided:
        return Node()
    if len(path) > 0:
        return _find_subconfig(sub, path)
    return sub


class BlissYamlResolver(Resolver):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        new_resolvers = collections.defaultdict(list)
        for k, resolver in self.__class__.yaml_implicit_resolvers.items():
            for item in resolver:
                tag, regexp = item
                if tag.endswith("2002:bool"):
                    regexp = re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$", re.X)
                new_resolvers[k].append((tag, regexp))
        self.__class__.yaml_implicit_resolvers = new_resolvers


class BlissSafeConstructor(SafeConstructor):
    bool_values = {"true": True, "false": False}


class BlissSafeYamlLoader(
    Reader, Scanner, Parser, Composer, BlissSafeConstructor, BlissYamlResolver
):
    def __init__(self, stream):
        Reader.__init__(self, stream)
        Scanner.__init__(self)
        Parser.__init__(self)
        Composer.__init__(self)
        BlissSafeConstructor.__init__(self)
        BlissYamlResolver.__init__(self)


def _replace_object_with_ref(obj):
    try:
        obj_name = obj.name
    except AttributeError:
        return False, obj
    else:
        config = get_config()
        if config._name2instance.get(obj_name):
            return True, f"${obj_name}"
        else:
            return False, obj


def _replace_list_node_with_ref(node_list):
    final_list = []
    for sub_node in node_list:
        if isinstance(sub_node, list):
            sub_list = _replace_list_node_with_ref(sub_node)
            final_list.append(sub_list)
        elif isinstance(sub_node, dict):
            _replace_node_with_ref(sub_node)
            final_list.append(sub_node)
        else:
            replaced, new_value = _replace_object_with_ref(sub_node)
            final_list.append(new_value if replaced else sub_node)
    return final_list


def _replace_node_with_ref(node):
    """
    replace all object with theirs references
    """
    for key, value in list(node.items()):
        replaced, new_value = _replace_object_with_ref(value)
        if replaced:
            node[key] = new_value
            continue

        if isinstance(value, dict):
            _replace_node_with_ref(value)
        elif isinstance(value, list):
            node[key] = _replace_list_node_with_ref(value)


def get_config(base_path="", timeout=3.):
    """
    Return configuration from bliss configuration server

    The first time the function is called, a new
    :class:`~bliss.config.static.Config` object is constructed and returned.
    Subsequent calls will return a cached object. Example::

        >>> from bliss.config.static import get_config

        >>> # access the bliss configuration object
        >>> config = get_config()

        >>> # see all available object names
        >>> config.names_list
        ['mock1', 'slit1', 's1f', 's1b', 's1u', 's1d', 's1vg', 's1vo', 's1hg', 's1ho']

        >>> # get a hold of motor 's1vo' configuration
        >>> s1u_config = config.get_config('s1u')
        >>> s1u_config
        Node([('name', 's1u')])
        >>> s1vo_config['velocity']
        500

    Args:
        base_path (str): base path to config
        timeout (float): response timeout (seconds)

    Returns:
        Config: the configuration object
    """
    global CONFIG
    if CONFIG is None:
        CONFIG = Config(base_path, timeout)
    return CONFIG


def get_config_dict(fullname, node_name):
    """Loads from file the node configuration
    as a dictionary
    """

    with client.remote_open(fullname) as f:
        d = yaml.safe_load(f.read())
    if isinstance(d, dict):
        d = _find_dict(node_name, d)
    elif isinstance(d, list):
        d = _find_list(node_name, d)
    else:
        d = None

    return d


class Node(dict):
    """
    Configuration Node. Do not instantiate this class directly.

    Typical usage goes throught :class:`~bliss.config.static.Config`.

    This class has a :class:`dict` like API::

        >>> from bliss.config.static import get_config

        >>> # access the bliss configuration object
        >>> config = get_config()

        >>> # get a hold of motor 's1vo' configuration
        >>> s1u_config = config.get_config('s1u')
        >>> s1u_config
        Node([('name', 's1u')])
        >>> s1vo_config['velocity']
        500
    """

    def __init__(self, config=None, parent=None, filename=None):
        super().__init__()
        self._parent = parent
        if config is None:
            config = CONFIG
        if config:
            self._config = weakref.proxy(config)
        config._create_file_index(self, filename)

    def __hash__(self):
        return id(self)

    @property
    def filename(self):
        """Filename where the configuration of this node is located"""
        return self.get_node_filename()[1]

    @property
    def parent(self):
        """Parent Node or None if it is the root Node"""
        return self._parent

    @property
    def children(self):
        """List of children Nodes"""
        return self.get("__children__")

    @property
    def plugin(self):
        """Active plugin name for this Node or None if no plugin active"""
        plugin = self.get("plugin")
        if plugin is None:
            if self == self._config._root_node:
                return
            if self._parent is not None:
                return self._parent.plugin
            return None
        else:
            return plugin

    def get_node_filename(self):
        """
        Returns the Node object corresponding to the filename where this Node
        is defined

        Returns:
           ~bliss.config.static.Node: the Node file object where this Node is
           defined
        """
        node = self if not hasattr(self, "_copied_from") else self._copied_from
        filename = self._config._node2file.get(node)
        if filename is not None:
            return self, filename
        elif self._parent is not None:
            return self._parent.get_node_filename()
        return None, None

    def get_inherited_value_and_node(self, key):
        """
        @see get_inherited
        """
        value = self.get(key)
        if value is None and self._parent:
            return self._parent.get_inherited_value_and_node(key)
        return value, self

    def get_inherited(self, key, default=None):
        """
        Returns the value for the given config key. If the key does not exist
        in this Node it is searched recusively up in the Node tree until it
        finds a parent which defines it

        Args:
            key (str): key to search

        Returns:
            object: value corresponding to the key or a default if key is not found
            in the Node tree and default is provied (None if no default)
        """
        value = self.get_inherited_value_and_node(key)[0]
        return value if value is not None else default

    def pprint(self, indent=1, depth=None):
        """
        Pretty prints this Node

        Keyword Args:
            indent (int): indentation level (default: 1)
            depth (int): max depth (default: None, meaning no max)
        """
        self._pprint(self, 0, indent, 0, depth)

    def save(self):
        """
        Saves the Node configuration persistently in the server
        """
        # Get the original node, synchronize it with
        # the copied one
        parent, filename = self.get_node_filename()
        if hasattr(self, "_copied_from"):
            # first copy to not modify
            copied_node = self.deep_copy()
            _replace_node_with_ref(copied_node)
            self._copied_from.clear()
            self._copied_from.update(copied_node)
        else:
            _replace_node_with_ref(self)

        if filename is None:
            return  # Memory
        nodes_2_save = self._config._file2node[filename]
        if len(nodes_2_save) == 1:
            node = tuple(nodes_2_save)[0]
            save_nodes = self._get_save_dict(node, filename)
        else:
            save_nodes = self._get_save_list(nodes_2_save, filename)
        file_content = yaml.dump(save_nodes, default_flow_style=False, sort_keys=False)
        self._config.set_config_db_file(filename, file_content)

    def deep_copy(self):
        """
        full copy of this node an it's children
        """
        node = Node()
        node._config = self._config
        node._parent = self._parent
        # keep source node in case of saving
        if hasattr(self, "_copied_from"):
            node._copied_from = self._copied_from
        else:
            node._copied_from = self
        for key, value in self.items():
            if isinstance(value, Node):
                child_node = value.deep_copy()
                node[key] = child_node
                child_node._parent = node
            elif isinstance(value, dict):
                child_node = Node()
                child_node.update(value)
                node[key] = child_node.deep_copy()
            elif isinstance(value, list):
                new_list = Node._copy_list(value, node)
                node[key] = new_list
            else:
                node[key] = value
        return node

    def to_dict(self):
        """
        full copy and transform all node to dict object.

        the return object is a simple dictionary
        """
        newdict = dict()
        for key, value in self.items():
            if isinstance(value, Node):
                child_dict = value.to_dict()
                newdict[key] = child_dict
            elif isinstance(value, list):
                new_list = Node._copy_list(value, self, dict_mode=True)
                newdict[key] = new_list
            else:
                newdict[key] = value
        return newdict

    @staticmethod
    def _copy_list(l, parent, dict_mode=False):
        new_list = list()
        for v in l:
            if isinstance(v, Node):
                if dict_mode:
                    new_node = v.to_dict()
                else:
                    new_node = v.deep_copy()
                    new_node._parent = parent
                new_list.append(new_node)
            elif isinstance(v, dict):
                tmp_node = Node()
                tmp_node.update(v)
                new_list.append(tmp_node.deep_copy().to_dict())
            elif isinstance(v, list):
                child_list = Node._copy_list(v, parent, dict_mode=dict_mode)
                new_list.append(child_list)
            else:
                new_list.append(v)
        return new_list

    def _get_save_dict(self, src_node, filename):
        return_dict = dict()
        for key, values in src_node.items():
            if isinstance(values, Node):
                if values.filename != filename:
                    continue
                return_dict[key] = self._get_save_dict(values, filename)
            elif isinstance(values, list):
                return_dict[key] = self._get_save_list(values, filename)
            else:
                return_dict[key] = values
        return return_dict

    def _get_save_list(self, l, filename):
        return_list = []
        for v in l:
            if isinstance(v, Node):
                if v.filename != filename:
                    break
                return_list.append(self._get_save_dict(v, filename))
            else:
                return_list.append(v)
        return return_list

    @staticmethod
    def _pprint(node, cur_indet, indent, cur_depth, depth):
        cfg = node._config
        space = " " * cur_indet
        print("%s{ filename: %r" % (space, cfg._node2file.get(node)))
        dict_space = " " * (cur_indet + 2)
        for k, v in node.items():
            print("%s%s:" % (dict_space, k), end=" ")
            if isinstance(v, Node):
                print()
                Node._pprint(v, cur_indet + indent, indent, cur_depth + 1, depth)
            elif isinstance(v, list):
                list_ident = cur_indet + indent
                list_space = " " * list_ident
                print("\n%s[" % list_space)
                for item in v:
                    if isinstance(item, Node):
                        print()
                        Node._pprint(
                            item, list_ident + indent, indent, cur_depth + 1, depth
                        )
                    else:
                        print(item)
                print("%s]" % list_space)
            else:
                print(v)
        print("%s}" % space)

    def __repr__(self):
        config = self._config
        value = dict.__repr__(self)
        # filename = config._node2file.get(self)
        return "filename:<%s>,plugin:%r,%s" % (
            self.filename,
            self.plugin,  # self.get("plugin"),
            value,
        )


class Config:
    """
    Bliss static configuration object.

    Typical usage is to call :func:`get_config` which will return an instance
    of this class.
    """

    #: key which triggers a YAML_ collection to be identified as a bliss named item
    NAME_KEY = "name"

    USER_TAG_KEY = "user_tag"

    def __init__(self, base_path, timeout=3, connection=None):
        self._base_path = base_path
        self._connection = connection or client.get_default_connection()
        self.reload(timeout=timeout)

    def close(self):
        self._clear_instances()
        channels.Bus.clear_cache()
        self._connection.close()

    def reload(self, base_path=None, timeout=3):
        """
        Reloads the configuration from the bliss server.

        Effectively cleans any cache (bliss objects and configuration tree)

        Keyword args:

            base_path (str): base path to config [default: empty string,
                             meaning full configuration]
            timeout (float): response timeout (seconds) [default: 3 seconds]

        Raises:
            RuntimeError: in case of connection timeout
        """
        if base_path is None:
            base_path = self._base_path

        self._name2node = weakref.WeakValueDictionary()
        self._usertag2node = {}
        self._root_node = Node(self)
        self._root_node["__children__"] = []
        self._node2file = weakref.WeakKeyDictionary()
        self._file2node = {}

        self._clear_instances()

        path2file = client.get_config_db_files(
            base_path=base_path, timeout=timeout, connection=self._connection
        )

        for path, file_content in path2file:
            if not file_content:
                continue
            base_path, file_name = os.path.split(path)
            fs_node, fs_key = self._get_or_create_path_node(base_path)
            if isinstance(fs_node, list):
                continue

            try:
                d = yaml.load(file_content, BlissSafeYamlLoader)
            except yaml.scanner.ScannerError as exp:
                exp.note = "Error in YAML parsing:\n"
                exp.note += "----------------\n"
                exp.note += f"{file_content}\n"
                exp.note += "----------------\n"
                exp.note += "Hint: You can check your configuration with an on-line YAML validator like http://www.yamllint.com/ \n\n"
                exp.problem_mark.name = path
                raise exp
            except yaml.error.MarkedYAMLError as exp:
                if exp.problem_mark is not None:
                    exp.problem_mark.name = path
                raise

            is_init_file = False
            if file_name.startswith("__init__"):
                _, last_path = os.path.split(base_path)
                is_init_file = not last_path.startswith("@")

            if is_init_file:
                if d is None:
                    continue

                parents = Node(self, fs_node if fs_key else None, path)
                parents["__children__"] = []
                # do not accept a list in case of __init__ file
                if isinstance(d, list):
                    raise TypeError("List are not allowed in *%s* file" % path)
                try:
                    self._parse(d, parents)
                except TypeError:
                    _msg = "Parsing error1 on %s in '%s'" % (self._connection, path)
                    raise RuntimeError(_msg)

                if not fs_key:
                    self._root_node = parents
                else:
                    fs_node[fs_key] = parents
                continue
            else:
                if isinstance(d, list):
                    parents = []
                    for item in d:
                        local_parent = Node(self, fs_node, path)
                        try:
                            self._parse(item, local_parent)
                        except TypeError:
                            _msg = "Parsing error2 on %s in '%s'" % (
                                self._connection,
                                path,
                            )
                            raise RuntimeError(_msg)
                        self._create_index(local_parent)
                        parents.append(local_parent)
                else:
                    parents = Node(self, fs_node, path)
                    try:
                        self._parse(d, parents)
                    except TypeError:
                        _msg = "Parsing error3 on %s in '%s'" % (self._connection, path)
                        raise RuntimeError(_msg)
                    self._create_index(parents)

            if isinstance(fs_node, list):
                continue
            elif fs_key == "":
                children = fs_node
            else:
                children = fs_node.get(fs_key)

            if isinstance(children, list):
                if isinstance(parents, list):
                    children.extend(parents)
                else:
                    children.append(parents)
            elif children is not None:
                # check if this node is __init__
                children_node = children.get("__children__")
                if isinstance(children_node, list):  # it's an init node
                    if isinstance(parents, list):
                        for p in parents:
                            p._parent = children
                            children_node.append(p)
                    else:
                        parents._parent = children
                        children_node.append(parents)
                else:
                    if isinstance(parents, list):
                        parents.append(children)
                        fs_node[fs_key] = parents
                    else:
                        fs_node[fs_key] = [children, parents]
            else:
                fs_node[fs_key] = parents
        while gc.collect():
            pass

    @property
    def names_list(self):
        """
        List of existing configuration names

        Returns:
            list<str>: sequence of configuration names
        """
        return sorted(list(self._name2node.keys()))

    @property
    def user_tags_list(self):
        """
        List of existing user tags

        Returns:
            list<str>: sequence of user tag names
        """
        return sorted(list(self._usertag2node.keys()))

    @property
    def root(self):
        """
        Reference to the root :class:`~bliss.config.static.Node`
        """
        return self._root_node

    def set_config_db_file(self, filename, content):
        """
        Update the server filename with the given content

        Args:
            filename (str): YAML_ file name (path relative to configuration
                            base directory. Example: motion/icepap.yml)
            content (str): configuration content

        Raises:
            RuntimeError: in case of connection timeout
        """

        full_filename = os.path.join(self._base_path, filename)
        client.set_config_db_file(full_filename, content, connection=self._connection)

    def _create_file_index(self, node, filename):
        if filename:
            self._node2file[node] = filename
            weak_set = self._file2node.setdefault(filename, weakref.WeakSet())
            weak_set.add(node)

    def _get_or_create_path_node(self, base_path):
        node = self._root_node
        sp_path = base_path.split(os.path.sep)
        if sp_path[-1].startswith("@"):
            sp_path.pop()

        for i, p in enumerate(sp_path[:-1]):
            if p.startswith("@"):
                rel_init_path = os.path.join(*sp_path[: i + 1])
                init_path = os.path.join(rel_init_path, "__init__.yml")
                for c in self._file2node.get(init_path, []):
                    child = c
                    break
            else:
                try:
                    child = node.get(p)
                except AttributeError:
                    # because it's a list and we need a dict (reparent)
                    gp = node[0].parent
                    parent = Node(self, gp)
                    for c in node:
                        c._parent = parent
                    gp[sp_path[i - 1]] = gp
                    node = gp
                    child = None

            if child is None:
                child = Node(self, node)
                node[p] = child
            node = child

        sp_path = [x for x in sp_path if not x.startswith("@")]

        return node, sp_path and sp_path[-1]

    def get_config(self, name):
        """
        Returns the config :class:`~bliss.config.static.Node` with the
        given name

        Args:
            name (str): config node name

        Returns:
            ~bliss.config.static.Node: config node or None if object is
            not found
        """
        # '$' means the item is a reference
        name = name.lstrip("$")
        return self._name2node.get(name)

    def get_user_tag_configs(self, tag_name):
        """
        Returns the set of config nodes (:class:`~bliss.config.static.Node`)
        which have the given user *tag_name*.

        Args:
            tag_name (str): user tag name

        Returns:
            set<Node>: the set of nodes wich have the given user tag
        """
        return set(self._usertag2node.get(tag_name, ()))

    def get(self, name):
        """
        Returns an object instance from its configuration name

        If names starts with *$* it means it is a reference.

        Args:
            name (str): config node name

        Returns:
            ~bliss.config.static.Node: config node

        Raises:
            RuntimeError: if name is not found in configuration
        """

        base_name, sep, remains = name.partition(".")
        if remains:
            obj = self.get(base_name)
            return operator.attrgetter(remains)(obj)

        if name is None:
            raise TypeError("Cannot get object with None name")

        name = name.lstrip("$")
        instance_object = self._name2instance.get(name)
        if instance_object is None:  # we will create it
            config_node = self.get_config(name)
            if config_node is None:
                raise RuntimeError("Object '%s' doesn't exist in config" % name)

            module_name = config_node.plugin
            if module_name is None:
                module_name = "default"
            m = __import__("bliss.config.plugins.%s" % (module_name), fromlist=[None])
            if hasattr(m, "create_object_from_cache"):
                cache_object = self._name2cache.pop(name, None)
                if cache_object is not None:
                    cache_func = getattr(m, "create_object_from_cache")
                    instance_object = cache_func(self, name, cache_object)
                    self._name2instance[name] = instance_object

            if instance_object is None:
                func = getattr(m, "create_objects_from_config_node")
                return_value = func(self, config_node)
                if isinstance(return_value, types.GeneratorType):
                    iteration = iter(return_value)
                else:
                    iteration = [return_value]

                for name2itemsAndname2itemcache in iteration:
                    if (
                        isinstance(name2itemsAndname2itemcache, (tuple, list))
                        and len(name2itemsAndname2itemcache) == 2
                    ):
                        name2items = name2itemsAndname2itemcache[0]
                        name2itemcache = name2itemsAndname2itemcache[1]
                        self._name2cache.update(name2itemcache)
                    else:
                        name2items = name2itemsAndname2itemcache
                    self._name2instance.update(name2items)

        return self._name2instance.get(name)

    def _create_index(self, node):
        name = node.get(self.NAME_KEY)
        if name is not None and not name.startswith("$"):
            if name in self._name2node:
                prev_node = self.get_config(name)
                raise ValueError(
                    "Duplicate key name (%s) in config files "
                    "(%s) and (%s)" % (name, prev_node.filename, node.filename)
                )
            else:
                self._name2node[name] = node

        user_tags = node.get(self.USER_TAG_KEY)
        if user_tags is not None:
            if not isinstance(user_tags, list):
                user_tags = [user_tags]
            for tag in user_tags:
                l = self._usertag2node.get(tag)
                if l is None:
                    self._usertag2node[tag] = weakref.WeakSet([node])
                else:
                    l.add(node)

    def _parse_list(self, l, parent):
        r_list = []
        for value in l:
            if isinstance(value, dict):
                node = Node(self, parent)
                self._parse(value, node)
                self._create_index(node)
                r_list.append(node)
            elif isinstance(value, list):
                child_list = self._parse_list(value, parent)
                r_list.append(child_list)
            else:
                r_list.append(value)
        return r_list

    def _parse(self, d, parent):
        if d is None:
            raise RuntimeError("Error parsing %r" % parent)
        else:
            for key, value in d.items():
                if isinstance(value, dict):
                    node = Node(self, parent=parent)
                    self._parse(value, node)
                    self._create_index(node)
                    parent[key] = node
                elif isinstance(value, list):
                    parent[key] = self._parse_list(value, parent)
                else:
                    parent[key] = value

    def _clear_instances(self):
        self._name2instance = weakref.WeakValueDictionary()
        self._name2cache = dict()

    def pprint(self, indent=1, depth=None):
        self.root.pprint(indent=indent, depth=depth)

    def __str__(self):
        return "{0}({1})".format(self.__class__.__name__, self._connection)
