# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Keithley meters.

YAML_ configuration example:

.. code-block:: yaml

    plugin: keithley               # (1)
    name: k_ctrl_1                 # (2)
    class: Ammeter                 # (3)
    model: 6485                    # (4)
    auto_zero: False               # (5)
    display: False                 # (6)
    zero_check: False              # (7)
    zero_correct: False            # (8)
    gpib:                          # (9)
      url: enet://gpibid31eh
      pad: 12
    sensors:                       # (10)
    - name: mondio                 # (11)
      address: 1                   # (12)
      current_dc_nplc: 0.1         # (13)
      current_dc_auto_range: False # (14)

#. plugin name (mandatory: keithley)
#. controller name (mandatory). Some controller settings are needed. To hook the
   settings to the controller we use the controller name. That is why it is
   mandatory
#. plugin class (mandatory)
#. controller model (optional. default: discover by asking instrument *IDN)
#. auto-zero enabled (optional, default: False)
#. display enabled (optional, default: False)
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
from bliss.config.settings import HashSetting
from bliss.comm.exceptions import CommunicationError
from bliss.comm.scpi import Cmd as SCPICmd
from bliss.comm.scpi import Commands as SCPICommands
from bliss.comm.scpi import BaseDevice as BaseDeviceSCPI

from .keithley_scpi_mapping import COMMANDS as SCPI_COMMANDS
from .keithley_scpi_mapping import MODEL_COMMANDS as SCPI_MODEL_COMMANDS


class KeithleySCPI(BaseDeviceSCPI):
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


class Sensor(SamplingCounter):
    def __init__(self, config, controller):
        name = config["name"]
        SamplingCounter.__init__(self, name, controller)
        self.__controller = controller
        self.config = config
        self.address = int(config["address"])
        self.index = self.address - 1
        self.controller.initialize_sensor(self)
        self.__init()

    @property
    def controller(self):
        return self.__controller

    def __int__(self):
        return self.address

    def __init(self):
        for attr_name in [
            "get_auto_range",
            "set_auto_range",
            "get_nplc",
            "set_nplc",
            "get_range",
            "set_range",
        ]:
            try:
                attr = getattr(self, attr_name)
            except AttributeError:
                pass
            else:
                setattr(self, attr_name, attr)

    def __getattr__(self, name):
        attr = getattr(self.controller, name)
        return functools.partial(attr, self)

    def measure(self, func=None):
        return self.controller.measure(func=func)[self.index]

    def data(self):
        return self.controller.data()[self.index]

    def get_meas_func(self):
        return self.controller.get_meas_func()

    def set_meas_func(self, funcname):
        return self.controller.set_meas_func(funcname)


class BaseAcquisition(object):
    def __init__(self, keithley, acq_time, channel):
        self.keithley = keithley
        self.channel = channel
        self.acq_time = acq_time
        self.start_time = None
        self.end_time = None
        self.acq_task = None
        self.value = None
        self.__prepared = False

    @property
    def total_time(self):
        return self.end_time - self.start_time

    def prepare(self):
        self._prepare()
        self.__prepared = True

    def _do_acq(self):
        raise NotImplementedError

    def _prepare(self):
        raise NotImplementedError

    def __on_acq_finished(self, task):
        self.end_time = time.time()
        self.acq_task = None

    def __set_value(self, value):
        self.value = value

    def start(self):
        if not self.__prepared:
            raise RuntimeError("Need prepare before start")
        self.__prepared = False
        self.start_time = time.time()
        self.acq_task = gevent.spawn(self._do_acq)
        self.acq_task.link(self.__on_acq_finished)
        self.acq_task.link_value(self.__set_value)
        return self.acq_task

    def abort(self):
        if self.acq_task is not None:
            self.acq_task.kill()
            self.acq_task.join()
            self.keithley.abort()

    def get_value(self):
        if self.acq_task is not None:
            return self.acq_task.get()
        raise ValueError("no value")


