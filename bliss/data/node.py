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
{db_name}_children -> QueueSetting, list of db names

The channel data node extends the structure above with:

{db_name}_channel -> QueueSetting, list of channel values

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
import datetime
import enum
import inspect
import pkgutil
import os
import re
import weakref
import gevent

from bliss.common.event import dispatcher
from bliss.common.utils import grouped
from bliss.common.greenlet_utils import protect_from_kill, AllowKill
from bliss.config.conductor import client
from bliss.config.settings import Struct, QueueSetting, HashObjSetting, scan


def is_zerod(node):
    return node.type == "channel" and len(node.shape) == 0


def to_timestamp(dt, epoch=None):
    if epoch is None:
        epoch = datetime.datetime(1970, 1, 1)
    td = dt - epoch
    return td.microseconds / float(10 ** 6) + td.seconds + td.days * 86400


# make list of available plugins for generating DataNode objects
node_plugins = dict()
for importer, module_name, _ in pkgutil.iter_modules(
    [os.path.dirname(__file__)], prefix="bliss.data."
):
    node_type = module_name.replace("bliss.data.", "")
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
                and x not in (DataNode, DataNodeContainer),
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
        data = Struct(db_name, connection=pipeline)
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
    NEW_CHILD_REGEX = re.compile(r"^__keyspace@.*?:(.*)_children_list$")
    NEW_DATA_IN_CHANNEL_REGEX = re.compile(r"^__keyspace@.*?:(.*)_data$")
    SCAN_EVENTS_REGEX = re.compile(r"^__scans_events__:(.+)$")
    EVENTS = enum.Enum("event", "NEW_NODE NEW_DATA_IN_CHANNEL END_SCAN EXTERNAL_EVENT")

    def __init__(self, node, last_child_id=None, wakeup_fd=None):
        self.node = node
        self.last_child_id = dict() if last_child_id is None else last_child_id
        self.wakeup_fd = wakeup_fd

    @protect_from_kill
    def walk(self, filter=None, wait=True, ready_event=None):
        """Iterate over child nodes that match the `filter` argument

           If wait is True (default), the function blocks until a new node appears
        """
        if self.node is None:
            raise ValueError("Invalid node: node is None.")

        if isinstance(filter, str):
            filter = (filter,)
        elif filter:
            filter = tuple(filter)

        if wait:
            pubsub = self.children_event_register()

        db_name = self.node.db_name
        self.last_child_id[db_name] = 0

        if filter is None or self.node.type in filter:
            with AllowKill():
                yield self.node

        data_node_2_children = self._get_grandchildren(db_name)
        all_nodes_names = list()
        for children_name in data_node_2_children.values():
            all_nodes_names.extend(children_name)

        data_nodes = {
            name: node
            for name, node in zip(all_nodes_names, get_nodes(*all_nodes_names))
            if node is not None
        }
        # should be convert to yield from
        pipeline = self.node.db_connection.pipeline()
        for n in self.__internal_walk(
            db_name, data_nodes, data_node_2_children, filter, pipeline
        ):
            with AllowKill():
                yield n
        pipeline.execute()

        if ready_event is not None:
            ready_event.set()

        if wait:
            # yield from self.wait_for_event(pubsub)
            for event_type, value in self.wait_for_event(pubsub, filter):
                if event_type is self.EVENTS.NEW_NODE:
                    yield value

    def __internal_walk(
        self, db_name, data_nodes, data_node_2_children, filter, pipeline
    ):
        for i, child_name in enumerate(data_node_2_children.get(db_name, list())):
            self.last_child_id[db_name] = i + 1
            child_node = data_nodes.get(child_name)
            if child_node is None:
                pipeline.lrem("%s_children_list" % db_name, 0, child_name)
                continue
            if filter is None or child_node.type in filter:
                yield child_node
            # walk to the tree leaf
            for n in self.__internal_walk(
                child_name, data_nodes, data_node_2_children, filter, pipeline
            ):
                yield n

    def _get_grandchildren(self, db_name):
        # grouped all redis request here and cache them
        # get all children queue
        children_queue = [
            x
            for x in scan(
                "%s*_children_list" % db_name, connection=self.node.db_connection
            )
        ]
        # get all the container node name
        data_node_containers_names = [
            x[: x.rfind("_children_list")] for x in children_queue
        ]
        # get all children for all container
        pipeline = self.node.db_connection.pipeline()
        [pipeline.lrange(name, 0, -1) for name in children_queue]
        data_node_2_children = {
            node_name: [child.decode() for child in children]
            for node_name, children in zip(
                data_node_containers_names, pipeline.execute()
            )
        }
        return data_node_2_children

    @protect_from_kill
    def walk_from_last(
        self, filter=None, wait=True, include_last=True, ready_event=None
    ):
        """Walk from the last child node (see walk)
        """
        if wait:
            pubsub = self.children_event_register()

        last_node = None
        if include_last:
            for last_node in self.walk(filter, wait=False):
                pass
        else:
            self.jumpahead()

        if last_node is not None:
            if include_last:
                yield last_node

        if ready_event is not None:
            ready_event.set()

        if wait:
            for event_type, node in self.wait_for_event(pubsub, filter=filter):
                if event_type is self.EVENTS.NEW_NODE:
                    yield node

    def jumpahead(self):
        """Move the iterator to the last available node so that only new nodes will be concerned"""
        db_name = self.node.db_name
        data_node_2_children = self._get_grandchildren(db_name)
        self.last_child_id = {
            db_name: len(children) for db_name, children in data_node_2_children.items()
        }

    def walk_on_new_events(self, filter=None):
        """Yields future events"""

        pubsub = self.children_event_register()

        self.jumpahead()

        for event_type, event_data in self.wait_for_event(pubsub, filter=filter):
            yield event_type, event_data

    def walk_events(self, filter=None, ready_event=None):
        """Walk through child nodes, just like `walk` function, yielding node events
        (like EVENTS.NEW_NODE or EVENTS.NEW_DATA_IN_CHANNEL) instead of node objects
        """
        pubsub = self.children_event_register()

        for node in self.walk(filter, wait=False):
            yield self.EVENTS.NEW_NODE, node
            if DataNode.exists("%s_data" % node.db_name):
                yield self.EVENTS.NEW_DATA_IN_CHANNEL, node

        if ready_event is not None:
            ready_event.set()

        for event_type, event_data in self.wait_for_event(pubsub, filter=filter):
            yield event_type, event_data

    def children_event_register(self):
        redis = self.node.db_connection
        pubsub = redis.pubsub()
        pubsub.psubscribe("__keyspace@1__:%s*_children_list" % self.node.db_name)
        pubsub.psubscribe("__keyspace@1__:%s*_data" % self.node.db_name)
        pubsub.psubscribe("__scans_events__:%s:*" % self.node.db_name)
        return pubsub

    @protect_from_kill
    def wait_for_event(self, pubsub, filter=None):
        if isinstance(filter, str):
            filter = (filter,)
        elif filter:
            filter = tuple(filter)

        read_fds = [pubsub.connection._sock]
        if self.wakeup_fd:
            read_fds.append(self.wakeup_fd)

        while True:
            msg = pubsub.get_message()
            with AllowKill():
                if msg is None:
                    read_event, _, _ = gevent.select.select(read_fds, [], [])
                    if self.wakeup_fd in read_event:
                        os.read(self.wakeup_fd, 16 * 1024)  # flush event stream
                        yield self.EVENTS.EXTERNAL_EVENT, None

            if msg is None:
                continue

            if msg["type"] != "pmessage":
                continue
            data = msg["data"].decode()
            channel = msg["channel"].decode()
            if data == "rpush":
                new_child_event = DataNodeIterator.NEW_CHILD_REGEX.match(channel)
                if new_child_event:
                    parent_db_name = new_child_event.groups()[0]
                    parent_node = get_node(parent_db_name)
                    first_child = self.last_child_id.setdefault(parent_db_name, 0)
                    for i, child in enumerate(parent_node.children(first_child, -1)):
                        self.last_child_id[parent_db_name] = first_child + i + 1
                        if filter is None or child.type in filter:
                            yield self.EVENTS.NEW_NODE, child
                else:
                    new_channel_event = DataNodeIterator.NEW_DATA_IN_CHANNEL_REGEX.match(
                        channel
                    )
                    if new_channel_event:
                        channel_db_name = new_channel_event.group(1)
                        channel_node = get_node(channel_db_name)
                        if channel_node and (
                            filter is None or channel_node.type in filter
                        ):
                            yield self.EVENTS.NEW_DATA_IN_CHANNEL, channel_node
            elif data == "lset":
                new_channel_event = DataNodeIterator.NEW_DATA_IN_CHANNEL_REGEX.match(
                    channel
                )
                if new_channel_event:
                    channel_db_name = new_channel_event.group(1)
                    channel_node = get_node(channel_db_name)
                    if channel_node and (filter is None or channel_node.type in filter):
                        yield self.EVENTS.NEW_DATA_IN_CHANNEL, channel_node
            elif data == "lrem":
                del_child_event = DataNodeIterator.NEW_CHILD_REGEX.match(channel)
                if del_child_event:
                    db_name = del_child_event.groups()[0]
                    last_child = self.last_child_id.get(db_name, 0)
                    if last_child > 0:
                        last_child -= 1
                        self.last_child_id[db_name] = last_child
                    else:  # remove entry
                        self.last_child_id.pop(db_name, None)
            elif data == "END":
                scan_event = DataNodeIterator.SCAN_EVENTS_REGEX.match(channel)
                if scan_event:
                    scan_db_name = scan_event.group(1)
                    scan_node = get_node(scan_db_name)
                    if scan_node and (filter is None or scan_node.type in filter):
                        yield self.EVENTS.END_SCAN, scan_node


