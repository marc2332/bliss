# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Keithley meters.

YAML_ configuration example:

.. code-block:: yaml

    plugin: keithley               # (1)
    name: k_ctrl_1                 # (2)
    model: 6485                    # (3)
    auto_zero: False               # (4)
    display: False                 # (5)
    zero_check: False              # (6)
    zero_correct: False            # (7)
    gpib:                          # (8)
      url: enet://gpibid31eh
      pad: 12
    sensors:                       # (10)
    - name: mondio                 # (11)
      address: 1                   # (12)
      nplc: 0.1                    # (13)
      auto_range: False            # (14)

#. plugin name (mandatory: keithley)
#. controller name (mandatory). Some controller settings are needed. To hook the
   settings to the controller we use the controller name. That is why it is
   mandatory
#. controller model (optional. default: discover by asking instrument *IDN)
#. auto-zero enabled (optional, default: False)
#. display enabled (optional, default: True)
#. zero-check enabled (optional, default: False). Only for 6485!
#. zero-correct enabled (optional, default: False). Only for 6485!
#. controller URL (mandatory, valid: gpib, tcp, serial)
  #. gpib (mandatory: *url* and *pad*). See :class:~bliss.comm.gpib.Gpib for
     list of options
  #. serial (mandatory: *port*). See :class:~bliss.comm.serial.Serial for list
     of options
  #. tcp (mandatory: *url*). See :class:~bliss.comm.tcp.Tcp for list of options
#. list of sensors (mandatory)
#. sensor name (mandatory)
#. sensor address (mandatory). Valid values:
  #. model 6482: 1, 2
  #. model 6485: 1
  #. model 2000: 1
#. sensor DC current NPLC (optional, default: 0.1)
#. sensor DC current auto-range (optional, default: False)

Some parameters (described below) are stored as settings. This means that the
static configuration described above serves as a *default configuration*.
The first time ever the system is brought to life it will read this
configuration and apply it to the settings. From now on, the keithley object
will rely on its settings. This is the same principle as it is applied on the
bliss axis velocity for example.

The following controller parameters are stored as settings: *auto_zero*,
*display*, (and *zero_check* and *zero_correct* only for 6485).

The following sensor parameters are stored as settings:
*current_dc_nplc* and *auto_range*.

A demo is available from the command line:

$ python -m bliss.controllers.keithley <url> <pad>

Developer details:
    READ? <=> INIT + FETCH?
    MEASURE[:<function>]? <=> CONF[:<function>] + READ?  == CONF[:<function>] + INIT + READ?
