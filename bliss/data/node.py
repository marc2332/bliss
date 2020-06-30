# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
"""
Redis structure

--eh3 (DataNodeContainer - inherits from DataNode)
   |
   --scan1 (Scan - inherits from DataNode)
     |
     --P201 (DataNodeContainer - inherits from DataNode)
       |
       --c0 (ChannelDataNode - inherits from DataNode)
       |
       -- frelon (LimaChannelDataNode - inherits from DataNode)

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
"""
import time
import inspect
import pkgutil
import os
import weakref
import warnings
from bliss.common.event import dispatcher
from bliss.common.utils import grouped
from bliss.common.greenlet_utils import protect_from_kill, AllowKill
from bliss.config.conductor import client
from bliss.config import settings
from bliss.config import streaming
from bliss.config import streaming_events
from bliss.data.events import Event, EventType


SCAN_TYPES = {"scan", "scan_group"}

# make list of available plugins for generating DataNode objects
node_plugins = dict()
for importer, module_name, _ in pkgutil.iter_modules(
    [os.path.join(os.path.dirname(__file__), "nodes")], prefix="bliss.data.nodes."
):
    node_type = module_name.replace("bliss.data.nodes.", "")
    node_plugins[node_type] = {"name": module_name}


def _get_node_object(node_type, name, parent, connection, create=False, **keys):
    module_info = node_plugins.get(node_type)
    if module_info is None:
        return DataNodeContainer(
            node_type, name, parent, connection=connection, create=create, **keys
        )
    else:
        klass = module_info.get("class")
        if klass is None:
            module_name = module_info.get("name")
            m = __import__(module_name, globals(), locals(), [""], 0)
            classes = inspect.getmembers(
                m,
                lambda x: inspect.isclass(x)
                and issubclass(x, DataNode)
                and x not in (DataNode, DataNodeContainer)
                and inspect.getmodule(x) == m,
            )
            # there should be only 1 class inheriting from DataNode in the plugin
            klass = classes[0][-1]
            module_info["class"] = klass
        return klass(name, parent=parent, connection=connection, create=create, **keys)


def get_node(db_name, connection=None):
    return get_nodes(db_name, connection=connection)[0]


def get_nodes(*db_names, **kw):
    """
    :param `*db_names`: str
    :param connection:
    :return list(DataNode):
    """
    connection = kw.get("connection")
    if connection is None:
        connection = client.get_redis_connection(db=1)
    pipeline = connection.pipeline()
    for db_name in db_names:
        data = settings.Struct(db_name, connection=pipeline)
        data.name
        data.node_type
    return [
        None
        if name is None
        else _get_node_object(
            None if node_type is None else node_type.decode(), db_name, None, connection
        )
        for db_name, (name, node_type) in zip(db_names, grouped(pipeline.execute(), 2))
    ]


def get_session_node(session_name):
    """ Return a session node even if the session doesn't exist yet.
    This method is an helper if you want to follow session events.
    """
    if session_name.find(":") > -1:
        raise ValueError(f"Session name can't contains ':' -> ({session_name})")
    return DataNodeContainer(None, session_name)


def sessions_list():
    """ Return all available session node(s).
    Return only sessions having data published in Redis.
    Session may or may not be running.
    """
    session_names = []
    conn = client.get_redis_connection(db=1)
    for node_name in settings.scan("*_children_list", connection=conn):
        if node_name.find(":") > -1:  # can't be a session node
            continue
        session_name = node_name.replace("_children_list", "")
        session_names.append(session_name)
    return get_nodes(*session_names, connection=conn)


def _create_node(name, node_type=None, parent=None, connection=None, **keys):
    if connection is None:
        connection = client.get_redis_connection(db=1)
    return _get_node_object(node_type, name, parent, connection, create=True, **keys)


