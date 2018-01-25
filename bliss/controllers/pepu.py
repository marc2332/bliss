# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2017 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""ESRF - PePU controller

Example YAML_ configuration:

.. code-block:: yaml

    plugin: bliss
    class: PEPU
    module: pepu
    name: pepudcm2
    tcp:
      url: pepudcm2


Usage::

    >>> from bliss.config.static import get_config()
    >>> config = get_config()

    >>> pepudcm2 = config.get('pepudcm2')

    >>> # Read device parameters:
    >>> pepudcm2.sys_info
    'DANCE version: 00.01 , build: 2016/11/28 13:02:35, versions: none'
    >>> pepudcm2.version
    '00.01'

    >>> # Get the input channel 1 and read the current value:
    >>> in1 = pepudcm2.in_channels[1]
    >>> print(in1.value)

    >>> # Define a calculation
    >>> calc1 = pepudcm2.calc_channels[1]
    >>> calc1.formula = '0.25 * IN1 + 3'

    >>> # Create a global inactive and unitialized stream and then initialize
    >>> from bliss.controllers.pepu import Stream, Trigger, Signal
    >>> s0 = pepu.Stream(pepudcm2, 'S0')
    >>> s0.trigger = Trigger(start=Signal.SOFT, clock=Signal.SOFT)
    >>> s0.frequency = 1
    >>> s0.nb_points = 10
    >>> s0.sources = ['CALC1']
    >>> pepudcm2.add_stream(s0)

    >>> # Create a fully intialized stream in one go
    >>> s1 = pepu.Stream(pepudcm2, name='S1',
                         trigger=Trigger(Signal.SOFT, Signal.SOFT),
                         frequency=10, nb_points=4,
                         sources=('CALC1', 'CALC2'))
    >>> pepudcm2.add_stream(s1)

    >>> # Do an acquisition:
    >>> s1.start()
    >>> pepudcm2.software_trigger()
    >>> s1.nb_points
    1
    >>> p1.read(1)
    array([ 2.75, -3.])
    >>> pepudcm2.software_trigger()
    >>> pepudcm2.software_trigger()
    >>> pepudcm2.software_trigger()
    >>> s1.nb_points
    3
    >>> p1.read(3)
    array([ 2.75, -3.  ,  2.75, -3.  ,  2.75, -3.  ])
