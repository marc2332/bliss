# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
"""
Redis data node structure

--session_name (DataNodeContainer - inherits from DataNode)
    ...
    |
    --sample_0001 (DataNodeContainer - inherits from DataNode)
        |
        --1_loopscan (ScanNode - inherits from DataNodeContainer)
            |
            --timer (DataNodeContainer - inherits from DataNode)
                |
                -- epoch (ChannelDataNode - inherits from _ChannelDataNodeBase)
                |
                -- frelon (LimaChannelDataNode - inherits from _ChannelDataNodeBase)
                |
                --P201 (DataNodeContainer - inherits from DataNode)
                    |
                    --c0 (ChannelDataNode - inherits from _ChannelDataNodeBase)

A DataNode is represented by 2 Redis keys:

 {db_name} -> Struct { name, db_name, node_type, parent=(parent db_name) }
 {db_name}_info -> HashObjSetting, free dictionary

A DataNodeContainer is represented by 3 Redis keys:

 {db_name} ->  see DataNode
 {db_name}_info -> see DataNode
 {db_name}_children -> DataStream, list of db names

A ScanNode is represented by 4 Redis keys:

 {db_name} ->  see DataNodeContainer
 {db_name}_info -> see DataNodeContainer
 {db_name}_children -> see DataNodeContainer
 {db_name}_end -> contains the END event
 {db_name}_prepared -> contains the PREPARED event

A ChannelDataNode is represented by 3 Redis keys:

 {db_name} ->  see DataNode
 {db_name}_info -> see DataNode
 {db_name}_data -> DataStream, list of channel values

A LimaChannelDataNode is represented by 4 Redis keys:

 {db_name} ->  see DataNode
 {db_name}_info -> see DataNode, with some extra keys like reference: True
 {db_name}_data -> DataStream, list of reference data
 {db_name}_data_ref -> QueueObjSetting, the 'live' reference info


Each DataNode can be iterated over to yield nodes (walk, walk_from_last)
or events (walk_events, walk_on_new_events) during or after a scan.

This is achieved by subscribing (i.e. adding to the active stream reader)
to "children_list" streams and when yielding events, "data" streams.
The subscribing is done whenever a new block of raw events is yielded by
the reader:

    DataNode:
        subscribe/create to the "data" stream when yielding events

    DataNodeContainer(DataNode):
        subscribe/create to the "children_list" stream
        subscribe to existing "children_list" streams of children
        subscribe to existing "data" streams of children when yielding events

    Scan(DataNodeContainer):
        subscribe/create to the "children_list" stream
        subscribe to existing "children_list" streams of children
        subscribe to existing "data" streams of children when yielding events
        subscribe/create to the "data" stream

The walk methods have the following filtering arguments:

    include_filter: only yield nodes/events for these nodes
    exclude_children: no events from the children of these nodes (recursive)
    exclude_existing_children: no events from existing children of these
                               nodes (recursive). Defaults to `exclude_children`.

Use the following utility functions to instantiate a DataNode:

    Absolute Redis key name:
        get_node: None when not in required state
        get_nodes: None when not in required state

    Absolute or relative Redis key name:
        create_node: create in Redis regardless of what exists
        get_or_create_node: create in Redis when not in required state
        datanode_factory: when not in required state:
                            return DataNode and create
                            return DataNode but don't create
                            return None
"""

import time
import inspect
import pkgutil
import os
import weakref
import warnings
from numbers import Number
from bliss.common.event import dispatcher
from bliss.common.utils import grouped
from bliss.common.greenlet_utils import protect_from_kill, AllowKill
from bliss.config.conductor import client
from bliss.config import settings
from bliss.config import streaming
from bliss.data.events import Event, EventType, NewNodeEvent


# Dict of available plugins for generating DataNode objects
node_plugins = dict()
for importer, module_name, _ in pkgutil.iter_modules(
    [os.path.join(os.path.dirname(__file__), "nodes")], prefix="bliss.data.nodes."
):
    node_type = module_name.replace("bliss.data.nodes.", "")
    node_plugins[node_type] = {"name": module_name}


class NodeStruct(settings.Struct):
    def __init__(self, db_name, **kwargs):
        # /!\ it is important to not modify redis keys here,
        # otherwise calls to '._get_struct' in pipelines (for example)
        # fail, since there are extra return values (corresponding to
        # the return values of redis calls in this constructor)
        super().__init__(db_name, **kwargs)
        object.__setattr__(self, "_NodeStruct__db_name", db_name)
        # self.__name is initialized to None => attempt to read the "name" property
        # will pass through the underlying HashSetting
        object.__setattr__(self, "_NodeStruct__name", None)

    @property
    def db_name(self):
        return self.__db_name

    @property
    def name(self):
        if self.__name is None:
            self.__name = self._proxy.get("name")
        return self.__name

    def _update(self, mapping):
        return self._proxy.update(mapping)

    def _init(self, **mapping):
        name = mapping.get("name")
        if name is None:
            _, _, name = self.db_name.rpartition(":")
        object.__setattr__(self, "_NodeStruct__name", name)
        mapping["name"] = name
        # hash setting needs to have `db_name` field,
        # since it is expected when doing `hgetall` (cf. test publishing)
        mapping["db_name"] = self.db_name
        self._update(mapping)


def _get_node_object(node_type, name, parent, connection, create=False, **kwargs):
    """Instantiated a DataNode class and optionally create it in Redis.
    This does not perform any checks on what already exists in Redis.

    :returns DataNode:
    """
    module_info = node_plugins.get(node_type)
    if module_info is None:
        return DataNodeContainer(
            node_type,
            name,
            parent=parent,
            connection=connection,
            create=create,
            **kwargs,
        )
    else:
        klass = module_info.get("class")
        if klass is None:
            module_name = module_info.get("name")
            m = __import__(module_name, globals(), locals(), [""], 0)
            classes = inspect.getmembers(
                m,
                lambda x: inspect.isclass(x)
                and not x.__name__.startswith("_")
                and issubclass(x, DataNode)
                and x not in (DataNode, DataNodeContainer)
                and inspect.getmodule(x) == m,
            )
            assert (
                len(classes) == 1
            ), "there should be only 1 public class inheriting from DataNode in the plugin"
            klass = classes[0][-1]
            module_info["class"] = klass
        return klass(
            name, parent=parent, connection=connection, create=create, **kwargs
        )


