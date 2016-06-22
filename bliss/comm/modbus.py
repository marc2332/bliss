# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import struct
import weakref
from gevent import socket,select
from gevent import lock
from gevent import queue
import gevent
import errno
import numpy

from .common import CommunicationError, CommunicationTimeout


class ModbusError(CommunicationError):
    pass


class ModbusTimeout(CommunicationTimeout):
    pass


#---------------------------------------------------------------------------#
# Error Detection Functions
#---------------------------------------------------------------------------#
def __generate_crc16_table():
    ''' Generates a crc16 lookup table

    .. note:: This will only be generated once
    '''
    result = []
    for byte in range(256):
        crc = 0x0000
        for _ in range(8):
            if (byte ^ crc) & 0x0001:
                crc = (crc >> 1) ^ 0xa001
            else: crc >>= 1
            byte >>= 1
        result.append(crc)
    return result

__crc16_table = __generate_crc16_table()

class Modbus_ASCII:
    def __init__(self,raw_com) :
        self._raw_com = raw_com

    def computeLRC(self,data):
        ''' Used to compute the longitudinal redundancy check
        against a string. This is only used on the serial ASCII
        modbus protocol. A full description of this implementation
        can be found in appendex B of the serial line modbus description.

        :param data: The data to apply a lrc to
        :returns: The calculated LRC

        '''
        lrc = sum(ord(a) for a in data) & 0xff
        lrc = (lrc ^ 0xff) + 1
        return lrc & 0xff

class Modbus_RTU:
    def __init__(self,raw_com) :
        self._raw_com = raw_com

    def computeCRC(self,data):
        ''' Computes a crc16 on the passed in string. For modbus,
        this is only used on the binary serial protocols (in this
        case RTU).

        The difference between modbus's crc16 and a normal crc16
        is that modbus starts the crc value out at 0xffff.

        :param data: The data to create a crc16 of
        :returns: The calculated CRC
        '''
        crc = 0xffff
        for a in data:
            idx = __crc16_table[(crc ^ ord(a)) & 0xff];
            crc = ((crc >> 8) & 0xff) ^ idx
        swapped = ((crc << 8) & 0xff00) | ((crc >> 8) & 0x00ff)
        return swapped




def try_connect_modbustcp(fu):
    def rfunc(self, *args, **kwarg):
        if(not self._connected):
            self.connect()
        try:
            return fu(self, *args, **kwarg)
        except socket.error as e:
            if e.errno == errno.EPIPE:
                # some modbus controller close the connection
                # give a chance to _raw_read_task to detect it
                gevent.sleep(0)
                self.connect()
                return fu(self,*args,**kwarg)
            else:
                raise
    return rfunc

