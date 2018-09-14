# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
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
import inspect
import pkgutil
import os
import re
import weakref

from bliss.common.event import dispatcher
from bliss.common.utils import grouped
from bliss.config.conductor import client
from bliss.config.settings import Struct, QueueSetting, HashObjSetting


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
    node_plugins[node_type] = module_name


def _get_node_object(node_type, name, parent, connection, create=False, **keys):
    module_name = node_plugins.get(node_type)
    if module_name is None:
        return DataNodeContainer(
            node_type, name, parent, connection=connection, create=create, **keys
        )
    else:
        m = __import__(module_name, globals(), locals(), [""], -1)
        classes = inspect.getmembers(
            m,
            lambda x: inspect.isclass(x)
            and issubclass(x, DataNode)
            and x not in (DataNode, DataNodeContainer),
        )
        # there should be only 1 class inheriting from DataNode in the plugin
        klass = classes[0][-1]
        return klass(name, parent=parent, connection=connection, create=create, **keys)


def get_node(db_name, connection=None):
    return get_nodes(db_name, connection=connection)[0]

def get_nodes(*db_names, **keys):
    connection = keys.get("connection")
    if connection is None:
        connection = client.get_cache(db=1)
    pipeline = connection.pipeline()
    for db_name in db_names:
        data = Struct(db_name, connection=pipeline)
        data.name
        data.node_type
    return [
        _get_node_object(node_type, db_name, None, connection)
        if name is not None
        else None
        for db_name, (name, node_type) in zip(db_names, grouped(pipeline.execute(), 2))
    ]


def _create_node(name, node_type=None, parent=None, connection=None, **keys):
    if connection is None:
        connection = client.get_cache(db=1)
    return _get_node_object(node_type, name, parent, connection, create=True, **keys)


def _get_or_create_node(name, node_type=None, parent=None, connection=None, **keys):
    if connection is None:
        connection = client.get_cache(db=1)
    db_name = DataNode.exists(name, parent, connection)
    if db_name:
        return get_node(db_name, connection=connection)
    else:
        return _create_node(name, node_type, parent, connection, **keys)


