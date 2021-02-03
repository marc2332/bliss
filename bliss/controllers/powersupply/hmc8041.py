from bliss.common.counter import SamplingCounter
from bliss.controllers.counter import SamplingCounterController
from bliss.common.protocols import CounterContainer

from bliss.common.utils import autocomplete_property

from bliss.comm.util import get_comm
from bliss.comm.scpi import SCPI, COMMANDS, Commands, StrCmdRO, FloatCmd, OnOffCmd


HMC8041_COMMANDS = Commands(
    COMMANDS,
    {
        "SYSTem:VERSion": StrCmdRO(doc="return SCPI revision level"),
        "*IDN": StrCmdRO(doc="return identification string"),
        # -- measurement commands
        "MEASure[:SCALar]:CURRent[:DC]": FloatCmd(doc="queries the measured current"),
        "MEASure[:SCALar][:VOLTage][:DC]": FloatCmd(doc="queries the measured voltage"),
        "MEASure[:SCALar]:POWer": FloatCmd(doc="queries the measured power"),
        # -- configuration commands
        "[SOURce:]VOLTage[:LEVel][:IMMediate][:AMPLitude]": FloatCmd(
            doc="sets the voltage value"
        ),
        "[SOURce:]CURRent[:LEVel][:IMMediate][:AMPLitude]": FloatCmd(
            doc="sets the current value"
        ),
        "OUTPut[:STATe]": OnOffCmd(doc="activate or deactivate channel"),
        # -- easyramp
        "[SOURce:]VOLTage:RAMP[:STATe]": OnOffCmd(
            doc="activate or deactivate ramp function"
        ),
        "[SOURce:]VOLTage:RAMP:DURation": FloatCmd(
            doc="sets the duration of the voltage ramp"
        ),
    },
)


class HMC8041CounterController(SamplingCounterController):
    TAGS = ["voltage", "current", "power"]
    UNITS = {"voltage": "V", "current": "A", "power": "Ws"}

    def __init__(self, device, config):
        super().__init__(f"{device.name}")
        self.device = device

        cnts_config = config.get("counters")
        if cnts_config is not None:
            for conf in cnts_config:
                name = conf["name"].strip()
                tag = conf["tag"].strip().lower()
                if tag not in self.TAGS:
                    raise ValueError("HMC8041CounterController: invalid tag")
                mode = conf.get("mode", "SINGLE")
                unit = self.UNITS[tag]
                cnt = self.create_counter(SamplingCounter, name, unit=unit, mode=mode)
                cnt.tag = tag

    def read(self, cnt):
        if cnt.tag == "voltage":
            return self.device.voltage
        elif cnt.tag == "current":
            return self.device.current
        elif cnt.tag == "power":
            return self.device.power


class HMC8041(CounterContainer):
    def __init__(self, name, config):
        self.__name = name
        self.__config = config

        self.__comm = get_comm(config)
        self.__scpi = SCPI(self.__comm, commands=HMC8041_COMMANDS)

        self.__cc = HMC8041CounterController(self, config)

    @property
    def name(self):
        return self.__name

    @property
    def comm(self):
        return self.__comm

    @property
    def scpi(self):
        return self.__scpi

    @autocomplete_property
    def counters(self):
        return self.__cc.counters

    def __info__(self):
        info = f"HMC Model     : {self.idn}\n"
        info += f"Communication : {self.__comm}\n\n"
        info += (
            f"Voltage : {self.voltage:.3f} V [setpoint {self.voltage_setpoint:.3f} V]\n"
        )
        info += (
            f"Current : {self.current:.3f} A [setpoint {self.current_setpoint:.3f} A]\n"
        )
        info += f"Power   : {self.power} Ws\n"
        info += f"Output  : {self.output}\n"
        info += f"Ramp    : {self.ramp:3.3s} [duration {self.ramp_duration} sec]\n"
        return info

    @property
    def idn(self):
        return self.__scpi["*IDN"]

    @property
    def voltage(self):
        return self.__scpi["MEAS:VOLT"]

    @property
    def voltage_setpoint(self):
        return self.__scpi["VOLT"]

    @voltage_setpoint.setter
    def voltage_setpoint(self, value):
        self.__scpi["VOLT"] = value

    @property
    def voltage_range(self):
        vmin = self.__scpi.read("VOLT? MIN")[0][1]
        vmax = self.__scpi.read("VOLT? MAX")[0][1]
        return (vmin, vmax)

    @property
    def current(self):
        return self.__scpi["MEAS:CURR"]

    @property
    def current_setpoint(self):
        return self.__scpi["CURR"]

    @current_setpoint.setter
    def current_setpoint(self, value):
        self.__scpi["CURR"] = value

    @property
    def current_range(self):
        vmin = self.__scpi.read("CURR? MIN")[0][1]
        vmax = self.__scpi.read("CURR? MAX")[0][1]
        return (vmin, vmax)

    @property
    def power(self):
        return self.__scpi["MEAS:POW"]

    @property
    def output(self):
        value = self.__scpi["OUTP:STAT"]
        return value and "ON" or "OFF"

    @output.setter
    def output(self, value):
        self.__scpi["OUTP:STAT"] = value

    @property
    def ramp(self):
        value = self.__scpi["VOLT:RAMP:STAT"]
        return value and "ON" or "OFF"

    @ramp.setter
    def ramp(self, value):
        self.__scpi["VOLT:RAMP:STAT"] = value

    @property
    def ramp_duration(self):
        return self.__scpi["VOLT:RAMP:DUR"]

    @ramp_duration.setter
    def ramp_duration(self, value):
        self.__scpi["VOLT:RAMP:DUR"] = value

    @property
    def ramp_duration_range(self):
        vmin = self.__scpi.read("VOLT:RAMP:DUR? MIN")[0][1]
        vmax = self.__scpi.read("VOLT:RAMP:DUR? MAX")[0][1]
        return (vmin, vmax)
