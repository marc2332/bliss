# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
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
    template: renishaw    # optional

Usage::

    >>> from bliss.config.static import get_config
    >>> from bliss.controllers.pepu import Stream, Trigger, Signal, ChannelMode

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

    >>> # enable / disable the channel
    >>> in1.enabled = True

    >>> # read/change the channel mode
    >>> in1.mode
    <ChannelMode.BISS: 'BISS'>
    >>> in1.mode = ChannelMode.QUAD

    >>> # Define a calculation
    >>> calc1 = pepudcm2.calc_channels[1]
    >>> calc1.formula = '0.25 * IN1 + 3'

    >>> # Create a global inactive and unitialized stream and then initialize
    >>> s0 = pepudcm2.create_stream('S0')
    >>> s0.trigger = Trigger(start=Signal.SOFT, clock=Signal.SOFT)
    >>> s0.frequency = 1
    >>> s0.nb_points = 10
    >>> s0.sources = ['CALC1']

    >>> # Create a fully initialized stream in one go
    >>> s1 = pepudcm2.create_stream(name='S1',
                                    trigger=Trigger(Signal.SOFT, Signal.SOFT),
                                    frequency=10, nb_points=4,
                                    sources=('CALC1', 'CALC2'))

    >>> # Do an acquisition:
    >>> s1.start()
    >>> pepudcm2.software_trigger()
    >>> s1.nb_points_ready
    1
    >>> p1.read(1)
    array([ 2.75, -3.])
    >>> pepudcm2.software_trigger()
    >>> pepudcm2.software_trigger()
    >>> pepudcm2.software_trigger()
    >>> s1.nb_points_ready
    3
    >>> p1.read(3)
    array([ 2.75, -3.  ,  2.75, -3.  ,  2.75, -3.  ])

For the counter interface, see the
`PePU scan support documentation <bliss.scanning.acquisition.pepu.html>`__.
"""

import enum
import logging
import weakref
import collections

import numpy

from bliss.comm.util import get_comm, TCP
from bliss.controllers.motors.icepap import _command, _ackcommand

from bliss.controllers.counter import CounterController
from bliss.common.counter import Counter
from bliss.controllers.counter import counter_namespace


TEMPLATE_RENISHAW = """\
CHCFG IN1 BISS
CHCFG IN2 BISS
CHCFG IN3 BISS
CHCFG IN4 BISS
CHCFG IN5 BISS
CHCFG IN6 BISS
BISSCFG IN1 32BITS 2500000HZ
BISSCFG IN2 32BITS 2500000HZ
BISSCFG IN3 32BITS 2500000HZ
BISSCFG IN4 32BITS 2500000HZ
BISSCFG IN5 32BITS 2500000HZ
BISSCFG IN6 32BITS 2500000HZ
CHCFG IN1 ENABLE
CHCFG IN2 ENABLE
CHCFG IN3 ENABLE
CHCFG IN4 ENABLE
CHCFG IN5 ENABLE
CHCFG IN6 ENABLE

CHCFG OUT7 BISS
CHCFG OUT8 BISS
BISSCFG OUT7 32BITS
BISSCFG OUT8 32BITS
CHCFG OUT7 ENABLE
CHCFG OUT8 ENABLE

