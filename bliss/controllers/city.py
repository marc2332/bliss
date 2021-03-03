import gevent

from bliss import global_map
from bliss.comm.util import get_comm
from bliss.common.greenlet_utils import protect_from_kill


class City:
    def __init__(self, name, config_tree):
        self._name = name

        # Commands
        self.autosync = CityCommandAutosync(self)
        self.burst = CityCommandBurst(self)
        self.dconfig = CityCommandDconfig(self)
        # self.dsync = CityCommandDsync(self)
        self.gate = CityCommandGate(self)
        self.iset = CityCommandIset(self)
        self.ockset = CityCommandOckset(self)
        self.oen = CityCommandOen(self)
        self.omode = CityCommandOmode(self)
        self.opuset = CityCommandOpuset(self)
        self.sgate = CityCommandSgate(self)
        self.usrclk = CityCommandUsrclk(self)

        # Communication
        self._cnx = get_comm(config_tree, timeout=3)
        global_map.register(self, children_list=[self._cnx])

        # Initialization
        self._outputs = [
            "OA1",
            "OA2",
            "OA3",
            "OA4",
            "OA5",
            "OA6",
            "OB1",
            "OB2",
            "OB3",
            "OB4",
            "OB5",
            "OB6",
        ]
        self._outputs_str = "[OA1:OB6]"
        self._sources = ["I1", "I2", "I3", "I4", "S1", "S2", "S3", "S4"]
        self._sources_str = "[I1:4|S1:4]"
        self._onoff = ["ON", "OFF"]
        self._onoff_str = "[ON|OFF]"
        self._yesno = ["YES", "NO"]
        self._yesno_str = "[YES|NO]"
        self._polarity = ["NORMAL", "INVERTED"]
        self._polarity_str = "[NORMAL|INVERTED]"
        self._inputs = ["I1", "I2", "I3", "I4", "ALL"]
        self._inputs_str = "[I1:4|ALL]"
        self._softs = ["S1", "S2", "S3", "S4"]
        self._softs_str = "[S1:4]"
        self._ref = ["I1", "I2", "I3", "I4", "SR"]
        self._ref_str = "[I1:4|SR]"
        self._Vunits = ["V", "mV"]
        self._Vunits_str = "[V|mV]"
        self._Tunits = ["ps", "ns", "us", "ms", "s"]
        self._Tunits_str = "[ps|ns|us|ms|s]"
        self._pattern = ["NONE", "SR", "16B", "4B"]
        self._pattern_str = "[NONE|SR|16B|4B]"
        self._state = ["DEFAULTS", "RESTORE", "SAVE"]
        self._state_str = "[DEFAULTS|RESTORE|SAVE]"
        self._clk = ["WR", "RF", "RFDDS"]
        self._clk_str = "[WR|RF|RFDDS]"
        self._divider_str = "[1:32]"

    def __info__(self):
        info_str = f"CITY\n\n"
        info_str += f"Name:   {self._name}\n"
        info_str += f"Host:   {self._cnx._host}\n"
        info_str += f"Socket: {self._cnx._port}\n\n"
        info_str += self._comm("?DCONFIG")
        return info_str

    def help(self):
        ret = self._comm("?HELP")
        print(ret)

    def monitor(self):
        ret = self._comm("?MONITOR")
        print(ret)

    def state(self):
        ret = self._comm("?STATE")
        print(ret)

    def sync(self, force=True):
        if force:
            self._comm("SYNC FORCE")
        else:
            self._comm("SYNC")

    def osync(self):
        self._comm("OSYNC")

    def version(self):
        print(self._comm("?VERSION"))

    def command(self, cmd):
        return self._comm(cmd)

    """
    Check Methods
    """

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


class CityCommandAutosync:
    def __init__(self, city):
        self._city = city
        self._name = "AUTOSYNC"

    def __info__(self):
        desc = "Command:\n"
        desc += "    autosync.on()\n"
        desc += "    autosync.off()\n"
        desc += "Query:\n"
        desc += "    autosync.get()"
        return desc

    def on(self):
        self._city._comm(f"{self._name} ON")

    def off(self):
        self._city._comm(f"{self._name} OFF")

    def get(self, silent=False):
        ret = self._city._comm(f"?{self._name}")
        if silent:
            return ret
        else:
            print(ret)


