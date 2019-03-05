# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Lakeshore 340, acessible via GPIB, Serial line or Ethernet

yml configuration example:
controller:
   class: lakeshore340
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

# from bliss.common import log
import logging

# communication
from bliss.comm.tcp import Tcp
from bliss.comm.gpib import Gpib
from bliss.comm import serial

from bliss.controllers.temperature.lakeshore.lakeshore import Base


class LakeShore340(object):

    MODE340 = (
        "Off",
        "Manual PID",
        "Zone",
        "Open Loop",
        "Auto Tune PID",
        "Auto Tune PI",
        "Auto Tune P",
    )

    UNITS340 = {"Kelvin": 1, "Celsius": 2, "Sensor unit": 3}
    REVUNITS340 = {1: "Kelvin", 2: "Celsius", 3: "Sensor unit"}

    def __init__(self, comm_type, url, **kwargs):
        self.eos = kwargs.get("eos", "\r\n")
        timeout = kwargs.get("timeout", 0.5)
        if "gpib" in comm_type:
            self._comm = Gpib(
                url, pad=kwargs["extra_param"], eos=self.eos, timeout=timeout
            )
        elif ("serial" or "usb") in comm_type:
            baudrate = kwargs.get("extra_param", 9600)
            self._comm = serial.Serial(
                url,
                baudrate=baudrate,
                bytesize=serial.SEVENBITS,
                parity=serial.PARITY_ODD,
                stopbits=serial.STOPBITS_ONE,
                timeout=timeout,
                eol=self.eos,
            )
        elif "tcp" in comm_type:
            self._comm = Tcp(url, eol=self.eos, timeout=timeout)
        else:
            return RuntimeError("Unknown communication  protocol")
        self._channel = None
        self.log = logging.getLogger(type(self).__name__)
        # self.log.setLevel(logging.NOTSET)
        self.log.setLevel(logging.DEBUG)
        self.log.debug("__init__")

    def _initialize_loop(self, loop):
        self._add_custom_method_loop(loop)

    def _initialize_output(self, output):
        self._add_custom_method_output(output)

    def _initialize_input(self, input):
        self._add_custom_method_input(input)

    def _add_custom_method_loop(self, loop):
        def cset(input=None, units=None, onoff=None):
            """ Read/Set Control Loop Parameters
                Args:
                   input (str): which input to control from. Valid entries: A or B.
                   units (str): sensor unit. Valid entries: Kelvin, Celsius, sensor unit.
                   onoff (str): control loop is on or off. Valid entries are on or off.
              Returns:
                   None if set
                   input (str): which input control the loop.
                   units (str): Unit for the input: Kelvin, Celsius, sensor unit.
                   onoff (str): control loop: on  or off.
            """
            return self._cset(
                loop.config.get("channel"), input=input, units=units, onoff=onoff
            )

        loop.cset = cset

        def cmode(mode=None):
            """ Read/Set Control Loop Mode
                Args:
                   mode (int): control mode. Valid entries: 1=Manual PID,
                               2=Zone, 3=Open Loop, 4=AutoTune PID,
                               5=AutoTune PI, 6=AutoTune P
                Returns:
                   None if set
                   mode (int): mode
            """
            return self._cmode(loop.config.get("channel"), mode=mode)

        loop.cmode = cmode

        def model():
            """ Get the model number
                Returns:
                  model (int): model number
            """
            return self._model()

        loop.model = model

    def _add_custom_method_output(self, output):
        def ramp_status():
            """Check ramp status (if running or not)
               Args:
                  None
                Returns:
                  Ramp status (1 = running, 0 = not running)
            """
            return self._rampstatus(output.config.get("channel"))

        output.ramp_status = ramp_status

        def heater_range(value=None):
            """ Set/Read the heater range (0 to 5) from 0 to 50W in 50Ohms
                Args:
                  value (int): The value of the range if set
                           None if read
                Returns:
                  None if set
                  value (int): The value of the range if read
            """
            return self._heater_range(output.config.get("channel"), value=value)

        output.heater_range = heater_range

        def model():
            """ Get the model number
                Returns:
                  model (int): model number
            """
            return self._model()

        output.model = model

    def _add_custom_method_input(self, input):
        def model():
            """ Get the model number
                Returns:
                  model (int): model number
            """
            return self._model()

        input.model = model

    def clear(self):
        """Clears the bits in the Status Byte, Standard Event and Operation
           Event Registers. Terminates all pending operations.
           Returns:
              None
        """
        # see if this should not be removed
        self.send_cmd("*CLS")

    def _model(self):
        """ Get the model number
            Returns:
              model (int): model number
        """
        model = self.send_cmd("*IDN?").split(",")[1]
        return int(model[5:])

    def read_temperature(self, channel):
        """ Read the current temperature
            Args:
              channel (int): input channel. Valid entries: A or B
            Returns:
              (float): current temperature [K]
        """
        self._channel = channel
        return float(self.send_cmd("KRDG?"))

    def setpoint(self, channel, value=None):
        """ Set/Read the control setpoint
           Args:
              channel (int): output channel. Valid entries: 1 or 2
              value (float): The value of the setpoint if set
                             None if read
           Returns:
              None if set
              value (float): The value of the setpoint if read
        """
        self._channel = channel
        if value is None:
            return float(self.send_cmd("SETP?"))
        # send the setpoint
        self.send_cmd("SETP", value)

    def _heater_range(self, channel, value=None):
        """ Set/Read the heater range (0=off 1=low 2=medium 3=high)
            Args:
              channel (int): output channel. Valid entries: 1 or 2
              value (int): The value of the range if set
                             None if read
           Returns:
              None if set
              value (int): The value of the range if read
        """
        self._channel = channel
        if value is None:
            return int(self.send_cmd("RANGE?"))
        # send the range
        if value not in [0, 1, 2, 3, 4, 5]:
            raise ValueError("Error, the value {0} is not in 0 to 5.".format(value))

        print("--------- value = {0}".format(value))
        self.send_cmd("RANGE", value)

    def ramp_rate(self, channel, value=None):
        """ Set/read the control setpoint ramp rate.
            Explicitly stop the ramping when setting.
            Args:
              channel (int): output channel. Valid entries: 1 or 2
              value (float): The ramp rate [K/min] 0 to 100 with 0.1 resolution 
                             or None when reading.
           Returns:
              None if set
              value (float): The value of the ramp rate if read.
        """
        self._channel = channel
        if value is None:
            rate_value = self.send_cmd("RAMP?").split(",")[1]
            return float(rate_value)

        # send the ramp rate
        self.send_cmd("RAMP", 0, value)

    def ramp(self, channel, sp, rate):
        """Change temperature to a set value at a controlled ramp rate
            Args:
              channel (int): output channel. Valid entries: 1 or 2
              rate (float): ramp rate [K/min], values 0 to 100 with 0.1 resolution 
              sp (float): target setpoint [K]
            Returns:
              None
        """
        self.log.debug("ramp(): SP=%r, RR=%r" % (sp, rate))
        self._channel = channel
        self.setpoint(channel, sp)
        self.send_cmd("RAMP", 1, rate)

    def _rampstatus(self, channel):
        """Check ramp status (if running or not)
            Args:
              channel (int): output channel. Valid entries: 1 or 2
            Returns:
              Ramp status (1 = running, 0 = not running)
        """
        self.log.debug("_rampstatus(): channel = %r" % channel)
        self._channel = channel
        ramp_stat = self.send_cmd("RAMPST?")
        self.log.debug("_rampstatus(): ramp_status = %r" % ramp_stat)
        return int(ramp_stat)

    def pid(self, channel, **kwargs):
        """ Read/Set Control Loop PID Values (P, I, D)
           Args:
              channel (int): loop channel. Valid entries: 1 or 2
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
        self._channel = channel
        kp = kwargs.get("P")
        ki = kwargs.get("I")
        kd = kwargs.get("D")
        if len(kwargs):
            kpc, kic, kdc = self.send_cmd("PID?").split(",")
            if kp is None:
                kp = kpc
            if ki is None:
                ki = kic
            if kd is None:
                kd = kdc
            self.send_cmd("PID", kp, ki, kd)
        else:
            try:
                kp, ki, kd = self.send_cmd("PID?").split(",")
                return float(kp), float(ki), float(kd)
            except (ValueError, AttributeError):
                raise RuntimeError("Invalid answer from the controller")

    def _cmode(self, channel, mode):
        """ Read/Set Control Loop Mode
            Args:
               channel(int): loop channel. Valid entries: 1 or 2
               mode (int): control mode. Valid entries: 1=Manual PID,
                           2=Zone, 3=Open Loop, 4=AutoTune PID,
                           5=AutoTune PI, 6=AutoTune P
          Returns:
               None if set
               mode (int): mode
        """
        self._channel = channel

        if mode is not None:
            if mode not in [1, 2, 3, 4, 5, 6]:
                raise ValueError("Bad value for cmode %r [should be 1->6]" % mode)
            self.send_cmd("CMODE", mode)
        else:
            return self.MODE340[int(self.send_cmd("CMODE?"))]

    def _cset(self, channel, **kwargs):
        """ Read/Set Control Loop Parameters
            Args:
               channel(int): loop channel. Valid entries: 1 or 2
            Kwargs:
               input (str): which input to control from. Valid entries: A or B
               units (int): 1 = Kelvin, 2 = Celsius, 3 = sensor unit
               onoff (bool): switch on (True) or off (False) the control loop
          Returns:
               None if set
               input (str): which input to control from
               units (str): Kelvin, Celsius, sensor unit
               onoff (bool): control loop on/off
        """

        self._channel = channel
        input = kwargs.get("input")
        units = kwargs.get("units")
        onoff = kwargs.get("onoff")

        if input is None and units is None and onoff is None:
            asw = self.send_cmd("CSET?").split(",")
            input = asw[0]
            units = self.REVUNITS340[int(asw[1])]
            onoff = "on" if bool(int(asw[2])) else "off"
            return (input, units, onoff)
        else:
            inputc, unitsc, onoffc, powerup_enable_unused = self.send_cmd(
                "CSET?"
            ).split(",")
            if input is None:
                input = inputc

            if units is None:
                units = unitsc
            elif units != "Kelvin" and units != "Celsius" and units != "Sensor unit":
                return print(
                    "Error: acceptables values for units are "
                    "'Kelvin' or 'Celsius' or 'Sensor unit'."
                )
            else:
                units = self.UNITS340[units]

            if onoff is None:
                onoff = onoffc
            elif onoff != "on" and onoff != "off":
                return print("Error: acceptables values for onoff are 'on' or 'off'.")
            else:
                onoff = 1 if onoff == "on" else 0

            self.send_cmd("CSET", input, units, onoff)

    def send_cmd(self, command, *args):
        """Send a command to the controller
           Args:
              command (str): The command string
              args: Possible variable number of parameters
           Returns:
              None
        """

        print("command = {0}".format(command))

        if command.startswith("*"):
            if "?" in command:
                ans = self._comm.write_readline(command.encode() + self.eos.encode())
                return ans.decode()
            else:
                self._comm.write(command.encode() + self.eos.encode())
        elif "?" in command:
            if isinstance(self._channel, str):
                cmd = command + " %s" % self._channel
            else:
                cmd = command + " %r" % self._channel
            ans = self._comm.write_readline(cmd.encode() + self.eos.encode())
            return ans.decode()
        else:

            if "RANGE" in command:
                value = "".join(str(x) for x in args)
                print("--------- value = {0}".format(value))
                cmd = command + " %s *OPC" % (value) + self.eos
            else:
                inp = ",".join(str(x) for x in args)
                cmd = command + " %d,%s *OPC" % (self._channel, inp) + self.eos

            self._comm.write(cmd.encode())

    def wraw(self, string):
        """Write a string to the controller
           Args:
              string The complete raw string to write (except eos)
                     Normaly will use it to set a/some parameter/s in 
                     the controller.
           Returns:
              None
        """

        print("string = {0}".format(string))
        cmd = string + " *OPC" + self.eos
        self._comm.write(cmd.encode())

    def rraw(self):
        """Read a string from the controller
           Returns:
              response from the controller
        """

        cmd = self.eos
        ans = self._comm.readline(cmd.encode())
        return ans.decode()

    def wrraw(self, string):
        """Write a string to the controller and then reading answer back
           Args:
              string The complete raw string to write (except eos)
           Returns:
              response from the controller
        """

        print("string = {0}".format(string))
        cmd = string + self.eos
        ans = self._comm.write_readline(cmd.encode())
        return ans.decode()


class lakeshore340(Base):
    def __init__(self, config, *args):
        comm_type = None
        extra_param = None
        if "gpib" in config:
            comm_type = "gpib"
            url = config["gpib"]["url"]
            extra_param = config["gpib"]["pad"]
            eos = config.get("gpib").get("eos", "\r\n")
        elif "serial" in config:
            comm_type = "serial"
            url = config["serial"]["url"]
            extra_param = config.get("serial").get("baudrate")
            eos = config.get("serial").get("eos", "\r\n")
        elif "tcp" in config:
            comm_type = "tcp"
            url = config["tcp"]["url"]
            eos = config.get("tcp").get("eos", "\r\n")
        else:
            raise ValueError("Must specify gpib or serial url")

        _lakeshore = LakeShore340(comm_type, url, extra_param=extra_param, eos=eos)

        model = _lakeshore._model()

        if model != 340:
            raise ValueError(
                "Error, the Lakeshore model is {0}. It should be 340.".format(model)
            )
        # else:
        #     print("\t\t\tthe model is {0}".format(model))

        Base.__init__(self, _lakeshore, config, *args)