class HardwareAcquisition(BaseAcquisition):
    """
    keithley acquisition where integration is done by the keithley itself
    using its internal buffer.
    Limited to 2500 points
    """

    def _calc(self, acq_time=None):
        nplc = self.keithley.get_current_dc_nplc(self.channel)
        if acq_time is None:
            nb_points = 0
        else:
            nb_points = int(acq_time * 1000 / (2.96 + 3 * (nplc * 20 + 1.94)))
            nb_points = max(1, nb_points)
            acq_time = acq_time + 3 * 20 * nplc / 1000
        if nb_points > 2499:
            raise ValueError(
                "cannot perform an acquisition of more "
                "than 2499 points (calculated %d)" % nb_points
            )
        return nb_points, acq_time

    def _prepare(self):
        nb_points, acq_time = self._calc(self.acq_time)
        self.nb_points, self.real_acq_time = nb_points, acq_time
        keithley = self.keithley
        keithley._logger.info(
            "nb points=%s; effective acq. time=%s", nb_points, acq_time
        )

        if nb_points == 0:
            raise RuntimeError("continuous acquisition not supported")
        elif nb_points == 1:
            start = time.time()
            # activate one-shot measurement
            self.keithley("CONF")
        else:
            keithley(
                "ABOR",  # abort whatever keithley is doing
                "TRAC:CLE",  # empty buffer
                "*OPC?",
            )  # synchronize
            keithley(
                "TRIG:DEL 0",  # no trigger delay
                "TRIG:COUN %d" % nb_points,  # nb of points to trig
                "TRAC:POIN %d" % nb_points,  # nb of points to store
                "TRAC:FEED:CONT NEXT",  # use buffer
                "*OPC?",
            )  # synchronize

    def _do_acq(self):
        if self.nb_points == 0:
            pass
        else:
            # start acquisition
            self.keithley("INIT")
        gevent.sleep(max(0, self.real_acq_time - 0.5))
        # synchronize
        self.keithley["*OPC"]
        try:
            if self.nb_points == 1:
                value = self.keithley["FETCH"]
            else:
                value = self.keithley["CALC3:DATA"]
        except ValueError:
            value = float("nan")
        #        finally:
        #            self.keithley('TRAC:FEED:CONT NEV')
        return value


class SoftwareAcquisition(BaseAcquisition):
    def _prepare(self):
        self.keithley.set_meas_func()

    def _do_acq(self):
        buff = []
        t0, acq_time = time.time(), self.acq_time
        while (time.time() - t0) < acq_time:
            try:
                data = self.keithley["READ"]
            except ValueError:
                data = float("nan")
            buff.append(data)
        self.buffer = numpy.array(buff)
        return numpy.average(self.buffer)


def read_cmd(name, settings=None):
    def read(self):
        value = self[name]
        if settings:
            self.settings[settings] = value
        return value

    read.__name__ = "get_" + name.lower().replace(":", "_")
    return read


def write_cmd(name, settings=None):
    def write(self, value=None):
        if value is None and settings:
            value = self.settings[settings]
        self[name] = value
        if settings:
            self.settings[settings] = value

    write.__name__ = "set_" + name.lower().replace(":", "_")
    return write


def cmd(name, settings=True):
    return read_cmd(name, settings=settings), write_cmd(name, settings=settings)


def read_sensor_cmd(name, settings=None):
    def read(self, sensor):
        address = int(sensor)
        cmd = self._sensor_cmd(sensor, name)
        value = self[cmd]
        if settings:
            value = self.sensor_settings[address][settings]
        return value

    read.__name__ = "get_" + name
    return read


def write_sensor_cmd(name, settings=None):
    def write(self, sensor, value=None):
        address = int(sensor)
        cmd = self._sensor_cmd(sensor, name)
        if value is None:
            if settings:
                value = self.sensor_settings[address][settings]
        self[cmd] = value
        if settings:
            self.sensor_settings[address][settings] = value

    return write


def sensor_cmd(name, settings=None):
    return (
        read_sensor_cmd(name, settings=settings),
        write_sensor_cmd(name, settings=settings),
    )


def read_sensor_meas_cmd(name, settings=None):
    def read(self, sensor, func=None):
        address = int(sensor)
        cmd = self._meas_func_sensor_cmd(sensor, name, func)
        value = self[cmd]
        if settings:
            sname = self._meas_func_settings_name(settings, func)
            value = self.sensor_settings[address][sname]
        return value

    read.__name__ = "get_" + name
    return read


def write_sensor_meas_cmd(name, settings=None):
    def write(self, sensor, value=None, func=None):
        address = int(sensor)
        cmd = self._meas_func_sensor_cmd(sensor, name, func)
        if settings:
            sname = self._meas_func_settings_name(settings, func)
        else:
            sname = None
        if value is None:
            if sname:
                value = self.sensor_settings[address][sname]
        self[cmd] = value
        if sname:
            self.sensor_settings[address][sname] = value

    write.__name__ = "set_" + name
    return write


