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


class PI_E517(Controller):

    def __init__(self, name, config, axes):
        Controller.__init__(self, name, config, axes)

        self.host = self.config.get("host")

    # Init of controller.
    def initialize(self):
        self.sock = tcp.Socket(self.host, 50000)

    def finalize(self):
        self.sock.close()

    # Init of each axis.
    def initialize_axis(self, axis):
        axis.channel = axis.config.get("channel", int)
        axis.chan_letter = axis.config.get("chan_letter")

        add_axis_method(axis, self.get_id)
        add_axis_method(axis, self.get_info)
        add_axis_method(axis, self.steps_per_unit)

        # Enables the closed-loop.
        # self.sock.write("SVO 1 1\n")

        # Switch piezo to ONLINE mode so that axis motion can be
        # caused by move commands.
        self.send_no_ans(axis, "ONL %d 1" % axis.channel)


        # VCO for velocity control mode ?
        # self.send_no_ans(axis, "VCO %d 1" % axis.channel)


        self.closed_loop = self._get_closed_loop_status(axis)

    def read_position(self, axis, measured=False):
        if measured:
            #                if self.closed_loop:
            _pos = self._get_pos(axis)
            #                else:
            #                   _pos = self._get_voltage(axis)
            print "PI_E517 position measured read : ", _pos
        else:
            _pos = self._get_target_pos(axis)
            print "PI_E517 position setpoint read : ", _pos

        return _pos

    def read_velocity(self, axis):
        print "PI-E517 read_velocity()"
        _velocity = self._get_velocity(axis)
        print "PI_E517 velocity read : ", _velocity
        return _velocity

    def set_velocity(self, axis, new_velocity):
        self.send_no_ans(axis, "VEL %s %f" %
                         (axis.chan_letter, new_velocity))
        print "PI_E517 velocity wrotten : ", new_velocity
        return self.read_velocity(axis)

    def state(self, axis):
        # if self._get_closed_loop_status(axis):
        if self.closed_loop:
            # print "CL is active"
            if self._get_on_target_status(axis):
                return READY
            else:
                return MOVING
        else:
            # print "CL is not active"
            return READY
            #raise RuntimeError("closed loop disabled")

    def prepare_move(self, motion):
        pass

    def start_one(self, motion):
        if self.closed_loop:
            # Command in position.
            self.send_no_ans(motion.axis, "MOV %s %g" %
                             (motion.axis.chan_letter, motion.target_pos))
        else:
            # Command in voltage.
            self.send_no_ans(motion.axis, "SVA %s %g" %
                             (motion.axis.chan_letter, motion.target_pos))

    def stop(self, axis):
        # HLT -> stop smoothly
        # STP -> stop asap
        # 24    -> stop asap

        # to check : copy of current position into target position ???

        self.send_no_ans(axis, "HLT %s" % axis.chan_letter)

    """
    E517 specific communication
    """

    def steps_per_unit(self, axis, new_step_per_unit=None):
        if new_step_per_unit is None:
            return float(axis.config.get("step_size"))
        else:
            print "steps_per_unit writing is not (yet?) implemented."

    def send(self, axis, cmd):
        '''
        Sends command <cmd> to the PI E517 controller.
        Channel is defined in  <cmd>.
        <axis> is passed for debugging purposes.
        Adds the terminator character : "\\n".
        Returns the 1-line answer received from the controller.
        '''
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
        '''
        Sends command <cmd> to the PI E517 controller.
        Channel is defined in  <cmd>.
        <axis> is passed for debugging purposes.
        Adds the terminator character : "\\n".
        Returns nothing.
        '''
        _cmd = cmd + "\n"
        self.sock.write(_cmd)

    def _get_velocity(self, axis):
        '''
        Returns velocity taken from controller.
        '''
        _ans = self.send(axis, "VEL? %s" % axis.chan_letter)
        # _ans should looks like "A=+0012.0000"
        # "\n" removed by tcp lib.

        # removes 'X=' prefix
        _velocity = float(_ans[2:])

        return _velocity

    def _get_pos(self, axis):
        '''
        Returns real position (POS? command) read by capacitive sensor.
        '''
        _ans = self.send(axis, "POS? %s" % axis.chan_letter)
        _pos = float(_ans[2:])

        return _pos

    def _get_target_pos(self, axis):
        '''
        Returns last target position (MOV?/SVA? command) (setpoint value).
        '''
        if self.closed_loop:
            _ans = self.send(axis, "MOV? %s" % axis.chan_letter)
        else:
            #PC to avoid updating in loop before target is reached
            #_ans = self.send(axis, "SVA? %s" % axis.chan_letter)
            _ans = self.send(axis, "VOL? %s" % axis.channel)
        _pos = float(_ans[2:])
        return _pos

    def _get_voltage(self, axis):
        '''
        Returns Voltage Of Output Signal Channel (VOL? command)
        '''
        _ans = self.send(axis, "VOL? %s" % axis.channel)
        _vol = float(_ans.split("=+")[-1])
        return _vol

    def _get_closed_loop_status(self, axis):
        '''
        Returns Closed loop status (Servo state) (SVO? command)
        -> True/False
        '''
        _ans = self.send(axis, "SVO? %s" % axis.chan_letter)
        _status = float(_ans[2:])

        if _status == 1:
            return True
        else:
            return False

    def _get_on_target_status(self, axis):
        '''
        Returns On Target status (ONT? command).
        True/False
        '''
        _ans = self.send(axis, "ONT? %s" % axis.chan_letter)
        _status = float(_ans[2:])

        if _status == 1:
            return True
        else:
            return False

    def _activate_threshold_trigger(self, axis, min, max):
        """
        CTO  {<TrigOutID> <CTOPam> <Value>}
          <TrigOutID> : {1, 2, 3}
          <CTOPam> : 3: trigger mode
                     5: min threshold
                     6: max threshold
          <Value> : {0, 2, 3, 4}
               0 : 
               2 : 
               3 : 
               4 : 
        """

        _cmd = "CTO %d " % (axis.channel)

    def get_id(self, axis):
        '''
        Returns Identification information (*IDN? command).
        '''
        return self.send(axis, "*IDN?\n")

    def _get_error(self, axis):
        _error_number = self.send(axis, "ERR?\n")
        _error_str = pi_gcs.get_error_str(_error_number)

        return (_error_number, _error_str)

    def _stop(self):
        '''
        Sends a stop to the controller (STP command).
        '''
        self.sock.write("STP\n")

    '''
    Returns a set of usefull information about controller.
    Can be helpful to tune the device.
    '''
    def get_info(self, axis):
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
