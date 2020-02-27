# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
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

DataNode is the base class.
A data node has 3 Redis keys to represent it:

{db_name} -> Struct { name, db_name, node_type, parent=(parent db_name) }
{db_name}_info -> HashObjSetting, free dictionary
{db_name}_children -> DataStream, list of db names

The channel data node extends the structure above with:

{db_name}_channel -> DataStream, list of channel values

When a Lima channel is published:

--eh3
   |
   --scan1
     |
     --P201
       |
       -- frelon (LimaChannelDataNode - inherits from DataNode)

{db_name}_info -> HashObjSetting with some extra keys like reference: True
{db_name}_data -> QueueObjSetting, list of reference data ; first item is the 'live' reference
"""
import time
import datetime
import enum
import inspect
import pkgutil
import os
import weakref
import gevent
from sortedcontainers import SortedSet

from bliss.common.event import dispatcher
from bliss.common.utils import grouped
from bliss.common.greenlet_utils import protect_from_kill, AllowKill
from bliss.config.conductor import client
from bliss.config import settings
from bliss.config.streaming import DataStream, stream_setting_read, stream_decr_index
from bliss.data.events import Event, EventType


def is_zerod(node):
    return node.type == "channel" and len(node.shape) == 0


def to_timestamp(dt, epoch=None):
    if epoch is None:
        epoch = datetime.datetime(1970, 1, 1)
    td = dt - epoch
    return td.microseconds / float(10 ** 6) + td.seconds + td.days * 86400


SCAN_TYPES = set(("scan", "scan_group"))

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


def get_nodes(*db_names, **keys):
    connection = keys.get("connection")
    if connection is None:
        connection = client.get_redis_connection(db=1)
    pipeline = connection.pipeline()
    for db_name in db_names:
        data = settings.Struct(db_name, connection=pipeline)
        data.name
        data.node_type
    return [
        _get_node_object(
            None if node_type is None else node_type.decode(), db_name, None, connection
        )
        if name is not None
        else None
        for db_name, (name, node_type) in zip(db_names, grouped(pipeline.execute(), 2))
    ]


def get_session_node(session_name):
    """ Return a session node even if the session doesn't exist yet.
    This method is an helper if you want to follow a session with an DataNodeIterator.
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
    for node_name in settings.scan(
        "*_children_list", connection=client.get_redis_connection(db=1)
    ):
        if node_name.find(":") > -1:  # can't be a session node
            continue
        session_name = node_name.replace("_children_list", "")
        session_names.append(session_name)
    return get_nodes(*session_names)


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


