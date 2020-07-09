# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
import gevent

from bliss import global_map
from bliss.comm.util import UDP, get_comm_type, get_comm
from bliss.comm.tcp import SocketTimeout
from bliss.common.utils import object_method
from bliss.common.axis import AxisState
from bliss.config.channels import Cache
from bliss.controllers.motor import Controller


class Elmo(Controller):
    """
    Elmo motor controller

    configuration example:
    - class: elmo
      udp:
      url: nscopeelmo
      axes:
        - name: rot
          steps_per_unit: 26222.2
          velocity: 377600
          acceleration: 755200
          control_slave: True
    """

    ErrorCode = {
        1: "Do not Update",
        2: "Bad Command",
        3: "Bad Index",
        5: "BEYOND_ALPHA_BET (Has No Interpreter Meaning",
        6: "Program is not running",
        7: "Mode cannot be started - bad initialization data",
        8: "Motion terminated, probably data underflow",
        9: "CAN message was lost",
        10: "Cannot be used by PDO",
        11: "Cannot write to flash memory",
        12: "Command not available in this unit mode",
        13: "Cannot reset communication - UART is busy",
        14: "Cannot perform CAN NMT service",
        15: "CAN Life time exceeded - motor shut down",
        16: "The command attribute is array '[]' is expected",
        17: "Format of UL command is not valid - check the command definition",
        18: "Empty Assign",
        19: "Command syntax error",
        21: "Operand Out of Range",
        22: "Zero Division",
        23: "Command cannot be assigned",
        24: "Bad Operation",
        25: "Command Not Valid While Moving",
        26: "Profiler mode not supported in this unit mode (UM)",
        28: "Out Of Limit",
        29: "CAN set object return an abort when called from interpreter",
        30: "No program to continue",
        31: "CAN get object return an abort when called from interpreter",
        32: "Communication overrun, parity, noise, or framing error",
        33: "Bad sensor setting",
        34: "There is a conflict with another command",
        36: "Commutation method (CA[17]) or commutation table does not fit to sensor",
        37: "Two Or More Hall sensors are defined to the same place",
        38: "Motion start specified for the past",
        41: "Command is not supported by this product",
        42: "No Such Label",
        43: "CAN state machine in fault(object 0x6041 in DS-402)",
        45: "Return Error From Subroutine",
        46: "May Not Use Multi- capture Homing Mode With Stop Event",
        47: "Program does not exist or not Compiled",
        48: "Motor cold not start - fault reason in CD",
        50: "Stack Overflow",
        51: "Inhibit OR Abort inputs are active, Cannot start motor",
        52: "PVT Queue Full",
        53: "Only For Current",
        54: "Bad Data Base",
        55: "Bad Context",
        56: "The product grade does not support this command",
        57: "Motor Must be Off",
        58: "Motor Must be On",
        60: "Bad Unit Mode",
        61: "Data Base Reset",
        64: "Cannot set the index of an active table",
        65: "Disabled By SW",
        66: "Amplifier Not Ready",
        67: "Recorder Is Busy",
        68: "Required profiler mode is not supported",
        69: "Recorder Usage Error",
        70: "Recorder data Invalid",
        71: "Homing is busy",
        72: "Modulo range must be even",
        73: "Please Set Position",
        74: "Bad profile database, see 0x2081 for object number (EE[2])",
        77: "Buffer Too Large",
        78: "Out of Program Range",
        80: "ECAM data inconsistent",
        81: "Download failed see specific error in EE[3]",
        82: "Program Is Running",
        83: "Command is not permitted in a program.",
        84: "The System Is Not In Point To Point Mode",
        86: "PVT table is soon going to underflow",
        88: "ECAM last interval is larger than allowed",
        90: "CAN state machine not ready (object 0x6041 in DS-402)",
        91: "Bad PVT Head Pointer",
        92: "PDO not configured",
        93: "There is a wrong initiation value for this command",
        95: "ER[3] Too large for modulo setting applied",
        96: "User program time out",
        97: "RS232 receive buffer overflow",
        98: "Cannot measure current offsets",
        99: "Bad auxiliary sensor configuration",
        100: "The requested PWM value is not supported",
        101: "Absolute encoder setting problem",
        105: "Speed loop KP out of range",
        106: "Position loop KP out of range",
        110: "Too long number",
        111: "KV vector is invalid",
        112: "KV defines scheduled block but scheduling is off",
        113: "Exp task queue is full",
        114: "Exp task queue is empty",
        115: "Exp output queue is full",
        116: "Exp output queue is empty",
        117: "Bad KV setting for sensor filter",
        118: "Bad KV setting",
        119: "Analog Sensor filter out of range",
        120: "Analog Sensor filter may contain 0 or 2 blocks",
        121: "Please wait until Analog Sensor initialized",
        122: "Motion mode is not supported or with initialization conflict",
        123: "Profiler queue is full",
        125: "Personality not loaded",
        126: "User Program failed - variable out of program size",
        127: "Modulo range must be positive",
        128: "Bad variable index in database",
        129: "Variable is not an array",
        130: "Variable name does not exist",
        131: "Cannot record local variable",
        132: "Variable is an array",
        133: "Number of function input arguments is not as expected",
        134: "Cannot run local label/function with the XQ command",
        135: "Frequency identification failed",
        136: "Not a number",
        137: "Program already compiled",
        139: "The number of break points exceeds maximal number",
        140: "An attempt to set/clear break point at the not relevant line",
        141: "Boot Identity parameters section is not clear",
        142: "Checksum of data is not correct",
        143: "Missing boot identity parameters",
        144: "Numeric Stack underflow",
        145: "Numeric stack overflow",
        146: "Expression stack overflow",
        147: "Executable command within math expression",
        148: "Nothing in the expression",
        149: "Unexpected sentence termination",
        150: "Sentence terminator not found",
        151: "Parentheses mismatch",
        152: "Bad operand type",
        153: "Overflow in a numeric operator",
        154: "Address is out of data memory segment",
        155: "Beyond stack range",
        156: "Bad op-code",
        157: "No Available program stack",
        158: "Out of flash memory range",
        159: "Flash memory verification error",
        160: "Program aborted by another thread",
        161: "Program is not halted.",
        162: "Badly formatted number.",
        163: "There is not enough space in the program data segment. Try to reduce variable usage in the user program.",
        164: "EC command (not an error)",
        165: "An attempt was made to access serial flash memory while busy.",
        166: "Out of modulo range.",
        167: "Infinite loop in for loop - zero step",
        168: "Speed too large to start motor.",
        169: "Time out using peripheral.(overflo w or busy)",
        170: "Cannot erase sector in flash memory",
        171: "Cannot read from flash memory",
        172: "Cannot write to flash memory",
        173: "Executable area of program is too large",
        174: "Program has not been loaded",
        175: "Cannot write program checksum - clear program (CP)",
        176: "User code, variables and functions are too large",
        181: "Writing to Flash program area, failed",
        182: "PAL Burn Is In Process or no PAL is burned",
        183: "PAL Burn (PB Command) Is Disabled",
        184: "Capture option already used by other operation",
        185: "This element may be modified only when interpolation is not active",
        186: "Interpolation queue is full",
        187: "Incorrect Interpolation sub-mode",
        188: "Gantry slave is disabled",
    }

    InputRegisters = {
        0: "General purpose input",
        1: "Safety",
        2: "Main home switch",
        3: "Aux. home switch",
        4: "Soft stop",
        5: "Hard stop",
        6: "Forward limit switch",
        7: "Reverse limit switch",
        8: "Inhibit switch",
        9: "Hardware motion begin",
        10: "Abort function",
        16: "Digital input 1",
        17: "Digital input 2",
        18: "Digital input 3",
        19: "Digital input 4",
        20: "Digital input 5",
        21: "Digital input 6",
    }

    def __init__(self, *args, **kwargs):
        Controller.__init__(self, *args, **kwargs)
        self._cnx = None

    def initialize(self):
        config = self.config.config_dict
        if get_comm_type(config) == UDP:
            opt = {"port": 5001, "eol": ";"}
        else:  # SERIAL
            opt = {"baudrate": 115200, "eol": ";"}

        self._cnx = get_comm(config, **opt)
        global_map.register(self, children_list=[self._cnx])

        self._elmostate = AxisState()
        for state, human in (
            ("SLAVESWITCH", "Slave switch activate"),
            ("INHIBITSWITCH", "Inhibit switch active"),
            ("CLOSEDLOOPOPEN", "Closed loop open"),
            ("DRIVEFAULT", "Problem into the drive"),
        ):
            self._elmostate.create_state(state, human)

        self._is_homing = dict()
        self._last_state = dict()
        self._is_aborted = dict()

    def initialize_hardware(self):
        # Check that the controller is alive
        try:
            self._query("VR", timeout=50e-3)
        except SocketTimeout:
            raise RuntimeError(
                "Controller Elmo (%s) is not connected" % (self._cnx._host)
            )

    def initialize_axis(self, axis):
        axis._mode = Cache(axis, "mode", default_value=None)
        self._is_homing[axis] = False
        self._last_state[axis] = None
        self._is_aborted[axis] = False

    def initialize_hardware_axis(self, axis):
        # Check user-mode
        mode = int(self._query("UM"))
        asked_mode = axis.config.get("user_mode", int, 5)
        if mode != asked_mode:
            self._query("UM=%d" % asked_mode)
        # Check closed loop on
        if self._query("MO") != "1":
            self.set_on(axis)
        mode = self._query("UM")
        axis._mode.value = int(mode)

    def close(self):
        self._cnx.close()

    def set_on(self, axis):
        self._set_power(axis, True)

    def set_off(self, axis):
        self._set_power(axis, False)

    def _set_power(self, axis, activate):
        # Activate slave if needed
        if axis.config.get("control_slave", bool, False):
            self._query("OB[1]=%d" % activate)

        self._query("MO=%d" % activate)

    def _query(self, msg, in_error_code=False, **keys):
        send_message = msg + "\r"
        raw_reply = self._cnx.write_readline(send_message.encode(), **keys)
        raw_reply = raw_reply.decode()
        if not raw_reply.startswith(send_message):  # something weird happened
            self._cnx.close()
            raise RuntimeError(
                "received reply: %s\n" "expected message starts with %s" % msg
            )
        reply = raw_reply[len(send_message) :]
        if not in_error_code and reply.endswith("?"):
            error_code = self._query("EC", in_error_code=True)
            try:
                error_code = int(error_code)
            except ValueError:  # Weird, don't know what to do
                pass
            else:
                human_error = self.ErrorCode.get(error_code, "Unknown")
                raise RuntimeError(
                    "Error %d (%s), Query (%s)" % (error_code, human_error, msg)
                )
        return reply

    def start_jog(self, axis, velocity, direction):
        self._query("JV=%d" % int(velocity * direction))
        self._query("BG")

    def stop_jog(self, axis):
        self._query("JV=0")
        self._query("BG")

        while int(self._query("MS")) in (1, 2):
            gevent.sleep(0.01)
        self._sync_pos(axis)

    def _enc_command(self, axis):
        if axis._mode == 4:
            return "PY"
        else:
            return "PX"

    def read_position(self, axis):
        if axis._mode == 2:
            return float(self._query("PX"))
        if self._last_state[axis] is not None:
            if "MOVING" in self._last_state[axis]:
                return float(self._query(self._enc_command(axis)))
        return float(self._query("PA"))

    def set_position(self, axis, new_pos):
        pos = round(new_pos)
        self._set_power(axis, False)
        self._query("%s=%d" % (self._enc_command(axis), pos))
        self._set_power(axis, True)
        self._query("PA=%d" % pos)
        return self.read_position(axis)

    def read_acceleration(self, axis):
        return int(self._query("AC"))

    def set_acceleration(self, axis, new_acc):
        self._query("AC=%d" % new_acc)
        self._query("DC=%d" % new_acc)
        return self.read_acceleration(axis)

    def read_velocity(self, axis):
        return float(self._query("SP"))

    def set_velocity(self, axis, new_vel):
        self._query("SP=%d" % new_vel)
        return self.read_velocity(axis)

    def home_search(self, axis, switch):
        # no pos can be set in home search
        # use then a home_position in config, 0.0 if not there
        # (to perform a homing without changing pos, commands are:
        #  HM[3]=3, HM[4]=0, HM[5]=2, HM[1]=1)
        home_pos = axis.config.get("home_position", float, 0.0)
        commands = [
            "HM[3]=3",
            "HM[2]=%d" % round(home_pos),
            "HM[4]=0",
            "HM[5]=0",
            "HM[1]=1",
        ]
        for cmd in commands:
            self._query(cmd)
        # Start search
        home_velocity = int(axis.config_velocity * axis.steps_per_unit)
        self.start_jog(axis, home_velocity, switch)
        self._is_homing[axis] = True

    def home_state(self, axis):
        state = self._elmostate.new()

        ans = int(self._query("SR"))
        if ans & (1 << 7):
            state.set("MOVING")
        else:
            self._end_home(axis)
            state.set("READY")

        self._last_state[axis] = state
        return state

    def _end_home(self, axis):
        self._sync_pos(axis)
        self._is_homing[axis] = False

    def _sync_pos(self, axis):
        cmd = "PA=%s" % self._enc_command(axis)
        self._query(cmd)

    def state(self, axis):
        if self._is_homing[axis]:
            return self.home_state(axis)

        state = self._elmostate.new()

        # check first that the controller is ready to move
        # bit0 of Status Register (page 3.135)
        ans = int(self._query("SR"))
        if ans & (1 << 7):
            state.set("MOVING")
        if ans & 0x1:  # problem into the drive
            state.set("DRIVEFAULT")
        if not (ans & (1 << 4)):  # closed loop open
            state.set("CLOSEDLOOPOPEN")

        # Check limits
        ans = int(self._query("IP"))
        if axis.config.get("control_slave", bool, False):
            if ans & (1 << 17):
                state.set("SLAVESWITCH")

        if ans & (1 << 6):
            state.set("LIMPOS")
        if ans & (1 << 7):
            state.set("LIMNEG")
        if ans & (1 << 8):
            # should be checked in spec ends in MOT_EMERGENCY ?
            state.set("INHIBITSWITCH")

        # Check motion state
        # Wrong if homing
        #
        ans = int(self._query("MS"))
        if ans == 0:
            state.set("READY")
        elif ans == 1 or ans == 2:
            state.set("MOVING")
        elif ans == 3:
            state.set("FAULT")

        if self._is_aborted[axis] and not "MOVING" in state:
            self._is_aborted[axis] = False
            self._sync_pos(axis)

        self._last_state[axis] = state
        return state

    def start_one(self, motion):
        # check first that the controller is ready to move
        # bit0 of Status Register (page 3.135)
        ans = int(self._query("SR"))
        if ans & 0x1:
            raise RuntimeError("problem into the drive")
        if not (ans & (1 << 4)):
            raise RuntimeError("closed loop open")

        self._query("PA=%d" % round(motion.target_pos))
        self._query("BG")

    def stop(self, axis):
        self._query("ST")
        if self._is_homing[axis]:
            self._end_home(axis)
        else:
            self._is_aborted[axis] = True

    @object_method(types_info=("None", "int"))
    def get_user_mode(self, axis):
        return int(self._query("UM"))

    @object_method(types_info=("int", "int"))
    def set_user_mode(self, axis, mode):
        commands = ["MO=0", "UM=%d" % mode]
        if mode == 2:
            commands.append("PM=1")
        commands.append("MO=1")
        for cmd in commands:
            self._query(cmd)
        if mode == 5 or mode == 4:
            axis.sync_hard()
        mode = int(self._query("UM"))
        axis._mode.value = mode
        return mode

    @object_method(types_info=("None", ("float", "float")))
    def jog_range(self, axis):
        # this method should be in emotion
        # todo move it has a generic
        jog_min = float(self._query("VL[2]"))
        jog_max = float(self._query("VH[2]"))
        return (jog_min / axis.steps_per_unit, jog_max / axis.steps_per_unit)

    @object_method(types_info=("None", "bool"))
    def get_enable_slave(self, axis):
        return bool(self._query("OB[1]"))

    @object_method(types_info=("bool", "bool"))
    def set_enable_slave(self, axis, active):
        self._query("OB[1]=%d" % active)
        return bool(self._query("OB[1]"))

    # encoders
    def initialize_encoder(self, encoder):
        pass

    def read_encoder(self, encoder):
        return float(self._query("PX"))

    def set_encoder(self, encoder, steps):
        self._query("PX=%d" % steps)

    @property
    def version(self):
        return self._query("VR")

    def __info__(self):
        info = "ELMO CONTROLLER\n"
        info += f"     version: {self.version}\n"
        info += f"     comm: {self._cnx.__info__()}"
        return info

    def get_axis_info(self, axis):
        pass

    @object_method(types_info=("None", "None"))
    def input_register(self, axis):
        inp = int(self._query("IP"))
        print(f"ELMO INPUT REGISTER = 0x{inp:x}")
        for (value, text) in self.InputRegisters.items():
            if inp & (1 << value):
                status = "ON"
            else:
                status = "OFF"
            print(f"* {text:30.30s} : {status}")

    @object_method(types_info=("None", "None"))
    def status_register(self, axis):
        status = int(self._query("SR"))
        print(f"ELMO STATUS REGISTER = 0x{status:x}")

        StatusRegisters = {
            1 << 4: "SERVO",
            1 << 5: "Ext Reference",
            1 << 6: "FAULT",
            1 << 7: "MOVING",
            1 << 12: "user program",
            1 << 13: "current limit",
            1 << 14: "safety input 1 alarm",
            1 << 15: "safety input 2 alarm",
            1 << 18: "target",
            1 << 21: "no shunt",
            1 << 22: "motor",
            1 << 23: "speed",
            1 << 24: "hall A sensor",
            1 << 25: "hall B sensor",
            1 << 26: "hall C sensor",
            1 << 27: "safe torque",
            1 << 28: "profile stop",
            1 << 30: "ptp buffer full",
        }
        for (val, txt) in StatusRegisters.items():
            print("* {0:s} : {1:s}".format(txt, status & val and "ON" or "OFF"))

        AmplifierStatus = {
            0: "OK",
            3: "UNDER voltage",
            5: "OVER voltage",
            7: "safety alarm",
            11: "over current",
            13: "over temperature",
            15: "additional ABORT activated",
        }
        val = status & (1 << 0 | 1 << 1 | 1 << 2 | 1 << 3)
        txt = AmplifierStatus.get(val, "unknown state")
        print(f"* AMPLIFIER : {txt}")

        ProfileStatus = {
            0: "none",
            1: "position",
            3: "velocity",
            4: "torque",
            6: "homing",
            7: "interpolate position",
            8: "cyclic sync position",
            9: "cyclic sync velocity",
            10: "cyclic sync torque",
        }
        val = status & (1 << 8 | 1 << 9 | 1 << 10 | 1 << 11)
        txt = ProfileStatus.get(val, "unknown state")
        print(f"* PROFILE MODE : {txt}")

        RecorderStatus = {
            0: "not active",
            1: "waiting for the trigger",
            2: "completed task",
            3: "active",
        }
        val = status & (1 << 16 | 1 << 17)
        txt = RecorderStatus.get(val, "unknown state")
        print(f"* RECORDER STATUS : {txt}")

    @object_method(types_info=("None", "None"))
    def comm_register(self, axis):
        ip_set = self._query("AA[10]")
        mask_set = self._query("AA[11]")
        gate_set = self._query("AA[12]")
        dhcp_set = int(self._query("AA[14]")) == 1 and "ENABLED" or "DISABLED"
        ip_now = self._query("AA[20]")
        mask_now = self._query("AA[21]")
        gate_now = self._query("AA[22]")
        mac_addr = self._query("AA[23]")
        info = "ELMO COMMUNICATION REGISTER:\n"
        info += f" * MAC ADDRESS : {mac_addr}\n"
        info += f" * DHCP        : {dhcp_set}\n"
        info += f" * IP ADDRESS  : {ip_now}\t[set = {ip_set}]\n"
        info += f" * GATEWAY     : {gate_now}\t[set = {gate_set}]\n"
        info += f" * SUBNET MASK : {mask_now}\t[set = {mask_set}]\n"
        print(info)
