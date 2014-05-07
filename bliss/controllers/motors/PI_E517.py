import time

from bliss.controllers.motor import Controller
from bliss.controllers.motor import add_axis_method
from bliss.common.axis import READY, MOVING

import pi_gcs
from bliss.comm import tcp

"""
Bliss controller for ethernet PI E517 piezo controller.
Cyril Guilloud ESRF BLISS
Thu 13 Feb 2014 15:51:41
"""


def e517_err(msg):
    log.error("[PI_E517] " + msg)

def e517_info(msg):
    log.info("[PI_E517] " + msg)

def e517_debug(msg):
    log.debug("[PI_E517] " + msg)


class PI_E517(Controller):

    def __init__(self, name, config, axes):
        Controller.__init__(self, name, config, axes)

        self.host = self.config.get("host")

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
        Switches piezo to ONLINE mode so that axis motion can be caused
        by move commands.

        Args:
            - <axis>
        Returns:
            - None
        """
        axis.channel = axis.config.get("channel", int)
        axis.chan_letter = axis.config.get("chan_letter")

        add_axis_method(axis, self.get_id)
        add_axis_method(axis, self.get_info)
        add_axis_method(axis, self.steps_per_unit)

        # Enables the closed-loop.
        # self.sock.write("SVO 1 1\n")

        self.send_no_ans(axis, "ONL %d 1" % axis.channel)

        # VCO for velocity control mode ?
        # self.send_no_ans(axis, "VCO %d 1" % axis.channel)

        # Updates cached value of closed loop status.
        self.closed_loop = self._get_closed_loop_status(axis)

    def read_position(self, axis, measured=False):
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
        if measured:
            _pos = self._get_pos(axis)
            e517_debug("position measured read : %g" % _pos)
        else:
            _pos = self._get_target_pos(axis)
            e517_debug("position setpoint read : %g" % _pos)

        return _pos

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

        e517_debug("read_velocity : %g " % _velocity)
        return _velocity

    def set_velocity(self, axis, new_velocity):
        self.send_no_ans(axis, "VEL %s %f" %
                         (axis.chan_letter, new_velocity))
        e517_debug( "velocity set : %g" % new_velocity)
        return self.read_velocity(axis)

    def state(self, axis):
        # if self._get_closed_loop_status(axis):
        if self.closed_loop:
            e517_debug("CLOSED-LOOP is active")
            if self._get_on_target_status(axis):
                return READY
            else:
                return MOVING
        else:
            e517_debug("CLOSED-LOOP is not active")
            return READY

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

        Args:
            - <axis> : Bliss axis object.

        Returns:
            -

        Raises:
            - ?
        """


        self.send_no_ans(axis, "HLT %s" % axis.chan_letter)

    """
    E517 specific communication
    """

    def steps_per_unit(self, axis, new_steps_per_unit=None):
        """
        - 

        Args:
            - <axis> : Bliss axis object.
            - [<new_steps_per_unit>] : float : 

        Returns:
            -

        Raises:
            - ?
        """
        if new_steps_per_unit is None:
            return float(axis.config.get("steps_per_unit"))
        else:
            print "steps_per_unit writing is not (yet?) implemented."

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

        Raises:
            ?
        """
        _cmd = cmd + "\n"
        _t0 = time.time()

        #PC
        _ans = "toto"
        _ans = self.sock.write_readline(_cmd)
        _duration = time.time() - _t0
        if _duration > 0.005:
            print "E517 Received %s from Send %s (duration : %g ms) " % (repr(_ans), _cmd, _duration * 1000)

        return _ans

    def send_no_ans(self, axis, cmd):
        """
        - Adds the 'newline' terminator character : "\\\\n"
        - Sends command <cmd> to the PI E517 controller.
        - Channel is defined in <cmd>.
        - <axis> is passed for debugging purposes.
        - Used for answer-less commands, then returns nothing.

        Args:
            - <axis> : 
            - <cmd> : 

        Returns:
            - None

        Raises:
            ?
        """
        _cmd = cmd + "\n"
        self.sock.write(_cmd)

    def _get_pos(self, axis):
        """
        Args:
            - <axis> : 
        Returns:
            - <position> Returns real position (POS? command) read by capacitive sensor.

        Raises:
            ?
        """
        _ans = self.send(axis, "POS? %s" % axis.chan_letter)
        _pos = float(_ans[2:])

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
            _ans = self.send(axis, "MOV? %s" % axis.chan_letter)
        else:
            _ans = self.send(axis, "SVA? %s" % axis.chan_letter)
        _pos = float(_ans[2:])
        return _pos

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
        - 

        Args:
            - <>
        Returns:
            -
        Raises:
            - ?
        """
        """
        Returns On Target status (ONT? command).
        True/False
        """
        _ans = self.send(axis, "ONT? %s" % axis.chan_letter)
        _status = float(_ans[2:])

        if _status == 1:
            return True
        else:
            return False

    def activate_threshold_trigger(self, axis, min, max):
        """
        CTO  {<TrigOutID> <CTOPam> <Value>}
         - <TrigOutID> : {1, 2, 3}
         - <CTOPam> :
             - 3: trigger mode
             - 5: min threshold
             - 6: max threshold
         - <Value> : {0, 2, 3, 4}
             - 0 : 
             - 2 : 
             - 3 : 
             - 4 : 
 
        Args:
            - <>
        Returns:
            -
        Raises:
            ?
        """

        _cmd = "CTO %d " % (axis.channel)

    def get_id(self, axis):
        """
        Returns Identification information (\*IDN? command).
        """
        return self.send(axis, "*IDN?\n")

    def get_error(self, axis):
        _error_number = self.send(axis, "ERR?\n")
        _error_str = pi_gcs.get_error_str(_error_number)

        return (_error_number, _error_str)

    def _stop(self):
        """
        Sends a stop to the controller (STP command).
        """
        self.sock.write("STP\n")

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
