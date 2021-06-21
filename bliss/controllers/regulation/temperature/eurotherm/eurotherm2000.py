# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os.path
from ast import literal_eval

from bliss import global_map
from bliss.controllers.regulator import Controller
from bliss.controllers.regulator import Loop as RegulationLoop
from .nanodac import PropertiesMenuNode
from bliss.common.regulation import lazy_init

from collections import namedtuple
from tabulate import tabulate
from bliss.comm import modbus
from warnings import warn

from bliss.common.logtools import log_info, log_debug
from bliss.common.utils import autocomplete_property


def get_eurotherm_cmds():
    __fpath = os.path.realpath(__file__)
    __fdir = os.path.dirname(__fpath)
    fpath = os.path.join(__fdir, "eurotherm2000_cmds.txt")
    txt = open(fpath, "r").read()
    cmds = literal_eval(txt)

    return cmds


class Loop(RegulationLoop):
    @lazy_init
    def __info__(self):
        lines = ["\n"]
        lines.append(f"=== Loop: {self.name} ===")
        lines.append(
            f"controller: {self.controller.name if self.controller.name is not None else f'Eurotherm{self.controller.model}'} ({self.controller.state})"
        )
        lines.append(
            f"Input: {self.input.name} @ {self.input.read():.3f} {self.input.config.get('unit', 'N/A')}"
        )
        lines.append(
            f"output: {self.output.name} @ {self.output.read():.3f} {self.output.config.get('unit', 'N/A')}"
        )

        lines.append("\n=== Setpoint ===")
        lines.append(
            f"setpoint: {self.setpoint} {self.input.config.get('unit', 'N/A')}"
        )
        lines.append(
            f"ramprate: {self.ramprate} {self.input.config.get('unit', 'N/A')}/{self.controller.get_ramprate_unit(self)}"
        )
        lines.append(f"ramping: {self.is_ramping()}")
        lines.append("\n=== PID ===")
        lines.append(f"kp: {self.kp}")
        lines.append(f"ki: {self.ki}")
        lines.append(f"kd: {self.kd}")

        return "\n".join(lines)