class ModbusTcp:
    ''' ModbusTcp

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
    '''
    class Transaction:
        def __init__(self,modbustcp) :
            self.__modbus = weakref.proxy(modbustcp)
            self._tid = 0
            self._queue = queue.Queue()

        def __enter__(self) :
            if self.__modbus._transaction:
                self._tid = max(self.__modbus._transaction.keys()) + 1
                if self._tid > 0xffff:
                    for i,key in enumerate(sorted(self.__modbus._transaction.keys())) :
                        if i != key:
                            break
                    self._tid = i
            self.__modbus._transaction[self._tid] = self
            return self

        def __exit__(self,*args):
            self.__modbus._transaction.pop(self._tid)
        
        def tid(self) :
            return self._tid

        def get(self):
            return self._queue.get()

        def put(self,msg):
            self._queue.put(msg)

    def __init__(self,host,unit = 0xFF,port=502,timeout=3.):
        self._unit = unit       # modbus unit
        self._host = host
        self._port = port
        self._timeout = timeout
        self._fd = None
        self._connected = False
        self._raw_read_task = None
        self._transaction = {}
        self._lock = lock.Semaphore()

    def __del__(self):
        self.close()

    ##@brief read holding registers
    @try_connect_modbustcp
    def read_holding_registers(self,address,struct_format,timeout=None):
        timeout_errmsg = "timeout on read_holding_registers modbus tcp (%s, %d)" % (self._host, self._port)
        nb_bytes = struct.calcsize(struct_format)
        if nb_bytes < 2:        # register are 16bits
            nb_bytes = 2
            struct_format = 'x' + struct_format
        nb_bytes /= 2
        return self._read(0x03,address,nb_bytes,struct_format,timeout_errmsg,timeout)
                
    @try_connect_modbustcp
    def write_register(self,address,struct_format,value,timeout = None):
        timeout_errmsg = "timeout on write_register modbus tcp (%s, %d)" % (self._host, self._port)
        self._write(0x06,address,struct_format,value,timeout_errmsg,timeout)

    @try_connect_modbustcp
    def read_input_registers(self,address,struct_format,timeout=None):
        timeout_errmsg = "timeout on read_input_registers modbus tcp (%s, %d)" % (self._host, self._port)
        nb_bytes = struct.calcsize(struct_format)
        if nb_bytes < 2:        # input register are 16bits
            nb_bytes = 2
            struct_format = 'x' + struct_format
        nb_bytes /= 2
        return self._read(0x04,address,nb_bytes,struct_format,timeout_errmsg,timeout)

    @try_connect_modbustcp
    def read_coils(self,address,nb_coils,timeout=None):
        timeout_errmsg = "timeout on read_coils tcp (%s, %d)" % (self._host, self._port)
        nb_bytes = (((nb_coils + 7) & ~7) // 8)
        struct_format = '%dB' % nb_bytes
        result = self._read(0x01,address,nb_coils,struct_format,timeout_errmsg,timeout)
        if isinstance(result,tuple):
            result = [int('{:08b}'.format(x)[::-1], 2) for x in result]
        else:
            result = int('{:08b}'.format(result)[::-1], 2)
        a = numpy.array(result,dtype=numpy.uint8)
        return numpy.unpackbits(a)[:nb_coils]

    @try_connect_modbustcp
    def write_coil(self,address,on_off,timeout=None):
         timeout_errmsg = "timeout on write_coil tcp (%s, %d)" % (self._host, self._port)
         value = 0xff00 if on_off else 0x0000
         self._write(0x05,address,'H',value,timeout_errmsg,timeout)

    def connect(self,host=None,port=None):
        local_host = host or self._host
        local_port = port or self._port

        self.close()
        
        self._fd = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._fd.connect((local_host,local_port))
        self._fd.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._connected = True
        self._host = local_host
        self._port = local_port
        self._raw_read_task = gevent.spawn(self._raw_read,
                                           weakref.proxy(self),self._fd)
        return True

    def close(self):
        if self._connected:
            try:
                self._fd.shutdown(socket.SHUT_RDWR)
            except:             # probably closed one the server side
                pass
            self._fd.close()
            if self._raw_read_task:
                self._raw_read_task.join()
                self._raw_read_task = None

    def _read(self,func_code,address,nb,struct_format,timeout_errmsg,timeout):
        with self.Transaction(self) as trans:
            with gevent.Timeout(timeout or self._timeout,
                                ModbusTimeout(timeout_errmsg)):
                msg = struct.pack('>HH',address,nb)
                self._raw_write(trans.tid(),func_code,msg)
                read_values = trans.get()
                if isinstance(read_values,socket.error):
                    raise read_values
                uid,f_code,msg = read_values
                if f_code != func_code: # Error
                    raise ModbusError('Error expecting func code %s instead of %s' %
                                      (func_code,self._error_code(msg)))
                returnVal = struct.unpack('>%s' % struct_format,msg[1:])
                return returnVal if len(returnVal) > 1 else returnVal[0]

    def _write(self,func_code,address,struct_format,value,timeout_errmsg,timeout):
        with self.Transaction(self) as trans:
            with gevent.Timeout(timeout or self._timeout,
                                ModbusTimeout(timeout_errmsg)):
                msg = struct.pack('>H' + struct_format,address,value)
                self._raw_write(trans.tid(),func_code,msg)
                read_values = trans.get()
                if isinstance(read_values,socket.error):
                    raise read_values
                uid,func_code,msg = read_values
                if func_code != func_code: # Error
                    raise ModbusError('Error expecting func code %s intead of %s' %
                                      (func_code,self._error_code(msg)))

    def _raw_write(self,tid,func,msg) :
        full_msg = struct.pack('>HHHBB',tid,0,len(msg) + 2,self._unit,func) + msg
        with self._lock:
            self._fd.sendall(full_msg)

    def _error_code(self,msg) :
        error_code = struct.unpack('B',msg)[0]
        errors = {
            0x01: "Illegal Function",
            0x02: "Illegal Data Address",
            0x03: "Illegal Data Value",
            0x04: "Slave Device Failure",
            0x05: "Acknowledge, The slave has accepted the request but it'll take time", # probably not an error
            0x06: "Slave Device Busy",
            0x07: "Negative Acknowledge",
            0x08: "Memory Parity Error",
            0x0A: "Gateway Path Unavailable",
            0x0B: "Gateway Target Device Failed to Respond",
        }
        return errors.get(error_code,"Unknown")

    @staticmethod
    def _raw_read(modbus,fd):
        data = ''
        try:
            while(1):
                raw_data = fd.recv(16 * 1024)
                if raw_data:
                    data += raw_data
                    if len(data) > 7:
                        tid,pid,lenght,uid = struct.unpack('>HHHB',data[:7])
                        if len(data) >= lenght + 6: # new complet msg
                            func_code = ord(data[7])
                            end_msg = 8 + lenght - 2
                            msg = data[8:end_msg]
                            data = data[end_msg:]
                            transaction = modbus._transaction.get(tid)
                            if transaction:
                                transaction.put((uid,func_code,msg))
                else:
                    break
        except:
            pass
        finally:
            fd.close()
            try:
                modbus._connected = False
                modbus._fd = None
                #inform all pending requests that the socket closed
                for trans in modbus._transaction.values():
                    trans.put(socket.error(errno.EPIPE,"Broken pipe"))
            except ReferenceError:
                pass
