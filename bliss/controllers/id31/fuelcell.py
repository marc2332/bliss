# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Leancat (www.lean-cat.com) fuel cell (used at ESRF-ID31).
A fuel cell plus a Kolibrik (kolibrick.net) potentiostat
"""

import inspect
import logging
import weakref
import functools

import gevent

from bliss.comm.util import get_comm, TCP


_FEEDBACK_MAP = {0: "Vout", 1: "Vsense", 2: "Vref", 3: "I"}
_INV_FEEDBACK_MAP = dict((v.lower(), k) for k, v in _FEEDBACK_MAP.items())


def decode_fuse_status(status):
    # TODO: decode fuse status
    return int(status)


def decode_bool(data):
    return not str(data).lower() in ("0", "false", "off")


def encode_bool(data):
    return "0" if str(data).lower() in ("0", "false", "off") else "1"


def decode_feedback(feedback):
    return _FEEDBACK_MAP[int(feedback)]


def encode_feedback(feedback):
    if isinstance(feedback, int):
        return str(feedback)
    return _INV_FEEDBACK_MAP[feedback.lower()]


_TYPE_MAP = {
    bool: (decode_bool, encode_bool),
    "feedback": (decode_feedback, encode_feedback),
    "fuse_status": (decode_fuse_status, None),
}


class FuelCellError(Exception):
    pass


class Attr(object):
    def __init__(
        self, name, decode=None, encode=None, channel=None, doc=None, unit=None
    ):
        self.name = name
        self.member_name = None  # class member name
        self.channel = channel
        self.decode = decode
        self.encode = encode
        self.doc = name if doc is None else doc
        self.unit = unit

    @property
    def readable(self):
        return self.decode is not None

    @property
    def writable(self):
        return self.encode is not None

    def __get__(self, obj, owner):
        if obj is None:
            return self
        return obj.get(self.name)[0]

    def __set__(self, obj, value):
        return obj.set(self.name, value)


BoolAttrRO = functools.partial(Attr, decode=bool)
BoolAttr = functools.partial(BoolAttrRO, encode=bool)
FloatAttrRO = functools.partial(Attr, decode=float)
FloatAttr = functools.partial(FloatAttrRO, encode=str)
IntAttrRO = functools.partial(Attr, decode=int)
IntAttr = functools.partial(IntAttrRO, encode=str)


class Group(object):
    class group(object):
        def __init__(self, g, o):
            self.__dict__.update(dict(g=g, o=o))

        def __getattr__(self, name):
            attr = self.g._attrs[name]
            return self.g.get(self.o, attr.name)

        def __setattr__(self, name, value):
            attr = self.g._attrs[name]
            return self.g.set(self.o, attr.name, value)

        def __dir__(self):
            klass = self.__class__
            return list(self.g._attrs.keys()) + list(dir(klass))

        def get_all(self):
            return self.g.get_all()

    def __init__(self, name, **attrs):
        self.name = name
        self.member_name = None
        self._attrs = attrs
        self._objs = weakref.WeakKeyDictionary()
        for k, attr in attrs.items():
            attr.name = "{0}.{1}".format(name, attr.name)
            attr.member_name = k
            setattr(self, k, attr)

    def __get__(self, obj, owner):
        if obj is None:
            return self
        return self.group(self, obj)

    def get(self, obj, name):
        return obj.get(name)[0]

    def get_all(self, obj):
        names = [attr.name for attr in self._attrs.values()]
        values = obj.get(*names)
        return dict(zip(names, values))

    def set(self, obj, name, value):
        return obj.set(name, value)

    def __set__(self, obj, value):
        raise NotImplementedError


class XCTDevice(object):

    PORT = None
    CMD_PREFIX = ""

    def __init__(self, config, port=None):
        port = self.PORT if port is None else port
        self._req_nb = 0
        self._sock = get_comm(config, ctype=TCP, port=port, eol="\r\n")

    def _write_readline(self, request):
        req_nb = self._req_nb
        self._req_nb = req_nb + 1
        req_tag = "#{0}".format(req_nb)
        req = "{0} {1}".format(req_tag, request)
        reply = self._sock.write_readline(req)
        while not reply.startswith(req_tag):
            reply = self._sock.readline()
        return reply.split(" ", 1)[1]

    def get(self, *names):
        if not names:
            return []
        commands, command_objs = [], []
        for name in names:
            cmd = self._get_xct_attr(name)
            if not cmd.readable:
                raise FuelCellError(
                    "{0}{1} is not readable".format(self.CMD_PREFIX, cmd.name)
                )
            request = "GET {0}{1}".format(self.CMD_PREFIX, cmd.name)
            commands.append(request)
            command_objs.append(cmd)

        request_line = ";".join(commands) + "\r\n"

        reply_line = self._write_readline(request_line)
        result = []
        for cmd, reply in zip(command_objs, reply_line.split(";")):
            reply = reply.strip()
            status, payload = reply.split(" ", 1)
            if status != "OK":
                raise FuelCellError(payload)
            decode = cmd.decode
            decode = _TYPE_MAP[decode][0] if decode in _TYPE_MAP else decode
            result.append(decode(payload))
        return result

    def get_all(self):
        attrs = self._get_xct_attrs()
        names = [attr.name for attr in attrs.values()]
        values = self.get(*names)
        return dict(zip(names, values))

    def set(self, *name_values):
        if not name_values:
            return
        commands, command_objs = [], []
        names, values = name_values[::2], name_values[1::2]
        for name, value in zip(names, values):
            cmd = self._get_xct_attr(name)
            if not cmd.writable:
                raise FuelCellError(
                    "{0}{1} is not writable".format(self.CMD_PREFIX, cmd.name)
                )
            encode = cmd.encode
            encode = _TYPE_MAP[encode][1] if encode in _TYPE_MAP else encode
            value_str = encode(value)
            request = "SET {0}{1} {2}".format(self.CMD_PREFIX, cmd.name, value_str)
            commands.append(request)
            command_objs.append(cmd)

        request_line = ";".join(commands) + "\r\n"

        reply_line = self._write_readline(request_line)
        errors = []
        for cmd, reply in zip(command_objs, reply_line.split(";")):
            reply = reply.strip()
            if reply != "OK":
                errors.append(reply)
        if errors:
            raise FuelCellError("\n".join(errors))

    @classmethod
    def _get_xct_attrs(cls):
        attrs = getattr(cls, "_XCTAttrs", None)
        if attrs is None:
            attrs = {}
            for member_name in dir(cls):
                obj = getattr(cls, member_name)
                if inspect.isdatadescriptor(obj):
                    if isinstance(obj, Attr):
                        obj.member_name = member_name
                        attrs[member_name] = obj
                        attrs[obj.name.lower()] = obj
                    elif isinstance(obj, Group):
                        obj.member_name = member_name
                        for attr_name, attr in obj._attrs.items():
                            attr_name = "{0}.{1}".format(member_name, attr_name)
                            attrs[attr_name] = attr
                            attrs[attr.name.lower()] = attr

            cls._XCTAttrs = attrs
        return attrs

    @classmethod
    def _get_xct_attr(cls, name):
        attrs = cls._get_xct_attrs()
        attr = attrs.get(name, attrs.get(name.lower()))
        if attr is None:
            raise KeyError("Unknown attribute {0!r}".format(name))
        return attr


class Ptc(XCTDevice):

    PORT = 20006
    CMD_PREFIX = "PTC."

    vout = FloatAttr("Vout", channel=0, doc="potentiostat output voltage", unit="V")
    vsense = FloatAttr("Vsense", channel=1, doc="potentiostat sensor voltage", unit="V")
    vref = FloatAttr("Vref", channel=2, doc="potentiostat reference voltage", unit="V")
    current = FloatAttr("I", channel=3, doc="potentiostat current", unit="A")
    set_point = FloatAttr(
        "Setpoint",
        doc="potentiostat set point (unit depends on active feedback channel",
    )
    output_enabled = BoolAttr("OutputEnabled", doc="enable/disable potentiostat output")
    feedback = Attr(
        "Feedback",
        decode="feedback",
        encode="feedback",
        doc="potentiostat feedback channel",
    )
    fuse_status = Attr(
        "FuseStatus", decode="fuse_status", doc="potentiostat fuse status"
    )
    connected = BoolAttrRO("Connected", doc="potentiostat connected")
    acq_mode = IntAttrRO(
        "AcqMode", doc="potentiostat acquisition mode (0==idle, 4==acquiring)"
    )

    def set_vout_feedback(self, vout=None):
        """
        Set the feedback mode to Vout and (optionaly) the vout setpoint
        """
        self.manual_control(feedback="Vout", set_point=vout)

    def set_vsense_feedback(self, vsense=None):
        """
        Set the feedback mode to Vsense and (optionaly) the vsense setpoint
        """
        self.manual_control(feedback="Vsense", set_point=vsense)

    def set_vref_feedback(self, vref=None):
        """
        Set the feedback mode to Vref and (optionaly) the vref setpoint
        """
        self.manual_control(feedback="Vref", set_point=vref)

    def set_current_feedback(self, current=None):
        """
        Set the feedback mode to Current and (optionaly) the current setpoint
        """
        self.manual_control(feedback="I", set_point=current)

    def manual_control(
        self, feedback=None, set_point=None, output_enabled=None, current_range=None
    ):
        args = []
        if feedback is not None:
            args += "Feedback", feedback
        if set_point is not None:
            args += "Setpoint", set_point
        if output_enabled is not None:
            args += "OutputEnabled", output_enabled
        if current_range is not None:
            args += "I", current_range
        self.set(*args)

    def reset_fuse(self):
        reply = self._write_readline("resetfuse\r\n")
        if reply != "OK":
            raise FuelCellError(reply)

    def stop(self):
        """Stop current potentiostat acquisition"""
        reply = self._write_readline("Stopacq\r\n")
        if reply != "OK":
            raise FuelCellError(reply)

    def timescan(
        self,
        sample_reduction=1,
        nb_samples_avg=1,
        channels=(vout, vsense, vref, current),
        wait=False,
    ):
        """
        Start a potentiostat time scan and (optionally) wait for it to finish.

        Keyword Args:
            sample_reduction (int): step dividing speed (1=> 50 sample/s,
                                    10=> 5 sample/s). Max is 255 (~0.2 sample/s)
                                    (default: 1)
            nb_samples_avg (int): number of samples to average
                                  ([1..sample_reduction]) (default: 1)
            channels: list of channels to measure (either Attr or string
                      representing channel name). Valid are (Vout, Vsense,
                      Vref, I) [default: (Vout, Vsense, Vref, I)]
            wait: wait for the end of scan [default: False]
                 (wait=True: not implemented yet)
        """
        if wait:
            raise NotImplementedError("wait=True not implemented yet!")
        if sample_reduction < 1 or sample_reduction > 255:
            raise ValueError("sample_reduction must be in range [1, 255]")
        if nb_samples_avg < 1 or nb_samples_avg > sample_reduction:
            raise ValueError("nb_samples_avg must be in range " "[1, sample_reduction]")

        ch_objs = [
            ch if isinstance(ch, Attr) else self._get_xct_attr(ch) for ch in channels
        ]
        channels_flag = 0

        for ch_obj in ch_objs:
            channels_flag |= 1 << ch_obj.channel
        timescan = "StartTimeScan {0} {1} {2}\r\n".format(
            channels_flag, sample_reduction, nb_samples_avg
        )
        self.stop()
        reply = self._write_readline(timescan)
        reply = reply.strip()
        if reply != "OK":
            raise FuelCellError(reply)

    # cyclic voltametry
    def cv(
        self,
        channel,
        start,
        stop,
        margin1,
        margin2,
        speed,
        sweeps=1,
        channels=(vout, vsense, vref, current),
        wait=False,
    ):
        """
        Start a potentiostat cyclic voltametry scan and (optionally)
        wait for it to finish.

        Args:
            channel: either Attr or string representing channel name). Valid
                     are (Vout, Vsense, Vref)
            start (float): starting voltage (V)
            stop (float): starting voltage (V)
            margin1 (float): scan to margin1 (V)
            margin2 (float): scan to margin2 (V)
            speed (float) : speed (mV/s)

        Keyword Args:
            sweeps: number of sweeps
            channels: list of channels to measure (either Attr or string
                      representing channel name). Valid are (Vout, Vsense,
                      Vref, I) [default: (Vout, Vsense, Vref, I)]

             wait: wait for the end of scan [default: False]
                 (wait=True: not implemented yet)
        """
        if wait:
            raise NotImplementedError("wait=True not implemented yet!")

        if isinstance(channel, Attr):
            channel_obj = channel
        else:
            channel_obj = self._get_xct_attr(channel)

        if channel_obj not in (Ptc.vout, Ptc.vsense, Ptc.vref):
            raise ValueError("Unsupported channel {0}".format(channel_obj.name))

        channel_flag = 1 << channel_obj.channel

        ch_objs = [
            ch if isinstance(ch, Attr) else self._get_xct_attr(ch) for ch in channels
        ]
        channels_flag = 0
        for ch_obj in ch_objs:
            channels_flag |= 1 << ch_obj.channel
        cv = "StartCV {0} {1} {2} {3} {4} {5} {6} {7}\r\n".format(
            channel_flag, channels_flag, start, margin1, margin2, stop, speed, sweeps
        )
        self.stop()
        reply = self._write_readline(cv)
        reply = reply.strip()
        if reply != "OK":
            raise FuelCellError(reply)

    # impedance spectroscopy
    def eis(self, *args, **kwargs):
        raise NotImplementedError


class Fcs(XCTDevice):

    PORT = 20005

    r1p_set = FloatAttr("R1SET", doc="R1 regulator set point pressure", unit="bar")
    r1p_get = FloatAttrRO("R1GET", doc="R1 regulator pressure", unit="bar")
    r1v_set = FloatAttr("R1SETV", doc="R1 regulator set point voltage", unit="V")
    r1v_get = FloatAttrRO("R1GETV", doc="R1 regulator voltage", unit="V")

    bubblerA_heater = BoolAttr("H1", doc="Heater bubbler A")  # == DIO1.O1
    bubblerN_heater = BoolAttr("H2", doc="Heater bubbler N")
    bubblerC_heater = BoolAttr("H3", doc="Heater bubbler C")
    valves_heater = BoolAttr("H4", doc="Heater valves")
    cellA_heater = BoolAttr("H5", doc="Heater cell A")
    cellC_heater = BoolAttr("H6", doc="Heater cell C")
    pipeA_heater = BoolAttr("H7", doc="Heater pipe A")
    pipeC_heater = BoolAttr("H8", doc="Heater pipe C")

    dio1 = Group(
        "DIO1",
        power=BoolAttr("O1"),
        fan=BoolAttr("O4"),
        k1rb=BoolAttrRO("DI1"),
        k1on=BoolAttrRO("DI2"),
    )

    xam1 = Group(
        "XAM1",
        h1=BoolAttr("O1"),
        h2=BoolAttr("O2"),
        h3=BoolAttr("O3"),
        h4=BoolAttr("O4"),
        pwm1=IntAttrRO("Pwm1"),
        pwm2=IntAttrRO("Pwm2"),
        pwm3=IntAttrRO("Pwm3"),
        pwm4=IntAttrRO("Pwm4"),
        t1=FloatAttrRO("XpValue1"),
        t2=FloatAttrRO("XpValue2"),
        t3=FloatAttrRO("XpValue3"),
        t4=FloatAttrRO("XpValue4"),
    )

    xam2 = Group(
        "XAM2",
        h1=BoolAttr("O1"),
        h2=BoolAttr("O2"),
        h3=BoolAttr("O3"),
        h4=BoolAttr("O4"),
        pwm1=IntAttrRO("Pwm1"),
        pwm2=IntAttrRO("Pwm2"),
        pwm3=IntAttrRO("Pwm3"),
        pwm4=IntAttrRO("Pwm4"),
        t1=FloatAttrRO("XpValue1"),
        t2=FloatAttrRO("XpValue2"),
        t3=FloatAttrRO("XpValue3"),
        t4=FloatAttrRO("XpValue4"),
    )

    power = dio1.power
    fan = dio1.fan
    k1rb = dio1.k1rb
    k1on = dio1.k1on
    heating = BoolAttr("HEATING", doc="Turns on/off selected heaters")


for i in range(28):
    name = "V{0}".format(i + 1)
    setattr(Fcs, name.lower(), BoolAttr(name))
for i in range(8):
    name = "T{0}".format(i + 1)
    setattr(Fcs, name.lower(), FloatAttrRO(name, unit="degC"))
for i in range(4):
    name = "S{0}".format(i + 1)
    member_name = "p{0}".format(i + 1)
    setattr(Fcs, member_name, FloatAttrRO(name, unit="bar"))
del i, name, member_name


def group_device(cls=None, classes=()):
    if cls is None:
        return functools.partial(group_device, classes=classes)
    for klass in classes:
        for member_name in dir(klass):
            member = getattr(klass, member_name)
            if inspect.isdatadescriptor(member):
                if isinstance(member, Attr) or isinstance(member, Group):
                    setattr(cls, member_name, member)
    return cls


@group_device(classes=(Fcs, Ptc))
class FuelCell(object):
    def __init__(self, name, config):
        self.name = name
        self.config = config
        self.ptc = Ptc(config)
        self.fcs = Fcs(config)

    def get(self, *names):
        r = len(names) * [None]
        ptc_attrs = self.ptc._get_xct_attrs()
        fcs_attrs = self.fcs._get_xct_attrs()
        ptc_name_map, fcs_name_map = {}, {}
        for i, name in enumerate(names):
            name = name.lower()
            if name in ptc_attrs:
                ptc_name_map[name] = i
            elif name in fcs_attrs:
                fcs_name_map[name] = i
            else:
                raise ValueError("Unknown attribute {0!r}".format(name))
        ptc_names = ptc_name_map.keys()
        fcs_names = fcs_name_map.keys()
        ptc_task = gevent.spawn(self.ptc.get, *ptc_names)
        fcs_task = gevent.spawn(self.fcs.get, *fcs_names)
        for value, name in zip(ptc_task.get(), ptc_names):
            r[ptc_name_map[name]] = value
        for value, name in zip(fcs_task.get(), fcs_names):
            r[fcs_name_map[name]] = value
        return r

    def set(self, *name_values):
        names, values = name_values[::2], name_values[1::2]
        ptc_attrs = self.ptc._get_xct_attrs()
        fcs_attrs = self.fcs._get_xct_attrs()
        ptc_name_values, fcs_name_values = [], []
        for name, value in zip(names, values):
            name = name.lower()
            if name in ptc_attrs:
                ptc_name_values.extend((name, value))
            elif name in fcs_attrs:
                fcs_name_values.extend((name, value))
            else:
                raise ValueError("Unknown attribute {0!r}".format(name))
        tasks = (
            gevent.spawn(self.ptc.set, *ptc_name_values),
            gevent.spawn(self.fcs.set, *fcs_name_values),
        )
        gevent.joinall(tasks)


def main():
    import argparse

    parser = argparse.ArgumentParser(description=main.__doc__)

    parser.add_argument(
        "--log-level",
        type=str,
        default="debug",
        choices=["debug", "info", "warning", "error"],
        help="log level [default: info]",
    )
    parser.add_argument("host", type=str, help="fuel cell host name")

    args = parser.parse_args()
    vargs = vars(args)

    log_level = getattr(logging, vargs.pop("log_level").upper())
    logging.basicConfig(
        level=log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    return FuelCell("Fuel Cell", dict(tcp=dict(url=args.host)))


if __name__ == "__main__":
    cell = main()
