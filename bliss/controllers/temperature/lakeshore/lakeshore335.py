# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Lakeshore 335, acessible via GPIB or USB

yml configuration example:
#controller:
- class: lakeshore335
  module: lakeshore.lakeshore335
  name: lakeshore335
  timeout: 3
  gpib:
     url: enet://gpibid10f.esrf.fr
     pad: 9 
  usb:
     url: ser2net://lid102:28000/dev/ttyUSB0
     # when not in model 331 or model 332 emulation mode,
     # baud-rate of 57600 is the only one possible. If configured
     # in emulation mode, then can have also 300, 1200, 9600
     # as possible values for baud-rate.
     baudrate: 57600
  inputs:
    - name: ls335_A
      channel: A 
      unit: Kelvin
      #tango_server: ls_335
    - name: ls335_A_c    # input temperature in Celsius
      channel: A
      unit: Celsius
    - name: ls335_A_su  # in sensor units (Ohm or Volt)
      channel: A
      unit: Sensor_unit

    - name: ls335_B
      channel: B 
      unit: Kelvin
      #tango_server: ls_335
    - name: ls335_B_c    # input temperature in Celsius
      channel: B
      unit: Celsius
    - name: ls335_B_su  # in sensor units (Ohm or Volt)
      channel: B
      unit: Sensor_unit

  outputs:
    - name: ls335o_1
      channel: 1 
      unit: Kelvin
    - name: ls335o_2
      channel: 2 

  ctrl_loops:
    - name: ls335l_1
      input: $ls335_A
      output: $ls335o_1
      channel: 1
    - name: ls335l_2
      input: $ls335_B
      output: $ls335o_2
      channel: 2
