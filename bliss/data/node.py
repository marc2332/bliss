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
 {db_name}_data -> contains the END event

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

    def scan_filter(node):
        return node.type == "scan" and node.info.get("save")

    return parent.get_last_child_container(filter=scan_filter)


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
    VERSION = (1, 0)  # change major version for incompatible API changes

    @staticmethod
    def _principal_db_name(name, parent=None):
        """Redis key of the principal representation of a `DataNode` in Redis
        """
        return f"{parent.db_name}:{name}" if parent else name

    def __init__(
        self, node_type, name, parent=None, connection=None, create=False, **kwargs
    ):
        """
        :param str node_type:
        :param str name: used in the associated Redis keys
        :param DataNode parent:
        :param bool create: create the associated Redis keys
        :param kwargs: see `_init_info`
        """
        # The DataNode's Redis connection, used by all Redis queries
        if connection is None:
            connection = client.get_redis_proxy(db=1)
        self.db_connection = connection

        # The DataNode's Redis key and type
        db_name = self._principal_db_name(name, parent=parent)
        self.__db_name = db_name
        self.node_type = node_type

        # The info dictionary associated to the DataNode
        self._info = settings.HashObjSetting(f"{db_name}_info", connection=connection)
        info_dict = self._init_info(create=create, **kwargs)
        if info_dict:
            info_dict["node_name"] = db_name
            self._info.update(info_dict)

        # The DataNode itself is represented by a Redis dictionary
        if create:
            self.__new_node = True
            self._struct = self._create_struct(db_name, name, node_type)
        else:
            self.__new_node = False
            self._ttl_setter = None
            self._struct = self._get_struct(db_name, connection=self.db_connection)

    def _init_info(self, **kwargs):
        return kwargs.pop("info", {})

    def _finalize_init(self, create=False, parent=None, **kwargs):
        if create:
            # Mark node as "initialized" in Redis
            self._mark_initialized()
            # Add to the children_list stream of the parent
            if parent is not None:
                self._struct.parent = parent.db_name
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
        return self._create_nonassociated_stream(f"{self.db_name}_{suffix}", **kw)

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
    def _get_struct(cls, db_name, connection=None):
        """Principal Redis representation of a `DataNode`
        """
        if connection is None:
            connection = client.get_redis_proxy(db=1)
        return settings.Struct(db_name, connection=connection)

    def _create_struct(self, db_name, name, node_type):
        """Create principal Redis representation of a `DataNode`
        """
        struct = self._get_struct(db_name, connection=self.db_connection)
        struct.version = None  # bool(version) means initialized
        struct.name = name
        struct.db_name = db_name
        struct.node_type = node_type
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
        warnings.warn("fullname is deprecated", FutureWarning)
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
            parent = self.get_node(parent_name)
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
    def set_ttl(self):
        """Set the time-to-live for all Redis objects associated to this node
        """
        if self._TIMETOLIVE is not None:
            self.apply_ttl(set(self.get_db_names()))
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

    def get_db_names(self):
        db_name = self.db_name
        db_names = [db_name, "%s_info" % db_name]
        parent = self.parent
        if parent:
            db_names.extend(parent.get_db_names())
        return db_names

    @protect_from_kill
    def walk(
        self,
        filter=None,
        wait=True,
        stop_handler=None,
        active_streams=None,
        first_index=0,
    ):
        """Iterate over child nodes that match the `filter` argument.

        :param None, str, iterable or callable filter: only these DataNode types are allowed (all by default)
        :param bool wait:
        :param DataStreamReaderStopHandler stop_handler:
        :param dict active_streams: stream name (str) -> stream info (dict)
        :param str or int first_index: Redis stream ID
        :yields DataNode:
        """
        with streaming.DataStreamReader(
            wait=wait, stop_handler=stop_handler, active_streams=active_streams
        ) as reader:
            yield from self._iter_reader(
                reader, filter=filter, first_index=first_index, yield_events=False
            )

    @protect_from_kill
    def walk_from_last(
        self, filter=None, wait=True, include_last=True, stop_handler=None
    ):
        """Like `walk` but start from the last node.

        :param None, str, iterable or callable filter: only these DataNode types are allowed (all by default)
        :param bool wait: if wait is True (default), the function blocks
                          until a new node appears
        :param bool include_last:
        :param DataStreamReaderStopHandler stop_handler:
        :yields DataNode:
        """
        active_streams = dict()
        # Start walking from "now":
        first_index = streaming.DataStream.now_index()
        if include_last:
            last_node, active_streams = self._get_last_child(filter=filter)
            if last_node is not None:
                yield last_node
                # Start walking from this node's index:
                first_index = last_node.get_children_stream_index()
                if first_index is None:
                    raise RuntimeError(
                        f"{last_node.db_name} was not added to the children stream of its parent"
                    )
        yield from self.walk(
            filter,
            wait=wait,
            active_streams=active_streams,
            first_index=first_index,
            stop_handler=stop_handler,
        )

    @protect_from_kill
    def walk_events(
        self,
        filter=None,
        wait=True,
        first_index=0,
        active_streams=None,
        stop_handler=None,
    ):
        """Iterate over node and children node events.

        :param None, str, iterable or callable filter: only these DataNode types are allowed (all by default)
        :param bool wait:
        :param str or int first_index: Redis stream ID
        :param dict active_streams: stream name (str) -> stream info (dict)
        :param DataStreamReaderStopHandler stop_handler:
        :yields Event:
        """
        with streaming.DataStreamReader(
            wait=wait, active_streams=active_streams, stop_handler=stop_handler
        ) as reader:
            yield from self._iter_reader(
                reader, filter=filter, first_index=first_index, yield_events=True
            )

    def walk_on_new_events(self, **kw):
        """Like `walk` but yield only new event.

        :param `**kw`: see `walk_events`
        :yields Event:
        """
        yield from self.walk_events(first_index=streaming.DataStream.now_index(), **kw)

    def _iter_reader(self, reader, filter=None, first_index=0, yield_events=False):
        """Iterate over the DataStreamReader

        :param DataStreamReader reader:
        :param None, str, iterable or callable filter: only these DataNode types are allowed (all by default)
        :param str or int first_index: Redis stream ID
        :param bool yield_events: yield Event or DataNode
        :yields Event or DataNode:
        """
        filter = self._init_node_filter(filter)
        self._subscribe_all_streams(
            reader, filter=filter, first_index=first_index, yield_events=yield_events
        )
        for stream, events in reader:
            node = reader.get_stream_info(stream, "node")
            handler = node.get_stream_event_handler(stream)
            yield from handler(
                reader,
                events,
                filter=filter,
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

    @staticmethod
    def _init_node_filter(filter):
        """
        :param None, str, iterable or callable filter:
        :returns tuple or callable:
        """
        if isinstance(filter, str):
            return (filter,)
        elif callable(filter):
            return filter
        elif filter:
            return tuple(filter)
        else:
            return tuple()

    def _filtered_out(self, filter):
        """
        :param None, tuple or callable filter:
        :returns bool:
        """
        if callable(filter):
            return not filter(self)
        else:
            return filter and self.type not in filter

    def _yield_on_new_node(self, reader, filter, first_index, yield_events):
        """
        :param DataStreamReader reader:
        :param None, tuple or callable filter: only these DataNode types are allowed (all by default)
        :param str or int first_index: Redis stream ID
        :param bool yield_events: yield Event or DataNode
        """
        self._subscribe_all_streams(
            reader, filter=filter, first_index=first_index, yield_events=yield_events
        )
        if not self._filtered_out(filter):
            with AllowKill():
                if yield_events:
                    yield Event(type=EventType.NEW_NODE, node=self)
                else:
                    yield self

    def _iter_data_stream_events(
        self, reader, events, filter=None, first_index=None, yield_events=False
    ):
        """
        :param DataStreamReader reader:
        :param list(2-tuple) events:
        :param None, tuple or callable filter: only these DataNode types are allowed (all by default)
        :param str or int first_index: Redis stream ID
        :param bool yield_events: yield Event or DataNode
        :yields Event:
        """
        if yield_events and not self._filtered_out(filter):
            with AllowKill():
                data = self.decode_raw_events(events)
                yield Event(type=EventType.NEW_DATA, node=self, data=data)

    def _get_last_child(self, filter=None):
        """Get the last child added to the _children_list stream of this node or its children.

        :param None, tuple or callable filter: only these DataNode types are allowed (all by default)
        :returns 2-tuple: DataNode, active streams
        """
        return None, None

    def _subscribe_stream(self, stream_suffix, reader, create=False, **kw):
        """Subscribe to a stream with a particular name,
        associated with this node.

        :param str stream_suffix: stream to add is "{db_name}_{stream_suffix}"
        :param DataStreamReader reader:
        :param bool create: create when missing
        :param `**kw`: see `DataStreamReader.add_streams`
        """
        stream_name = f"{self.db_name}_{stream_suffix}"
        if not create:
            if not self.db_connection.exists(stream_name):
                return
        stream = self._create_nonassociated_stream(stream_name)
        reader.add_streams(stream, node=self, **kw)

    def _subscribe_all_streams(
        self, reader, filter=None, first_index=None, yield_events=False
    ):
        """Subscribe to new streams before yielding the NEW_NODE event.

        :param DataStreamReader reader:
        :param None, tuple or callable filter: only these DataNode types are allowed (all by default)
        :param str or int first_index: Redis stream ID
        :param bool yield_events: yield Event or DataNode
        """
        if yield_events:
            # Always subscribe to the *_data stream
            # from the start (index 0)
            self._subscribe_stream("data", reader, first_index=0, create=True)

    def _subscribe_on_new_node_after_yield(
        self, reader, filter=None, first_index=None, yield_events=False
    ):
        """Subscribe to new streams after yielding the NEW_NODE event.

        :param DataStreamReader reader:
        :param None, tuple or callable filter: only these DataNode types are allowed (all by default)
        :param str or int first_index: Redis stream ID
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

    def get_db_names(self):
        db_names = super().get_db_names()
        db_names.append("%s_children_list" % self.db_name)
        return db_names

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
        self, reader, events, filter=None, first_index=None, yield_events=False
    ):
        """
        :param DataStreamReader reader:
        :param list(2-tuple) events:
        :param None, tuple or callable filter: only these DataNode types are allowed (all by default)
        :param str or int first_index: Redis stream ID
        :param bool yield_events: yield Event or DataNode
        :yields Event or DataNode:
        """
        for node in self.get_children(events):
            yield from node._yield_on_new_node(
                reader, filter, first_index, yield_events
            )

    def _subscribe_all_streams(
        self, reader, filter=None, first_index=None, yield_events=False
    ):
        """Subscribe to new streams before yielding the NEW_NODE event.

        :param DataStreamReader reader:
        :param None, tuple or callable filter: only these DataNode types are allowed (all by default)
        :param str or int first_index: Redis stream ID
        :param bool yield_events: yield Event or DataNode
        """
        # Do not use the filter for *_children_list. Maybe we don't want the node's
        # events but we may want the events from its children
        self._subscribe_stream(
            "children_list", reader, create=True, first_index=first_index
        )
        if yield_events:
            # Make sure the NEW_NODE always arrives before NEW_DATA event:
            # - assume "...:parent_children_list" is created BEFORE "...parent:child_data"
            # - search for *_children_list AFTER searching for *_data
            # - subscribe to *_children_list BEFORE subscribing to *_data
            nodes_with_data = list(
                self._nodes_with_streams("data", include_parent=False, filter=filter)
            )
            nodes_with_children = list(
                self._nodes_with_streams(
                    "children_list", include_parent=False, filter=None
                )
            )
            for node in nodes_with_children:
                node._subscribe_stream("children_list", reader, first_index=first_index)
            for node in nodes_with_data:
                node._subscribe_stream("data", reader, first_index=0)
        else:
            for node in self._nodes_with_streams(
                "children_list", include_parent=False, filter=None
            ):
                node._subscribe_stream("children_list", reader, first_index=first_index)

    def _subscribe_on_new_node_after_yield(
        self, reader, filter=None, first_index=None, yield_events=False
    ):
        """Subscribe to new streams after yielding the NEW_NODE event.

        :param DataStreamReader reader:
        :param tuple filter: only these DataNode types are allowed (all by default)
        :param str or int first_index: Redis stream ID
        :param bool yield_events: yield Event or DataNode
        """
        pass

    def _nodes_with_streams(
        self, stream_suffix, include_parent=False, forbidden_types=None, filter=None
    ):
        """Find all children nodes recursively (including self or not)
        which have associated streams with a particular suffix.

        :param str stream_suffix: streams to add have the name
                                  "{db_name}_{stream_suffix}"
        :param bool include_parent: consider self as a child
        :param tuple forbidden_types: exclude these node types and their children
        :param None, tuple or callable filter: only these DataNode types are allowed (all by default)
        :yields DataNode:
        """
        # Get existing stream names
        if include_parent:
            pattern = f"{self.db_name}*_{stream_suffix}"
        else:
            pattern = f"{self.db_name}:*_{stream_suffix}"
        stream_names = self.search_redis(pattern)
        stream_names = sorted(stream_names, key=self._node_sort_key)

        # Get associated DataNode's
        nsuffix = len(stream_suffix) + 1  # +1 for the underscore
        node_names = (db_name[:-nsuffix] for db_name in stream_names)
        nodes = self.get_nodes(*node_names)
        # Some nodes may be None because a Redis key could end with
        # the suffix and not be a stream associated to a node.

        # Function to check whether a node's stream
        # should be added (applies to its children as well).
        if forbidden_types:
            forbidden_prefixes = [
                node.db_name
                for node in nodes
                if node is not None and node.type in forbidden_types
            ]
        else:
            forbidden_prefixes = []

        def addstream(db_name):
            for forbidden_prefix in forbidden_prefixes:
                if db_name.startswith(forbidden_prefix):
                    return False
            return True

        # Subscribe to the streams associated to the nodes
        for node in nodes:
            if node is None:
                continue
            if node._filtered_out(filter):
                continue
            if addstream(node.db_name):
                yield node

    @staticmethod
    def _node_sort_key(db_name):
        """For hierarchical sort of node names
        """
        return db_name.count(":")

    def _get_last_child(self, filter=None):
        """Get the last child added to the _children_list stream of this node or its children.

        :param None, tuple or callable filter: only these DataNode types are allowed (all by default)
        :returns 2-tuple: DataNode, active streams
        """
        active_streams = dict()
        children_stream = self._create_stream("children_list")
        first_index = children_stream.before_last_index()
        if first_index is None:
            return None, active_streams
        last_node = None
        for last_node in self.walk(
            filter=filter,
            wait=False,
            active_streams=active_streams,
            first_index=first_index,
        ):
            pass
        return last_node, active_streams

    def get_child_containers(self, filter=None):
        """Get the child `DataNodeContainer` of this node and its children.

        :param None, str, iterable or callable filter: only these `DataNodeContainer` types are allowed (all by default)
        :yields DataNodeContainer:
        """
        filter = self._init_node_filter(filter)
        node_names = self.search_redis("*_children_list")
        it_node_names = (db_name[:-14] for db_name in node_names)
        for node in get_nodes(*it_node_names):
            if node._filtered_out(filter):
                continue
            yield node

    def get_last_child_container(self, filter=None):
        """Get the last child `DataNodeContainer` of this node or its children.
        The order is based on the Redis streamid in the `*_children_list` streams.

        :param None, str, iterable or callable filter: only these `DataNodeContainer` types are allowed (all by default)
        :returns DataNodeContainer:
        """
        last_node = None
        last_id = 0, 0
        for node in self.get_child_containers(filter=filter):
            streamid = node.get_children_stream_index()
            if streamid is None:
                continue
            node_id = tuple(map(int, streamid.decode().split("-")))
            if node_id > last_id:
                last_node = node
                last_id = node_id
        return last_node