class DataNodeIterator(object):
    def __init__(self, node):
        self.node = node

    @protect_from_kill
    def walk(
        self,
        filter=None,
        wait=True,
        stream_stop_reading_handler=None,
        stream_status=None,
        first_index="0",
    ):
        """Iterate over child nodes that match the `filter` argument

           If wait is True (default), the function blocks until a new node appears
        """
        if self.node is None:
            raise ValueError("Invalid node: node is None.")

        if isinstance(filter, str):
            filter = (filter,)
        elif filter:
            filter = tuple(filter)
        stream2nodes = weakref.WeakKeyDictionary()
        with stream_setting_read(
            block=0 if wait else None,
            stream_stop_reading_handler=stream_stop_reading_handler,
            stream_status=stream_status,
        ) as reader:
            yield from self._loop_on_event(
                reader, stream2nodes, filter, first_index, self._iter_new_child
            )

    def _loop_on_event(
        self,
        reader,
        stream2nodes,
        filter,
        first_index,
        new_child_func,
        new_data_event=False,
    ):
        children_stream = DataStream(
            f"{self.node.db_name}_children_list", connection=self.node.connection
        )
        reader.add_streams(children_stream, first_index=first_index)
        self._add_existing_children(
            reader,
            stream2nodes,
            f"{self.node.db_name}:",
            first_index,
            filter_scan=self.node.type not in SCAN_TYPES,
        )
        # In case the node is a scan we register also to the end of the scan
        if self.node.type in SCAN_TYPES:
            # also register for new data
            if new_data_event:
                data_stream_name = list(
                    settings.scan(
                        f"{self.node.db_name}:*_data", connection=self.node.connection
                    )
                )
                child_nodes = get_nodes(
                    *(name[: -len("_data")] for name in data_stream_name)
                )
                data_streams = {
                    DataStream(name, connection=self.node.connection): node
                    for name, node in zip(data_stream_name, child_nodes)
                }
                stream2nodes.update(data_streams)
                reader.add_streams(*data_streams, first_index=0)
            scan_data_stream = DataStream(
                f"{self.node.db_name}_data", connection=self.node.connection
            )
            stream2nodes[scan_data_stream] = self.node
            reader.add_streams(scan_data_stream, first_index=0, priority=1)
        elif new_data_event:
            data_stream = DataStream(
                f"{self.node.db_name}_data", connection=self.node.connection
            )
            stream2nodes[data_stream] = self.node
            reader.add_streams(data_stream, first_index=0)

        for stream, events in reader:
            if stream.name.endswith("_children_list"):
                children = {
                    value.get(self.node.CHILD_KEY).decode(): index
                    for index, value in events
                }
                new_stream = [
                    DataStream(f"{name}_children_list", connection=self.node.connection)
                    for name in children
                ]
                reader.add_streams(*new_stream, first_index=first_index)
                yield from new_child_func(
                    reader, stream2nodes, filter, stream, children, first_index
                )
            else:
                node = stream2nodes.get(stream)
                # New event on scan
                if node and node.type in SCAN_TYPES:
                    for index, values in events:
                        ev = values.get(node.EVENT_TYPE_KEY, "")
                        if ev == node.END_EVENT:
                            if new_data_event:
                                with AllowKill():
                                    yield Event(type=EventType.END_SCAN, node=node)
                            reader.remove_match_streams(f"{node.db_name}*")
                elif node is not None:
                    data = node.decode_raw_events(events)
                    with AllowKill():
                        yield Event(type=EventType.NEW_DATA, node=node, data=data)

    def _iter_new_child(
        self, reader, stream2nodes, filter, stream, children, first_index
    ):
        with settings.pipeline(stream):
            for (child_name, index), new_child in zip(
                children.items(), get_nodes(*children)
            ):
                if new_child is not None:
                    if filter is None or new_child.type in filter:
                        with AllowKill():
                            yield new_child
                    if new_child.type in SCAN_TYPES:
                        self._add_existing_children(
                            reader, stream2nodes, child_name, first_index
                        )
                        # Watching END scan event to clear all streams link with this scan
                        data_stream = DataStream(
                            f"{child_name}_data", connection=self.node.connection
                        )
                        stream2nodes[data_stream] = new_child
                        reader.add_streams(data_stream, first_index=0)

                else:
                    stream.remove(index)

    def _iter_new_child_with_data(
        self, reader, stream2nodes, filter, stream, children, first_index
    ):
        with settings.pipeline(stream):
            for (child_name, index), new_child in zip(
                children.items(), get_nodes(*children)
            ):
                if new_child is not None:
                    if filter is None or new_child.type in filter:
                        if new_child.type not in SCAN_TYPES:
                            data_stream = DataStream(
                                f"{child_name}_data", connection=self.node.connection
                            )
                            stream2nodes[data_stream] = new_child
                            reader.add_streams(data_stream, first_index=0)
                        with AllowKill():
                            yield Event(type=EventType.NEW_NODE, node=new_child)
                    if new_child.type in SCAN_TYPES:
                        # Need to listen all data streams already known
                        self._add_existing_children(
                            reader, stream2nodes, child_name, first_index
                        )
                        data_stream_names = list(
                            settings.scan(
                                f"{child_name}:*_data", connection=self.node.connection
                            )
                        )
                        new_sub_child_streams = list()
                        for sub_child_name, sub_child_node in zip(
                            data_stream_names,
                            get_nodes(*(x[: -len("_data")] for x in data_stream_names)),
                        ):
                            if sub_child_node is not None:
                                if filter is None or sub_child_node.type in filter:
                                    if sub_child_node.type in SCAN_TYPES:
                                        continue

                                    data_stream = DataStream(
                                        sub_child_name, connection=self.node.connection
                                    )
                                    stream2nodes[data_stream] = sub_child_node
                                    new_sub_child_streams.append(data_stream)
                        if new_sub_child_streams:
                            reader.add_streams(*new_sub_child_streams, first_index=0)

                        # In case of scan we must put the listening of it (its stream)
                        # At the ends of all streams of that branch
                        # otherwise SCAN_END arrive before other datas.
                        # so stream priority == 1
                        # Watching END scan event to clear all streams link with this scan
                        data_stream = DataStream(
                            f"{child_name}_data", connection=self.node.connection
                        )
                        stream2nodes[data_stream] = new_child
                        reader.add_streams(data_stream, first_index=0, priority=1)
                else:
                    stream.remove(index)

    def _add_existing_children(
        self, reader, stream2nodes, parent_db_name, first_index, filter_scan=False
    ):
        """
        Adding already known children stream for this parent
        """

        def depth_sort(s):
            return s.count(":")

        streams_names = sorted(
            settings.scan(
                f"{parent_db_name}*_children_list", connection=self.node.connection
            ),
            key=depth_sort,
        )
        if filter_scan:
            # We don't add scan nodes and underneath
            child_node = get_nodes(
                *(name[: -len("_children_list")] for name in streams_names)
            )
            scan_names = list(n.db_name for n in child_node if n.type in SCAN_TYPES)
            children_stream = list()
            for stream_name in streams_names:
                for scan_name in scan_names:
                    if stream_name.startswith(scan_name):
                        break
                else:
                    children_stream.append(
                        DataStream(stream_name, connection=self.node.connection)
                    )
        else:
            children_stream = (
                DataStream(stream_name, connection=self.node.connection)
                for stream_name in streams_names
            )
        reader.add_streams(*children_stream, first_index=first_index)

    @protect_from_kill
    def walk_from_last(
        self,
        filter=None,
        wait=True,
        include_last=True,
        stream_stop_reading_handler=None,
    ):
        """Walk from the last child node (see walk)
        """
        stream_status = dict()
        first_index = int(time.time() * 1000)
        if include_last:
            children_stream = DataStream(
                f"{self.node.db_name}_children_list", connection=self.node.connection
            )
            children = children_stream.rev_range(count=1)
            if children:
                last_index, _ = children[-1]
                last_index = stream_decr_index(last_index)
                last_node = None
                for last_node in self.walk(
                    filter,
                    wait=False,
                    stream_status=stream_status,
                    first_index=last_index,
                ):
                    pass
                if last_node is not None:
                    yield last_node
                    parent = last_node.parent
                    children_stream = DataStream(
                        f"{parent.db_name}_children_list",
                        connection=self.node.connection,
                    )
                    # look for the last_node
                    for index, child_info in children_stream.rev_range():
                        db_name = child_info.get(parent.CHILD_KEY, b"").decode()
                        if db_name == last_node.db_name:
                            break
                    else:
                        raise RuntimeError("Something weird happen")
                    first_index = index
        yield from self.walk(
            filter,
            wait=wait,
            stream_status=stream_status,
            first_index=first_index,
            stream_stop_reading_handler=stream_stop_reading_handler,
        )

    def walk_on_new_events(
        self, filter=None, stream_status=None, stream_stop_reading_handler=None
    ):
        """Yields future events"""
        yield from self.walk_events(
            filter,
            first_index=int(time.time() * 1000),
            stream_status=stream_status,
            stream_stop_reading_handler=stream_stop_reading_handler,
        )

    @protect_from_kill
    def walk_events(
        self,
        filter=None,
        first_index="0",
        stream_status=None,
        stream_stop_reading_handler=None,
    ):
        """Walk through child nodes, just like `walk` function,
        yielding node events (instance of `Event`) instead of node objects
        """
        if isinstance(filter, str):
            filter = (filter,)
        elif filter:
            filter = tuple(filter)
        stream2nodes = weakref.WeakKeyDictionary()
        with stream_setting_read(
            stream_status=stream_status,
            stream_stop_reading_handler=stream_stop_reading_handler,
        ) as reader:
            yield from self._loop_on_event(
                reader,
                stream2nodes,
                filter,
                first_index,
                self._iter_new_child_with_data,
                new_data_event=True,
            )