"""
import types
import time
import enum
from bliss.comm import serial
from bliss.comm.util import get_interface, get_comm
from bliss.common.logtools import LogMixin
from bliss.controllers.temperature.lakeshore.lakeshore import LakeshoreBase

_last_call = time.time()
# limit number of commands per second
# lakeshore 331 supports at most 20 commands per second
def _send_limit(func):
    def f(*args, **kwargs):
        global _last_call
        delta_t = time.time() - _last_call
        if delta_t <= 0.15:
            time.sleep(0.15 - delta_t)
        try:
            return func(*args, **kwargs)
        finally:
            _last_call = time.time()

    return f


class LakeShore335(LogMixin):
    UNITS331 = {"Kelvin": 1, "Celsius": 2, "Sensor unit": 3}
    REVUNITS331 = {1: "Kelvin", 2: "Celsius", 3: "Sensor unit"}
    IPSENSORUNITS331 = {1: "volts", 2: "ohms"}

    def __init__(self, comm, **kwargs):
        self._comm = comm
        self._channel = None

        self._logger.info("__init__")

    @property
    def eol(self):
        return self._comm._eol

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
        self._logger.info("_initialize_input")
        self._add_custom_method_input(input)

    # - Output object
    #   -------------
    def _initialize_output(self, output):
        self._logger.info("_initialize_output")
        # self._add_custom_method_output(output)

    # - Loop object
    #   -----------
    def _initialize_loop(self, loop):
        self._logger.info("_initialize_loop")
        self._add_custom_method_loop(loop)
        # Get input object channel
        ipc = loop.input.config["channel"]
        # Get output object unit
        opu = loop.input.config["unit"]
        # Get loop object channel
        loop_channel = loop.config["channel"]

        self.set_loop_params(loop_channel, input=ipc, unit=opu)

    # Standard INPUT-object related method(s)
    # ---------------------------------------
    def read_temperature(self, channel, scale):
        """ Read the current temperature
            Args:
              channel (int): input channel. Valid entries: A or B
              scale (str): temperature unit for reading: Kelvin or Celsius
                           or Sensor_unit (Ohm or Volt)
            Returns:
              (float): current temperature
        """
        self._logger.info("read_temperature")
        # Query Input Status before reading temperature
        # If status is OK, then read the temperature
        asw = int(self.send_cmd("RDGST?", channel=channel))
        if asw == 0:
            if scale == "Kelvin":
                return float(self.send_cmd("KRDG?", channel=channel))
            elif scale == "Celsius":
                return float(self.send_cmd("CRDG?", channel=channel))
            elif scale == "Sensor_unit":
                return float(self.send_cmd("SRDG?", channel=channel))
        if asw & 16:
            self._logger.warning("Temperature UnderRange on input %s" % channel)
            raise ValueError("Temperature value on input %s is invalid" % channel)
        if asw & 32:
            self._logger.warning("Temperature OverRange on input %s" % channel)
            raise ValueError("Temperature value on input %s is invalid" % channel)
        if asw & 64:
            self._logger.warning("Temperature in Sensor_unit = 0 on input %s" % channel)
            raise ValueError("Temperature in Sensor_unit = 0 on input %s" % channel)
        if asw & 128:
            self._logger.warning(
                "Temperature OverRange in Sensor_unit on input %s" % channel
            )
            raise ValueError(
                "Temperature OverRange in Sensor_unit on input %s" % channel
            )

    # Adding CUSTOM INPUT-object related method(s)
    # --------------------------------------------
    def _add_custom_method_input(self, input):
        self._logger.info("_add_custom_method_input")

        def alarm_status():
            """ Shows high and low alarm state for given input
                Args:
                  None
                Returns:
                  high and low alarm state (str, str): "On/Off"
            """
            self._logger.info("alarm_status")
            return self._alarm_status(input.config.get("channel"))

        input.alarm_status = alarm_status

        def alarm_reset():
            """ Clears both the high and low status of all alarms
                Args:
                  None (though this command does not need the input channel,
                        we put it here, since alarms are related to the state
                        on input like for ex. measured temperature above 
                        alarm high-limit etc.)
                Returns:
                  None
            """
            self.log.info("alarm_reset")
            return self._alarm_reset()

        input.alarm_reset = alarm_reset

        # Next 3 (model, show, loglevel) are also in custom methods
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
                Returns:
                  model, PID, heater range, loop status, sensors 
                  configuration, inputs temperature
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
              value (float): The ramp rate [K/min] 0.1 to 100 with 0.1 resolution 
                             or None when reading.
           Returns:
              None if set
              value (float): The value of the ramp rate if read.
        """
        self.log.info("ramp_rate")
        self._channel = channel
        if value is None:
            rate_value = self.send_cmd("RAMP?").split(",")[1]
            return float(rate_value)

        # send the ramp rate if OK
        if value < 0.1 or value > 100:
            raise ValueError("Ramp value %s is out of bounds [0.1,100]" % value)

        # send the ramp rate
        self.send_cmd("RAMP", 0, value)

    def ramp(self, channel, sp, rate):
        """Change temperature to a set value at a controlled ramp rate
            Args:
              channel (int): output channel. Valid entries: 1 or 2
              rate (float): ramp rate [K/min], values 0.1 to 100 with 0.1 resolution 
              sp (float): target setpoint [K]
            Returns:
              None
        """
        self.log.info("ramp")
        self.log.debug("ramp(): SP=%r, RR=%r" % (sp, rate))
        self._channel = channel
        self.setpoint(channel, sp)
        if rate < 0.1 or rate > 100:
            raise ValueError("Ramp value %s is out of bounds [0.1,100]" % rate)
        self.send_cmd("RAMP", 1, rate)

    # Adding CUSTOM OUTPUT-object related method(s)
    # ---------------------------------------------
    def _add_custom_method_output(self, output):
        self.log.info("_add_custom_method_output")

        def ramp_status():
            """Check ramp status (if running or not)
               Args:
                  None
                Returns:
                  Ramp status (1 = running, 0 = not running)
            """
            self.log.info("ramp_status")
            return self._rampstatus(output.config.get("channel"))

        output.ramp_status = ramp_status

        def heater_range(value=None):
            """ Set/Read the heater range (0 to 3) from 0 to 50W in 50Ohms
                Args:
                  value (int): The value of the range if set. The valid range: 
                               for chan. 1 and 2: 0=Off,1=Low,2=Medium,3=High
                               for channels 3 and 4: 0=Off,1=On
                               None if read
                Returns:
                  None if set
                  value (int): The value of the range if read
            """
            self.log.info("heater_range")
            return self._heater_range(output.config.get("channel"), value=value)

        output.heater_range = heater_range

        def outmode(mode=None, input=None):
            """ Read/Set Output Control Mode and  Control Input
                Args:
                   mode (int): control mode. Valide entires: 0=Off,
                               1=Closed Loop PID, 2=Zone, 3=Open Loop,
                               4=Monitor Out, 5=Warmup Supply
                   input (str): which input to control from. 
                                Valid entries: None, A, B
              Returns:
                   None if set
                   mode (str): control mode
                   input (str): which input controls the loop.
            """
            self.log.info("outmode")
            return self._outmode(output.config.get("channel"), mode=mode, input=input)

        output.outmode = outmode

        # Next 3 (model, show, loglevel) are also in custom methods
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
            """ Display all main parameters and values for the 
                temperature controller
                Returns:
                  model, PID, heater range, loop status, sensors 
                  configuration, inputs temperature
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
        self.log.info("pid")
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
            if float(kp) < 0.1 or float(kp) > 1000.:
                raise ValueError(
                    "Proportional gain %s is out of bounds [0.1,1000]" % kp
                )
            if float(ki) < 0.1 or float(ki) > 1000.:
                raise ValueError("Integral reset %s is out of bounds [0.1,1000]" % ki)
            if float(kd) < 0 or float(kd) > 200:
                raise ValueError("Derivative rate %s is out of bounds [0,200]" % kd)
            self.send_cmd("PID", kp, ki, kd)
        else:
            kp, ki, kd = self.send_cmd("PID?").split(",")
            return float(kp), float(ki), float(kd)

    # Adding CUSTOM LOOP-object related method(s)
    # ---------------------------------------------
    def _add_custom_method_loop(self, loop):
        self.log.info("_add_custom_method_loop")

        def outmode(mode=None, input=None):
            """ Read/Set Output Control Mode and  Control Input
                Args:
                   mode (int): control mode. Valid entries: 0=Off,
                               1=Closed Loop PID, 2=Zone, 3=Open Loop,
                               4=Monitor Out, 5=Warmup Supply
                   input (str): which input to control from. 
                                Valid entries: None, A or B.
              Returns:
                   None if set
                   mode (str): control mode
                   input (str): which input control the loop.
            """
            self.log.info("outmode")
            return self._outmode(loop.config.get("channel"), mode=mode, input=input)

        loop.outmode = outmode

        # Next 3 (model, show, loglevel) are also in custom methods
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
            """ Display all main parameters and values for the 
                temperature controller
                Returns:
                  model, PID, heater range, loop status, 
                  sensors configuration, inputs temperature
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
        return int(model[5:8])

    def _show(self):
        """ Display all main parameters and values for the 
            temperature controller
            Returns:
              device ID, PID, heater range, loop status, 
              sensors configuration, inputs temperature etc.
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
            % (asw[0].strip(), asw[1].strip(), self.CURVEFORMAT335[int(asw[2])])
        )
        print(
            "Temp.limit = %s K , Temp.coeff. = %s"
            % (asw[3], self.CURVETEMPCOEF335[int(asw[4])])
        )

        # Get input A sensor preferred units (Kelvin,Celsius,Sensor-unit)
        # The same preferred units are used for the control set-point
        asw = self.send_cmd("INTYPE?")
        asw = asw.split(",")
        ipsu_A = asw[4]
        print("Input A sensor preferred units = %s" % self.REVSPUNITS335[int(ipsu_A)])

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
            print("Input A reading in Sensor Units = %.3f" % resorvol_A)
        else:
            print("Invalid status on input %s" % self._channel)
            if asw & 16:
                self.log.warning("Temperature UnderRange on input %s" % self._channel)
            if asw & 32:
                self.log.warning("Temperature OverRange on input %s" % self._channel)
            if asw & 64:
                self.log.warning("0 value in sensor units on input %s" % self._channel)
            if asw & 128:
                self.log.warning(
                    "Overrange of value in sensor units on input %s" % self._channel
                )

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
            % (asw[0].strip(), asw[1].strip(), self.CURVEFORMAT335[int(asw[2])])
        )
        print(
            "Temp.limit = %s K, Temp.coeff. = %s"
            % (asw[3], self.CURVETEMPCOEF335[int(asw[4])])
        )

        # Get input B sensor preferred units (Kelvin,Celsius,Sensor-unit)
        # The same preferred units are used for the control set-point
        asw = self.send_cmd("INTYPE?")
        asw = asw.split(",")
        ipsu_B = asw[4]
        print("Input B sensor preferred units = %s" % self.REVSPUNITS335[int(ipsu_B)])

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
            print("Input B reading in Sensor Units = %.3f" % resorvol_B)
        else:
            print("Invalid status on input %s" % self._channel)
            if asw & 16:
                self.log.warning("Temperature UnderRange on input %s" % self._channel)
            if asw & 32:
                self.log.warning("Temperature OverRange on input %s" % self._channel)
            if asw & 64:
                self.log.warning("0 value in sensor units on input %s" % self._channel)
            if asw & 128:
                self.log.warning(
                    "Overrange of value in sensor units on input %s" % self._channel
                )

        # Loop 1
        # ------
        print("\nLoop 1:")
        print("=======")

        # Specify channel to be used in send_cmd for the commands
        # needing it: OUTMODE?, RAMP?, SETP?, RAMPST?, PID?
        self._channel = "1"

        # Get control loop parameters
        asw = self.send_cmd("OUTMODE?").split(",")
        mode = asw[0]
        sensor = asw[1]
        if sensor == "1":
            units = ipsu_A
        if sensor == "2":
            units = ipsu_B

        units = self.REVSPUNITS335[int(units)]
        print("Controlled by sensor %s in %s " % (sensor, units))
        print("Temp Control is set to %s" % self.MODE335[int(mode)])

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
        # needing it: OUTMODE?, RAMP?, SETP?, RAMPST?, PID?

        self._channel = "2"

        # Get control loop parameters
        asw = self.send_cmd("OUTMODE?").split(",")
        mode = asw[0]
        sensor = asw[1]
        if sensor == "1":
            units = ipsu_A
        if sensor == "2":
            units = ipsu_B
        units = self.REVSPUNITS335[int(units)]
        print("Controlled by sensor %s in %s " % (sensor, units))
        print("Temp Control is set to %s" % self.MODE335[int(mode)])

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

        # Get PID parameters for loop 2
        kp, ki, kd = self.send_cmd("PID?").split(",")
        print("PID parameters: ")
        print("     P = %.1f" % float(kp))
        print("     I = %.1f" % float(ki))
        print("     D = %.1f" % float(kd))

        # Output Heater
        # -------------
        print("\nHeater 1:")
        print("=========")
        # Get heater range value
        self._channel = "1"
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
        print("Heater status = %s" % self.HTRSTATUS335[int(htr_status)])

        print("\nHeater 2:")
        print("=========")
        # Get heater range value
        self._channel = "2"
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
        print("Heater status = %s" % self.HTRSTATUS335[int(htr_status)])

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
              curve number (int): 0=none, 1->20 standard, 21->59 user defined curves
              curve name (str): limited to 15 characters
              curve SN (str): limited to 10 characters (Standard,...)
              curve format (int): 1=mV/K, 2=V/K, 3=Ohms/K, 4=logOhms/K
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
        curve_format = self.CURVEFORMAT335[int(header[2])]
        curve_temperature_limit = header[3]
        curve_temperature_coefficient = self.CURVETEMPCOEF335[int(header[4])]

        print("Used curve number is: %d" % int(curve_number))
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
                                        21->59 user defined
	    Returns: 
	      None
        """
        self.log.info("_curve_to_use")
        self._channel = channel
        if crvn not in range(1, 60):
            raise ValueError("Curve number %d is invalid. Should be [1,59]" % crvn)
        else:
            self.send_cmd("INCRV", crvn)

    def _curve_list_all(self):
        """ Get the input curve used
            Print:
               curve number (int): 0=none, 1->20 standard, 21->59 user defined curves
               curve name (str): limited to 15 characters
               curve SN (str): limited to 10 characters (Standard,...)
               curve format (int): 1=mV/K, 2=V/K, 3=Ohms/K, 4=logOhms/K
               curve temperature limit (float): in Kelvin
               curve temperature coefficient (int): 1=negative, 2=positive
        """
        self.log.info("_curve_list_all")
        # curve_number = self.send_cmd("INCRV?")
        print(" #            Name       SN         Format     Limit(K) Temp. coef.")
        for i in range(1, 60):
            command = "CRVHDR? %s" % i
            curve_header = self.send_cmd(command)
            header = curve_header.split(",")
            curve_name = header[0].strip()
            curve_sn = header[1]
            curve_format = self.CURVEFORMAT335[int(header[2])]
            curve_temperature_limit = header[3]
            curve_temperature_coefficient = self.CURVETEMPCOEF335[int(header[4])]
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
              crvn (int): The user curve number from 21 to 59 
              crvfile (str): full file name
            Returns:
              Status of curve written
        """
        self.log.info("_curve_write")
        if crvn is None:
            crvn = input("Number of curve to be written [21,59]? ")
        else:
            print("Curve number passed as arg = %d" % crvn)

        if crvn not in range(21, 60):
            raise ValueError("User curve number %d is not in [21,59]" % crvn)

        print("Readings from actual curve %d in LakeShore 335 :" % crvn)
        command = "CRVHDR? %d" % crvn
        loaded_curve = self.send_cmd(command)
        header = loaded_curve.split(",")
        curve_name = header[0].strip()
        curve_sn = header[1]
        curve_format = self.CURVEFORMAT335[int(header[2])]
        curve_temp_limit = header[3]
        curve_temp_coeff = self.CURVETEMPCOEF335[int(header[4])]
        print("no channel")
        print(
            "\t%15s %10s %12s %12s %s"
            % (curve_name, curve_sn, curve_format, curve_temp_limit, curve_temp_coeff)
        )
        print("no channel")
        if crvfile is None:
            crvfile = input("Filename of temperature curve? ")
        else:
            print("File name passed as arg = %s" % crvfile)

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
            elif int(curve_format) not in range(1, 5):
                raise ValueError("Curve data format %s not in [1,4]" % curve_format)
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
            "Curve %d has been written into the LakeShore model 335 temperature controller."
            % crvn
        )

        # Reading back for checking the header
        command = "CRVHDR? %d" % crvn
        curve_header = self.send_cmd(command)
        print("The header read back for the %d is:" % crvn)
        print(curve_header)

    def _curve_delete(self, crvn):
        """ Delete a user curve from the Lakeshore
            Args:
              crvn (int): The user curve number from 21 to 59 
            Returns:
              None.
        """
        self.log.info("_curve_delete")
        if crvn is None:
            crvn = input("Number of curve to be deleted [21,59]? ")
        else:
            print("Curve number passed as arg = %d" % crvn)

        if crvn not in range(21, 60):
            raise ValueError("User curve number %d is not in [21,59]" % crvn)

        # Delete the curve
        command = "CRVDEL %d" % crvn
        self.send_cmd(command)

    def _filter(self, channel, **kwargs):
        """ Configure(Set)/Read input filter parameters
            Args:
              channel (str): input channel. Valid entries: A or B
                             If read, only this parameter is needed.
              onoff (int): 1 = enable, 0 = disable
              points (int): specifies how many points the filtering fct uses.
                            Valid range: 2 to 64.
              window (int): specifies what percent of full scale reading
                            limits the filtering function. Reading changes
                            greater than this percentage reset the filter.
                            Valid range: 1 to 10%.
              None if read
            Returns:
              None if set
              onoff (int): filter on/off
              points (int): nb of points used by filter function
              window (int): filter window (in %)
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

    def _intype(self, channel, **kwargs):
        """ Read/set input type parameters
            Args: 
              channel (str): A to D. If read only this arg is needed
              sensor_type (int): Valid entries: 0=Disabled, 1=Diode,
                                 2=Platinum RTD, 3=NTC RTD,
                                 4=Thermocouple (3060 option only)
              autorange (int): 0=off, 1=on
              iprange (int): input range when autorange in off ;
                             see table 6-8 on page 118 of manual
              compensation (int): input compensation. 0=off, 1=on
              unit (int): prefered unit for sensor reading AND for the 
                         control setpoint. 1=Kelvin, 2=Celsius, 3=Sensor_unit
              Returns:
                None if set
                sensor_type, autorange, iprange, compensation, unit
        """

        self.log.info("_intype")
        self._channel = channel
        sensor_type = kwargs.get("sensor_type")
        autorange = kwargs.get("autorange")
        iprange = kwargs.get("iprange")
        compensation = kwargs.get("compensation")
        unit = kwargs.get("unit")

        if (
            sensor_type is None
            and autorange is None
            and iprange is None
            and compensation is None
            and unit is None
        ):
            asw = self.send_cmd("INTYPE?").split(",")
            sensor_type = asw[0]
            autorange = asw[1]
            iprange = asw[2]
            compensation = asw[3]
            unit = asw[4]
            return (sensor_type, autorange, iprange, compensation, unit)
        else:
            sensor_typec, autorangec, iprangec, compensationc, unitc = self.send_cmd(
                "INTYPE?"
            ).split(",")
            if sensor_type is None:
                sensor_type = sensor_typec
            elif sensor_type not in range(0, 5):
                raise ValueError("Error: acceptable value for sensor type are 0->4.")
            if autorange is None:
                autorange = autorangec
            if iprange is None:
                iprange = iprangec
            elif autorange == "off":
                if (
                    sensor_type == 1
                    and iprange not in [0, 1]
                    or sensor_type == 2
                    and iprange not in range(0, 6)
                    or sensor_type == 3
                    and iprange not in range(0, 9)
                    or sensor_type == 4
                    and iprange != 0
                ):
                    raise ValueError("Error: bad value for input range")
            if compensation is None:
                compensation = compensationc
            if unit is None:
                unit = unitc
            elif unit not in [1, 2, 3]:
                raise ValueError(
                    "Error: invalid value for input sensor reading and for the control setpoint; should be 1,2 or 3"
                )

            self.send_cmd("INTYPE", sensor_type, autorange, iprange, compensation, unit)

    def _alarm_status(self, channel):
        """ Shows high and low alarm state for given input
            Args:
              channel (str): A or B
            Returns:
              high and low alarm state (str, str): "On/Off"
        """
        self.log.info("_alarm_status")
        self._channel = channel
        asw = self.send_cmd("ALARMST?").split(",")
        hist = "On" if int(asw[0]) == 1 else "Off"
        lost = "On" if int(asw[1]) == 1 else "Off"
        self.log.debug("Alarm high state = %s" % hist)
        self.log.debug("Alarm Low  state = %s" % lost)
        return (hist, lost)

    def _alarm_reset(self):
        """ Clears both the high and low status of all alarms
            Args:
              None (though this command does not need even the input
                    channel, we put it here since alarms are related
                    to the state on input like for ex. measured temperature
                    above alarm high-limit etc)
            Returns:
              None
        """
        self.log.info("_alarm_reset")
        self.send_cmd("ALMRST")

    # CUSTOM OUTPUT-object related method(s)
    # --------------------------------------
    def _rampstatus(self, channel):
        """Check ramp status (if running or not)
            Args:
              channel (int): output channel. Valid entries: 1 or 2
            Returns:
              Ramp status (1 = running, 0 = not running)
        """
        # TODO: in case rampstatus found is 0 (= no ramping active)
        #       could add sending command OPSTE? and checking in the answer
        #       Bit 3 (for output 1 ramp status) or
        #       Bit 2 (for output 2 ramp-status)
        #       which indicates (when set to 1) that ramp is done.
        self.log.info("_rampstatus")
        self.log.debug("_rampstatus(): channel = %r" % channel)
        self._channel = channel
        ramp_stat = self.send_cmd("RAMPST?")
        self.log.debug("_rampstatus(): ramp_status = %r" % ramp_stat)
        return int(ramp_stat)

    def _heater_range(self, channel, value=None):
        """ Set/Read the heater range (0=off 1=low 2=medium 3=high)
            Args:
              channel (int): output channel: 1 or 2
              value (int): The value of the range if set. The valid range:
			   for channels 1 and 2: 0=Off,1=Low,2=Medium,3=High
                           None if read
           Returns:
              None if set
              value (int): The value of the heater range if read
        """
        self.log.info("_heater_range")
        self._channel = channel
        if value is None:
            return int(self.send_cmd("RANGE?"))
        # send the range
        if value not in [0, 1, 2, 3]:
            raise ValueError("Error, the value {0} is not in 0 to 3.".format(value))
        else:
            self.send_cmd("RANGE", value)

    def _outmode(self, channel, **kwargs):
        """ Read/Set Output Control Mode, Control Input and Power-Up
            Enable Parameters
            Args:
               channel(int): output channel. Valid entries: 1-4
            Kwargs:
               mode (int): control mode. Valide entires: 0=Off,
                           1=Closed Loop PID, 2=Zone, 3=Open Loop,
                           4=Monitor Out, 5=Warmup Supply
               input (str): which input to control from.
                            Valid entries: None, A or B.
          Returns:
               None if set
               mode (str): control mode as string
               input (str): which input to control from
        """
        self.log.info("_outmode")
        self._channel = channel
        mode = kwargs.get("mode")
        input = kwargs.get("input")
        # The output power remains off after power cycle
        powerup = 0

        if mode is None and input is None:
            asw = self.send_cmd("OUTMODE?").split(",")
            mode = self.MODE335[int(asw[0])]
            input = self.REVINPUT335[int(asw[1])]
            return (mode, input)
        else:
            modec, inputc, powerupc = self.send_cmd("OUTMODE?").split(",")
            if mode is None:
                mode = modec
            elif mode not in range(0, 6):
                raise ValueError("Error: acceptable value for control mode are 0->5.")
            if input is None:
                input = inputc
            elif input not in ["None", "A", "B"]:
                raise ValueError("Error: acceptable value for input are None,'A','B'.")
            else:
                input = self.INPUT335[input]

            self.send_cmd("OUTMODE", mode, input, powerup)

    # CUSTOM LOOP-object related method(s)
    # ------------------------------------

    # 'Internal' COMMUNICATION method
    # -------------------------------
    def send_cmd(self, command, *args):
        """Send a command to the controller
           Args:
              command (str): The command string
              args: Possible variable number of parameters
           Returns:
              None
        """

        self.log.info("send_cmd")
        self.log.debug("command = {0}".format(command))

        if command.startswith("*"):
            if "?" in command:
                asw = self._comm.write_readline(command.encode() + self.eos.encode())
                return asw.decode()
            else:
                self._comm.write(command.encode() + self.eos.encode())
        elif "?" in command:
            if "CRVHDR" in command:
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
                "CRVHDR" in command
                or "CRVPT" in command
                or "CRVDEL" in command
                or "ALMRST" in command
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
        """Write a string to the controller
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
        """Read a string from the controller
           Returns:
              response from the controller
        """

        self.log.info("rraw")
        cmd = self.eos
        asw = self._comm.readline(cmd.encode())
        self.log.debug("raw answer = {0}".format(asw))
        return asw.decode()

    def wrraw(self, string):
        """Write a string to the controller and then reading answer back
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


class lakeshore335(Base):
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
            raise ValueError("Must specify gpib or serial")

        _lakeshore = LakeShore335(comm_type, url, extra_param=extra_param, eos=eos)

        model = _lakeshore._model()

        if model != 335:
            raise ValueError(
                "Error, the Lakeshore model is {0}. It should be 335.".format(model)
            )
        # else:
        #     print("\t\t\tthe model is {0}".format(model))

        Base.__init__(self, _lakeshore, config, *args)
