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
      # possible set-point units: Kelvin, Celsius, Sensor_unit
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
      # possible set-point units: Kelvin, Celsius, Sensor_unit
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
from bliss.comm import gpib
from bliss.comm.util import get_interface, get_comm
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


class LakeShore335:
    UNITS331 = {"Kelvin": 1, "Celsius": 2, "Sensor unit": 3}
    REVUNITS331 = {1: "Kelvin", 2: "Celsius", 3: "Sensor unit"}
    IPSENSORUNITS331 = {1: "volts", 2: "ohms"}

    def __init__(self, comm, logger, **kwargs):
        self._comm = comm
        self._channel = None
        self._logger = logger
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

    # - Output object
    #   -------------
    def _initialize_output(self, output):
        self._logger.info("_initialize_output")

    # - Loop object
    #   -----------
    def _initialize_loop(self, loop):
        self._logger.info("_initialize_loop")
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
        raise RuntimeError("Could not read temperature on channel %s" % channel)

    def _sensor_type(self, channel, type=None, compensation=None):
        """ Read or set input type parameters
            Args: According to the model, use the appropriate args
              type (int): 0 to ?
              compensation (int): 0=off and 1 =on
              example: input.sensor_type(type=3,compensation=1) 
            Returns:
               <type>, <compensation>
        """
        self._logger.info("_sensor_type")
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
        self._logger.info("setpoint")
        if value is None:
            return float(self.send_cmd("SETP?", channel=channel))
        else:
            self.send_cmd("SETP", value, channel=channel)

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
        self._logger.info("ramp_rate")
        if value is None:
            r = self.send_cmd("RAMP?", channel=channel).split(",")
            state = "ON" if int(r[0]) == 1 else "OFF"
            rate_value = float(r[1])
            return {"state": state, "rate": rate_value}

        if value < 0.1 or value > 100:
            raise ValueError("Ramp value %s is out of bounds [0.1,100]" % value)
        self.send_cmd("RAMP", 0, value, channel=channel)

    def ramp(self, channel, sp, rate):
        """Change temperature to a set value at a controlled ramp rate
            Args:
              channel (int): output channel. Valid entries: 1 or 2
              rate (float): ramp rate [K/min], values 0.1 to 100 with 0.1 resolution 
              sp (float): target setpoint [K]
            Returns:
              None
        """
        self._logger.info("ramp")
        self._logger.debug("ramp(): SP=%r, RR=%r" % (sp, rate))
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
        self._logger.info("ramp_status")
        self._logger.debug("ramp_status(): channel = %r" % channel)
        ramp_stat = self.send_cmd("RAMPST?", channel=channel)
        self._logger.debug("ramp_status(): ramp_status = %r" % ramp_stat)
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
        self._logger.info("pid")
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
        self._logger.info("_model")
        model = self.send_cmd("*IDN?").split(",")[1]
        return int(model[5:8])

    # CUSTOM INPUT-object related method(s)
    # -------------------------------------
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

        _lakeshore = LakeShore335(
            comm_type, url, logger, extra_param=extra_param, eos=eos
        )

        model = _lakeshore._model()

        if model != 335:
            raise ValueError(
                "Error, the Lakeshore model is {0}. It should be 335.".format(model)
            )
        # else:
        #     print("\t\t\tthe model is {0}".format(model))

        LakeshoreBase.__init__(self, _lakeshore, config, *args)