def set_ttl(db_name):
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
        self, node_type, name, parent=None, connection=None, create=False, **keys
    ):
        info_dict = keys.pop("info", {})
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
            self._struct = settings.Struct(db_name, connection=connection)
            self.__db_name = self._struct._proxy.name

        # node type cache
        self.node_type = node_type

    def _create_struct(self, db_name, name, node_type):
        struct = settings.Struct(db_name, connection=self.db_connection)
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
        return self._struct._cnx()

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
            parent = get_node(parent_name)
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
        redis_conn = client.get_redis_connection(db=1)
        pipeline = redis_conn.pipeline()
        for name in db_names:
            pipeline.expire(name, DataNode.default_time_to_live)
        pipeline.execute()
        if self._ttl_setter is not None:
            self._ttl_setter.detach()

    def _get_db_names(self):
        db_name = self.db_name
        children_queue_name = "%s_children_list" % db_name
        info_hash_name = "%s_info" % db_name
        db_names = [db_name, children_queue_name, info_hash_name]
        parent = self.parent
        if parent:
            db_names.extend(parent._get_db_names())
        return db_names


class DataNodeContainer(DataNode):
    CHILD_KEY = b"child"

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
        children_queue_name = "%s_children_list" % db_name
        self._children = DataStream(children_queue_name, connection=connection)

    def add_children(self, *children):
        for child in children:
            self._children.add({self.CHILD_KEY: child.db_name})

    def children(self):
        """Iter over children.

        @return an iterator
        """
        children = {
            values.get(self.CHILD_KEY).decode(): index
            for index, values in self._children.range()
        }
        with settings.pipeline(self._children):
            for (child_name, index), new_child in zip(
                children.items(), get_nodes(*children)
            ):
                if new_child is not None:
                    yield new_child
                else:
                    self._children.remove(index)  # clean