class Eurotherm2000(Controller):
    """
        Eurotherm2000 regulation controller.
    """

    def __init__(self, config):
        super().__init__(config)

        self._hw_controller = None
        self._setpoint = {}

    def __info__(self):
        return self.hw_controller.show_status()

    def dump_all_cmds(self):
        return self.hw_controller.dump_all_cmds()

    @autocomplete_property
    def hw_controller(self):
        if self._hw_controller is None:
            try:
                port = self.config["serial"]["url"]
            except KeyError:
                port = self.config["port"]
                warn("'port' is deprecated. Use 'serial' instead", DeprecationWarning)
            self._hw_controller = Eurotherm2000Device(1, port)
            self._hw_controller.initialize()
        return self._hw_controller

    @autocomplete_property
    def cmds(self):
        return self.hw_controller.cmds

    @property
    def status(self):
        return self.hw_controller.status

    @property
    def state(self):
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

    def show_status(self):
        self.hw_controller.show_status()

    @property
    def model(self):
        return self.hw_controller.model

    @property
    def manual(self):
        return self.hw_controller.manual

    @manual.setter
    def manual(self, value):
        self.hw_controller.manual = value

    # ------ init methods ------------------------

    def initialize_controller(self):
        """ 
        Initializes the controller (including hardware).
        """
        self.hw_controller

    def initialize_input(self, tinput):
        """
        Initializes an Input class type object

        Args:
           tinput:  Input class type object          
        """
        log_debug(self, "initialize_input")

    def initialize_output(self, toutput):
        """
        Initializes an Output class type object

        Args:
           toutput:  Output class type object          
        """
        log_debug(self, "initialize_output")

    def initialize_loop(self, tloop):
        """
        Initializes a Loop class type object

        Args:
           tloop:  Loop class type object          
        """
        if tloop.channel is None:
            tloop._channel = 1

        # Force input and output to share the same channel as their associated loop
        tloop.input._channel = tloop.channel
        tloop.output._channel = tloop.channel

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
        return self.hw_controller.send_cmd("process_variable", channel=tinput.channel)

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
        return self.hw_controller.send_cmd("pc_output_power", channel=toutput.channel)

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
        return self.state

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
        return self.state

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
        self.hw_controller.send_cmd("proportional_band_pid1", kp, channel=tloop.channel)

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
        return self.hw_controller.send_cmd(
            "proportional_band_pid1", channel=tloop.channel
        )

    def set_ki(self, tloop, ki):
        """
        Set the PID I value
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object 
           ki: the ki value
        """
        log_info(self, "Controller:set_ki: %s %s" % (tloop, ki))
        self.hw_controller.send_cmd("integral_time_pid1", ki, channel=tloop.channel)

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
        return self.hw_controller.send_cmd("integral_time_pid1", channel=tloop.channel)

    def set_kd(self, tloop, kd):
        """
        Set the PID D value
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object 
           kd: the kd value
        """
        log_info(self, "Controller:set_kd: %s %s" % (tloop, kd))
        self.hw_controller.send_cmd("derivative_time_pid1", kd, channel=tloop.channel)

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
        return self.hw_controller.send_cmd(
            "derivative_time_pid1", channel=tloop.channel
        )

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
        if self._setpoint.get(tloop.channel) is None:
            self._setpoint[tloop.channel] = self.hw_controller.send_cmd(
                "target_setpoint", channel=tloop.channel
            )
        return self._setpoint[tloop.channel]

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
        return self.hw_controller.send_cmd("working_set_point", channel=tloop.channel)

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
        self.hw_controller.send_cmd("target_setpoint", sp, channel=tloop.channel)
        self._setpoint[tloop.channel] = sp

    def stop_ramp(self, tloop):
        """
        Stop the current ramping to a setpoint
        It must NOT stop the PID process, use 'stop_regulation' to do so.
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object
        """
        log_info(self, "Controller:stop_ramp: %s" % (tloop))
        sp = self.read_input(tloop.input)
        self.hw_controller.send_cmd("target_setpoint", sp, channel=tloop.channel)
        self._setpoint[tloop.channel] = sp

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

        wsp = self.hw_controller.send_cmd("working_set_point", channel=tloop.channel)
        sp = self.hw_controller.send_cmd("target_setpoint", channel=tloop.channel)

        if sp != wsp:
            return True
        else:
            return False

    def set_ramprate(self, tloop, rate):
        """Set the ramp rate
           Args:
              toutput (object): Output class type object
              rate (float): The ramp rate [degC/unit]
        """
        self.hw_controller.send_cmd("setpoint_rate_limit", rate, channel=tloop.channel)

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
        return self.hw_controller.send_cmd("setpoint_rate_limit", channel=tloop.channel)

    def get_ramprate_unit(self, tloop):
        log_info(self, "Controller:get_ramprate_unit: %s" % (tloop))
        return self.hw_controller.get_ramprate_unit(channel=tloop.channel)