def _get_or_create_node(name, node_type=None, parent=None, connection=None, **keys):
    if connection is None:
        connection = client.get_redis_connection(db=1)
    db_name = DataNode.exists(name, parent, connection)
    if db_name:
        return get_node(db_name, connection=connection)
    else:
        return _create_node(name, node_type, parent, connection, **keys)


class DataNodeIterator:
    """Iterate over nodes or events of a DataNode
    """

    def __init__(self, node):
        warnings.warn(
            "DataNodeIterator is deprecated. Use 'DataNode.walk' instead.",
            FutureWarning,
        )
        self.node = node

    def __getattr__(self, attr):
        return getattr(self.node, attr)


def set_ttl(db_name):
    """Create a new DataNode in order to call its set_ttl
    """
    node = get_node(db_name)
    if node is not None:
        node.set_ttl()


class DataNode:
    default_time_to_live = 24 * 3600  # 1 day

    @staticmethod
    @protect_from_kill
    def exists(name, parent=None, connection=None):
        if connection is None:
            connection = client.get_redis_connection(db=1)
        db_name = "%s:%s" % (parent.db_name, name) if parent else name
        return db_name if connection.exists(db_name) else None

    def __init__(
        self, node_type, name, parent=None, connection=None, create=False, **kwargs
    ):
        info_dict = self._init_info(create=create, **kwargs)
        if connection is None:
            connection = client.get_redis_connection(db=1)
        db_name = "%s:%s" % (parent.db_name, name) if parent else name
        info_hash_name = "%s_info" % db_name
        self._info = settings.HashObjSetting(info_hash_name, connection=connection)
        if info_dict:
            info_dict["node_name"] = db_name
            self._info.update(info_dict)

        self.db_connection = connection

        if create:
            self.__new_node = True
            self.__db_name = db_name
            self._struct = self._create_struct(db_name, name, node_type)
            if parent:
                self._struct.parent = parent.db_name
                parent.add_children(self)
            self._ttl_setter = weakref.finalize(self, set_ttl, db_name)
        else:
            self.__new_node = False
            self._ttl_setter = None
            self._struct = self._get_struct(db_name)
            self.__db_name = db_name

        # node type cache
        self.node_type = node_type

    def _init_info(self, **kwargs):
        return kwargs.pop("info", {})

    def get_nodes(self, *db_names):
        """
        :param `*db_names`: str
        :return list(DataNode):
        """
        return get_nodes(*db_names, connection=self.db_connection)

    def get_node(self, db_name):
        """
        :param str db_name:
        :return DataNode:
        """
        return get_node(db_name, connection=self.db_connection)

    def create_stream(self, name, **kw):
        """
        :param str name:
        :param `**kw`: see `DataStream`
        :returns DataStream:
        """
        return streaming.DataStream(name, connection=self.db_connection, **kw)

    def create_associated_stream(self, suffix, **kw):
        """
        :param str suffix:
        :param `**kw`: see `create_stream`
        :returns DataStream:
        """
        return self.create_stream(f"{self.db_name}_{suffix}", **kw)

    def search_redis(self, pattern):
        """
        :param str pattern:
        :returns generator: db_name generator
        """
        return (x.decode() for x in self.db_connection.keys(pattern))

    def _get_struct(self, db_name):
        return settings.Struct(db_name, connection=self.db_connection)

    def _create_struct(self, db_name, name, node_type):
        struct = self._get_struct(db_name)
        struct.name = name
        struct.db_name = db_name
        struct.node_type = node_type
        return struct

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
    def iterator(self):
        return DataNodeIterator(self)

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
        db_names = set(self._get_db_names())
        pipeline = self.connection.pipeline()
        for name in db_names:
            pipeline.expire(name, DataNode.default_time_to_live)
        pipeline.execute()
        if self._ttl_setter is not None:
            self._ttl_setter.detach()

    def _get_db_names(self):
        db_name = self.db_name
        db_names = [db_name, "%s_info" % db_name]
        parent = self.parent
        if parent:
            db_names.extend(parent._get_db_names())
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
        """Iterate over child nodes that match the `filter` argument

        :param tuple filter: only these DataNode types are allowed (all by default)
        :param bool wait: if wait is True (default), the function blocks
                          until a new node appears
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
        """Walk from the last child node (see walk)

        :param tuple filter: only these DataNode types are allowed (all by default)
        :param bool wait: if wait is True (default), the function blocks
                          until a new node appears
        :param bool include_last:
        :param DataStreamReaderStopHandler stop_handler:
        :yields DataNode:
        """
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
        else:
            active_streams = dict()
            # Start walking from "now":
            first_index = streaming.DataStream.now_index()
        yield from self.walk(
            filter,
            wait=wait,
            active_streams=active_streams,
            first_index=first_index,
            stop_handler=stop_handler,
        )

    @protect_from_kill
    def walk_events(
        self, filter=None, first_index=0, active_streams=None, stop_handler=None
    ):
        """Iterate over node and children node events starting from a
        particular stream index.

        :param tuple filter: only these DataNode types are allowed (all by default)
        :param str or int first_index: Redis stream ID
        :param dict active_streams: stream name (str) -> stream info (dict)
        :param DataStreamReaderStopHandler stop_handler:
        :yields Event:
        """
        with streaming.DataStreamReader(
            active_streams=active_streams, stop_handler=stop_handler
        ) as reader:
            yield from self._iter_reader(
                reader, filter=filter, first_index=first_index, yield_events=True
            )

    def walk_on_new_events(self, **kw):
        """Iterate over node and children node events starting from now.

        :param `**kw`: see `walk_events`
        :yields Event:
        """
        yield from self.walk_events(first_index=streaming.DataStream.now_index(), **kw)

    def _iter_reader(self, reader, filter=None, first_index=0, yield_events=False):
        """Iterate over the DataStreamReader

        :param DataStreamReader reader:
        :param tuple filter: only these DataNode types are allowed (all by default)
        :param str or int first_index: Redis stream ID
        :param bool yield_events: return Event or DataNode
        :yields Event or DataNode:
        """
        if isinstance(filter, str):
            filter = (filter,)
        elif filter:
            filter = tuple(filter)
        if yield_events:
            new_child_func = self._yield_events
        else:
            new_child_func = self._yield_nodes
        self.subscribe_initial_streams(
            reader, first_index=first_index, yield_data=yield_events
        )
        for stream, events in reader:
            if stream.name.endswith("_children_list"):
                children = self._read_children_stream(stream_events=events)
                new_stream = [
                    self.create_stream(f"{name}_children_list") for name in children
                ]
                reader.add_streams(*new_stream, first_index=first_index)
                yield from new_child_func(reader, filter, stream, children, first_index)
            else:
                yield from self._iter_data_events(
                    reader, filter, stream, events, yield_events=yield_events
                )

    def _iter_data_events(self, reader, filter, stream, events, yield_events=False):
        """
        :param DataStreamReader reader:
        :param tuple filter: only these DataNode types are allowed (all by default)
        :param DataStream stream:
        :param list(tuple) events:
        :param bool yield_events:
        :yields Event:
        """
        node = reader.get_stream_info(stream, "node")
        allowed = not filter or node.type in filter
        if node.type in SCAN_TYPES:
            if yield_events and allowed:
                with AllowKill():
                    data = node.decode_raw_events(events)
                    yield Event(type=EventType.END_SCAN, node=node, data=data)
            # Stop reading events from the scan
            reader.remove_matching_streams(f"{node.db_name}*")
        else:
            if yield_events and allowed:
                with AllowKill():
                    data = node.decode_raw_events(events)
                    yield Event(type=EventType.NEW_DATA, node=node, data=data)

    def _yield_nodes(self, reader, filter, stream, children, first_index):
        """
        :param DataStreamReader reader:
        :param tuple filter: only these DataNode types are allowed (all by default)
        :param DataStream stream:
        :param dict children: db_name -> stream ID
        :param str or int first_index: Redis stream ID
        :yields DataNode:
        """
        for db_name, node in self._iter_new_children(stream, children):

            if not filter or node.type in filter:
                with AllowKill():
                    yield node

            if node.type in SCAN_TYPES:
                node.subscribe_existing_children_streams(
                    "children_list",
                    reader,
                    include_parent=True,
                    first_index=first_index,
                )
                node.subscribe_stream("data", reader, first_index=0)

    def _yield_events(self, reader, filter, stream, children, first_index):
        """
        :param DataStreamReader reader:
        :param tuple filter: only these DataNode types are allowed (all by default)
        :param DataStream stream:
        :param dict children: node.db_name -> stream ID
        :param str or int first_index: Redis stream ID
        :yields Event:
        """
        for db_name, node in self._iter_new_children(stream, children):

            if not filter or node.type in filter:
                if node.type not in SCAN_TYPES:
                    node.subscribe_stream("data", reader, first_index=0)
                with AllowKill():
                    yield Event(type=EventType.NEW_NODE, node=node)

            if node.type in SCAN_TYPES:
                node.subscribe_existing_children_streams(
                    "children_list",
                    reader,
                    include_parent=True,
                    first_index=first_index,
                )
                node.subscribe_existing_children_streams(
                    "data",
                    reader,
                    include_parent=False,
                    first_index=0,
                    forbidden_types=SCAN_TYPES,  # TODO why?
                    allowed_types=filter,
                )
                node.subscribe_stream("data", reader, first_index=0)

    def _get_last_child(self, filter=None):
        """Get the last child added to the _children_list stream

        :param tuple filter: only these DataNode types are allowed (all by default)
        :returns 2-tuple: DataNode, active streams
        """
        # TODO: Why do we need to walk and
        #       not just return the last node
        #       from the _children_list stream?
        active_streams = dict()
        children_stream = self.create_associated_stream("children_list")
        first_index = children_stream.before_last_index()
        if first_index is None:
            return None, active_streams
        last_node = None
        for last_node in self.walk(
            filter, wait=False, active_streams=active_streams, first_index=first_index
        ):
            pass
        return last_node, active_streams

    def subscribe_stream(self, stream_suffix, reader, create=True, **kw):
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
        stream = self.create_stream(stream_name)
        reader.add_streams(stream, node=self, **kw)
        # print(stream_name, kw)

    def subscribe_initial_streams(self, reader, yield_data=False, **kw):
        """Subscribe to a minimal amount of streams so
        we can eventually get all nodes and events.

        :param DataStreamReader reader:
        :param bool yield_data:
        """
        if yield_data:
            # Always subscribe to the *_data stream
            # from the start (index 0)
            self.subscribe_stream("data", reader, first_index=0)

    def get_children_stream_index(self):
        """Get the node's stream ID in parent node's _children_list stream

        :returns bytes or None: stream ID
        """
        children_stream = self.parent.create_associated_stream("children_list")
        for index, raw in children_stream.rev_range():
            db_name = NewDataNodeEvent(raw=raw).db_name
            if db_name == self.db_name:
                break
        else:
            return None
        return index


class NewDataNodeEvent(streaming_events.StreamEvent):

    TYPE = b"NEW_DATA_NODE"
    DB_KEY = b"db_name"

    def init(self, db_name):
        self.db_name = db_name

    def _encode(self):
        raw = super()._encode()
        raw[self.DB_KEY] = self.encode_string(self.db_name)
        return raw

    def _decode(self, raw):
        super()._decode(raw)
        self.db_name = self.decode_string(raw[self.DB_KEY])


class DataNodeContainer(DataNode):
    def __init__(
        self, node_type, name, parent=None, connection=None, create=False, **keys
    ):
        DataNode.__init__(
            self,
            node_type,
            name,
            parent=parent,
            connection=connection,
            create=create,
            **keys,
        )
        db_name = name if parent is None else self.db_name
        self._children_stream = self.create_stream(f"{db_name}_children_list")

    def add_children(self, *children):
        """Publish new (direct) child in Redis
        """
        for child in children:
            self._children_stream.add_event(NewDataNodeEvent(child.db_name))

    def _iter_new_children(self, stream, node_dict):
        """
        :param DataStream stream:
        :param dict node_dict: node.db_name -> stream index
        :yields 2-tuple: (db_name(str), node(DataNode))
        """
        with settings.pipeline(stream):
            for (db_name, index), node in zip(
                node_dict.items(), self.get_nodes(*node_dict)
            ):
                if node is None:
                    # Why would that happen?
                    stream.remove(index)
                else:
                    yield db_name, node

    def _read_children_stream(self, stream_events=None):
        """Get direct children from Redis

        :param dict events: list((streamID, dict))
        :returns dict: db_name -> stream ID
        """
        if stream_events is None:
            stream_events = self._children_stream.range()
        return {
            NewDataNodeEvent.factory(raw).db_name: index for index, raw in stream_events
        }

    def children(self):
        """Iter over children.

        @return an iterator
        """
        for db_name, node in self._iter_new_children(
            self._children_stream, self._read_children_stream()
        ):
            yield node

    def _get_db_names(self):
        db_names = super()._get_db_names()
        db_names.append("%s_children_list" % self.db_name)
        return db_names

    def subscribe_initial_streams(self, reader, first_index=0, **kw):
        """Subscribe to a minimal amount of streams so
        we can eventually get all nodes and events.

        :param DataStreamReader reader:
        :param str or int first_index: Redis stream ID
        """
        # This is where the new node events are published:
        self.subscribe_children_list_streams(reader, first_index=first_index)

    def subscribe_children_list_streams(self, reader, **kw):
        """Subscribe to the _children_list stream (whether it exists or not)
        and all existing _children_list streams of the children.

        :param DataStreamReader reader:
        :param `**kw`: see `DataStreamReader.add_streams`
        """
        self.subscribe_stream("children_list", reader, **kw)
        # Do not add scan related streams
        # unless we listen to a scan node:
        # TODO: why?
        if self.type in SCAN_TYPES:
            forbidden_types = None
        else:
            forbidden_types = SCAN_TYPES
        self.subscribe_existing_children_streams(
            "children_list",
            reader,
            include_parent=False,
            forbidden_types=forbidden_types,
            **kw,
        )

    def subscribe_existing_children_streams(
        self,
        stream_suffix,
        reader,
        include_parent=False,
        forbidden_types=None,
        allowed_types=None,
        **kw,
    ):
        """Subscribe to the existing streams with a particular name,
        associated with all children of this node (recursive).

        :param str stream_suffix: streams to add have the name
                                  "{db_name}_{stream_suffix}"
        :param DataStreamReader reader:
        :param bool include_parent: including self in the children
        :param tuple forbidden_types: do not add streams associated to DataNode's
                                      with these node types (also not their children)
        :param tuple allowed_types: only these DataNode types are allowed (all by default)
        :param `**kw`: see `DataStreamReader.add_streams`
        """
        # Get existing stream names (only existing ones)
        if include_parent:
            pattern = f"{self.db_name}*_{stream_suffix}"
        else:
            pattern = f"{self.db_name}:*_{stream_suffix}"
        stream_names = self.search_redis(pattern)
        # TODO: Do we need hierarchical sorting?
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
                if node is not None and node.type in SCAN_TYPES
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
            if allowed_types and node.type not in allowed_types:
                continue
            if addstream(node.db_name):
                node.subscribe_stream(stream_suffix, reader, **kw)

    @staticmethod
    def _node_sort_key(db_name):
        """For hierarchical sort of node names
        """
        return db_name.count(":")
