# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Keller controllers. So far only the pressure transmitter (tested with 33X).

YAML_ configuration example:

.. code-block:: yaml

    name: keller_1                             # (1)
    module: keller                             # (2)
    class: PressureTransmitter                 # (3)
    serial:                                    # (4)
      url: enet://hexstarbis:50000/dev/ttyUSB0 # (5)
    serial_nb: 133445                          # (6)
    address: 250                               # (7)
    counters:                                  # (8)
    - counter_name: k1_p                       # (9)
      type: P1                                 # (10)
    - counter_name: k1_t                       # (11)
      type: T1                                 # (12)


#. controller name (mandatory)
#. module name (mandatory = 'keller')
#. class name (mandatory = 'PressureTransmitter')
#. serial line configuration (mandatory)
#. serial line url (mandatory)
#. serial number (optional). If given, the connected keller must match
   the expected
#. address (optional, default=250 meaning use the transparent address).
   Most times don't need to give it.
#. list of counters
#. counter name (mandatory)
#. counter type (optional, default='P1').
   Available types: P1, P2, T1, T2, T. Most kellers only have P1 and T1


Example how to use it in a scan:

    >>> from bliss.common.scans import timescan
    >>> from bliss.static.config import get_config

    >>> config = get_config()
    >>> keller_1 = config.get('keller_1')
    >>> timescan(1, keller_1.k1_p, keller_1.k1_t, npoints=5)

    Scan 16 Mon Sep 18 13:39:21 2017 /tmp/scans/slits/ slits user = coutinho
    timescan 1

       #         dt(s)    k1_t(degC)      k1_p(Pa)
       0       0.01725       27.2772    -0.0150309
       1       1.01954       27.2834    -0.0149823
       2       2.02192       27.2911    -0.0151045
       3       3.02389       27.2822    -0.0149921
       4       4.02563       27.2783    -0.0150896

    Took 0:00:05.048202