class CityCommandBurst:
    """
    The BURST command can configure channels independantely, by list or by groups.
    In this module we choose to configure channels only one by one and to get
    the status of all of them.
    Use the .command method to be more vesatile
    """

    def __init__(self, city):
        self._city = city
        self._name = "BURST"

    def __info__(self):
        desc = "Command:\n"
        desc += f'    burst.set("{self._city._outputs_str}", "{self._city._onoff_str}", count=1)\n'
        desc += "Query:\n"
        desc += "    burst.get()\n"
        return desc

    def set(self, output, onoff, count=1):
        if output.upper() not in self._city._outputs:
            raise ValueError(f'Output not in "{self._city._outputs_str}"')
        if onoff.upper() not in self._city._onoff:
            raise ValueError(f'onoff not in "{self._city._onoff_str}"')
        count = int(abs(count))
        if onoff.upper() == "OFF":
            self._city._comm(f"{self._name} {output} OFF")
        else:
            self._city._comm(f"{self._name} {output} ON {count}")

    def get(self, silent=False):
        ret = self._city._comm(f"?{self._name}")
        if silent:
            return ret
        else:
            print(ret)


class CityCommandDconfig:
    def __init__(self, city):
        self._city = city
        self._name = "DCONFIG"

    def __info__(self):
        desc = "Command:\n"
        desc += f'    dconfig.set("{self._city._state_str}")\n'
        desc += "Query:\n"
        desc += "    dconfig.get()\n"
        return desc

    def set(self, state):
        if state.upper() not in self._city._state:
            raise ValueError(f'state not in "{self._city._state_str}"')
        self._city._comm(f"{self._name} {state}")

    def get(self, silent=False):
        ret = self._city._comm(f"?{self._name}")
        if silent:
            return ret
        else:
            print(ret)


class CityCommandGate:
    """
    The GATE command can configure channels independantely, by list or by groups.
    In this module we choose to configure channels only one by one and to get
    the status of all of them.
    Use the .command method to be more vesatile
    """

    def __init__(self, city):
        self._city = city
        self._name = "GATE"

    def __info__(self):
        desc = "Command:\n"
        desc += "    gate.set(\n"
        desc += f'         "{self._city._outputs_str}",\n'
        desc += f'         "{self._city._sources_str}",\n'
        desc += f'         onoff="{self._city._onoff_str}",\n'
        desc += f'         polarity="{self._city._polarity_str}")\n'
        desc += "Query:\n"
        desc += "    gate.get()\n"
        return desc

    def set(self, output, source, onoff=Nonoe, polarity=None):
        if output.upper() not in self._city._outputs:
            raise ValueError(f'Output not in "{self._city._outputs_str}"')
        if source.upper() not in self._city._sources:
            raise ValueError(f'Output not in "{self._city._sources_str}"')
        if onoff is not None and onoff.upper() not in self._city._onoff:
            raise ValueError(f'onoff not in "{self._city._onoff_str}"')
        if polarity is not None and polarity.upper() not in self._city._polarity:
            raise ValueError(f'onoff not in "{self._city._onoff_str}"')

        if polarity is None:
            if onoff is None:
                self._city._comm(f"{self._name} {output} {source}")
            else:
                self._city._comm(f"{self._name} {output} {source} {onoff}")
        else:
            if onoff is None:
                self._city._comm(f"{self._name} {output} {source} {polarity}")
            else:
                self._city._comm(f"{self._name} {output} {source} {onoff} {polarity}")

    def get(self, silent=False):
        ret = self._city._comm(f"?{self._name}")
        if silent:
            return ret
        else:
            print(ret)


