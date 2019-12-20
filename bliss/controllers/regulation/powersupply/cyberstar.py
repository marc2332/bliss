# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
- class: Cyberstar
  module: regulation.powersupply.cyberstar
  plugin: bliss
  name: cyberstar
  timeout: 3
  serial:
     url: ser2net://lid00limace:28000/dev/ttyS0

-
    class: CyberstarOutput
    module: regulation.powersupply.cyberstar
    name: cyberstar_hv
    device: $cyberstar
    unit: volt
    low_limit: 250            # <== minimum device value [unit]
    high_limit: 1250          # <== maximum device value [unit]
    ramprate: 0.0             # <== ramprate to reach the output value [unit/s].
    mode: absolute
    module_id: 0              # <== identify the module in the serial line
    channel: hv               # <== the high voltage output

-
    class: CyberstarOutput
    module: regulation.powersupply.cyberstar
    name: cyberstar_sca_low
    device: $cyberstar
    unit: volt
    low_limit: 0            # <== minimum device value [unit]
    high_limit: 10          # <== maximum device value [unit]
    ramprate: 0.0           # <== ramprate to reach the output value [unit/s].
    mode: absolute
    module_id: 0
    channel: sca_low        # <== the SCA low level voltage output

-
    class:  CyberstarOutput   # an ExternalOutput
    module: regulation.powersupply.cyberstar
    name: cyberstar_sca_up
    device: $cyberstar
    unit: volt
    low_limit: 0             # <== minimum device value [unit]
    high_limit: 10           # <== maximum device value [unit]
    ramprate: 0.0            # <== ramprate to reach the output value [unit/s].
    mode: absolute
    module_id: 0
    channel: sca_up          # <== the SCA low level voltage output
