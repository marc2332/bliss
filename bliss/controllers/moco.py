from bliss import global_map
from bliss.comm.util import get_comm, get_comm_type, SERIAL, TCP
from bliss.comm import serial
from bliss.common.greenlet_utils import KillMask, protect_from_kill
from bliss.common.counter import SamplingCounter, SamplingMode
from bliss.controllers.counter import SamplingCounterController
from bliss.common.protocols import counter_namespace
from bliss.common.axis import AxisState
from bliss.controllers.motor import Controller
from bliss.config import static


class Moco(object):
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
        comm_type = None
        try:
            comm_type = get_comm_type(config_tree)
            key = "serial" if comm_type == SERIAL else "tcp"
            config_tree[key]["url"]  # test if url is available
            comm_config = config_tree
        except:
            if "serial" in config_tree:
                comm_type = SERIAL
                comm_config = dict(serial=dict(url=config_tree["serial"]))
                warn(
                    "'serial: <url>' is deprecated. "
                    "Use 'serial: url: <url>' instead",
                    DeprecationWarning,
                )
            else:
                raise RuntimeError("moco: need to specify a serial communication url")

        if comm_type != SERIAL:
            raise TypeError("moco: invalid communication type %r" % comm_type)

        self._cnx = get_comm(comm_config, ctype=comm_type, timeout=3)
        self._cnx.flush()
        self.__debug = False

        # motor
        self.motor = None

        # Counters
        self.counters_controller = MocoCounterController(self)
        counter_node = config_tree.get("counters")
        for config_dict in counter_node:
            if self.counters_controller is not None:
                counter_name = config_dict.get("counter_name")
                counter = MocoCounter(
                    counter_name, config_dict, self.counters_controller
                )

    def __info__(self):
        info_str = f"MOCO\nName    : {self.name}\nComm.   : {self._cnx}\n\n"
        try:
            info = self.comm("?INFO")
            info_str += info
        except:
            info_str += "Communication problems..."

        return info_str

    @property
    def debug(self):
        return self.__debug

    @debug.setter
    def debug(self, flag):
        self.__debug = bool(flag)

    def __debugMsg(self, wr, msg):
        if self.__debug:
            print("%-5.5s on %s > %s" % (wr, self.name, msg))

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
                self.__debugMsg("Read", msg.strip("\n\r".encode()))
                if text:
                    return (msg.strip("\r\n".encode())).decode()
                else:
                    return msg.strip("\r\n".encode())

    """
    MOCO counters
    """

    def get_counter(self, name):
        for counter in self.counterlist:
            if counter.name == name:
                return counter

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

    def outbeam(
        self,
        source=None,
        polarity=None,
        channel=None,
        fullscale=None,
        autoscale=None,
        silent=False,
    ):

        if source in ["CURR", "VOLT", "EXT"]:
            comm = f"OUTBEAM {source}"
            if polarity in ["NORM", "INV"]:
                comm = f"{comm} {polarity}"
                if channel in ["BIP", "UNI"]:
                    comm = f"{comm} channel"
                    if fullscale is not None:
                        comm = f"{comm} {float(fullscale)}"
                        if autoscale in ["AUTO", "NOAUTO"]:
                            comm = f"{comm} {autoscale}"
                            self.comm(comm)
                            return

        if not silent:
            ans = self.comm("?OUTBEAM")
            rep = ans.split()
            print(f"OUTBEAM: source    : {rep[0]}\t[CURR | VOLT | EXT]")
            print(f"         polarity  : {rep[1]}\t[NORM | INV]")
            print(f"         channel   : {rep[2]}\t[BIP | UNI]")
            print(f"         fullscale : {rep[3]}")
            print(f"         autoscale : {rep[4]}\t[AUTO | NOAUTO]")

    def go(self, setpoint=None):
        # param: sPoint | #
        if setpoint is None:
            self.comm("GO")
        elif setpoint == "#":
            self.comm("GO #")
        else:
            self.comm(f"GO {param}")

    def stop(self):
        self.comm("STOP")

    def tune(self, setpoint=None):
        # param: sPoint | #
        if setpoint is None:
            self.comm("TUNE")
        elif setpoint == "#":
            self.comm("TUNE #")
        else:
            self.comm(f"TUNE {param}")

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

        super().__init__(self.moco.name + "CC", register_counters=False)

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


class MocoMotor(Controller):
    def __init__(self, name, config, axes, *args):

        if len(axes) > 1:
            raise RuntimeError(
                f"moco: only 1 motor is allowed, {len(axes)} are configured"
            )

        static_config = static.get_config()
        self.moco = static_config.get(config.get("moco"))

        super().__init__(self.moco.name + "_motor", config, axes, *args)

        self.moco.motor = self

    def initialize(self):
        # velocity and acceleration are not mandatory in config
        self.axis_settings.config_setting["velocity"] = False
        self.axis_settings.config_setting["acceleration"] = False

    def initialize_axis(self, axis):
        pass

    def read_position(self, axis):
        ret_val = self.moco.comm("?PIEZO")
        return float(ret_val)

    def state(self, axis):
        state = self.moco.comm("?STATE")
        if state == "IDLE":
            return AxisState("READY")
        elif state == "RUN":
            return AxisState("MOVING")

        return AxisState("OFF")

    def start_one(self, motion):
        self.moco.comm("PIEZO %g" % motion.target_pos)

    def start_all(self, *motions):
        for m in motions:
            self.start_one(m)

    def stop(self, axis):
        pass