def sensor_meas_cmd(name, settings=None):
    return (
        read_sensor_meas_cmd(name, settings=settings),
        write_sensor_meas_cmd(name, settings=settings),
    )


class BaseMultimeter(KeithleySCPI):
    """"""

    HARD_INTEG, SOFT_INTEG = "HARDWARE", "SOFTWARE"

    DefaultConfig = {
        "auto_zero": False,
        "display_enable": False,
        "meas_func": "CURR:DC",
        "integration_mode": SOFT_INTEG,
    }

    DefaultSensorConfig = {}

    MeasureFunctions = SCPICommands()

    Sensor = Sensor
    SoftwareAcquisition = SoftwareAcquisition
    HardwareAcquisition = HardwareAcquisition

    def __init__(self, config, interface=None):
        kwargs = dict(config)
        if interface:
            kwargs["interface"] = interface
        self.name = config["name"]
        self.config = config
        self.__active_acq = None
        super(BaseMultimeter, self).__init__(**kwargs)
        defaults = {}
        for key, value in self.DefaultConfig.items():
            defaults[key] = config.get(key, value)
        k_setting_name = "multimeter." + self.name
        self.settings = HashSetting(k_setting_name, default_values=defaults)
        self.sensor_settings = {}

    def __str__(self):
        return "{0}({1})".format(self.__class__.__name__, self.name)

    def initialize(self):
        self("*RST", "*OPC?")
        with self:
            self.set_meas_func()
            self.set_display_enable()
            self.set_auto_zero()
        self._initialize()
        self("*OPC?")

    def initialize_sensor(self, sensor):
        address = int(sensor)
        if address in self.sensor_settings:
            return
        setting_name = "multimeter.{0}".format(sensor.name)
        defaults = {}
        for key, value in self.DefaultSensorConfig.items():
            defaults[key] = sensor.config.get(key, value)
        settings = HashSetting(setting_name, default_values=defaults)
        self.sensor_settings[address] = settings
        with self:
            self._initialize_sensor(sensor)

    def _initialize_sensor(self, sensor):
        pass

    def _meas_func(self, func=None):
        if func is None:
            func = self.settings["meas_func"]
        return self.MeasureFunctions[func]["max_command"]

    def _meas_func_settings_name(self, name, func=None):
        func = self._meas_func(func).replace(":", "_")
        return "{0}_{1}".format(func, name).lower()

    def _meas_func_sensor_cmd(self, sensor, param, func=None):
        func = self._meas_func(func)
        return "SENS%d:%s:%s" % (sensor, func, param)

    def _sensor_cmd(self, sensor, param):
        return "SENS%d:%s" % (sensor, param)

    def get_meas_func(self):
        func = self["CONF"]
        func = func.replace('"', "")
        return self.MeasureFunctions[func]["max_command"]

    def set_meas_func(self, func=None):
        func = self._meas_func(func)
        self("CONF:" + func)
        self.settings["meas_func"] = func

    get_display_enable, set_display_enable = cmd("DISP:ENAB", "display_enable")
    get_auto_zero, set_auto_zero = cmd("SYST:AZER", "auto_zero")

    get_nplc, set_nplc = sensor_meas_cmd("NPLC", "nplc")
    get_auto_range, set_auto_range = sensor_meas_cmd("RANG:AUTO", "auto_range")

    def measure(self, func=None):
        func = self._meas_func(func)
        return self["MEAS:" + func]

    def read(self):
        return self["READ"]

    def read_all(self, *counters):
        values = self.read()
        return [values[int(cnt) - 1] for cnt in counters]

    def data(self):
        return self["DATA"]

    def abort(self):
        return self("ABOR", "OPC?")

    def set_integration_mode(self, mode):
        self.settings["integration_mode"] = mode

    def get_integration_mode(self):
        return self.settings["integration_mode"]

    def create_acq(self, acq_time=None, channel=1, integ_mode=None):
        integ_mode = integ_mode or self.get_integration_mode()
        if integ_mode == self.HARD_INTEG:
            klass = self.HardwareAcquisition
        elif integ_mode == self.SOFT_INTEG:
            klass = self.SoftwareAcquisition
        return klass(self, acq_time, channel)

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


