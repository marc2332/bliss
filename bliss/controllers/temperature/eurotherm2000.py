# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Eurothers 2000 Series Cryostream, acessible via serial line

yml configuration example:
plugin: temperature
class: eurotherm2000
serial:
    url: rfc2217://lid30b2:28003       #serial line name
outputs:
    -
      name: heatblower
      type: sp
      unit: deg
      low_limit: 10
      high_limit: 30
      deadband: 0.1
      tango_server: euro2400_ss

inputs:
    -
      name: T1
      type: pv
      #tango_server: euro2400_ss
"""
import logging
from collections import namedtuple
from tabulate import tabulate

from bliss.comm import modbus
from bliss.comm.exceptions import CommunicationError

from warnings import warn

""" TempController import """
from bliss.controllers.temp import Controller
from bliss.common.temperature import Input, Output
from bliss.common.utils import (
    object_attribute_type_get,
    object_attribute_type_set,
    object_attribute_get,
    object_method,
)
from bliss import global_map
from bliss.common.logtools import *


class Eurotherm2000Error(CommunicationError):
    pass


class Eurotherm2000Device:
    RampRateUnits = ("sec", "min", "hour")
    SensorTypes = (
        "J",
        "K",
        "L",
        "R",
        "B",
        "N",
        "T",
        "S",
        "PL 2",
        "Custom (factory)",
        "RTD",
        "Linear mV (+/- 100mV)",
        "Linear V (0-10V)",
        "Linear mA",
        "Square root V",
        "Square root mA",
        "Custom mV",
        "Custom V",
        "Custom mA",
    )
    StatusFields = (
        "Alarm_1",
        "Alarm_2",
        "Alarm_3",
        "Alarm_4",
        "Manual_mode",
        "Sensor_broken",
        "Open_loop",
        "Heater_fail",
        "Auto_tune_active",
        "Ramp_program_complete",
        "PV_out_of_range",
        "DC_control_module_fault",
        "Programmer_Segment_Sync_running",
        "Remote_input_sensor_broken",
    )
    EuroStatus = namedtuple("EuroStatus", StatusFields)

    def __init__(self, modbus_address, serialport):
        """ RS232 settings: 9600 baud, 8 bits, no parity, 1 stop bit
        """
        global_map.register(
            self, parents_list=["comms"]
        )  # instantiating once to allow the debug
        log_debug(
            self,
            f"Eurotherm2000: __init__(address {modbus_address}, port {serialport})",
        )
        self.comm = modbus.Modbus_RTU(
            modbus_address, serialport, baudrate=9600, eol="\r"
        )
        global_map.register(
            self, parents_list=["comms"], children_list=[self.comm]
        )  # twice to attach child

        self._model = None
        self._ident = None
        self._version = None
        self._ramping = None

    def __exit__(self, etype, evalue, etb):
        self.comm._serial.close()

    def close(self):
        """Close the serial line
        """
        log_debug(self, "close()")
        self.comm._serial.close()

    def flush(self):
        self.comm._serial.flush()

    def read_register(self, address):
        return self.comm.read_holding_registers(address, "H")

    def write_register(self, address, value):
        self.comm.write_registers(address, "H", value)

    def read_float_register(self, address):
        """ reading floating point value from IEEE address zone"""
        return self.comm.read_holding_registers(2 * address + 0x8000, "f")

    def write_float_register(self, address, value):
        """ writing floating point value from IEEE address zone"""
        self.comm.write_register(2 * address + 0x8000, "f", value)

    def read_time_register(self, address):
        """ reading time (in sec) from IEEE address zone (precision of ms) """
        value = self.comm.read_holding_registers(2 * address + 0x8000, "i")
        value /= 1000.0
        return value

    def write_time_register(self, address, value):
        """ writing time (in sec) from IEEE address zone (precision of ms) """
        valset = int(1000.0 * value)
        self.comm.write_register(2 * address + 0x8000, "i", valset)

    def initialize(self):
        """Get the model, the firmware version and the resolution of the module.
        """
        log_debug(self, "initialize")
        self.flush()
        self._read_identification()
        self._read_version()
        log_info(
            self,
            f"Eurotherm2000 {self._ident:02X} (firmware: {self._version:02X}) (comm: {self.comm!s})",
        )

    def _read_identification(self):
        """ Ident contains a number in hex format which will identify
        your controller in format >ABCD (hex):
        A = 2 (series 2000) B = Range number  C = Size       D = Type
          2: 2200           3: 1/32 din    0: PID/on-off
          4: 2400           6: 1/16 din    2: VP
          8: 1/8 din
          4: 1/4 din
        """
        ident = self.read_register(122)
        if ident >> 12 == 2:
            log_debug(self, "Connected to Eurotherm model %x" % ident)
            self._ident = ident
            self._model = (ident & 0xf00) >> 8
        else:
            raise Eurotherm2000Error(
                "Device with identification number %x is not an Eurotherm series 2000 device and cannot be controlled"
                % (ident)
            )

    @property
    def model(self):
        return "{0:x}".format(self._ident)

    def _read_version(self):
        """There is the possibility to config the 2400 series with floating
        point or integer values. Tag address 525 tells you how many digits
        appear after the radix character.
        BUT !!!!! there was one controller (firmware version 0x0411) on which
        this cell`s contents has no influence on the modbus readings.
        The sample environment controllers have version 0x0461.
        """

        self._version = self.read_register(107)
        log_info(
            self,
            "Firmware V%x.%x"
            % ((self._version & 0xff00) >> 8, (self._version & 0x00ff)),
        )

    @property
    def version(self):
        return self._version

    def display_resolution(self):
        """ Get the display resolution and the number of decimal points value.
            Raises:
              Eurotherm2000Error
        """
        if self._model == 4:  # 2400 series
            # 0:full, 1:integer or the oposite
            resol = self.read_register(12550)
            # 0:0, #1:1, 2:2
            decimal = self.read_register(525)
        elif self._model == 7:  # 2700 series
            # 0:full, 1:integer
            resol = self.read_register(12275)
            # 0:0, #1:1, 2:2
            decimal = self.read_register(5076)
        else:
            raise Eurotherm2000Error("Unsuported model")

        if resol == 0:
            scale = pow(10, decimal)
            log_debug(self, "Display Resolution full, decimal %d" % decimal)
        else:
            scale = 1
            log_debug(self, "Display Resolution integer")
        return scale

    @property
    def sp(self):
        try:
            value = self.read_float_register(2)
            return value
        except:
            raise Eurotherm2000Error("Cannot read the sp value")

    @sp.setter
    def sp(self, value):
        self.write_float_register(2, value)
        self._set_point = value

    @property
    def wsp(self):
        try:
            value = self.read_float_register(5)
            return value
        except TypeError:
            raise Eurotherm2000Error("Cannot read the wsp value")

    @property
    def pv(self):
        try:
            value = self.read_float_register(1)
            return value
        except TypeError:
            raise Eurotherm2000Error("Cannot read the pv value")

    @property
    def op(self):
        try:
            value = self.read_float_register(3)
            return value
        except TypeError:
            raise Eurotherm2000Error("Cannot read the op value")

    @property
    def ramprate(self):
        """ Read the current ramprate
            Returns:
              (float): current ramprate [degC/unit]
            Raises:
              Eurotherm2000Error
        """
        try:
            value = self.read_float_register(35)
            return value
        except TypeError:
            raise Eurotherm2000Error("Cannot read the ramp rate")

    @ramprate.setter
    def ramprate(self, value):
        self.write_float_register(35, value)
        if value:
            self._ramping = True
        else:
            self._ramping = False

    @property
    def ramprate_units(self):
        """ Get the ramprate time unit.
            Returns:
              (str): Time unit - 'sec', 'min' or 'hour'
        """
        value = self.read_register(531)
        return self.RampRateUnits[value]

    @ramprate_units.setter
    def ramprate_units(self, value):
        """ Set the ramprate time unit
            Args:
              value (str): Time unit - 'sec', 'min' or 'hour'
        """
        if value not in self.RampRateUnits:
            raise ValueError(
                "Invalid eurotherm ramp rate units. Should be in {}".format(
                    self.RampRateUnits
                )
            )
        self.write_register(531, self.RampRateUnits.index(value))

    @property
    def pid(self):
        return (self.P, self.I, self.D)

    @property
    def P(self):
        return self.read_float_register(6)

    @property
    def I(self):
        return self.read_time_register(8)

    @property
    def D(self):
        return self.read_time_register(9)

    @property
    def sensor_type(self):
        sensor = self.read_register(12290)
        return self.SensorTypes[sensor]

    def prog_status(self):
        """Read the setpoint status
           Returns:
              (int): 0 - ready
                     1 - wsp != sp so running
                     2 - busy, a program is running
        """
        if self._model == 4 and self.read_register(23) != 1:
            return 2
        else:
            if self.wsp != self.sp:
                return 1
        return 0

    @property
    def status(self):
        value = self.read_register(75)
        status = self.EuroStatus(
            *[bool(value & (1 << i)) for i in range(len(self.EuroStatus._fields))]
        )
        return status

    def show_status(self):
        status = self.status
        rows = [(field, str(getattr(status, field))) for field in status._fields]
        heads = ["EuroStatus", "Value"]
        print(tabulate(rows, headers=heads))


class eurotherm2000(Controller):
    InputTypes = ("pv", "wsp", "op")
    OutputTypes = ("sp",)

    def __init__(self, config, *args):
        """
        controller configuration
        """
        try:
            port = config["serial"]["url"]
        except KeyError:
            port = config["port"]
            warn("'port' is deprecated. Use 'serial' instead", DeprecationWarning)
        self.device = Eurotherm2000Device(1, port)
        Controller.__init__(self, config, *args)
        log_debug(self, "eurotherm2000:__init__ (%s %s)" % (config, args))
        self._set_point = None

    def initialize(self):
        log_debug(self, "initialize")
        self.device.initialize()

    def initialize_input(self, tinput):
        log_debug(self, "initialize_input")
        if "type" not in tinput.config:
            tinput.config["type"] = "pv"
        else:
            if tinput.config["type"] not in self.InputTypes:
                raise ValueError(
                    "Invalid input type [{0}]. Should one of {1}.".format(
                        tinput.config["type"], self.InputTypes
                    )
                )

    def initialize_output(self, toutput):
        log_debug(self, "initialize_output")
        if "type" not in toutput.config:
            toutput.config["type"] = "sp"
        else:
            if toutput.config["type"] not in self.OutputTypes:
                raise ValueError(
                    "Invalid input type [{0}]. Should one of {1}.".format(
                        toutput.config["type"], self.OutputTypes
                    )
                )

    def set(self, toutput, sp):
        """Go to the desired temperature as quickly as possible.
           Args:
              toutput (object): Output class type object
              sp (float): final temperature [degC]
        """
        log_debug(self, "set() %r" % sp)

        # Ramprate should be 0 in order to get there ASAP
        self.device.ramprate = 0
        self.device.sp = sp
        self._set_point = sp

    def get_setpoint(self, toutput):
        """Read the as quick as possible setpoint
           Args:
              toutput (object): Output class type object
           Returns:
              (float): current temperature setpoint
        """
        log_debug(self, "get_setpoint")
        return self._set_point

    def setpoint_abort(self, touput):
        if self.device.prog_status() == 2:
            raise Eurotherm2000Error(
                "Cannot abort, an internal program is running; RESET device first"
            )

        self.set(touput, self.device.pv)

    def read_output(self, toutput):
        """Read the current temperature
           Args:
              toutput (object): Output class type object
           Returns:
              (float): current temperature [degC]
        """
        log_info(self, "read_output %s" % toutput.config["type"])
        typ = toutput.config["type"]
        if typ is "wsp":
            return self.device.wsp
        else:
            return self.device.sp

    def start_ramp(self, toutput, sp, **kwargs):
        """Start ramping to setpoint
           Args:
              toutput (object): Output class type object
              sp (float): The setpoint temperature [degC]
           Kwargs:
              rate (int): The ramp rate [degC/unit]
        """
        rate = kwargs.get("rate", None)
        if rate is None:
            rate = self.device.ramprate
            if not rate:
                raise Eurotherm2000Error("Cannot start ramping, ramp rate not set")
        else:
            self.device.ramprate = rate
        self.device.sp = sp

    def set_ramprate(self, toutput, rate):
        """Set the ramp rate
           Args:
              toutput (object): Output class type object
              rate (float): The ramp rate [degC/unit]
       """
        self.device.ramprate = rate

    def read_ramprate(self, toutput):
        """Read the ramp rate
           Returns:
              (float): Previously set ramp rate  [degC/unit]
        """
        return self.device.ramprate

    def state_output(self, toutput):
        """Read the state parameters of the controller
        Args:
           toutput(object):  Output class type object
        Returns:
           (string): This is one of READY/RUNNING/ALARM
        """
        return self.control_status()

    def control_status(self):
        status = self.device.status
        if (
            status.Heater_fail
            or status.Sensor_broken
            or status.PV_out_of_range
            or status.DC_control_module_fault
        ):
            return "FAULT"
        if status.Alarm_1 or status.Alarm_2 or status.Alarm_3 or status.Alarm_4:
            return "ALARM"
        if not status.Ramp_program_complete:
            return "RUNNING"
        return "READY"

    def read_input(self, tinput):
        log_debug(self, "read_input")
        typ = str(tinput.config["type"])
        if typ == "op":
            return self.device.op
        elif typ == "sp":
            return self.device.sp
        elif typ == "wsp":
            return self.device.wsp
        return self.device.pv

    def state_input(self, tinput):
        """Read the state parameters of the controller
           Args:
              tinput(object):  Input class type object
           Returns:
              (string): This is one of READY/RUNNING/ALARM
        """
        return self.control_status()

    @object_attribute_type_get(type_info=("str"), type=Output)
    def get_ramprate_unit(self, toutput):
        return self.device.ramprate_units

    @object_attribute_type_set(type_info=("str"), type=Output)
    def set_ramprate_unit(self, toutput, value):
        self.device.ramprate_units = value

    @object_attribute_type_get(type_info=("str"), type=Input)
    def sensor_type(self, tinput):
        return self.device.sensor_type

    @object_method()
    def status(self, tobj):
        self.device.show_status()

    @object_attribute_get()
    def get_device(self, tobj):
        return self.device

    @object_attribute_get(type_info=("str"))
    def get_model(self, tobj):
        return self.device.model