class CityCommandIset:
    def __init__(self, city):
        self._city = city
        self._name = "ISET"

    def __info__(self):
        desc = "Command:\n"
        desc += "    iset.set(\n"
        desc += f'        "{self._city._inputs_str}",\n'
        desc += f'        term="{self._city._yesno_str}",\n'
        desc += "        bias=<value>,\n"
        desc += f'        bias_unit="{self._city._Vunits_str}")\n'
        desc += "Query:\n"
        desc += "    iset.get()\n"
        return desc

    def set(self, inputs, term=None, bias=None, bias_unit=None):
        if inputs.upper() not in self._city._inputs:
            raise ValueError(f'input not in "{self._city._inputs_str}"')
        if term is not None and term.upper() not in self._city._yesno:
            raise ValueError(f'term not in "{self._city._yesno_str}"')
        if bias_unit is not None and bias_unit not in self._city._Vunits:
            raise ValueError(f'bias_unit not in "{self._city._Vunits_str}"')
        if term is None and bias is None:
            raise ValueError(f"Term AND/OR bias must be specified")
        comm = f"{self._name}"
        if term is not None:
            comm += f" TERM {term}"
        if bias is not None:
            comm += f" BIAS {bias}{bias_unit}"
        self._city._comm(comm)

    def get(self, silent=False):
        ret = self._city._comm(f"?{self._name}")
        if silent:
            return ret
        else:
            print(ret)


class CityCommandOckset:
    def __init__(self, city):
        self._city = city
        self._name = "OCKSET"

    def __info__(self):
        desc = "Command:\n"
        desc += "    ockset.set(\n"
        desc += f'        "{self._city._outputs_str}",\n'
        desc += f'        pattern="{self._city._pattern_str}",\n'
        desc += f'        div=<value>, width=[<value>|"50%"], width_unit="{self._city._Tunits_str}",\n'
        desc += "        divh=<value>, divl=<value>,\n"
        desc += f'        phase=<value>, phase_unit="{self._city._Tunits_str}",\n'
        desc += "        delay_start=<value>, delay_stop=<value>,\n"
        desc += f'        delay_unit="{self._city._Tunits_str}",\n'
        desc += "Query:\n"
        desc += "    ockset.get()\n"
        return desc

    def set(
        self,
        output,
        pattern=None,
        div=None,
        width=None,
        width_unit=None,
        divh=None,
        divl=None,
        phase=None,
        phase_unit=None,
        delay_start=None,
        delay_stop=None,
        delay_unit=None,
    ):
        if output.upper() not in self._city._outputs:
            raise ValueError(f'output not in "{self._city._outputs_str}"')
        if pattern is not None and pattern.upper() not in self._city._pattern:
            raise ValueError(f'pattern not in "{self._city._pattern_str}"')
        if width is not None:
            if not isinstance(width, float) and not isinstance(width, int):
                if width.upper() != "50%":
                    raise ValueError(f'width is not a number nor "50%"')
        if phase is not None and phase_unit.lower() not in self._city._Tunits:
            raise ValueError(f'phase_unit not in "{self._city._Tunits_str}"')
        if delay_unit.lower() not in self._city._Tunits:
            raise ValueError(f'delay_unit not in "{self._city._Tunits_str}"')
        comm = f"{self._name}"
        if pattern is not None:
            comm += f" TERM {term}"
        if bias is not None:
            comm += f" BIAS {bias}"
        self._city._comm(comm)

    def get(self, silent=False):
        ret = self._city._comm(f"?{self._name}")
        if silent:
            return ret
        else:
            print(ret)


class CityCommandOen:
    """
    The OEN command can configure channels independantely, by list or by groups.
    In this module we choose to configure channels only one by one and to get
    the status of all of them.
    Use the .command method to be more vesatile
    """

    def __init__(self, city):
        self._city = city
        self._name = "OEN"

    def __info__(self):
        desc = "Command:\n"
        desc += f'    oen.on("{self._city._outputs_str}")\n'
        desc += f'    oen.off("{self._city._outputs_str}"\n'
        desc += "Query:\n"
        desc += "    oen.get()\n"
        return desc

    def onset(self, output, onoff):
        if output.upper() not in self._city._outputs:
            raise ValueError(f'Output not in "{self._city._outputs_str}"')
        if onoff.upper() not in self._city._onoff:
            raise ValueError(f'onoff not in "{self._city._onoff_str}"')
        self._city._comm(f"{self._name} {output} {onoff}")

    def get(self, silent=False):
        ret = self._city._comm(f"?{self._name}")
        if silent:
            return ret
        else:
            print(ret)


