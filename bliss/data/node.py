# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pkgutil
import inspect
import re
import datetime
import os

from bliss.common.event import dispatcher
from bliss.config.conductor import client
from bliss.config.settings import Struct, QueueSetting, HashObjSetting

def to_timestamp(dt, epoch=None):
    if epoch is None:
        epoch = datetime.datetime(1970,1,1)
    td = dt - epoch
    return td.microseconds / 10**6 + td.seconds + td.days * 86400

# From continuous scan
node_plugins = dict()
for importer, module_name, _ in pkgutil.iter_modules([os.path.join(os.path.dirname(__file__),'..','data')]):
    node_plugins[module_name] = importer

def _get_node_object(node_type, name, parent, connection, create=False):
    importer = node_plugins.get(node_type)
    if importer is None:
        return DataNode(node_type, name, parent, connection = connection, create = create)
    else:
        m = importer.find_module(node_type).load_module(node_type)
        classes = inspect.getmembers(m, lambda x: inspect.isclass(x) and issubclass(x, DataNode) and x!=DataNode)
        # there should be only 1 class inheriting from DataNode in the plugin
        klass = classes[0][-1]
        return klass(name, parent = parent, connection = connection, create = create)

def get_node(name, node_type = None, parent = None, connection = None):
    if connection is None:
        connection = client.get_cache(db=1)
    data = Struct(name, connection=connection)
    if node_type is None:
        node_type = data.node_type
        if node_type is None:       # node has been deleted
            return None

    return _get_node_object(node_type, name, parent, connection)

def _create_node(name, node_type = None, parent = None, connection = None):
    if connection is None:
        connection = client.get_cache(db=1)
    return _get_node_object(node_type, name, parent, connection, create=True)

def _get_or_create_node(name, node_type=None, parent=None, connection = None):
    if connection is None:
        connection = client.get_cache(db=1)
    db_name = DataNode.exists(name, parent, connection)
    if db_name:
        return get_node(db_name, connection=connection)
    else:
        return _create_node(name, node_type, parent, connection)

class DataNodeIterator(object):
    NEW_CHILD_REGEX = re.compile("^__keyspace@.*?:(.*)_children_list$")
    NEW_CHANNEL_REGEX = re.compile("^__keyspace@.*?:(.*)_channels$")
    NEW_CHILD_EVENT,NEW_CHANNEL_EVENT,NEW_DATA_IN_CHANNEL_EVENT = range(3)
    
    def __init__(self, node,last_child_id = None):
        self.node = node
        self.last_child_id = dict() if last_child_id is None else last_child_id
        self.zerod_channel_event = dict()

    def walk(self, filter=None, wait=True):
        """Iterate over child nodes that match the `filter` argument

           If wait is True (default), the function blocks until a new node appears
        """ 
        if isinstance(filter, (str,unicode)):
            filter = (filter, )
        else:
            filter = tuple(filter)
        
        if wait:
            pubsub = self.children_event_register()

        db_name = self.node.db_name()
        self.last_child_id[db_name]=0

        if filter is None or self.node.type() in filter:
            yield self.node

        for i, child in enumerate(self.node.children()):
            iterator = DataNodeIterator(child,last_child_id=self.last_child_id)
            for n in iterator.walk(filter, wait=False):
                self.last_child_id[db_name] = i+1
                if filter is None or n.type() in filter:
                    yield n
        if wait:
            #yield from self.wait_for_event(pubsub)
            for event_type,value in self.wait_for_event(pubsub,filter):
                if event_type is self.NEW_CHILD_EVENT:
                    yield value

    def walk_from_last(self, filter=None, wait=True):
        """Walk from the last child node (see walk)
        """
        pubsub = self.children_event_register()
        last_node = None
        for last_node in self.walk(filter, wait=False):
            pass

        if last_node is not None:
            yield last_node

        for event_type, node in self.wait_for_event(pubsub, filter=filter):
            if event_type is self.NEW_CHILD_EVENT:
                yield node

    def walk_events(self, filter=None):
        """Walk through child nodes, just like `walk` function, yielding node events
        (like NEW_CHILD_EVENT or NEW_DATA_IN_CHANNEL_EVENT) instead of node objects
        """
        pubsub = self.children_event_register()
 
        for node in self.walk(filter, wait=False):
            self.child_register_new_data(node, pubsub)
            yield self.NEW_CHILD_EVENT, node 

        for event_type, event_data in self.wait_for_event(pubsub, filter=filter):
            yield event_type, event_data

    def children_event_register(self):
        redis = self.node.db_connection
        pubsub = redis.pubsub()
        pubsub.psubscribe("__keyspace@1__:%s*_children_list" % self.node.db_name())
        pubsub.psubscribe("__keyspace@1__:%s*_channels" % self.node.db_name())
        return pubsub
    
    def child_register_new_data(self,child_node,pubsub):
        if child_node.type() == 'zerod':
            for channel_name in child_node.channels_name():
                zerod_db_name = child_node.db_name()
                event_key = "__keyspace@1__:%s_%s" % (zerod_db_name, channel_name)
                pubsub.subscribe(event_key)
                self.zerod_channel_event[event_key] = zerod_db_name
        else:
            pass                # warning not managed yet

    def zerod_channels_events(self, pubsub, zerod, filter):
        events = list()
        print filter, zerod.type()
        filter = filter is None or zerod.type() in filter

        for channel_name in zerod.channels_name():
            zerod_db_name = zerod.db_name()
            event_key = "__keyspace@1__:%s_%s" % (zerod_db_name,channel_name)
            if event_key in self.zerod_channel_event:
                continue
            else:
                if filter:
                    pubsub.subscribe(event_key)
                    self.zerod_channel_event[event_key] = zerod_db_name
                    events.append((self.NEW_DATA_IN_CHANNEL_EVENT, (zerod, channel_name)))

        if filter and events:
            events.insert(0, (self.NEW_CHANNEL_EVENT,zerod))

        return events

    def wait_for_event(self, pubsub, filter = None):
        if isinstance(filter, (str,unicode)):
            filter = (filter, )
        else:
            filter = tuple(filter)

        for msg in pubsub.listen():
            if msg['data'] == 'rpush':
                channel = msg['channel']
                new_child_event = DataNodeIterator.NEW_CHILD_REGEX.match(channel)
                if new_child_event:
                    parent_db_name = new_child_event.groups()[0]
                    parent_node = get_node(parent_db_name)
                    first_child = self.last_child_id.setdefault(parent_db_name, 0)
                    for i, child in enumerate(parent_node.children(first_child, -1)):
                        self.last_child_id[parent_db_name] = first_child + i + 1
                        if filter is None or child.type() in filter:
                            yield self.NEW_CHILD_EVENT,child
                        if child.type() == 'zerod':
                            zerod = child
                            for event in self.zerod_channels_events(pubsub, zerod, filter):
                                yield event
                else:
                    new_channel_event = DataNodeIterator.NEW_CHANNEL_REGEX.match(channel)
                    if new_channel_event:
                        zerod_db_name = new_channel_event.groups()[0]
                        zerod = get_node(zerod_db_name)
                        for event in self.zerod_channels_events(pubsub, zerod, filter):
                            yield event
                    else:
                        new_data_in_channel = self.zerod_channel_event.get(channel)
                        if new_data_in_channel is not None:
                            zerod = get_node(new_data_in_channel)
                            db_name = zerod.db_name() + '_'
                            channel_name = channel.split(db_name)[-1]
                            if filter is None or zerod.type() in filter:
                                yield self.NEW_DATA_IN_CHANNEL_EVENT,(zerod,channel_name)

