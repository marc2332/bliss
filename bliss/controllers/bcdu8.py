import gevent

from bliss import global_map
from bliss.comm.util import get_comm
from bliss.common.greenlet_utils import protect_from_kill
from bliss.common.counter import SamplingCounter, SamplingMode
from bliss.controllers.counter import SamplingCounterController
from bliss.common.axis import AxisState
from bliss.controllers.motor import Controller


class Bcdu8:
    def __init__(self, name, config_tree):

        self._name = name

        # Commands
        self.calib = Bcdu8CommandCalib(self)
        self.chan = Bcdu8CommandChan(self)
        self.freq = Bcdu8CommandFreq(self)
        self.delay = Bcdu8CommandDelay(self)
        self.delaylm = Bcdu8CommandDelayLm(self)
        self.rffreq = Bcdu8CommandRffreq(self)
        self.rfmode = Bcdu8CommandRfmode(self)
        self.rflock = Bcdu8CommandRflock(self)
        self.gfdelay = Bcdu8CommandGfdelay(self)
        self.gfdelaylm = Bcdu8CommandGfdelaylm(self)
        self.gshift = Bcdu8CommandGshift(self)
        self.pscaler = Bcdu8CommandPscaler(self)
        self.monitor = Bcdu8CommandMonitor(self)
        self.sync = Bcdu8CommandSync(self)
        self.gate = Bcdu8CommandGate(self)
        self.fdelay = Bcdu8CommandFdelay(self)
        self.fdelaylm = Bcdu8CommandFdelayLm(self)

        # Communication
        self._cnx = get_comm(config_tree, timeout=3)
        global_map.register(self, children_list=[self._cnx])

    def __info__(self):
        info_str = f"BCDU8\n\n"
        info_str += f"Name:   {self._name}\n"
        info_str += f"Host:   {self._cnx._host}\n"
        info_str += f"Socket: {self._cnx._port}\n\n"
        info_str += self._comm("?CONFIG")
        return info_str

    def help(self):
        ret = self._comm("?HELP")
        print(ret)

    def command(self, cmd):
        return self._comm(cmd)

    """
    Check Methods
    """

    def _check_unit(self, unit, cmd):
        if unit.lower() not in ["ps", "ns", "us", "ms", "s"]:
            raise RuntimeError(f"{self._name}.{cmd} - unit - [ps | ns | us | ms | s]")

    def _check_output_first(self, output, cmd):
        if output.upper() not in ["O1", "O2"]:
            raise RuntimeError(f"{self._name}.{cmd} - output - [O1 | O2]")

    def _check_output_all(self, output, cmd):
        if output.upper() not in ["O1", "O2", "O2", "O3", "O4", "O5", "O6", "O7", "O8"]:
            raise RuntimeError(
                f"{self._name}.{cmd} - output - [O1 | O2 | O3 | O4 | O5 | O6 | O7 | O8]"
            )

    def _check_polarity(self, polarity, cmd):
        if polarity not in ["NORMAL", "INVERTED"]:
            raise RuntimeError(f"{self._name}.{cmd} - polarity - [NORMAL | INVERTED]")

    def _check_state_polarity(self, polarity, cmd):
        if polarity not in ["OFF", "NORMAL", "INVERTED"]:
            raise RuntimeError(
                f"{self._name}.{cmd} - polarity - [OFF | NORMAL | INVERTED]"
            )

    def _check_period(self, period, cmd):
        if period < 8 or period > 71303168:
            raise RuntimeError(
                f"{self._name}.{cmd} - period - [8 - 71303168 (34x32x256x256)]"
            )

    def _check_offon(self, offon, cmd):
        if offon.lower() not in ["off", "on"]:
            raise RuntimeError(f"{self._name}.{cmd} - offon - [off | on]")

    def _check_mode(self, mode, cmd):
        if mode.lower() not in ["user", "auto"]:
            raise RuntimeError(f"{self._name}.{cmd} - mode - [user | auto]")

    def _check_signal(self, signal, cmd):
        if signal.upper() not in ["PSCALER", "RF/8", "RF/16", "RF/31"]:
            raise RuntimeError(
                f"{self._name}.{cmd} - signal - [PSCALER | RF/8 | RF/16 | RF/31]"
            )

    """
    Ethernet Communication
    """

    def _comm_ack(self, msg):
        return self.comm("#" + msg)

    @protect_from_kill
    def _comm(self, cmd, timeout=None, text=True):
        self._cnx.open()
        with self._cnx._lock:
            self._cnx._write((cmd + "\r\n").encode())
            if cmd.startswith("?") or cmd.startswith("#"):
                msg = self._cnx._readline(timeout=timeout)
                cmd = cmd.strip("#").split(" ")[0]
                msg = msg.replace((cmd + " ").encode(), "".encode())
                if msg.startswith("$".encode()):
                    msg = self._cnx._readline(
                        # transaction=transaction,
                        # clear_transaction=False,
                        eol="$\n",
                        timeout=timeout,
                    )
                    return msg.strip("$\n".encode()).decode()
                elif msg.startswith("ERROR".encode()):
                    raise RuntimeError(msg.decode())
                if text:
                    return (msg.strip("\r\n".encode())).decode()
                else:
                    return msg.strip("\r\n".encode())


