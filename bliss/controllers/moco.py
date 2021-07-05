import gevent

from bliss import global_map
from bliss.comm.util import get_comm
from bliss.common.greenlet_utils import protect_from_kill
from bliss.common.counter import SamplingCounter, SamplingMode
from bliss.controllers.counter import SamplingCounterController
from bliss.common.protocols import CounterContainer
from bliss.common.logtools import user_warning


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

        # default config
        self._default_config = config_tree.get("default_config", None)

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
        if msg == "ECHO":
            raise ValueError("MOCO: ECHO mode is not supported")
        self._cnx.open()
        echo = False
        ret = None
        with self._cnx._lock:
            self._cnx._write((msg + "\r\n").encode())
            if msg.startswith("?") or msg.startswith("#"):
                ans = self._cnx._readline(timeout=timeout)
                if ans.decode().strip() == msg.strip():
                    echo = True
                    ans = self._cnx._readline(timeout=timeout)
                if ans.startswith("$".encode()):
                    ans = self._cnx._readline("$\r\n".encode(), timeout=timeout)
                if text:
                    ret = (ans.strip("\r\n".encode())).decode()
                else:
                    ret = ans.strip("\r\n".encode())
        if echo and msg != "NOECHO":
            user_warning(f"MOCO: {self.name}: Disabling ECHO")
            self.comm("NOECHO")
        return ret

    """
    MOCO Default Config
    """

    def set_default_config(self):
        if self._default_config is not None:
            try:
                fd = open(self._default_config)
                for line in fd:
                    self.comm(line[:-1])
                    gevent.sleep(0.01)
            except:
                raise RuntimeError(
                    f"moco (set_default_config) File {self._default_config} does not exist"
                )

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

    def oprange(self, vmin=None, vmax=None, vsafe=None, silent=False):
        ans = self.comm("?OPRANGE")
        [valmin, valmax, valsafe] = ans.split()

        if vmin is not None:
            if vmin < -10.0 and vmin > 10.0:
                raise RuntimeError(
                    f"moco: OPRANGE: Min. value {vmin} outside limits [-10:10]"
                )
            valmin = vmin
        if vmax is not None:
            if vmax < -10.0 and vmax > 10.0:
                raise RuntimeError(
                    f"moco: OPRANGE: Max. value {vmax} outside limits [-10:10]"
                )
            valmax = vmax
        if vsafe is not None:
            if vsafe < -10.0 and vmax > 10.0:
                raise RuntimeError(
                    f"moco: OPRANGE: Safe value {vsafe} outside limits [-10:10]"
                )
            valsafe = vsafe

        if vmin is not None or vmax is not None or vsafe != valsafe:
            comm = f"OPRANGE {valmin} {valmax} {valsafe}"
            self.comm(comm)
            gevent.sleep(0.1)
            ans = self.comm("?OPRANGE")
            [valmin, valmax, valsafe] = ans.split()

        if not silent:
            print(f"OPRANGE: [{valmin} - {valmax} - {valsafe}]")

        return [float(valmin), float(valmax), float(valsafe)]

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

        ans = self.comm("?OUTBEAM")
        rep = ans.split()
        valsource = rep[0].upper()
        valpolarity = rep[1].upper()
        valchannel = rep[2].upper()
        valfullscale = rep[3]
        valautoscale = rep[4].upper()

        sendcomm = False

        if source is not None:
            if source.upper() not in ["CURR", "VOLT", "EXT"]:
                raise RuntimeError(
                    f"moco (OUTBEAM) Unknown source value ({source}) [CURR/VOLT/EXT]"
                )
            valsource = source.upper()
            sendcomm = True
        if polarity is not None:
            if polarity.upper() not in ["NORM", "INV"]:
                raise RuntimeError(
                    f"moco (OUTBEAM) Unknown polarity value ({polarity}) [NORM/INV]"
                )
            valpolarity = polarity.upper()
            sendcomm = True
        if channel is not None:
            if channel.upper() not in ["BIP", "UNIP"]:
                raise RuntimeError(
                    f"moco (OUTBEAM) Unknown channel value ({channel}) [BIP/UNIP]"
                )
            valchannel = channel.upper()
            sendcomm = True
        if fullscale is not None:
            valfullscale = fullscale
            sendcomm = True
        if autoscale is not None:
            if autoscale.upper() not in ["AUTO", "NOAUTO"]:
                raise RuntimeError(
                    f"moco (OUTBEAM) Unknown autoscale value ({autoscale}) [AUTO/NOAUTO]"
                )
            valautoscale = autoscale.upper()
            sendcomm = True

        if sendcomm:
            comm = f"OUTBEAM {valsource} {valpolarity} {valchannel} {valfullscale} {valautoscale}"
            self.comm(comm)
            gevent.sleep(0.1)
            ans = self.comm("?OUTBEAM")
            rep = ans.split()
            valsource = rep[0]
            valpolarity = rep[1]
            valchannel = rep[2]
            valfullscale = rep[3]
            valautoscale = rep[4]

        if not silent:
            print(f"OUTBEAM:  source    : {valsource}\t[CURR | VOLT | EXT]")
            print(f"          polarity  : {valpolarity}\t[NORM | INV]")
            print(f"          channel   : {valchannel}\t[BIP | UNIP]")
            print(f"          fullscale : {valfullscale}")
            print(f"          autoscale : {valautoscale}\t[AUTO | NOAUTO]")

    # INBEAM [{CURR | VOLT | EXT}] [{NORM | INV}] [{BIP | UNIP}] [<fS>] [{AUTO | NOAUTO}]
    # INBEAM [SOFT] [<softThresh>]
    def inbeam(
        self,
        source=None,
        polarity=None,
        channel=None,
        fullscale=None,
        autoscale=None,
        threshold=None,
        silent=False,
    ):

        ans = self.comm("?INBEAM")
        rep = ans.split()
        valsource = rep[0].upper()
        if valsource == "SOFT":
            valthreshold = rep[1]
        else:
            valpolarity = rep[1].upper()
            valchannel = rep[2].upper()
            valfullscale = rep[3]
            valautoscale = rep[4].upper()

        sendcomm = False

        if source is not None:
            if source.upper() not in ["SOFT", "CURR", "VOLT", "EXT"]:
                raise RuntimeError(
                    f"moco (INBEAM) Unknown source value ({source}) [SOFT/CURR/VOLT/EXT]"
                )
            valsource = source.upper()
            sendcomm = True
        if threshold is not None:
            valthreshold = threshold
            sendcomm = True
        if polarity is not None:
            if polarity.upper() not in ["NORM", "INV"]:
                raise RuntimeError(
                    f"moco (INBEAM) Unknown polarity value ({polarity}) [NORM/INV]"
                )
            valpolarity = polarity.upper()
            sendcomm = True
        if channel is not None:
            if channel.upper() not in ["BIP", "UNIP"]:
                raise RuntimeError(
                    f"moco (INBEAM) Unknown channel value ({channel}) [BIP/UNIP]"
                )
            valchannel = channel.upper()
            sendcomm = True
        if fullscale is not None:
            valfullscale = fullscale
            sendcomm = True
        if autoscale is not None:
            if autoscale.upper() not in ["AUTO", "NOAUTO"]:
                raise RuntimeError(
                    f"moco (INBEAM) Unknown autoscale value ({autoscale}) [AUTO/NOAUTO]"
                )
            valautoscale = autoscale.upper()
            sendcomm = True

        if sendcomm:
            if source == "SOFT":
                comm = f"INBEAM {valsource} {valthreshold}"
            else:
                comm = f"INBEAM {valsource} {valpolarity} {valchannel} {valfullscale} {valautoscale}"
            self.comm(comm)
            gevent.sleep(0.1)
            ans = self.comm("?INBEAM")
            rep = ans.split()
            valsource = rep[0]
            if valsource == "SOFT":
                valthreshold = rep[1]
            else:
                valpolarity = rep[1]
                valchannel = rep[2]
                valfullscale[3]
                valautoscale = rep[4]

        if not silent:
            print(f"INBEAM:  source    : {valsource}\t[CURR | VOLT | EXT]")
            if valsource == "SOFT":
                print(f"         Threshold : {valthreshold}")
            else:
                print(f"         polarity  : {valpolarity}\t[NORM | INV]")
                print(f"         channel   : {valchannel}\t[BIP | UNIP]")
                print(f"         fullscale : {valfullscale}")
                print(f"         autoscale : {valautoscale}\t[AUTO | NOAUTO]")

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
