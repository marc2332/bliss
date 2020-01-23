# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Linkam Controllers

Linkam TMS94, acessible via Serial line (RS232)

yml configuration example:

- class: LinkamTms94
  module: temperature.linkam.linkam_TMS94_T95
  plugin: regulation
  name: linkamtms94
  timeout: 3
  serial:
    url: ser2net://lid15a1:28000/dev/ttyRP21
    #baudrate: 19200       # <-- optional

  inputs:
    - name: linkam1_in

  outputs:
    - name: linkam1_out
      low_limit: -196.0     # <-- minimum device value [Celsius]
      high_limit:  600.0    # <-- maximum device value [Celsius]

  ctrl_loops:
    - name: linkam1_loop
      input: $linkam1_in
      output: $linkam1_out
"""

import time
import enum

from bliss import global_map
from bliss.comm.util import get_comm
from bliss.common.logtools import log_info, log_debug
from bliss.controllers.regulator import Controller

# --- patch the Input, Output and Loop classes with their Linkam equivalent -----------
from bliss.controllers.regulation.temperature.linkam.linkam import LinkamInput as Input
from bliss.controllers.regulation.temperature.linkam.linkam import (
    LinkamOutput as Output
)
from bliss.controllers.regulation.temperature.linkam.linkam import LinkamLoop as Loop


_last_call = time.time()
# limit number of commands per second
def _send_limit(func):
    def f(*args, **kwargs):
        global _last_call
        delta_t = time.time() - _last_call
        if delta_t <= 0.30:
            time.sleep(0.30 - delta_t)
        try:
            return func(*args, **kwargs)
        finally:
            _last_call = time.time()

    return f


class LinkamTms94(Controller):
    """
    Linkam TMS94 controller class
    """

    SB1 = {
        1: "Stopped",
        16: "Heating",
        32: "Cooling",
        48: "Holding at limit",
        64: "Holding at the setpoint temperature",
        80: "Holding at current temperature",
    }
    EB1 = {
        0: "No error",
        1: "Cooling rate too fast",
        2: "Stage not connected or sensor is open circuit",
        4: "Current protection has been set due to overload",
        32: "Problems with RS-232 data tansmission",
    }

    @enum.unique
    class PumpMode(enum.IntEnum):
        NOT_YET_DEFINED = -1
        MANUAL = 0
        AUTOMATIC = 1

    def __init__(self, config):

        if "baudrate" in config["serial"]:
            _baudrate = config["serial"]["baudrate"]
        else:
            _baudrate = 19200

        self._comm = get_comm(
            config, baudrate=_baudrate, parity="N", bytesize=8, stopbits=1
        )

        self._pump_auto = None

        self._ramp_rate = float("NAN")
        self._setpoint = float("NAN")
        self._low_limit = float("NAN")
        self._high_limit = float("NAN")

        super().__init__(config)

        global_map.register(self._comm, parents_list=[self, "comms"])

    # ------ init methods ------------------------

    def initialize_controller(self):
        """ 
        Initializes the controller (including hardware).
        """
        log_info(self, "initialize_controller")

        self.clear()

    def initialize_input(self, tinput):
        """
        Initializes an Input class type object

        Args:
           tinput:  Input class type object          
        """
        log_info(self, "initialize_input")

    def initialize_output(self, toutput):
        """
        Initializes an Output class type object

        Args:
           toutput:  Output class type object          
        """
        log_info(self, "initialize_output")

    def initialize_loop(self, tloop):
        """
        Initializes a Loop class type object

        Args:
           tloop:  Loop class type object          
        """
        log_info(self, "initialize_loop")
        self._low_limit = tloop.output.config["low_limit"]
        self._high_limit = tloop.output.config["high_limit"]

    # ------ get methods ------------------------

    def read_input(self, tinput):
        """ Read the current temperature """
        log_info(self, "read_input")
        return self._get_temperature_info()["temperature"]

    def read_output(self, toutput):
        """
        Reads an Output class type object
        Raises NotImplementedError if not defined by inheriting class

        Args:
           toutput:  Output class type object 

        Returns:
           read value (in output unit)         
        """
        log_info(self, "read_output")

        # no cmd to return the current output value
        return float("NAN")

    def state_input(self, tinput):
        """
        Return a string representing state of an Input object.
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tinput:  Input class type object

        Returns:
           object state string. This is one of READY/RUNNING/ALARM/FAULT
        """
        log_info(self, "Controller:state_input: %s" % (tinput))
        return "\n".join(self.state())

    def state_output(self, toutput):
        """
        Return a string representing state of an Output object.
        Raises NotImplementedError if not defined by inheriting class

        Args:
           toutput:  Output class type object

        Returns:
           object state string. This is one of READY/RUNNING/ALARM/FAULT
        """
        log_info(self, "Controller:state_output: %s" % (toutput))
        return "\n".join(self.state())

    # ------ PID methods ------------------------

    def set_kp(self, tloop, kp):
        """
        Set the PID P value
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object 
           kp: the kp value
        """
        log_info(self, "Controller:set_kp: %s %s" % (tloop, kp))
        print("The PID kp coefficient cannot be set for this controller")

    def get_kp(self, tloop):
        """
        Get the PID P value
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object 
        
        Returns:
           kp value
        """
        log_info(self, "Controller:get_kp: %s" % (tloop))
        raise NotImplementedError

    def set_ki(self, tloop, ki):
        """
        Set the PID I value
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object 
           ki: the ki value
        """
        log_info(self, "Controller:set_ki: %s %s" % (tloop, ki))
        print("The PID ki coefficient cannot be set for this controller")

    def get_ki(self, tloop):
        """
        Get the PID I value
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object 
        
        Returns:
           ki value
        """
        log_info(self, "Controller:get_ki: %s" % (tloop))
        raise NotImplementedError

    def set_kd(self, tloop, kd):
        """
        Set the PID D value
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object 
           kd: the kd value
        """
        log_info(self, "Controller:set_kd: %s %s" % (tloop, kd))
        print("The PID kd coefficient cannot be set for this controller")

    def get_kd(self, tloop):
        """
        Reads the PID D value
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Output class type object 
        
        Returns:
           kd value
        """
        log_info(self, "Controller:get_kd: %s" % (tloop))
        raise NotImplementedError

    def start_regulation(self, tloop):
        """
        Starts the regulation process.
        It must NOT start the ramp, use 'start_ramp' to do so.
        Raises NotImplementedError if not defined by inheriting class

        Args: 
           tloop:  Loop class type object
        """
        log_info(self, "Controller:start_regulation: %s" % (tloop))
        self._set_loop_on(tloop)

    def stop_regulation(self, tloop):
        """
        Stops the regulation process.
        It must NOT stop the ramp, use 'stop_ramp' to do so.
        Raises NotImplementedError if not defined by inheriting class

        Args: 
           tloop:  Loop class type object
        """
        log_info(self, "Controller:stop_regulation: %s" % (tloop))
        self._set_loop_off(tloop)

    # ------ setpoint methods ------------------------

    def set_setpoint(self, tloop, sp, **kwargs):
        """
        Set the current setpoint (target value).
        It must NOT start the PID process, use 'start_regulation' to do so.
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object
           sp:     setpoint (in tloop.input unit)
           **kwargs: auxilliary arguments
        """
        log_info(self, "Controller:set_setpoint: %s %s" % (tloop, sp))

        if sp < self._low_limit or sp > self._high_limit:
            raise ValueError(
                f"Setpoint value {sp} is out of bounds [{self._low_limit},{self._high_limit}]"
            )

        cmd = "%4d" % int(round(sp * 10))
        cmd = cmd.strip(" ")
        self.send_cmd("L1", cmd)
        self._setpoint = int(cmd) / 10.  # or sp ???

    def get_setpoint(self, tloop):
        """
        Get the current setpoint (target value)
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object

        Returns:
           (float) setpoint value (in tloop.input unit).
        """
        log_info(self, "Controller:get_setpoint: %s" % (tloop))
        return self._setpoint

    # ------ setpoint ramping methods ------------------------

    def start_ramp(self, tloop, sp, **kwargs):
        """
        Start ramping to a setpoint
        It must NOT start the PID process, use 'start_regulation' to do so.
        Raises NotImplementedError if not defined by inheriting class

        Replace 'Raises NotImplementedError' by 'pass' if the controller has ramping but doesn't have a method to explicitly starts the ramping.
        Else if this function returns 'NotImplementedError', then the Loop 'tloop' will use a SoftRamp instead.

        Args:
           tloop:  Loop class type object
           sp:       setpoint (in tloop.input unit)
           **kwargs: auxilliary arguments
        """
        log_info(self, "Controller:start_ramp: %s %s" % (tloop, sp))

        self.set_setpoint(tloop, sp)

    def stop_ramp(self, tloop):
        """
        Stop the current ramping to a setpoint
        It must NOT stop the PID process, use 'stop_regulation' to do so.
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object
        """
        log_info(self, "Controller:stop_ramp: %s" % (tloop))

    def is_ramping(self, tloop):
        """
        Get the ramping status.
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object

        Returns:
           (bool) True if ramping, else False.
        """
        log_info(self, "Controller:is_ramping: %s" % (tloop))
        status = self._get_temperature_info()["status"]
        # Heating or cooling
        if status == self.SB1[16] or status == self.SB1[32]:
            return True
        else:
            return False

    def set_ramprate(self, tloop, rate):
        """
        Set the ramp rate  for heating or cooling

                Args:
           tloop:  Loop class type object
           rate:   ramp rate (in input unit per second)
        """
        log_info(self, "Controller:set_ramprate: %s %s" % (tloop, rate))

        if rate <= 0 or rate > 32:
            raise ValueError("Ramp value %s is out of bounds [0,32]" % rate)

        val = "%4d" % int(round(rate * 100))
        val = val.strip(" ")
        self.send_cmd("R1", val)
        self._ramp_rate = int(val) / 100.  # or rate ???

    def get_ramprate(self, tloop):
        """
        Get the ramp rate for heating or cooling

        Args:
           tloop:  Loop class type object
        
        Returns:
           ramp rate (in input unit per second)
        """
        log_info(self, "Controller:get_ramprate: %s" % (tloop))
        return self._ramp_rate

    # ------ raw methods (optional) ----------------

    def wraw(self, string):
        """ Write a string to the controller
            Args:
              string The complete raw string to write (except eol)
                     Normaly will use it to set a/some parameter/s in
                     the controller.
            Returns:
              None
        """
        # log_info(self, "wraw")
        # log_debug(self, "command to send = {0}".format(string))
        # self._comm.write(string.encode())
        raise NotImplementedError

    def rraw(self):
        """ Read a string from the controller
            Returns:
              response from the controller
        """
        log_info(self, "rraw")
        # asw = self._comm.raw_read()
        # log_debug(self, "raw answer = {0}".format(asw))
        # return asw
        raise NotImplementedError

    def wrraw(self, string):
        """ Write a string to the controller and then reading answer back
            Args:
              string The complete raw string to write (except eol)
            Returns:
              response from the controller
        """
        log_info(self, "wrraw")
        log_debug(self, "command to send = {0}".format(string))
        # self._comm.write(string.encode())
        # asw = self._comm.raw_read()
        # log_debug(self, "raw answer = {0}".format(asw))
        # return asw
        raise NotImplementedError

    # ------ safety methods (optional) ------------------------------

    def set_in_safe_mode(self, toutput):
        """
        Set the output in a safe mode (like stop heating)
        Raises NotImplementedError if not defined by inheriting class

        Args:
           toutput:  Output class type object 
        """
        log_info(self, "Controller:set_in_safe_mode: %s" % (toutput))
        # set_hold_on ????

    # ----- controller specific methods --------------------------

    @_send_limit
    def send_cmd(self, command, arg=None):
        """ Send a command to the controller
            Args:
              command (str): The command string
              args: Possible variable number of parameters
            Returns:
              Answer from the controller 
        """
        log_info(self, "send_cmd")
        log_debug(self, "command = {0}, arg is {1}".format(command, arg))

        if arg is not None:
            arg = str(arg)
            command = f"{command}{arg}"

        cmd = command + "\r"

        # print(f"=== SEND: {cmd}")
        ans = self._comm.write_readline(cmd.encode(), eol="\r", timeout=3.0)
        # print(f"=== RECV: {ans}")

        return ans

    def clear(self):
        """ Clears the bits in the Status Byte, Standard Event and Operation
            Event Registers. Terminates all pending operations.
            Returns:
                None
        """
        self.send_cmd("B")

    def heat(self):
        log_info(self, "heat")
        raise NotImplementedError("This command is not available for the TMS94 model.")

    def cool(self):
        log_info(self, "cool")
        raise NotImplementedError("This command is not available for the TMS94 model.")

    def state(self):
        """
            Returns:
              List of messages for SB1 and EB1 and PB1.
        """
        log_info(self, "state")
        info = self._get_temperature_info()
        state_list = []
        state_list.append("Status byte (SB1): %s" % (info["status"]))
        state_list.append("Error byte (EB1): %s" % (info["error"]))
        state_list.append(
            "Pump byte (PB1): speed = %s (%s)"
            % (info["pump_speed"], self.get_pump_auto())
        )
        state_list.append(
            f"Current temperature: {info['temperature']}C (setpoint: {self._setpoint}, rate: {self._ramp_rate})"
        )

        return state_list

    def dsc(self):
        """ 
            Return the temperature and the DSC value as an integer.
        """
        log_info(self, "dsc")
        asw = self.send_cmd("D")
        temperature = int(asw[0:4], 16) / 10
        dsc = int(asw[4:8], 16)
        # if the buffer is full then clear it
        # if dsc == 32765:
        #    self.clear()
        return temperature, dsc

    def set_hold_on(self, tloop):
        log_info(self, "set_hold_on")
        self.send_cmd("O")

    def get_pump_auto(self):
        """ Read the pump automatic mode.
            1: Pump mode is automatic
            0: Pump mode is manual
        """
        log_info(self, "get_pump_auto")
        if self._pump_auto is None:
            r = self.PumpMode(-1)
        else:
            r = self.PumpMode(self._pump_auto)
        return r

    def set_pump_auto(self, value):
        """ Set the pump in autaomatic mode 0 or 1
            Args:
              value (int): 1 or 0
        """
        log_info(self, "set_pump_auto")

        if self.PumpMode(value).value == 1:
            self.send_cmd("Pa0")
        else:
            self.send_cmd("Pm0")
        self._pump_auto = self.PumpMode(value).value

    def get_pump_speed(self):
        """ Read the set pump speed. """
        log_info(self, "get_pump_speed")
        return self._get_temperature_info()["pump_speed"]

    def set_pump_speed(self, speed):
        """ Set the pump speed.
            Args:
              value (int): 0 to 30
        """
        log_info(self, "set_pump_speed")
        if speed < 0 or speed > 30:
            raise ValueError("speed {0} is out of range [0,30]".format(speed))
        self.send_cmd("P{0}".format(chr(speed + 48)))

    def _set_loop_on(self, tloop):
        """
            Start heating or colling at the specified rate
            to the specified setpoint.
        """
        log_info(self, "_set_loop_on")
        self.send_cmd("S")

    def _set_loop_off(self, tloop):
        """
            Stop heating or cooling.
        """
        log_info(self, "_set_loop_off")
        self.send_cmd("E")

    def _get_temperature_info(self):
        asw = self.send_cmd("T")
        sb1 = asw[0]
        eb1 = asw[1] - 128
        pb1 = asw[2] - 128 - 96
        temp = int(asw[6:10], 16) / 10
        return {
            "status": self.SB1[sb1],
            "error": self.EB1[eb1],
            "pump_speed": pb1,
            "temperature": temp,
        }


class LinkamT95(LinkamTms94):
    def heat(self):
        log_info(self, "heat")
        self.send_cmd("H")

    def cool(self):
        log_info(self, "cool")
        self.send_cmd("C")
