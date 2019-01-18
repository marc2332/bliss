# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
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
      resolution: full
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

from bliss.comm import modbus
from bliss.comm.exceptions import CommunicationError

from warnings import warn

""" TempController import """
from bliss.controllers.temp import Controller
from bliss.common.temperature import Input, Output
from bliss.common.utils import object_attribute_type_get
from bliss.common.utils import object_attribute_type_set


class Eurotherm2000Error(CommunicationError):
    pass


class Eurotherm2000(object):
    def __init__(self, modbus_address, serialport):
        """RS232 settings: 9600 baud, 8 bits, no parity, 1 stop bit
        """
        self.log = logging.getLogger("Eurotherm2000." + serialport)
        self.log.debug(
            "Eurotherm2000: __init__(address %d, port %s)", modbus_address, serialport
        )
        self.device = modbus.Modbus_RTU(
            modbus_address, serialport, baudrate=9600, eol="\r"
        )
        self.setpointvalue = None
        self._scale = None
        self._model = None
        self._ident = None
        self._ramping = None

    def __exit__(self, etype, evalue, etb):
        self.device._serial.close()

    def close(self):
        """Close the serial line
        """
        self.log.debug("close()")
        self.device._serial.close()

    def initialize(self):
        """Get the model, the firmware version and the resolution of the module.
        """
        self.log.debug("initialize")
        self.identification()
        version = self.firmware()
        self.resolution()
        self.log.info(
            "Eurotherm %x (firmware: %x), connected to serial port: %s",
            self._ident,
            version,
            self.device._serial,
        )

    def identification(self):
        """ Ident contains a number in hex format which will identify
        your controller in format >ABCD (hex):
        A = 2 (series 2000) B = Range number  C = Size       D = Type
          2: 2200           3: 1/32 din    0: PID/on-off
          4: 2400           6: 1/16 din    2: VP
          8: 1/8 din
          4: 1/4 din
        """
        self.device._serial.flush()
        ident = self.device.read_holding_registers(122, "H")
        if ident >> 12 == 2:
            self.log.debug("Connected to Eurotherm model %x" % ident)
            self._ident = ident
            self._model = (ident & 0xf00) >> 8
        else:
            raise Eurotherm2000Error(
                "Device with identification number %x is not an Eurotherm series 2000 device and cannot be controlled"
                % (ident)
            )

    def firmware(self):
        """There is the possibility to config the 2400 series with floating
        point or integer values. Tag address 525 tells you how many digits
        appear after the radix character.
        BUT !!!!! there was one controller (firmware version 0x0411) on which
        this cell`s contents has no influence on the modbus readings.
        The sample environment controllers have version 0x0461.
        """

        version = self.device.read_holding_registers(107, "H")
        self.log.info("Firmware V%x.%x" % ((version & 0xff00) >> 8, (version & 0x00ff)))
        return version

    def resolution(self):
        """ Get the resolution and the number of decimal points value.
            Calculate the scaling factor as their function.
            Raises:
              Eurotherm2000Error
        """
        if self._model == 4:  # 2400 series
            # 0:full, 1:integer or the oposite
            resol = self.device.read_holding_registers(12550, "H")
            # 0:0, #1:1, 2:2
            decimal = self.device.read_holding_registers(525, "H")
        elif self._model == 7:  # 2700 series
            # 0:full, 1:integer
            resol = self.device.read_holding_registers(12275, "H")
            # 0:0, #1:1, 2:2
            decimal = self.device.read_holding_registers(5076, "H")
        else:
            raise Eurotherm2000Error("Unsuported model")

        if resol == 0:
            self._scale = pow(10, decimal)
            self.log.debug("Resolution full, decimal %d" % decimal)
        else:
            self._scale = 1
            self.log.debug("Resolution integer")

    def ramprate_units(self, value=None):
        """ Get/Set the ramprate time unit.
            Args:
              value (str): Time unit - 'sec', 'min' or 'hour'
            Returns:
              (str): Time unit - 'sec', 'min' or 'hour
        """
        units = ("sec", "min", "hour")
        if value in units:
            self.device.write_registers(531, "H", units.index(value))
            return value
        else:
            rate = self.device.read_holding_registers(531, "H")
            return units[rate]

    def setpoint(self, value):
        """ Set the temperature target.
            Args:
              value (float): Desired setpoint [degC]
        """
        self.setpointvalue = value
        value *= self._scale
        self.device.write_registers(2, "H", int(value))

    def get_setpoint(self, address=2):
        if address != 5:  # working setpoint rather than setp
            address = 2
        try:
            value = self.device.read_holding_registers(address, "H")
            value /= float(self._scale)
            if address == 2:
                self.setpointvalue = value
            return value
        except TypeError:
            raise Eurotherm2000Error("Cannot read the setpoint value")

    def pv(self):
        try:
            value = self.device.read_holding_registers(1, "H")
            return value / self._scale
        except TypeError:
            raise Eurotherm2000Error("Cannot read the pv value")

    def op(self):
        try:
            value = self.device.read_holding_registers(3, "H")
            return value / self._scale
        except TypeError:
            raise Eurotherm2000Error("Cannot read the op value")

    def abort(self):
        if self.sp_status() == 2:
            raise Eurotherm2000Error(
                "Cannot abort, an internal program is running; RESET device first"
            )

        self.setpoint(self.pv())

    def set_ramprate(self, value):
        """ Set the ramp rate.
            Args:
              value (float): ramp rate [degC/unit]
        """
        value *= self._scale
        self.device.write_registers(35, "H", int(value))
        self._ramping = False
        if value:
            self._ramping = True

    def get_ramprate(self):
        """ Read the current ramprate
            Returns:
              (float): current ramprate [degC/unit]
            Raises:
              Eurotherm2000Error
        """
        value = self.device.read_holding_registers(35, "H")
        try:
            return float(value / self._scale)
        except TypeError:
            raise Eurotherm2000Error("Cannot read the ramp rate")

    def sp_status(self):
        """Read the setpoint status
           Returns:
              (int): 0 - ready
                     1 - wsp != sp so running
                     2 - busy, a program is running
        """
        if self._model == 4 and self.device.read_holding_registers(23, "H") != 1:
            return 2
        else:
            sp = self.get_setpoint(2)
            wsp = self.get_setpoint(5)
            if sp is not wsp:
                return 1
        return 0

    def update_cmd(self):
        return self.sp_status()

    def _fast_status(self):
        """Read the fast status
           Returns:
              (int): current status byte
        """
        _status = [
            "Alarm 1",
            "Alarm 2",
            "Alarm 3",
            "Alarm 4",
            "Manual mode",
            "Sensor broken",
            "Open loop",
            "Heater fail",
            "Auto tune active",
            "Ramp program complete",
            "PV out of range",
            "DC control module fault",
            "Programmer Segment Sync running",
            "Remote input sensor break",
        ]
        value = self.device.read_holding_registers(74, "H")  # Fast Status Byte
        if value:
            for stat in _status:
                if pow(2, _status.index(stat)) & value:
                    print(stat)
            return value
        return 0

    def _output_status(self):
        """Read the output status
           Returns:
              (int): current status byte
        """
        value = self.device.read_holding_registers(75, "H")
        if not (value & 0x200):
            return 2
        return 0

    def device_status(self):
        status = self._fast_status()
        if self._ramping:
            status = status or self._output_status()
        return status

    def _rd(self, address, format="H"):
        return self.device.read_holding_registers(address, format)

    def _wr(self, address, format, value):
        return self.device.write_registers(address, format, value)

    def pid(self):
        try:
            value = self.device.read_holding_registers(6, "HHHH")
            _pid = (value[0] / self._scale, value[2], value[3])
        except TypeError:
            raise Eurotherm2000Error("Cannot read PID")
        return _pid