class BaseAmmeter(BaseMultimeter):

    MeasureFunctions = SCPICommands({"CURRent[:DC]": SCPICmd()})

    DefaultSensorConfig = dict(
        BaseMultimeter.DefaultSensorConfig,
        current_dc_auto_range=False,
        current_dc_nplc=0.1,
    )

    get_current_dc_nplc, set_current_dc_nplc = sensor_cmd(
        "CURR:DC:NPLC", "current_dc_nplc"
    )
    get_current_dc_auto_range, set_current_dc_auto_range = sensor_cmd(
        "CURR:DC:RANG:AUTO", "current_dc_auto_range"
    )

    def _initialize_sensor(self, sensor):
        super(BaseAmmeter, self)._initialize_sensor(sensor)
        self.set_current_dc_auto_range(sensor)
        self.set_current_dc_nplc(sensor)

    get_range = read_sensor_cmd("CURRent:RANGe")


class Ammeter6485(BaseAmmeter):

    DefaultConfig = dict(
        BaseAmmeter.DefaultConfig, zero_check=False, zero_correct=False
    )

    def _initialize(self):
        with self:
            self["FORM:ELEM"] = [
                "READ"
            ]  # just get the current when you read (no timestamp)
            self["CALC3:FORM"] = "MEAN"  # buffer statistics is mean
            self["TRAC:FEED"] = "SENS"  # source of reading is sensor
            self.set_zero_check()
            self.set_zero_correct()

    get_zero_check, set_zero_check = cmd("SYST:ZCH", "zero_check")
    get_zero_correct, set_zero_correct = cmd("SYST:ZCOR", "zero_correct")

    def zero_correct(self):
        """Zero correct procedure"""
        zero_check = self.settings["zero_check"]
        zero_correct = self.settings["zero_correct"]
        with self:
            self.set_zero_check(True)  # zero check must be enabled
            self.set_zero_correct(False)  # zero correct state must be disabled
            self("INIT")  # trigger a reading
            self("SYST:ZCOR:ACQ")  # acquire zero correct value
            self.set_zero_correct(zero_correct)  # restore zero correct state
            self.set_zero_check(zero_check)  # restore zero check

    def set_range(self, sensor, range_value):
        """
        Select a fixed measure range
        """
        address = int(sensor)
        cmd = self._sensor_cmd(sensor, "CURRent:RANGe:UPPer")
        possible_range = [2e-9, 20e-9, 200e-9, 2e-6, 20e-6, 200e-6, 2e-3, 20e-3]
        for value in possible_range:
            if value >= range_value:
                break

        self.set_auto_range(sensor, False)
        self[cmd] = value
        return value


class Ammeter6482(BaseAmmeter):
    def _initialize(self):
        with self:
            # should it not be FORM:ELEM instead of FORM:ELEM:TRAC ?
            self["FORM:ELEM:TRAC"] = ["CURR1", "CURR2"]
            self["CALC8:FORM"] = "MEAN"  # buffer statistics is mean


