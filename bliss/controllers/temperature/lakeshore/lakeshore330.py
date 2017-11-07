"""
Lakeshore 33* series, acessible via GPIB, Serial line or Ethernet

yml configuration example:
controller:
   class: lakeshore330
   eos: '\r\n'
   timeout: 3
#gpib
   gpib:
      url: id30oh3ls335  #enet://gpibid30b1.esrf.fr
      pad: 12
#serial line
   serial:
      url: "rfc2217://lidxxx:28003"
      baudrate: 57600
#ethernet
   tcp:
      url: idxxlakeshore:7777
   inputs:
       -
        name: ls335_A
        channel: A # or B
        #tango_server: ls_335
   outputs:
       -
        name: ls335o_1
        channel: 1 #  to 4
        units: K  #K(elvin) C(elsius) S(ensor)
   ctrl_loops:
       -
        name: ls335l_1
        input: $ls335_A
        output: $ls335o_1
        channel: 1 # to 4
"""

import time

from bliss.common import log

# communication
from bliss.comm.tcp import Tcp
from bliss.comm.gpib import Gpib
from bliss.comm import serial

from bliss.controllers.temperature.lakeshore.lakeshore import Base


class LakeShore330(object):

    def __init__(self, comm_type, url, **kwargs):
        eos = kwargs.get('eos', '\r\n')
        timeout = kwargs.get('timeout', 0.5)
        if 'gpib' in comm_type:
            self._comm = Gpib(url, pad=kwargs['extra_param'], eos=eos,
                              timeout=timeout)
        elif 'serial' or 'usb' in comm_type:
            baudrate = kwargs.get('extra_param', 9600)
            self._comm = serial.Serial(url, baudrate=baudrate,
                                       bytesize=serial.SEVENBITS,
                                       parity=serial.PARITY_ODD,
                                       stopbits=serial.STOPBITS_ONE,
                                       timeout=timeout,
                                       eol=eos)
        elif 'tcp' in comm_type:
            self._comm = Tcp(url, eol=eos, timeout=timeout)
        else:
            return RuntimeError("Unknown communication  protocol")

    def init(self, channel):
        """Set the channel name
        """
        self.channel = channel

    def clear(self):
        """Clears the bits in the Status Byte, Standard Event and Operation
           Event Registers. Terminates all pending operations.
           Returns:
              None
        """
        # see if this should not be removed
        self.send_cmd("*CLS")

    def model(self):
        """ Get the model number
            Returns:
              model (int): model number
        """
        model = self.send_cmd("*IDN?").split(',')[1]
        return int(model[5:])

    def read_temperature(self):
        """ Read the current temperature
            Returns:
              (float): current temperature [K]
        """
        return self.send_cmd("KRDG?")

    def setpoint(self, value=None):
        """ Set/Read the control setpoint
           Args:
              value (float): The value of the setpoint if set
                             None if read
           Returns:
              None if set
              value (float): The value of the setpoint if read
        """
        if value is None:
            return float(self.send_cmd("SETP?"))
        # send the setpoint
        self.send_cmd("SETP", value)

    def range(self, range=None):
        """ Set/Read the heater range (0=off 1=low 2=medium 3=high)
            Args:
              value (int): The value of the range if set
                             None if read
           Returns:
              None if set
              value (int): The value of the range if read
        """
        if value is None:
            return float(self.send_cmd("RANGE?"))
        # send the range
        self.send_cmd("RANGE", value)

    def read_ramp_rate(self):
        """ Read the current ramprate
            Returns:
              (float): current ramprate [K/min]
        """
        try:
            value = self.send_cmd("RAMP?").split(',')[1]
            return float(value)
        except (ValueError, AttributeError):
            raise RuntimeError("Invalid answer from the controller")

    def set_ramp_rate(self, value):
        """ Set the control setpoint ramp rate. Explicitly stop the ramping.
            Args:
              value (float): The ramp rate [K/min] 0.1 - 100
              start (int):   0 (stop) or 1 (start) the ramping
            Returns:
              None
        """
        self.send_cmd("RAMP", 0, value)

    def ramp(self, sp, rate):
        """Change temperature to a set value at a controlled rate
            Args:
              rate (float): ramp rate [K/min], values 0.1 to 100
              sp (float): target setpoint [K]
            Returns:
              None
        """
        self.setpoint(sp)
        self.send_cmd("RAMP", 1, rate)

    def pid(self, **kwargs):
        """ Read/Set Control Loop PID Values (P, I, D)
           Args:
               P (float): Proportional gain (0.1 to 1000)
               I (float): Integral reset (0.1 to 1000) [value/s]
               D (float): Derivative rate (0 to 200) [%]
               None if read
           Returns:
               None if set
               p (float): P
               i (float): I
               d (float): D
        """
        kp = kwargs.get('P')
        ki = kwargs.get('I')
        kd = kwargs.get('D')
        if None not in (kp, ki, kd):
            self.send_cmd("PID", kp, ki, kd)
        else:
            try:
                kp, ki, kd = self.send_cmd("PID?").split(',')
                return float(kp), float(ki), float(kd)
            except (ValueError, AttributeError):
                raise RuntimeError("Invalid answer from the controller")

    def send_cmd(self, command, *args):
        """Send a command to the controller
           Args:
              command (str): The command string
              args: Possible variable number of parameters
           Returns:
              None
        """
        if '?' in command:
            return self._comm.write_readline(command + ' %r' % self.channel)
        elif command.startswith('*'):
            self._comm.write(command)
        else:
            inp = ','.join(str(x) for x in args)
            self._comm.write(command + ' %d,%s *OPC' % (self.channel, inp))


class lakeshore330(Base):
    def __init__(self, config, *args):
        comm_type = None
        extra_param = None
        if 'gpib' in config:
            comm_type = 'gpib'
            url = config['gpib']['url']
            extra_param = config['gpib']['pad']
            eos = config.get('gpib').get('eos', "\r\n")
        elif 'serial' in config:
            comm_type = 'serial'
            url = config['serial']['url']
            extra_param = config.get('serial').get('baudrate')
            eos = config.get('serial').get('eos', "\r\n")
        elif 'tcp' in config:
            comm_type = 'tcp'
            url = config['tcp']['url']
            eos = config.get('tcp').get('eos', "\r\n")
        else:
            raise ValueError("Must specify gpib or serial url")

        _lakeshore = LakeShore330(comm_type, url,
                                  extra_param=extra_param,
                                  eos=eos)
        Base.__init__(self, _lakeshore, config, *args)


if __name__ == '__main__':
    ls_obj = LakeShore330('gpib', 'id30oh3ls335', addr=12)

    for i in range(100):
        print ls_obj.read_temperature()
        time.sleep(10)