def get_node(db_name, **kwargs):
    """Do not create in Redis.

    :param str db_name: Redis key
    :param **kwargs: see `get_nodes`
    :returns DataNode or None: `None` when node not in `state`
    """
    return get_nodes(db_name, **kwargs)[0]


def create_node(name, node_type=None, parent=None, connection=None, **kwargs):
    """Create in Redis regardless of its state.

    :returns DataNode:
    """
    if connection is None:
        connection = client.get_redis_proxy(db=1)
    return _get_node_object(node_type, name, parent, connection, create=True, **kwargs)


def get_or_create_node(name, **kwargs):
    """Create in Redis when node not in `state`.

    :param str name: absolute or relative to parent (if any)
    :param **kwargs:
    :returns DataNode:
    """
    return datanode_factory(name, create_not_state=True, **kwargs)


def _default_datanode_state(state):
    """DataNode state in Redis

    :param str or None state:
    :returns str:
    """
    if state is None:
        return "supported"
    if state not in {"exists", "initialized", "supported"}:
        raise ValueError("State should be 'exists', 'initialized' or 'supported'")
    return state


def get_nodes(*db_names, connection=None, state=None, **kwargs):
    """Do not create in Redis.

    :param `*db_names`: Redis keys (str)
    :param Connection connection:
    :param str state: "exists" < "initialized" < "supported"
    :param **kwargs: see `_get_node_object`
    :return list(DataNode or None): `None` when node not in `state`
    """
    state = _default_datanode_state(state)
    if connection is None:
        connection = client.get_redis_proxy(db=1)

    # Get attributes from the principal representations in 1 call (pipeline)
    pipeline = connection.pipeline()
    for db_name in db_names:
        pipeline.exists(db_name)
        struct = DataNode._get_struct(db_name, connection=pipeline)
        struct.version
        struct.node_type
    iter_result = grouped(pipeline.execute(), 3)
    it = enumerate(zip(db_names, iter_result))

    # Instantiate a DataNode when it is in `state`.
    nodes = [None] * len(db_names)
    for i, (db_name, (valid, version, node_type)) in it:
        if state != "exists":
            valid &= bool(version)  # initialized
        if state == "supported":
            valid &= DataNode.supported_version(version)
        if valid:
            if node_type:
                node_type = node_type.decode()
            nodes[i] = _get_node_object(node_type, db_name, None, connection, **kwargs)
    return nodes


def get_filtered_nodes(
    *db_names,
    include_filter=None,
    recursive_exclude=None,
    strict_recursive_exclude=True,
    **kw,
):
    """Get nodes filtered on node properties. String filtering applies to the type property.
    The default required node state is "exists".

    :param `*db_names`: Redis keys (str)
    :param tuple(str) or callable include_filter:
    :param tuple(str) or callable recursive_exclude: exclude children as well
    :param bool strict_recursive_exclude: exclude only the children when False
    :param **kw: see `get_nodes`
    :yields DataNode:
    """
    kw.setdefault("state", "exists")
    if not include_filter and not recursive_exclude:
        for node in get_nodes(*db_names, **kw):
            if node is not None:
                yield node
    elif callable(include_filter) or callable(recursive_exclude):
        yield from _filtered_nodes(
            *db_names,
            include_filter=include_filter,
            recursive_exclude=recursive_exclude,
            strict_recursive_exclude=strict_recursive_exclude,
            **kw,
        )
    else:
        if kw.get("connection") is None:
            kw["connection"] = client.get_redis_proxy(db=1)
        db_names = filter_node_names(
            *db_names,
            include_types=include_filter,
            recursive_exclude_types=recursive_exclude,
            strict_recursive_exclude=strict_recursive_exclude,
            connection=kw["connection"],
        )
        for node in get_nodes(*db_names, **kw):
            if node is not None:
                yield node


def _filtered_nodes(
    *db_names,
    include_filter=None,
    recursive_exclude=None,
    strict_recursive_exclude=True,
    **kw,
):
    """Get nodes filtered on node properties. String filtering applies to the type property.

    :param `*db_names`: Redis keys (str)
    :param tuple(str) or callable include_filter:
    :param tuple(str) or callable recursive_exclude: exclude children as well
    :param bool strict_recursive_exclude: exclude only the children when False
    :param **kw: see `get_nodes`
    :yields DataNode:
    """
    nodes = get_nodes(*db_names, **kw)

    if not include_filter and not recursive_exclude:
        for node in nodes:
            if node is not None:
                yield node
        return

    if recursive_exclude:
        exclude_prefixes = [
            node.db_name
            for node in nodes
            if node is not None and node._excluded(recursive_exclude)
        ]
    else:
        exclude_prefixes = []

    def include(node):
        if node is None:
            return False
        if not node._included(include_filter):
            return False
        db_name = node.db_name
        for exclude_prefix in exclude_prefixes:
            if db_name.startswith(exclude_prefix):
                if strict_recursive_exclude:
                    return False
                else:
                    # Exclude only the children
                    return ":" not in db_name[len(exclude_prefix) :]
        return True

    # Subscribe to the streams associated to the nodes
    for node in nodes:
        if include(node):
            yield node


