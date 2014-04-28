import gevent
from gevent import socket, select, lock, event

import re
import struct
import serial
from serial import rfc2217
#import all rfc2217 protol keys in this module
key_match = re.compile('^[A-Z_]+$')
pro_keys_dict = dict([(x,rfc2217.__dict__[x]) for x in dir(rfc2217) if key_match.match(x)])
globals().update(pro_keys_dict)
from serial.rfc2217 import TelnetOption,TelnetSubnegotiation,RFC2217_PARITY_MAP,RFC2217_STOPBIT_MAP

import weakref
import os

def try_open(fu) :
    def rfunc(self,*args,**kwarg) :
        self.open()
        return fu(self,*args,**kwarg)
    return rfunc

class _BaseSerial:
    def __init__(self,cnt,port):
        self._cnt = weakref.ref(cnt)
        self._port = port

        self._data = ''
        self._event = event.Event()
        self._rx_filter = None

    def _init(self):
        self._raw_read_task = gevent.spawn(self._raw_read)

    def readline(self, eol, timeout):
        timeout_errmsg = "timeout on serial(%s)" % (self._port)
        with gevent.Timeout(timeout, RuntimeError(timeout_errmsg)):
            eol_pos = self._data.find(eol)
            while eol_pos == -1:
                self._event.wait()
                self._event.clear()
                eol_pos = self._data.find(eol)

        msg = self._data[:eol_pos]
        self._data = self._data[eol_pos + len(eol):]
        return msg

    def read(self, size, timeout):
        timeout_errmsg = "timeout on serial(%s)" % (self._port)
        with gevent.Timeout(timeout,RuntimeError(timeout_errmsg)):
            while len(self._data) < size:
                self._event.wait()
                self._event.clear()
        msg = self._data[:size]
        self._data = self._data[size + 1:]
        return msg
    
    def write(self,msg,timeout) :
        timeout_errmsg = "timeout on serial(%s)" % (self._port)
        with gevent.Timeout(timeout,RuntimeError(timeout_errmsg)):
            while msg:
                _,ready,_ = select.select([],[self.fd],[])
                size_send = os.write(self.fd,msg)
                msg = msg[size_send:]

    def raw_read(self, maxsize, timeout):
        timeout_errmsg = "timeout on serial(%s)" % (self._port)
        with gevent.Timeout(timeout,RuntimeError(timeout_errmsg)):
            while not self._data:
                self._event.wait()
                self._event.clear()
        if maxsize:
            msg = self._data[:maxsize]
            self._data = self._data[maxsize + 1:]
        else:
            msg = self._data
            self._data = ''
        return msg
 
    def _raw_read(self):
        try:
            while(1):
                ready,_,_ = select.select([self.fd],[],[])
                raw_data = os.read(self.fd,4096)
                if raw_data:
                    if self._rx_filter:
                        raw_data = self._rx_filter(raw_data)
                    self._data += raw_data
                    self._event.set()
                else:
                    break
        except:
            pass
        finally:
            cnt = self._cnt()
            if cnt:
                cnt._raw_handler = None

class LocalSerial(_BaseSerial):
    def __init__(self,cnt,**keys):
        _BaseSerial.__init__(self,cnt,keys.get('port'))
        self.__serial = serial.Serial(**keys)
        self.fd = self.__serial.fd
        self._init()

    def flushInput(self):
        self.__serial.flushInput()
        self._data = ''

    def close(self) :
        self.__serial.close()