class Multimeter6514(BaseMultimeter):

    MeasureFunctions = SCPICommands(
        {
            "VOLTage[:DC]": SCPICmd(),
            "CURRent[:DC]": SCPICmd(),
            "RESistance": SCPICmd(),
            "CHARge": SCPICmd(),
        }
    )
    DefaultSensorConfig = dict(
        BaseMultimeter.DefaultSensorConfig,
        current_dc_auto_range=False,
        current_dc_nplc=0.1,
        voltage_dc_auto_range=False,
        voltage_dc_nplc=0.1,
    )

    get_current_dc_nplc, set_current_dc_nplc = sensor_cmd(
        "CURR:DC:NPLC", "current_dc_nplc"
    )
    get_current_dc_auto_range, set_current_dc_auto_range = sensor_cmd(
        "CURR:DC:RANG:AUTO", "current_dc_auto_range"
    )
    get_voltage_dc_nplc, set_voltage_dc_nplc = sensor_cmd(
        "VOLT:DC:NPLC", "voltage_dc_nplc"
    )
    get_voltage_dc_auto_range, set_voltage_dc_auto_range = sensor_cmd(
        "VOLT:DC:RANG:AUTO", "voltage_dc_auto_range"
    )
    get_resistance_nplc, set_resistance_nplc = sensor_cmd("RES:NPLC", "resistance_nplc")
    get_resistance_auto_range, set_resistance_auto_range = sensor_cmd(
        "RES:RANG:AUTO", "resistance_auto_range"
    )
    get_charge_nplc, set_charge_nplc = sensor_cmd("CHAR:NPLC", "charge_nplc")
    get_charge_auto_range, set_charge_auto_range = sensor_cmd(
        "CHAR:RANG:AUTO", "charge_auto_range"
    )

    get_range = read_sensor_meas_cmd("RANG")

    def _initialize(self):
        with self:
            self["FORM:ELEM"] = [
                "READ"
            ]  # just get the current when you read (no timestamp)
            self["CALC3:FORM"] = "MEAN"  # buffer statistics is mean
            self["TRAC:FEED"] = "SENS"  # source of reading is sensor
            self.set_zero_check()
            self.set_zero_correct()

    get_zero_check, set_zero_check = cmd("SYST:ZCH", "zero_check")
    get_zero_correct, set_zero_correct = cmd("SYST:ZCOR", "zero_correct")

    def zero_correct(self):
        """Zero correct procedure"""
        zero_check = self.settings["zero_check"]
        zero_correct = self.settings["zero_correct"]
        with self:
            self.set_zero_check(True)  # zero check must be enabled
            self.set_zero_correct(False)  # zero correct state must be disabled
            self("INIT")  # trigger a reading
            self("SYST:ZCOR:ACQ")  # acquire zero correct value
            self.set_zero_correct(zero_correct)  # restore zero correct state
            self.set_zero_check(zero_check)  # restore zero check

    def set_range(self, sensor, range_value):
        """
        Select a fixed measure range
        """
        address = int(sensor)
        cmd = self._meas_func_sensor_cmd(sensor, "RANGe:UPPer")
        func = self._meas_func()
        if func == "CURRENT:DC":
            possible_range = [
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
            ]
        elif func == "VOLTAGE:DC":
            possible_range = [2, 20, 200]
        elif func == "RESISTANCE":
            possible_range = [2e3, 20e3, 200e3, 2e6, 20e6, 200e6, 2e9, 20e9, 200e9]
        elif func == "CHARGE":
            possible_range = [20e-9, 200e-9, 2, 20]
        else:
            raise ValueError("Invalid measure function [{0}] !!".format(func))
        for value in possible_range:
            if value >= range_value:
                break

        self.set_auto_range(sensor, False)
        self[cmd] = value
        return value


class Multimeter2000(BaseMultimeter):

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

    get_range, set_range = sensor_meas_cmd("RANGe:UPPer")

    def _initialize(self):
        pass


class AmmeterDDC(object):
    def __init__(self, config):
        self.interface = get_comm(config)
        self.name = config["name"]

    def initialize(self):
        self.interface.write(b"F1X\r\n")  # Amp function
        self.interface.write(b"G0X\r\n")  # Reading with prefix (NDCA<value>)
        self.interface.write(b"T4X\r\n")  # Continuous triggered by X

    def initialize_sensor(self, sensor):
        pass

    def measure(self, func=None):
        # change to '\r\n' will make it faster but we don't know what it does!
        cmd = b"X\r\n"
        return [float(self.interface.write_readline(cmd)[4:])]

    def read_all(self, *counters):
        return self.measure()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class Ammeter6512(AmmeterDDC):
    pass


def Multimeter(config):
    class_name = config["class"]
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
    if class_name in ("Multimeter", "Ammeter"):
        class_name += model
    elif not class_name.endswith(model):
        raise ValueError("class: {0} != model: {1}".format(class_name, model))
    try:
        klass = globals()[class_name]
    except KeyError:
        raise ValueError(
            "Unknown keithley model {} (hint: DDC needs a model "
            "in YAML)".format(model)
        )
    obj = klass(config, **kwargs)
    obj.initialize()
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
    ctrl = config.get(ctrl_node["name"])
    with ctrl:
        obj = Sensor(node, ctrl)
    return obj


