import time

from bliss.controllers.motor import Controller
from bliss.common import log as elog
from bliss.controllers.motor import add_axis_method
from bliss.common.axis import AxisState

import pi_gcs
from bliss.comm import tcp
from bliss.common import event

"""
Bliss controller for ethernet PI E517 piezo controller.
Cyril Guilloud ESRF BLISS
Thu 13 Feb 2014 15:51:41
"""


class PI_E517(Controller):

    def __init__(self, name, config, axes):
        Controller.__init__(self, name, config, axes)
        self.host = self.config.get("host")

    def move_done_event_received(self, state):
        if self.auto_gate_enabled:
            if state is True:
                elog.info("PI_E517.py : movement is finished")
                self._set_gate(0)
                elog.debug("mvt finished, gate set to 0")
            else:
                elog.info("PI_E517.py : movement is starting")
                self._set_gate(1)
                elog.debug("mvt started, gate set to 1")

    def initialize(self):
        """
        Opens a single socket for all 3 axes.
        """
        self.sock = tcp.Socket(self.host, 50000)

    def finalize(self):
        """
        Closes the controller socket.
        """
        self.sock.close()

    def initialize_axis(self, axis):
        """
        - Reads specific config
        - Adds specific methods
        - Switches piezo to ONLINE mode so that axis motion can be caused
        by move commands.

        Args:
            - <axis>
        Returns:
            - None
        """
        axis.channel = axis.config.get("channel", int)
        axis.chan_letter = axis.config.get("chan_letter")

        add_axis_method(axis, self.get_id, types_info=(None, str))

        '''Closed loop'''
        add_axis_method(axis, self.open_loop, types_info=(None, None))
        add_axis_method(axis, self.close_loop, types_info=(None, None))

        '''DCO'''
        add_axis_method(axis, self.activate_dco, types_info=(None, None))
        add_axis_method(axis, self.desactivate_dco, types_info=(None, None))

        '''GATE'''
        # to enable automatic gating (ex: zap)
        add_axis_method(axis, self.enable_auto_gate, types_info=(bool, None))

        # to trig gate from external device (ex: HPZ with setpoint controller)
        add_axis_method(axis, self.set_gate, types_info=(bool, None))

        if axis.channel == 1:
            self.gate_axis = axis
            self.ctrl_axis = axis

        # NO automatic gating by default.
        self.auto_gate_enabled = False

        '''end of move event'''
        event.connect(axis, "move_done", self.move_done_event_received)

        # Enables the closed-loop.
        # self.sock.write("SVO 1 1\n")

        self.send_no_ans(axis, "ONL %d 1" % axis.channel)

        # VCO for velocity control mode ?
        # self.send_no_ans(axis, "VCO %d 1" % axis.channel)

        # Updates cached value of closed loop status.
        self.closed_loop = self._get_closed_loop_status(axis)

    def read_position(self, axis, measured=False,
                      last_read=[{"t": time.time(), "pos": [None, None, None]},
                                 {"t": time.time(), "pos": [None, None, None]}]):
        """
        Returns position's setpoint or measured position.
        Measured position command is POS?
        Setpoint position is MOV? of VOL? or SVA? depending on closed-loop
        mode is ON or OFF.

        Args:
            - <axis> : bliss axis.
            - [<measured>] : boolean : if True, function returns measured position.
        Returns:
            - <position> : float : piezo position in Micro-meters or in Volts.
        """
        cache = last_read[1 if measured else 0]

        if measured:
            if time.time() - cache["t"] < 0.005:
                # print "encache meas %f" % time.time()
                _pos = cache["pos"]
            else:
                # print "PAS encache meas %f" % time.time()
                _pos = self._get_pos(axis)
                cache["pos"] = _pos
                cache["t"] = time.time()
            elog.debug("position measured read : %r" % _pos)
        else:
            if time.time() - cache["t"] < 0.005:
                # print "encache not meas %f" % time.time()
                _pos = cache["pos"]
            else:
                # print "PAS encache not meas %f" % time.time()
                _pos = self._get_target_pos(axis)
                cache["pos"] = _pos
                cache["t"] = time.time()
            elog.debug("position setpoint read : %r" % _pos)

        return _pos[axis.channel - 1]

    def read_velocity(self, axis):
        """
        Args:
            - <axis> : Bliss axis object.
        Returns:
            - <velocity> : float
        """
        _ans = self.send(axis, "VEL? %s" % axis.chan_letter)
        # _ans should looks like "A=+0012.0000"
        # removes 'X=' prefix
        _velocity = float(_ans[2:])

        elog.debug("read_velocity : %g " % _velocity)
        return _velocity

    def set_velocity(self, axis, new_velocity):
        self.send_no_ans(axis, "VEL %s %f" %
                         (axis.chan_letter, new_velocity))
        elog.debug("velocity set : %g" % new_velocity)
        return self.read_velocity(axis)

