# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss import global_map
from bliss.controllers.regulator import Controller

from collections import namedtuple
from tabulate import tabulate
from bliss.comm import modbus
from bliss.comm.exceptions import CommunicationError
from warnings import warn

from bliss.common.logtools import log_info, log_debug


class Eurotherm2000(Controller):
    """
        Eurotherm2000 regulation controller.
    """

    # INPUT_TYPES = ("pv", "wsp", "op")
    # OUTPUT_TYPES = ("sp",)

    def __init__(self, config):
        super().__init__(config)

        self._hw_controller = None
        self._setpoint = None

    @property
    def hw_controller(self):
        if self._hw_controller is None:
            try:
                port = self.config["serial"]["url"]
            except KeyError:
                port = self.config["port"]
                warn("'port' is deprecated. Use 'serial' instead", DeprecationWarning)
            self._hw_controller = Eurotherm2000Device(1, port)
        return self._hw_controller

    def __info__(self):
        return self.hw_controller.status

    def control_status(self):
        status = self.hw_controller.status
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

    def get_ramprate_unit(self):
        return self.hw_controller.ramprate_units

    def set_ramprate_unit(self, value):
        self.hw_controller.ramprate_units = value

    def sensor_type(self):
        return self.hw_controller.sensor_type

    def status(self):
        self.hw_controller.show_status()

    def get_model(self):
        return self.hw_controller.model

    # ------ init methods ------------------------

    def initialize_controller(self):
        """ 
        Initializes the controller (including hardware).
        """
        log_debug(self, "initialize")
        self.hw_controller.initialize()

    def initialize_input(self, tinput):
        """
        Initializes an Input class type object

        Args:
           tinput:  Input class type object          
        """

        log_debug(self, "initialize_input")
        # if "type" not in tinput.config:
        #     tinput.config["type"] = "pv"
        # else:
        #     if tinput.config["type"] not in self.INPUT_TYPES:
        #         raise ValueError(
        #             "Invalid input type [{0}]. Should one of {1}.".format(
        #                 tinput.config["type"], self.INPUT_TYPES
        #             )
        #         )

    def initialize_output(self, toutput):
        """
        Initializes an Output class type object

        Args:
           toutput:  Output class type object          
        """
        log_debug(self, "initialize_output")
        # if "type" not in toutput.config:
        #     toutput.config["type"] = "sp"
        # else:
        #     if toutput.config["type"] not in self.OUTPUT_TYPES:
        #         raise ValueError(
        #             "Invalid input type [{0}]. Should one of {1}.".format(
        #                 toutput.config["type"], self.OUTPUT_TYPES
        #             )
        #         )

    def initialize_loop(self, tloop):
        """
        Initializes a Loop class type object

        Args:
           tloop:  Loop class type object          
        """
        pass

    # ------ get methods ------------------------

    def read_input(self, tinput):
        """
        Reads an Input class type object
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tinput:  Input class type object 

        Returns:
           read value  (in input unit)    
        """
        log_info(self, "Controller:read_input: %s" % (tinput))
        # typ = str(tinput.config["type"])
        # if typ == "op":
        #     return self.hw_controller.op
        # elif typ == "sp":
        #     return self.hw_controller.sp
        # elif typ == "wsp":
        #     return self.hw_controller.wsp
        return self.hw_controller.pv

    def read_output(self, toutput):
        """
        Reads an Output class type object
        Raises NotImplementedError if not defined by inheriting class

        Args:
           toutput:  Output class type object 

        Returns:
           read value (in output unit)         
        """
        log_info(self, "Controller:read_output: %s" % (toutput))
        # if toutput.config["type"] is "wsp":
        #     return self.hw_controller.wsp
        # else:
        #     return self.hw_controller.sp

        return self.hw_controller.op

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
        return self.control_status()

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
        return self.control_status()

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
        print("PID parameters cannot be set on this device")

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
        return self.hw_controller.P

    def set_ki(self, tloop, ki):
        """
        Set the PID I value
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object 
           ki: the ki value
        """
        log_info(self, "Controller:set_ki: %s %s" % (tloop, ki))
        print("PID parameters cannot be set on this device")

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
        return self.hw_controller.I

    def set_kd(self, tloop, kd):
        """
        Set the PID D value
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object 
           kd: the kd value
        """
        log_info(self, "Controller:set_kd: %s %s" % (tloop, kd))
        print("PID parameters cannot be set on this device")

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
        return self.hw_controller.D

    def start_regulation(self, tloop):
        """
        Starts the regulation process.
        It must NOT start the ramp, use 'start_ramp' to do so.
        Raises NotImplementedError if not defined by inheriting class

        Args: 
           tloop:  Loop class type object
        """
        log_info(self, "Controller:start_regulation: %s" % (tloop))
        pass

    def stop_regulation(self, tloop):
        """
        Stops the regulation process.
        It must NOT stop the ramp, use 'stop_ramp' to do so.
        Raises NotImplementedError if not defined by inheriting class

        Args: 
           tloop:  Loop class type object
        """
        log_info(self, "Controller:stop_regulation: %s" % (tloop))
        pass

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
        pass

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
        if self._setpoint is None:
            self._setpoint = self.hw_controller.sp
        return self._setpoint

    def get_working_setpoint(self, tloop):
        """
        Get the current working setpoint (setpoint along ramping)
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object

        Returns:
           (float) working setpoint value (in tloop.input unit).
        """
        log_info(self, "Controller:get_working_setpoint: %s" % (tloop))
        return self.hw_controller.wsp

    # ------ setpoint ramping methods (optional) ------------------------

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
        self.hw_controller.sp = sp
        self._setpoint = sp

    def stop_ramp(self, tloop):
        """
        Stop the current ramping to a setpoint
        It must NOT stop the PID process, use 'stop_regulation' to do so.
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object
        """
        log_info(self, "Controller:stop_ramp: %s" % (tloop))
        sp = self.hw_controller.pv
        self.hw_controller.sp = sp
        self._setpoint = sp

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
        return self.hw_controller.is_ramping()

    def set_ramprate(self, tloop, rate):
        """Set the ramp rate
           Args:
              toutput (object): Output class type object
              rate (float): The ramp rate [degC/unit]
        """
        self.hw_controller.ramprate = rate

    def get_ramprate(self, tloop):
        """
        Get the ramp rate
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object
        
        Returns:
           ramp rate (in input unit per second)
        """
        log_info(self, "Controller:get_ramprate: %s" % (tloop))
        return self.hw_controller.ramprate


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
            "Eurotherm2000Device: __init__(address %s, port %s)",
            modbus_address,
            serialport,
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
            log_debug(self, "Connected to Eurotherm model 2XXX ident code = %x" % ident)
            self._ident = ident
            self._model = (ident & 0xf00) >> 8
        else:
            log_debug(self, "Connected to Eurotherm model ident code = %x" % ident)
            self._ident = ident
            self._model = (ident & 0xf00) >> 8

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
        """Read the setpoint status.

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

    def is_ramping(self):
        return bool(self.prog_status())

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
