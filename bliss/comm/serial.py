# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


__all__ = ["LocalSerial", "RFC2217", "SER2NET", "TangoSerial", "Serial"]

import os
import re
import struct
import logging
import weakref

import gevent
from gevent import socket, select, lock, event
from ..common.greenlet_utils import KillMask
from bliss.common.cleanup import capture_exceptions
from .util import HexMsg

import serial

try:
    from serial import rfc2217
    from serial import serialutil
except ImportError:
    pass
else:
    # import all rfc2217 protol keys in this module
    key_match = re.compile(r"^[A-Z_]+$")
    pro_keys_dict = dict(
        [(x, rfc2217.__dict__[x]) for x in dir(rfc2217) if key_match.match(x)]
    )
    globals().update(pro_keys_dict)
    from serial.rfc2217 import (
        TelnetOption,
        TelnetSubnegotiation,
        RFC2217_PARITY_MAP,
        RFC2217_STOPBIT_MAP,
    )

from . import tcp
from .exceptions import CommunicationError, CommunicationTimeout


class SerialError(CommunicationError):
    pass


class SerialTimeout(CommunicationTimeout):
    pass


def try_open(fu):
    def rfunc(self, *args, **kwarg):
        try:
            with KillMask():
                self.open()
                return fu(self, *args, **kwarg)
        except gevent.Timeout:
            raise
        except:
            try:
                self.close()
            except:
                pass
            raise

    return rfunc


class _BaseSerial:
    def __init__(self, cnt, port):
        self._cnt = weakref.ref(cnt)
        self._port = port

        self._data = b""
        self._event = event.Event()
        self._rx_filter = None
        self._rpipe, self._wpipe = os.pipe()
        self._raw_read_task = None

    def _init(self):
        self._raw_read_task = gevent.spawn(
            self._raw_read_loop, weakref.proxy(self), self.fd, self._rpipe
        )

    def _timeout_context(self, timeout):
        timeout_errmsg = "timeout on serial(%s)" % (self._port)
        return gevent.Timeout(timeout, SerialTimeout(timeout_errmsg))

    def _close(self):
        if self._wpipe:
            os.write(self._wpipe, b"|")
        if self._raw_read_task:
            self._raw_read_task.join()
            self._raw_read_task = None

    def readline(self, eol, timeout):
        with self._timeout_context(timeout):
            return self._readline(eol)

    def _readline(self, eol):
        if not isinstance(eol, bytes):
            eol = eol.encode()
        eol_pos = self._data.find(eol)
        with capture_exceptions() as capture:
            while eol_pos == -1:
                with capture():
                    self._event.wait()
                    self._event.clear()

                eol_pos = self._data.find(eol)

                if capture.failed:
                    other_exc = [
                        x
                        for _, x, _ in capture.failed
                        if not isinstance(x, gevent.Timeout)
                    ]
                    if not other_exc:
                        if eol_pos == -1:
                            continue
                    else:
                        break

            msg = self._data[:eol_pos]
            self._data = self._data[eol_pos + len(eol) :]
            self._cnt()._debug("Rx: %r %r ", msg, HexMsg(msg))
            return msg

    def read(self, size, timeout):
        with self._timeout_context(timeout):
            return self._read(size)

    def _read(self, size):
        with capture_exceptions() as capture:
            while len(self._data) < size:
                with capture():
                    self._event.wait()
                    self._event.clear()
                if capture.failed:
                    other_exc = [
                        x
                        for _, x, _ in capture.failed
                        if not isinstance(x, gevent.Timeout)
                    ]
                    if not other_exc:
                        if len(self._data) < size:
                            continue
                    else:
                        break
            msg = self._data[:size]
            self._data = self._data[size:]
            self._cnt()._debug("Rx: %r %r ", msg, HexMsg(msg))
            return msg

    def write(self, msg, timeout):
        with self._timeout_context(timeout):
            return self._write(msg)

    def _write(self, msg):
        self._cnt()._debug("Tx: %r %r ", msg, HexMsg(msg))
        while msg:
            _, ready, _ = select.select([], [self.fd], [])
            size_send = os.write(self.fd, msg)
            msg = msg[size_send:]

    def raw_read(self, maxsize, timeout):
        with self._timeout_context(timeout):
            return self._raw_read(maxsize)

    def _raw_read(self, maxsize):
        while not self._data:
            self._event.wait()
            self._event.clear()
        if maxsize:
            msg = self._data[:maxsize]
            self._data = self._data[maxsize:]
        else:
            msg = self._data

            self._data = b""
        self._cnt()._debug("Rx: %r %r ", msg, HexMsg(msg))
        return msg

    @staticmethod
    def _raw_read_loop(ser, fd, rp):
        try:
            while 1:
                ready, _, _ = select.select([fd, rp], [], [])
                if rp in ready:
                    break
                raw_data = os.read(fd, 4096)
                if raw_data:
                    if ser._rx_filter:
                        raw_data = ser._rx_filter(raw_data)
                    ser._data += raw_data
                    ser._event.set()
                else:
                    break
        except:
            pass
        finally:
            try:
                cnt = ser._cnt()
                if cnt:
                    cnt._raw_handler = None
            except ReferenceError:
                pass