#     def read_acceleration(self, axis):
#         """Returns axis current acceleration in steps/sec2"""
#         return 1
#
#     def set_acceleration(self, axis, new_acc):
#         """Set axis acceleration given in steps/sec2"""
#         pass

    def state(self, axis):
        # if self._get_closed_loop_status(axis):
        if self.closed_loop:
            # elog.debug("CLOSED-LOOP is active")
            if self._get_on_target_status(axis):
                return AxisState("READY")
            else:
                return AxisState("MOVING")
        else:
            elog.debug("CLOSED-LOOP is not active")
            return AxisState("READY")

    def prepare_move(self, motion):
        """
        - TODO for multiple move...

        Args:
            - <motion> : Bliss motion object.

        Returns:
            -

        Raises:
            - ?
        """
        pass

    def start_one(self, motion):
        """
        - Sends 'MOV' or 'SVA' depending on closed loop mode.

        Args:
            - <motion> : Bliss motion object.

        Returns:
            - None
        """
        if self.closed_loop:
            # Command in position.
            self.send_no_ans(motion.axis, "MOV %s %g" %
                             (motion.axis.chan_letter, motion.target_pos))
        else:
            # Command in voltage.
            self.send_no_ans(motion.axis, "SVA %s %g" %
                             (motion.axis.chan_letter, motion.target_pos))

    def stop(self, axis):
        """
        * HLT -> stop smoothly
        * STP -> stop asap
        * 24    -> stop asap
        * to check : copy of current position into target position ???
        """
        self.send_no_ans(axis, "HLT %s" % axis.chan_letter)

        # self.sock.write("STP\n")

    """
    Communication
    """

    def raw_write(self, cmd):
        self.send_no_ans(self.ctrl_axis, cmd)

