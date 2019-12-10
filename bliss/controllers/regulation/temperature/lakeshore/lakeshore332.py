# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Lakeshore 332, acessible via GPIB and Serial line (RS232)

yml configuration example:
#controller:
- class: lakeshore332
  module: lakeshore.lakeshore332
  name: lakeshore332
  timeout: 3
  gpib:
     url: enet://gpibid10f.esrf.fr
     pad: 12
     eol: "\r\n"     
  # serial:
  #    url: ser2net://lid102:28000/dev/ttyR1
  #    baudrate: 9600    # = max (other possible values: 300, 1200)
  #    eol: "\r\n"     
  inputs:
    - name: ls332_A
      channel: A 
      # possible set-point units: Kelvin, Celsius, Sensor_unit
      unit: Kelvin
      #tango_server: ls_332
    - name: ls332_A_c    # input temperature in Celsius
      channel: A
      unit: Celsius
    - name: ls332_A_su  # in sensor units (Ohm or Volt)
      channel: A
      unit: Sensor_unit

    - name: ls332_B
      channel: B 
      # possible set-point units: Kelvin, Celsius, Sensor_unit
      unit: Kelvin
      #tango_server: ls_332
    - name: ls332_B_c    # input temperature in Celsius
      channel: B
      unit: Celsius
      type: temperature_C
    - name: ls332_B_su  # in sensor units (Ohm or Volt)
      channel: B
      unit: Sensor_unit

  outputs:
    - name: ls332o_1
      channel: 1 
    - name: ls332o_2
      channel: 2 

  ctrl_loops:
    - name: ls332l_1
      input: $ls332_A
      output: $ls332o_1
      channel: 1
    - name: ls332l_2
      input: $ls332_B
      output: $ls332o_2
      channel: 2