class Eurotherm2000Device:

    RAMP_RATE_UNITS = ("sec", "min", "hour")

    SENSOR_TYPES = (
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

    STATUS_FIELDS = (
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
    EURO_STATUS = namedtuple("EURO_STATUS", STATUS_FIELDS)

    # load the default cmds dict => { cmd: (register, dtype), } with dtype in ['H', 'f', 'i']
    _DEFAULT_CMDS_MAPPING = get_eurotherm_cmds()

    def __init__(self, modbus_address, serialport):
        """ RS232 settings: 9600 baud, 8 bits, no parity, 1 stop bit
        """

        self._model = None
        self._ident = None
        self._version = None
        self._floating_point_format = None

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

    def initialize(self):
        """Get the model, the firmware version and the resolution of the module.
        """
        log_debug(self, "initialize")
        # self.flush()

        # get a copy of cmds dict in case it needs to be modified regarding the controller model
        # get the 2400 series cmds
        self._CMDS_MAPPING = self._DEFAULT_CMDS_MAPPING[4].copy()

        self._read_identification()
        self._update_cmd_registers()
        self._read_version()
        self._load_cmds()

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
        ident = self.send_cmd("instrument_ident")
        log_debug(self, "Connected to Eurotherm model ident code = %x" % ident)
        self._ident = ident
        self._model = (ident & 0xf00) >> 8

    def _update_cmd_registers(self):
        # The default cmds register values are for 2400 series
        # Update cmds register values for other models
        if self._model == 4:
            pass

        elif self._model in self._DEFAULT_CMDS_MAPPING.keys():

            # for k in self._DEFAULT_CMDS_MAPPING[self._model].keys():
            #     print("update register {k} from {self._CMDS_MAPPING[k]} to {self._DEFAULT_CMDS_MAPPING[self._model][k]}")

            self._CMDS_MAPPING.update(self._DEFAULT_CMDS_MAPPING[self._model])

            # for k in self._DEFAULT_CMDS_MAPPING[self._model].keys():
            #     assert self._CMDS_MAPPING[k] == self._DEFAULT_CMDS_MAPPING[self._model][k]

        else:
            raise ValueError(f"Unsuported model {self._model} !")

    def _load_cmds(self):
        """ Creates a PropertiesMenuNode to access all mapped commands as properties via self.cmds """
        tmp = {}
        for k in self._CMDS_MAPPING:

            def getter_cb(obj, cmd=k):
                return self.send_cmd(cmd, None)

            def setter_cb(obj, value, cmd=k):
                return self.send_cmd(cmd, value)

            tmp[k] = (getter_cb, setter_cb)

        self.cmds = PropertiesMenuNode(tmp)

    def _read_version(self):
        """There is the possibility to config the 2400 series with floating
        point or integer values. Tag address 525 tells you how many digits
        appear after the radix character.
        BUT !!!!! there was one controller (firmware version 0x0411) on which
        this cell`s contents has no influence on the modbus readings.
        The sample environment controllers have version 0x0461.
        """

        self._version = self.send_cmd("instrument_version_number")
        log_info(
            self,
            "Firmware V%x.%x"
            % ((self._version & 0xff00) >> 8, (self._version & 0x00ff)),
        )

    def _update_resolution(self):
        log_debug(self, "get the floating point data format")
        self._floating_point_format = self.send_cmd("aa_comms_resolution")

    def flush(self):
        self.comm._serial.flush()

    def send_cmd(self, cmd, value=None, channel=None):
        """
            Send commands to the hardware controller.
            Args:
              - cmd: a string or a tuple (register, dtype) with dtype in ['H', 'f', 'i']
                See 'self._CMDS_MAPPING' for all commands and associated register.
              - value: if None, the register is read else it set to this value.
              - channel: some commands can be sent to one of the 3 loops (2700 models).
                If channel value is in [2, 3] the value of the register that will be read is augmented by '(channel-1)*1024'.
        """

        if isinstance(cmd, (tuple, list)):
            reg, dtype = cmd[0:2]
        else:
            reg, dtype = self._CMDS_MAPPING[cmd]

        # Handle multiple loops of 2704 model
        if channel in [2, 3]:
            reg += (channel - 1) * 1024

        if dtype in ["f", "i"]:
            reg = 2 * reg + 0x8000
        elif dtype != "H":
            raise ValueError(f"Unknown register type {dtype} for command {cmd} !")

        if value is None:
            value = self.comm.read_holding_registers(reg, dtype)
            if dtype == "i":
                value /= 1000.0
            return value

        else:
            if dtype == "i":
                value = int(1000.0 * value)
            elif dtype == "f":
                value = float(value)
            self.comm.write_registers(reg, dtype, value)

    def display_resolution(self):
        """ Get the display resolution and the number of decimal points value.
        """

        resol = self.send_cmd("aa_comms_resolution")  # 0:full, 1:integer
        decimal = self.send_cmd("decimal_places_in_displayed_value")  # 0:0, #1:1, 2:2

        if resol == 0:
            scale = pow(10, decimal)
            log_debug(self, "Display Resolution full, decimal %d" % decimal)
        else:
            scale = 1
            log_debug(self, "Display Resolution integer")
        return scale

    @property
    def floating_point_format(self):
        if self._floating_point_format is None:
            self._update_resolution()
        return self._floating_point_format

    @property
    def resolution(self):
        self._update_resolution()
        if self.floating_point_format == 0:
            return "Full"
        elif self.floating_point_format == 1:
            return "Integer"

    @property
    def model(self):
        return f"{self._ident:x}"

    @property
    def version(self):
        return self._version

    @property
    def sp(self):
        """ get target setpoint """
        return self.send_cmd("target_setpoint")

    @sp.setter
    def sp(self, value):
        """ set target setpoint """
        self.send_cmd("target_setpoint", value)

    @property
    def wsp(self):
        """ get working setpoint """
        return self.send_cmd("working_set_point")

    @property
    def pv(self):
        """ get process variable """
        return self.send_cmd("process_variable")

    @property
    def op(self):
        """ get output power """
        return self.send_cmd("pc_output_power")

    @property
    def ramprate(self):
        """ Read the current ramprate
            Returns:
              (float): current ramprate [degC/unit]
        """
        return self.send_cmd("setpoint_rate_limit")

    @ramprate.setter
    def ramprate(self, value):
        self.send_cmd("setpoint_rate_limit", value)

    def get_ramprate_unit(self, channel=None):
        """ Get the ramprate time unit.
            Returns:
              (str): Time unit - 'sec', 'min' or 'hour'
        """
        value = self.send_cmd("setpoint_rate_limit_units", channel=channel)
        return self.RAMP_RATE_UNITS[value]

    def set_ramprate_unit(self, value, channel=None):
        """ Set the ramprate time unit
            Args:
              value (str): Time unit - 'sec', 'min' or 'hour'
        """
        if value not in self.RAMP_RATE_UNITS:
            raise ValueError(
                f"Invalid eurotherm ramp rate units. Should be in {self.RAMP_RATE_UNITS}"
            )

        # self.send_cmd("instrument_mode", 2)
        self.send_cmd(
            "setpoint_rate_limit_units",
            self.RAMP_RATE_UNITS.index(value),
            channel=channel,
        )
        # self.send_cmd("instrument_mode", 0)

    @property
    def manual(self):
        if self.send_cmd("auto_man_select") == 1:
            return True
        else:
            return False

    @manual.setter
    def manual(self, value):
        if value:
            self.send_cmd("auto_man_select", 1)
        else:
            self.send_cmd("auto_man_select", 0)

    @property
    def pid(self):
        return (self.kp, self.ki, self.kd)

    @property
    def kp(self):
        """ get proportional band PID1 """
        return self.send_cmd("proportional_band_pid1")

    @kp.setter
    def kp(self, value):
        """ set proportional band PID1 """
        self.send_cmd("proportional_band_pid1", value)

    @property
    def ki(self):
        """ get integral time PID1 """
        return self.send_cmd("integral_time_pid1")

    @ki.setter
    def ki(self, value):
        """ set integral time PID1 """
        self.send_cmd("integral_time_pid1", value)

    @property
    def kd(self):
        """ get derivative time PID1 """
        return self.send_cmd("derivative_time_pid1")

    @kd.setter
    def kd(self, value):
        """ set derivative time PID1 """
        self.send_cmd("derivative_time_pid1", value)

    @property
    def sensor_type(self):
        sensor = self.send_cmd("input_type")
        try:
            return self.SENSOR_TYPES[sensor]
        except IndexError:
            return f"Unknown sensor type:{sensor}"

    @sensor_type.setter
    def sensor_type(self, stype):
        if stype != self.sensor_type:
            # self.send_cmd("instrument_mode", 2)
            self.send_cmd("input_type", self.SENSOR_TYPES.index(stype))
            # self.send_cmd("instrument_mode", 0)

    def prog_status(self):
        """Read the setpoint status.

           Returns:
              (int): 0 - ready
                     1 - wsp != sp so running
                     2 - busy, a program is running
        """
        if self._model == 4 and self.send_cmd("program_status") != 1:
            return 2
        else:
            if self.wsp != self.sp:
                return 1
        return 0

    def is_ramping(self):
        return bool(self.prog_status())

    @property
    def status(self):
        value = self.send_cmd("status_info")
        status = self.EURO_STATUS(
            *[bool(value & (1 << i)) for i in range(len(self.EURO_STATUS._fields))]
        )
        return status

    def show_status(self):
        status = self.status
        rows = [(field, str(getattr(status, field))) for field in status._fields]
        heads = ["EuroStatus", "Value"]
        print(tabulate(rows, headers=heads))

    def dump_all_cmds(self):
        return {k: self.send_cmd(k) for k in self._CMDS_MAPPING.keys()}