class RFC2217(_BaseSerial):
    class TelnetCmd:
        def __init__(self):
            self.data = ''
        def telnetSendOption(self,action,option) :
            self.data += ''.join([IAC,action,option])

    class TelnetSubNego:
        def __init__(self) :
            self.data = ''
            self.logger = None

        def rfc2217SendSubnegotiation(self,option,value):
            value = value.replace(IAC, IAC_DOUBLED)
            self.data += ''.join([IAC, SB, COM_PORT_OPTION, option] + 
                                 list(value) + [IAC, SE])

    def __init__(self,cnt,port,baudrate,
                 bytesize,parity,stopbits,
                 timeout,xonxoff,rtscts,writeTimeout,
                 dsrdtr,interCharTimeout):
        _BaseSerial.__init__(self,cnt,port)
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

        port_parse = re.compile('^(rfc2217://)?([^:/]+?):([0-9]+)$')
        match = port_parse.match(port)
        if match is None:
            raise RuntimeError('RFC2217: port is not a valid url (%s)' % port)

        local_host,local_port = match.group(2),match.group(3)
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.connect((local_host, local_port))
        self._socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.fd = self._socket.fileno()
        self._init()

        telnet_cmd = self.TelnetCmd()
        #get code from rfc2217 in serial module
        # name the following separately so that, below, a check can be easily done
        mandatory_options = [
            TelnetOption(telnet_cmd, 'we-BINARY', BINARY, WILL, WONT, DO, DONT, INACTIVE),
            TelnetOption(telnet_cmd, 'we-RFC2217', COM_PORT_OPTION, WILL, WONT, DO, DONT, REQUESTED),
        ]
        # all supported telnet options
        self.telnet_options = [
            TelnetOption(telnet_cmd, 'ECHO', ECHO, DO, DONT, WILL, WONT, REQUESTED),
            TelnetOption(telnet_cmd, 'we-SGA', SGA, WILL, WONT, DO, DONT, REQUESTED),
            TelnetOption(telnet_cmd, 'they-SGA', SGA, DO, DONT, WILL, WONT, REQUESTED),
            TelnetOption(telnet_cmd, 'they-BINARY', BINARY, DO, DONT, WILL, WONT, INACTIVE),
            TelnetOption(telnet_cmd, 'they-RFC2217', COM_PORT_OPTION, DO, DONT, WILL, WONT, REQUESTED),
        ] + mandatory_options
        
        telnet_sub_cmd = self.TelnetSubNego()
        self.rfc2217_port_settings = {
            'baudrate': TelnetSubnegotiation(telnet_sub_cmd, 'baudrate', SET_BAUDRATE, SERVER_SET_BAUDRATE),
            'datasize': TelnetSubnegotiation(telnet_sub_cmd, 'datasize', SET_DATASIZE, SERVER_SET_DATASIZE),
            'parity':   TelnetSubnegotiation(telnet_sub_cmd, 'parity',   SET_PARITY,   SERVER_SET_PARITY),
            'stopsize': TelnetSubnegotiation(telnet_sub_cmd, 'stopsize', SET_STOPSIZE, SERVER_SET_STOPSIZE),
            }
        self.rfc2217_options = {
            'purge':    TelnetSubnegotiation(telnet_sub_cmd, 'purge',    PURGE_DATA,   SERVER_PURGE_DATA),
            'control':  TelnetSubnegotiation(telnet_sub_cmd, 'control',  SET_CONTROL,  SERVER_SET_CONTROL),
            }
        self.rfc2217_options.update(self.rfc2217_port_settings)

        # negotiate Telnet/RFC 2217 -> send initial requests
        for option in self.telnet_options:
            if option.state is REQUESTED:
                telnet_cmd.telnetSendOption(option.send_yes,option.option)

        self._socket.send(telnet_cmd.data)
        telnet_cmd.data = ''

        #Read telnet negotiation
        with gevent.Timeout(5.,RuntimeError("timeout on serial negotiation(%s)",
                                            self._port)):
            while(1):
                self._parse_nego(telnet_cmd)
                if sum(o.active for o in mandatory_options) == len(mandatory_options):
                    break

            #configure port
            self.rfc2217_port_settings['baudrate'].set(struct.pack('!I', self.baudrate))
            self.rfc2217_port_settings['datasize'].set(struct.pack('!B', self.bytesize))
            self.rfc2217_port_settings['parity'].set(struct.pack('!B', RFC2217_PARITY_MAP[self.parity]))
            self.rfc2217_port_settings['stopsize'].set(struct.pack('!B', RFC2217_STOPBIT_MAP[self.stopbits]))

            if self.rtscts and self.xonxoff:
                raise ValueError('xonxoff and rtscts together are not supported')
            elif self.rtscts:
                self.rfc2217_options['control'].set(SET_CONTROL_USE_HW_FLOW_CONTROL)
            elif self.xonxoff:
                self.rfc2217_options['control'].set(SET_CONTROL_USE_SW_FLOW_CONTROL)
            else:
                self.rfc2217_options['control'].set(SET_CONTROL_USE_NO_FLOW_CONTROL)

            self._socket.send(telnet_sub_cmd.data)
            telnet_sub_cmd.data = ''
            items = self.rfc2217_port_settings.values()
            while(1):
                self._parse_nego(telnet_cmd)
                if sum(o.active for o in items) == len(items):
                    break


        #check rtscts,xonxoff or no flow control
        while not self.rfc2217_options['control'].isReady():
            self._parse_nego(self.telnet_options,telnet_cmd,self.rfc2217_options)
        
        #plug the data filter
        self._rx_filter = self._rfc2217_filter
        self._pending_data = None

    def write(self,msg,timeout):
        msg = msg.replace(IAC,IAC_DOUBLED)
        _BaseSerial.write(self,msg,timeout)
    
    def flushInput(self) :
        telnet_cmd = self.telnet_options[0].connection
        purge = self.rfc2217_options['purge']
        telnet_sub_cmd = purge.connection
        purge.set(PURGE_RECEIVE_BUFFER)
        self._data = ''
        self._rx_filter = None
        self._socket.send(telnet_sub_cmd.data)
        telnet_sub_cmd.data = ''

        while not purge.isReady():
            self._parse_nego(telnet_cmd)
        self._rx_filter = self._rfc2217_filter
        self._data = ''

    def _rfc2217_filter(self,data):
        if data[-1] == IAC and data[-2] != IAC:
            self._pending_data = data
            return ''

        if self._pending_data:
            data = self._pending_data + data
            self._pending_data = None
        return data.replace(IAC_DOUBLED,IAC)

    def _parse_nego(self,telnet_cmd):
        iac_pos = -1
        while 1:
            while iac_pos == -1 or len(self._data[iac_pos:]) < 3:
                self._event.wait()
                self._event.clear()
                iac_pos = self._data.find(IAC)

            if len(self._data[iac_pos:]) > 2 and self._data[iac_pos+1] == IAC:  # ignore double IAC
                self._data = self._data[iac_pos+2:]
            else:
                _,command,option = self._data[iac_pos:iac_pos+3]
                self._data = self._data[iac_pos+3:]
                if command != SB:
                    #ignore other command than
                    if command in (DO, DONT, WILL, WONT):
                        known = False
                        for item in self.telnet_options:
                            if item.option == option:
                                item.process_incoming(command)
                                known = True

                        if not known:
                            if command == WILL:
                                telnet_cmd.telnetSendOption(DONT,option)
                            elif command == DO:
                                telnet_cmd.telnetSendOption(WONT,option)
                else:           # sub-negotiation
                    se_pos = self._data.find(IAC + SE)
                    while se_pos == -1:
                        self._event.wait()
                        self._event.clear()
                        se_pos = self._data.find(IAC + SE)
                    suboption,value = self._data[0],self._data[1:se_pos]
                    self._data = self._data[se_pos+2:]
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
                                    item.checkAnswer(value)
                                    break
                    
            iac_pos = self._data.find(IAC)
            #check if we need to send extra command
            if iac_pos == -1: # no more negotiation rx
                if telnet_cmd.data:
                    self._socket.send(telnet_cmd.data)
                    telnet_cmd.data = ''
                else:
                    break

    def close(self):
        self._socket.close()

        
