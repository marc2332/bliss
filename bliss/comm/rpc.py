# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
pythonic RPC implementation using zerorpc.

Server example::

    from bliss.comm.rpc import Server

    class Car(object):
        '''A silly car. This doc should show up in the client'''

        wheels = 4

        def __init__(self, color, horsepower):
            self.horsepower = horsepower
            self.__position = 0

        @property
        def position(self):
            '''this doc should show up in the client too'''
            return self.__position

        @staticmethod
        def horsepower_to_watts(horsepower):
            '''so should this'''
             return horsepower * 735.499

        @property
        def watts(self):
            '''also this one'''
            return self.horsepower_to_watts(self.horsepower)

        def move(self, value, relative=False):
            '''needless to say this one as well'''
            if relative:
                 self.__position += value
            else:
                 self.__position = value

    car = Car('yellow', 120)
    server = Server(car)
    server.bind('tcp://0:8989')
    server.run()


Client::

    from bliss.comm.rpc import Client

    car = Client('tcp://localhost:8989')

    assert car.__doc__
    assert type(car).__name__ == 'Car'
    assert car.position == 0
    assert car.horsepower == 120.0
    assert car.horsepower_to_watts(1) == 735.499
    assert car.watts == 120 * 735.499
    car.move(12)
    assert car.position == 12
    car.move(10, relative=True)
    assert car.position == 22