class LocalSerial(_BaseSerial):
    def __init__(self, cnt, **keys):
        _BaseSerial.__init__(self, cnt, keys.get("port"))
        try:
            self.__serial = serial.Serial(**keys)
        except:
            self.__serial = None
            raise
        self.fd = self.__serial.fd
        self._init()

    def __del__(self):
        self.close()

    def flushInput(self):
        self.__serial.flushInput()
        self._data = b""

    def close(self):
        self._close()
        if self.__serial:
            self.__serial.close()


class RFC2217Error(SerialError):
    pass


class RFC2217Timeout(SerialTimeout):
    pass


class RFC2217(_BaseSerial):
    class TelnetCmd:
        def __init__(self):
            self.data = b""

        def telnet_send_option(self, action, option):
            self.data += b"".join([IAC, action, option])

    class TelnetSubNego:
        def __init__(self):
            self.data = b""
            self.logger = None

        def rfc2217_send_subnegotiation(self, option, value):
            value = value.replace(IAC, IAC_DOUBLED)
            self.data += IAC + SB + COM_PORT_OPTION + option + value + IAC + SE

    def __init__(
        self,
        cnt,
        port,
        baudrate,
        bytesize,
        parity,
        stopbits,
        timeout,
        xonxoff,
        rtscts,
        writeTimeout,
        dsrdtr,
        interCharTimeout,
    ):
        _BaseSerial.__init__(self, cnt, port)
        self.baudrate = baudrate
        self.bytesize = bytesize
        self.parity = parity
        self.stopbits = stopbits
        self.xonxoff = xonxoff
        self.rtscts = rtscts
        self.dsrdtr = dsrdtr
        # cache for line and modem states that the server sends to us
        self._linestate = 0
        self._modemstate = None
        self._modemstate_expires = 0
        # RFC 2217 flow control between server and client
        self._remote_suspend_flow = False

        port_parse = re.compile(r"^(rfc2217://)?([^:/]+?):([0-9]+)$")
        match = port_parse.match(port)
        if match is None:
            raise RFC2217Error("port is not a valid url (%s)" % port)

        local_host, local_port = match.group(2), match.group(3)
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.connect((local_host, int(local_port)))
        self._socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._socket.setsockopt(socket.SOL_IP, socket.IP_TOS, 0x10)
        self.fd = self._socket.fileno()
        self._init()

        telnet_cmd = self.TelnetCmd()
        # get code from rfc2217 in serial module
        # name the following separately so that, below, a check can be easily done
        mandatory_options = [
            TelnetOption(
                telnet_cmd, "we-BINARY", BINARY, WILL, WONT, DO, DONT, INACTIVE
            ),
            TelnetOption(
                telnet_cmd,
                "we-RFC2217",
                COM_PORT_OPTION,
                WILL,
                WONT,
                DO,
                DONT,
                REQUESTED,
            ),
        ]
        # all supported telnet options
        self.telnet_options = [
            TelnetOption(telnet_cmd, "ECHO", ECHO, DO, DONT, WILL, WONT, REQUESTED),
            TelnetOption(telnet_cmd, "we-SGA", SGA, WILL, WONT, DO, DONT, REQUESTED),
            TelnetOption(telnet_cmd, "they-SGA", SGA, DO, DONT, WILL, WONT, REQUESTED),
            TelnetOption(
                telnet_cmd, "they-BINARY", BINARY, DO, DONT, WILL, WONT, INACTIVE
            ),
            TelnetOption(
                telnet_cmd,
                "they-RFC2217",
                COM_PORT_OPTION,
                DO,
                DONT,
                WILL,
                WONT,
                REQUESTED,
            ),
        ] + mandatory_options

        telnet_sub_cmd = self.TelnetSubNego()
        self.rfc2217_port_settings = {
            "baudrate": TelnetSubnegotiation(
                telnet_sub_cmd, "baudrate", SET_BAUDRATE, SERVER_SET_BAUDRATE
            ),
            "datasize": TelnetSubnegotiation(
                telnet_sub_cmd, "datasize", SET_DATASIZE, SERVER_SET_DATASIZE
            ),
            "parity": TelnetSubnegotiation(
                telnet_sub_cmd, "parity", SET_PARITY, SERVER_SET_PARITY
            ),
            "stopsize": TelnetSubnegotiation(
                telnet_sub_cmd, "stopsize", SET_STOPSIZE, SERVER_SET_STOPSIZE
            ),
        }
        self.rfc2217_options = {
            "purge": TelnetSubnegotiation(
                telnet_sub_cmd, "purge", PURGE_DATA, SERVER_PURGE_DATA
            ),
            "control": TelnetSubnegotiation(
                telnet_sub_cmd, "control", SET_CONTROL, SERVER_SET_CONTROL
            ),
        }
        self.rfc2217_options.update(self.rfc2217_port_settings)

        # negotiate Telnet/RFC 2217 -> send initial requests
        for option in self.telnet_options:
            if option.state is REQUESTED:
                telnet_cmd.telnet_send_option(option.send_yes, option.option)

        self._socket.send(telnet_cmd.data)
        telnet_cmd.data = b""

        # Read telnet negotiation
        with gevent.Timeout(
            5., RFC2217Timeout("timeout on serial negotiation(%s)" % self._port)
        ):
            while 1:
                self._parse_nego(telnet_cmd)
                if sum(o.active for o in mandatory_options) == len(mandatory_options):
                    break

            # configure port
            self.rfc2217_port_settings["baudrate"].set(struct.pack("!I", self.baudrate))
            self.rfc2217_port_settings["datasize"].set(struct.pack("!B", self.bytesize))
            self.rfc2217_port_settings["parity"].set(
                struct.pack("!B", RFC2217_PARITY_MAP[self.parity])
            )
            self.rfc2217_port_settings["stopsize"].set(
                struct.pack("!B", RFC2217_STOPBIT_MAP[self.stopbits])
            )

            if self.rtscts and self.xonxoff:
                raise ValueError("xonxoff and rtscts together are not supported")
            elif self.rtscts:
                self.rfc2217_options["control"].set(SET_CONTROL_USE_HW_FLOW_CONTROL)
            elif self.xonxoff:
                self.rfc2217_options["control"].set(SET_CONTROL_USE_SW_FLOW_CONTROL)
            else:
                self.rfc2217_options["control"].set(SET_CONTROL_USE_NO_FLOW_CONTROL)

            self._socket.send(telnet_sub_cmd.data)
            telnet_sub_cmd.data = b""
            items = self.rfc2217_port_settings.values()
            while 1:
                self._parse_nego(telnet_cmd)
                if sum(o.active for o in items) == len(items):
                    break

        # check rtscts,xonxoff or no flow control
        while not self.rfc2217_options["control"].is_ready():
            self._parse_nego(self.telnet_options, telnet_cmd, self.rfc2217_options)

        # plug the data filter
        self._rx_filter = self._rfc2217_filter
        self._pending_data = None

    def __del__(self):
        self.close()

    def write(self, msg, timeout):
        msg = msg.replace(IAC, IAC_DOUBLED)
        _BaseSerial.write(self, msg, timeout)

    def flushInput(self):
        telnet_cmd = self.telnet_options[0].connection
        purge = self.rfc2217_options["purge"]
        telnet_sub_cmd = purge.connection
        purge.set(PURGE_RECEIVE_BUFFER)
        self._data = b""
        self._rx_filter = None
        self._socket.send(telnet_sub_cmd.data)
        telnet_sub_cmd.data = b""

        while not purge.is_ready():
            self._parse_nego(telnet_cmd)
        self._rx_filter = self._rfc2217_filter
        self._data = b""

    def _rfc2217_filter(self, data):
        if data[-1] == IAC and data[-2] != IAC:
            self._pending_data = data
            return b""

        if self._pending_data:
            data = self._pending_data + data
            self._pending_data = None
        return data.replace(IAC_DOUBLED, IAC)

    def _parse_nego(self, telnet_cmd):
        iac_pos = -1
        while 1:
            while iac_pos == -1 or len(self._data[iac_pos:]) < 3:
                self._event.wait()
                self._event.clear()
                iac_pos = self._data.find(IAC)

            if (
                len(self._data[iac_pos:]) > 2 and self._data[iac_pos + 1] == IAC
            ):  # ignore double IAC
                self._data = self._data[iac_pos + 2 :]
            else:
                _, command, option = serialutil.iterbytes(
                    self._data[iac_pos : iac_pos + 3]
                )
                self._data = self._data[iac_pos + 3 :]
                if command != SB:
                    # ignore other command than
                    if command in (DO, DONT, WILL, WONT):
                        known = False
                        for item in self.telnet_options:
                            if item.option == option:
                                item.process_incoming(command)
                                known = True

                        if not known:
                            if command == WILL:
                                telnet_cmd.telnet_send_option(DONT, option)
                            elif command == DO:
                                telnet_cmd.telnet_send_option(WONT, option)
                else:  # sub-negotiation
                    se_pos = self._data.find(IAC + SE)
                    while se_pos == -1:
                        self._event.wait()
                        self._event.clear()
                        se_pos = self._data.find(IAC + SE)
                    suboption, value = self._data[0:1], self._data[1:se_pos]
                    self._data = self._data[se_pos + 2 :]
                    if option == COM_PORT_OPTION:
                        if suboption == SERVER_NOTIFY_LINESTATE:
                            self._linestate = ord(value)
                        elif suboption == SERVER_NOTIFY_MODEMSTATE:
                            self._modemstate = ord(value)
                        elif suboption == FLOWCONTROL_SUSPEND:
                            self._remote_suspend_flow = True
                        elif suboption == FLOWCONTROL_RESUME:
                            self._remote_suspend_flow = False
                        else:
                            for item in self.rfc2217_options.values():
                                if item.ack_option == suboption:
                                    item.check_answer(value)
                                    break

            iac_pos = self._data.find(IAC)
            # check if we need to send extra command
            if iac_pos == -1:  # no more negotiation rx
                if telnet_cmd.data:
                    self._socket.send(telnet_cmd.data)
                    telnet_cmd.data = b""
                break

    def close(self):
        self._close()
        if self._socket:
            self._socket.close()


