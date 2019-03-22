# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Lakeshore 340, acessible via GPIB, Serial line or Ethernet

yml configuration example:
#controller:
- class: lakeshore340
  module: lakeshore.lakeshore340
  #eos: '\r\n'
  name: lakeshore340
  timeout: 3
#gpib
  gpib:
     url: enet://gpibid10f.esrf.fr
     pad: 9 
#serial line
  serial:
     url: "rfc2217://lidxxx:28003"
     baudrate: 19200    # = max
#ethernet
  tcp:
     url: idxxlakeshore:7777
  inputs:
    - name: ls340_A
      channel: A 
      # next type is default
      #type: temperature_K
      #tango_server: ls_340
    - name: ls340_A_c    # input temperature in Celsius
      channel: A
      type: temperature_C
    - name: ls340_A_su  # in sensor units (Ohm or Volt)
      channel: A
      type: sensorunit

    - name: ls340_B
      channel: B 
      # next type is default
      #type: temperature_K
      #tango_server: ls_340
    - name: ls340_B_c    # input temperature in Celsius
      channel: B
      type: temperature_C
    - name: ls340_B_su  # in sensor units (Ohm or Volt)
      channel: B
      type: sensorunit

  outputs:
    - name: ls340o_1
      channel: 1 
      units: K  #K(elvin) C(elsius) S(ensor)
    - name: ls340o_2
      channel: 2 
      units: K  #K(elvin) C(elsius) S(ensor)

  ctrl_loops:
    - name: ls340l_1
      input: $ls340_A
      output: $ls340o_1
      channel: 1
    - name: ls340l_2
      input: $ls340_B
      output: $ls340o_2
      channel: 2