"""

import time
import enum
from bliss.comm import serial
from bliss.comm import gpib
from bliss.comm.util import get_interface, get_comm
from bliss.common.logtools import *
from bliss.controllers.temperature.lakeshore.lakeshore import LakeshoreBase
from .lakeshore import LakeshoreInput as Input
from .lakeshore import LakeshoreOutput as Output
from .lakeshore import LakeshoreLoop as Loop

_last_call = time.time()
# limit number of commands per second
# lakeshore 332 supports at most 20 commands per second
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


class LakeShore332:
    UNITS332 = {"Kelvin": 1, "Celsius": 2, "Sensor unit": 3}
    REVUNITS332 = {1: "Kelvin", 2: "Celsius", 3: "Sensor unit"}
    IPSENSORUNITS332 = {1: "volts", 2: "ohms"}

    def __init__(self, comm, **kwargs):
        self._comm = comm
        self._channel = None
        log_info(self, "__init__")

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
        log_info(self, "_initialize_input")

    # - Output object
    #   -------------
    def _initialize_output(self, output):
        log_info(self, "_initialize_output")

    # - Loop object
    #   -----------
    def _initialize_loop(self, loop):
        log_info(self, "_initialize_loop")
        # Get input object channel
        ipch = loop.input.config["channel"]
        # Get output object unit
        ipu = loop.input.config["unit"]
        # Get loop object channel
        loop_channel = loop.config["channel"]

        self.set_loop_params(loop_channel, input=ipch, unit=ipu)

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
        log_info(self, "read_temperature")
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
            log_warning(self, "Temperature UnderRange on input %s" % channel)
            raise ValueError("Temperature value on input %s is invalid" % channel)
        if asw & 32:
            log_warning(self, "Temperature OverRange on input %s" % channel)
            raise ValueError("Temperature value on input %s is invalid" % channel)
        if asw & 64:
            log_warning(self, "Temperature in Sensor_unit = 0 on input %s" % channel)
            raise ValueError("Temperature in Sensor_unit = 0 on input %s" % channel)
        if asw & 128:
            log_warning(
                self, "Temperature OverRange in Sensor_unit on input %s" % channel
            )
            raise ValueError(
                "Temperature OverRange in Sensor_unit on input %s" % channel
            )
        raise RuntimeError("Could not read temperature on channel %s" % channel)

    def _sensor_type(self, channel, type=None, compensation=None):
        """ Read or set input type parameters
        Args: According to the model, use the appropriate args
            type (int): 0 to ?
            compensation (int): 0=off and 1=on

            example: input.sensor_type(type=3,compensation=1) 
        Returns:
            <type>, <compensation>
        """
        log_info(self, "_sensor_type")
        if type is None:
            return self.send_cmd("INTYPE?", channel=channel)
        else:
            self.send_cmd("INTYPE", type, compensation, channel=channel)

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
        log_info(self, "setpoint")
        if value is None:
            return float(self.send_cmd("SETP?", channel=channel))
        else:
            self.send_cmd("SETP", value, channel=channel)

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
        log_info(self, "ramp_rate")
        if value is None:
            r = self.send_cmd("RAMP?", channel=channel).split(",")
            state = "ON" if int(r[0]) == 1 else "OFF"
            rate_value = float(r[1])
            return {"state": state, "rate": rate_value}
        if value < 0.1 or value > 100:
            raise ValueError("Ramp value %s is out of bounds [0.1,100]" % value)
        self.send_cmd("RAMP", 0, value, channel=channel)

    def ramp(self, channel, sp, rate):
        """ Change temperature to a set value at a controlled ramp rate
            Args:
              channel (int): output channel. Valid entries: 1 or 2
              rate (float): ramp rate [K/min], values 0.1 to 100 with 0.1 resolution 
              sp (float): target setpoint [K]
            Returns:
              None
        """
        log_info(self, "ramp")
        log_debug(self, "ramp(): SP=%r, RR=%r" % (sp, rate))
        self.setpoint(channel, sp)
        if rate < 0.1 or rate > 100:
            raise ValueError("Ramp value %s is out of bounds [0.1,100]" % rate)
        self.send_cmd("RAMP", 1, rate, channel=channel)

    def ramp_status(self, channel):
        """ Check ramp status (if running or not)
            Args:
              channel (int): output channel. Valid entries: 1 or 2
            Returns:
              Ramp status (1 = running, 0 = not running)
        """
        # TODO: in case rampstatus found is 0 (= no ramping active)
        #       could add sending command *STB? and checking bit 7,
        #       which indicates (when set to 1) that ramp is done.
        log_info(self, "ramp_status")
        log_debug(self, "ramp_status(): channel = %r" % channel)
        ramp_stat = self.send_cmd("RAMPST?", channel=channel)
        log_debug(self, "ramp_status(): ramp_status = %r" % ramp_stat)
        return int(ramp_stat)

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
        log_info(self, "pid")
        kp = kwargs.get("P")
        ki = kwargs.get("I")
        kd = kwargs.get("D")
        if len(kwargs):
            kpc, kic, kdc = self.send_cmd("PID?", channel=channel).split(",")
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
            self.send_cmd("PID", kp, ki, kd, channel=channel)
        else:
            kp, ki, kd = self.send_cmd("PID?", channel=channel).split(",")
            return float(kp), float(ki), float(kd)

    # General CUSTOM methods [valid for any type of object:
    # input, output, loop]
    # -----------------------------------------------------
    def _model(self):
        """ Get the model number
            Returns:
              model (int): model number
        """
        log_info(self, "_model")
        model = self.send_cmd("*IDN?").split(",")[1]
        return int(model[5:8])

    # CUSTOM INPUT-object related method(s)
    # -------------------------------------
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
              None if set
              onoff (int): filter on/off
              points (int): nb of points used by filter function
              window (int): filter window (in %)
        """
        log_info(self, "_filter")
        input = channel
        onoff = kwargs.get("onoff")
        points = kwargs.get("points")
        window = kwargs.get("window")

        if onoff is None and points is None and window is None:
            asw = self.send_cmd("FILTER?", channel=channel).split(",")
            onoff = int(asw[0])
            points = int(asw[1])
            window = int(asw[2])
            return (onoff, points, window)
        else:
            onoffc, pointsc, windowc = self.send_cmd("FILTER?", channel=channel).split(
                ","
            )
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
            self.send_cmd("FILTER", onoff, points, window, channel=channel)

    def _alarm_status(self, channel):
        """ Shows high and low alarm state for given input
            Args:
              channel (str): A or B
            Returns:
              high and low alarm state (str, str): "On/Off"
        """
        log_info(self, "_alarm_status")
        asw = self.send_cmd("ALARMST?", channel=channel).split(",")
        hist = "On" if int(asw[0]) == 1 else "Off"
        lost = "On" if int(asw[1]) == 1 else "Off"
        log_debug(self, "Alarm high state = %s" % hist)
        log_debug(self, "Alarm Low  state = %s" % lost)
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
        log_info(self, "_alarm_reset")
        self.send_cmd("ALMRST")

    # CUSTOM OUTPUT-object related method(s)
    # --------------------------------------

    # CUSTOM LOOP-object related method(s)
    # ------------------------------------
    def read_loop_params(self, channel, **kwargs):
        """ Read Control Loop Parameters
            Args:
               channel(int): loop channel. Valid entries: 1 or 2
            Kwargs:
               input (str): which input to control from. Valid entries: A or B
               unit (str): set-point unit: Kelvin(1), Celsius(2), Sensor_unit(3)
          Returns:
               input (str): which input to control from
               unit (str): set-point unit: Kelvin, Celsius, Sensor_unit
          Remark: In this method we do not pass 2 further arguments:
                  - power up state of control loop
                  - heater output display
                    since we keep them at default values. Therefore:
                  - We set the 4-th arg for CSET (when setting) to 0, which
                    means that the control loop is off after powerup. This
                    is the default value and the logic is consistent with
                    the one for models 336 and 340.
                  - We set the 5-th arg for CSET (when setting) to 1, which
                    means that the heater output display current. Other
                    possibility is to display power (2). We are thus
                    consistent with the default value (= 1 = current).
        """
        log_info(self, "_read_loop_params")
        asw = self.send_cmd("CSET?", channel=channel).split(",")
        input = asw[0]
        unit = self.REVUNITS332[int(asw[1])]
        powerup = "ON" if int(asw[2]) == 1 else "OFF"
        currpow = "current" if int(asw[3]) == 1 else "power"
        return {"input": input, "unit": unit, "powerup": powerup, "currpow": currpow}

    def set_loop_params(self, channel, input=None, unit=None):
        inputc, unitc, powerupc, currpowc = self.send_cmd(
            "CSET?", channel=channel
        ).split(",")
        if input is None:
            input = inputc
        if unit is None:
            unit = unitc
        elif unit != "Kelvin" and unit != "Celsius" and unit != "Sensor_unit":
            raise ValueError(
                "Error: acceptables values for unit are 'Kelvin' or 'Celsius' or 'Sensor_unit'."
            )
        else:
            unit = self.UNITS332[unit]

        self.send_cmd("CSET", input, unit, powerupc, currpowc, channel=channel)

    # 'Internal' COMMUNICATION method
    # -------------------------------
    @_send_limit
    def send_cmd(self, command, *args, channel=None):
        """ Send a command to the controller
            Args:
              command (str): The command string
              args: Possible variable number of parameters
            Returns:
              Answer from the controller if ? in the command
        """
        log_info(self, "send_cmd")
        log_debug(self, "command = {0}, channel = {1})".format(command, channel))
        if channel is None:
            values = "".join(str(x) for x in args)
            cmd = f"{command} {values}"
            # print("-------- command = {0}, values = {1}".format(cmd, values))
        else:
            # print("args = {0}".format(args))
            values = ",".join(str(x) for x in args)
            if len(values) == 0:
                cmd = f"{command} {channel}"
            else:
                cmd = f"{command} {channel},{values}"
            # print("------------ command = {0}".format(cmd))
        log_debug(self, "values = {0}".format(values))
        if "?" in command:
            asw = self._comm.write_readline(cmd.encode() + self.eol.encode())
            # print("asw = {0}".format(asw.decode()))
            return asw.decode().strip(";")
        else:
            self._comm.write(cmd.encode() + self.eol.encode())

    # Raw COMMUNICATION methods
    # -------------------------
    def wraw(self, string):
        """ Write a string to the controller
            Args:
              string The complete raw string to write (except eol)
                     Normaly will use it to set a/some parameter/s in 
                     the controller.
            Returns:
              None
        """
        log_info(self, "wraw")
        log_debug(self, "command to send = {0}".format(string))
        cmd = string + self.eol
        self._comm.write(cmd.encode())

    def rraw(self):
        """ Read a string from the controller
            Returns:
              response from the controller
        """
        log_info(self, "rraw")
        cmd = self.eol
        asw = self._comm.readline(cmd.encode())
        log_debug(self, "raw answer = {0}".format(asw))
        return asw.decode()

    def wrraw(self, string):
        """ Write a string to the controller and then reading answer back
            Args:
              string The complete raw string to write (except eol)
            Returns:
              response from the controller
        """
        log_info(self, "wrraw")
        log_debug(self, "command to send = {0}".format(string))
        cmd = string + self.eol
        asw = self._comm.write_readline(cmd.encode())
        log_debug(self, "raw answer = {0}".format(asw))
        return asw.decode()