class DataNodeIterator(object):
    NEW_CHILD_REGEX = re.compile("^__keyspace@.*?:(.*)_children_list$")
    NEW_DATA_IN_CHANNEL_REGEX = re.compile("^__keyspace@.*?:(.*)_data$")
    NEW_CHILD_EVENT, NEW_DATA_IN_CHANNEL_EVENT = range(2)

    def __init__(self, node, last_child_id=None):
        self.node = node
        self.last_child_id = dict() if last_child_id is None else last_child_id

    def walk(self, filter=None, wait=True, ready_event=None):
        """Iterate over child nodes that match the `filter` argument

           If wait is True (default), the function blocks until a new node appears
        """
        if self.node is None:
            raise ValueError("Invalid node: node is None.")

        if isinstance(filter, (str, unicode)):
            filter = (filter,)
        elif filter:
            filter = tuple(filter)

        if wait:
            pubsub = self.children_event_register()

        db_name = self.node.db_name
        self.last_child_id[db_name] = 0

        if filter is None or self.node.type in filter:
            yield self.node

        if isinstance(self.node, DataNodeContainer):
            for i, child in enumerate(self.node.children()):
                iterator = DataNodeIterator(child, last_child_id=self.last_child_id)
                for n in iterator.walk(filter, wait=False):
                    self.last_child_id[db_name] = i + 1
                    if filter is None or n.type in filter:
                        yield n
        if wait:
            if ready_event is not None:
                ready_event.set()

            # yield from self.wait_for_event(pubsub)
            for event_type, value in self.wait_for_event(pubsub, filter):
                if event_type is self.NEW_CHILD_EVENT:
                    yield value

    def walk_from_last(
        self, filter=None, wait=True, include_last=True, ready_event=None
    ):
        """Walk from the last child node (see walk)
        """
        pubsub = self.children_event_register()
        last_node = None
        for last_node in self.walk(filter, wait=False):
            pass

        if last_node is not None:
            if include_last:
                yield last_node

        if wait:
            if ready_event is not None:
                ready_event.set()

            for event_type, node in self.wait_for_event(pubsub, filter=filter):
                if event_type is self.NEW_CHILD_EVENT:
                    yield node

    def walk_events(self, filter=None, ready_event=None):
        """Walk through child nodes, just like `walk` function, yielding node events
        (like NEW_CHILD_EVENT or NEW_DATA_IN_CHANNEL_EVENT) instead of node objects
        """
        pubsub = self.children_event_register()

        for node in self.walk(filter, wait=False):
            yield self.NEW_CHILD_EVENT, node
            if DataNode.exists("%s_data" % node.db_name):
                yield self.NEW_DATA_IN_CHANNEL_EVENT, node

        if ready_event is not None:
            ready_event.set()

        for event_type, event_data in self.wait_for_event(pubsub, filter=filter):
            yield event_type, event_data

    def children_event_register(self):
        redis = self.node.db_connection
        pubsub = redis.pubsub()
        pubsub.psubscribe("__keyspace@1__:%s*_children_list" % self.node.db_name)
        pubsub.psubscribe("__keyspace@1__:%s*_data" % self.node.db_name)
        return pubsub

    def wait_for_event(self, pubsub, filter=None):
        if isinstance(filter, (str, unicode)):
            filter = (filter,)
        elif filter:
            filter = tuple(filter)

        for msg in pubsub.listen():
            if msg["data"] == "rpush":
                channel = msg["channel"]
                new_child_event = DataNodeIterator.NEW_CHILD_REGEX.match(channel)
                if new_child_event:
                    parent_db_name = new_child_event.groups()[0]
                    parent_node = get_node(parent_db_name)
                    first_child = self.last_child_id.setdefault(parent_db_name, 0)
                    for i, child in enumerate(parent_node.children(first_child, -1)):
                        self.last_child_id[parent_db_name] = first_child + i + 1
                        if filter is None or child.type in filter:
                            yield self.NEW_CHILD_EVENT, child
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
                            yield self.NEW_DATA_IN_CHANNEL_EVENT, channel_node
            elif msg["data"] == "lset":
                channel = msg["channel"]
                new_channel_event = DataNodeIterator.NEW_DATA_IN_CHANNEL_REGEX.match(
                    channel
                )
                if new_channel_event:
                    channel_db_name = new_channel_event.group(1)
                    channel_node = get_node(channel_db_name)
                    if channel_node and (filter is None or channel_node.type in filter):
                        yield self.NEW_DATA_IN_CHANNEL_EVENT, channel_node


class _TTL_setter(object):
    def __init__(self, db_name):
        self._db_name = db_name
        self._disable = False

    def disable(self):
        self._disable = True

    def __del__(self):
        if self._disable:
            return
        try:
            node = get_node(self._db_name)
            if node is not None:
                node.set_ttl()
        except TypeError:
            pass


class DataNode(object):
    default_time_to_live = 24 * 3600  # 1 day

    @staticmethod
    def exists(name, parent=None, connection=None):
        if connection is None:
            connection = client.get_cache(db=1)
        db_name = "%s:%s" % (parent.db_name, name) if parent else name
        return db_name if connection.exists(db_name) else None

    def __init__(
        self, node_type, name, parent=None, connection=None, create=False, **keys
    ):
        info_dict = keys.pop("info", {})
        if connection is None:
            connection = client.get_cache(db=1)
        db_name = "%s:%s" % (parent.db_name, name) if parent else name
        self._data = Struct(db_name, connection=connection)
        info_hash_name = "%s_info" % db_name
        self._info = HashObjSetting(info_hash_name, connection=connection)
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
            self._ttl_setter = _TTL_setter(self.db_name)
        else:
            self.__new_node = False
            self._ttl_setter = None

    @property
    def db_name(self):
        return self._data.db_name

    @property
    def name(self):
        return self._data.name

    @property
    def type(self):
        return self._data.node_type

    @property
    def iterator(self):
        return DataNodeIterator(self)

    @property
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

    def set_ttl(self):
        db_names = set(self._get_db_names())
        redis_conn = client.get_cache(db=1)
        pipeline = redis_conn.pipeline()
        for name in db_names:
            pipeline.expire(name, DataNode.default_time_to_live)
        pipeline.execute()
        if self._ttl_setter is not None:
            self._ttl_setter.disable()

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

        children_queue_name = "%s_children_list" % self.db_name
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
