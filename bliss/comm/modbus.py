# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import struct
import weakref
from functools import wraps
from gevent import socket, select
from gevent import lock
from gevent import queue
import gevent
import errno
import numpy

from .exceptions import CommunicationError, CommunicationTimeout
from ..common.greenlet_utils import KillMask, protect_from_kill
from . import serial

from bliss.common import session
from bliss.common.logtools import LogMixin


class ModbusError(CommunicationError):
    pass


class ModbusTimeout(CommunicationTimeout):
    pass


def _error_code(msg):
    error_code = struct.unpack("B", msg)[0]
    errors = {
        0x01: "Illegal Function",
        0x02: "Illegal Data Address",
        0x03: "Illegal Data Value",
        0x04: "Slave Device Failure",
        0x05: "Acknowledge, The slave has accepted the request but it'll take time",  # probably not an error
        0x06: "Slave Device Busy",
        0x07: "Negative Acknowledge",
        0x08: "Memory Parity Error",
        0x0A: "Gateway Path Unavailable",
        0x0B: "Gateway Target Device Failed to Respond",
    }
    return errors.get(error_code, "Unknown")


# ---------------------------------------------------------------------------#
# Error Detection Functions
# ---------------------------------------------------------------------------#
def __generate_crc16_table():
    """ Generates a crc16 lookup table
    .. note:: This will only be generated once
    """
    result = []
    for byte in range(256):
        crc = 0x0000
        for _ in range(8):
            if (byte ^ crc) & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
            byte >>= 1
        result.append(crc)
    return result


_crc16_table = __generate_crc16_table()


class Modbus_ASCII:
    def __init__(self, raw_com):
        self._raw_com = raw_com

    def computeLRC(self, data):
        """ Used to compute the longitudinal redundancy check
        against a string. This is only used on the serial ASCII
        modbus protocol. A full description of this implementation
        can be found in appendex B of the serial line modbus description.

        :param data: The data to apply a lrc to
        :returns: The calculated LRC

        """
        lrc = sum(data) & 0xff
        lrc = (lrc ^ 0xff) + 1
        return lrc & 0xff