class SER2NETError(SerialError):
    pass


class SER2NET(RFC2217):
    def __init__(self, cnt, **keys):
        # just in case it cant open the serial
        self._wpipe = None
        self._raw_read_task = None
        self._socket = None

        port = keys.pop("port")
        port_parse = re.compile(r"^(ser2net://)?([^:/]+?):([0-9]+)(.+)$")
        match = port_parse.match(port)
        if match is None:
            raise SER2NETError("port is not a valid url (%s)" % port)
        comm = tcp.Command(match.group(2), int(match.group(3)), eol="\r\n->")
        msg = b"showshortport\n\r"
        rx = comm.write_readline(msg)
        msg_pos = rx.find(msg)
        rx = rx[msg_pos + len(msg) :]
        rx = rx.decode()
        port_parse = re.compile(r"^([0-9]+).+?%s" % match.group(4))
        rfc2217_port = None
        for line in rx.split("\r\n"):
            g = port_parse.match(line)
            if g:
                rfc2217_port = int(g.group(1))
                break
        if rfc2217_port is None:
            raise SER2NETError("port %s is not found on server" % match.group(4))

        keys["port"] = "rfc2217://%s:%d" % (match.group(2), rfc2217_port)
        RFC2217.__init__(self, cnt, **keys)

    def __del__(self):
        self.close()