"""


import time
import os
import re


# Logging messages
# from bliss.common import log
import logging

# logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s')
logging.basicConfig(format="%(levelname)s - %(message)s")


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
    CURVEFORMAT340 = {
        1: "mV/K",
        2: "V/K",
        3: "Ohms/K",
        4: "logOhms/K",
        5: "logOhms/logK",
    }
    CURVETEMPCOEF340 = {1: "negative", 2: "positive"}
    IPSENSORUNITS340 = {1: "volts", 2: "ohms"}
    HTRSTATUS340 = {
        0: "OK",
        1: "Power Supply Over Voltage",
        2: "Power Supply Under Voltage",
        3: "Ouput DAC error",
        4: "Current limit DAC error",
        5: "Open heater load",
        6: "Heater load less than 10 ohms",
    }

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
        # Set initial log level to logging.WARNING = 30
        # to get only Warning, Error and Critical messages logged
        self.log.setLevel(logging.WARNING)

        self.log.info("__init__")

    # Initialization methods
    # ----------------------

    # - Controller
    #   ----------
    def clear(self):
        """Clears the bits in the Status Byte, Standard Event and Operation
           Event Registers. Terminates all pending operations.
           Returns:
              None
        """
        self.send_cmd("*CLS")

    # - Input object
    #   ------------
    def _initialize_input(self, input):
        self.log.info("_initialize_input")
        self._add_custom_method_input(input)

    # - Output object
    #   -------------
    def _initialize_output(self, output):
        self.log.info("_initialize_output")
        self._add_custom_method_output(output)

    # - Loop object
    #   -----------
    def _initialize_loop(self, loop):
        self.log.info("_initialize_loop")
        self._add_custom_method_loop(loop)

    # Standard INPUT-object related method(s)
    # ---------------------------------------
    def read_temperature(self, channel, scale):
        """ Read the current temperature
            Args:
              channel (int): input channel. Valid entries: A or B
              scale (str): temperature unit for reading: kelvin or celsius
            Returns:
              (float): current temperature [K] or [C]
        """
        self.log.info("read_temperature")
        self._channel = channel

        # Query Input Status before reading temperature
        # If status is OK, then read the temperature
        asw = int(self.send_cmd("RDGST?"))
        if asw == 0:
            if scale == "kelvin":
                return float(self.send_cmd("KRDG?"))
            elif scale == "celsius":
                return float(self.send_cmd("CRDG?"))
        if asw & 16:
            self.log.warning("Temperature UnderRange on input %s" % channel)
            raise ValueError("Temperature value on input %s is invalid" % channel)
        if asw & 32:
            self.log.warning("Temperature OverRange on input %s" % channel)
            raise ValueError("Temperature value on input %s is invalid" % channel)

    def read_insensorunits(self, channel):
        """ Read the current value in sensor units (Ohm or Volt)
            Args:
              channel (int): input channel. Valid entries: A or B
            Returns:
              (float): current value in sensor units (Ohm or Volt)
        """
        self.log.info("read_insensorunits")
        self._channel = channel
        return float(self.send_cmd("SRDG?"))

    # Adding CUSTOM INPUT-object related method(s)
    # --------------------------------------------
    def _add_custom_method_input(self, input):
        self.log.info("_add_custom_method_input")

        def curve_used_curve():
            """ Get the input curve used
                Prints:
                   curve number (int): 0=none, 1->20 standard, 21->60 user defined curves
                   curve name (str): limited to 15 characters
                   curve SN (str): limited to 10 characters (Standard,...)
                   curve format (int): 1=mV/K, 2=V/K, 3=Ohms/K, 4=logOhms/K, 5=logOhms/logK
                   curve temperature limit (float): in Kelvin
                   curve temperature coefficient (int): 1=negative, 2=positive
            """
            self.log.info("curve_used_curve")
            return self._curve_used_curve(input.config.get("channel"))

        input.curve_used_curve = curve_used_curve

        def curve_to_use(crvn=None):
            """ Select the curve to be used on in input
                Args:
                  crvn (int): Curve number: 0=none, 1->20 standard, 
                                            21->60 user defined curves
            """
            self.log.info("curve_to_use")
            self._curve_to_use(input.config.get("channel"))

        input.curve_to_use = curve_to_use

        def curve_list_all():
            """ List all the curves
                Returns:
                  a row for all the curves from 1 to 60
            """
            self.log.info("curve_list_all")
            return self._curve_list_all()

        input.curve_list_all = curve_list_all

        def curve_write(crvn=None, crvfile=None):
            """ Write the user curve into the Lakeshore
                Args:
                  crvn (int): The user curve number from 21 to 60
                  crvfile (str): full file name
                Returns:
                  Status of curve written
            """
            self.log.info("curve_write")
            return self._curve_write(crvn, crvfile)

        input.curve_write = curve_write

        def curve_delete(crvn=None):
            """ Delete a user curve from the Lakeshore
                Args:
                  crvn (int): The user curve number from 21 to 60
                Returns:
                  None.
            """
            self.log.info("curve_delete")
            self._curve_delete(crvn)

        input.curve_delete = curve_delete

        def filter(onoff=None, points=None, window=None):
            """ Configure input filter parameters
                Args:
                  onoff (int): 1 = enable, 0 = disable
                  points (int): specifies how many points the filtering 
                                function uses. Valid range: 2 to 64
                  window (int): specifies what percent of full scale 
                                reading limits the filtering function. 
                                Reading changes greater than this percentage
                                reset the filter. Valid range: 1 to 10%.
                Returns:
                  None
            """
            self.log.info("filter")
            return self._filter(
                input.config.get("channel"), onoff=onoff, points=points, window=window
            )

        input.filter = filter

        # Next 3 (show, model, loglevel) are also in custom methods
        # for output and loop objects
        def model():
            """ Get the model number
                Returns:
                  model (int): model number
            """
            self.log.info("model")
            return self._model()

        input.model = model

        def show():
            """ Display all main parameters and values for the 
                temperature controller
                Prints:
                  model, PID, heater range, loop status, 
                  sensors configuration, inputs temperature
            """
            self.log.info("show")
            return self._show()

        input.show = show

        def loglevel(value=None):
            """ Set/Read the log level ("NOTSET","DEBUG","INFO","WARNING",
                                        "WARN","ERROR","CRITICAL","FATAL")
                Args:
                  value (str): The value of the log-level if set
                               None if read
                Returns:
                  None if set
                  value (str): The value of the log-level if read
            """
            self.log.info("loglevel")
            return self._log_level(value=value)

        input.loglevel = loglevel

    # Standard OUTPUT-object related method(s)
    # ----------------------------------------
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
        self.log.info("setpoint")
        self._channel = channel
        if value is None:
            return float(self.send_cmd("SETP?"))
        # send the setpoint
        self.send_cmd("SETP", value)

    def ramp_rate(self, channel, value=None):
        """ Set/read the control setpoint ramp rate.
            Explicitly stop the ramping when setting.
            Args:
              channel (int): output channel. Valid entries: 1 or 2
              value (float): The ramp rate [K/min] 0 to 100 with 0.1 resolution 
                             None if read
            Returns:
              None if set
              value (float): The value of the ramp rate if read.
        """
        self.log.info("ramp_rate")
        self._channel = channel
        if value is None:
            rate_value = self.send_cmd("RAMP?").split(",")[1]
            return float(rate_value)

        # send the ramp rate
        self.send_cmd("RAMP", 0, value)

    def ramp(self, channel, sp, rate):
        """ Change temperature to a set value at a controlled ramp rate
            Args:
              channel (int): output channel. Valid entries: 1 or 2
              rate (float): ramp rate [K/min], values 0 to 100 with 0.1 resolution 
              sp (float): target setpoint [K]
            Returns:
              None
        """
        self.log.info("ramp")
        self.log.debug("ramp(): SP=%r, RR=%r" % (sp, rate))
        self._channel = channel
        self.setpoint(channel, sp)
        self.send_cmd("RAMP", 1, rate)

    # Adding CUSTOM OUTPUT-object related method(s)
    # ---------------------------------------------
    def _add_custom_method_output(self, output):
        self.log.info("_add_custom_method_output")

        def ramp_status():
            """ Check ramp status (if running or not)
                Args:
                  None
                Returns:
                  Ramp status (1 = running, 0 = not running)
            """
            self.log.info("ramp_status")
            return self._rampstatus(output.config.get("channel"))

        output.ramp_status = ramp_status

        def heater_range(value=None):
            """ Set/Read the heater range (0 to 5) [see Table 6-2 in manual] 
                Args:
                  value (int): The value of the range if set
                               None if read
                Returns:
                  None if set
                  value (int): The value of the range if read
            """
            self.log.info("heater_range")
            return self._heater_range(value=value)

        output.heater_range = heater_range

        # Next 3 (show, model, loglevel) are also in custom methods
        # for input and loop objects
        def model():
            """ Get the model number
                Returns:
                  model (int): model number
            """
            self.log.info("model")
            return self._model()

        output.model = model

        def show():
            """ Display all main parameters and values for the temperature controller
                Prints:
                  model, PID, heater range, loop status, sensors configuration, inputs temperature
            """
            self.log.info("show")
            return self._show()

        output.show = show

        def loglevel(value=None):
            """ Set/Read the log level ("NOTSET","DEBUG","INFO","WARNING",
                                        "WARN","ERROR","CRITICAL","FATAL")
                Args:
                  value (str): The value of the log-level if set
                               None if read
                Returns:
                  None if set
                  value (str): The value of the log-level if read
            """
            self.log.info("loglevel")
            return self._log_level(value=value)

        output.loglevel = loglevel

    # Standard LOOP-object related method(s)
    # --------------------------------------
    def pid(self, channel, **kwargs):
        """ Read/Set Control Loop PID Values (P, I, D)
            Args:
              channel (int): loop channel. Valid entries: 1 or 2
              P (float): Proportional gain (0.1 to 1000), None if read
              I (float): Integral reset (0.1 to 1000) [value/s], None if read
              D (float): Derivative rate (0 to 200) [%], None if read
            Returns:
              None if set
              p (float): P
              i (float): I
              d (float): D
        """
        self.log.info("pid")
        self._channel = channel
        print(self._channel)
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
            kp, ki, kd = self.send_cmd("PID?").split(",")
            return float(kp), float(ki), float(kd)

    # Adding CUSTOM LOOP-object related method(s)
    # ---------------------------------------------
    def _add_custom_method_loop(self, loop):
        self.log.info("_add_custom_method_loop")

        def cmode(mode=None):
            """ Read/Set Control Loop Mode
                Args:
                  mode (int): control mode. Valid entries: 1=Manual PID,
                              2=Zone, 3=Open Loop, 4=AutoTune PID,
                              5=AutoTune PI, 6=AutoTune P
                              None if read
                Returns:
                  None if set
                  mode (int): mode
            """
            self.log.info("cmode")
            return self._cmode(loop.config.get("channel"), mode=mode)

        loop.cmode = cmode

        def cset(input=None, units=None, onoff=None):
            """ Read/Set Control Loop Parameters
                Args:
                  input (str): which input to control from. 
                               Valid entries: A or B.
                  units (str): sensor unit. Valid entries: Kelvin, 
                               Celsius, sensor unit.
                  onoff (str): control loop is on or off. Valid entries 
                               are on or off.
                Returns:
                  None if set
                  input (str): which input control the loop.
                  units (str): Unit for the input: Kelvin, Celsius, 
                               sensor unit.
                  onoff (str): control loop: on  or off.
            """
            self.log.info("cset")
            return self._cset(
                loop.config.get("channel"), input=input, units=units, onoff=onoff
            )

        loop.cset = cset

        # Next 3 (show, model, loglevel) are also in custom methods
        # for input and output objects
        def model():
            """ Get the model number
                Returns:
                  model (int): model number
            """
            self.log.info("model")
            return self._model()

        loop.model = model

        def show():
            """ Display all main parameters and values for the temperature controller
                Prints:
                  model, PID, heater range, loop status, sensors configuration, inputs temperature
            """
            self.log.info("show")
            return self._show()

        loop.show = show

        def loglevel(value=None):
            """ Set/Read the log level ("NOTSET","DEBUG","INFO","WARNING",
                                        "WARN","ERROR","CRITICAL","FATAL")
                Args:
                  value (str): The value of the log-level if set
                               None if read
                Returns:
                  None if set
                  value (str): The value of the log-level if read
            """
            self.log.info("loglevel")
            return self._log_level(value=value)

        loop.loglevel = loglevel

    # General CUSTOM methods [valid for any type of object:
    # input, output, loop]
    # -----------------------------------------------------
    def _model(self):
        """ Get the model number
            Returns:
              model (int): model number
        """
        self.log.info("_model")
        model = self.send_cmd("*IDN?").split(",")[1]
        return int(model[5:])

    def _show(self):
        """ Display all main parameters and values for the temperature controller
            Prints:
              device ID, PID, heater range, loop status, sensors configuration, inputs temperature etc.
        """

        self.log.info("_show")
        self.log.debug("channel = %r" % self._channel)
        # Get full identification string
        full_id = self.send_cmd("*IDN?")
        print("\nLakeshore identification %s" % (full_id))

        # Sensor A
        # --------
        print("\nSensor A:")
        print("=========")

        # Specify channel to be used in send_cmd for the commands
        # needing it: INCRV?, INTYPE?, RDGST?, KRDG?, CRDG?, SRDG?
        self._channel = "A"
        # Get temperature calibration curve for input A
        asw = self.send_cmd("INCRV?")
        print("Uses calibration curve number %d" % int(asw))
        asw = self.send_cmd("CRVHDR? %s" % asw)
        asw = asw.split(",")
        print(
            "Curve type = %s, SerNum = %s, Format = %s"
            % (asw[0].strip(), asw[1].strip(), self.CURVEFORMAT340[int(asw[2])])
        )
        print(
            "Temp.limit = %s K , Temp.coeff. = %s"
            % (asw[3], self.CURVETEMPCOEF340[int(asw[4])])
        )

        # Get input sensor units (Volt or Ohm) for input A
        asw = self.send_cmd("INTYPE?")
        asw = asw.split(",")
        ipsu = asw[1]
        print("Input A sensor units = %s" % self.IPSENSORUNITS340[int(ipsu)])

        # Query Input Status before reading temperature
        # If status is OK, then read the temperature in
        # Kelvin, Celsius and sensor units (volt or ohm).
        asw = int(self.send_cmd("RDGST?"))
        if asw == 0:
            # Read input A temperature now since input status OK
            tempK_A = float(self.send_cmd("KRDG?"))  # in Kelvin
            tempC_A = float(self.send_cmd("CRDG?"))  # in Celsius
            resorvol_A = float(self.send_cmd("SRDG?"))  # in sensor units
            print("Temperature on input A = %.3f K (%.3f C)" % (tempK_A, tempC_A))
            if int(ipsu) == 1:
                print("Input A reading in Sensor Units = %.3f Volts" % resorvol_A)
            else:
                print("Input A reading in Sensor Units = %.3f Ohms" % resorvol_A)
        if asw & 16:
            self.log.warning("Temperature UnderRange on input %s" % channel)
            raise ValueError("Temperature value on input %s is invalid" % channel)
        if asw & 32:
            self.log.warning("Temperature OverRange on input %s" % channel)
            raise ValueError("Temperature value on input %s is invalid" % channel)
        if asw & 64:
            self.log.warning("0 value in sensor units on input %s" % channel)
            raise ValueError("Value in sensor units on input %s is invalid" % channel)
        if asw & 128:
            self.log.warning("Overrange of value in sensor units on input %s" % channel)
            raise ValueError("Value in sensor units on input %s is invalid" % channel)

        # Sensor B
        # --------
        print("\nSensor B:")
        print("=========")

        # Specify channel to be used in send_cmd for the commands
        # needing it: INCRV?, INTYPE?, KRDG?, CRDG?, SRDG?
        self._channel = "B"

        # Get temperature calibration curve for input B
        asw = self.send_cmd("INCRV?")
        print("Uses calibration curve number %d" % int(asw))
        asw = self.send_cmd("CRVHDR? %s" % asw)
        asw = asw.split(",")
        print(
            "Curve type = %s, SerNum = %s, Format = %s"
            % (asw[0].strip(), asw[1].strip(), self.CURVEFORMAT340[int(asw[2])])
        )
        print(
            "Temp.limit = %s K, Temp.coeff. = %s"
            % (asw[3], self.CURVETEMPCOEF340[int(asw[4])])
        )

        # Get input sensor units (Volt or Ohm) for input B
        asw = self.send_cmd("INTYPE?")
        asw = asw.split(",")
        ipsu = asw[1]
        print("Input B sensor units = %s" % self.IPSENSORUNITS340[int(ipsu)])

        # Query Input Status before reading temperature
        # If status is OK, then read the temperature in
        # Kelvin, Celsius and sensor units (volt or ohm).
        asw = int(self.send_cmd("RDGST?"))
        if asw == 0:
            # Read input B temperature now since input status OK
            tempK_B = float(self.send_cmd("KRDG?"))  # in Kelvin
            tempC_B = float(self.send_cmd("CRDG?"))  # in Celsius
            resorvol_B = float(self.send_cmd("SRDG?"))  # in sensor units
            print("Temperature on input B = %.3f K (%.3f C)" % (tempK_B, tempC_B))
            if int(ipsu) == 1:
                print("Input B reading in Sensor Units = %.3f Volts" % resorvol_B)
            else:
                print("Input B reading in Sensor Units = %.3f Ohms" % resorvol_B)
        if asw & 16:
            self.log.warning("Temperature UnderRange on input %s" % channel)
            raise ValueError("Temperature value on input %s is invalid" % channel)
        if asw & 32:
            self.log.warning("Temperature OverRange on input %s" % channel)
            raise ValueError("Temperature value on input %s is invalid" % channel)
        if asw & 64:
            self.log.warning("0 value in sensor units on input %s" % channel)
            raise ValueError("Value in sensor units on input %s is invalid" % channel)
        if asw & 128:
            self.log.warning("Overrange of value in sensor units on input %s" % channel)
            raise ValueError("Value in sensor units on input %s is invalid" % channel)

        # Loop 1
        # ------
        print("\nLoop 1:")
        print("=======")

        # Specify channel to be used in send_cmd for the commands
        # needing it: CSET?, RAMP?, SETP?, RAMPST?, CMODE, PID?
        self._channel = "1"

        # Get control loop parameters
        asw = self.send_cmd("CSET?").split(",")
        sensor = asw[0]
        units = self.REVUNITS340[int(asw[1])]
        onoff = "ON" if bool(int(asw[2])) else "OFF"
        print("Controlled by sensor %s in %s and is %s." % (sensor, units, onoff))

        # Read ramp enable/disable status and ramp rate
        rp_1 = self.send_cmd("RAMP?").split(",")
        ronoff_1 = "ON" if int(rp_1[0]) == 1 else "OFF"
        rrate_1 = float(rp_1[1])

        # Read setpoint
        sp_1 = float(self.send_cmd("SETP?"))

        print(
            "Ramp enable is %s with set-point %.3f %s and ramp-rate = %.3f K/min."
            % (ronoff_1, sp_1, units, rrate_1)
        )
        # Read ramp status (only if ramp is enabled)
        if ronoff_1 == "ON":
            asw = self.send_cmd("RAMPST?")
            rs_1 = "RAMPING" if int(asw) == 1 else "NOT RAMPING"
            print("Ramp status is %s." % rs_1)

        # Get control loop mode
        asw = self.send_cmd("CMODE?")
        print("Temp Control is set to %s" % self.MODE340[int(asw)])

        kp, ki, kd = self.send_cmd("PID?").split(",")
        print("PID parameters: ")
        print("     P = %.1f" % float(kp))
        print("     I = %.1f" % float(ki))
        print("     D = %.1f" % float(kd))

        # Loop 2
        # ------
        print("\nLoop 2:")
        print("=======")

        # Specify channel to be used in send_cmd for the commands
        # needing it: CSET?, RAMP?, SETP?, RAMPST?, CMODE, PID?
        self._channel = "2"

        # Get control loop parameters
        asw = self.send_cmd("CSET?").split(",")
        sensor = asw[0]
        units = self.REVUNITS340[int(asw[1])]
        onoff = "ON" if bool(int(asw[2])) else "OFF"
        print("Controlled by sensor %s in %s and is %s." % (sensor, units, onoff))

        # Read ramp enable/disable status and ramp rate
        rp_2 = self.send_cmd("RAMP?").split(",")
        ronoff_2 = "ON" if int(rp_2[0]) == 1 else "OFF"
        rrate_2 = float(rp_2[1])

        # Read setpoint
        sp_2 = float(self.send_cmd("SETP?"))

        print(
            "Ramp enable is %s with set-point %.3f %s and ramp-rate = %.3f K/min. "
            % (ronoff_2, sp_2, units, rrate_2)
        )
        # Read ramp status (only if ramp is enabled)
        if ronoff_2 == "ON":
            asw = self.send_cmd("RAMPST?")
            rs_2 = "RAMPING" if int(asw) == 1 else "NOT RAMPING"
            print("Ramp status is %s." % rs_2)

        # Get control loop mode
        asw = self.send_cmd("CMODE?")
        print("Temp Control is set to %s" % self.MODE340[int(asw)])

        # Get PID parameters for loop 2
        kp, ki, kd = self.send_cmd("PID?").split(",")
        print("PID parameters: ")
        print("     P = %.1f" % float(kp))
        print("     I = %.1f" % float(ki))
        print("     D = %.1f" % float(kd))

        # Heater
        # ------
        print("\nHeater:")
        print("=======")
        # Get heater range value
        htr_range = int(self.send_cmd("RANGE?"))
        if htr_range == 0:
            print("Heater is OFF")
        else:
            print("Heater is on range = %d" % htr_range)

        # Get heater power
        htr_power = float(self.send_cmd("HTR?"))
        print("Heater power = %.1f %%" % htr_power)

        # Get heater status
        htr_status = int(self.send_cmd("HTRST?"))
        print("Heater status = %s" % self.HTRSTATUS340[int(htr_status)])

    def _log_level(self, value=None):

        """ Set/Read the log level ("NOTSET","DEBUG","INFO","WARNING",
                                    "WARN","ERROR","CRITICAL","FATAL")
            Args:
              value (str): The value of the log-level if set
                           None if read
            Returns:
              None if set
              value (str): The value of the log-level if read
        """

        self.log.info("_low_level")
        # Get the log-level
        if value is None:
            level_as_num = self.log.level
            return logging._levelToName[level_as_num]

        # Set the log-level
        value = value.upper()
        if value not in [
            "NOTSET",
            "DEBUG",
            "INFO",
            "WARNING",
            "WARN",
            "ERROR",
            "CRITICAL",
            "FATAL",
        ]:
            raise ValueError("Log-Level %s is invalid" % value)
        self.log.setLevel(logging._nameToLevel[value])

    # CUSTOM INPUT-object related method(s)
    # -------------------------------------
    def _curve_used_curve(self, channel):
        """ Get the input curve used
            Args:
              channel (str): input channel. Valied entries: A or B
            Prints:
              curve number (int): 0=none, 1->20 standard, 21->60 user defined curves
              curve name (str): limited to 15 characters
              curve SN (str): limited to 10 characters (Standard,...)
              curve format (int): 1=mV/K, 2=V/K, 3=Ohms/K, 4=logOhms/K, 5=logOhms/logK
              curve temperature limit (float): in Kelvin
              curve temperature coefficient (int): 1=negative, 2=positive
        """
        self.log.info("_curve_used_curve")
        self._channel = channel
        curve_number = self.send_cmd("INCRV?")
        command = "CRVHDR? %s" % curve_number
        curve_header = self.send_cmd(command)
        header = curve_header.split(",")
        curve_name = header[0]
        curve_sn = header[1]
        curve_format = self.CURVEFORMAT340[int(header[2])]
        curve_temperature_limit = header[3]
        curve_temperature_coefficient = self.CURVETEMPCOEF340[int(header[4])]

        print("Used curve number is %d" % int(curve_number))
        print(
            "curve name: %s\tcurve SN: %s\t format: %s\n\
temperature limit: %sK\t\ttemp. coefficient: %s"
            % (
                curve_name,
                curve_sn,
                curve_format,
                curve_temperature_limit,
                curve_temperature_coefficient,
            )
        )

    def _curve_to_use(self, channel, crvn):
        """ Set the curve to be used on a given input
            Args:
              channel (str): input channel. Valid entries: A or B
              crvn (int): curve number: 0=none, 1->20 standard, 
                                        21->60 user defined
	    Returns: 
	      None
        """
        self.log.info("_curve_to_use")
        self._channel = channel
        if crvn == None:
            crvn = 30
        if crvn < 0 or crvn > 60:
            raise ValueError("Curve number %d invalid, should be [0,60]" % crvn)
        command = "INCRV %d" % int(crvn)
        self.send_cmd(command)

    def _curve_list_all(self):
        """ Get the input curve used
            Prints:
              curve number (int): 0=none, 1->20 standard, 21->60 user defined curves
              curve name (str): limited to 15 characters
              curve SN (str): limited to 10 characters (Standard,...)
              curve format (int): 1=mV/K, 2=V/K, 3=Ohms/K, 4=logOhms/K, 5=logOhms/logK
              curve temperature limit (float): in Kelvin
              curve temperature coefficient (int): 1=negative, 2=positive
        """
        self.log.info("_curve_list_all")
        # curve_number = self.send_cmd("INCRV?")
        print(" #            Name       SN         Format     Limit(K) Temp. coef.")
        for i in range(1, 61):
            command = "CRVHDR? %s" % i
            curve_header = self.send_cmd(command)
            header = curve_header.split(",")
            curve_name = header[0].strip()
            curve_sn = header[1]
            curve_format = self.CURVEFORMAT340[int(header[2])]
            curve_temperature_limit = header[3]
            curve_temperature_coefficient = self.CURVETEMPCOEF340[int(header[4])]
            print(
                "%2d %15s %10s %12s %12s %s"
                % (
                    i,
                    curve_name,
                    curve_sn,
                    curve_format,
                    curve_temperature_limit,
                    curve_temperature_coefficient,
                )
            )

    def _curve_write(self, crvn, crvfile):
        """ Write the user curve to the Lakeshore
            Args:
              crvn (int): The user curve number from 21 to 60
              crvfile (str): full file name
            Returns:
              Status of curve written
        """
        self.log.info("_curve_write")
        if crvn is None:
            crvn = input("Number of curve to be written [21,60]? ")
        else:
            print("Curve number passed as arg = %d" % crvn)

        if crvn not in range(21, 61):
            raise ValueError("User curve number %d is not in [21,60]" % crvn)

        print("Readings from actual curve %d in LakeShore 340 :" % crvn)
        command = "CRVHDR? %d" % crvn
        loaded_curve = self.send_cmd(command)
        header = loaded_curve.split(",")
        curve_name = header[0].strip()
        curve_sn = header[1]
        curve_format = self.CURVEFORMAT340[int(header[2])]
        curve_temp_limit = header[3]
        curve_temp_coeff = self.CURVETEMPCOEF340[int(header[4])]
        print("no channel")
        print(
            "\t%15s %10s %12s %12s %s"
            % (curve_name, curve_sn, curve_format, curve_temp_limit, curve_temp_coeff)
        )
        print("no channel")
        if crvfile is None:
            crvfile = input("Filename of temperature curve? ")
        else:
            self.log.debug("File name passed as arg = %s" % crvfile)

        if os.path.isfile(crvfile) == False:
            raise FileNotFoundError("Curve file %s not found" % crvfile)

        with open(crvfile) as f:

            for line in f:
                # print(line)
                if line.count(":") == 1:
                    lline = line.split(":")
                    # print(lline[0] + lline[1])
                    if lline[0] == "Sensor Model":
                        curve_name = lline[1].strip()
                    if lline[0] == "Serial Number":
                        curve_sn = lline[1].strip()
                    if lline[0] == "Data Format":
                        curve_format_long = lline[1]
                        # cvf = curve_format_long.split(None,1)
                        # curve_format = cvf[0]
                        curve_format = curve_format_long.split(None, 1)[0]

                    if lline[0] == "SetPoint Limit":
                        curve_temp_limit_long = lline[1]
                        curve_temp_limit = curve_temp_limit_long.split(None, 1)[0]

                    if lline[0] == "Temperature coefficient":
                        curve_temp_coeff_long = lline[1]
                        curve_temp_coeff = curve_temp_coeff_long.split(None, 1)[0]

                    if lline[0] == "Number of Breakpoints":
                        curve_nb_breakpts = lline[1].strip()

            # checking header values
            if curve_name == "":
                raise ValueError("No sensor model")
            if curve_sn == "":
                raise ValueError("No serial number")
            if curve_format_long == "":
                raise ValueError("No data format")
            elif int(curve_format) not in range(1, 6):
                raise ValueError("Curve data format %s not in [1,5]" % curve_format)
            if curve_temp_limit_long == "":
                raise ValueError("No setpoint limit")
            if curve_temp_coeff_long == "":
                raise ValueError("No temperature coefficient")
            elif int(curve_temp_coeff) not in range(1, 3):
                raise ValueError(
                    "Curve temperature coefficient %s not in [1,2]" % curve_temp_coeff
                )
            if curve_nb_breakpts == "":
                raise ValueError("No number of breakpoints")
            elif int(curve_nb_breakpts) not in range(1, 201):
                raise ValueError(
                    "Number of breakpoints %s not in [1,200]" % curve_nb_breakpts
                )

        print("fichier ouvert et lu\n")

        print(curve_name)
        print(curve_sn)
        print(curve_format)
        print(curve_temp_limit)
        print(curve_temp_coeff)
        print(curve_nb_breakpts)

        # writing the curve header into the Lakeshore
        command = "CRVHDR %d,%s,%s,%d,%f,%d" % (
            crvn,
            curve_name,
            curve_sn,
            int(curve_format),
            float(curve_temp_limit),
            int(curve_temp_coeff),
        )
        # print(command)
        self.send_cmd(command)

        with open(crvfile) as f:
            for line in f:
                exp = re.compile(
                    r"^\s*([0-9]+)\s+([0-9]+\.[0-9]+)\s+([0-9]+\.[0-9]+)\s*$"
                )
                if exp.match(line):
                    command = "CRVPT %d,%d,%f,%f" % (
                        crvn,
                        int(exp.match(line).group(1)),
                        float(exp.match(line).group(2)),
                        float(exp.match(line).group(3)),
                    )
                    print(command)
                    self.send_cmd(command)

        print(
            "Curve %d has been written into the LakeShore model 340 temperature controller."
            % crvn
        )

        # Reading back for checking the header
        command = "CRVHDR? %d" % crvn
        curve_header = self.send_cmd(command)
        print("The header read back for the %d is:" % crvn)
        print(curve_header)

        print(
            "Warning: The curve was not saved to the flash memory of the LakeShore 340."
        )
        asw = input("Do you want to save it into the curve flash memory ?")
        if asw.lower() == "yes" or asw.lower() == "y":
            print("This operation may take several seconds.")
            self.send_cmd("CRVSAV")
            print("The curve has been written into the flash memory.")

    def _curve_delete(self, crvn):
        """ Delete a user curve from the Lakeshore
            Args:
              crvn (int): The user curve number from 21 to 60
            Returns:
              None.
        """
        self.log.info("_curve_delete")
        if crvn is None:
            crvn = input("Number of curve to be deleted [21,60]? ")
        else:
            self.log.debug("Curve number passed as arg = %d" % crvn)

        if crvn not in range(21, 61):
            raise ValueError("User curve number %d is not in [21,60]" % crvn)

        # Delete the curve
        command = "CRVDEL %d" % crvn
        self.send_cmd(command)

        print(
            "Warning: The curve was not deleted yet from the flash memory of the LakeShore 340."
        )
        asw = input("Do you want to delete the curve from the flash memory ?")
        if asw.lower() == "yes" or asw.lower() == "y":
            print("This operation may take several seconds.")
            self.send_cmd("CRVSAV")
            print("The curve has been deleted from the flash memory.")

    def _filter(self, channel, **kwargs):
        """ Configure input filter parameters
            Args:
              channel (str): input channel. Valied entries: A or B
              onoff (int): 1 = enable, 0 = disable
              points (int): specifies how many points the filtering function
                            uses. Valid range: 2 to 64.
              window (int): specifies what percent of full scale reading
                            limits the filtering function. Reading changes
                            greater than this percentage reset the filter.
                            Valid range: 1 to 10%.
            Returns:
              None
        """
        self.log.info("_filter")
        self._channel = channel
        input = channel
        onoff = kwargs.get("onoff")
        points = kwargs.get("points")
        window = kwargs.get("window")

        if onoff is None and points is None and window is None:
            asw = self.send_cmd("FILTER?").split(",")
            onoff = int(asw[0])
            points = int(asw[1])
            window = int(asw[2])
            return (onoff, points, window)
        else:
            onoffc, pointsc, windowc = self.send_cmd("FILTER?").split(",")
            if onoff is None:
                onoff = onoffc
            if points is None:
                points = pointsc
            elif points not in range(2, 65):
                raise ValueError(
                    "Error, the nb of points {0} is not in range 2 to 64.".format(
                        points
                    )
                )
            if window is None:
                window = windowc
            elif window not in range(1, 11):
                raise ValueError(
                    "Error, the filter windows {0} is not in range 1 to 10 percent.".format(
                        window
                    )
                )
            self.send_cmd("FILTER", onoff, points, window)

    # CUSTOM OUTPUT-object related method(s)
    # --------------------------------------
    def _rampstatus(self, channel):
        """ Check ramp status (if running or not)
            Args:
              channel (int): output channel. Valid entries: 1 or 2
            Returns:
              Ramp status (1 = running, 0 = not running)
        """
        # TODO: in case rampstatus found is 0 (= no ramping active)
        #       could add sending command *STB? and checking bit 7,
        #       which indicates (when set to 1) that ramp is done.
        self.log.info("_rampstatus")
        self.log.debug("_rampstatus(): channel = %r" % channel)
        self._channel = channel
        ramp_stat = self.send_cmd("RAMPST?")
        self.log.debug("_rampstatus(): ramp_status = %r" % ramp_stat)
        return int(ramp_stat)

    def _heater_range(self, value=None):
        """ Set/Read the heater range (0 to 5) [see Table 6-2 in manual] 
            Args:
              value (int): The value of the range if set
              None if read
            Returns:
              None if set
              value (int): The value of the range if read
        """
        self.log.info("_heater_range")
        if value is None:
            return int(self.send_cmd("RANGE?"))
        # send the range
        if value not in [0, 1, 2, 3, 4, 5]:
            raise ValueError("Error, the value {0} is not in 0 to 5.".format(value))

        print("--------- value = {0}".format(value))
        self.send_cmd("RANGE", value)

    # CUSTOM LOOP-object related method(s)
    # ------------------------------------
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
        self.log.info("_cmode")
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
               units (str): set-point unit: Kelvin(1), Celsius(2), sensor unit(3)
               onoff (str): on or off to switch on or off the control loop
          Returns:
               None if set
               input (str): which input to control from
               units (str): set-point unit: Kelvin, Celsius, sensor unit
               onoff (str): control loop on/off
        """
        self.log.info("_cset")
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
                raise ValueError(
                    "Error: acceptables values for units are 'Kelvin' or 'Celsius' or 'Sensor unit'."
                )
            else:
                units = self.UNITS340[units]
            if onoff is None:
                onoff = onoffc
            elif onoff != "on" and onoff != "off":
                raise ValueError(
                    "Error: acceptables values for onoff are 'on' or 'off'."
                )
            else:
                onoff = 1 if onoff == "on" else 0

            self.send_cmd("CSET", input, units, onoff)

    # 'Internal' COMMUNICATION method
    # -------------------------------
    def send_cmd(self, command, *args):
        """ Send a command to the controller
            Args:
              command (str): The command string
              args: Possible variable number of parameters
            Returns:
              None
        """

        self.log.info("send_cmd")
        self.log.debug("command = {0}".format(command))
        ## print("command = {0}".format(command))

        if command.startswith("*"):
            if "?" in command:
                asw = self._comm.write_readline(command.encode() + self.eos.encode())
                return asw.decode()
            else:
                self._comm.write(command.encode() + self.eos.encode())
        elif "?" in command:
            if (
                "CRVHDR" in command
                or "RANGE" in command
                or "HTR" in command
                or "HTRST" in command
            ):
                cmd = command
            else:
                if isinstance(self._channel, str):
                    cmd = command + " %s" % self._channel
                else:
                    cmd = command + " %r" % self._channel
            asw = self._comm.write_readline(cmd.encode() + self.eos.encode())
            return asw.decode()
        else:
            if (
                "RANGE" in command
                or "CRVHDR" in command
                or "CRVPT" in command
                or "CRVDEL" in command
                or "CRVSAV" in command
            ):
                value = "".join(str(x) for x in args)
                ## print("--------- command = {0}".format(command))
                cmd = command + " %s *OPC" % (value) + self.eos
            else:
                inp = ",".join(str(x) for x in args)
                if isinstance(self._channel, str):
                    cmd = command + " %s,%s *OPC" % (self._channel, inp) + self.eos
                else:
                    cmd = command + " %d,%s *OPC" % (self._channel, inp) + self.eos

            self._comm.write(cmd.encode())

    # Raw COMMUNICATION methods
    # -------------------------
    def wraw(self, string):
        """ Write a string to the controller
            Args:
              string The complete raw string to write (except eos)
                     Normaly will use it to set a/some parameter/s in 
                     the controller.
            Returns:
              None
        """
        self.log.info("wraw")

        self.log.debug("command to send = {0}".format(string))
        cmd = string + " *OPC" + self.eos
        self._comm.write(cmd.encode())

    def rraw(self):
        """ Read a string from the controller
            Returns:
              response from the controller
        """

        self.log.info("rraw")
        cmd = self.eos
        asw = self._comm.readline(cmd.encode())
        self.log.debug("raw answer = {0}".format(asw))
        return asw.decode()

    def wrraw(self, string):
        """ Write a string to the controller and then reading answer back
            Args:
              string The complete raw string to write (except eos)
            Returns:
              response from the controller
        """

        self.log.info("wrraw")
        self.log.debug("command to send = {0}".format(string))
        cmd = string + self.eos
        asw = self._comm.write_readline(cmd.encode())
        self.log.debug("raw answer = {0}".format(asw))
        return asw.decode()


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