class Modbus_RTU(LogMixin):
    def __init__(self, node, *args, **kwargs):
        self._serial = serial.Serial(*args, **kwargs)
        self.node = node
        self._lock = lock.RLock()
        session.get_current().map.register(self, children_list=[self._serial])

    def __del__(self):
        self._serial.close()

    def __str__(self):
        return "{0}({1})".format(self.__class__.__name__, self._serial)

    @property
    def lock(self):
        return self._lock

    def computeCRC(self, data):
        """ Computes a crc16 on the passed in string. For modbus,
        this is only used on the binary serial protocols (in this
        case RTU).

        The difference between modbus's crc16 and a normal crc16
        is that modbus starts the crc value out at 0xffff.

        :param data: The data to create a crc16 of
        :returns: The calculated CRC
        """
        crc = 0xFFFF
        for a in data:
            idx = _crc16_table[(crc ^ a) & 0xFF]
            crc = ((crc >> 8) & 0xFF) ^ idx
        swapped = ((crc << 8) & 0xFF00) | ((crc >> 8) & 0x00FF)
        return swapped

    def read_holding_registers(self, address, struct_format, timeout=None):
        timeout_errmsg = "timeout on read_holding_registers modbus rtu (%s)" % (
            self._serial
        )
        nb_bytes = struct.calcsize(struct_format)
        if nb_bytes < 2:  # input register are 16bits
            nb_bytes = 2
            struct_format = "x" + struct_format
        nb_bytes /= 2
        return self._read(
            0x03, address, nb_bytes, struct_format, timeout_errmsg, timeout
        )

    def write_register(self, address, struct_format, value, timeout=None):
        timeout_errmsg = "timeout on write_register modbus rtu (%s)" % (self._serial)
        self.write_registers(address, struct_format, (value,), timeout=timeout)

    def write_registers(self, address, struct_format, values, timeout=None):
        timeout_errmsg = "timeout on write_registers modbus rtu (%s)" % (self._serial)
        self._write(0x10, address, struct_format, values, timeout_errmsg, timeout)

    def read_input_registers(self, address, struct_format, timeout=None):
        timeout_errmsg = "timeout on read_input_registers modbus rtu (%s)" % (
            self._serial
        )
        nb_bytes = struct.calcsize(struct_format)
        if nb_bytes < 2:  # input register are 16bits
            nb_bytes = 2
            struct_format = "x" + struct_format
        nb_bytes /= 2
        return self._read(
            0x04, address, nb_bytes, struct_format, timeout_errmsg, timeout
        )

    def read_coils(self, address, nb_coils, timeout=None):
        timeout_errmsg = "timeout on read_coils modbus rtu (%s)" % (self._serial)
        nb_bytes = ((nb_coils + 7) & ~7) // 8
        struct_format = "%dB" % nb_bytes
        result = self._read(
            0x01, address, nb_coils, struct_format, timeout_errmsg, timeout
        )
        if isinstance(result, tuple):
            result = [int("{0:08b}".format(x)[::-1], 2) for x in result]
        else:
            result = int("{0:08b}".format(result)[::-1], 2)
        a = numpy.array(result, dtype=numpy.uint8)
        return numpy.unpackbits(a)[:nb_coils]

    def write_coil(self, address, on_off, timeout=None):
        timeout_errmsg = "timeout on write_coil modbus rtu (%s)" % (self._serial)
        value = 0xFF00 if on_off else 0x0000
        self._write(0x05, address, "H", value, timeout_errmsg, timeout)

    def _read(self, func_code, address, nb, struct_format, timeout_errmsg, timeout):
        msg = self._cmd(address, func_code, nb)
        data = struct.unpack(">%s" % struct_format, msg)
        return data if len(data) > 1 else data[0]

    def _write(self, func_code, address, struct_format, value, timeout_errmsg, timeout):
        if isinstance(value, (tuple, list)):
            data_write = struct.pack(">%s" % struct_format, *value)
        else:
            data_write = struct.pack(">%s" % struct_format, value)
        nb_bytes = struct.calcsize(struct_format) / 2
        msg = self._cmd(address, func_code, nb_bytes, data_write)
        return struct.unpack(">H", msg)[0]

    @protect_from_kill
    def _fstatus(self, timeout=None):
        timeout_errmsg = "timeout on read_fstatus modbus rtu (%s)" % (self._serial)
        func_code = 0x07
        msg = struct.pack(">BB", self.node, func_code)
        msg += struct.pack(">H", self.computeCRC(msg))

        with self.lock:
            self._serial.write(msg)

            raw_msg = self._serial.read(5)
            rx_node, rx_func_code, status_byte, rx_crc = struct.unpack(">BBBH", raw_msg)

            if rx_node != self.node:
                raise ModbusError(
                    "Wrong device address rx: %s expected: %s" % (rx_node, self.node)
                )

            if rx_func_code != func_code:
                if (rx_func_code & 0x80) == func_code:
                    raise ModbusError("Rx Error %s", _error_code(status_byte))
                else:
                    #                    self._serial.flushInput()
                    self._serial.flush()
                    raise ModbusError(
                        "Wrong function code rx: %s expected: %s"
                        % (rx_func_code, func_code)
                    )

        crc = self.computeCRC(raw_msg[:-2])
        if rx_crc != crc:
            raise ModbusError("Wrong CRC")

        return status_byte

    @protect_from_kill
    def _cmd(self, address, func_code, nb, data_write=None):
        #        msg = struct.pack('>BBHH',self.node,func_code,address,nb)
        nb = int(
            nb
        )  # in python2 is was always int in python3 it occured to be float, so we make sure it is always int
        msg = struct.pack(">BBH", self.node, func_code, address)
        if data_write is not None:  # write
            if func_code is 0x5:
                msg += struct.pack(">%ds" % len(data_write), data_write)
            else:
                msg += struct.pack(">HB%ds" % len(data_write), nb, nb * 2, data_write)
        else:
            msg += struct.pack(">H", nb)
        msg += struct.pack(">H", self.computeCRC(msg))

        #        timeout=3
        #        with gevent.Timeout(timeout or self._timeout, ModbusTimeout(timeout_errmsg)):

        with self.lock:

            self._serial.write(msg)
            if data_write is not None:  # WRITE
                raw_msg = self._serial.read(4)
                rx_node, rx_func_code, first_address = struct.unpack(">BBH", raw_msg)
                nb_bytes = 2
            else:  # READ
                raw_msg = self._serial.read(3)
                rx_node, rx_func_code, nb_bytes = struct.unpack(">BBB", raw_msg)

            if rx_node != self.node:
                raise ModbusError(
                    "Wrong device address rx: %s expected: %s" % (rx_node, self.node)
                )

            if rx_func_code != func_code:
                if (rx_func_code & 0x80) == func_code:
                    crc = self._serial.read(2)
                    raise ModbusError("Rx Error %s", _error_code(nb_bytes))
                else:
                    #                    self._serial.flushInput()
                    self._serial.flush()
                    raise ModbusError(
                        "Wrong function code rx: %s expected: %s"
                        % (rx_func_code, func_code)
                    )

            data_and_crc = self._serial.read(nb_bytes + 2)

        data = data_and_crc[:-2]
        rx_crc = struct.unpack(">H", data_and_crc[-2:])[0]
        crc = self.computeCRC(raw_msg + data)
        if rx_crc != crc:
            raise ModbusError("Wrong CRC")
        return data