"""

import enum
import logging
import weakref
import collections

from bliss.comm.util import get_comm, TCP
from bliss.controllers.motors.icepap import _command, _ackcommand


def from_48bit(a):
    a.dtype = '<i8'
    b = a.copy()
    b &= 1 << 47
    b *= -2
    a |= b
    a = a / float(1<<8)
    return a


def frequency_fromstring(text):
    text = text.upper()
    if 'MHZ' in text:
        frequency = float(text.replace('MHZ', '')) * 1e6
    elif 'KHZ' in text:
        frequency = float(text.replace('KHZ', '')) * 1e3
    elif 'HZ' in text:
        frequency = float(text.replace('HZ', ''))
    else:
        ValueError('Unrecognized frequency {0!r}'.format(text))
    return frequency


class Scope(enum.Enum):
    GLOBAL = 'GLOBAL'
    LOCAL = 'LOCAL'


class ChannelMode(enum.Enum):
    OFF = 'OFF'         # not configured
    QUAD = 'QUAD'
    PULSE = 'PULSE'
    SSI = 'SSI'
    BISS = 'BISS'
    ENDAT = 'ENDAT'


class ChannelState(enum.Enum):
    ENABLED = 'ENABLE'
    DISABLED = 'DISABLE'


ChannelConfig = collections.namedtuple('ChannelConfig', 'mode state')


def ChannelConfig_fromstring(text):
    for elem in text.split():
        try:
            mode = ChannelMode(elem)
        except ValueError:
            state = ChannelState(elem)
    return ChannelConfig(mode, state)


def ChannelConfig_tostring(cfg):
    return ' '.join(cfg.mode.value, cfg.state.value)


ChannelConfig.fromstring = staticmethod(ChannelConfig_fromstring)
ChannelConfig.tostring = ChannelConfig_tostring


class QuadConfig(enum.Enum):
    X1 = 'X1'
    X2 = 'X2'
    X4 = 'X4'


BissConfig = collections.namedtuple('BissConfig', 'bits frequency')


def BissConfig_fromstring(text):
    for elem in text.split():
        elem = elem.upper()
        if 'BITS' in elem:
            bits = int(elem.replace('BITS', ''))
        else:
            frequency = frequency_fromstring(elem)
    return BissConfig(bits, frequency)


def BissConfig_tostring(cfg):
    return '{0}BITS {1}HZ'.format(cfg.bits, cfg.frequency)

BissConfig.fromstring = staticmethod(BissConfig_fromstring)
BissConfig.tostring = BissConfig_tostring


class BaseAttr(object):

    def __init__(self, name, decode=str, encode=str):
        self.name = name
        self.decode = decode
        self.encode = encode


class DeviceAttr(BaseAttr):

    def __get__(self, instance, owner):
        if self.decode is None:
            raise RuntimeError('Cannot get {0}'.format(self.name))
        request = '?{0}'.format(self.name)
        reply = instance.raw_write(request)
        return self.decode(reply)

    def __set__(self, instance, value):
        if self.encode is None:
            raise RuntimeError('Cannot set {0}'.format(self.name))
        value = self.encode(value)
        command = '{0} {1}'.format(self.name, value)
        return instance.raw_write_read(command)


class ChannelAttr(BaseAttr):

    def __get__(self, instance, owner):
        if self.decode is None:
            raise RuntimeError('Cannot get {0}'.format(self.name))
        request = '?{0} {1}'.format(self.name, instance.name)
        reply = instance.pepu.raw_write(request)
        return self.decode(reply)

    def __set__(self, instance, value):
        if self.encode is None:
            raise RuntimeError('Cannot set {0}'.format(self.name))
        value = self.encode(value)
        command = '{0} {1} {2}'.format(self.name, instance.name, value)
        return instance.pepu.raw_write_read(command)


class BaseChannel(object):

    value = ChannelAttr('CHVAL', float, str)
    set_value = ChannelAttr('CHSET', None, str)
    config = ChannelAttr('CHCFG',
                         ChannelConfig.fromstring,
                         ChannelConfig.tostring)
    error = ChannelAttr('CHERR', str, None)

    def __init__(self, pepu, ctype, id):
        self._pepu = weakref.ref(pepu)
        self.ctype = ctype
        self.id = id

    @property
    def name(self):
        return '{0}{1}'.format(self.ctype, self.id)

    @property
    def pepu(self):
        return self._pepu()


class BaseChannelINOUT(BaseChannel):
    quad_config = ChannelAttr('QUADCFG', QuadConfig, lambda x: x.value)

    def reset(self):
        command = 'CHRESET {0}'.format(self.name)
        return self.pepu.raw_write_read(command)


class ChannelIN(BaseChannelINOUT):

    biss_config = ChannelAttr('BISSCFG',
                              BissConfig.fromstring,
                              BissConfig.tostring)
    # TODO: SSI, ENDAT, HSSL

    def __init__(self, pepu, id):
        super(ChannelIN, self).__init__(pepu, 'IN', id)


class ChannelOUT(BaseChannelINOUT):

    source = ChannelAttr('CHSRC')
    biss_config = ChannelAttr('BISSCFG',
                              BissConfig.fromstring,
                              lambda x: x.tostring().rsplit(' ', 1)[0])
    # TODO: SSI, ENDAT, HSSL

    def __init__(self, pepu, id):
        super(ChannelOUT, self).__init__(pepu, 'OUT', id)


class ChannelCALC(BaseChannel):

    formula = ChannelAttr('CALCCFG')

    def __init__(self, pepu, id):
        super(ChannelCALC, self).__init__(pepu, 'CALC', id)


class Signal(enum.Enum):
    SOFT = 'SOFT'
    DI1 = 'DI1'
    DI2 = 'DI2'
    FREQ = 'FREQ'


Trigger = collections.namedtuple('Trigger', 'start clock')

def Trigger_fromstring(text):
    return Trigger(*map(Signal, text.split()[:2]))

def Trigger_tostring(trigger):
    return '{0} {1}'.format(trigger.start.value, trigger.clock.value)

Trigger.fromstring = staticmethod(Trigger_fromstring)
Trigger.tostring = Trigger_tostring


StreamInfo = collections.namedtuple('StreamInfo', 'name active scope trigger ' \
                                    'frequency nb_points sources')

def StreamInfo_fromstring(text):
    args = text.strip().split()
    (name, state, scope), args = args[:3], args[3:]
    active = state.upper() == 'ON'
    scope = Scope(scope)
    items = dict(name=name, active=active, scope=scope,
                 trigger=None, frequency=None, nb_points=None, sources=None)
    i = 0
    while i < len(args):
        item = args[i]
        if item == 'TRIG':
            items['trigger'] = Trigger.fromstring(args[i+1] + ' ' + args[i+2])
            i += 1
        elif item == 'FSAMPL':
            items['frequency'] = frequency_fromstring(args[i+1])
        elif item == 'NSAMPL':
            items['nb_points'] = int(args[i+1])
        elif item == 'SRC':
            items['sources'] = args[i+1:]
            break
        else:
            #raise ValueError('Unrecognized DSTREAM {0!r}'.format(text))
            raise ValueError('Unrecognized {0!r} in DSTREAM'.format(item))
        i += 2
    return StreamInfo(**items)


def StreamInfo_tostring(s):
    result = [s.name, 'ON' if s else 'OFF', s.scope.value]
    if s.trigger is not None:
        result += 'TRIG', s.trigger.tostring()
    if s.frequency is not None:
        result += 'FSAMPL', '{0}HZ'.format(s.frequency)
    if s.nb_points is not None:
        result += 'NSAMPL', str(s.nb_points)
    if s.sources is not None:
        result.append('SRC')
        result += s.sources
    return ' '.join(result)

StreamInfo.fromstring = staticmethod(StreamInfo_fromstring)
StreamInfo.tostring = StreamInfo_tostring


class StreamAttr(BaseAttr):
    # many stream parameters are set through a specific command
    # (ex: DSTREAM toto NSAMPL 100) but to know the current value
    # you have to execute the '?DSTREAM <stream name>'

    def __get__(self, instance, owner):
        if self.decode is None:
            raise RuntimeError('Cannot get {0}'.format(self.name))
        request = instance._cmd(query=True)
        reply = instance.pepu.raw_write(request)
        new_info = StreamInfo.fromstring(reply)
        instance.info = new_info
        return self.decode(new_info)

    def __set__(self, instance, value):
        if self.encode is None:
            raise RuntimeError('Cannot set {0}'.format(self.name))
        value = self.encode(value)
        command = instance._cmd(self.name, value)
        return instance.pepu.raw_write_read(command)


class NbPointsStreamAttr(StreamAttr):

    def __get__(self, instance, owner):
        request = instance._cmd(self.name, query=True)
        reply = instance.pepu.raw_write(request)
        return self.decode(reply)


class Stream(object):

    active = StreamAttr('',
                        decode=lambda x: x.active,
                        encode=lambda x: 'ON' if x else 'OFF')
    status = StreamAttr('STATUS', str, None)
    trigger = StreamAttr('TRIG',
                         decode=lambda x: x.trigger,
                         encode=lambda x: x.tostring())
    frequency = StreamAttr('FSAMPL',
                           decode=lambda x: x.frequency,
                           encode=lambda x: '{0}HZ'.format(x))
    nb_points = NbPointsStreamAttr('NSAMPL', decode=int)


    def __init__(self, pepu, info=None, name=None, active=False,
                 scope=Scope.GLOBAL, trigger=None, frequency=None,
                 nb_points=None, sources=None):
        if info is None:
            info = StreamInfo(name, active, scope, trigger, frequency,
                              nb_points, sources)
        self._pepu = weakref.ref(pepu)
        self.info = info

    @property
    def pepu(self):
        return self._pepu()

    @property
    def name(self):
        return self.info.name

    @staticmethod
    def fromstring(pepu, text):
        info = StreamInfo.fromstring(text)
        return Stream(pepu, info=info)

    def add_source(self, channel):
        command = 'DSTREAM {0} SRC {1}'.format(self.name, channel.name)
        return self.pepu.raw_write_read(command)

    def _cmd(self, *args, **kwargs):
        query = kwargs.get('query', False)
        return ' '.join(['?DSTREAM' if query else 'DSTREAM', self.name] +
                        list(map(str, args)))

    def start(self):
        self._buffer = []
        return self.pepu.raw_write_read(self._cmd('APPLY'))

    def stop(self):
        return self.pepu.raw_write_read(self._cmd('STOP'))

    def flush(self):
        return self.pepu.raw_write_read(self._cmd('FLUSH'))

    def _remove(self):
        cmd = self._cmd('DEL', self.info.scope.value)
        print cmd
        return self.pepu.raw_write_read(cmd)

    def _add(self):
        return self.pepu.raw_write_read('DSTREAM ' + self.info.tostring())

    def read(self, n=1):
        command = '?*DSTREAM {0} READ {1}'.format(self.name, n)
        raw_data = self.pepu.raw_write_read(command)
        return from_48bit(raw_data)

    def idata(self, n):
        while n > 0:
            available = self.nb_points
            yield self.read(n=available) if available else []
            n -= available


class PEPU(object):
    """
    ESRF - PePU controller
    """

    IN_CHANNELS = range(1, 7)     # 7 and 8 are development only
    OUT_CHANNELS = range(7, 9)
    AUX_CHANNELS = range(1, 9)
    CALC_CHANNELS = range(1, 9)
    F_IN_CHANNELS = range(1, 7)   # 7 and 8 are development only

    app_name = DeviceAttr('APPNAME', str, None)
    version = DeviceAttr('VERSION', str, None)
    up_time = DeviceAttr('UPTIME', float, None)
    sys_info = DeviceAttr('SYSINFO', str,None)
    dance_info = DeviceAttr('DINFO', str, None)
    config = DeviceAttr('DCONFIG')

    def __init__(self, name, config):
        self.name = name
        self.bliss_config = config
        self.streams = collections.OrderedDict()

        url = config['tcp']['url'] + ':5000'
        if not url.startswith('command://'):
            url = 'command://'+ url
        config['tcp']['url'] = url

        self._log = logging.getLogger('PEPU({0})'.format(url))

        self.conn = get_comm(config, TCP, eol='\n')

        self.in_channels = {i:ChannelIN(self, i) for i in self.IN_CHANNELS}
        self.out_channels = {i:ChannelOUT(self, i) for i in self.OUT_CHANNELS}
        self.calc_channels = {i:ChannelCALC(self, i) for i in self.CALC_CHANNELS}

        # initialize with existing streams
        str_streams = (stream
                       for stream in self.raw_write_read('?DSTREAM').split('\n')
                       if stream)
        for str_stream in str_streams:
            stream = Stream.fromstring(self, str_stream)
            self.streams[stream.name] = stream

    def raw_write(self, message, data = None):
        return _command(self.conn, message, data=data)

    def raw_write_read(self, message, data = None):
        return _ackcommand(self.conn, message, data=data)

    def reboot(self):
        self.raw_write('REBOOT')
        self.conn.close()

    def software_trigger(self):
        return self.raw_write_read('STRIG')

    def add_stream(self, stream):
        self.remove_stream(stream)
        stream._add()
        self.streams[stream.name] = stream

    def remove_stream(self, stream):
        if stream.name in self.streams:
            stream = self.streams.pop(stream.name)
            stream._remove()