#    def raw_write_read(self, cmd):
#        return self.send(self.ctrl_axis, cmd)

    def raw_write_read(self, cmd):
        return self.send(self.ctrl_axis, cmd)

    def send(self, axis, cmd):
        """
        - Adds the 'newline' terminator character : "\\\\n"
        - Sends command <cmd> to the PI E517 controller.
        - Channel is defined in <cmd>.
        - <axis> is passed for debugging purposes.
        - Returns answer from controller.

        Args:
            - <axis> : passed for debugging purposes.
            - <cmd> : GCS command to send to controller (Channel is already mentionned  in <cmd>).

        Returns:
            - 1-line answer received from the controller (without "\\\\n" terminator).

        """
        _cmd = cmd + "\n"
        _t0 = time.time()

        # PC
        _ans = "toto"
        _ans = self.sock.write_readline(_cmd)
        _duration = time.time() - _t0
        if _duration > 0.005:
            elog.info("PI_E517.py : Received %r from Send %s (duration : %g ms) " % (_ans, _cmd, _duration * 1000))
        return _ans

    def send_no_ans(self, axis, cmd):
        """
        - Adds the 'newline' terminator character : "\\\\n"
        - Sends command <cmd> to the PI E517 controller.
        - Channel is already defined in <cmd>.
        - <axis> is passed for debugging purposes.
        - Used for answer-less commands, thus returns nothing.
        """
        _cmd = cmd + "\n"
        self.sock.write(_cmd)

    """
    E517 specific
    """

    def _get_pos(self, axis):
        """
        Args:
            - <axis> :
        Returns:
            - <position> Returns real position (POS? command) read by capacitive sensor.

        Raises:
            ?
        """
        # _ans = self.send(axis, "POS? %s" % axis.chan_letter)
        # _pos = float(_ans[2:])
        _ans = self.sock.write_readlines("POS?\n", 3)
        _pos = map(float, [x[2:] for x in _ans])

        return _pos

    def _get_target_pos(self, axis):
        """
        Returns last target position (MOV?/SVA?/VOL? command) (setpoint value).
            - SVA? : Query the commanded output voltage (voltage setpoint).
            - VOL? : Query the current output voltage (real voltage).
            - MOV? : Returns the last valid commanded target position.
        Args:
            - <>
        Returns:
            -
        Raises:
            ?
        """
        if self.closed_loop:
            # _ans = self.send(axis, "MOV? %s" % axis.chan_letter)
            _ans = self.sock.write_readlines("MOV?\n", 3)
        else:
            # _ans = self.send(axis, "SVA? %s" % axis.chan_letter)
            _ans = self.sock.write_readlines("SVA?\n", 3)
        # _pos = float(_ans[2:])
        _pos = map(float, [x[2:] for x in _ans])
        return _pos

    def open_loop(self, axis):
        self.send_no_ans(axis, "SVO %s 0" % axis.chan_letter)

    def close_loop(self, axis):
        self.send_no_ans(axis, "SVO %s 1" % axis.chan_letter)

    """
    DCO : Drift Compensation Offset.
    """
    def activate_dco(self, axis):
        self.send_no_ans(axis, "DCO %s 1" % axis.chan_letter)

    def desactivate_dco(self, axis):
        self.send_no_ans(axis, "DCO %s 0" % axis.chan_letter)

    """
    Voltage commands
    """

    def _get_voltage(self, axis):
        """
        Returns Voltage Of Output Signal Channel (VOL? command)
        """
        _ans = self.send(axis, "VOL? %s" % axis.channel)
        _vol = float(_ans.split("=+")[-1])
        return _vol

    def _get_closed_loop_status(self, axis):
        """
        Returns Closed loop status (Servo state) (SVO? command)
        -> True/False
        """
        _ans = self.send(axis, "SVO? %s" % axis.chan_letter)
        _status = float(_ans[2:])

        if _status == 1:
            return True
        else:
            return False

    def _get_on_target_status(self, axis):
        """
        Returns << On Target >> status (ONT? command).
        True/False
        """
        _ans = self.send(axis, "ONT? %s" % axis.chan_letter)
        _status = float(_ans[2:])

        if _status == 1:
            return True
        else:
            return False

    def enable_auto_gate(self, axis, value):
        if value:
            # auto gating
            self.auto_gate_enabled = True
            self.gate_axis = axis
            elog.info("PI_E517.py : enable_gate " + value + "fro axis.channel " + axis.channel)
        else:
            self.auto_gate_enabled = False

            # for external gating
            self.gate_axis = 1

    def set_gate(self, axis, state):
        """
        Method to wrap '_set_gate' to be exported to device server.
        <axis> parameter is requiered.
        """
        self.gate_axis = axis
        self._set_gate(state)

    def _set_gate(self, state):
        """
        CTO  [<TrigOutID> <CTOPam> <Value>]+
         - <TrigOutID> : {1, 2, 3}
         - <CTOPam> :
             - 3: trigger mode
                      - <Value> : {0, 2, 3, 4}
                      - 0 : position distance
                      - 2 : OnTarget
                      - 3 : MinMaxThreshold   <----
                      - 4 : Wave Generator
             - 5: min threshold
             - 6: max threshold
             - 7: polarity : 0 / 1

        ex : CTO 1 3 3   1 5 0   1 6 100   1 7 1

        Args:
            - <state> : True / False
        Returns:
            -
        Raises:
            ?
        """
        if state:
            _cmd = "CTO %d 3 3 1 5 0 1 6 100 1 7 1" % (self.gate_axis.channel)
        else:
            _cmd = "CTO %d 3 3 1 5 0 1 6 100 1 7 0" % (self.gate_axis.channel)

        self.send_no_ans(self.gate_axis, _cmd)

    def get_id(self, axis):
        """
        Returns Identification information (\*IDN? command).
        """
        return self.send(axis, "*IDN?")

    def get_error(self, axis):
        _error_number = self.send(axis, "ERR?")
        _error_str = pi_gcs.get_error_str(_error_number)

        return (_error_number, _error_str)

    def get_info(self, axis):
        """
        Returns a set of usefull information about controller.
        Helpful to tune the device.

        Args:
            <axis> : bliss axis
        Returns:
            None
        Raises:
            ?
        """
        _infos = [
            ("Identifier                 ", "*IDN?"),
            ("Serial Number              ", "SSN?"),
            ("Com level                  ", "CCL?"),
            ("GCS Syntax version         ", "CSV?"),
            ("Last error code            ", "ERR?"),
            ("Real Position              ", "POS? %s" % axis.chan_letter),
            ("Position low limit         ", "NLM? %s" % axis.chan_letter),
            ("Position high limit        ", "PLM? %s" % axis.chan_letter),
            ("Closed loop status         ", "SVO? %s" % axis.chan_letter),
            ("Voltage output high limit  ", "VMA? %s" % axis.channel),
            ("Voltage output low limit   ", "VMI? %s" % axis.channel),
            ("Output Voltage             ", "VOL? %s" % axis.channel),
            ("Setpoint Position          ", "MOV? %s" % axis.chan_letter),
            ("Drift compensation Offset  ", "DCO? %s" % axis.chan_letter),
            ("Online                     ", "ONL? %s" % axis.channel),
            ("On target                  ", "ONT? %s" % axis.chan_letter),
            ("ADC Value of input signal  ", "TAD? %s" % axis.channel),
            ("Input Signal Position value", "TSP? %s" % axis.channel),
            ("Velocity control mode      ", "VCO? %s" % axis.chan_letter),
            ("Velocity                   ", "VEL? %s" % axis.chan_letter),
            ("Osensor                    ", "SPA? %s 0x02000200" %
             axis.channel),
            ("Ksensor                    ", "SPA? %s 0x02000300" %
             axis.channel),
            ("Digital filter type        ", "SPA? %s 0x05000000" %
             axis.channel),
            ("Digital filter Bandwidth   ", "SPA? %s 0x05000001" %
             axis.channel),
            ("Digital filter order       ", "SPA? %s 0x05000002" %
             axis.channel),
        ]

        _txt = ""

        for i in _infos:
            _txt = _txt + "    %s %s\n" % \
                (i[0], self.send(axis, i[1]))

        _txt = _txt + "    %s  \n%s\n" % \
            ("Communication parameters",
             "\n".join(self.sock.write_readlines("IFC?\n", 6)))

        _txt = _txt + "    %s  \n%s\n" % \
            ("Firmware version",
                "\n".join(self.sock.write_readlines("VER?\n", 3)))

        return _txt
