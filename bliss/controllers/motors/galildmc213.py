"""
Bliss controller for ethernet Galil DC controller.
"""

from warnings import warn

from bliss.controllers.motor import Controller
from bliss.common import session

from bliss.common.axis import AxisState
from bliss.comm.util import get_comm, TCP
from bliss.common.greenlet_utils import protect_from_kill
from gevent import lock

SERVO = 1
INV_SERVO = -1
STEPPER_LOW = 2
STEPPER_HIGH = -2
INV_STEPPER_LOW = 2.5
INV_STEPPER_HIGH = -2.5
HIGH_LEVEL = 1
LOW_LEVEL = -1
QUADRA = 0
PULSE = 1
REVERSED_QUADRA = 2
REVERSED_PULSE = 3
DISABLED = 0
ENABLED = 1


class GalilDMC213(Controller):
    def __init__(self, *args, **kwargs):
        Controller.__init__(self, *args, **kwargs)
        self.socket_lock = lock.Semaphore()

    def initialize(self):
        try:
            self.sock = get_comm(self.config.config_dict, ctype=TCP, port=23)
        except ValueError:
            host = self.config.get("host")
            warn("'host' keyword is deprecated. Use 'tcp' instead", DeprecationWarning)
            comm_cfg = {"tcp": {"url": host}}
            self.sock = get_comm(comm_cfg, port=23)
        session.get_current().map.register(self, children_list=[self.sock])

    def initialize_hardware(self):
        # perform hw reset
        self._galil_query("RS")
        # set default sample time
        self._galil_query("TM 1000")
        # set vector time constant (motion smoothing)
        self._galil_query("VT 1.0")
        # configure switches and latch polarity
        self._galil_query("CN %d,%d,%d" % (LOW_LEVEL, HIGH_LEVEL, HIGH_LEVEL))

    def finalize(self):
        self.close()

    def close(self):
        self.sock.close()

    def initialize_axis(self, axis):
        axis.channel = axis.config.get("channel")
        if not axis.channel in "ABCDEFGH":
            raise RuntimeError("Invalid channel, should be one of: A,B,C,D,E,F,G,H")

    def initialize_hardware_axis(self, axis):
        axis_type = axis.config.get("type", int, default=SERVO)
        axis_vect_acc = axis.config.get("vect_acceleration", int, default=262144)
        axis_vect_dec = axis.config.get("vect_deceleration", int, default=262144)
        axis_vect_slewrate = axis.config.get("vect_slewrate", int, default=8192)
        axis_encoder_type = axis.config.get("encoder_type", int, default=QUADRA)
        axis_kp = axis.config.get("kp", float, default=1.0)
        axis_ki = axis.config.get("ki", float, default=6.0)
        axis_kd = axis.config.get("kd", float, default=7.0)
        axis_integ_limit = axis.config.get("integrator_limit", float, default=9.998)
        axis_smoothing = axis.config.get("smoothing", float, default=1.0)
        axis_acceleration = axis.config.get("acceleration", float, default=100000)
        axis_deceleration = axis.config.get("deceleration", float, default=100000)
        axis_slewrate = axis.config.get("slewrate", float, default=100000)
        # axis_onoff = axis.config.get("off_on_error", int, default=DISABLED)
        axis_error_limit = axis.config.get("error_limit", int, default=16384)
        axis_cmd_offset = axis.config.get("cmd_offset", float, default=0.0)
        axis_torque_limit = axis.config.get("torque_limit", float, default=9.998)

        # set motor off
        self._galil_query("MO%s" % axis.channel)
        # set vector acceleration
        self._galil_query("VA%s=%d" % (axis.channel, axis_vect_acc))
        # set vector deceleration
        self._galil_query("VD%s=%d" % (axis.channel, axis_vect_dec))
        # set vector slewrate
        self._galil_query("VS%s=%d" % (axis.channel, axis_vect_slewrate))
        # set encoder type
        self._galil_query("CE%s=%d" % (axis.channel, axis_encoder_type))
        # set motor type
        self._galil_query("MT%s=%d" % (axis.channel, axis_type))
        # set PID parameters
        self._galil_query("KP%s=%f" % (axis.channel, axis_kp))
        self._galil_query("KI%s=%f" % (axis.channel, axis_ki))
        self._galil_query("KD%s=%f" % (axis.channel, axis_kd))
        # set integrator limit
        self._galil_query("IL%s=%f" % (axis.channel, axis_integ_limit))
        # set independent time constant (smoothing)
        self._galil_query("IT%s=%f" % (axis.channel, axis_smoothing))
        # set acceleration
        self._galil_query("AC%s=%d" % (axis.channel, axis_acceleration))
        # set deceleration
        self._galil_query("DC%s=%d" % (axis.channel, axis_deceleration))
        # set speed
        self._galil_query("SP%s=%d" % (axis.channel, axis_slewrate))
        # set on/off error
        # self._galil_query("OE%s=%d" % (axis.channel, axis_onoff))
        # set error limit
        self._galil_query("ER%s=%d" % (axis.channel, axis_error_limit))
        # set cmd offset
        self._galil_query("OF%s=%f" % (axis.channel, axis_cmd_offset))
        # set torque limit
        self._galil_query("TL%s=%f" % (axis.channel, axis_torque_limit))
        # start motor (power on)
        self._galil_query("SH%s" % axis.channel)
        # set on/off error to ENABLED
        self._galil_query("OE%s=1" % axis.channel)

    def initialize_encoder(self, encoder):
        encoder.channel = encoder.config.get("channel")
        if encoder.channel not in "ABCDEFGH":
            raise RuntimeError(
                "Invalid encoder channel, should be one of: A,B,C,D,E,F,G,H"
            )

    def read_position(self, axis):
        """
        Returns position's setpoint or measured position (in steps).
        """
        return float(self._galil_query("TP %s" % axis.channel))

    def read_encoder(self, encoder):
        return float(self._galil_query("TD %s" % encoder.channel))

    def set_acceleration(self, axis, new_acc):
        padding = "," * (ord(axis.channel) - ord("A"))
        self._galil_query("AC%s%d" % (padding, new_acc))
        self._galil_query("DC%s%d" % (padding, new_acc))

    def read_acceleration(self, axis):
        return int(self._galil_query("AC%s=?" % axis.channel))

    def read_velocity(self, axis):
        return int(self._galil_query("SP%s=?" % axis.channel))

    def set_velocity(self, axis, new_velocity):
        padding = "," * (ord(axis.channel) - ord("A"))
        self._galil_query("SP%s%d" % (padding, new_velocity))
        return self.read_velocity(axis)

    def set_off(self, axis):
        self._galil_query("MO%s" % axis.channel)

    def set_on(self, axis):
        self._galil_query("SH%s" % axis.channel)

    def state(self, axis):
        sta = int(self._galil_query("TS%s" % axis.channel))
        if sta & (1 << 7):
            return AxisState("MOVING")
        """
        elif sta & (1<<6):
          # on limit
          return
        elif sta & (1<<5):
          # motor off
          return AxisState("READY")
        """
        return AxisState("READY")

    def prepare_move(self, motion):
        self._galil_query("PA%s=%d" % (motion.axis.channel, motion.target_pos))

    def start_one(self, motion):
        self._galil_query("BG%s" % motion.axis.channel)

    def stop(self, axis):
        self._galil_query("ST %s" % axis.channel)

    def home_search(self, axis, switch):
        """
        start home search.
        """
        self._galil_query("OE%s=0" % axis.channel)
        self._galil_query("SH%s" % axis.channel)
        self._galil_query("FI%s" % axis.channel)
        self._galil_query("BG%s" % axis.channel)

    def home_state(self, axis):
        # reading home switch
        # if int(self._galil_query("TS%s" % axis.channel)) & (1<<1):
        return self.state(axis)

    @protect_from_kill
    def _galil_query(self, cmd, raw=False):
        if not cmd.endswith(";"):
            cmd += ";"

        with self.socket_lock:
            # print "SENDING: %r" % cmd
            self.sock.write(cmd.encode())
            ans = self.sock.raw_read().decode()
            if ans[0] == "?":
                raise RuntimeError("Invalid command")
            ans = ans.strip(": \r\n")
            # print 'received',repr(ans)
            return ans or None

    def raw_write_read(self, cmd):
        return self._galil_query(cmd)