def filter_node_names(
    *db_names,
    include_types=None,
    recursive_exclude_types=None,
    strict_recursive_exclude=True,
    connection=None,
):
    """Filter node names based on node type.

    :param `*db_names`: Redis keys (str)
    :param tuple(str) include_types:
    :param tuple(str) recursive_exclude_types: exclude children as well
    :param bool strict_recursive_exclude: exclude only the children when False
    :param Connection connection:
    :return list(str):
    """
    if not include_types and not recursive_exclude_types:
        return db_names

    if not include_types:
        include_types = tuple()
    elif isinstance(include_types, str):
        include_types = (include_types,)
    if not recursive_exclude_types:
        recursive_exclude_types = tuple()
    elif isinstance(recursive_exclude_types, str):
        recursive_exclude_types = (recursive_exclude_types,)

    if connection is None:
        connection = client.get_redis_proxy(db=1)

    # Get attributes from the principal representations in 1 call (pipeline)
    pipeline = connection.pipeline()
    for db_name in db_names:
        struct = DataNode._get_struct(db_name, connection=pipeline)
        struct.node_type
    iter_result = grouped(pipeline.execute(), 1)
    it = zip(db_names, iter_result)

    # Filter names based on type
    exclude_prefixes = []
    ret_names = []
    for db_name, (node_type,) in it:
        if node_type:
            node_type = node_type.decode()
        if recursive_exclude_types and node_type in recursive_exclude_types:
            exclude_prefixes.append(db_name)
        if include_types and node_type not in include_types:
            continue
        ret_names.append(db_name)

    if not exclude_prefixes:
        return ret_names

    def include(db_name):
        for exclude_prefix in exclude_prefixes:
            if db_name.startswith(exclude_prefix):
                if strict_recursive_exclude:
                    return False
                else:
                    # Exclude only the children
                    return ":" not in db_name[len(exclude_prefix) :]
        return True

    return [db_name for db_name in ret_names if include(db_name)]


def datanode_factory(
    name,
    node_type=None,
    parent=None,
    connection=None,
    state=None,
    create_not_state=False,
    **kwargs,
):
    """Instantiate a DataNode class. When not in `state`, optionally
    (re)create the node in Redis.

    :param str name: absolute or relative to parent (if any)
    :param str node_type: ignored when node already in `state`
    :param DataNode parent:
    :param Connection connection: a new one will be created when `None`
    :param str state: default is "supported"
    :param bool create_not_state:
    :param **kwargs: see `_get_node_object`
    :returns DataNode:
    """
    if connection is None:
        connection = client.get_redis_proxy(db=1)
    db_name = DataNode._principal_db_name(name, parent=parent)
    node = get_node(db_name, connection=connection, state=state, **kwargs)
    if node is None:
        node = _get_node_object(
            node_type, name, parent, connection, create=create_not_state, **kwargs
        )
    elif parent is not None and create_not_state and node.parent is None:
        node._struct.parent = parent.db_name
    return node


def get_session_node(session_name):
    """Do not create in Redis but instantiate even when it does not exist yet.

    :returns DataNodeContainer:
    """
    if session_name.find(":") > -1:
        raise ValueError(f"Session name can't contains ':' -> ({session_name})")
    return DataNodeContainer(None, session_name)


def sessions_list():
    """Return all available session node(s).
    Return only sessions having data published in Redis.
    Session may or may not be running.
    """
    session_names = []
    conn = client.get_redis_proxy(db=1)
    for node_name in settings.scan("*_children_list", connection=conn):
        if node_name.find(":") > -1:  # can't be a session node
            continue
        session_names.append(node_name[:-14])
    return [n for n in get_nodes(*session_names, connection=conn) if n is not None]


def get_last_saved_scan(parent):
    """
    :param DataNodeContainer parent:
    :returns ScanNode or None:
    """

    def include_filter(node):
        return node.type == "scan" and node.info.get("save")

    return parent.get_last_child_container(
        include_filter=include_filter, exclude_children=("scan", "scan_group")
    )


def get_last_scan_filename(parent):
    """
    :param DataNodeContainer parent:
    :returns str or None:
    """
    last_scan_node = get_last_saved_scan(parent)
    if last_scan_node is None:
        return None
    else:
        return last_scan_node.info.get("filename")


def _get_or_create_node(*args, **kwargs):
    warnings.warn(
        "'_get_or_create_node' is deprecated. Use 'get_or_create_node' instead.",
        FutureWarning,
    )
    return get_or_create_node(*args, **kwargs)


def _create_node(*args, **kwargs):
    warnings.warn(
        "'_create_node' is deprecated. Use 'create_node' instead.", FutureWarning
    )
    return create_node(*args, **kwargs)


class DataNodeAsyncHelper:
    """This context manager helps to create and use DataNode's in a pipeline.
    It can be used as a context manager. Inside the context, you use the
    `replace_connection` method to replace the DataNode's connection with
    an asynchronous proxy. The DataNode's connection will be replaced
    again upon exiting the context with the synchronous proxy provided
    to this helper.

    Usage:

        with DataNodeAsyncHelper(sync_proxy) as helper:
            helper.replace_connection(node1)
            helper.replace_connection(node2)
            # ... all Redis calls of node1 and node2 are asynchronous

        # ... all Redis calls of node1 and node2 are synchronous

    Warning: the DataNode's are no longer thread-safe inside the context.
    """

    def __init__(self, sync_proxy):
        self.sync_proxy = sync_proxy
        self._nodes = []
        self._async_proxy = None
        self._results = None

    @property
    def results(self):
        self._raise_inside_context()
        return self._results

    @property
    def async_proxy(self):
        self._raise_outside_context()
        return self._async_proxy

    def _raise_outside_context(self):
        if self._async_proxy is None:
            raise RuntimeError(
                f"Can only be done inside the {self.__class__.__name__} context"
            )

    def _raise_inside_context(self):
        if self._async_proxy is None:
            raise RuntimeError(
                f"Can only be done outside the {self.__class__.__name__} context"
            )

    def __enter__(self):
        """Create asynchronous proxy
        """
        if self._async_proxy is not None:
            raise RuntimeError("You cannot enter this context more than once")
        if self._nodes:
            raise RuntimeError(
                "Node connections were not reset in the previous context"
            )
        self._nodes = []
        self._async_proxy = self.sync_proxy.pipeline()
        self._results = None
        return self

    def replace_connection(self, *nodes):
        """Replace all connections with the asynchronous proxy. When
        the context exits, all connections are replace with the synchronous
        proxy.
        """
        self._raise_outside_context()
        for node in nodes:
            if node not in self._nodes:
                self._nodes.append(node)
                node.replace_connection(self._async_proxy)

    def __exit__(self, *args):
        """Execute the pipeline and reset the node connections
        """
        try:
            self._results = self._async_proxy.execute()
        finally:
            self._async_proxy = None
            for node in self._nodes:
                node.replace_connection(self.sync_proxy)
            self._nodes = None


