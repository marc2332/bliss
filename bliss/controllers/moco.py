from bliss import global_map
from bliss.comm.util import get_comm
from bliss.common.greenlet_utils import protect_from_kill
from bliss.common.counter import SamplingCounter, SamplingMode
from bliss.controllers.counter import SamplingCounterController
from bliss.common.protocols import CounterContainer


class Moco(CounterContainer):
    def __init__(self, name, config_tree):

        self.values = {
            "outbeam": 0.0,
            "inbeam": 0.0,
            "sum": 0.0,
            "diff": 0.0,
            "ndiff": 0.0,
            "ratio": 0.0,
            "foutbeam": 0.0,
            "finbeam": 0.0,
            "fsum": 0.0,
            "fdiff": 0,
            "fndiff": 0.0,
            "fratio": 0.0,
            "fratio": 0.0,
            "oscmain": 0.0,
            "oscquad": 0.0,
            "softbeam": 0.0,
            "piezo": 0.0,
        }

        self.name = name

        # Communication
        self._cnx = get_comm(config_tree, timeout=3)
        global_map.register(self, children_list=[self._cnx])

        # motor
        self.motor = None

        # Counters
        self.counters_controller = MocoCounterController(self)
        self.counters_controller.max_sampling_frequency = config_tree.get(
            "max_sampling_frequency"
        )
        counter_node = config_tree.get("counters")
        for config_dict in counter_node:
            if self.counters_controller is not None:
                counter_name = config_dict.get("counter_name")
                MocoCounter(counter_name, config_dict, self.counters_controller)

    def __info__(self):
        info_str = f"MOCO\nName    : {self.name}\nComm.   : {self._cnx}\n\n"
        try:
            info = self.comm("?INFO")
            info_str += info
        except:
            info_str += "Communication problems..."

        return info_str

    """
    Serial Communication
    """

    def comm_ack(self, msg):
        return self.comm("#" + msg)

    @protect_from_kill
    def comm(self, msg, timeout=None, text=True):
        self._cnx.open()
        with self._cnx._lock:
            self._cnx._write((msg + "\r\n").encode())
            if msg.startswith("?") or msg.startswith("#"):
                msg = self._cnx._readline(timeout=timeout)
                if msg.startswith("$".encode()):
                    msg = self._cnx._readline("$\r\n".encode(), timeout=timeout)
                if text:
                    return (msg.strip("\r\n".encode())).decode()
                else:
                    return msg.strip("\r\n".encode())

    """
    MOCO counters
    """

    @property
    def counters(self):
        return self.counters_controller.counters

    """
    MOCO command
    """

    def info(self):
        print("\n", self.comm("?INFO"), "\n")

    def help(self):
        print("\n", self.comm("?HELP"), "\n")

    def state(self):
        print(self.comm("?STATE"))

    def oscil(self):
        return self.comm("?OSCIL")

    def oscilon(self):
        self.comm("OSCIL ON")

    def osciloff(self):
        self.comm("OSCIL OFF")

    @property
    def amplitude(self):
        return float(self.comm("?AMPLITUDE"))

    @amplitude.setter
    def amplitude(self, val):
        self.comm(f"AMPLITUDE {val}")

    @property
    def phase(self):
        return float(self.comm("?PHASE"))

    @phase.setter
    def phase(self, val):
        self.comm(f"PHASE {val}")

    @property
    def slope(self):
        return float(self.comm("?SLOPE"))

    @slope.setter
    def slope(self, val):
        self.comm(f"SLOPE {val}")

    @property
    def tau(self):
        return float(self.comm("?TAU"))

    @tau.setter
    def tau(self, val):
        self.comm(f"TAU {val}")

    @property
    def frequency(self):
        return float(self.comm("?FREQUENCY"))

    @frequency.setter
    def frequency(self, val):
        self.comm(f"FREQUENCY {val}")

    def beam(self):
        rep_str = self.comm("?beam")
        rep = rep_str.split()
        print(f"\nBeam IN  [{rep[0]}]")
        print(f"Beam OUT [{rep[1]}]")
        print("\n")

    def mode(self, mode=None, silent=False):
        if mode in ("POSITION", "INTENSITY", "OSCILLATION"):
            self.comm(f"MODE {mode}")

        ans = self.comm("?MODE")
        if not silent:
            print(f"MODE: {ans}\t[POSITION | INTENSITY | OSCILLATION]")

        return ans

    def srange(self, vmin=None, vmax=None, silent=False):
        if vmin is not None:
            comm = f"SRANGE {vmin}"
            if vmax is not None:
                comm = f"{comm} {vmax}"
                self.comm(comm)

        ans = self.comm("?SRANGE")
        [valmin, valmax] = ans.split()
        if not silent:
            print(f"SRANGE: [{valmin} - {valmax}]")

        return [float(valmin), float(valmax)]

    # OUTBEAM  [{CURR  |  VOLT  |  EXT}]  [{NORM  |  INV}]  [{BIP |  UNIP}]  [<fS>]  [{AUTO  | NOAUTO}]
    def outbeam(
        self,
        source=None,
        polarity=None,
        channel=None,
        fullscale=None,
        autoscale=None,
        silent=False,
    ):

        comm = ""
        if (source is not None) and (source.upper() in ["CURR", "VOLT", "EXT"]):
            comm = f"{comm} {source}"
        if (polarity is not None) and (polarity.upper() in ["NORM", "INV"]):
            comm = f"{comm} {polarity}"
        if (channel is not None) and (channel.upper() in ["BIP", "UNIP"]):
            comm = f"{comm} {channel}"
        if fullscale is not None:
            comm = f"{comm} {float(fullscale)}"
        if (autoscale is not None) and (autoscale.upper() in ["AUTO", "NOAUTO"]):
            comm = f"{comm} {autoscale}"
        if comm != "":
            self.comm(f"OUTBEAM {comm}".upper())
            return

        if not silent:
            ans = self.comm("?OUTBEAM")
            rep = ans.split()
            print(f"OUTBEAM: source    : {rep[0]}\t[CURR | VOLT | EXT]")
            print(f"         polarity  : {rep[1]}\t[NORM | INV]")
            print(f"         channel   : {rep[2]}\t[BIP | UNIP]")
            print(f"         fullscale : {rep[3]}")
            print(f"         autoscale : {rep[4]}\t[AUTO | NOAUTO]")

    # INBEAM [{CURR | VOLT | EXT}] [{NORM | INV}] [{BIP | UNIP}] [<fS>] [{AUTO | NOAUTO}]
    # INBEAM [SOFT] [<softThresh>]
    def inbeam(
        self,
        source=None,
        polarity=None,
        channel=None,
        fullscale=None,
        autoscale=None,
        silent=False,
    ):

        comm = ""
        if (source is not None) and (source.upper() in ["CURR", "VOLT", "EXT"]):
            comm = f"{comm} {source}"
        if (polarity is not None) and (polarity.upper() in ["NORM", "INV"]):
            comm = f"{comm} {polarity}"
        if (channel is not None) and (channel.upper() in ["BIP", "UNIP"]):
            comm = f"{comm} {channel}"
        if fullscale is not None:
            comm = f"{comm} {float(fullscale)}"
        if (autoscale is not None) and (autoscale.upper() in ["AUTO", "NOAUTO"]):
            comm = f"{comm} {autoscale}"
        if comm != "":
            self.comm(f"INBEAM {comm}".upper())
            return

        if not silent:
            ans = self.comm("?INBEAM")
            rep = ans.split()
            print(f"INBEAM:  source    : {rep[0]}\t[CURR | VOLT | EXT]")
            print(f"         polarity  : {rep[1]}\t[NORM | INV]")
            print(f"         channel   : {rep[2]}\t[BIP | UNIP]")
            print(f"         fullscale : {rep[3]}")
            print(f"         autoscale : {rep[4]}\t[AUTO | NOAUTO]")

    def go(self, setpoint=None):
        # setpoint: sPoint | #
        if setpoint is None:
            self.comm("GO")
        elif setpoint == "#":
            self.comm("GO #")
        else:
            self.comm(f"GO {setpoint}")

    def stop(self):
        self.comm("STOP")

    def tune(self, setpoint=None):
        # setpoint: sPoint | #
        if setpoint is None:
            self.comm("TUNE")
        elif setpoint == "#":
            self.comm("TUNE #")
        else:
            self.comm(f"TUNE {setpoint}")

    def peak(self, height=None, width=None, pos=None, silent=False):
        if height is not None:
            if width is not None:
                comm = f"PEAK {height} {width}"
                if pos is not None:
                    comm = f"{comm} {pos}"
                self.comm(comm)

        ans = self.comm("?PEAK")
        [hval, wval, pval] = ans.split()
        if not silent:
            print(f"PEAK: height={hval}  width={wval}  pos={pval}")

        return [float(hval), float(wval), float(pval)]

    def moco_read_counters(self):
        ret_val = self.comm("?BEAM")
        val_in = float(ret_val.rsplit()[0])
        val_out = float(ret_val.rsplit()[1])
        self.values["inbeam"] = val_in
        self.values["outbeam"] = val_out
        self.values["sum"] = val_in + val_out
        self.values["diff"] = val_out - val_in
        if (val_in + val_out) != 0.0:
            self.values["ndiff"] = (val_out - val_in) / (val_in + val_out)
        else:
            self.values["ndiff"] = 0.0
        if val_in != 0.0:
            self.values["ratio"] = val_out / val_in
        else:
            self.values["ratio"] = 1.0

        ret_val = self.comm("?FBEAM")
        val_in = float(ret_val.rsplit()[0])
        val_out = float(ret_val.rsplit()[1])
        self.values["finbeam"] = val_in
        self.values["foutbeam"] = val_out
        self.values["fsum"] = val_in + val_out
        self.values["fdiff"] = val_out - val_in
        if (val_in + val_out) != 0.0:
            self.values["fndiff"] = (val_out - val_in) / (val_in + val_out)
        else:
            self.values["fndiff"] = 0.0
        if val_in != 0.0:
            self.values["fratio"] = val_out / val_in
        else:
            self.values["fratio"] = 1.0

        if self.mode(silent=True) == "OSCILLATION":
            ret_val = self.comm("?OSCBEAM")
            self.values["oscmain"] = float(ret_val.rsplit()[0])
            self.values["oscquad"] = float(ret_val.rsplit()[1])
        else:
            self.values["oscmain"] = 0
            self.values["oscquad"] = 0

        ret_val = self.comm("?PIEZO")
        self.values["piezo"] = float(ret_val)


class MocoCounterController(SamplingCounterController):
    def __init__(self, moco):

        self.moco = moco

        super().__init__(self.moco.name, register_counters=False)

        global_map.register(moco, parents_list=["counters"])

    def read_all(self, *counters):

        self.moco.moco_read_counters()

        values = []

        for cnt in counters:
            values.append(self.moco.values[cnt.role])

        return values


class MocoCounter(SamplingCounter):
    def __init__(self, name, config, controller):

        self.role = config["role"]

        if self.role not in controller.moco.values.keys():
            raise RuntimeError(
                f"moco: counter {self.name} role {self.role} does not exists"
            )

        SamplingCounter.__init__(self, name, controller, mode=SamplingMode.LAST)