class CityCommandOmode:
    """
    The OMODE command can get channels configuration independantely, by list or by groups.
    In this module we choose to get channels configuration for all of them.
    Use the .command method to be more versatile
    """

    def __init__(self, city):
        self._city = city
        self._name = "OMODE"

    def __info__(self):
        desc = "Command:\n"
        desc += "Query:\n"
        desc += "    omode.get()\n"
        return desc

    def get(self, silent=False):
        ret = self._city._comm(f"?{self._name} ")
        if silent:
            return ret
        else:
            print(ret)


class CityCommandOpuset:
    def __init__(self, city):
        self._city = city
        self._name = "OPUSET"

    def __info__(self):
        desc = "Command:\n"
        desc += "    opuset.set(\n"
        desc += f'         "{self._city._outputs_str}",\n'
        desc += f'         "{self._city._ref_str}",\n'
        desc += f'         <delay>, "{self._city._Tunits_str}",\n'
        desc += f'         <width>, "{self._city._Tunits_str}",\n'
        desc += f'         "{self._city._polarity_str}")\n'
        desc += "Query:\n"
        desc += "    opuset.get()\n"
        return desc

    def set(self, output, ref, delay, delay_unit, width, width_unit, polarity):
        if output.upper() not in self._city._outputs:
            raise ValueError(f'Output not in "{self._city._outputs_str}"')
        if ref.upper() not in self._city._ref:
            raise ValueError(f'ref not in "{self._city._ref_str}"')
        if delay_unit.lower() not in self._city._Tunits:
            raise ValueError(f'delay_unit not in "{self._city._Tunits_str}"')
        if width_unit.lower() not in self._city._Tunits:
            raise ValueError(f'width_unit not in "{self._city._Tunits_str}"')
        if polarity.upper() not in self._city._polarity:
            raise ValueError(f'polarity not in "{self._city._polarity_str}"')

        self._city._comm(
            f"{self._name} {output} {ref} {delay}{delay_units} {width}{width_units} {polarity}"
        )

    def get(self, silent=False):
        ret = self._city._comm(f"?{self._name}")
        if silent:
            return ret
        else:
            print(ret)


class CityCommandSgate:
    def __init__(self, city):
        self._city = city
        self._name = "SGATE"

    def __info__(self):
        desc = "Command:\n"
        desc += "    sgate.set(\n"
        desc += f'         "{self._city._softs_str}",\n'
        desc += f'         "{self._city._onoff_str}")\n'
        desc += "Query:\n"
        desc += "    sgate.get()\n"
        return desc

    def set(self, soft_input, onoff):
        if soft_input.upper() not in self._city._softs:
            raise ValueError(f'Software inputs not in "{self._city._softs_str}"')
        if onoff.upper() not in self._city._onoff:
            raise ValueError(f'onoff not in "{self._city._onoff_str}"')

        self._city._comm(f"{self._name} {soft_input} {onoff}")

    def get(self, silent=False):
        ret = self._city._comm(f"?{self._name}")
        if silent:
            return ret
        else:
            print(ret)


class CityCommandUsrclk:
    def __init__(self, city):
        self._city = city
        self._name = "USRCLK"

    def __info__(self):
        desc = "Command:\n"
        desc += "    usrclk.set(\n"
        desc += f'         "{self._city._clk_str}",\n'
        desc += f'         "{self._city._divider_str}")\n'
        desc += "Query:\n"
        desc += "    usrclk.get()\n"
        return desc

    def set(self, clk, divider):
        if clk.upper() not in self._city._clk:
            raise ValueError(f'Clock not in "{self._city._clk_str}"')
        if divider < 1 or divider > 32:
            raise ValueError(f'diver not in "{self._city._divider_str}"')

        if clk.upper() == "RFDDS":
            self._city._comm(f"{self._name} {clk}")
        else:
            self._city._comm(f"{self._name} {clk} {divider}")

    def get(self, silent=False):
        ret = self._city._comm(f"?{self._name}")
        if silent:
            return ret
        else:
            print(ret)