class Bcdu8CommandCalib:
    def __init__(self, bcdu8):
        self._bcdu8 = bcdu8
        self._name = "CALIB"

    def __info__(self):
        desc = "Command:\n"
        desc += '    calib.set({"O1"|"O2"}, <calValue>, {"ps"|"ns"|"us"|"ms"|"s"})\n'
        desc += "Query:\n"
        desc += '    calib.get({"O1"|"O2"} , {"ps"|"ns"|"us"|"ms"|"s"})'
        return desc

    def set(self, output, calValue, unit):
        self._bcdu8._check_output_first(output, "calib")
        self._bcdu8._check_unit(unit, "calib")
        self._bcdu8._comm(f"#{self._name} {output} {calValue} {unit}")

    def get(self, output, unit):
        self._bcdu8._check_output_first(output, "calib")
        self._bcdu8._check_unit(unit, "calib")
        return self._bcdu8._comm(f"?{self._name} {output} {unit}")


class Bcdu8CommandChan:
    def __init__(self, bcdu8):
        self._bcdu8 = bcdu8
        self._name = "CHAN"

    def __info__(self):
        desc = "Command:\n"
        desc += '    chan.set("O<n>", "[{NORMAL|INVERTED}]", "[<period>]", "[<width>]", "[<delay>]")\n'
        desc += "       or\n"
        desc += '    chan.set("O<n>" "{OFF|ON}")\n'
        desc += "Query:\n"
        desc += '    chan.get("O<n>")'
        return desc

    def set(
        self, output, offon=None, polarity=None, period=None, width=None, delay=None
    ):
        # TO DO: check width and delay
        self._bcdu8._check_output_all(output, "chan")
        cmd = f"#{self._name} {output}"
        if offon is not None:
            self._bcdu8._check_offon(offon, "chan")
            cmd += f" {offon}"
        else:
            if polarity is not None:
                self._bcdu8._check_polarity(polarity, "chan")
                cmd += " {polarity}"
            if period is not None:
                self._bcdu8._check_period(period, "chan")
                cmd += " PERIOD {period}"
            if width is not None:
                cmd += " WIDTH {width}"
            if delay is not None:
                cmd += " DELAY {delay}"
        self._bcdu8._comm(cmd)

    def get(self, output):
        self._bcdu8._check_output_all(output, "chan")
        return self._bcdu8._comm(f"?{self._name} {output}")


class Bcdu8CommandFreq:
    def __init__(self, bcdu8):
        self._bcdu8 = bcdu8
        self._name = "FREQ"

    def __info__(self):
        desc = "Query:\n"
        desc += '    freq.get("O<n>")'
        return desc

    def get(self, output=None):
        if output is not None:
            self._bcdu8._check_output_all(output, "freq")
            return self._bcdu8._comm(f"?{self._name} {output}")
        return self._bcdu8._comm(f"?{self._name} ")


class Bcdu8CommandDelay:
    def __init__(self, bcdu8):
        self._bcdu8 = bcdu8
        self._name = "DELAY"

    def __info__(self):
        desc = "Command:\n"
        desc += '    delay.set("O<n>", <chanDelay>, [{"ps"|"ns"|"us"|"ms"|"s"}])\n'
        desc += "Query:\n"
        desc += '    delay.get("O<n>", [{"ps"|"ns"|"us"|"ms"|"s"}])\n'
        desc += "       or\n"
        desc += '    delay.get("{O1|O2} #")'
        return desc

    def set(
        self, output, offon=None, polarity=None, period=None, width=None, delay=None
    ):
        # TO DO: check width and delay
        self._bcdu8._check_output_all(output, "chan")
        cmd = f"#{self._name} {output}"
        if offon is not None:
            self._bcdu8_check_offon(offon, "chan")
            cmd += f" {offon}"
        else:
            if polarity is not None:
                self._bcdu8_check_polarity(polarity, "chan")
                cmd += " {polarity}"
            if period is not None:
                self._bcdu8_check_period(period, "chan")
                cmd += " PERIOD {period}"
            if width is not None:
                cmd += " WIDTH {width}"
            if delay is not None:
                cmd += " DELAY {delay}"
        self._bcdu8._comm(cmd)

    def get(self, output, unit=None):
        if output.upper() in ["O1 #", "O2 #"]:
            return self._bcdu8._comm(f"?{self._name} {output}")
        else:
            self._bcdu8._check_output_all(output, "delay")
            if unit is not None:
                self._bcdu8._check_unit(unit, "delay")
                return self._bcdu8._comm(f"?{self._name} {output} {unit}")
            else:
                return self._bcdu8._comm(f"?{self._name} {output} #")