"""

import time
import weakref
import functools
import collections
import functools
from types import SimpleNamespace
import numpy
import gevent

from bliss.common.counter import SamplingCounter
from bliss.controllers.counter import SamplingCounterController
from bliss.comm.util import get_interface, get_comm
from bliss.config.beacon_object import BeaconObject
from bliss.config.settings import pipeline
from bliss.comm.exceptions import CommunicationError
from bliss.comm.scpi import Cmd as SCPICmd
from bliss.comm.scpi import Commands as SCPICommands
from bliss.comm.scpi import BaseSCPIDevice
from bliss.common.utils import autocomplete_property

from .keithley_scpi_mapping import COMMANDS as SCPI_COMMANDS
from .keithley_scpi_mapping import MODEL_COMMANDS as SCPI_MODEL_COMMANDS

CTRL = weakref.WeakValueDictionary()


class KeithleySCPI(BaseSCPIDevice):
    """Keithley instrument through SCPI language. Can be used with any Keithley
    SCPI capable device.

    Example usage::

        from bliss.comm.gpib import Gpib
        from bliss.controllers.keithley import KeithleySCPI

        gpib = Gpib('enet://gpibhost', pad=10)
        keithley = KeithleySCPI(gpib)

        print( keithley('*IDN?') )
        print( keithley['*IDN'] )
    """

    def __init__(self, *args, **kwargs):
        commands = SCPICommands(SCPI_COMMANDS)
        model = str(kwargs.pop("model"))
        commands.update(SCPI_MODEL_COMMANDS.get(model, {}))
        kwargs["commands"] = commands
        super(KeithleySCPI, self).__init__(*args, **kwargs)


class BaseSensor(SamplingCounter, BeaconObject):
    MeasureFunctions = SCPICommands({"CURRent[:DC]": SCPICmd()})
    MeasureRanges = {
        "CURRent[:DC]": [2e-9, 20e-9, 200e-9, 2e-6, 20e-6, 200e-6, 2e-3, 20e-3]
    }
    name = BeaconObject.config_getter("name")
    address = BeaconObject.config_getter("address")

    def __init__(self, config, controller):
        BeaconObject.__init__(self, config)
        SamplingCounter.__init__(self, self.name, controller._counter_controller)
        self.__controller = controller
        self.__measure_range_cache = None

    @autocomplete_property
    def comm(self):
        return self.__controller._keithley_comm

    @autocomplete_property
    def controller(self):
        return self.__controller

    @property
    def index(self):
        return self.address - 1

    @BeaconObject.property(default="CURR:DC", priority=-1)
    def meas_func(self):
        func = self.comm["CONF"]
        func = func.replace('"', "")
        return self.MeasureFunctions[func]["max_command"]

    @meas_func.setter
    def meas_func(self, func):
        func = self.MeasureFunctions[func]["max_command"]
        self.comm("CONF:" + func)
        # remove range and auto_range in settings
        if not self._in_initialize_with_setting:
            with pipeline(self.settings):
                del self.settings["auto_range"]
                del self.settings["range"]
        return func

    @BeaconObject.property(default=0.1)
    def nplc(self):
        cmd = self._meas_func_sensor_cmd("NPLC")
        return self.comm[cmd]

    @nplc.setter
    def nplc(self, value):
        cmd = self._meas_func_sensor_cmd("NPLC")
        self.comm[cmd] = value

    @BeaconObject.property(priority=1)
    def auto_range(self):
        cmd = self._meas_func_sensor_cmd("RANG:AUTO")
        return self.comm[cmd]

    @auto_range.setter
    def auto_range(self, value):
        cmd = self._meas_func_sensor_cmd("RANG:AUTO")
        self.comm[cmd] = value
        if value:
            self.disable_setting("range")
        else:
            self.enable_setting("range")

    @property
    def possible_ranges(self):
        """
        Return the possible ranges for the current
        measure functions.
        """
        if self.__measure_range_cache is None:
            measure_ranges = dict()
            for measure_name, ranges in self.MeasureRanges.items():
                cmd = SCPICommands({measure_name: SCPICmd()})
                cmd_info = next(iter(cmd.command_expressions.values()))
                full_name = cmd_info["max_command"]
                measure_ranges[full_name] = ranges
            self.__measure_range_cache = measure_ranges
        measure_func = self.MeasureFunctions[self.meas_func]["max_command"]
        return self.__measure_range_cache.get(measure_func, [])

    @BeaconObject.property(priority=2)
    def range(self):
        cmd = self._meas_func_sensor_cmd("RANGe:UPPer")
        return self.comm[cmd]

    @range.setter
    def range(self, range_value):
        cmd = self._meas_func_sensor_cmd("RANGe:UPPer")
        value = range_value
        for value in self.possible_ranges:
            if value >= range_value:
                break

        self.auto_range = False
        self.comm[cmd] = value
        return self.comm[cmd]

    def _initialize_with_setting(self):
        if self._is_initialized:
            return
        self.__controller._initialize_with_setting()
        super()._initialize_with_setting()

    def _meas_func_sensor_cmd(self, param):
        func = self.meas_func
        return "SENS%d:%s:%s" % (self.address, func, param)

    def _sensor_cmd(self, param):
        return "SENS%d:%s" % (self.address, param)

    def __info__(self):
        sinfo = f"meas_func = {self.meas_func}\n"
        sinfo += f"auto_range = {self.auto_range}\n"
        sinfo += f"range = {self.range}\n"
        sinfo += f"nplc = {self.nplc}\n"
        return sinfo


class SensorZeroCheckMixin:
    """
    Mixin to add Zero Check and Zero Correct
    """

    @BeaconObject.property(default=False)
    def zero_check(self):
        return self.comm["SYST:ZCH"]

    @zero_check.setter
    def zero_check(self, value):
        self.comm["SYST:ZCH"] = value

    @BeaconObject.property(default=False)
    def zero_correct(self):
        return self.comm["SYST:ZCOR"]

    @zero_correct.setter
    def zero_correct(self, value):
        self.comm["SYST:ZCOR"] = value

    def acquire_zero_correct(self):
        """Zero correct procedure"""
        zero_check = self.settings["zero_check"]
        zero_correct = self.settings["zero_correct"]
        self.zero_check = True  # zero check must be enabled
        self.zero_correct = False  # zero correct state must be disabled
        self.comm("INIT")  # trigger a reading
        self.comm("SYST:ZCOR:ACQ")  # acquire zero correct value
        self.zero_correct = zero_correct  # restore zero correct state
        self.zero_check = zero_check  # restore zero check

    def __info__(self):
        sinfo = f"zero_check = {self.zero_check}"
        sinfo += f"zero_correct = {self.zero_correct}"
        return sinfo


class BaseMultimeter(BeaconObject):
    def __init__(self, config, interface=None):
        self.__name = config.get("name", "keithley")
        kwargs = dict(config)
        if interface:
            kwargs["interface"] = interface
        BeaconObject.__init__(self, config)
        self._keithley_comm = KeithleySCPI(**kwargs)
        comm = self._keithley_comm

        class _CounterController(SamplingCounterController):
            def read_all(self, *counters):
                for counter in counters:
                    counter._initialize_with_setting()
                values = comm["READ"]
                return [values[cnt.index] for cnt in counters]

        self._counter_controller = _CounterController("keithley")

    def __str__(self):
        return "{0}({1})".format(self.__class__.__name__, self.name)

    @property
    def name(self):
        return self.__name

    def _initialize_with_setting(self):
        if self._is_initialized:
            return

        self._keithley_comm("*RST", "*OPC?")
        super()._initialize_with_setting()
        self._keithley_comm("*OPC?")

    @BeaconObject.property(default=True)
    def display_enable(self):
        return self._keithley_comm["DISP:ENAB"]

    @display_enable.setter
    def display_enable(self, value):
        self._keithley_comm["DISP:ENAB"] = value

    @BeaconObject.property(default=False)
    def auto_zero(self):
        return self._keithley_comm["SYST:AZER"]

    @auto_zero.setter
    def auto_zero(self, value):
        self._keithley_comm["SYST:AZER"] = value

    @BeaconObject.lazy_init
    def abort(self):
        return self._keithley_comm("ABOR", "OPC?")

    @BeaconObject.lazy_init
    def __info__(self):
        values = self.settings.get_all()
        settings = "\n".join(("    {0}={1}".format(k, v) for k, v in values.items()))
        idn = "\n".join(
            ("    {0}={1}".format(k, v) for k, v in self._keithley_comm["*IDN"].items())
        )
        return "{0}:\n  name:{1}\n  IDN:\n{2}\n  settings:\n{3}".format(
            self, self.name, idn, settings
        )

    class Sensor(BaseSensor):
        pass


class K6485(BaseMultimeter):
    def _initialize_with_setting(self):
        if self._is_initialized:
            return

        self._keithley_comm["FORM:ELEM"] = [
            "READ"
        ]  # just get the current when you read (no timestamp)
        self._keithley_comm["CALC3:FORM"] = "MEAN"  # buffer statistics is mean
        self._keithley_comm["TRAC:FEED"] = "SENS"  # source of reading is sensor
        super()._initialize_with_setting()

    class Sensor(BaseMultimeter.Sensor, SensorZeroCheckMixin):
        @property
        def meas_func(self):
            """
            Fixed the measure function to Current
            """
            return "CURR"

        def __info__(self):
            return BaseMultimeter.Sensor.__info__(self) + SensorZeroCheckMixin.__info__(
                self
            )


class K6482(BaseMultimeter):
    def _initialize_with_setting(self):
        if self._is_initialized:
            return

        # should it not be FORM:ELEM instead of FORM:ELEM:TRAC ?
        self._keithley_comm["FORM:ELEM:TRAC"] = ["CURR1", "CURR2"]
        self._keithley_comm["CALC8:FORM"] = "MEAN"  # buffer statistics is mean
        super()._initialize_with_setting()

    class Sensor(BaseMultimeter.Sensor):
        @property
        def meas_func(self):
            """
            Fixed the measure function to Current
            """
            return "CURR"


class K6514(BaseMultimeter):
    def _initialize_with_setting(self):
        if self._is_initialized:
            return

        self._keithley_comm["FORM:ELEM"] = [
            "READ"
        ]  # just get the current when you read (no timestamp)
        self._keithley_comm["CALC3:FORM"] = "MEAN"  # buffer statistics is mean
        self._keithley_comm["TRAC:FEED"] = "SENS"  # source of reading is sensor
        super()._initialize_with_setting()

    class Sensor(BaseSensor, SensorZeroCheckMixin):
        MeasureFunctions = SCPICommands(
            {
                "VOLTage[:DC]": SCPICmd(),
                "CURRent[:DC]": SCPICmd(),
                "RESistance": SCPICmd(),
                "CHARge": SCPICmd(),
            }
        )
        MeasureRanges = {
            "CURRENT:DC": [
                20e-12,
                200e-12,
                2e-9,
                20e-9,
                200e-9,
                2e-6,
                20e-6,
                200e-6,
                2e-3,
                20e-3,
            ],
            "VOLTAGE:DC": [2, 20, 200],
            "RESISTANCE": [2e3, 20e3, 200e3, 2e6, 20e6, 200e6, 2e9, 20e9, 200e9],
            "CHARGE": [20e-9, 200e-9, 2, 20],
        }

        def __info__(self):
            return BaseSensor.__info__(self) + SensorZeroCheckMixin.__info__(self)


class K2000(BaseMultimeter):
    class Sensor(BaseMultimeter.Sensor):
        MeasureFunctions = SCPICommands(
            {
                "CURRent[:DC]": SCPICmd(),
                "CURRent:AC": SCPICmd(),
                "VOLTage[:DC]": SCPICmd(),
                "VOLTage:AC": SCPICmd(),
                "RESistance": SCPICmd(),
                "FRESistance": SCPICmd(),
                "PERiod": SCPICmd(),
                "FREQuency": SCPICmd(),
                "TEMPerature": SCPICmd(),
            }
        )


class AmmeterDDCCounterController(SamplingCounterController):
    def __init__(self, name, interface):
        super().__init__(name)
        self.interface = interface

    def read_all(self, *counters):
        for counter in counters:
            counter._initialize_with_setting()
        values = self.interface.write_readline(b"X\r\n")
        return [values]


class AmmeterDDC(BeaconObject):
    def __init__(self, config):
        self.__name = config.get("name", "keithley")
        interface = get_comm(config, eol="\r\n")
        super().__init__(config)

        self._counter_controller = AmmeterDDCCounterController("keithley", interface)

    @property
    def name(self):
        return self.__name

    def __str__(self):
        return "{0}({1})".format(self.__class__.__name__, self.name)

    class Sensor(SamplingCounter, BeaconObject):
        name = BeaconObject.config_getter("name")
        address = BeaconObject.config_getter("address")

        def __init__(self, config, controller):
            BeaconObject.__init__(self, config)
            SamplingCounter.__init__(self, self.name, controller._counter_controller)
            self.interface = controller._counter_controller.interface

        @property
        def index(self):
            return 0

        def _initialize_with_setting(self):
            if self._is_initialized:
                return

            self.interface.write(b"F1X\r\n")  # Amp function
            self.interface.write(b"B0X\r\n")  # electrometer reading
            self.interface.write(b"G1X\r\n")  # Reading without prefix
            self.interface.write(b"T4X\r\n")
            super()._initialize_with_setting()


class K6512(AmmeterDDC):
    pass


class K485(AmmeterDDC):
    pass


class K487(AmmeterDDC):
    pass


def Multimeter(config):
    model = config.get("model")
    kwargs = {}
    if model is None:
        # Discover model
        interface, _, _ = get_interface(**config)
        decode_IDN = SCPI_COMMANDS["*IDN"].get("get")
        idn = decode_IDN(interface.write_readline(b"*IDN?\n"))
        model = idn["model"]
        kwargs["interface"] = interface
        config["model"] = model
    else:
        model = str(model)
    class_name = f"K{model}"
    try:
        klass = globals()[class_name]
    except KeyError:
        raise ValueError(
            "Unknown keithley model {} (hint: DDC needs a model "
            "in YAML)".format(model)
        )
    obj = klass(config, **kwargs)
    return obj


def create_objects_from_config_node(config, node):
    name = node["name"]
    if "sensors" in node:
        # controller node
        obj = Multimeter(node)
        CTRL[name] = obj
        for s_node in node["sensors"]:
            create_sensor(s_node)
    else:
        # sensor node
        obj = create_sensor(node)
    return {name: obj}


def create_sensor(node):
    ctrl_node = node.parent
    while ctrl_node and "sensors" not in ctrl_node:
        ctrl_node = ctrl_node.parent

    try:
        name = ctrl_node["name"]
    except KeyError:
        name = node["name"]

    ctrl = CTRL.setdefault(name, Multimeter(ctrl_node))

    sensor_names = [sensor_node["name"] for sensor_node in ctrl_node["sensors"]]
    for s_name in sensor_names:
        CTRL[s_name] = ctrl
    obj = ctrl.Sensor(node, ctrl)
    return obj
