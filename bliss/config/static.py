# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
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
    ConfigNode([('name', 's1u')])
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
import json
import types
import pickle
import weakref
import operator
import hashlib
from collections import defaultdict
from collections.abc import MutableMapping, MutableSequence

import ruamel
from ruamel.yaml import YAML
from ruamel.yaml.compat import StringIO

from bliss.config.conductor import client
from bliss.config import channels
from bliss.common.utils import prudent_update, Singleton
from bliss import global_map
from bliss.comm import service


def get_config(base_path="", timeout=3., raise_yaml_exc=True):
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
        ConfigNode([('name', 's1u')])
        >>> s1vo_config['velocity']
        500

    Args:
        base_path (str): base path to config
        timeout (float): response timeout (seconds)
        raise_yaml_exc (bool): if False will not raise exceptions related
                         to yaml parsing and config nodes creation

    Returns:
        Config: the configuration object
    """
    return Config(base_path, timeout, raise_yaml_exc=raise_yaml_exc)


class ConfigReference:
    @staticmethod
    def is_reference(name):
        if isinstance(name, str):
            return name.startswith("$")
        return False

    def __init__(self, parent, value):
        self._parent = parent
        ref, _, attr = value.lstrip("$").partition(".")
        self._object_name = ref
        self._attr = attr

    def __getstate__(self):
        return {
            "object_name": self.object_name,
            "attr": self.attr,
            "parent": self._parent,
        }

    def __setstate__(self, d):
        self._object_name = d["object_name"]
        self._attr = d["attr"]
        self._parent = d["parent"]

    def __eq__(self, other):
        if isinstance(other, ConfigReference):
            return self._object_name == other._object_name and self._attr == other._attr
        else:
            return False

    @property
    def object_name(self):
        return self._object_name

    @property
    def attr(self):
        return self._attr

    def dereference(self):
        obj = self._parent.config.get(self.object_name)
        alias = global_map.aliases.get_alias(obj)
        if alias:
            obj = global_map.aliases.get(alias)
        if self.attr:
            return operator.attrgetter(self.attr)(obj)
        return obj

    def encode(self):
        if self.attr:
            return f"${self.object_name}.{self.attr}"
        else:
            return f"${self.object_name}"


class ConfigList(MutableSequence):
    def __init__(self, parent):
        self._data = []
        self._parent = parent

    def __getstate__(self):
        return {"data": self._data, "parent": self._parent}

    def __setstate__(self, d):
        self._data = d["data"]
        self._parent = d["parent"]

    @property
    def raw_list(self):
        return self._data

    def __eq__(self, other):
        if isinstance(other, ConfigList):
            return self.raw_list == other.raw_list
        else:
            if isinstance(other, MutableSequence):
                return list(other) == list(self)
            return False

    def __getitem__(self, key):
        value = self._data[key]
        if isinstance(value, ConfigReference):
            return value.dereference()
        return value

    def __len__(self):
        return len(self._data)

    def __setitem__(self, key, value):
        self._data[key] = convert_value(value, self._parent)

    def __delitem__(self, key):
        del self._data[key]

    def __repr__(self):
        return repr(self._data)

    def encode(self):
        return self._data

    def insert(self, index, value):
        self._data.insert(index, convert_value(value, self._parent))


def convert_value(value, parent):
    """Convert value to a ConfigReference, a config node or a config list with the given parent

    Scalars, or values with the right type, are just returned as they are
    """
    if value is None or isinstance(
        value, (ConfigReference, ConfigNode, ConfigList, bool, int, float)
    ):
        pass
    else:
        if isinstance(value, str):
            if ConfigReference.is_reference(value):
                value = ConfigReference(parent, value)
        else:
            if isinstance(value, dict):
                new_node = ConfigNode(parent)
                build_nodes_from_dict(value, new_node)
                value = new_node
            elif isinstance(value, list):
                value = build_nodes_from_list(value, parent)
            else:
                # a custom object from bliss? => make a reference
                try:
                    obj_name = value.name
                except AttributeError:
                    raise ValueError(f"Cannot make a reference to object {value}")
                if obj_name in parent.config.names_list:
                    value = ConfigReference(parent, obj_name)
                else:
                    raise ValueError(f"Cannot make a reference to object {value}")
    return value


class ConfigNode(MutableMapping):
    """
    Configuration ConfigNode. Do not instantiate this class directly.

    Typical usage goes through :class:`~bliss.config.static.Config`.

    This class has a :class:`dict` like API
    """

    # key which triggers a YAML_ collection to be identified as a bliss named item
    NAME_KEY = "name"
    USER_TAG_KEY = "user_tag"
    RPC_SERVICE_KEY = "service"

    indexed_nodes = weakref.WeakValueDictionary()
    tagged_nodes = defaultdict(weakref.WeakSet)
    services = weakref.WeakSet()

    @staticmethod
    def reset_cache():
        ConfigNode.indexed_nodes = weakref.WeakValueDictionary()
        ConfigNode.tagged_nodes = defaultdict(weakref.WeakSet)
        ConfigNode.services = weakref.WeakSet()

    @staticmethod
    def goto_path(d, path_as_list, key_error_exception=True):
        path_in_dict = path_as_list[:]
        while path_in_dict:
            try:
                d = d[path_in_dict.pop(0)]
            except KeyError:
                if key_error_exception:
                    raise
                else:
                    return ConfigNode(d)  # return a new config node, with 'd' as parent
        return d

    def __init__(self, parent=None, filename=None, path=None):
        self._data = {}
        self._parent = parent
        self._filename = filename
        self._path = path

    def raw_get(self, key):
        return self._data.get(key)

    def raw_items(self):
        return self._data.items()

    def get(self, key, default=None):
        if key in self._data:
            return self[key]
        else:
            return default

    def encode(self):
        return self._data

    def md5hash(self):
        """Return md5 hex digest of the config node

        Uses internal config dict to build the hash, so
        two nodes with same digest represent the exact same config
        """
        return hashlib.md5(str(self._data).encode()).hexdigest()

    def reparent(self, new_parent_node):
        self._parent = new_parent_node

    def reload(self):
        with client.remote_open(self.filename) as f:
            yaml = YAML(pure=True)
            yaml.allow_duplicate_keys = True
            d = ConfigNode.goto_path(yaml.load(f.read()), self.path)
            self._data = {}
            for k, v in d.items():
                self[k] = v

    @property
    def config(self):
        return self.root.config

    @property
    def root(self):
        root = self
        while root.parent:
            root = root.parent
        return root

    @property
    def path(self):
        """Return a list to access the node in the list+dictionaries from the YAML file parsing
        """
        parent_path = []
        if self.parent:
            if self.parent.filename == self.filename:
                parent_path = self.parent.path
        # return a copy of the path
        return list(parent_path + self._path if self._path is not None else [])

    def __getstate__(self):
        return {
            "data": self._data,
            "parent": self._parent,
            "filename": self._filename,
            "path": self._path,
        }

    def __setstate__(self, d):
        self._data = d["data"]
        self._parent = d["parent"]
        self._filename = d["filename"]
        self._path = d["path"]

    def __eq__(self, other):
        if isinstance(other, ConfigNode):
            return dict(self.raw_items()) == dict(other.raw_items())
        elif isinstance(other, MutableMapping):
            return dict(other) == dict(self)
        else:
            return False

    def __getitem__(self, key):
        """Return value if it is not a reference, otherwise evaluate and return the reference value
        """
        value = self._data[key]
        if isinstance(value, ConfigReference):
            return value.dereference()
        return value

    def __setitem__(self, key, value):
        if key == ConfigNode.NAME_KEY:
            # need to index this node
            node = self
            name = value
            if name is None or not isinstance(name, str) or name[:1].isdigit():
                raise ValueError(
                    f"Invalid name {name} in file ({node.filename}). Must start with [a-zA-Z_]"
                )
            if ConfigReference.is_reference(name):
                # a name must be a string, or a direct reference to an object in config
                assert "." not in name
            else:
                if name in ConfigNode.indexed_nodes:
                    existing_node = ConfigNode.indexed_nodes[name]
                    if existing_node.filename == self.filename:
                        pass
                    else:
                        raise ValueError(
                            f"Duplicated name {name}, already in {existing_node.filename}"
                        )
                else:
                    ConfigNode.indexed_nodes[name] = node
        elif key == ConfigNode.USER_TAG_KEY:
            node = self
            user_tags = value if isinstance(value, MutableSequence) else [value]
            for tag in user_tags:
                ConfigNode.tagged_nodes[tag].add(node)
        elif key == ConfigNode.RPC_SERVICE_KEY:
            ConfigNode.services.add(self)
        self._data[key] = convert_value(value, self)

    def setdefault(self, key, value):
        """Re-implement 'setdefault' to not return value but element of the
        dict (once it is inserted).
        """
        try:
            return self[key]
        except KeyError:
            self[key] = value
            return self[key]

    def __delitem__(self, key):
        del self._data[key]

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)

    def __hash__(self):
        return id(self)

    @property
    def filename(self):
        """Filename where the configuration of this node is located"""
        filename = self._filename
        if filename is None:
            if self._parent:
                return self._parent.filename
        return filename

    @property
    def parent(self):
        """Parent Node"""
        return self._parent

    @property
    def children(self):
        """List of children Nodes"""
        return self.get("__children__")

    @property
    def plugin(self):
        """Active plugin name for this Node or None if no plugin active"""
        plugin = self.get("plugin")
        if plugin:
            return plugin
        else:
            try:
                return self._parent.plugin
            except AttributeError:
                return  # no parent == root node, no plugin

    @property
    def is_service(self):
        """Is this node is serve with a rpc server"""
        through_server = self in ConfigNode.services
        if through_server is False and self._parent:
            return self._parent.is_service
        return through_server

    def get_top_key_node(self, key):
        topnode = None
        node = self
        while True:
            if node.get(key):
                topnode = node
            node = node._parent
            if node is None or "__children__" in node.keys():
                break
        return topnode

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
        filename = self.filename

        if filename is None:
            return  # Memory

        yaml = YAML(pure=True)
        yaml.allow_duplicate_keys = True
        yaml.default_flow_style = False
        try:
            yaml_contents = yaml.load(
                client.get_text_file(filename, self.config._connection)
            )
        except RuntimeError:
            # file does not exist
            yaml_contents = self.to_dict(resolve_references=False)
        else:
            prudent_update(
                ConfigNode.goto_path(yaml_contents, self.path),
                self.to_dict(resolve_references=False),
            )

        string_stream = StringIO()
        yaml.dump(yaml_contents, stream=string_stream)
        file_content = string_stream.getvalue()
        self.config.set_config_db_file(filename, file_content)

    def clone(self):
        """
        return a full copy of this node
        """
        node = pickle.loads(pickle.dumps(self, protocol=-1))
        # keep source node in case of saving
        return node

    def to_dict(self, resolve_references=True):
        """
        full copy and transform to dict object.

        the return object is a simple dictionary
        """
        if resolve_references:

            def decoder_hook(d):
                for k, v in d.items():
                    if isinstance(v, str) and ConfigReference.is_reference(v):
                        d[k] = ConfigReference(self.parent, v).dereference()
                    elif isinstance(v, list):
                        d[k] = [
                            ConfigReference(self.parent, item).dereference()
                            if ConfigReference.is_reference(item)
                            else item
                            for item in v
                        ]
                return d

            return json.JSONDecoder(object_hook=decoder_hook).decode(
                json.dumps(self._data, cls=ConfigNodeDictEncoder)
            )
        else:
            return json.loads(json.dumps(self._data, cls=ConfigNodeDictEncoder))

    @staticmethod
    def _pprint(node, cur_indet, indent, cur_depth, depth):
        space = " " * cur_indet
        print(f"{space}{{ filename: {repr(node.filename)}")
        dict_space = " " * (cur_indet + 2)
        for k, v in node.items():
            print("%s%s:" % (dict_space, k), end=" ")
            if isinstance(v, ConfigNode):
                print()
                ConfigNode._pprint(v, cur_indet + indent, indent, cur_depth + 1, depth)
            elif isinstance(v, MutableSequence):
                list_ident = cur_indet + indent
                list_space = " " * list_ident
                print("\n%s[" % list_space)
                for item in v:
                    if isinstance(item, ConfigNode):
                        print()
                        ConfigNode._pprint(
                            item, list_ident + indent, indent, cur_depth + 1, depth
                        )
                    else:
                        print(item)
                print("%s]" % list_space)
            else:
                print(v)
        print("%s}" % space)

    def __info__(self):
        value = repr(self._data)
        return "filename:<%s>,plugin:%r,%s" % (self.filename, self.plugin, value)

    def __repr__(self):
        return repr(self._data)


class ConfigNodeDictEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (ConfigNode, ConfigList, ConfigReference)):
            return obj.encode()
        return super().default(obj)


class RootConfigNode(ConfigNode):
    def __init__(self, config):
        super().__init__()
        self._config = config

    def __getstate__(self):
        d = super().__getstate__()
        d["config_object"] = (
            self._config._base_path,
            self._config._timeout,
            self._config.raise_yaml_exc,
        )
        return d

    def __setstate__(self, d):
        super().__setstate__(d)
        self._config = get_config(*d["config_object"])

    @property
    def config(self):
        return self._config


def build_nodes_from_list(l, parent, path=None):
    result = ConfigList(parent)
    for i, value in enumerate(l):
        if isinstance(value, dict):
            node = ConfigNode(parent, path=[i] if path is None else [path, i])
            build_nodes_from_dict(value, node)
            result.append(node)
        elif isinstance(value, list):
            result.append(
                build_nodes_from_list(
                    value, parent, path=[i] if path is None else [path, i]
                )
            )
        else:
            result.append(value)
    return result


def build_nodes_from_dict(d, parent):
    if d is None:
        raise TypeError("Error parsing %r" % parent)
    else:
        for key, value in d.items():
            if isinstance(value, dict):
                node = ConfigNode(parent, path=[key])
                build_nodes_from_dict(value, node)
                parent[key] = node
            elif isinstance(value, list):
                parent[key] = build_nodes_from_list(value, parent, path=key)
            else:
                parent[key] = value


class InvalidConfig(RuntimeError):
    pass


class Config(metaclass=Singleton):
    """
    Bliss static configuration object.

    Typical usage is to call :func:`get_config` which will return an instance
    of this class.
    """

    def __init__(self, base_path, timeout=3, connection=None, raise_yaml_exc=True):
        self.raise_yaml_exc = raise_yaml_exc
        self._base_path = base_path
        self._timeout = timeout
        self._connection = connection or client.get_default_connection()
        self.invalid_yaml_files = dict()
        self._name2instance = weakref.WeakValueDictionary()
        self._name2cache = dict()
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

        ConfigNode.reset_cache()
        self._root_node = RootConfigNode(self)
        self._root_node["__children__"] = ConfigList(self._root_node)

        self._clear_instances()
        self.invalid_yaml_files = dict()

        path2file = client.get_config_db_files(
            base_path=base_path, timeout=timeout, connection=self._connection
        )

        for path, file_content in path2file:
            if not file_content:
                continue
            base_path, file_name = os.path.split(path)
            fs_node, fs_key = self._get_or_create_path_node(base_path)
            if isinstance(fs_node, MutableSequence):
                continue

            try:
                try:
                    # typ='safe' -> Gives dict instead of OrderedDict subclass
                    # (removing comments)
                    # pure=True -> if False 052 is interpreted as octal (using C engine)

                    yaml = YAML(pure=True)
                    yaml.allow_duplicate_keys = True
                    d = yaml.load(file_content)
                except (
                    ruamel.yaml.scanner.ScannerError,
                    ruamel.yaml.parser.ParserError,
                ) as exp:
                    exp.note = "Error in YAML parsing:\n"
                    exp.note += "----------------\n"
                    exp.note += f"{file_content}\n"
                    exp.note += "----------------\n"
                    exp.note += "Hint: You can check your configuration with an on-line YAML validator like http://www.yamllint.com/ \n\n"
                    exp.problem_mark.name = path
                    if self.raise_yaml_exc:
                        raise exp
                    else:
                        raise InvalidConfig("Error in YAML parsing", path)
                except ruamel.yaml.error.MarkedYAMLError as exp:
                    if exp.problem_mark is not None:
                        exp.problem_mark.name = path
                    if self.raise_yaml_exc:
                        raise exp
                    else:
                        raise InvalidConfig("Error in YAML parsing", path)

                is_init_file = False
                if file_name.startswith("__init__"):
                    _, last_path = os.path.split(base_path)
                    is_init_file = not last_path.startswith("@")

                if is_init_file:
                    if d is None:
                        continue

                    if fs_key:
                        parents = fs_node[fs_key] = ConfigNode(fs_node, filename=path)
                    else:
                        parents = self._root_node = RootConfigNode(self)

                    parents["__children__"] = ConfigList(parents)
                    # do not accept a list in case of __init__ file
                    if isinstance(d, MutableSequence):
                        _msg = "List are not allowed in *%s* file" % path
                        if self.raise_yaml_exc:
                            raise TypeError(_msg)
                        else:
                            raise InvalidConfig(_msg, path)
                    try:
                        build_nodes_from_dict(d, parents)
                    except (TypeError, AttributeError):
                        _msg = (f"Error while parsing '{path}'",)
                        if self.raise_yaml_exc:
                            raise RuntimeError(_msg)
                        else:
                            raise InvalidConfig(_msg, path)

                    continue
                else:
                    if isinstance(d, MutableSequence):
                        parents = ConfigList(fs_node)
                        for i, item in enumerate(d):
                            local_parent = ConfigNode(fs_node, path, path=[i])
                            try:
                                build_nodes_from_dict(item, local_parent)
                            except (ValueError, TypeError, AttributeError):
                                _msg = f"Error while parsing a list on '{path}'"
                                if self.raise_yaml_exc:
                                    raise RuntimeError(_msg)
                                else:
                                    raise InvalidConfig(_msg, path)
                            else:
                                parents.append(local_parent)
                    else:
                        parents = ConfigNode(fs_node, path)
                        try:
                            build_nodes_from_dict(d, parents)
                        except (ValueError, TypeError, AttributeError):
                            _msg = f"Error while parsing '{path}'"
                            if self.raise_yaml_exc:
                                raise RuntimeError(_msg)
                            else:
                                raise InvalidConfig(_msg, path)

                if isinstance(fs_node, MutableSequence):
                    continue
                elif fs_key == "":
                    children = fs_node
                else:
                    children = fs_node.get(fs_key)

                if isinstance(children, MutableSequence):
                    if isinstance(parents, MutableSequence):
                        children.extend(parents)
                    else:
                        children.append(parents)
                elif children is not None:
                    # check if this node is __init__
                    children_node = children.get("__children__")
                    if isinstance(children_node, MutableSequence):  # it's an init node
                        if isinstance(parents, MutableSequence):
                            for p in parents:
                                p._parent = children
                                children_node.append(p)
                        else:
                            parents.reparent(children)
                            children_node.append(parents)
                    else:
                        if isinstance(parents, MutableSequence):
                            parents.append(children)
                            fs_node[fs_key] = parents
                        else:
                            fs_node[fs_key] = [children, parents]
                else:
                    fs_node[fs_key] = parents

            except InvalidConfig as exp:
                msg, path = exp.args[:2]
                self.invalid_yaml_files[path] = msg
                continue

    @property
    def names_list(self):
        """
        List of existing configuration names

        Returns:
            list<str>: sequence of configuration names
        """
        return sorted(list(ConfigNode.indexed_nodes.keys()))

    @property
    def user_tags_list(self):
        """
        List of existing user tags

        Returns:
            list<str>: sequence of user tag names
        """
        return sorted(list(ConfigNode.tagged_nodes.keys()))

    @property
    def service_names_list(self):
        return sorted(
            name for name, node in ConfigNode.indexed_nodes.items() if node.is_service
        )

    @property
    def root(self):
        """
        ConfigReference to the root :class:`~bliss.config.static.ConfigNode`
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

    def _get_or_create_path_node(self, base_path):
        node = self._root_node
        if "/" in base_path:
            sp_path = base_path.split("/")  # beacon server runs on linux
        else:
            sp_path = base_path.split("\\")  # beacon server runs on windows

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
                    parent = ConfigNode(gp)
                    for c in node:
                        c.reparent(parent)
                    gp[sp_path[i - 1]] = gp
                    node = gp
                    child = None

            if child is None:
                child = ConfigNode(node)
                node[p] = child
            node = child

        sp_path = [x for x in sp_path if not x.startswith("@")]

        return node, sp_path and sp_path[-1]

    def get_config(self, name):
        """
        Returns the config :class:`~bliss.config.static.ConfigNode` with the
        given name

        Args:
            name (str): config node name

        Returns:
            ~bliss.config.static.ConfigNode: config node or None if object is
            not found
        """
        return ConfigNode.indexed_nodes.get(name)

    def get_user_tag_configs(self, tag_name):
        """
        Returns the set of config nodes (:class:`~bliss.config.static.ConfigNode`)
        which have the given user *tag_name*.

        Args:
            tag_name (str): user tag name

        Returns:
            set<Node>: the set of nodes wich have the given user tag
        """
        return set(ConfigNode.tagged_nodes.get(tag_name, ()))

    def get(self, name):
        """
        Returns an object instance from its configuration name

        If names starts with *$* it means it is a reference to an existing object in the config
        If the reference contains '.', the specified attribute can be evaluated
        by calling '.dereference()'

        Args:
            name (str): config node name

        Returns:
            ~bliss.config.static.ConfigNode: config node

        Raises:
            RuntimeError: if name is not found in configuration
        """
        return self._get(name)

    def _get(self, name, direct_access=False):
        if name is None:
            raise TypeError("Cannot get object with None name")

        instance_object = self._name2instance.get(name)
        if instance_object is None:  # we will create it
            config_node = self.get_config(name)
            if config_node is None:
                raise RuntimeError("Object '%s' doesn't exist in config" % name)

            if not direct_access and config_node.is_service:
                # need to load locally the module in case the package is defined (local to beamline)
                klass_name, klass_node = config_node.get_inherited_value_and_node(
                    "class"
                )
                module_name = klass_node.get("package")
                if module_name is not None:
                    # load the module to init service plugin if needed
                    module = __import__(module_name, fromlist=[""])

                # This is through a service, so just return the Client proxy
                service_client = service.Client(name, config_node)
                self._name2instance[name] = service_client
                return service_client

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

    def _clear_instances(self):
        self._name2instance.clear()
        self._name2cache.clear()

    def pprint(self, indent=1, depth=None):
        self.root.pprint(indent=indent, depth=depth)

    def __str__(self):
        return f"{self.__class__.__name__}({self._connection})"