"""

import inspect
import logging
import weakref

import louie
import gevent.queue

from bliss.common import zerorpc
from bliss.common.utils import StripIt


SPECIAL_METHODS = set((
    'new', 'init', 'del', 'hash', 'class', 'dict', 'sizeof', 'weakref',
    'metaclass', 'subclasshook',
    'getattr', 'setattr', 'delattr', 'getattribute',
    'instancecheck', 'subclasscheck',
    'reduce', 'reduce_ex', 'getstate', 'setstate'))


class ServerError(Exception):
    pass


def _discover_object(obj):
    members = {}
    otype = type(obj)
    for name, member in inspect.getmembers(otype):
        info = dict(name=name, doc=inspect.getdoc(member))
        if callable(member):
            if inspect.ismethod(member) and member.__self__ == otype:
                member_type = 'classmethod'
            elif inspect.isfunction(member):
                member_type = 'staticmethod'
            else:
                member_type = 'method'
        elif inspect.isdatadescriptor(member):
            member_type = 'attribute'
        else:
            member_type = 'attribute'
            info['doc'] = None
        info['type'] = member_type
        members[name] = info

    for name in dir(obj):
        if name.startswith('__') or name in members:
            continue
        member = getattr(obj, name)
        info = dict(name=name, doc=inspect.getdoc(member))
        if callable(member):
            member_type = 'method'
        else:
            member_type = 'attribute'
            info['doc'] = None
        info['type'] = member_type
        members[name] = info

    return dict(name=otype.__name__,
                module=inspect.getmodule(obj).__name__,
                doc=inspect.getdoc(obj),
                members=members)


class _ServerObject(object):

    def __init__(self, obj):
        self._object = obj
        self._log = logging.getLogger('zerorpc.' + type(obj).__name__)
        self._metadata = _discover_object(obj)

    def __dir__(self):
        result = ['zerorpc_call__']
        for name, info in self._metadata['members'].items():
            if 'method' in info['type']:
                result.append(name)
        return result

    def __getattr__(self, name):
        return getattr(self._object, name)

    def zerorpc_call__(self, code, args, kwargs):
        if code == 'introspect':
            self._log.debug("zerorpc 'introspect'")
            return self._metadata
        else:
            name = args[0]
            if code == 'call':
                value = getattr(self._object, name)(*args[1:], **kwargs)
                self._log.debug("zerorpc call %s() = %r", name, StripIt(value))
                return value
            elif code == 'getattr':
                value = getattr(self._object, name)
                self._log.debug("zerorpc get %s = %r", name, StripIt(value))
                return value
            elif code == 'setattr':
                value = args[1]
                self._log.debug("zerorpc set %s = %r", name, StripIt(value))
                return setattr(self._object, name, value)
            elif code == 'delattr':
                self._log.debug("zerorpc del %s", name)
                return delattr(self._object, name)
            else:
                raise ServerError('Unknown call type {0!r}'.format(code))


class _StreamServerObject(_ServerObject):

    def __init__(self, obj):
        super(_StreamServerObject, self).__init__(obj)
        self._metadata['stream'] = True
        self._streams = weakref.WeakSet()
        self._dispatchers = weakref.WeakSet()

    @zerorpc.stream
    def zerorpc_stream__(self):
        yield (None, None)  # Signal the stream has started
        stream = gevent.queue.Queue()
        dispatcher = lambda value, signal: stream.put((signal, value))
        self._streams.add(stream)
        self._dispatchers.add(dispatcher)
        louie.connect(dispatcher, sender=self._object)
        debug = self._log.debug
        for message in stream:
            if message is None:
                break
            signal, value = message
            debug('streaming signal=%r value=%s', signal, StripIt(value))
            yield message

    def __dir__(self):
        return super(_StreamServerObject, self).__dir__() + ['zerorpc_stream__']

    def close(self):
        for dispatcher in self._dispatchers:
            louie.disconnect(dispatcher, sender=self._object)
        for stream in self._streams:
            stream.put(None)


def Server(obj, stream=False, **kwargs):
    """
    Create a zerorpc server for the given object with a pythonic API

    Args:
        obj: any python object
    Keyword Args:
        stream (bool): supply a stream listening to events coming from obj
    Return:
        a zerorpc server

    It accepts the same keyword arguments as :class:`zerorpc.Server`.
    """
    instance = _StreamServerObject(obj) if stream else _ServerObject(obj)
    server = zerorpc.Server(instance, **kwargs)

    def close():
        instance.close()
        server_close()

    # Patch close method with instance.close()
    server_close, server.close = server.close, close
    return server


# Client code

def _property(name, doc):
    def fget(self):
        return self._client.zerorpc_call__('getattr', (name,), {})
    def fset(self, value):
        self._client.zerorpc_call__('setattr', (name, value), {})
    def fdel(self):
        return self._client.zerorpc_call__('delattr', (name,), {})
    return property(fget=fget, fset=fset, fdel=fdel, doc=doc)


def _method(name, doc):
    if name == '__dir__':
        # need to handle __dir__ to make sure it returns a list, not a tuple
        def method(self):
            return list(self._client.zerorpc_call__('call', [name], {}))
    else:
        def method(self, *args, **kwargs):
            args = [name] + list(args)
            return self._client.zerorpc_call__('call', args, kwargs)
    method.__name__ = name
    method.__doc__ = doc
    return method


def _static_method(client, name, doc):
    def method(*args, **kwargs):
        args = [name] + list(args)
        return client.zerorpc_call__('call', args, kwargs)
    method.__name__ = name
    method.__doc__ = doc
    return staticmethod(method)


def _class_method(client, name, doc):
    def method(cls, *args, **kwargs):
        args = [name] + list(args)
        return client.zerorpc_call__('call', args, kwargs)
    method.__name__ = name
    method.__doc__ = doc
    return classmethod(method)


def _member(client, member_info):
    name, mtype, doc = info['name'], info['type'], info['doc']
    if mtype == 'attribute':
        members[name] = _property(name, doc)
    elif mtype == 'method':
        members[name] = _method(name, doc)
    elif mtype == 'staticmethod':
        members[name] = _static_method(client, name, doc)
    elif mtype == 'classmethod':
        members[name] = _class_method(client, name, doc)


def Client(address, **kwargs):
    """
    Create a zerorpc client with a pythonic API

    Args:
        address: connection address (ex: 'tcp://lid00c:8989')
    Return:
        a zerorpc client

    It accepts the same keyword arguments as :class:`zerorpc.Client`.
    """
    kwargs['connect_to'] = address
    client = zerorpc.Client(**kwargs)
    metadata = client.zerorpc_call__('introspect', (), {})
    client._log = logging.getLogger('zerorpc.' + metadata['name'])
    stream = metadata.get('stream', False)
    members = dict(_client=client)

    for name, info in metadata['members'].items():
        if name.startswith('__') and name[2:-2] in SPECIAL_METHODS:
            continue
        name, mtype, doc = info['name'], info['type'], info['doc']
        if mtype == 'attribute':
            members[name] = _property(name, doc)
        elif mtype == 'method':
            members[name] = _method(name, doc)
        elif mtype == 'staticmethod':
            members[name] = _static_method(client, name, doc)
        elif mtype == 'classmethod':
            members[name] = _class_method(client, name, doc)

    def close(self):
        self._client.close()
        if hasattr(self._client, '_stream_task'):
            self._client._stream_task.kill()
    members['close'] = close

    klass = type(metadata['name'], (object,), members)
    proxy = klass()

    if stream:
        def stream_task_ended(task):
            if task.exception:
                client._log.warning('stream task terminated in error: %s',
                                    task.exception)
            else:
                client._log.debug('stream task terminated')

        def dispatch(proxy):
            while True:
                for signal, value in client.zerorpc_stream__():
                    if signal is None:
                        continue
                    client._log.debug(
                        'dispatching stream event signal=%r value=%r',
                        signal, StripIt(value))
                    louie.send(signal, proxy, value)
        client._stream_task = gevent.spawn(dispatch, proxy)
        client._stream_task.link(stream_task_ended)
    return proxy
