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

import numpy
import gevent

from bliss.common.measurement import SamplingCounter
from bliss.comm.util import get_interface, get_comm
from bliss.config.beacon_object import BeaconObject
from bliss.config.settings import pipeline
from bliss.comm.exceptions import CommunicationError
from bliss.comm.scpi import Cmd as SCPICmd
from bliss.comm.scpi import Commands as SCPICommands
from bliss.comm.scpi import BaseSCPIDevice

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
        SamplingCounter.__init__(self, self.name, controller)
        self.__controller = controller
        self.__measure_range_cache = None

    @property
    def index(self):
        return self.address - 1

    @property
    def controller(self):
        return self.__controller

    @BeaconObject.property(default="CURR:DC", priority=-1)
    def meas_func(self):
        func = self.controller["CONF"]
        func = func.replace('"', "")
        return self.MeasureFunctions[func]["max_command"]

    @meas_func.setter
    def meas_func(self, func):
        func = self.MeasureFunctions[func]["max_command"]
        self.controller("CONF:" + func)
        # remove range and auto_range in settings
        if not self._in_initialize_with_setting:
            with pipeline(self.settings):
                del self.settings["auto_range"]
                del self.settings["range"]
        return func

    @BeaconObject.property(default=0.1)
    def nplc(self):
        cmd = self._meas_func_sensor_cmd("NPLC")
        return self.controller[cmd]

    @nplc.setter
    def nplc(self, value):
        cmd = self._meas_func_sensor_cmd("NPLC")
        self.controller[cmd] = value

    @BeaconObject.property(priority=1)
    def auto_range(self):
        cmd = self._meas_func_sensor_cmd("RANG:AUTO")
        return self.controller[cmd]

    @auto_range.setter
    def auto_range(self, value):
        cmd = self._meas_func_sensor_cmd("RANG:AUTO")
        self.controller[cmd] = value
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
        return self.controller[cmd]

    @range.setter
    def range(self, range_value):
        cmd = self._meas_func_sensor_cmd("RANGe:UPPer")
        value = range_value
        for value in self.possible_ranges:
            if value >= range_value:
                break

        self.auto_range = False
        self.controller[cmd] = value
        return self.controller[cmd]

    def _initialize_with_setting(self):
        if self._is_initialized:
            return
        self.controller._initialize_with_setting()
        super()._initialize_with_setting()

    @BeaconObject.lazy_init
    def measure(self, func=None):
        return self.controller.measure(func=func)[self.index]

    @BeaconObject.lazy_init
    def data(self):
        return self.controller.data()[self.index]

    def _meas_func_sensor_cmd(self, param):
        func = self.meas_func
        return "SENS%d:%s:%s" % (self.address, func, param)

    def _sensor_cmd(self, param):
        return "SENS%d:%s" % (self.address, param)


class SensorZeroCheckMixin:
    """
    Mixin to add Zero Check and Zero Correct
    """

    @BeaconObject.property(default=False)
    def zero_check(self):
        return self.controller["SYST:ZCH"]

    @zero_check.setter
    def zero_check(self, value):
        self.controller["SYST:ZCH"] = value

    @BeaconObject.property(default=False)
    def zero_correct(self):
        return self.controller["SYST:ZCOR"]

    @zero_correct.setter
    def zero_correct(self, value):
        self.controller["SYST:ZCOR"] = value

    def acquire_zero_correct(self):
        """Zero correct procedure"""
        zero_check = self.settings["zero_check"]
        zero_correct = self.settings["zero_correct"]
        self.zero_check = True  # zero check must be enabled
        self.zero_correct = False  # zero correct state must be disabled
        self("INIT")  # trigger a reading
        self("SYST:ZCOR:ACQ")  # acquire zero correct value
        self.zero_correct = zero_correct  # restore zero correct state
        self.zero_check = zero_check  # restore zero check