def main():
    """
    Start a Keithley console.

    The following example will start a Keithley console with one Keithley
    instrument called *k*::

        $ python -m bliss.controllers.keithley gpib --pad=15 enet://gpibhost

        keithley> print( k['*IDN?'] )

     """

    import sys
    import logging
    import argparse

    try:
        import serial
    except:
        serial = None

    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="keithley model (ex: 6482) [default: auto discover]",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="info",
        choices=["debug", "info", "warning", "error"],
        help="log level [default: info]",
    )
    parser.add_argument(
        "--scpi-log-level",
        type=str,
        default="info",
        choices=["trace", "debug", "info", "warning", "error"],
        help="log level for scpi object [default: info]",
    )
    parser.add_argument(
        "--keithley-log-level",
        type=str,
        default="info",
        choices=["trace", "debug", "info", "warning", "error"],
        help="log level for keithley object [default: info]",
    )
    parser.add_argument(
        "--gevent",
        action="store_true",
        default=False,
        help="enable gevent in console [default: False]",
    )

    subparsers = parser.add_subparsers(
        title="object/connection",
        dest="connection",
        description="config object name or valid type of connections",
        help="choose keithley config object name or type of connection",
    )
    config_parser = subparsers.add_parser("config", help="keithey config object")
    config_parser.add_argument("name", help="config object name")

    gpib_parser = subparsers.add_parser("gpib", help="GPIB connection")
    add = gpib_parser.add_argument
    add(
        "url", type=str, help="gpib instrument url (ex: gpibhost, enet://gpibhost:5000)"
    )
    add("--pad", type=int, required=True, help="primary address")
    add("--sad", type=int, default=0, help="secondary address [default: 0]")
    add(
        "--tmo",
        type=int,
        default=10,
        help="GPIB timeout (GPIB tmo unit) [default: 11 (=1s)]",
    )
    add("--eos", type=str, default="\n", help=r"end of string [default: '\n']")
    add("--timeout", type=float, default=1.1, help="socket timeout [default: 1.1]")

    tcp_parser = subparsers.add_parser("tcp", help="TCP connection")
    add = tcp_parser.add_argument
    add("url", type=str, help="TCP instrument url (ex: keith6485:25000)")

    if serial:
        serial_parser = subparsers.add_parser("serial", help="serial line connection")
        add = serial_parser.add_argument
        add(
            "port",
            type=str,
            help="serial instrument port (ex: rfc2217://.., ser2net://..)",
        )
        add("--baudrate", type=int, default=9600, help="baud rate")
        add(
            "--bytesize",
            type=int,
            choices=[6, 7, 8],
            default=serial.EIGHTBITS,
            help="byte size",
        )
        add(
            "--parity",
            choices=list(serial.PARITY_NAMES.keys()),
            default=serial.PARITY_NONE,
            help="parity type",
        )
        add("--timeout", type=float, default=5, help="timeout")
        add(
            "--stopbits",
            type=float,
            choices=[1, 1.5, 2],
            default=serial.STOPBITS_ONE,
            help="stop bits",
        )
        add("--xonxoff", action="store_true", default=False, help="")
        add("--rtscts", action="store_true", default=False, help="")
        add("--write-timeout", dest="writeTimeout", type=float, default=None, help="")
        add("--dsrdtr", action="store_true", default=False, help="")
        add(
            "--interchar-timeout",
            dest="interCharTimeout",
            type=float,
            default=None,
            help="",
        )
        add("--eol", type=str, default="\n", help="end of line [default: '\\n']")

    args = parser.parse_args()
    vargs = vars(args)

    model = vargs.pop("model", None)
    log_level = getattr(logging, vargs.pop("log_level").upper())
    keithley_log_level = vargs.pop("keithley_log_level").upper()
    scpi_log_level = vargs.pop("scpi_log_level").upper()
    logging.basicConfig(
        level=log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    gevent_arg = vargs.pop("gevent")

    conn = vargs.pop("connection")
    local = {}
    if conn == "config":
        from bliss.config.static import get_config

        config = get_config()
        name = vargs["name"]
        keithley = create_objects_from_config_node(config, config.get_config(name))[
            name
        ]
        if isinstance(keithley, Sensor):
            sensor = keithley
            keithley = sensor.controller
            local["s"] = sensor
    else:
        kwargs = {conn: vargs, "model": model}
        keithley = KeithleySCPI(**kwargs)
    local["k"] = keithley
    keithley._logger.setLevel(keithley_log_level)
    keithley.language._logger.setLevel(scpi_log_level)
    keithley.interface._logger.setLevel(scpi_log_level)

    sys.ps1 = "keithley> "
    sys.ps2 = len(sys.ps1) * "."

    if gevent_arg:
        try:
            from gevent.monkey import patch_sys
        except ImportError:
            mode = "no gevent"
        else:
            patch_sys()

    import code

    mode = not gevent_arg and "interactive, no gevent" or "gevent"
    banner = "\nWelcome to Keithley console " "(connected to {0}) ({1})\n".format(
        keithley, mode
    )
    code.interact(banner=banner, local=local)


if __name__ == "__main__":
    main()
