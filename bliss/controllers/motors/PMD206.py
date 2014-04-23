import time

from bliss.controllers.motor import Controller; from bliss.common import log
from bliss.controllers.motor import add_axis_method
from bliss.common.axis import READY, MOVING, FAULT

from bliss.comm import tcp

"""
Bliss controller for PiezoMotor PMD206 piezo motor controller.
Ethernet
Cyril Guilloud ESRF BLISS
Thu 10 Apr 2014 09:18:51
"""


def pmd206_err(msg):
    log.error("[PMD206] " + msg)


def pmd206_info(msg):
    log.info("[PMD206] " + msg)


def pmd206_debug(msg):
    log.debug("[PMD206] " + msg)


class PMD206(Controller):
    def __init__(self, name, config, axes):
        Controller.__init__(self, name, config, axes)

        self._controller_error_codes = [
            (0x8000, "Abnormal reset detected."),
            (0x4000, "ComPic cannot communicate internally with MotorPic1 or MotorPic2"),
            (0x2000, "MotorPic2 has sent an unexpected response (internal error)"),
            (0x1000, "MotorPic1 has sent an unexpected response (internal error)"),
            (0x800, "Error reading ADC. A voltage could not be read"),
            (0x400, "48V level low or high current draw detected"),
            (0x200, "5V level on driver board outside limits"),
            (0x100, "3V3 level on driver board outside limits"),
            (0x80, "Sensor board communication error detected"),
            (0x40, "Parity or frame error RS422 sensor UART. Check cable/termination"),
            (0x20, "Wrong data format on external sensor (RS422 or TCP/IP)"),
            (0x10, "External sensor not detected (RS422 and TCP/IP)"),
            (0x8, "Problem with UART on host. Check cable and termination"),
            (0x4, "Host command error - driver board (e.g. buffer overrun)"),
            (0x2, "300 ms command timeout ocurred"),
            (0x1, "Command execution gave a warning"),
            ]

        self._motor_error_codes = [
            (0x80, "48V low or other critical error, motor is stopped"),
            (0x40, "Temperature limit reached, motor is stopped"),
            (0x20, "Motor is parked"),
            (0x10, "Max or min encoder limit was reached in target mode, \
            or motor was stopped due to external limit signal "),
            (0x8, "Target mode is active"),
            (0x4, "Target position was reached (if target mode is active). \
            Also set during parking/unparking. "),
            (0x2, "Motor direction"),
            (0x1, "Motor is running"),
            ]

        self.host = self.config.get("host")

    def initialize(self):
        """
        Opens a single communication socket to the controller for all 1..6 axes.
        """
        self.sock = tcp.Socket(self.host, 9760)

    def finalize(self):
        """
        Closes the controller socket.
        """
        self.sock.close()

    def initialize_axis(self, axis):
        """

        Args:
            - <axis>
        Returns:
            - None
        """
        axis.channel = axis.config.get("channel", int)

        add_axis_method(axis, self.get_info)
        add_axis_method(axis, self.steps_per_unit)

        # Enables the closed-loop.
        # self.send(axis, "CM=0")

    # int_to_hex :  int("41a", 16)
    # hex_to_int :  hex(1050)[2:]

    def read_position(self, axis, measured=False):
        """
        Returns position's setpoint or measured position.

        Args:
            - <axis> : bliss axis.
            - [<measured>] : boolean : if True, function returns measured position
              otherwise returns last target position.
        Returns:
            - <position> : float :
        """
        #                      1234567812345678
        # example of answer : 'PM11MP?:fffffff6'

        if measured:
            _ans = self.send(axis, "MP?")
            _pos = int(_ans[8:], 16)
            pmd206_debug("PMD206 position measured read : %d (_ans=%s)" % (_pos, _ans))
        else:
            _ans = self.send(axis, "TP?")
            _pos = int(_ans[8:], 16)
            pmd206_debug("PMD206 position setpoint read : %d (_ans=%s)" % (_pos, _ans))

        return _pos

    def read_velocity(self, axis):
        """
        Speed ramp up in target mode - wfm-steps per second per millisecond

        Args:
            - <axis> : Bliss axis object.
        Returns:
            - <velocity> : float
        """
        _ans = self.send(axis, "CP?9")
        #                           123456789
        # _ans should looks like : 'PM11CP?9:00000030'
        # Removes 9 firsts characters.
        _velocity = int(_ans[9:], 16)

        # Test velocity to be in good range ?
        if _velocity < 1:
            _velocity = 1

        if _velocity > 50:
            _velocity = 50

            # etc ?

        pmd206_debug("read_velocity : %d" % _velocity)
        return _velocity

    def set_velocity(self, axis, new_velocity):

        # !!!! must be converted  ?
        # _nv = hex(new_velocity)[2:]

        _nv = 30
        self.send(axis, "CP=9,%d" % _nv)

        pmd206_debug("velocity wrotten : %d " % _nv)

        return self.read_velocity(axis)

    def pmd206_get_status(self, axis):
        '''
        Sends status command (CS?) and puts results (hexa strings) in :
        - self._ctrl_status
        - self._axes_status[1..6]

        '''
        # broadcast command -> returns status of all 6 axis
        # _ans should looks like : 'PM11CS?:0100,20,20,20,20,20,20'

        # ~ 1.6ms
        _ans = self.send(axis, "CS?")

        self._axes_status = dict()

        (self._ctrl_status, self._axes_status[1], self._axes_status[2],
         self._axes_status[3], self._axes_status[4], self._axes_status[5],
         self._axes_status[6]) = _ans.split(':')[1].split(',')

        pmd206_debug("ctrl status : %s" % self._ctrl_status)
        pmd206_debug("mot1 status : %s" % self._axes_status[1])
        pmd206_debug("mot2 status : %s" % self._axes_status[2])
        pmd206_debug("mot3 status : %s" % self._axes_status[3])
        pmd206_debug("mot4 status : %s" % self._axes_status[4])
        pmd206_debug("mot5 status : %s" % self._axes_status[5])
        pmd206_debug("mot6 status : %s" % self._axes_status[6])

    def get_controller_status(self):
        '''
        Returns a string build with all status of controller.
        '''
        _s = int(self._ctrl_status, 16)
        _status = ""

        for _c in self._controller_error_codes:
            if _s & _c[0]:
                print _c[1]
                _status.append(_c[1]+"\n")

        return _status

    def get_motor_status(self, axis):
        '''
        Returns a string build with all status of motor <axis>.
        '''
        _s = int(self._axes_status[axis.channel], 16)
        _status = ""

        for _c in self._motor_error_codes:
            if _s & _c[0]:
                print _c[1]
                _status.append(_c[1]+"\n")

        return _status

    def motor_state(self, axis):
        _s = int(self._axes_status[axis.channel], 16)

        pmd206_debug("axis %d status : %s" % (axis.channel, self._axis_status))

        if _s & 0x01:
            # motor is running
            if _s - 0x20:
                return FAULT
            else:
                return MOVING
        else:
            return READY

    def state(self, axis):
        # Read status fronm controller.
        self.pmd206_get_status(axis)

        return self.motor_state(axis)

    def status(self, axis):
        '''
        Returns a string composed by controller and motor status string.
        '''
        return self.get_controller_status() + "\n\n" + self.get_motor_status(axis)

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
        - Sends

        Args:
            - <motion> : Bliss motion object.

        Returns:
            - None
        """
        pass
        # self.send(axis, "TP=%s" %  hex(motion.target_pos)[2:])

    def stop(self, axis):
        """
        Stops all axis motions.
        Args:
            - <axis> : Bliss axis object.

        Returns:
            -

        Raises:
            - ?
        """
        self.send(axis, "CS=0")

    def steps_per_unit(self, axis, new_step_per_unit=None):
        """
        -

        Args:
            - <axis> : Bliss axis object.
            - [<new_step_per_unit>] : float :

        Returns:
            -

        Raises:
            - ?
        """
        if new_step_per_unit is None:
            return float(axis.config.get("step_size"))
        else:
            print "steps_per_unit writing is not (yet?) implemented."

    """
    PMD206 specific communication
    """
    def send(self, axis, cmd):
        """
        - Adds 'CP<x><y>' prefix
        - Adds the 'carriage return' terminator character : "\\\\r"
        - Sends command <cmd> to the PMD206 controller.
        - Channel is defined in <cmd>.
        - <axis> is passed for debugging purposes.
        - if <axis> is 0 : sends a broadcast message.

        Args:
            - <axis> : passed for debugging purposes.
            - <cmd> : command to send to controller (Channel is already mentionned  in <cmd>).

        Returns:
            - Answer from controller for get commands.
            - True if for successful set commands.

        Raises:
            ?
        """
        _prefix = "PM%d%d" % (1, axis.channel)
        _cmd = _prefix + cmd + "\r"
        _t0 = time.time()

        _ans = self.sock.write_readline(_cmd, eol='\r')

        pmd206_debug("send(%s) returns : %s " % (_cmd, _ans))

        set_command = cmd[:3] in ["DR=", "CS=", "TP=", "TR=", "RS="]

        if set_command:
            print "SET COMMAD "
            if _ans != _cmd:
                print "oh oh "

        _duration = time.time() - _t0
        if _duration > 0.005:
            print "PMD206 Received %s from Send %s (duration : %g ms) " % \
                  (repr(_ans), _cmd, _duration * 1000)

        return _ans

    def get_error(self, axis):
        pass

    def print_error(err):
        (_err_code, _pos, _ascii, _errstr) = err.split('=')[1].split(',')
        print "---------ERROR--------------"
        print " code   =", _err_code
        print " pos    =", _pos
        print " ascii  =", _ascii
        print " string =", _errstr
        print "----------------------------"

    def do_homing(self, axis, freq, max_steps, max_counts, first_dir):
        self.send("HO=%d,%d,%d,%d,%d,%d" % (freq, max_steps, max_counts,
                                            first_dir, max_steps, max_counts))

    def homing_sequence_status_string(self, status):
        _home_status_table = [
            ('0c', "initiating"),
            ('0b', "starting index mode 3"),
            ('0a', "starting direction 1"),
            ('09', "running direction 1"),
            ('08', "starting direction 2"),
            ('07', "running direction 2"),
            ('06', "is encoder counting ?"),
            ('05', "running direction 2"),
            ('04', "end direction 2"),
            ('03', "stopped with error"),
            ('02', "index not found"),
            ('01', "index was found"),
            ('00', "not started")
            ]
        print _home_status_table

    def park_motor(self, axis):
        self.send(axis, "CC=1")

    def unpark_motor(self, axis):
        self.send(axis, "CC=0")

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
            ("Firmware version               ", "SV?"),
            ("Extended Version Information   ", "XV?"),
            ("Controller status              ", "CS?"),
            ("Extended Controller status     ", "XS?"),
            ("Closed loop status             ", "CM?"),
            ("Motor Position                 ", "MP?"),
            ("Status of Homing Sequence      ", "HO?"),
            ("Cycle counter                  ", "CP?0"),
            ("Parking and initialization     ", "CP?1"),
            ("External limits                ", "CP?2"),
            ("Position limit high            ", "CP?3"),
            ("Position limit low             ", "CP?4"),
            ("Stop range (dead band)         ", "CP?5"),
            ("Encoder direction              ", "CP?6"),
            ("Minimum speed in target mode   ", "CP?7"),
            ("Maximum speed in target mode   ", "CP?8"),
            ("Speed ramp up in target mode   ", "CP?9"),
            ("Speed ramp down in target mode ", "CP?a"),
            ("StepsPerCount                  ", "CP?b"),
            ("Driver board temperature       ", "CP?10"),
            ("Driver board 48 V level        ", "CP?12"),
            ("Position                       ", "CP?14"),
            ("Wfm point and voltages         ", "CP?1d"),
            ("Target mode parameters         ", "CP?1e"),
        ]

        _txt = ""

        for i in _infos:
            _txt = _txt + "    %s %s\n" % \
                (i[0], self.send(axis, i[1]))

        return _txt