def set_ttl(db_name):
    node = get_node(db_name)
    if node is not None:
        node.set_ttl()


class DataNode(object):
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
        self._data = Struct(db_name, connection=connection)
        info_hash_name = "%s_info" % db_name
        self._info = HashObjSetting(info_hash_name, connection=connection)
        if info_dict:
            info_dict["node_name"] = db_name
            self._info.update(info_dict)

        self.db_connection = connection

        if create:
            self.__new_node = True
            self._data.name = name
            self._data.db_name = db_name
            self._data.node_type = node_type
            if parent:
                self._data.parent = parent.db_name
                parent.add_children(self)
            self._ttl_setter = weakref.finalize(self, set_ttl, self.db_name)
        else:
            self.__new_node = False
            self._ttl_setter = None

        # node type cache
        self.node_type = node_type

    @property
    @protect_from_kill
    def db_name(self):
        return self._data._proxy.name

    @property
    def connection(self):
        return self._data._cnx()

    @property
    @protect_from_kill
    def name(self):
        return self._data.name

    @property
    @protect_from_kill
    def fullname(self):
        return self._data.fullname

    @property
    @protect_from_kill
    def type(self):
        if self.node_type is not None:
            return self.node_type
        return self._data.node_type

    @property
    def iterator(self):
        return DataNodeIterator(self)

    @property
    @protect_from_kill
    def parent(self):
        parent_name = self._data.parent
        if parent_name:
            parent = get_node(parent_name)
            if parent is None:  # clean
                del self._data.parent
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
            **keys
        )
        db_name = name if parent is None else self.db_name
        children_queue_name = "%s_children_list" % db_name
        self._children = QueueSetting(children_queue_name, connection=connection)

    def add_children(self, *child):
        if len(child) > 1:
            self._children.extend([c.db_name for c in child])
        else:
            self._children.append(child[0].db_name)

    def children(self, from_id=0, to_id=-1):
        """Iter over children.

        @return an iterator
        @param from_id start child index
        @param to_id last child index
        """
        children_names = self._children.get(from_id, to_id)
        try:
            # replace connection with pipeline
            saved_db_connection = self._children._cnx
            pipeline = saved_db_connection().pipeline()
            self._children._cnx = weakref.ref(pipeline)
            for child_name, new_child in zip(
                children_names, get_nodes(*children_names)
            ):
                if new_child is not None:
                    yield new_child
                else:
                    self._children.remove(child_name)  # clean
            pipeline.execute()
        finally:
            self._children._cnx = saved_db_connection

    @property
    def last_child(self):
        return get_node(self._children.get(-1))