class lakeshore332(LakeshoreBase):
    # Number of calibration curves available
    NCURVES = 41
    NUSERCURVES = (21, 41)
    CURVEFORMAT = {1: "mV/K", 2: "V/K", 3: "Ohms/K", 4: "logOhms/K"}
    CURVETEMPCOEF = {1: "negative", 2: "positive"}

    @enum.unique
    class Unit(enum.IntEnum):
        KELVIN = 1
        CELSIUS = 2
        SENSOR_UNIT = 3

    @enum.unique
    class Mode(enum.IntEnum):
        MANUAL_PID = 1
        ZONE = 2
        OPEN_LOOP = 3
        AUTO_TUNE_PID = 4
        AUTO_TUNE_PI = 5
        AUTO_TUNE_P = 6

    @enum.unique
    class HeaterRange(enum.IntEnum):
        OFF = 0
        LOW = 1
        MEDIUM = 2
        HIGH = 3

    @enum.unique
    class HeaterState(enum.IntEnum):
        OK = 0
        OPEN_LOAD = 1
        SHORT = 2

    def __init__(self, config, *args):
        if "serial" in config:
            comm_interface = get_comm(config, parity="O", bytesize=7, stopbits=1)
        else:
            comm_interface = get_comm(config)

        _lakeshore = LakeShore332(comm_interface)

        model = _lakeshore._model()
        if model != 332:
            raise ValueError(
                "Error, the Lakeshore model is {0}. It should be 332.".format(model)
            )

        LakeshoreBase.__init__(self, _lakeshore, config, *args)

    def _read_state_output(self, channel):
        log_info(self, "_state_output")
        r = int(self._lakeshore.send_cmd("HTRST?"))
        return self.HeaterState(r)

    def _read_value_percent(self, channel):
        log_info(self, "_state_output")
        return self._lakeshore.send_cmd("HTR?")

    def _read_heater_range(self, channel):
        """ Read the heater range """
        log_info(self, "_read_heater_range")
        r = int(self._lakeshore.send_cmd("RANGE?"))
        return self.HeaterRange(r)

    def _set_heater_range(self, channel, value=None):
        """ Set the heater range (0 to 3) [see Paragaph 4.13]
            It is used for heater output for loop 1, while for
            loop 2 can choose only between 0(heater off) and 1(heater on)
            though in the command syntax the output channel or loop
            is not used!! (cmd = RANGE value)
            Args:
              value (int): The value of the range
        """
        log_info(self, "_set_heater_range")
        v = self.HeaterRange(value).value
        self._lakeshore.send_cmd("RANGE", v)

    def _read_loop_mode(self, channel):
        return self.Mode(int(self._lakeshore.send_cmd("CMODE?", channel=channel)))

    def _set_loop_mode(self, channel, mode):
        value = self.Mode(mode).value
        self._lakeshore.send_cmd("CMODE", value, channel=channel)

    def _read_loop_unit(self, channel):
        log_info(self, "_read_loop_units")
        asw = self._lakeshore.send_cmd("CSET?", channel=channel).split(",")
        unit = int(asw[1])
        return self.Unit(unit)

    def _set_loop_unit(self, channel, unit):
        log_info(self, "_set_loop_units")
        asw = self._lakeshore.send_cmd("CSET?", channel=channel).split(",")
        value = self.Unit(unit).value
        self._lakeshore.send_cmd("CSET", asw[0], value, asw[2], asw[3], channel=channel)

    def _set_loop_on(self, tloop):
        log_info(self, "_set_loop_on")
        tloop.output.range = 1
        return tloop.output.range == self.HeaterRange.LOW

    def _set_loop_off(self, tloop):
        log_info(self, "_set_loop_off")
        tloop.output.range = 0
        return tloop.output.range == self.HeaterRange.OFF