CALCCFG CALC1 (IN1+IN2+IN3+IN4)/4
CHSRC OUT8 CALC1
"""


def idint_to_float(value, integer=40, decimal=8):
    """Convert the given 0...0i...id...d value
    into the corresponding float.

    Trick: the missing sign bits can be padded using
    the following formula:

        value |= -2 * mask(value, sign_bit)

    Load data:

    >>> import numpy as np
    >>> data = (
    ...    b'\\x00\\x00\\x00\\x00\\x00\\x00\\x01\\x80'
    ...    b'\\x00\\x00\\xff\\xff\\xff\\xff\\xfe\\x80')
    >>> a = np.fromstring(data, dtype='>i8')
    >>> x, y = a

    Cast numpy integers:

    >>> idint_to_float(x)
    1.5
    >>> idint_to_float(y)
    -1.5

    Cast python integers:

    >>> idint_to_float(int(x))
    1.5
    >>> idint_to_float(int(y))
    -1.5

    Cast numpy arrays

    >>> idint_to_float(a)
    array([ 1.5, -1.5])
    """
    mask = value & (1 << integer + decimal - 1)
    mask *= -2
    value |= mask
    return value / float(1 << decimal)


def frequency_fromstring(text):
    text = text.upper()
    if "MHZ" in text:
        frequency = float(text.replace("MHZ", "")) * 1e6
    elif "KHZ" in text:
        frequency = float(text.replace("KHZ", "")) * 1e3
    elif "HZ" in text:
        frequency = float(text.replace("HZ", ""))
    else:
        ValueError("Unrecognized frequency {0!r}".format(text))
    return int(frequency)


class Scope(enum.Enum):
    GLOBAL = "GLOBAL"
    LOCAL = "LOCAL"


class ChannelMode(enum.Enum):
    OFF = "OFF"  # not configured
    QUAD = "QUAD"
    PULSE = "PULSE"
    SSI = "SSI"
    BISS = "BISS"
    ENDAT = "ENDAT"


class QuadConfig(enum.Enum):
    X1 = "X1"
    X2 = "X2"
    X4 = "X4"


class Signal(enum.Enum):
    SOFT = "SOFT"
    DI1 = "DI1"
    DI2 = "DI2"
    FREQ = "FREQ"


class PEPUError(Exception):
    pass


ChannelConfig = collections.namedtuple("ChannelConfig", "mode state")


def ChannelConfig_fromstring(text):
    for elem in text.split():
        try:
            mode = ChannelMode(elem)
        except ValueError:
            state = elem.lower() == "enable"
    return ChannelConfig(mode, state)


def ChannelConfig_tostring(cfg):
    return " ".join((cfg.mode.value, "ENABLE" if cfg.state else "DISABLE"))


ChannelConfig.fromstring = staticmethod(ChannelConfig_fromstring)
ChannelConfig.tostring = ChannelConfig_tostring


BissConfig = collections.namedtuple("BissConfig", "bits frequency")


def BissConfig_fromstring(text):
    for elem in text.split():
        elem = elem.upper()
        if "BITS" in elem:
            bits = int(elem.replace("BITS", ""))
        else:
            frequency = frequency_fromstring(elem)
    return BissConfig(bits, frequency)


def BissConfig_tostring(cfg):
    return "{0}BITS {1}HZ".format(cfg.bits, cfg.frequency)


BissConfig.fromstring = staticmethod(BissConfig_fromstring)
BissConfig.tostring = BissConfig_tostring


Trigger = collections.namedtuple("Trigger", "start clock")


def Trigger_fromstring(text):
    return Trigger(*list(map(Signal, text.split()[:2])))


def Trigger_tostring(trigger):
    return "{0} {1}".format(trigger.start.value, trigger.clock.value)


Trigger.fromstring = staticmethod(Trigger_fromstring)
Trigger.tostring = Trigger_tostring


StreamInfo = collections.namedtuple(
    "StreamInfo", "name active scope trigger frequency nb_points sources"
)


def StreamInfo_fromstring(text):
    args = text.strip().split()
    (name, state, scope), args = args[:3], args[3:]
    active = state.upper() == "ON"
    scope = Scope(scope)
    items = dict(
        name=name,
        active=active,
        scope=scope,
        trigger=None,
        frequency=None,
        nb_points=None,
        sources=None,
    )
    i = 0
    while i < len(args):
        item = args[i]
        if item == "TRIG":
            items["trigger"] = Trigger.fromstring(args[i + 1] + " " + args[i + 2])
            i += 1
        elif item == "FSAMPL":
            items["frequency"] = frequency_fromstring(args[i + 1])
        elif item == "NSAMPL":
            items["nb_points"] = int(args[i + 1])
        elif item == "SRC":
            items["sources"] = args[i + 1 :]
            break
        else:
            raise ValueError("Unrecognized {0!r} in DSTREAM".format(item))
        i += 2
    return StreamInfo(**items)


def StreamInfo_tostring(s):
    result = [s.name, "ON" if s.active else "OFF", s.scope.value]
    if s.trigger is not None:
        result += "TRIG", s.trigger.tostring()
    if s.frequency is not None:
        result += "FSAMPL", "{0}HZ".format(int(s.frequency))
    if s.nb_points is not None:
        result += "NSAMPL", str(s.nb_points)
    if s.sources is not None:
        result.append("SRC")
        result += s.sources
    return " ".join(result)


StreamInfo.fromstring = staticmethod(StreamInfo_fromstring)
StreamInfo.tostring = StreamInfo_tostring


class BaseAttr(object):
    def __init__(self, name, decode=str, encode=str):
        self.name = name
        self.decode = decode
        self.encode = encode


class DeviceAttr(BaseAttr):
    def __get__(self, instance, owner):
        if self.decode is None:
            raise PEPUError("Cannot get {0}".format(self.name))
        request = "?{0}".format(self.name)
        reply = instance.raw_write(request)
        return self.decode(reply)

    def __set__(self, instance, value):
        if self.encode is None:
            raise PEPUError("Cannot set {0}".format(self.name))
        value = self.encode(value)
        command = "{0} {1}".format(self.name, value)
        return instance.raw_write_read(command)


class ChannelAttr(BaseAttr):
    def __get__(self, instance, owner):
        if self.decode is None:
            raise PEPUError("Cannot get {0}".format(self.name))
        request = "?{0} {1}".format(self.name, instance.name)
        reply = instance.pepu.raw_write(request)
        return self.decode(reply)

    def __set__(self, instance, value):
        if self.encode is None:
            raise PEPUError("Cannot set {0}".format(self.name))
        value = self.encode(value)
        command = "{0} {1} {2}".format(self.name, instance.name, value)
        return instance.pepu.raw_write_read(command)


class BaseChannel(object):

    value = ChannelAttr("CHVAL", float, None)

    set_value = ChannelAttr("CHSET", None, str)

    def __init__(self, pepu, ctype, id):
        self._pepu = weakref.ref(pepu)
        self.ctype = ctype
        self.id = id

    @property
    def name(self):
        return "{0}{1}".format(self.ctype, self.id)

    @property
    def pepu(self):
        return self._pepu()

    # Counter shortcut

    @property
    def counters(self):
        from bliss.scanning.acquisition.pepu import PepuCounter

        return PepuCounter(self)


class BaseChannelINOUT(BaseChannel):

    value = ChannelAttr("CHVAL", float, str)
    error = ChannelAttr("CHERR", str, None)
    _config = ChannelAttr("CHCFG", ChannelConfig.fromstring, ChannelConfig.tostring)
    quad_config = ChannelAttr("QUADCFG", QuadConfig, lambda x: x.value)

    @property
    def enabled(self):
        return self._config.state

    @enabled.setter
    def enabled(self, enabled):
        self._config = self._config._replace(state=enabled)

    @property
    def mode(self):
        return self._config.mode

    @mode.setter
    def mode(self, mode):
        self._config = self._config._replace(mode=mode)

    def reset(self):
        command = "CHRESET {0}".format(self.name)
        return self.pepu.raw_write_read(command)


class ChannelIN(BaseChannelINOUT):

    biss_config = ChannelAttr("BISSCFG", BissConfig.fromstring, BissConfig.tostring)

    # TODO: SSI, ENDAT, HSSL

    def __init__(self, pepu, id):
        super(ChannelIN, self).__init__(pepu, "IN", id)


class ChannelOUT(BaseChannelINOUT):

    source = ChannelAttr("CHSRC")

    biss_config = ChannelAttr(
        "BISSCFG", BissConfig.fromstring, lambda x: x.tostring().rsplit(" ", 1)[0]
    )

    # TODO: SSI, ENDAT, HSSL

    def __init__(self, pepu, id):
        super(ChannelOUT, self).__init__(pepu, "OUT", id)


class ChannelCALC(BaseChannel):

    formula = ChannelAttr("CALCCFG")

    def __init__(self, pepu, id):
        super(ChannelCALC, self).__init__(pepu, "CALC", id)


class ChannelAUX(BaseChannel):

    value = ChannelAttr("CHVAL", float, None)

    def __init__(self, pepu, id):
        super(ChannelAUX, self).__init__(pepu, "AUX", id)


class StreamAttr(BaseAttr):

    # many stream parameters are set through a specific command
    # (ex: DSTREAM toto NSAMPL 100) but to know the current value
    # you have to execute the '?DSTREAM <stream name>'

    def __get__(self, instance, owner):
        if self.decode is None:
            raise PEPUError("Cannot get {0}".format(self.name))
        request = instance._cmd(query=True)
        reply = instance.pepu.raw_write(request)
        new_info = StreamInfo.fromstring(reply)
        instance.info = new_info
        return self.decode(new_info)

    def __set__(self, instance, value):
        if self.encode is None:
            raise PEPUError("Cannot set {0}".format(self.name))
        value = self.encode(value)
        command = instance._cmd(self.name, value)
        return instance.pepu.raw_write_read(command)


class NbPointsStreamAttr(StreamAttr):
    def __get__(self, instance, owner):
        request = instance._cmd(self.name, query=True)
        reply = instance.pepu.raw_write(request)
        return self.decode(reply)


class Stream(object):

    active = StreamAttr(
        "", decode=lambda x: x.active, encode=lambda x: "ON" if x else "OFF"
    )

    status = StreamAttr("STATUS", str, None)

    trigger = StreamAttr(
        "TRIG", decode=lambda x: x.trigger, encode=lambda x: x.tostring()
    )

    frequency = StreamAttr(
        "FSAMPL", decode=lambda x: x.frequency, encode=lambda x: "{0}HZ".format(int(x))
    )

    nb_points = StreamAttr("NSAMPL", decode=lambda x: x.nb_points, encode=str)

    nb_points_ready = NbPointsStreamAttr("NSAMPL", decode=int, encode=None)

    sources = StreamAttr("SRC", decode=lambda x: x.sources, encode=" ".join)

    def __init__(self, pepu, info):
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
        command = "DSTREAM {0} SRC {1}".format(self.name, channel.name)
        return self.pepu.raw_write_read(command)

    def _cmd(self, *args, **kwargs):
        query = kwargs.get("query", False)
        return " ".join(
            ["?DSTREAM" if query else "DSTREAM", self.name] + list(map(str, args))
        )

    def start(self):
        self._buffer = []
        return self.pepu.raw_write_read(self._cmd("APPLY"))

    def stop(self):
        return self.pepu.raw_write_read(self._cmd("STOP"))

    def flush(self):
        return self.pepu.raw_write_read(self._cmd("FLUSH"))

    def read(self, n=None):
        if n is None:
            n = self.nb_points_ready
        if n == 0:
            return numpy.array([])
        command = "?*DSTREAM {0} READ {1}".format(self.name, n)
        raw_data = self.pepu.raw_write_read(command)
        raw_data.dtype = "<i8"
        array = idint_to_float(raw_data)
        array.dtype = [(source, array.dtype) for source in self.info.sources]
        return array

    def idata(self, n=None):
        if n is None:
            n = self.nb_points
        while n > 0:
            data = self.read()
            n -= data.shape[0]
            yield data

    def __repr__(self):
        return "{0}(pepu={1!r}, {2})".format(
            type(self).__name__, self.pepu.name, self.info.tostring()
        )


class DeviceConfigAttr(DeviceAttr):
    def __init__(self):
        super(DeviceAttr, self).__init__("DCONFIG")

    def __set__(self, instance, value):
        return instance.raw_write(value)


class PEPU(CounterController):
    """
    ESRF - PePU controller
    """

    IN_CHANNELS = list(range(1, 7))  # 7 and 8 are development only
    OUT_CHANNELS = list(range(7, 9))
    AUX_CHANNELS = list(range(1, 9))
    CALC_CHANNELS = list(range(1, 9))
    F_IN_CHANNELS = list(range(1, 7))  # 7 and 8 are development only

    app_name = DeviceAttr("APPNAME", str, None)
    version = DeviceAttr("VERSION", str, None)
    dance_info = DeviceAttr("DINFO", str, None)
    config = DeviceConfigAttr()

    def __init__(self, name, config, master_controller=None):

        super().__init__(name, master_controller=master_controller)

        # self.name = name
        self.bliss_config = config
        self.streams = dict()

        url = config["tcp"]["url"] + ":5000"
        if not url.startswith("command://"):
            url = "command://" + url
        config["tcp"]["url"] = url

        self._log = logging.getLogger("PEPU({0})".format(url))

        self.conn = get_comm(config, TCP, eol="\n")

        self.in_channels = dict([(i, ChannelIN(self, i)) for i in self.IN_CHANNELS])
        self.out_channels = dict([(i, ChannelOUT(self, i)) for i in self.OUT_CHANNELS])
        self.calc_channels = dict(
            [(i, ChannelCALC(self, i)) for i in self.CALC_CHANNELS]
        )

        if "template" in config:
            template_name = "TEMPLATE_" + config["template"].upper()
            template = globals()[template_name]
            self.config = template.format(pepu=self)

        # initialize with existing streams
        str_streams = (
            stream for stream in self.raw_write_read("?DSTREAM").split("\n") if stream
        )
        for str_stream in str_streams:
            stream_info = StreamInfo.fromstring(str_stream)
            self._create_stream(stream_info, write=False)

    def get_acquisition_object(self, acq_params, ctrl_params=None):
        from bliss.scanning.acquisition.pepu import PepuAcquisitionSlave

        return PepuAcquisitionSlave(self, ctrl_params=ctrl_params, **acq_params)

    def get_default_chain_parameters(self, scan_params, acq_params):
        try:
            npoints = acq_params["npoints"]
        except KeyError:
            npoints = scan_params["npoints"]

        start = acq_params.get("start", Signal.SOFT)
        trigger = acq_params.get("trigger", Signal.SOFT)
        frequency = acq_params.get("frequency", None)
        prepare_once = acq_params.get("prepare_once", True)
        start_once = acq_params.get("start_once", True)

        params = {}
        params["npoints"] = npoints
        params["start"] = start
        params["trigger"] = trigger
        params["frequency"] = frequency
        # params["prepare_once"] = prepare_once
        # params["start_once"] = start_once

        return params

    def __getitem__(self, text_or_seq):
        if isinstance(text_or_seq, str):
            return self[(text_or_seq,)][0]
        items = []
        for text in text_or_seq:
            text = text.upper()
            if text.startswith("IN"):
                item = self.in_channels[int(text[2:])]
            elif text.startswith("OUT"):
                item = self.out_channels[int(text[3:])]
            elif text.startswith("CALC"):
                item = self.calc_channels[int(text[4:])]
            else:
                item = self.streams[text]
            items.append(item)
        return items

    def raw_write(self, message, data=None):
        return _command(self.conn, message, data=data)

    def raw_write_read(self, message, data=None):
        return _ackcommand(self.conn, message, data=data)

    def reboot(self):
        self.raw_write("REBOOT")
        self.conn.close()

    def software_trigger(self):
        return self.raw_write_read("STRIG")

    def _create_stream(self, stream_info, write=True):
        if write:
            assert stream_info.scope == Scope.GLOBAL
            active = stream_info.active
            # global streams must be created active
            stream_info = stream_info._replace(active=True)
            self.raw_write_read("DSTREAM " + stream_info.tostring())
            # read back stream info because it may not be exactly what we asked for
            raw_stream_info = self.raw_write_read("?DSTREAM " + stream_info.name)
            stream_info = StreamInfo.fromstring(raw_stream_info)
            stream = Stream(self, stream_info)
            # deactivate if necessary
            if not active:
                stream.active = False
        else:
            stream = Stream(self, stream_info)
        self.streams[stream.name] = stream
        return stream

    def create_stream(
        self,
        name,
        active=False,
        scope=Scope.GLOBAL,
        trigger=None,
        frequency=None,
        nb_points=None,
        sources=None,
        overwrite=False,
    ):
        name = name.upper()
        if overwrite:
            self.remove_stream(name)
        elif name in self.streams:
            raise ValueError("Stream {0!r} already exists".format(name))
        info = StreamInfo(name, active, scope, trigger, frequency, nb_points, sources)
        return self._create_stream(info)

    def remove_stream(self, stream):
        if isinstance(stream, Stream):
            name = stream.name
        else:
            name = stream.upper()
        if name in self.streams:
            stream = self.streams.pop(name)
            cmd = "DSTREAM {0.name} DEL {0.scope.value}".format(stream.info)
            return self.raw_write_read(cmd)

    def __info__(self):
        return "{0}(name={1!r})".format(type(self).__name__, self.name)

    @property
    def counters(self):
        # --- add counters
        channels = list(self.in_channels.values()) + list(self.calc_channels.values())
        counters = []
        for channel in channels:
            counters.append(PepuCounter(channel))

        self._counters = {cnt.name: cnt for cnt in counters}

        return counter_namespace(self._counters)


class PepuCounter(Counter):
    def __init__(self, channel):
        self.channel = channel
        self.acquisition_device = None
        super().__init__(self.channel.name, self.channel.pepu)

    # Standard interface

    # @property
    # def controller(self):
    #     return self.channel.pepu

    # @property
    # def name(self):
    #     return self.channel.name

    @property
    def dtype(self):
        return float

    # @property
    # def shape(self):
    #     return ()

    # Extra logic

    def feed_point(self, stream_data):
        self.emit_data_point(stream_data[self.name])

    def emit_data_point(self, data_point):
        pepu = self.acquisition_device
        pepu.channels.update({f"{pepu.name}:{self.name}": data_point})
