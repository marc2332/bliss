# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2017 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import enum
import logging
import weakref
import collections

from bliss.comm.util import get_comm, TCP
from bliss.controllers.motors.icepap import _command, _ackcommand


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
    x4 = 'X4'


BissConfig = collections.namedtuple('BissConfig', 'bits frequency')


def BissConfig_fromstring(text):
    for elem in text.split():
        if 'BITS' in elem:
            bits = int(elem.replace('BITS', ''))
        elif 'MHZ' in elem:
            frequency = float(elem.replace('MHZ', '')) * 1e6
        elif 'KHZ' in elem:
            frequency = float(elem.replace('KHZ', '')) * 1e3
        elif 'HZ' in elem:
            frequency = float(elem.replace('HZ', ''))
        else:
            ValueError('Unknown BISS config value {0!r}'.format(elem))
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
        reply = instance.raw_write(equest)
        return self.decode(reply)

    def __set__(self, instance, value):
        if self.encode is None:
            raise RuntimeError('Cannot set {0}'.format(self.name))
        value = self.encode(value)
        command = '{0} {1} {2}'.format(self.name, instance.name, value)
        return instance.raw_write_read(command)


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

    calc_config = ChannelAttr('CALCCFG')

    def __init__(self, pepu, id):
        super(ChannelCALC, self).__init__(pepu, 'CALC', id)


class Signal(enum.Enum):
    SOFT = 'SOFT'
    DI1 = 'DI1'
    DI2 = 'DI2'
    FREQ = 'FREQ'


Trigger = collections.namedtuple('Trigger', 'start clock')


class StreamAttr(BaseAttr):

    def __get__(self, instance, owner):
        if self.decode is None:
            raise RuntimeError('Cannot get {0}'.format(self.name))
        request = instance._cmd(self.name, query=True)
        reply = instance.raw_write(request)
        return self.decode(reply)

    def __set__(self, instance, value):
        if self.encode is None:
            raise RuntimeError('Cannot set {0}'.format(self.name))
        value = self.encode(value)
        command = instance._cmd(self.name, value)
        return instance.raw_write_read(command)


class Stream(object):

    active = StreamAttr('',
                        lambda x: x.split()[1].upper() == 'ON',
                        lambda x: 'ON' and x or 'OFF')
    status = StreamAttr('STATUS', str, None)
    trigger = StreamAttr('TRIG',
                         None,
                         lambda trigger: '{0.start.value} {0.clock.value}' \
                         .format(trigger))
    frequency = StreamAttr('FSAMPL',
                           None,
                           lambda frequency: '{0}HZ'.format(frequency))
    nb_points = StreamAttr('NSAMPL', int, str)

    def __init__(self, pepu, name, scope=Scope.GLOBAL):
        self._pepu = weakref.ref(pepu)
        self.name = name
        self.scope = scope

    @property
    def pepu(self):
        return self._pepu()

    @staticmethod
    def fromstring(pepu, text):
        name, _, scope = text.split()
        scope = Scope(scope)
        return Stream(pepu, name, scope=scope)

    def add_source(self, channel):
        command = 'DSTREAM {0} SRC {1}'.format(self.name, channel.name)
        return self.pepu.raw_write_read(command)

    def _cmd(self, *args. query=False):
        return ' '.join('?DSTREAM' if query else 'DSTREAM', self.name,
                        *map(str, args))

    def start(self):
        self._buffer = []
        return self.pepu.raw_write_read(self._cmd('APPLY'))

    def stop(self):
        return self.pepu.raw_write_read(self._cmd('STOP'))

    def flush(self):
        return self.pepu.raw_write_read(self._cmd('FLUSH'))

    def _remove(self):
        return self.pepu.raw_write_read(self._cmd('DEL', self.scope.value))

    def _add(self):
        return self.pepu.raw_write_read(self._cmd(self.scope.value))

    def _read(self, n=1):
        #command = '?*DSTREAM {0} READ {1}'.format(self.name, n)
        raise NotImplementedError


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

    def remove_stream(self, stream):
        if stream.name in self.streams:
            stream = self.streams.pop(stream.name)
            stream._remove()