class eurotherm2000(Controller):
    def __init__(self, config, *args):
        """
        controller configuration
        """
        self.log = logging.getLogger("eurotherm2000")
        self.log.debug("eurotherm2000:__init__ (%s %s)" % (config, args))

        try:
            port = config["serial"]["url"]
        except KeyError:
            port = config["port"]
            warn("'port' is deprecated. Use 'serial' instead", DeprecationWarning)
        self._dev = Eurotherm2000(1, port)
        Controller.__init__(self, config, *args)

    def initialize(self):
        self.log.debug("initialize")
        self._dev.initialize()

    def initialize_input(self, tinput):
        self.log.debug("initialize_input")
        if "type" not in tinput.config:
            tinput.config["type"] = "pv"

    def initialize_output(self, toutput):
        self.log.debug("initialize_output")

        self.ramp_rate = None

        if "type" not in toutput.config:
            toutput.config["type"] = "sp"

    def read_output(self, toutput):
        """Read the current temperature
           Args:
              toutput (object): Output class type object
           Returns:
              (float): current temperature [degC]
        """
        self.log.info("read_output %s" % toutput.config["type"])
        typ = toutput.config["type"]
        if typ is "wsp":
            return self._dev.get_setpoint(5)
        return self._dev.get_setpoint(5)

    def set(self, toutput, sp):
        """Go to the desired temperature as quickly as possible.
           Args:
              toutput (object): Output class type object
              sp (float): final temperature [degC]
        """
        self.log.debug("set() %r" % sp)

        # Ramprate should be 0 in order to get there AQAP
        self._dev.set_ramprate(0)
        self._dev.setpoint(sp)

    def get_setpoint(self, toutput):
        """Read the as quick as possible setpoint
           Args:
              toutput (object): Output class type object
           Returns:
              (float): current temperature setpoint
        """
        self.log.debug("get_setpoint")
        return self._dev.setpointvalue

        """
        or
        print "eurotherm2000:get_setpoint",toutput.config['type']
        typ = toutput.config['type']
        if typ is 'wsp':
            return self._dev.get_setpoint(5)
        return self._dev.get_setpoint()
        """

    def start_ramp(self, toutput, sp, **kwargs):
        """Start ramping to setpoint
           Args:
              toutput (object): Output class type object
              sp (float): The setpoint temperature [degC]
           Kwargs:
              rate (int): The ramp rate [degC/unit]
        """
        try:
            rate = int(kwargs.get("rate", self.ramp_rate))
            self._dev.set_ramprate(rate)
        except TypeError:
            raise Eurotherm2000Error("Cannot start ramping, ramp rate not set")

        self._dev.setpoint(sp)

    def set_ramprate(self, toutput, rate):
        """Set the ramp rate
           Args:
              toutput (object): Output class type object
              rate (float): The ramp rate [degC/unit]
       """
        self.ramp_rate = rate
        self._dev.set_ramprate(self.ramp_rate)

    def read_ramprate(self, toutput):
        """Read the ramp rate
           Returns:
              (float): Previously set ramp rate  [degC/unit]
        """
        self.ramp_rate = self._dev.get_ramprate()
        return self.ramp_rate

    def state_output(self, toutput):
        """Read the state parameters of the controller
        Args:
           toutput(object):  Output class type object
        Returns:
           (string): This is one of READY/RUNNING/ALARM
        """
        _status = self._dev.device_status()

        if 0 == _status:
            return "READY"
        if 2 == _status:
            return "RUNNING"
        return "ALARM"

    def read_input(self, tinput):
        self.log.debug("read_input")
        typ = tinput.config["type"]
        if typ is "op":
            return self._dev.op()
        elif typ is "sp":
            return self._dev.get_setpoint()
        elif typ is "wsp":
            return self._dev.get_setpoint(5)
        return self._dev.pv()

    def state_input(self, tinput):
        """Read the state parameters of the controller
           Args:
              tinput(object):  Input class type object
           Returns:
              (string): This is one of READY/RUNNING/ALARM
        """

        _status = self._dev.device_status()

        if 0 == _status:
            return "READY"
        if 2 == _status:
            return "RUNNING"
        return "ALARM"

    @object_attribute_type_get(type_info=("str"), type=Output)
    def get_ramprate_unit(self, toutput):
        return self._dev.ramprate_units()

    @object_attribute_type_set(type_info=("str"), type=Output)
    def set_ramprate_unit(self, toutput, value):
        return self._dev.ramprate_units(value)