"""

import time
import enum
from bliss.comm.util import get_comm
from bliss.common.logtools import log_debug, log_info
from bliss.common.regulation import lazy_init, ExternalOutput


class CyberstarOutput(ExternalOutput):
    """ Interface to handle Cyberstar module as a regulation Output """

    @enum.unique
    class Remote(enum.IntEnum):
        OFF = 0
        ON = 1

    def __init__(self, name, config):
        super().__init__(config)
        self.module_id = config["module_id"]
        self.channel = config["channel"]

    @lazy_init
    def __info__(self):
        return "\n".join(self.device.show(self.module_id))

    @lazy_init
    def __str__(self):
        # this is for the mapping: it needs a representation of instance
        return super().__repr__()

    @lazy_init
    def state(self):
        """ returns the output device state """

        log_debug(self, "PowersupplyOutput:state")
        return "READY"

    @lazy_init
    def clear(self):
        """ Reset the apprropriate module. """
        log_debug(self, "PowersupplyOutput:clear")
        self.device._clear(self.module_id)

    @lazy_init
    def read(self):
        """ returns the output device value (in output unit) """

        log_debug(self, "CyberstarOutput:read")
        return self.device.get_value(self.module_id, self.channel)

    @lazy_init
    def _set_value(self, value):
        """ Set the value for the output. Value is expressed in output unit """
        log_debug(self, "CyberstarOutput:_set_value %s" % value)
        self.device.set_value(self.module_id, self.channel, value)

    @lazy_init
    def get_remote(self):
        """ Get the remote controle """
        log_info(self, "CyberstarOutput:get_remote")
        return self.device.get_param_value(self.module_id, "remote")

    @lazy_init
    def set_remote(self, value):
        """ Set the remote control to ON or OFF
            Args:
               channel (int): module address
               value (str): ON or OFF
        """
        log_info(self, "CyberstarOutput:set_remote")
        value = self.Remote(value).name
        self.device.set_param_value(self.module_id, "remote", value)

    @property
    @lazy_init
    def gain(self):
        log_debug(self, "CyberstarOutput:@gain")
        return self.device.get_param_value(self.module_id, "gain")

    @gain.setter
    @lazy_init
    def gain(self, value):
        log_debug(self, "CyberstarOutput:@gain.setter %s" % value)
        self.device.set_param_value(self.module_id, "gain", value)

    @property
    @lazy_init
    def peaking_time(self):
        log_debug(self, "CyberstarOutput:@peaking_time")
        return int(self.device.get_param_value(self.module_id, "peaking_time"))

    @peaking_time.setter
    @lazy_init
    def peaking_time(self, value):
        log_debug(self, "CyberstarOutput:@peaking_time.setter %s" % value)
        self.device.set_param_value(self.module_id, "peaking_time", value)

    @property
    @lazy_init
    def delay(self):
        log_debug(self, "CyberstarOutput:getter delay")
        return int(self.device.get_param_value(self.module_id, "delay"))

    @delay.setter
    @lazy_init
    def delay(self, value):
        log_debug(self, "CyberstarOutput:setter delay %s" % value)
        self.device.set_param_value(self.module_id, "delay", value)


class Cyberstar:
    def __init__(self, name, config):
        self._comm = get_comm(config)
        self._channel = None
        log_info(self, "Cyberstar:__init__")

        self.channel_names = {
            "hv": ":SOUR:VOLT",
            "sca_low": ":SENS:SCA:LOW",
            "sca_up": ":SENS:SCA:UPP",
            "gain": ":INP:GAIN",
        }
        self.params = {
            "gain": ":INP:GAIN",
            "peaking_time": ":SENS:PKT",
            "delay": ":TRIG:ECO",
            "remote": ":SYST:COMM:REM",
        }

    def show(self, module_id):
        """ Display all main parameters and values of the cyberstar module
            Prints:
              device ID, communication information,
              high voltage value, SCA low voltage, SCA high voltage,
              peaking time and gain
        """
        info_list = []
        log_info(self, "show")
        info_list.append(f"Module {module_id} using {self._comm}:")
        hv = str(self.get_value(module_id, "hv"))
        info_list.append(f"High voltage = {hv}V")
        sca_low = str(self.get_value(module_id, "sca_low"))
        info_list.append(f"SCA low level = {sca_low}V")
        sca_up = str(self.get_value(module_id, "sca_up"))
        info_list.append(f"SCA up = {sca_up}V")
        gain = str(self.get_param_value(module_id, "gain"))
        info_list.append(f"Gain = {gain}%")
        pkt = str(int(self.get_param_value(module_id, "peaking_time")))
        info_list.append(f"Peaking time = {pkt}ns")
        delay = str(int(self.get_param_value(module_id, "delay")))
        info_list.append(f"Delay = {delay}s")
        remote = str(self.get_param_value(module_id, "remote"))
        info_list.append(f"Switch forced remote control is {remote}")

        return info_list

    def _clear(self, module_id):
        """ Reset the module_id in the serial chain """
        self.send_cmd("*RST", module_id)

    def get_value(self, module_id, channel):
        """ Read the current value on given channel of given cyberstar module
            Returns:
              value (float): The current value
        """
        log_info(self, "Cyberstar:%s:%s:get_value" % (module_id, channel))
        return float(self.send_cmd("%s?" % self.channel_names[channel], module_id))

    def set_value(self, module_id, channel, value):
        """ Set the current value on given channel of given cyberstar module
        """
        log_info(self, "Cyberstar:%s:%s:set_value %s" % (module_id, channel, value))
        self.send_cmd(self.channel_names[channel], module_id, arg=value)

    def get_param_value(self, module_id, param):
        """ Read the current parameter value of given cyberstar module
            Returns:
              value (float): The current value
        """
        log_info(self, "Cyberstar:%s:%s:get_param_value" % (module_id, param))
        if param is "remote":
            return int(self.send_cmd("%s?" % self.params[param], module_id))
        else:
            return float(self.send_cmd("%s?" % self.params[param], module_id))

    def set_param_value(self, module_id, param, value):
        """ Set the current parameter value of given cyberstar module
        """
        log_info(self, "Cyberstar:%s:%s:set_param_value %s" % (module_id, param, value))
        self.send_cmd(self.params[param], module_id, arg=value)

    # 'Internal' COMMUNICATION method
    # -------------------------------
    # @_send_limit
    def send_cmd(self, command, module_id, arg=None):
        """ Send a command to the controller
            Args:
              command (str): The command string
              module_id (int): module number in the daisy chain
              args: Possible argument number
            Returns:
              Answer from the controller if ? in the command
        """
        log_info(self, "send_cmd")
        with self._comm.lock:
            if arg is None:
                command = command
            else:
                arg = str(arg)
                command = f"{command} {arg}"

            if "RST" in command:
                command = f"{command}{module_id}"
            else:
                cIndex = command.find(":", 1)
                command = command[0:cIndex] + str(module_id) + command[cIndex:]
            self._comm.write(command.encode() + "\n".encode())
            time.sleep(0.1)
            ack = self._comm.read()
            if ack != b"\x06":
                error_msg = f"Timeout with {self._comm} and command {command}"
                print(error_msg)
                self._comm.flush()
            if "?" in command:
                time.sleep(0.1)
                asw = self._comm.readline(eol="\n")
                asw = asw.decode()
                return asw

    # Raw COMMUNICATION methods
    # -------------------------
    def wraw(self, string):
        """ Write a string to the controller
            Args:
              string The complete raw string to write
                     Normaly will use it to set a/some parameter/s in
                     the controller.
            Returns:
              None
        """
        log_info(self, "wraw")
        log_debug(self, "command to send = {0}".format(string))
        with self._comm.lock:
            self._comm.write(string.encode())

    def rraw(self):
        """ Read a string from the controller
            Returns:
              response from the controller
        """
        log_info(self, "rraw")
        with self._comm.lock:
            asw = self._comm.raw_read()
            asw = asw.decode()
            log_debug(self, "raw answer = {0}".format(asw))
            return asw

    def wrraw(self, string):
        """ Write a string to the controller and then reading answer back
            Args:
              string The complete raw string to write
            Returns:
              response from the controller
        """
        log_info(self, "wrraw")
        log_debug(self, "command to send = {0}".format(string))
        with self._comm.lock:
            self._comm.write(string.encode())
            time.sleep(0.3)
            asw = self._comm.raw_read()
            asw = asw.decode()
            log_debug(self, "raw answer = {0}".format(asw))
            return asw