def set_ttl(db_name):
    """Set the time-to-live upon garbage collection of DataNode
    which was instantiated with `create==True` (also affects the parents).
    """
    if DataNode._TIMETOLIVE is None:
        return
    # Do not create a Redis connection pool during garbage collection
    connection = client.get_existing_redis_proxy(db=1, timeout=10)
    if connection is None:
        return
    # New instance needs to be created because we are in garbage collection
    # of the original instance
    node = get_node(db_name, state="exists", connection=connection)
    if node is not None:
        node.set_ttl()


def enable_ttl(ttl: Number = 24 * 3600):
    """Enable `set_ttl`
    """
    DataNode._TIMETOLIVE = ttl


def disable_ttl():
    """Disable `set_ttl`
    """
    DataNode._TIMETOLIVE = None


class DataNodeMetaClass(type):
    def __call__(cls, *args, **kwargs):
        """This wraps the __init__ execution
        """
        instance = super().__call__(*args, **kwargs)
        instance._finalize_init(**kwargs)
        return instance


class DataNode(metaclass=DataNodeMetaClass):
    """The DataNode can have these states, depending associated Redis keys:

        1. exists: the principal Redis key is created in Redis
        2. initialized: all Redis keys are created and initialized
        3. supported: initialized + version can be handled by the current implementation
    
    Use the utility methods `get_node`, `get_nodes`, ... to instantiate
    a `DataNode` depending on its state.
    """

    _TIMETOLIVE = 24 * 3600  # 1 day
    VERSION = (1, 1)  # change major version for incompatible API changes

    @staticmethod
    def _principal_db_name(name, parent=None):
        """Redis key of the principal representation of a `DataNode` in Redis
        """
        if parent:
            return f"{parent.db_name}:{name}"
        else:
            return name

    def __init__(
        self,
        node_type,
        name,
        parent=None,
        add_to_parent=True,
        create=False,
        connection=None,
        **kwargs,
    ):
        """
        :param str node_type:
        :param str name: used in the associated Redis keys
        :param DataNode parent:
        :param bool create: create the associated Redis keys
        :param bool add_to_parent: only applicable when `create=True`.
        :param connection:
        :param kwargs: see `_init_info`. The `kwargs["info"]` will become `node.info`.
                       All other keys from `kwargs` are skipped, except for derived classes
                       that overwrite `_init_info`. They can take keys from `kwargs`
                       to populate the `kwargs["info"]`.
        """
        # The DataNode's Redis connection, used by all Redis queries
        if connection is None:
            connection = client.get_redis_proxy(db=1)
        self.db_connection = connection

        # The DataNode's Redis key and type
        db_name = self._principal_db_name(name, parent=parent)
        self.__db_name = db_name
        self.node_type = node_type

        self._priorities = {}
        """Hold priorities per streams."""

        # The info dictionary associated to the DataNode
        self._info = settings.HashObjSetting(f"{db_name}_info", connection=connection)
        info_dict = self._init_info(create=create, **kwargs)
        if info_dict:
            info_dict["node_name"] = db_name
            self._info.update(info_dict)

        # The DataNode itself is represented by a Redis dictionary
        if create:
            self.__new_node = True
            self._struct = self._create_struct(db_name, node_type)
        else:
            self.__new_node = False
            self._ttl_setter = None
            self._struct = self._get_struct(db_name, connection=self.db_connection)

    def _register_stream_priority(self, fullname: str, priority: int):
        """
        Register the stream priority which will be used on the reader side.

        :paran str fullname: Full name of the stream
        :param int priority: data from streams with a lower priority is never
                             yielded as long as higher priority streams have
                             data. Lower number means higher priority.
        """
        self._priorities[fullname] = priority

    def add_prefetch(self, async_proxy=None):
        """As long as caching on the proxy level exists in CachingRedisDbProxy,
        we need to prefetch settings like this.
        """
        if async_proxy is None:
            async_proxy = self.db_connection
        async_proxy.add_prefetch(self._struct, self._info)

    def remove_prefetch(self, async_proxy=None):
        """Undo `add_prefetch`.
        """
        if async_proxy is None:
            async_proxy = self.db_connection
        async_proxy.remove_prefetch(self._struct, self._info)

    def _init_info(self, **kwargs):
        return kwargs.pop("info", {})

    def _finalize_init(self, parent=None, add_to_parent=True, **kwargs):
        if self.__new_node:
            # Mark node as "initialized" in Redis
            self._mark_initialized()
            # Add to the children_list stream of the parent
            if parent is not None:
                self._struct.parent = parent.db_name
                if add_to_parent:
                    parent.add_children(self)
            # Set TTL on garbage collection
            self._ttl_setter = weakref.finalize(self, set_ttl, self.__db_name)

    def get_nodes(self, *db_names, **kw):
        """
        :param `*db_names`: str
        :param `**kw`: see `get_nodes`
        :return list(DataNode):
        """
        kw.setdefault("connection", self.db_connection)
        return get_nodes(*db_names, **kw)

    def get_filtered_nodes(self, *db_names, **kw):
        """
        :param `*db_names`: str
        :param `**kw`: see `get_nodes`
        :yields DataNode:
        """
        kw.setdefault("connection", self.db_connection)
        yield from get_filtered_nodes(*db_names, **kw)

    def get_node(self, db_name, **kw):
        """
        :param str db_name:
        :param `**kw`: see `get_node`
        :return DataNode:
        """
        kw.setdefault("connection", self.db_connection)
        return get_node(db_name, **kw)

    def _create_nonassociated_stream(self, name, **kw):
        """Create any stream, not necessarily associated to this DataNode
        (but use the DataNode's Redis connection).

        :param str name:
        :param `**kw`: see `DataStream`
        :returns DataStream:
        """
        kw.setdefault("connection", self.db_connection)
        return streaming.DataStream(name, **kw)

    def _create_stream(self, suffix, **kw):
        """Create a stream associated to this DataNode.

        :param str suffix:
        :param `**kw`: see `_create_nonassociated_stream`
        :returns DataStream:
        """
        stream = self._create_nonassociated_stream(f"{self.db_name}_{suffix}", **kw)
        return stream

    @classmethod
    def _streamid_to_idx(cls, streamID):
        """
        :param bytes streamID:
        :returns int:
        """
        return int(streamID.split(b"-")[0])

    def search_redis(self, pattern):
        """Look for Redis keys that match a pattern.

        :param str pattern:
        :returns generator: db_name generator
        """
        # TODO: Redis SCAN too slow
        return (x.decode() for x in self.db_connection.keys(pattern))

    def scan_redis(self, *args, **kw):
        warnings.warn(
            "'scan_redis' is deprecated. Use 'search_redis' instead.", FutureWarning
        )
        return self.search_redis(*args, **kw)

    @property
    @protect_from_kill
    def exists(self):
        return bool(self.db_connection.exists(self.db_name))

    @property
    def initialized(self):
        return bool(self.version)

    def _mark_initialized(self):
        self._struct.version = self.encode_version(self.VERSION)

    @property
    def supported(self):
        return self.supported_version(self.version)

    @classmethod
    def supported_version(cls, version):
        """Version can be handled by the current implementation

        :param tuple, bytes or None version:
        :returns bool:
        """
        if not isinstance(version, tuple):
            version = cls.decode_version(version)
        if version:
            return version[0] == cls.VERSION[0]
        return False

    @classmethod
    def _get_struct(cls, db_name, connection=None, **kwargs):
        """Principal Redis representation of a `DataNode`
        """
        if connection is None:
            connection = client.get_redis_proxy(db=1)
        return NodeStruct(db_name, connection=connection, **kwargs)

    def _create_struct(self, db_name, node_type, name=None):
        """Create principal Redis representation of a `DataNode`
        """
        struct = self._get_struct(db_name, connection=self.db_connection)
        # the following call finalize initialization
        # 1) sets db_name
        # 2) sets version to None => means the node is uninitialized
        # 3) if name is None, it is assigned to the last part of "db_name" (default)
        #        - this is useful for Channel nodes only
        struct._init(version=None, node_type=node_type, name=name)
        return struct

    @staticmethod
    def decode_version(version):
        """
        :param str, bytes or None version:
        :returns tuple or None:
        """
        if version:
            if isinstance(version, bytes):
                version = version.decode()
            if version[0] == "v":
                return tuple(map(int, version[1:].split(".")))

    @staticmethod
    def encode_version(version):
        """
        :param tuple or None version:
        :returns str or None:
        """
        if version:
            # Prefix is needed: float on decoding otherwise
            return "v" + ".".join(map(str, version))

    @property
    @protect_from_kill
    def db_name(self):
        return self.__db_name

    @property
    def connection(self):
        return self.db_connection

    @property
    @protect_from_kill
    def name(self):
        return self._struct.name

    @property
    @protect_from_kill
    def fullname(self):
        return self._struct.fullname

    @property
    @protect_from_kill
    def type(self):
        if self.node_type is not None:
            return self.node_type
        return self._struct.node_type

    @property
    @protect_from_kill
    def version(self):
        """`
        :returns None or tuple:
        """
        return self.decode_version(self._struct.version)

    @property
    def iterator(self):
        warnings.warn(
            "DataNodeIterator is deprecated. Use 'DataNode' itself.", FutureWarning
        )
        return self

    @property
    @protect_from_kill
    def parent(self):
        parent_name = self._struct.parent
        if parent_name:
            parent = self.get_node(parent_name, state="exists")
            if parent is None:  # clean
                del self._struct.parent
            return parent

    @property
    def new_node(self):
        return self.__new_node

    @property
    def info(self):
        return self._info

    def connect(self, signal, callback):
        dispatcher.connect(callback, signal, self)

    @protect_from_kill
    def set_ttl(self, include_parents=True):
        """Set the time-to-live for all Redis objects associated to this node
        """
        if self._TIMETOLIVE is not None:
            self.apply_ttl(set(self.get_db_names(include_parents=include_parents)))
        self.detach_ttl_setter()

    def detach_ttl_setter(self):
        """Make sure ttl is not set upon garbage collection.
        """
        if self._ttl_setter is not None:
            self._ttl_setter.detach()

    def apply_ttl(self, db_names):
        """Set time-to-live for a list of Redis objects

        :param list(str) db_names:
        """
        if self._TIMETOLIVE is None:
            return
        p = self.connection.pipeline()
        try:
            for name in db_names:
                p.expire(name, self._TIMETOLIVE)
        finally:
            p.execute()

    def get_db_names(self, include_parents=True):
        """All associated Redis keys, including the associated keys of the parents.
        """
        db_name = self.db_name
        db_names = [db_name, "%s_info" % db_name]
        if include_parents:
            parent = self.parent
            if parent:
                db_names.extend(parent.get_db_names())
        return db_names

    def get_settings(self):
        return [self._struct, self._info]

    def replace_connection(self, redis_proxy):
        """Replace the connection of this nodes and all associated
        Bliss settings.
        """
        # A hard reference to the Redis proxy
        self.db_connection = redis_proxy
        # Weak references to the Redis proxy
        cnx = weakref.ref(redis_proxy)
        for setting in self.get_settings():
            setting._cnx = cnx

    @protect_from_kill
    def walk(
        self,
        filter=None,
        include_filter=None,
        exclude_children=None,
        exclude_existing_children=None,
        wait=True,
        stop_handler=None,
        active_streams=None,
        excluded_stream_names=None,
        first_index=0,
        started_event=None,
    ):
        """Iterate over child nodes that match the `include_filter` argument.

        :param filter: deprecated in favor of include_filter
        :param include_filter: only these nodes are included (all by default)
        :param exclude_children: ignore children of these nodes recursively
        :param exclude_existing_children: defaults to `exclude_children`.
        :param bool wait:
        :param DataStreamReaderStopHandler stop_handler:
        :param dict active_streams: stream name (str) -> stream info (dict)
        :param set excluded_stream_names:
        :param str or int first_index: Redis stream index (None is now)
        :param Event started_event: set when subscribed to initial streams
        :yields DataNode:
        """
        with streaming.DataStreamReader(
            wait=wait,
            stop_handler=stop_handler,
            active_streams=active_streams,
            excluded_stream_names=excluded_stream_names,
        ) as reader:
            yield from self._iter_reader(
                reader,
                filter=filter,
                include_filter=include_filter,
                exclude_children=exclude_children,
                exclude_existing_children=exclude_existing_children,
                first_index=first_index,
                yield_events=False,
                started_event=started_event,
            )

    @protect_from_kill
    def walk_from_last(
        self,
        filter=None,
        include_filter=None,
        exclude_children=None,
        exclude_existing_children=None,
        wait=True,
        include_last=True,
        stop_handler=None,
        started_event=None,
    ):
        """Like `walk` but start from the last node.

        :param filter: deprecated in favor of include_filter
        :param include_filter: only these nodes are included (all by default)
        :param exclude_children: ignore children of these nodes recursively
        :param exclude_existing_children: defaults to `exclude_children`.
        :param bool wait: if wait is True (default), the function blocks
                          until a new node appears
        :param bool include_last:
        :param DataStreamReaderStopHandler stop_handler:
        :param Event started_event: set when subscribed to initial streams
        :yields DataNode:
        """
        # Start walking from "now":
        first_index = streaming.DataStream.now_index()
        if include_last:
            last_node, active_streams, excluded_stream_names = self._get_last_child(
                filter=filter,
                include_filter=include_filter,
                exclude_children=exclude_children,
                exclude_existing_children=exclude_existing_children,
            )
            if last_node is not None:
                exclude_existing_children = None
                yield last_node
                # Start walking from this node's index:
                first_index = last_node.get_children_stream_index()
                if first_index is None:
                    raise RuntimeError(
                        f"{last_node.db_name} was not added to the children stream of its parent"
                    )
        else:
            started_event = None
            active_streams = dict()
            excluded_stream_names = set()

        yield from self.walk(
            filter=filter,
            include_filter=include_filter,
            exclude_children=exclude_children,
            exclude_existing_children=exclude_existing_children,
            wait=wait,
            active_streams=active_streams,
            excluded_stream_names=excluded_stream_names,
            first_index=first_index,
            stop_handler=stop_handler,
            started_event=started_event,
        )

    @protect_from_kill
    def walk_events(
        self,
        filter=None,
        include_filter=None,
        exclude_children=None,
        exclude_existing_children=None,
        wait=True,
        first_index=0,
        active_streams=None,
        excluded_stream_names=None,
        stop_handler=None,
        started_event=None,
    ):
        """Iterate over node and children node events.

        :param filter: deprecated in favor of include_filter
        :param include_filter: only these nodes are included (all by default)
        :param exclude_children: ignore children of these nodes recursively
        :param exclude_existing_children: defaults to `exclude_children`.
        :param bool wait:
        :param str or int first_index: Redis stream index (None is now)
        :param dict active_streams: stream name (str) -> stream info (dict)
        :param set excluded_stream_names:
        :param DataStreamReaderStopHandler stop_handler:
        :param Event started_event: set when subscribed to initial streams
        :yields Event:
        """
        with streaming.DataStreamReader(
            wait=wait,
            stop_handler=stop_handler,
            active_streams=active_streams,
            excluded_stream_names=excluded_stream_names,
        ) as reader:
            yield from self._iter_reader(
                reader,
                filter=filter,
                include_filter=include_filter,
                exclude_children=exclude_children,
                exclude_existing_children=exclude_existing_children,
                first_index=first_index,
                yield_events=True,
                started_event=started_event,
            )

    def walk_on_new_events(self, **kw):
        """Like `walk_en_events` but yield only new event.

        :param `**kw`: see `walk_events`
        :yields Event:
        """
        yield from self.walk_events(first_index=streaming.DataStream.now_index(), **kw)

    def _iter_reader(
        self,
        reader,
        filter=None,
        include_filter=None,
        exclude_children=None,
        exclude_existing_children=None,
        first_index=0,
        yield_events=False,
        started_event=None,
    ):
        """Iterate over the DataStreamReader

        :param DataStreamReader reader:
        :param filter: deprecated in favor of include_filter
        :param include_filter: only these nodes are included (all by default)
        :param exclude_children: ignore children of these nodes recursively
        :param exclude_existing_children: defaults to `exclude_children`.
        :param str or int first_index: Redis stream index (None is now)
        :param bool yield_events: yield Event or DataNode
        :param Event started_event: set when subscribed to initial streams
        :yields Event or DataNode:
        """
        if filter:
            if include_filter:
                raise ValueError("Only use include_filter")
            else:
                warnings.warn(
                    "'filter' is deprecated. Use 'include_filter' instead.",
                    FutureWarning,
                )
                include_filter = filter
        if exclude_existing_children is None:
            exclude_existing_children = exclude_children
        self._subscribe_streams(
            reader,
            include_filter=include_filter,
            exclude_children=exclude_existing_children,
            first_index=first_index,
            yield_events=yield_events,
        )
        if started_event is not None:
            started_event.set()
        for stream, events in reader:
            node = reader.get_stream_info(stream, "node")
            handler = node.get_stream_event_handler(stream)
            yield from handler(
                reader,
                events,
                include_filter=include_filter,
                exclude_children=exclude_children,
                first_index=first_index,
                yield_events=yield_events,
            )

    def get_stream_event_handler(self, stream):
        """
        :param DataStream stream:
        :returns callable:
        """
        if stream.name == f"{self.db_name}_data":
            return self._iter_data_stream_events
        else:
            raise RuntimeError(f"Unknown stream {stream.name}")

    def _filter(self, fltr, default=True):
        """When the filter is a string or sequence, the node type is filtered.

        :param None, callable, str or sequence fltr:
        :param bool default: returned when filter is `None`
        :returns bool:
        """
        if callable(fltr):
            return fltr(self)
        elif isinstance(fltr, str):
            return self.type == fltr
        elif fltr:
            return self.type in fltr
        else:
            return default

    def _included(self, include_filter):
        """When the filter is a string or sequence, the node type is filtered.

        :param None, callable, str or sequence include_filter:
        :returns bool: True by default
        """
        return self._filter(include_filter, default=True)

    def _excluded(self, exclude_filter):
        """When the filter is a string or sequence, the node type is filtered.

        :param None, callable, str or sequence exclude_filter:
        :returns bool: False by default
        """
        return self._filter(exclude_filter, default=False)

    def _yield_on_new_node(
        self, reader, include_filter, exclude_children, first_index, yield_events
    ):
        """
        :param DataStreamReader reader:
        :param include_filter: only these nodes are included (all by default)
        :param exclude_children: ignore children of these nodes recursively
        :param str or int first_index: Redis stream index (None is now)
        :param bool yield_events: yield Event or DataNode
        """
        self._subscribe_streams(
            reader,
            include_filter=include_filter,
            exclude_children=exclude_children,
            first_index=first_index,
            yield_events=yield_events,
        )
        if self._included(include_filter):
            with AllowKill():
                if yield_events:
                    yield Event(type=EventType.NEW_NODE, node=self)
                else:
                    yield self

    def _iter_data_stream_events(
        self,
        reader,
        events,
        include_filter=None,
        exclude_children=None,
        first_index=None,
        yield_events=False,
    ):
        """
        :param DataStreamReader reader:
        :param list(2-tuple) events:
        :param include_filter: only these nodes are included (all by default)
        :param exclude_children: ignore children of these nodes recursively
        :param str or int first_index: Redis stream index (None is now)
        :param bool yield_events: yield Event or DataNode
        :yields Event:
        """
        if yield_events and self._included(include_filter):
            with AllowKill():
                data = self.decode_raw_events(events)
                yield Event(type=EventType.NEW_DATA, node=self, data=data)

    def _get_last_child(
        self,
        filter=None,
        include_filter=None,
        exclude_children=None,
        exclude_existing_children=None,
    ):
        """Get the last child added to the _children_list stream of this node or its children.

        :param filter: deprecated in favor of include_filter
        :param include_filter: only these nodes are included (all by default)
        :param exclude_children: ignore children of these nodes recursively
        :param exclude_existing_children: defaults to `exclude_children`.
        :returns 2-tuple: DataNode, active streams
        """
        return None, None

    def _subscribe_stream(
        self, stream_suffix, reader, create=False, first_index=None, **kw
    ):
        """Subscribe to a particular stream associated with this node.

        :param str stream_suffix: stream to add is "{db_name}_{stream_suffix}"
        :param DataStreamReader reader:
        :param bool create: create when missing
        :param str or int first_index: Redis stream index (None is now)
        :param `**kw`: see `DataStreamReader.add_streams`
        """
        stream_name = f"{self.db_name}_{stream_suffix}"
        if not create:
            if not self.db_connection.exists(stream_name):
                return
        stream = self._create_nonassociated_stream(stream_name)

        # Use the priority as it was setup
        priority = self._priorities.get(stream.name, 0)
        if priority is not None:
            kw["priority"] = priority

        reader.add_streams(stream, node=self, first_index=first_index, **kw)

    def _subscribe_streams(
        self,
        reader,
        include_filter=None,
        exclude_children=None,
        first_index=None,
        yield_events=False,
    ):
        """Subscribe to all associated streams of this node.

        :param DataStreamReader reader:
        :param include_filter: only these nodes are included (all by default)
        :param exclude_children: ignore children of these nodes recursively
        :param str or int first_index: Redis stream index (None is now)
        :param bool yield_events: yield Event or DataNode
        """
        pass

    def get_children_stream_index(self):
        """Get the node's stream ID in parent node's _children_list stream

        :returns bytes or None: stream ID
        """
        parent = self.parent
        if parent is None:
            return None
        # Higher priority than PREPARED scan
        children_stream = parent._create_stream("children_list")
        self_db_name = self.db_name
        for index, raw in children_stream.rev_range():
            db_name = NewNodeEvent(raw=raw).db_name
            if db_name == self_db_name:
                break
        else:
            return None
        return index