class TangoSerial(_BaseSerial):
    """Tango serial line"""

    SL_RAW = 0
    SL_NCHAR = 1
    SL_LINE = 2
    SL_RETRY = 3

    SL_NONE = 0
    SL_ODD = 1
    SL_EVEN = 3

    SL_STOP1 = 0
    SL_STOP15 = 1
    SL_STOP2 = 2

    SL_TIMEOUT = 3
    SL_PARITY = 4
    SL_CHARLENGTH = 5
    SL_STOPBITS = 6
    SL_BAUDRATE = 7
    SL_NEWLINE = 8

    FLUSH_INPUT = 0
    FLUSH_OUTPUT = 1
    FLUSH_BOTH = 2

    PARITY_MAP = {
        serial.PARITY_NONE: SL_NONE,
        serial.PARITY_ODD: SL_ODD,
        serial.PARITY_EVEN: SL_EVEN,
    }

    STOPBITS_MAP = {
        serial.STOPBITS_ONE: SL_STOP1,
        serial.STOPBITS_TWO: SL_STOP2,
        serial.STOPBITS_ONE_POINT_FIVE: SL_STOP15,
    }

    PAR_MAP = {
        SL_BAUDRATE: ("baudrate", lambda o, v: int(v)),
        SL_CHARLENGTH: ("bytesize", lambda o, v: int(v)),
        SL_PARITY: ("parity", lambda o, v: o.PARITY_MAP[v]),
        SL_STOPBITS: ("stopbits", lambda o, v: o.STOPBITS_MAP[v]),
        SL_TIMEOUT: ("timeout", lambda o, v: int(v * 1000)),
        SL_NEWLINE: ("eol", lambda o, v: ord(v[-1])),
    }

    def __init__(self, cnt, **kwargs):
        _BaseSerial.__init__(self, cnt, kwargs.get("port"))
        self._device = None
        self._pars = kwargs
        self._last_eol = kwargs["eol"] = cnt._eol
        del self._data
        del self._event
        del self._rpipe, self._wpipe
        # import tango here to prevent import serial from failing in places
        # were tango is not installed
        from PyTango import GreenMode
        from PyTango.client import Object, get_object_proxy

        device = Object(kwargs["port"], green_mode=GreenMode.Gevent)
        timeout = kwargs.get("timeout")
        if timeout:
            get_object_proxy(device).set_timeout_millis(int(timeout * 1000))
        args = []
        kwargs["eol"] = cnt._eol
        for arg, (key, encode) in self.PAR_MAP.items():
            args.append(arg)
            args.append(encode(self, kwargs[key]))
        device.DevSerSetParameter(args)
        self._device = device

    def close(self):
        self._device = None

    def _readline(self, eol):
        lg = len(eol)

        if eol != self._last_eol:
            _, eol_encode = self.PAR_MAP[self.SL_NEWLINE]
            self._device.DevSerSetNewline(eol_encode(self, eol))
            self._last_eol = eol

        buff = b""
        while True:
            line = self._device.DevSerReadLine() or b""
            if line == b"":
                return b""
            buff += line
            if buff[-lg:] == eol:
                return buff[:-lg]

    def _raw_read(self, maxsize):
        if maxsize:
            return self._device.DevSerReadNChar(maxsize) or b""
        else:
            return self._device.DevSerReadRaw() or b""

    _read = _raw_read

    def _write(self, msg):
        self._device.DevSerWriteChar(bytearray(msg))

    def flushInput(self):
        self._device.DevSerFlush(self.FLUSH_INPUT)