class BaseMultimeter(KeithleySCPI, BeaconObject):
    def __init__(self, config, interface=None):
        kwargs = dict(config)
        if interface:
            kwargs["interface"] = interface
        BeaconObject.__init__(self, config)
        KeithleySCPI.__init__(self, **kwargs)

    def __str__(self):
        return "{0}({1})".format(self.__class__.__name__, self.name)

    @property
    def name(self):
        sensors_name = "/".join(
            [sensor["name"] for sensor in self.config.get("sensors")]
        )
        return f"keithley:{sensors_name}"

    def _initialize_with_setting(self):
        if self._is_initialized:
            return

        self("*RST", "*OPC?")
        super()._initialize_with_setting()
        self("*OPC?")

    @BeaconObject.property(default=True)
    def display_enable(self):
        return self["DISP:ENAB"]

    @display_enable.setter
    def display_enable(self, value):
        self["DISP:ENAB"] = value

    @BeaconObject.property(default=False)
    def auto_zero(self):
        return self["SYST:AZER"]

    @auto_zero.setter
    def auto_zero(self, value):
        self["SYST:AZER"] = value

    @BeaconObject.lazy_init
    def read_all(self, *counters):
        values = self["READ"]
        return [values[cnt.index] for cnt in counters]

    @BeaconObject.lazy_init
    def data(self):
        return self["DATA"]

    @BeaconObject.lazy_init
    def abort(self):
        return self("ABOR", "OPC?")

    @BeaconObject.lazy_init
    def pprint(self):
        values = self.settings.get_all()
        settings = "\n".join(("    {0}={1}".format(k, v) for k, v in values.items()))
        idn = "\n".join(("    {0}={1}".format(k, v) for k, v in self["*IDN"].items()))
        print(
            (
                "{0}:\n  name:{1}\n  IDN:\n{2}\n  settings:\n{3}".format(
                    self, self.name, idn, settings
                )
            )
        )

    class Sensor(BaseSensor):
        pass


class K6485(BaseMultimeter):
    def _initialize_with_setting(self):
        if self._is_initialized:
            return

        self["FORM:ELEM"] = [
            "READ"
        ]  # just get the current when you read (no timestamp)
        self["CALC3:FORM"] = "MEAN"  # buffer statistics is mean
        self["TRAC:FEED"] = "SENS"  # source of reading is sensor
        super()._initialize_with_setting()

    class Sensor(BaseMultimeter.Sensor, SensorZeroCheckMixin):
        @property
        def meas_func(self):
            """
            Fixed the measure function to Current
            """
            return "CURR"


class K6482(BaseMultimeter):
    def _initialize_with_setting(self):
        if self._is_initialized:
            return

        # should it not be FORM:ELEM instead of FORM:ELEM:TRAC ?
        self["FORM:ELEM:TRAC"] = ["CURR1", "CURR2"]
        self["CALC8:FORM"] = "MEAN"  # buffer statistics is mean
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

        self["FORM:ELEM"] = [
            "READ"
        ]  # just get the current when you read (no timestamp)
        self["CALC3:FORM"] = "MEAN"  # buffer statistics is mean
        self["TRAC:FEED"] = "SENS"  # source of reading is sensor
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


class AmmeterDDC:
    def __init__(self, config):
        self.interface = get_comm(config, eol="\r\n")
        self.config = config

    @property
    def name(self):
        sensors_name = "/".join(
            [sensor["name"] for sensor in self.config.get("sensors")]
        )
        return f"keithley:{sensors_name}"

    def __str__(self):
        return "{0}({1})".format(self.__class__.__name__, self.name)

    class Sensor(SamplingCounter, BeaconObject):
        name = BeaconObject.config_getter("name")
        address = BeaconObject.config_getter("address")

        def __init__(self, config, controller):
            BeaconObject.__init__(self, config)
            SamplingCounter.__init__(self, self.name, controller)
            self.__controller = controller

        @property
        def controller(self):
            return self.__controller

        @BeaconObject.lazy_init
        def measure(self, func=None):
            svalue = self.interface.write_readline(b"X\r\n")
            return [float(svalue)]

        def data(self):
            return self.measure()

        def read(self):
            return self.measure()

        def _initialize_with_setting(self):
            if self._is_initialized:
                return

            ctrl = self.controller
            ctrl.interface.write(b"F1X\r\n")  # Amp function
            ctrl.write(b"B0X\r\n")  # electrometer reading
            ctrl.write(b"G1X\r\n")  # Reading without prefix
            ctrl.write(b"T4X\r\n")
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
        idn = decode_IDN(interface.write_readline("*IDN?\n"))
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
    else:
        # sensor node
        obj = create_sensor(config, node)
    return {name: obj}


def create_sensor(config, node):
    ctrl_node = node.parent
    while ctrl_node and "sensors" not in ctrl_node:
        ctrl_node = ctrl_node.parent

    ctrl = CTRL.get(node["name"])
    if ctrl is None:
        sensor_names = [sensor_node["name"] for sensor_node in ctrl_node["sensors"]]
        ctrl = Multimeter(ctrl_node)
        for s_name in sensor_names:
            CTRL[s_name] = ctrl
    obj = ctrl.Sensor(node, ctrl)
    return obj