class Bcdu8CommandDelayLm:
    def __init__(self, bcdu8):
        self._bcdu8 = bcdu8
        self._name = "DELAYLM"

    def __info__(self):
        desc = "Query:\n"
        desc += '    delaylm.get("O<n>", [{"ps"|"ns"|"us"|"ms"|"s"}])\n'
        return desc

    def get(self, output, unit):
        self._bcdu8._check_output_all(output, "delaylm")
        self._bcdu8._check_unit(unit, "delaylm")
        return self._bcdu8._comm(f"?{self._name} {output} {unit}")


class Bcdu8CommandRffreq:
    def __init__(self, bcdu8):
        self._bcdu8 = bcdu8
        self._name = "RFFREQ"

    def __info__(self):
        desc = "Command:\n"
        desc += '    rffreq.set("[<RFfrequency>]")\n'
        desc += "Query:\n"
        desc += "    rffreq.get()"
        return desc

    def set(self, freq):
        self._bcdu8._comm(f"#{self._name} {freq}")

    def get(self):
        return self._bcdu8._comm(f"?{self._name}")


class Bcdu8CommandRfmode:
    def __init__(self, bcdu8):
        self._bcdu8 = bcdu8
        self._name = "RFMODE"

    def __info__(self):
        desc = "Command:\n"
        desc += '    rfmode.set([{"USER"|"AUTO"}])\n'
        desc += "Query:\n"
        desc += "    rfmode.get()"
        return desc

    def set(self, mode):
        self._bcdu8._check_mode(mode, "rfmode")
        self._bcdu8._comm(f"#{self._name} {mode}")

    def get(self):
        return self._bcdu8._comm(f"?{self._name}")


class Bcdu8CommandRflock:
    def __init__(self, bcdu8):
        self._bcdu8 = bcdu8
        self._name = "RFLOCK"

    def __info__(self):
        desc = "Command:\n"
        desc += "    rflock.set()\n"
        desc += "Query:\n"
        desc += "    rflock.get()"
        return desc

    def set(self):
        return self._bcdu8._comm(f"#{self._name}")

    def get(self):
        return self._bcdu8._comm(f"?{self._name}")


class Bcdu8CommandGfdelay:
    def __init__(self, bcdu8):
        self._bcdu8 = bcdu8
        self._name = "GFDELAY"

    def __info__(self):
        desc = "Command:\n"
        desc += '    gfdelay.set(<globalDelay>, [{"#"|"ps"|"ns"|"us"|"ms"|"s"}])\n'
        desc += "       or\n"
        desc += '    gfdelay.set("#<fineDelaySteps>")\n'
        desc += "Query:\n"
        desc += '    gfdelay.get([{"ps"|"ns"|"us"|"ms"|"s"}])\n'
        desc += "       or\n"
        desc += '    gfdelay.get("#")'
        return desc

    def set(self, delay, unit=None):
        if unit is not None:
            self._bcdu8._check_unit(unit, "gfdelay")
            self._bcdu8._comm(f"#{self._name} {delay} {unit}")
        else:
            self._bcdu8._comm(f"#{self._name} {delay}")

    def get(self, output):
        if output == "#":
            return self._bcdu8._comm(f"?{self._name} {output}")
        else:
            self._bcdu8._check_unit(output, "gfdelay")
            return self._bcdu8._comm(f"?{self._name} {output}")


class Bcdu8CommandGfdelaylm:
    def __init__(self, bcdu8):
        self._bcdu8 = bcdu8
        self._name = "GFDELAYLM"

    def __info__(self):
        desc = "Query:\n"
        desc += '    gfdelaylm.get([{"#"|"ps"|"ns"|"us"|"ms"|"s"}])\n'
        return desc

    def get(self, output):
        if output == "#":
            return self._bcdu8._comm(f"?{self._name} {output}")
        else:
            self._bcdu8._check_unit(output, "gfdelay")
            return self._bcdu8._comm(f"?{self._name} {output}")