class _TTL_setter(object):
    def __init__(self,db_name):
        self._db_name = db_name
        self._disable = False

    def disable(self):
        self._disable = True

    def __del__(self):
        if not self._disable:
            node = get_node(self._db_name)
            if node is not None:
                node.set_ttl()

class DataNode(object):
    default_time_to_live = 24*3600 # 1 day
    
    @staticmethod
    def exists(name,parent = None, connection = None):
        if connection is None:
            connection = client.get_cache(db=1)
        db_name = '%s:%s' % (parent.db_name(),name) if parent else name
        return db_name if connection.exists(db_name) else None

    def __init__(self,node_type,name,parent = None, connection = None, create=False):
        if connection is None:
            connection = client.get_cache(db=1)
        db_name = '%s:%s' % (parent.db_name(),name) if parent else name
        self._data = Struct(db_name,
                            connection=connection)
        children_queue_name = '%s_children_list' % db_name
        self._children = QueueSetting(children_queue_name,
                                      connection=connection)
        info_hash_name = '%s_info' % db_name
        self._info = HashObjSetting(info_hash_name,
                                    connection=connection)
        self.db_connection = connection
        
        if create:
            self._data.name = name
            self._data.db_name = db_name
            self._data.node_type = node_type
            if parent: 
                self._data.parent = parent.db_name()
                parent.add_children(self)
            self._ttl_setter = _TTL_setter(self.db_name())
        else:
            self._ttl_setter = None

    def db_name(self):
        return self._data.db_name

    def name(self):
        return self._data.name

    def type(self):
        return self._data.node_type

    def iterator(self):
        return DataNodeIterator(self)

    def add_children(self,*child):
        if len(child) > 1:
            children_no = self._children.extend([c.db_name() for c in child])
        else:
            children_no = self._children.append(child[0].db_name())

    def connect(self, signal, callback):
        dispatcher.connect(callback, signal, self)

    def parent(self):
        parent_name = self._data.parent
        if parent_name:
            parent = get_node(parent_name)
            if parent is None:  # clean
                del self._data.parent
            return parent

    #@brief iter over children
    #@return an iterator
    #@param from_id start child index
    #@param to_id last child index
    def children(self,from_id = 0,to_id = -1):
        for child_name in self._children.get(from_id,to_id):
            new_child = get_node(child_name)
            if new_child is not None:
                yield new_child
            else:
                self._children.remove(child_name) # clean

    def last_child(self):
        return get_node(self._children.get(-1))

    def set_info(self,key,values):
        self._info[keys] = values
        if self._ttl > 0:
            self._info.ttl(self._ttl)

    def info_iteritems(self):
        return self._info.iteritems()

    def info_get(self,name):
        return self._info.get(name)

    def data_update(self,keys):
        self._data.update(keys)

    def set_ttl(self):
        db_names = set(self._get_db_names())
        self._set_ttl(db_names)
        if self._ttl_setter is not None:
            self._ttl_setter.disable()
        
    @staticmethod
    def _set_ttl(db_names):
        redis_conn = client.get_cache(db=1)
        pipeline = redis_conn.pipeline()
        for name in db_names:
            pipeline.expire(name,DataNode.default_time_to_live)
        pipeline.execute()

    def _get_db_names(self):
        db_name = self.db_name()
        children_queue_name = '%s_children_list' % db_name
        info_hash_name = '%s_info' % db_name
        db_names = [db_name,children_queue_name,info_hash_name]
        parent = self.parent()
        if parent:
            db_names.extend(parent._get_db_names())
        return db_names

    def store(self, signal, event_dict):
        pass