"""

import struct
import functools
import collections

import gevent.lock

from bliss.comm.util import get_comm
from bliss.common.counter import SamplingCounter
from bliss.common.logtools import *
from bliss import global_map

BROADCAST_ADDR = 0
TRANSPARENT_ADDR = 250

COMMON_ERROR_MAP = {
    1: "illegal non-implemented function",
    2: "illegal data address",
    3: "message length is incorrect",
    4: "slave device failure",
    32: "device has not yet been initialised",
}

_CmdInfo = collections.namedtuple(
    "CmdInfo", "name fn reply_size encode " "decode error_map args " "pre_check cache"
)


def CmdInfo(name, fn, reply_size, *args, **kwargs):
    error_map = dict(kwargs.get("error_map", {}))
    error_map.update(COMMON_ERROR_MAP)
    pre_check = kwargs.get("pre_check")
    cache = kwargs.get("cache", False)
    encode = kwargs.get("encode")
    decode = kwargs["decode"]
    return _CmdInfo(
        name, fn, reply_size, encode, decode, error_map, args, pre_check, cache
    )


_InitInfo = collections.namedtuple(
    "InitInfo", "klass group version_tuple buffer_size status version type full_version"
)


def InitInfo(klass, group, version_tuple, buffer_size, status):
    dev_type = "{0}.{1}".format(klass, group)
    version = "{0}.{1}".format(*version_tuple)
    full_version = dev_type + "-" + version
    return _InitInfo(
        klass,
        group,
        version_tuple,
        buffer_size,
        status,
        version,
        dev_type,
        full_version,
    )


class KellerError(Exception):
    pass


def crc16(*ords):
    crc = 0xFFFF
    for ch in ords:
        crc ^= ch
        for i in range(8):
            shift_carry = crc & 1
            crc >>= 1
            if shift_carry:
                crc ^= 0xA001
    return crc


def check_message_crc16(msg, crc):
    crc_h, crc_l = struct.unpack("!BB", msg[-2:])
    crc_msg = crc_h << 8 | crc_l
    return crc == crc_msg


def _decode_uint32(msg):
    return struct.unpack("!I", msg[:4])[0]


def _encode_uint32(i):
    return struct.pack("!I", i)


def _decode_uint8(msg):
    return struct.unpack("!B", msg[:1])[0]


def _encode_uint8(i):
    return struct.pack("!B", i)


def _decode_float(msg):
    return struct.unpack("!f", msg[:4])[0]


def _encode_float(f):
    return struct.pack("!f", f)


def _decode_status(msg):
    status = _decode_uint8(msg)
    if not status:
        return "OK"
    msgs, channels = [], []
    if status & (1 << 7):
        msgs.append("Power-up mode")
    if status & (1 << 6):
        msgs.append("Analog signal in saturation")
    if not msgs:
        msgs.append("Measuring or computation error")
    for i, ch in enumerate(("CH0", "P1", "P2", "T", "T1", "T2")):
        if status & (1 << i):
            channels.append(ch)
    msg = "Error(s): " + ", ".join(msgs)
    if channels:
        msg += " on channels {0}".format(", ".join(channels))
    return msg


def _decode_float_status(msg):
    number = _decode_float(msg[:4])
    status = _decode_status(msg[4:])
    if status != "OK":
        raise KellerError(status)
    return number


def _decode_init(msg):
    data = struct.unpack("!BBBBBB", msg[:6])
    klass, group = data[0:2]
    version_tuple = data[2:4]
    return InitInfo(klass, group, version_tuple, data[4], data[5])


def _decode_active_ch(msg):
    data = _decode_uint8(msg)
    return [i for i in range(8) if data & (1 << i)]


def _decode_active_p(msg):
    return ["P{0}".format(p) for p in _decode_active_ch(msg)]


def _decode_active_t(msg):
    t_ch_map = {3: "T", 4: "TOB1", 5: "TOB2", 7: "CON"}
    channels = _decode_active_ch(msg)
    return [name for ch, name in t_ch_map.items() if ch in channels]


def debug_it(f):
    name = f.__name__

    @functools.wraps(f)
    def wrapper(self, *args, **kwargs):
        log_debug(self, f"[start] {name}()")
        r = f(self, *args, **kwargs)
        log_debug(self, f"[end] {name}() -> {r}")
        return r

    return wrapper


def _only_dev_type(device, cmd, dev_type=None):
    dev = device.init_info.type
    if dev != dev_type:
        raise KellerError(
            "Command {0} only valid for {1} (device is {2})".format(
                cmd.name, dev_type, dev
            )
        )


_only_5_20 = functools.partial(_only_dev_type, dev_type="5.20")
_only_5_21 = functools.partial(_only_dev_type, dev_type="5.21")


class BaseCmd(object):
    def __init__(self, *args, **kwargs):
        self.cmd = CmdInfo("", *args, **kwargs)

    def get(self, obj, type=None):
        if obj is None:
            return self
        name, cache = self.cmd.name, self.cmd.cache
        value = obj._cache.get(cache)
        if not cache or value is None:
            obj.debug("[start] %s", name)
            value = obj.get(self.cmd)
            obj.debug("[end] %s = %s", name, value)
        obj._cache[cache or name] = value
        return value

    def set(self, obj, value):
        name, cache = self.cmd.name, self.cmd.cache
        if self.cmd.encode is None:
            raise KellerError("{0} is read-only".format(name))
        obj.set(self.cmd, value)
        obj._cache[cache or name] = value


class Attr(BaseCmd):

    __get__ = BaseCmd.get
    __set__ = BaseCmd.set


class Cmd(BaseCmd):
    class command(object):
        def __init__(self, desc, obj):
            self.desc = desc
            self.obj = obj

        def __call__(self):
            return self.desc.get(self.obj)

    def __get__(self, obj, type=None):
        if obj is None:
            return self
        return self.command(self, obj)

    def __set__(self, obj, value):
        raise KellerError("Cannot write {0!r} command".format(self.cmd.name))


def fill(klass):
    def create_read(descriptor):
        name = descriptor.cmd.name

        def read(self):
            self._cache.pop(name, None)
            return descriptor.get(self)

        read.__name__ = "read_" + name
        return read

    def create_write(descriptor):
        def write(self, value):
            return descriptor.set(self, value)

        write.__name__ = "write_" + descriptor.cmd.name
        return write

    for name in dir(klass):
        item = getattr(klass, name)
        if isinstance(item, BaseCmd):
            item.cmd = item.cmd._replace(name=name)
            if item.cmd.cache == True:
                item.cmd = item.cmd._replace(cache=name)
        if isinstance(item, Attr):
            if item.cmd.cache:
                # if cached, provide read/write methods to force communication
                setattr(klass, "read_" + name, create_read(item))
                if item.cmd.encode is not None:
                    setattr(klass, "write_" + name, create_write(item))
        elif isinstance(item, Cmd):
            item.cmd = item.cmd._replace(name=name)
    return klass


PT_PPRINT_TEMPLATE = """\
{pt.__class__.__name__}:
  communication = {pt.comm}
  serial number = {pt.serial_nb}
  address = {pt.address}
  active pressure channels = {pt.active_pressure_channels}
  active temperature channels = {pt.active_temperature_channels}
  temperature measurement interval = {pt.temperature_measurement_interval}s
  measurement status = {pt.measurement_status}
  info: {pt.init_info.full_version}
    type: {pt.init_info.type}
    version: {pt.init_info.version}
    class: {pt.init_info.klass}
    group: {pt.init_info.group}
    buffer size: {pt.init_info.buffer_size}
    status: {pt.init_info.status}"""


class KellerCounter(SamplingCounter):
    def __init__(self, name, controller, channel, unit=None):
        SamplingCounter.__init__(self, name, controller)
        self.channel = channel
        self.unit = unit

    def read(self):
        return getattr(self.controller, self.channel)


UI8AttrRO = functools.partial(Attr, decode=_decode_uint8)
UI8AttrRW = functools.partial(UI8AttrRO, encode=_encode_uint8)
UI8Attr = UI8AttrRW
FAttrRO = functools.partial(Attr, decode=_decode_float)
FAttrRW = functools.partial(FAttrRO, encode=_encode_float)
FAttr = FAttrRW

FSAttrRO = functools.partial(Attr, decode=_decode_float_status)


@fill
class PressureTransmitter:
    """
    Keller pressure transmitter for the S30 and S40 series.

    Tested with the PA-33X.
    """

    active_pressure_channels = Attr(32, 1, 0, cache=True, decode=_decode_active_p)
    active_temperature_channels = Attr(32, 1, 1, cache=True, decode=_decode_active_t)
    temperature_measurement_interval = UI8Attr(
        32, 1, 3, cache=True, pre_check=_only_5_20
    )
    measurement_status = Attr(32, 1, 12, decode=_decode_status)
    address = Attr(32, 1, 13, decode=_decode_uint8, cache=True)

    init = Cmd(48, 6, decode=_decode_init)
    init_info = Attr(48, 6, decode=_decode_init, cache="init")

    pressure1 = FSAttrRO(73, 5, 1)
    pressure1_gain = FAttrRW(30, 4, 65)
    pressure1_offset = FAttrRW(30, 4, 64)

    pressure2 = FSAttrRO(73, 5, 2, pre_check=_only_5_20)
    pressure2_gain = FAttrRW(30, 4, 67, pre_check=_only_5_20)
    pressure2_offset = FAttrRW(30, 4, 66, pre_check=_only_5_20)

    temperature = FSAttrRO(73, 5, 3, pre_check=_only_5_21)
    temperature1 = FSAttrRO(73, 5, 4)
    temperature2 = FSAttrRO(73, 5, 5, pre_check=_only_5_20)

    serial_nb = Attr(69, 4, decode=_decode_uint32, cache=True)

    _CHANNEL_MAP = {
        "P1": ("pressure1", "bar"),
        "P2": ("pressure2", "bar"),
        "TOB1": ("temperature1", "degC"),
        "TOB2": ("temperature2", "degC"),
        "T1": ("temperature1", "degC"),
        "T2": ("temperature2", "degC"),
        "T": ("temperature", "degC"),
    }

    def __init__(self, name, config):
        self._cache = {}
        self._configured_address = int(config.get("address", TRANSPARENT_ADDR))
        self._comm_lock = gevent.lock.RLock()
        self.counters = {}
        self.config = config
        self.name = name
        self.comm = get_comm(config, baudrate=9600)
        self.echo = config.get("echo", 1)
        self.expected_serial_nb = config.get("serial_nb", None)
        global_map.register(self, children_list=[self.comm])

        # Create counters
        for counter_config in self.config.get("counters", []):
            counter_name = counter_config["counter_name"]
            if hasattr(self, counter_name):
                log_error(
                    self,
                    f"Skipped counter {counter_name} (controller already "
                    f"has a member with that name)",
                )
                continue
            channel = counter_config.get("channel", "P1")
            counter = self.__create_counter(counter_name, channel=channel)
            self.counters[counter_name] = counter
            setattr(self, counter_name, counter)

        self.initialize()

    def __str__(self):
        try:
            version = self.init_info.full_version
        except KellerError:
            version = "?"
        try:
            serial_nb = self.serial_nb
        except KellerError:
            serial_nb = "?"
        msg = "{type}(version={version}, serial_nb={serial_nb}, comm={comm})"
        return msg.format(
            type=self.__class__.__name__,
            version=version,
            serial_nb=serial_nb,
            comm=self.comm,
        )

    def __create_counter(self, name, channel="P1"):
        cname, unit = self._CHANNEL_MAP[channel.upper()]
        return KellerCounter(name, self, cname, unit=unit)

    def pprint(self):
        print((PT_PPRINT_TEMPLATE.format(pt=self)))

    def initialize(self):
        self.comm.flush()
        self._cache = {}
        if self.expected_serial_nb:
            log_info(
                self,
                f"Verifying instrument serial number against {self.expected_serial_nb}",
            )
            if self.serial_nb != self.expected_serial_nb:
                raise KellerError(
                    "Serial number mismatch. Expected {0} but "
                    "instrument says it is {1}".format(
                        self.expected_serial_nb, self.serial_nb
                    )
                )
        self.init()

    def set(self, cmd, value):
        with self._comm_lock:
            return self._set(cmd, value)

    def _set(self, cmd, value):
        # Only tested with function 33!
        str_value = cmd.encode(value)
        # REQUEST: Addr + (Function+1) + <args> + CRC_H + CRC_L
        request = (
            [self._configured_address, cmd.fn + 1]
            + list(cmd.args)
            + list(map(ord, str_value))
        )
        crc = crc16(*request)
        crc_h, crc_l = crc >> 8, crc & 0xFF
        request.extend([crc_h, crc_l])
        request = "".join(map(chr, request))
        log_debug_data(self, "raw write", request)
        self.comm.write(request)

        # REPLY: transmitted message is received again immediately as an echo
        if self.echo:
            echo = self.comm.read(len(request))
            if echo != request:
                raise KellerError("Failed to syncronize serial buffer")

        # REPLY: Addr + Function + Error code + CRC_H + CRC_L
        reply = self.comm.read(5)
        log_debug_data(self, "raw reply", reply)

    def get(self, cmd):
        with self._comm_lock:
            return self._get(cmd)

    def _get(self, cmd):
        if cmd.pre_check:
            cmd.pre_check(self, cmd)

        # REQUEST: Addr + Function + <args> + CRC_H + CRC_L (if f==3 => invert CRC)
        request = [self._configured_address, cmd.fn] + list(cmd.args)
        crc = crc16(*request)
        crc_h, crc_l = crc >> 8, crc & 0xFF
        if cmd.fn == 3:
            request.extend([crc_l, crc_h])
        else:
            request.extend([crc_h, crc_l])
        request = bytes(request)
        log_debug_data(self, "raw write", request.hex())
        self.comm.write(request)

        # REPLY: transmitted message is received again immediately as an echo
        if self.echo:
            echo = self.comm.read(len(request))
            if echo != request:
                raise KellerError("Failed to syncronize serial buffer")

        # OK REPLY: Addr + Function + <specific response> + CRC_H + CRC_L
        # ERR REPLY: Addr + (0x80 | Function) + Error code + CRC_H + CRC_L
        reply = self.comm.read(2)
        reply_addr = reply[0]
        reply_fn = reply[1]

        if self._configured_address != reply_addr:
            raise KellerError("Unexpected response address")
        elif cmd.fn != (reply_fn & 0x7F):
            raise KellerError("Unexpected response function")
        elif reply_fn & 0x80:
            reply_payload = self.comm.read(1)
            reply_crc = self.comm.read(2)
            reply += reply_payload + reply_crc
            log_debug_data(self, "raw reply", reply)
            err = ord(reply_payload)
            crc = crc16(reply_addr, reply_fn, err)
            if not check_message_crc16(reply_crc, crc):
                raise KellerError("CRC failure in error reply")
            err_desc = cmd.error_map.get(err, "Unregistered error")
            raise KellerError(
                "Error {0} running function {1}: {2}".format(err, cmd.name, err_desc)
            )

        # read actual response + CRC
        reply_payload = self.comm.read(cmd.reply_size)
        reply_crc = self.comm.read(2)
        reply += reply_payload + reply_crc
        log_debug_data(self, "raw reply", reply)
        crc = crc16(reply_addr, reply_fn, *[n for n in reply_payload])
        if not check_message_crc16(reply_crc, crc):
            raise KellerError("CRC failure in reply")
        return cmd.decode(reply_payload)


def main():
    fmt = "%(levelname)s %(asctime)-15s %(name)s: %(message)s"
    logging.basicConfig(format=fmt, level=logging.DEBUG)

    import sys

    config = dict(serial=dict(url=sys.argv[1]))
    if len(sys.argv) > 2:
        config["serial_nb"] = int(sys.argv[2])
    return PressureTransmitter("my_pt", config)


if __name__ == "__main__":
    pt = main()