def try_connect_modbustcp(fu):
    @wraps(fu)
    def rfunc(self, *args, **kwargs):
        timeout = kwargs.get("timeout")
        if not self._connected:
            self.connect(timeout=timeout)
        try:
            with KillMask():
                return fu(self, *args, **kwargs)
        except socket.error as e:
            if e.errno == errno.EPIPE:
                # some modbus controller close the connection
                # give a chance to _raw_read_task to detect it
                gevent.sleep(0)
                self.connect(timeout=timeout)
                with KillMask():
                    return fu(self, *args, **kwargs)
            else:
                raise

    return rfunc


class ModbusTcp:
    """ ModbusTcp

    Before each modbus TCP message is an MBAP header which is used as a
    message frame.  It allows us to easily separate messages as follows::

        [         MBAP Header         ] [ Function Code] [ Data ]
        [ tid ][ pid ][ length ][ uid ]
          2b     2b     2b        1b           1b           Nb

        while len(message) > 0:
            tid, pid, length`, uid = struct.unpack(">HHHB", message)
            request = message[0:7 + length - 1`]
            message = [7 + length - 1:]

        * length = uid + function code + data
        * The -1 is to account for the uid byte
    """

    class Transaction:
        def __init__(self, modbustcp):
            self.__modbus = weakref.proxy(modbustcp)
            self._tid = 0
            self._queue = queue.Queue()

        def __enter__(self):
            if self.__modbus._transaction:
                self._tid = max(self.__modbus._transaction.keys()) + 1
                if self._tid > 0xFFFF:
                    for i, key in enumerate(sorted(self.__modbus._transaction.keys())):
                        if i != key:
                            break
                    self._tid = i
            self.__modbus._transaction[self._tid] = self
            return self

        def __exit__(self, *args):
            self.__modbus._transaction.pop(self._tid)

        def tid(self):
            return self._tid

        def get(self):
            return self._queue.get()

        def put(self, msg):
            self._queue.put(msg)

    def __init__(self, host, unit=0xFF, port=502, timeout=3.0):
        self._unit = unit  # modbus unit
        self._host = host
        self._port = port
        self._timeout = timeout
        self._fd = None
        self._connected = False
        self._raw_read_task = None
        self._transaction = {}
        self._lock = lock.RLock()

    def __del__(self):
        self.close()

    @property
    def lock(self):
        return self._lock

    ##@brief read holding registers
    @try_connect_modbustcp
    def read_holding_registers(self, address, struct_format, timeout=None):
        timeout_errmsg = "timeout on read_holding_registers modbus tcp (%s, %d)" % (
            self._host,
            self._port,
        )
        nb_bytes = struct.calcsize(struct_format)
        if nb_bytes < 2:  # register are 16bits
            nb_bytes = 2
            struct_format = "x" + struct_format
        nb_bytes /= 2
        return self._read(
            0x03, address, nb_bytes, struct_format, timeout_errmsg, timeout
        )

    @try_connect_modbustcp
    def write_register(self, address, struct_format, value, timeout=None):
        timeout_errmsg = "timeout on write_register modbus tcp (%s, %d)" % (
            self._host,
            self._port,
        )
        self._write(0x06, address, struct_format, value, timeout_errmsg, timeout)

    @try_connect_modbustcp
    def write_float(self, address, value, timeout=None):

        timeout_errmsg = "timeout on write_registers modbus tcp (%s, %d)" % (
            self._host,
            self._port,
        )

        func_code = 0x10
        with self.Transaction(self) as trans:
            with gevent.Timeout(
                timeout or self._timeout, ModbusTimeout(timeout_errmsg)
            ):
                quantityOfRegisters = 2
                byteCount = 2 * quantityOfRegisters
                msg = struct.pack(
                    ">HHBf", address, quantityOfRegisters, byteCount, value
                )
                self._raw_write(trans.tid(), func_code, msg)

                read_values = trans.get()
                if isinstance(read_values, socket.error):
                    raise read_values
                uid, func_code_answer, msg = read_values
                if func_code != func_code_answer:  # Error
                    raise ModbusError(
                        "Error expecting func code %s intead of %s"
                        % (func_code, _error_code(msg))
                    )
                # in this case received msg should contain starting address and qty of registers

    @try_connect_modbustcp
    def read_input_registers(self, address, struct_format, timeout=None):
        timeout_errmsg = "timeout on read_input_registers modbus tcp (%s, %d)" % (
            self._host,
            self._port,
        )
        nb_bytes = struct.calcsize(struct_format)
        if nb_bytes < 2:  # input register are 16bits
            nb_bytes = 2
            struct_format = "x" + struct_format
        nb_bytes /= 2
        return self._read(
            0x04, address, nb_bytes, struct_format, timeout_errmsg, timeout
        )

    @try_connect_modbustcp
    def read_coils(self, address, nb_coils, timeout=None):
        timeout_errmsg = "timeout on read_coils tcp (%s, %d)" % (self._host, self._port)
        nb_bytes = ((nb_coils + 7) & ~7) // 8
        struct_format = "%dB" % nb_bytes
        result = self._read(
            0x01, address, nb_coils, struct_format, timeout_errmsg, timeout
        )
        if isinstance(result, tuple):
            result = [int("{0:08b}".format(x)[::-1], 2) for x in result]
        else:
            result = int("{0:08b}".format(result)[::-1], 2)
        a = numpy.array(result, dtype=numpy.uint8)
        return numpy.unpackbits(a)[:nb_coils]

    @try_connect_modbustcp
    def write_coil(self, address, on_off, timeout=None):
        timeout_errmsg = "timeout on write_coil tcp (%s, %d)" % (self._host, self._port)
        value = 0xFF00 if on_off else 0x0000
        self._write(0x05, address, "H", value, timeout_errmsg, timeout)

    def connect(self, host=None, port=None, timeout=None):
        local_host = host or self._host
        local_port = port or self._port
        local_timeout = timeout if timeout is not None else self._timeout
        self.close()

        with self._lock:
            if self._connected:
                return True

            with gevent.Timeout(
                local_timeout, RuntimeError("Cannot connect to %s" % self._host)
            ):
                self._fd = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._fd.connect((local_host, local_port))
                self._fd.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                self._fd.setsockopt(socket.SOL_IP, socket.IP_TOS, 0x10)
                self._host = local_host
                self._port = local_port
                self._raw_read_task = gevent.spawn(
                    self._raw_read, weakref.proxy(self), self._fd
                )
            self._connected = True

        return True

    def close(self):
        if self._connected:
            try:
                self._fd.shutdown(socket.SHUT_RDWR)
            except:  # probably closed one the server side
                pass

            self._fd.close()

            if self._raw_read_task:
                self._raw_read_task.join()
                self._raw_read_task = None

    def _read(self, func_code, address, nb, struct_format, timeout_errmsg, timeout):
        with self.Transaction(self) as trans:
            with gevent.Timeout(
                timeout or self._timeout, ModbusTimeout(timeout_errmsg)
            ):
                msg = struct.pack(">HH", address, int(nb))
                self._raw_write(trans.tid(), func_code, msg)
                read_values = trans.get()
                if isinstance(read_values, socket.error):
                    raise read_values
                uid, f_code, msg = read_values
                if f_code != func_code:  # Error
                    raise ModbusError(
                        "Error expecting func code %s instead of %s"
                        % (func_code, _error_code(msg))
                    )
                returnVal = struct.unpack(">%s" % struct_format, msg[1:])
                return returnVal if len(returnVal) > 1 else returnVal[0]

    def _write(self, func_code, address, struct_format, value, timeout_errmsg, timeout):
        with self.Transaction(self) as trans:
            with gevent.Timeout(
                timeout or self._timeout, ModbusTimeout(timeout_errmsg)
            ):
                msg = struct.pack(">H" + struct_format, address, value)
                self._raw_write(trans.tid(), func_code, msg)
                read_values = trans.get()
                if isinstance(read_values, socket.error):
                    raise read_values
                uid, func_code_read, msg = read_values
                if func_code != func_code_read:  # Error
                    raise ModbusError(
                        "Error expecting func code %s intead of %s"
                        % (func_code, _error_code(msg))
                    )

    def _raw_write(self, tid, func, msg):
        full_msg = struct.pack(">HHHBB", tid, 0, len(msg) + 2, self._unit, func) + msg
        with self._lock:
            self._fd.sendall(full_msg)

    @staticmethod
    def _raw_read(modbus, fd):
        data = b""

        try:
            while 1:
                raw_data = fd.recv(16 * 1024)
                if raw_data:
                    data += raw_data
                    if len(data) > 7:
                        tid, pid, length, uid = struct.unpack(">HHHB", data[:7])
                        if len(data) >= length + 6:  # new msg
                            func_code = data[7]
                            end_msg = 8 + length - 2
                            msg = data[8:end_msg]
                            data = data[end_msg:]
                            transaction = modbus._transaction.get(tid)
                            if transaction:
                                transaction.put((uid, func_code, msg))
                else:
                    break
        except:
            pass
        finally:
            fd.close()
            try:
                modbus._connected = False
                modbus._fd = None
                # inform all pending requests that the socket closed
                for trans in modbus._transaction.values():
                    trans.put(socket.error(errno.EPIPE, "Broken pipe"))
            except ReferenceError:
                pass