class Serial:
    LOCAL,RFC2217 = range(2)

    def __init__(self,port=None, 
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
                 eol = '\n') :

        self._serial_kwargs = {
            "port":port,
            "baudrate":baudrate,
            "bytesize":bytesize,
            "parity":parity,
            "stopbits":stopbits,
            "timeout":timeout,
            "xonxoff":xonxoff,
            "rtscts":rtscts,
            "writeTimeout":writeTimeout,
            "dsrdtr":dsrdtr,
            "interCharTimeout":interCharTimeout,
            }
        self._eol = eol
        self._timeout = timeout
        self._raw_handler = None
        self._lock = lock.Semaphore()

    def __del__(self) :
        if self._raw_handler:
            self._raw_handler.close()

    def open(self) :
        if self._raw_handler is None:
            serial_type = self._check_type()
            if serial_type == self.RFC2217:
                self._raw_handler = RFC2217(self,**self._serial_kwargs)
            else:                   # LOCAL
                self._raw_handler = LocalSerial(self,**self._serial_kwargs)
        
    def close(self) :
        if self._raw_handler:
            self._raw_handler.close()
            self._raw_handler = None
        
    @try_open
    def raw_read(self,maxsize = None,timeout = None) :
        local_timeout = timeout or self._timeout
        return self._raw_handler.raw_read(maxsize,local_timeout)
                
    @try_open
    def read(self,size=1,timeout=None):
        local_timeout = timeout or self._timeout
        msg = self._raw_handler.read(size,local_timeout)
        if len(msg) != size:
            raise RuntimeError("read timeout on serial (%s)" % self._serial_kwargs.get(port,''))
        return msg

    @try_open
    def readline(self,eol = None,timeout = None) :
        local_eol = eol or self._eol
        local_timeout = timeout or self._timeout
        return self._raw_handler.readline(local_eol,local_timeout)
    
    @try_open
    def write(self,msg,timeout=None) :
        with self._lock:
            return self._raw_handler.write(msg,timeout)
        
    @try_open
    def write_read(self,msg,write_synchro=None,size=1,timeout=None) :
        local_timeout = timeout or self._timeout
        with self._lock:
            self._raw_handler.write(msg,local_timeout)
            if write_synchro: write_synchro.notify()
            return self.read(size,local_timeout)

    @try_open
    def write_readline(self,msg,write_synchro = None,
                       eol = None,timeout = None) :
        local_eol = eol or self._eol
        local_timeout = timeout or self._timeout
        with self._lock:
            self._raw_handler.write(msg,local_timeout)
            if write_synchro: write_synchro.notify()
            return self.readline(local_eol,local_timeout)

    def flush(self) :
        if self._raw_handler:
            self._raw_handler.flushInput()

    def _check_type(self) :
        port = self._serial_kwargs.get('port','')
        if port.lower().startswith("rfc2217://"):
            return self.RFC2217
        else:
            return self.LOCAL