class Serial:
    LOCAL, RFC2217, SER2NET, TANGO = list(range(4))

    def __init__(
        self,
        port=None,
        baudrate=9600,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=5.,
        xonxoff=False,
        rtscts=False,
        writeTimeout=None,
        dsrdtr=False,
        interCharTimeout=None,
        eol=b"\n",
    ):

        self._serial_kwargs = {
            "port": port,
            "baudrate": baudrate,
            "bytesize": bytesize,
            "parity": parity,
            "stopbits": stopbits,
            "timeout": timeout,
            "xonxoff": xonxoff,
            "rtscts": rtscts,
            "writeTimeout": writeTimeout,
            "dsrdtr": dsrdtr,
            "interCharTimeout": interCharTimeout,
        }
        self._port = port
        self._eol = eol
        self._timeout = timeout
        self._raw_handler = None
        self._lock = lock.RLock()
        self._logger = logging.getLogger(str(self))
        self._debug = self._logger.debug

    def __del__(self):
        self.close()

    def __str__(self):
        return "{0}({1})".format(self.__class__.__name__, self._serial_kwargs["port"])

    @property
    def lock(self):
        return self._lock

    def open(self):
        if self._raw_handler is None:
            serial_type = self._check_type()
            self._debug("open - serial_type=%s" % serial_type)
            if serial_type == self.RFC2217:
                self._raw_handler = RFC2217(self, **self._serial_kwargs)
            elif serial_type == self.SER2NET:
                self._raw_handler = SER2NET(self, **self._serial_kwargs)
            elif serial_type == self.TANGO:
                self._raw_handler = TangoSerial(self, **self._serial_kwargs)
            else:  # LOCAL
                self._raw_handler = LocalSerial(self, **self._serial_kwargs)

    def close(self):
        self._debug("close")
        if self._raw_handler:
            self._raw_handler.close()
            self._raw_handler = None

    @try_open
    def raw_read(self, maxsize=None, timeout=None):
        local_timeout = timeout or self._timeout
        return self._raw_handler.raw_read(maxsize, local_timeout)

    def read(self, size=1, timeout=None):
        with self._lock:
            return self._read(size, timeout)

    @try_open
    def _read(self, size=1, timeout=None):
        local_timeout = timeout or self._timeout
        msg = self._raw_handler.read(size, local_timeout)
        if len(msg) != size:
            raise SerialError(
                "read timeout on serial (%s)" % self._serial_kwargs.get(self._port, "")
            )
        return msg

    def readline(self, eol=None, timeout=None):
        with self._lock:
            return self._readline(eol, timeout)

    @try_open
    def _readline(self, eol=None, timeout=None):
        local_eol = eol or self._eol
        local_timeout = timeout or self._timeout
        return self._raw_handler.readline(local_eol, local_timeout)

    def write(self, msg, timeout=None):
        if isinstance(msg, str):
            raise TypeError("a bytes-like object is required, not 'str'")
        with self._lock:
            return self._write(msg, timeout)

    @try_open
    def _write(self, msg, timeout=None):
        local_timeout = timeout or self._timeout
        return self._raw_handler.write(msg, local_timeout)

    def write_read(self, msg, write_synchro=None, size=1, timeout=None):
        if isinstance(msg, str):
            raise TypeError("a bytes-like object is required, not 'str'")
        with self._lock:
            self._write(msg, timeout)
            if write_synchro:
                write_synchro.notify()
            return self._read(size, timeout)

    def write_readline(self, msg, write_synchro=None, eol=None, timeout=None):
        if isinstance(msg, str):
            raise TypeError("a bytes-like object is required, not 'str'")
        with self._lock:
            self._write(msg, timeout)
            if write_synchro:
                write_synchro.notify()
            return self._readline(eol, timeout)

    def write_readlines(
        self, msg, nb_lines, write_synchro=None, eol=None, timeout=None
    ):
        if isinstance(msg, str):
            raise TypeError("a bytes-like object is required, not 'str'")
        with self._lock:
            self._write(msg, timeout)
            if write_synchro:
                write_synchro.notify()

            str_list = []
            for ii in range(nb_lines):
                str_list.append(self._readline(eol=eol, timeout=timeout))

            return str_list

    @try_open
    def flush(self):
        self._raw_handler.flushInput()

    def _check_type(self):
        port = self._serial_kwargs.get("port", "")
        port_lower = port.lower()
        if port_lower.startswith("rfc2217://"):
            return self.RFC2217
        elif port_lower.startswith("ser2net://"):
            return self.SER2NET
        elif port_lower.startswith("tango://"):
            return self.TANGO
        else:
            return self.LOCAL
