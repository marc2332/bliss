# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2017 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.comm.util import get_comm_type, get_comm, SERIAL
from bliss.comm.serial import SerialTimeout
from bliss.common.utils import object_method
from bliss.common.axis import AxisState
from bliss.config.channels import Cache
from bliss.controllers.motor import Controller
from bliss.common import session
from bliss.common.logtools import *

import time
import sys


class Elmo_whistle(Controller):
    """
    Elmo motor controller

    configuration example:
    - name: MR_SROT
      class: Elmo_whistle
      serial:
        url: tango://id19/serialrp_192/20
      axes:
        - name: mrsrot
          steps_per_unit: 12800 
          velocity: 22.5    # deg/s
          acceleration: 45  # deg/s2
          user_mode: 5
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

    def __init__(self, *args, **kwargs):
        Controller.__init__(self, *args, **kwargs)
        self._cnx = None

    def initialize(self):
        log_info(self, "Entering")

        config = self.config.config_dict
        if get_comm_type(config) == SERIAL:
            opt = {"baudrate": 19200, "eol": ";"}
        else:  # Not SERIAL
            raise RuntimeError("Serial line is not configured!")

        self._cnx = get_comm(config, **opt)
        session.get_current().map.register(self, children_list=[self._cnx])

        self._elmostate = AxisState()
        for state, human in (
            ("INHIBITSWITCH", "Inhibit switch active"),
            ("CLOSEDLOOPOPEN", "Closed loop open"),
            ("DRIVEFAULT", "Problem with the Elmo controller"),
            ("SPEEDCONTROL", "Speed control mode is acive"),
        ):
            self._elmostate.create_state(state, human)

        # Internal variables
        self.off_limit_sleep_time = 1  # seconds
        self.stopped = False

    def initialize_hardware(self):
        log_info(self, "Entering")

        # Check that the controller is alive
        try:
            self._query("VR")
        except SerialTimeout:
            raise RuntimeError(
                "Controller Elmo (%s) is not connected" % (self._cnx._port)
            )

    def initialize_axis(self, axis):
        log_info(self, "Entering for %s" % axis.name)
        axis._mode = Cache(axis, "mode", default_value=None)

    def initialize_hardware_axis(self, axis):
        log_info(self, "Entering for %s" % axis.name)

        # Check user-mode
        mode = int(self._query("UM"))
        asked_mode = axis.config.get("user_mode", int, 5)
        if mode != asked_mode:
            self.set_user_mode(axis, asked_mode)

        # Check closed loop on
        if self._query("MO") != "1":
            self.set_on(axis)
        mode = self._query("UM")
        axis._mode.value = int(mode)
        log_info(self, "%s init done!" % axis.name)

    def set_on(self, axis):
        log_info(self, "Entering for %s" % axis.name)
        self._set_power(axis, True)

    def set_off(self, axis):
        log_info(self, "Entering for %s" % axis.name)
        self._set_power(axis, False)

    def _set_power(self, axis, activate):
        log_info(self, "Entering for %s" % axis.name)
        self._query("MO=%d" % activate)

    def _query(self, msg, in_error_code=False, **keys):
        log_debug(self, "Entering for cmd = %s" % msg)

        send_message = msg + "\r"

        # Some controllers show communication problems.
        # timeouts or corrupted answers!
        # Just flush and retry to make it work!
        #

        retry = 0
        while retry < 3:
            try:
                raw_reply = self._cnx.write_readline(send_message.encode(), **keys)
                raw_reply = raw_reply.decode()

                if not raw_reply.startswith(send_message):  # something weird happened
                    raise RuntimeError(
                        "received reply: %s\n\n expected message starts with %s\n\n"
                        % (raw_reply, msg)
                    )
                else:
                    retry = 3
            except (SerialTimeout, RuntimeError) as e:
                retry = retry + 1
                # print exception and number of tries done
                sys.excepthook(*sys.exc_info())

                if retry >= 3:
                    # re-throw the caught exception
                    raise e

        reply = raw_reply[len(send_message) :]
        if not in_error_code and reply.endswith("?"):
            error_code = self._query("EC", in_error_code=True)
            try:
                error_code = int(error_code)
            except ValueError:
                raise RuntimeError(
                    "Something weired happed, could not decode error code!"
                )
            else:
                human_error = self.ErrorCode.get(error_code, "Unknown")
                raise RuntimeError(
                    "Error %d (%s), Query (%s)" % (error_code, human_error, msg)
                )

        log_debug(self, "Leaving with reply = %s" % reply)
        return reply

    def _check_move_conditions(self):
        log_info(self, "Entering")

        sleep = False

        ans = int(self._query("SR"))
        # No movements allowd in speed control mode
        mode = (ans & (0x7 << 7)) >> 7
        if mode == 2:
            raise RuntimeError("Speed Control Mode: No movements allowed!")

        # check first that the controller is ready to move
        # bit0 of Status Register (page 3.135)
        if ans & 0x1:
            raise RuntimeError("Problem with the Elmo controller")
        if not (ans & (1 << 4)):
            raise RuntimeError("The positioning loop is open")

        # A sleep time is necessary to leave the limit switch without stopping
        # the movement again in state()
        ans_ip = int(self._query("IP"))
        if ans_ip & (1 << 10) | ans_ip & (1 << 11):
            sleep = True

        return sleep

    def start_jog(self, axis, velocity, direction):
        log_info(
            self, "Entering for %s with %f and %d" % (axis.name, velocity, direction)
        )

        # switch the controller mode
        self.set_user_mode(axis, 2)

        self._query("JV=%d" % (velocity * direction))
        self._query("BG")

    def stop_jog(self, axis):
        log_info(self, "Entering for %s" % axis.name)

        # stop the movement
        self._query("JV=0")
        self._query("BG")

        # wait for stabilization
        time.sleep(1)

        # switch the user mode
        self.set_user_mode(axis, 5)

    @object_method(types_info=("None", ("float", "float")))
    def jog_range(self, axis):
        log_info(self, "Entering for %s" % axis.name)

        # this method should be in emotion
        # to use it in real units
        return float(self._query("VL[2]")), float(self._query("VH[2]"))

    def read_position(self, axis):
        log_info(self, "Entering for %s" % axis.name)

        # Rotary movements use the main encoder PX and
        # linear movements use the auxillary encoder PY
        encoder_name = "PY" if axis._mode.value == 4 else "PX"
        log_debug(self, "Encoder %s" % encoder_name)

        # In speed control mode, always return encoder position
        if axis._mode.value == 2:
            return float(self._query(encoder_name))
        else:
            # In position mode, returns:
            # encoder position if moving
            # command position if motion finished

            sta = int(self._query("MS"))
            if sta == 2:
                return float(self._query(encoder_name))
            else:
                # Workaround for controller bug: when a limit switch is hit,
                # some times the PA position is wrong, only the encoder one
                # can be trusted
                #
                # workaround for controller bug: on a ST command the PA remains
                # to the target value and therefore is no more synchronized
                # with the PX encoder value. Force PA to the PX value.

                if self.stopped:
                    # give some time for the encoder stabilization
                    time.sleep(0.1)
                    # set the encoder position as requested value
                    pos = int(self._query(encoder_name))
                    self._query("PA=%d" % pos)

                    self.stopped = False

                return float(self._query("PA"))

    def set_position(self, axis, new_pos):
        log_info(self, "Entering for %s with dial = %f" % (axis.name, new_pos))

        pos = round(new_pos)
        self._set_power(axis, False)
        encodeur_name = "PY" if axis._mode.value == 4 else "PX"
        self._query("%s=%d" % (encodeur_name, pos))
        self._set_power(axis, True)
        self._query("PA=%d" % pos)
        return self.read_position(axis)

    def read_acceleration(self, axis):
        log_info(self, "Entering for %s" % axis.name)
        return int(self._query("AC"))

    def set_acceleration(self, axis, new_acc):
        log_info(self, "Entering for %s with acc = %f" % (axis.name, new_acc))

        self._query("AC=%d" % new_acc)
        self._query("DC=%d" % new_acc)
        return self.read_acceleration(axis)

    def read_velocity(self, axis):
        log_info(self, "Entering for %s" % axis.name)
        return float(self._query("SP"))

    def set_velocity(self, axis, new_vel):
        log_info(self, "Entering for %s with velocity = %f" % (axis.name, new_vel))

        self._query("SP=%d" % new_vel)
        return self.read_velocity(axis)

    def home_search(self, axis, switch, set_pos=None):
        log_info(self, "Entering for %s with switch = %s" % (axis.name, switch))

        # Check the conditions to allow the movement
        sleep = self._check_move_conditions()

        # can't set the position when searching home
        # we should change emotion to add an option in
        # home search i.e: set_pos = None
        if set_pos is not None:
            set_pos = round(set_pos * switch * axis.steps_per_unit)
            commands = [
                "HM[3]=3",
                "HM[2]=%d" % round(set_pos),
                "HM[4]=0",
                "HM[5]=0",
                "HM[1]=1",
            ]
        else:
            commands = ["HM[3]=3", "HM[4]=0", "HM[5]=2", "HM[1]=1"]
        for cmd in commands:
            self._query(cmd)

        # Start search
        step_sign = 1 if axis.config.get("steps_per_unit", float) > 0 else -1
        self._query("JV=%d" % (switch * step_sign * self.read_velocity(axis)))
        self._query("BG")

        # Sleep only necessary when moving away from a limit switch
        if sleep:
            # print ("Sleep at start!!!!!!")
            time.sleep(self.off_limit_sleep_time)

    def home_state(self, axis):
        log_info(self, "Entering for %s" % axis.name)

        ans = int(self._query("SR"))
        if ans & (1 << 11):
            return AxisState("MOVING")
        else:
            ans = self._query("PA=DV[3]")

            # Need to call stop axis to clear the bit 14 of the status register!
            self.stop(axis)
            # axis.sync_hard()
            # self.homing = False

            return AxisState("READY")

    def state(self, axis):
        log_info(self, "Entering for %s" % axis.name)

        state = self._elmostate.new()

        # check first that the controller is ready to move
        # bit0 of Status Register (page 3.135)
        ans = int(self._query("SR"))
        log_info(
            self, "Moving state for %s : %d" % (axis.name, (ans & (0x3 << 14)) >> 14)
        )
        # print ("state = %d" % ((ans & (0x3 << 14)) >> 14))

        if ans & (0x3 << 14):
            state.set("MOVING")
        else:
            state.set("READY")

        # Check for problems
        if ans & 0x1:  # problem detected by the elmo driver
            state.set("DRIVEFAULT")
        if not (ans & (1 << 4)):  # closed loop open
            state.set("CLOSEDLOOPOPEN")

        # check the controller mode
        mode = (ans & (0x7 << 7)) >> 7
        if mode == 2:
            state.set("SPEEDCONTROL")

        # Check limits
        ans_ip = int(self._query("IP"))
        if ans_ip & (1 << 10):
            # print ("limit ON")

            # We need to send a stop command, otherwise the controller status bits will stay moving!
            if state.current_states() == "MOVING (Axis is MOVING)":
                if int(((ans & (0x3 << 14)) >> 14)) == 2:
                    # print ("stop now!")
                    self.stop(axis)
            state.set("LIMPOS")

        if ans_ip & (1 << 11):
            print("limit ON")
            # We need to send a stop command, otherwise the controller status bits will stay moving!
            if state.current_states() == "MOVING (Axis is MOVING)":
                if int(((ans & (0x3 << 14)) >> 14)) == 2:
                    # print ("stop now!")
                    self.stop(axis)
            state.set("LIMNEG")

        if ans_ip & (1 << 12):
            # should be checked, ends in MOT_EMERGENCY
            state.set("INHIBITSWITCH")

        return state

    def start_one(self, motion):
        log_info(self, "Entering for %s" % motion.axis.name)

        # Check the conditions to allow the movement
        sleep = self._check_move_conditions()

        # start movement
        self._query("PA=%d" % round(motion.target_pos))
        self._query("BG")

        # Sleep only necessary when moving away from a limit switch
        if sleep:
            # print ("Sleep at start!!!!!!")
            time.sleep(self.off_limit_sleep_time)

    def stop(self, axis):
        log_info(self, "Entering for %s" % axis.name)

        # Stop cannot be executed in speed control mode
        if axis._mode.value != 2:

            self._query("ST")
            self.stopped = True

            # If the move status is not changing to 0, we have to open and close the regulation loop!
            sta = 1
            nst = 0
            while sta and (nst < 10):
                time.sleep(0.1)
                sta = int(self._query("MS"))
                nst += 1

            if nst == 10:
                self.set_off(axis)
                time.sleep(0.1)
                self.set_on(axis)
                # print ("Off/On done")

            # be sure to have the dial value correponding to the controller position
            axis.sync_hard()

    @object_method(types_info=("None", "int"))
    def get_user_mode(self, axis):
        log_info(self, "Entering for %s" % axis.name)
        return int(self._query("UM"))

    @object_method(types_info=("int", "int"))
    def set_user_mode(self, axis, mode):
        log_info(self, "Entering for %s with mode = %d" % (axis.name, mode))

        commands = ["MO=0", "UM=%d" % mode]
        if mode == 2:
            commands.append("PM=1")

        commands.append("MO=1")
        for cmd in commands:
            self._query(cmd)

        if mode == 5 or mode == 4:
            # set the encoder position as requested value
            encoder_name = "PY" if axis._mode.value == 4 else "PX"
            log_debug(self, "Encoder %s" % encoder_name)
            pos = int(self._query(encoder_name))
            self._query("PA=%d" % pos)

            axis.sync_hard()

        mode = int(self._query("UM"))
        axis._mode.value = mode

        return mode

    def limit_search(self, axis, limit):
        log_info(self, "Entering for %s with limit = %d" % (axis.name, limit))

        # Check the conditions to allow the movement
        sleep = self._check_move_conditions()

        # Start search
        step_sign = 1 if axis.config.get("steps_per_unit", float) > 0 else -1
        self._query("JV=%d" % (limit * step_sign * self.read_velocity(axis)))
        self._query("BG")

        if sleep:
            time.sleep(self.off_limit_sleep_time)

    # encoders
    def initialize_encoder(self, encoder):
        log_info(self, "Entering for %s" % encoder.name)

    def read_encoder(self, encoder):
        log_info(self, "Entering for %s" % encoder.name)

        mode = int(self._query("UM"))
        encoder_name = "PY" if mode == 4 else "PX"

        return float(self._query(encoder_name))

    def set_encoder(self, encoder, steps):
        log_info(self, "Entering for %s with steps = %d" % (encoder.name, steps))

        mode = int(self._query("UM"))
        encoder_name = "PY" if mode == 4 else "PX"

        self._query("%s=%d" % (encoder_name, steps))

    @object_method(types_info=("None", "string"))
    def get_id(self, axis):
        log_info(self, "Entering for %s" % axis.name)
        return self._query("VR")

    def get_info(self, axis):
        log_info(self, "Entering for %s" % axis.name)

        print("\nStatus Register:")
        _status = int(self._query("SR"))
        print("SR> ---- [0x%08x]" % _status)

        val = _status & ((1 << 0) | (1 << 1) | (1 << 2) | (1 << 3))
        prefix = "AMPLIFIER"
        if val == 0:
            print("--- %s: %s" % (prefix, "OK"))
        else:
            if val == 3:
                print("--- %s: %s" % (prefix, "UNDER voltage"))
            if val == 5:
                print("--- %s: %s" % (prefix, "OVER voltage"))
            if val == 11:
                print("--- %s: %s" % (prefix, "SHORT CIRCUIT"))
            if val == 13:
                print("--- %s: %s" % (prefix, "OVER Temperature"))
            else:
                print("--- %s: %s [%d]" % (prefix, "unknown value", val))

        val = _status & (1 << 4)
        print("--- %s: %s" % ("SERVO", "enabled" if val else "disabled"))
        val = _status & (1 << 5)
        print("--- %s: %s" % ("Ext. Reference", "enabled" if val else "disabled"))
        val = _status & (1 << 6)
        print("--- %s: %s" % ("Motor Failure", "Ocurred" if val else "none"))
        val = _status & (1 << 11)
        print("--- %s: %s" % ("Homing", "activated" if val else "none"))
        val = _status & (1 << 12)
        print("--- %s: %s" % ("User Program", "running" if val else "NOT running"))
        val = _status & (1 << 13)
        print("--- %s: %s" % ("Current Limit", "limited to CL[1]" if val else "none"))

        val = _status & (((1 << 16) | (1 << 17)) >> 16)
        prefix = "RECORDER status"
        if val == 0:
            print("--- %s: %s" % (prefix, "NOT active"))
        else:
            if val == 1:
                print("--- %s: %s" % (prefix, "Waiting for the trigger"))
            if val == 2:
                print("--- %s: %s" % (prefix, "Completed, data ready to use"))
            if val == 3:
                print("--- %s: %s" % (prefix, "Active"))

        val = _status & (1 << 28)
        print("--- %s: %s" % ("Limit Switch", "activated" if val else "none"))

        print("\nInput Port Register:")
        _status = int(self._query("IP"))
        print("IP> ---- [0x%08x]" % _status)

        if _status & (1 << 6):
            print("--- Main home switch : Active")
        if _status & (1 << 7):
            print("--- Auxillary home switch : Active")
        if _status & (1 << 8):
            print("--- Soft stop : Active")
        if _status & (1 << 9):
            print("--- Hard stop : Active")
        if _status & (1 << 10):
            print("--- Forward limit : Active")
        if _status & (1 << 11):
            print("--- Reverse limit : Active")
        if _status & (1 << 12):
            print("--- Inhibit switch : Active")
        if _status & (1 << 13):
            print("--- Hardware motion begin : Active")
        if _status & (1 << 14):
            print("--- Abort function : Active")

        if _status & (1):
            print("--- General purpose input 1 : Active")
        if _status & (1 << 1):
            print("--- General purpose input 2 : Active")
        if _status & (1 << 2):
            print("--- General purpose input 3 : Active")
        if _status & (1 << 3):
            print("--- General purpose input 4 : Active")
        if _status & (1 << 4):
            print("--- General purpose input 5 : Active")
        if _status & (1 << 5):
            print("--- General purpose input 6 : Active")

        if _status & (1 << 16):
            print("--- Digital input 1 : Active")
        if _status & (1 << 17):
            print("--- Digital input 2 : Active")
        if _status & (1 << 18):
            print("--- Digital input 3 : Active")
        if _status & (1 << 19):
            print("--- Digital input 4 : Active")
        if _status & (1 << 20):
            print("--- Digital input 5 : Active")
        if _status & (1 << 21):
            print("--- Digital input 6 : Active")
        if _status & (1 << 22):
            print("--- Digital input 7 : Active")
        if _status & (1 << 23):
            print("--- Digital input 8 : Active")
        if _status & (1 << 24):
            print("--- Digital input 9 : Active")
        if _status & (1 << 25):
            print("--- Digital input 10 : Active")