class DataNodeContainer(DataNode):
    def __init__(
        self, node_type, name, parent=None, connection=None, create=False, **kwargs
    ):
        DataNode.__init__(
            self,
            node_type,
            name,
            parent=parent,
            connection=connection,
            create=create,
            **kwargs,
        )
        db_name = name if parent is None else self.db_name
        self._children_stream = self._create_nonassociated_stream(
            f"{db_name}_children_list"
        )

    def get_db_names(self, **kw):
        db_names = super().get_db_names(**kw)
        db_names.append("%s_children_list" % self.db_name)
        return db_names

    def get_settings(self):
        return super().get_settings() + [self._children_stream]

    def add_children(self, *children):
        """Publish new (direct) child in Redis
        """
        for child in children:
            self._children_stream.add_event(NewNodeEvent(child.db_name))

    def get_children(self, events=None, purge=False):
        """Get direct children as published in the _children_list
        DataStream. When purging missing nodes, you can no longer
        verify whether all data is still there.

        :param dict events: list((streamID, dict))
        :param bool purge: purge missing nodes
        :yields DataNode:
        """
        if events is None:
            events = self._children_stream.range()
        node_dict = {NewNodeEvent(raw=raw).db_name: index for index, raw in events}
        nodes = self.get_nodes(*node_dict)
        if purge:
            with settings.pipeline(self._children_stream):
                for index, node in zip(node_dict.values(), nodes):
                    if node is None:
                        # When the index is not present
                        # it is silently ignored.
                        self._children_stream.remove(index)
        for index, node in zip(node_dict.values(), nodes):
            if node is not None:
                yield node

    def children(self, purge=False):
        """
        :yields DataNode:
        """
        yield from self.get_children(purge=purge)

    def get_stream_event_handler(self, stream):
        """
        :param DataStream stream:
        :returns callable:
        """
        if stream.name == f"{self.db_name}_children_list":
            return self._iter_children_stream_events
        else:
            return super().get_stream_event_handler(stream)

    def _iter_children_stream_events(
        self,
        reader,
        events,
        include_filter=None,
        exclude_children=None,
        first_index=None,
        yield_events=False,
    ):
        """
        :param DataStreamReader reader:
        :param list(2-tuple) events:
        :param include_filter: only these nodes are included (all by default)
        :param str or int first_index: Redis stream index (None is now)
        :param bool yield_events: yield Event or DataNode
        :yields Event or DataNode:
        """
        for node in self.get_children(events):
            yield from node._yield_on_new_node(
                reader, include_filter, exclude_children, first_index, yield_events
            )

    def _subscribe_streams(
        self,
        reader,
        include_filter=None,
        exclude_children=None,
        first_index=None,
        yield_events=False,
    ):
        """Subscribe to all associated streams of this node.

        :param DataStreamReader reader:
        :param include_filter: only these nodes are included (all by default)
        :param exclude_children: ignore children of these nodes recursively
        :param str or int first_index: Redis stream index (None is now)
        :param bool yield_events: yield Event or DataNode
        """
        search_child_streams = not reader.n_subscribed_streams and first_index

        # Do not use the include_filter for *_children_list. Maybe we don't
        # want the events from the direct children but may want the events
        # from their children.
        exclude_my_children = self._excluded(exclude_children)
        if not exclude_my_children:
            self._subscribe_stream(
                "children_list", reader, create=True, first_index=first_index
            )

        # Subscribing to child streams requires searching for Redis keys
        # which is an expensive operation for the Redis server so skip it
        # when possible.
        if not search_child_streams:
            return

        # Delay subscribing to *_data streams to the moment we receive the
        # NEW_NODE events of those nodes. Same reason as above: search Redis
        # keys is expensive.
        # search_data_streams = yield_events
        search_data_streams = False

        # Subscribe to the streams of all children, not only the direct children.
        # TODO: this assumes that all streams to subscribe too are called
        #       "*_children_list" and "*_data". Can be solved with DataNode
        #       derived class self-registration and each class adding
        #       stream suffixes and orders.

        # Subscribe to streams found by a recursive search
        nodes_with_data = list()
        nodes_with_children = list()
        excluded_stream_names = set(reader.excluded_stream_names)
        if search_data_streams:
            # Make sure the NEW_NODE event always arrives before the NEW_DATA event:
            # - assume "...:parent_children_list" is created BEFORE "...parent:child_data"
            # - search for *_children_list AFTER searching for *_data
            # - subscribe to *_children_list BEFORE subscribing to *_data
            node_names = self._search_nodes_with_streams(
                "data", excluded_stream_names, include_parent=False
            )
            nodes_with_data = list(
                self.get_filtered_nodes(
                    *node_names,
                    include_filter=include_filter,
                    recursive_exclude=exclude_children,
                    strict_recursive_exclude=False,
                )
            )
        if not exclude_my_children:
            node_names = self._search_nodes_with_streams(
                "children_list", excluded_stream_names, include_parent=False
            )
            nodes_with_children = self.get_filtered_nodes(
                *node_names,
                include_filter=None,
                recursive_exclude=exclude_children,
                strict_recursive_exclude=True,
            )

        # Subscribe to the streams that were searched
        for node in nodes_with_children:
            node._subscribe_stream("children_list", reader, first_index=first_index)
        for node in nodes_with_data:
            node._subscribe_stream("data", reader, first_index=first_index)

        # Exclude searched Redis keys from further subscription attempts
        reader.excluded_stream_names |= excluded_stream_names

    def _search_nodes_with_streams(
        self, stream_suffix, excluded_stream_names=None, include_parent=False
    ):
        """Find all children nodes recursively (optionally including self)
        which have associated streams with a particular suffix.

        :param str stream_suffix: streams to add have the name
                                  "{db_name}_{stream_suffix}"
        :param set excluded_stream_names: will be updated with the found redis keys
        :param bool include_parent: include self
        :returns list(str):
        """
        # Get existing stream names
        if include_parent:
            pattern = f"{self.db_name}*_{stream_suffix}"
        else:
            pattern = f"{self.db_name}:*_{stream_suffix}"
        found_names = set(self.search_redis(pattern))
        if excluded_stream_names is None:
            stream_names = sorted(found_names, key=self._node_sort_key)
        else:
            stream_names = sorted(
                found_names - excluded_stream_names, key=self._node_sort_key
            )
            excluded_stream_names |= found_names

        # Get associated DataNode key names
        nsuffix = len(stream_suffix) + 1  # +1 for the underscore
        # Warning: some nodes may be None because a Redis key could end with
        # the suffix and not be a stream associated to a node.
        return [db_name[:-nsuffix] for db_name in stream_names]

    @staticmethod
    def _node_sort_key(db_name):
        """For hierarchical sort of node names
        """
        return db_name.count(":")

    def _get_last_child(
        self,
        filter=None,
        include_filter=None,
        exclude_children=None,
        exclude_existing_children=None,
    ):
        """Get the last child added to the _children_list stream of this node or its children.

        :param filter: deprecated in favor of include_filter
        :param include_filter: only these nodes are included (all by default)
        :param exclude_children: ignore children of these nodes recursively
        :param exclude_existing_children: defaults to `exclude_children`
        :returns 3-tuple: DataNode, active streams, excluded stream names
        """
        last_node = None
        active_streams = dict()
        excluded_stream_names = set()
        # Higher priority than PREPARED scan
        children_stream = self._create_stream("children_list")
        first_index = children_stream.before_last_index()
        if first_index is None:
            return last_node, active_streams, excluded_stream_names
        for last_node in self.walk(
            filter=filter,
            include_filter=include_filter,
            exclude_children=exclude_children,
            exclude_existing_children=exclude_existing_children,
            wait=False,
            active_streams=active_streams,
            excluded_stream_names=excluded_stream_names,
            first_index=first_index,
        ):
            pass
        return last_node, active_streams, excluded_stream_names

    def get_child_containers(self, include_filter=None, exclude_children=None):
        """Get the child `DataNodeContainer` of this node and its children.

        :param include_filter: only these nodes are included (all by default)
        :param exclude_children: ignore children of these nodes recursively
        :yields DataNodeContainer:
        """
        node_names = self._search_nodes_with_streams(
            "children_list", include_parent=True
        )
        yield from self.get_filtered_nodes(
            *node_names,
            include_filter=include_filter,
            recursive_exclude=exclude_children,
            strict_recursive_exclude=False,
        )

    def get_last_child_container(self, include_filter=None, exclude_children=None):
        """Get the last child `DataNodeContainer` of this node or its children.
        The order is based on the Redis streamid in the `*_children_list` streams.

        :param include_filter: only these nodes are included (all by default)
        :param exclude_children: ignore children of these nodes recursively
        :returns DataNodeContainer:
        """
        last_node = None
        last_id = 0, 0
        containers = self.get_child_containers(
            include_filter=include_filter, exclude_children=exclude_children
        )
        for node in containers:
            streamid = node.get_children_stream_index()
            if streamid is None:
                continue
            node_id = tuple(map(int, streamid.decode().split("-")))
            if node_id > last_id:
                last_node = node
                last_id = node_id
        return last_node
