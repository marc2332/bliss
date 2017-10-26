"""
Lakeshore 33* series, acessible via GPIB

yml configuration example:
class: lakeshore330
gpib_url: id30oh3ls335  #enet://gpibid30b1.esrf.fr
gpib_pad: 12
inputs:
    -
        name: ls335_A
        channel: A #  or B
        units: K  #K(elvin) C(elsius) S(ensor)
        #tango_server: ls_335
outputs:
    -
        name: ls335_1
        channel: 1 #  or 2
        units: K  #K(elvin) C(elsius) S(ensor)
"""

import time

from bliss.common import log
from bliss.comm.gpib import Gpib
from bliss.comm import serial

from bliss.controllers.temperature.lakeshore.lakeshore import Base

class LakeShore330(object):
    def __init__(self, comm_type, url, *kwargs):
        eos = kwargs.get('eos', '\r\n')
        timeout = kwargs.get('timeout', 0.5)
        if 'gpib' in comm_type:
            self._comm = Gpib(url, pad=kwargs['addr'], eos=eos,
                              timeout=timeout)
        elif 'serial' or 'usb' in comm_type:
            baudrate = kwargs.get('addr', 9600)
            self._comm = serial.Serial(url, baudrate=baudrate,
                                       bytesize=serial.SEVENBITS,
                                       parity=serial.PARITY_ODD,
                                       stopbits=serial.STOPBITS_ONE,
                                       eol=eos)
        else:
            return RuntimeError("Unknown communication  protocol")

        self.channel = kwargs.get("channel", "A")

    def clear(self):
        """Clears the bits in the Status Byte, Standard Event and Operation
           Event Registers. Terminates all pending operations.
           Returns:
              None
        """
        self.send_cmd("*CLS")

    def read_temperature(self):
        """ Read the current temperature
            Returns:
              (float): current temperature [K]
        """
        return self.send_cmd("KRDG? %r" % self.channel)

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
            return float(self.send_cmd("SETP? %d" % self.channel))
        # send the setpoint
        self.send_cmd("SETP %d" % self.channel, value)

    def read_ramp_rate(self):
        """ Read the current ramp rate
            Returns:
              (float): current ramp rate [K/min]
        """
        asw = self.send_cmd("RAMP? %d" % self.channel)
        try:
            _, value = asw.split(',')
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
        self.send_cmd("RAMP %d" % self.channel, 0, value)

    def ramp(self, sp, rate):
        """Change temperature to a set value at a controlled rate
           Args:
              rate (float): ramp rate [K/min], values 0.1 to 100
              sp (float): target setpoint [K]
           Returns:
              None
        """
        self.setpoint(sp)
        self.send_cmd("RAMP %d" % self.channel, 1, rate)

    def send_cmd(self, command, *args):
        """Send a command to the controller
           Args:
              command (str): The command string
              args: Possible variable number of parameters
           Returns:
              None
        """
        if '?' in command:
            return self._comm.write_readline(command)
        elif command.startswith('*'):
            self._comm.write(command)
        else:
            inp = ','.join(str(x) for x in args)
            self._comm.write(command + ' %s,%s' % (self.channel, inp))


class lakeshore330(Base):
    def __init__(self, config, *args):
        channel = config.get('channel')
        comm_type = None

        if 'gpib_url' in config:
            comm_type = 'gpib'
            url = config['gpib_url']
            addr = config['gpib_pad']
            eos = config.get('gpib_eos', '\r\n')
        elif 'serial' in config:
            comm_type = 'serial'
            url = config['serial_url']
            addr = config.get('baudrate')
            eos = config.get('eol', '\r\n')
        else:
            raise ValueError("Must specify gpib or serial url")

        _lakeshore = LakeShore330(comm_type, url,
                                  addr=addr,
                                  eso=eos,
                                  channel=channel)
        Base.__init__(self, _lakeshore, config, *args)


if __name__ == '__main__':
    ls_obj = LakeShore330('gpib', 'id30oh3ls335', addr=12)

    for i in range(100):
        print ls_obj.read_temperature()
        time.sleep(10)