class Bcdu8CommandGshift:
    def __init__(self, bcdu8):
        self._bcdu8 = bcdu8
        self._name = "GSHIFT"

    def __info__(self):
        desc = "Command:\n"
        desc += "    gshift.set(<nCycles>)\n"
        return desc

    def set(self, ncycles):
        self._bcdu8._comm(f"#{self._name} {ncycles}")


class Bcdu8CommandPscaler:
    def __init__(self, bcdu8):
        self._bcdu8 = bcdu8
        self._name = "PSCALER"

    def __info__(self):
        desc = "Command:\n"
        desc += '    pscaler.set({"AUTO" | <pscalerVal>})\n'
        desc += "Query:\n"
        desc += "    pscaler.get()"
        return desc

    def set(self, value):
        self._bcdu8._comm(f"#{self._name} {value}")

    def get(self):
        return self._bcdu8._comm(f"?{self._name}")


class Bcdu8CommandMonitor:
    def __init__(self, bcdu8):
        self._bcdu8 = bcdu8
        self._name = "MONITOR"

    def __info__(self):
        desc = "Command:\n"
        desc += '    monitor.set({"PSCALER"|"RF/8"|"RF/16"|"RF/31"})\n'
        desc += "Query:\n"
        desc += "    monitor.get()"
        return desc

    def set(self, signal):
        raise NotImplementedError(
            "Cannot set to the fixed divisions of the RF input clock"
        )
        # self._bcdu8._check_signal(signal, "monitor")
        # self._bcdu8._comm(f"{self._name} {signal}")

    def get(self):
        return self._bcdu8._comm(f"?{self._name}")


class Bcdu8CommandSync:
    def __init__(self, bcdu8):
        self._bcdu8 = bcdu8
        self._name = "SYNC"

    def __info__(self):
        desc = "Command:\n"
        desc += '    sync.set(["CLEAR"])\n'
        desc += "Query:\n"
        desc += "    sync.get()"
        return desc

    def set(self, clear=None):
        if clear is None:
            self._bcdu8._comm(f"#{self._name} {clear}")
        elif clear == "CLEAR":
            self._bcdu8._comm(f"#{self._name} {clear}")
        else:
            raise RuntimeError(f"{self._name}.sync [CLEAR]")

    def get(self):
        return self._bcdu8._comm(f"?{self._name}")


class Bcdu8CommandGate:
    def __init__(self, bcdu8):
        self._bcdu8 = bcdu8
        self._name = "GATE"

    def __info__(self):
        desc = "Command:\n"
        desc += '    gate.set("{"OFF"|"NORMAL"|"INVERTED"}")\n'
        desc += "Query:\n"
        desc += "    gate.get()"
        return desc

    def set(self, state):
        self._bcdu8._check_state_polarity(state, "gate")
        self._bcdu8._comm(f"#{self._name} {state}")

    def get(self):
        return self._bcdu8._comm(f"?{self._name}")


class Bcdu8CommandFdelay:
    def __init__(self, bcdu8):
        self._bcdu8 = bcdu8
        self._name = "FDELAY"

    def __info__(self):
        desc = "Command:\n"
        desc += '    fdelay.set("O<n>", <chanDelay>, [{"ps"|"ns"|"us"|"ms"|"s"}])\n'
        desc += "       or\n"
        desc += '    fdelay.set("O<n>", #<fineDelaySteps>)\n'
        return desc

    def set(self, output, delay, unit=None):
        self._bcdu8._check_output_first(output, "fdelay")
        if unit is not None:
            self._bcdu8._check_unit(unit, "fdelay")
            self._bcdu8._comm(f"#{self._name} {output} {delay} {unit}")
        else:
            self._bcdu8._comm(f"#{self._name} {output} {delay}")


class Bcdu8CommandFdelayLm:
    def __init__(self, bcdu8):
        self._bcdu8 = bcdu8
        self._name = "FDELAYLM"

    def __info__(self):
        desc = "Query:\n"
        desc += '    fdelaylm.set("O<n>", [{"#"|"ps"|"ns"|"us"|"ms"|"s"}])\n'
        return desc

    def get(self, output, unit):
        self._bcdu8._check_output_all(output, "fdelaylm")
        if unit == "#":
            return self._bcdu8._comm(f"?{self._name} {output} {unit}")
        else:
            self._bcdu8._check_unit(unit, "fdelaylm")
            return self._bcdu8._comm(f"?{self._name} {output} {unit}")
