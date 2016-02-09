import time

from bliss.controllers.motor import Controller
from bliss.common import log as elog
from bliss.controllers.motor import add_axis_method
from bliss.common.axis import AxisState

import pi_gcs
from bliss.comm import tcp

"""
Bliss controller for ethernet PI E712 piezo controller.
Copied from the preliminary E517 controller.
Programmed keeping in mind, that we might have a PI controller class, which could
be inherited to the E517, E712 etc.

Holger Witsch ESRF BLISS
Oct 2014

config example:
<config>
  <controller class="PI_E712">
    <host value="blabla" />
    <port value="50000" />
    <!-- unnecessary, as the port is always 50000-->
    <axis name="e712">
      <channel value="1" />
      <velocity value="1" />
    </axis>
  </controller>
</config>

"""


class PI_E712(Controller):

    def __init__(self, name, config, axes, encoders):
        Controller.__init__(self, name, config, axes, encoders)

        self.sock = None
        self.host = self.config.get("host")
        self.cname = "E712"

    def initialize(self):
        """
        Controller intialization : opens a single socket for all 3 axes.
        """
        self.sock = tcp.Socket(self.host, 50000)

    def finalize(self):
        """
        Closes the controller socket.
        """
        if self.sock:
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
        elog.info("initialize_axis() called for axis %r" % axis.name)

        self._hw_status = AxisState("READY")


        """ Documentation uses the word AxisID instead of channel
            Note: any function used as axis method must accept axis as an argument! Otherwise
                  you will see:
                  TypeError: check_power_cut() takes exactly 1 argument (2 given)
        """
        axis.channel = axis.config.get("channel", int)

        add_axis_method(axis, self.check_power_cut, name = "CheckPowerCut", types_info = (None, None))
        add_axis_method(axis, self._get_tns, name = "Get_TNS", types_info = (None, float))
        add_axis_method(axis, self._get_tsp, name = "Get_TSP", types_info = (None, float))
        add_axis_method(axis, self._get_sva, name = "Get_SVA", types_info = (None, float))
        add_axis_method(axis, self._get_vol, name = "Get_VOL", types_info = (None, float))
        add_axis_method(axis, self._get_mov, name = "Get_MOV", types_info = (None, float))
        add_axis_method(axis, self._get_offset, name = "Get_Offset", types_info = (None, float))
        add_axis_method(axis, self._put_offset, name = "Put_Offset", types_info = (float, None))
        add_axis_method(axis, self._get_tad, name = "Get_TAD", types_info = (None, float))
        add_axis_method(axis, self._get_closed_loop_status, name = "Get_Closed_Loop_Status", types_info = (None, bool))
        add_axis_method(axis, self._set_closed_loop, name = "Set_Closed_Loop", types_info = (bool, None))
        #add_axis_method(axis, self._get_on_target_status, name = "Get_On_Target_Status", types_info = (None, bool))
        add_axis_method(axis, self._get_pos, name = "Get_Pos", types_info = (None, float))

        try:
            axis.paranoia_mode = axis.config.get("paranoia_mode")  # check error after each command
        except KeyError :
            axis.paranoia_mode = False

        self._gate_enabled = False

        # Updates cached value of closed loop status.
        axis.closed_loop = self._get_closed_loop_status(axis)
        self.check_power_cut(axis)

        elog.debug("axis = %r" % axis.name)
        #elog.debug("axis.encoder = %r" % axis.encoder)
        #if axis.encoder:
            #elog.debug("axis = %r" % axis)


    def read_position(self, axis):
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
        _pos = self._get_target_pos(axis)
        elog.debug("position setpoint read : %g" % _pos)

        return _pos

#   def read_encoder(self, encoder):
#       axis = self.__encoders[encoder]["axis"]

#       elog.debug("read_encoder measured = %r" % encoder)
#       _ans = self._get_pos(axis)
#       elog.debug("read_encoder measured = %r" % _ans)
#       return _ans

    """ VELOCITY """
    def read_velocity(self, axis):
        """
        """
        _ans = self.send(axis, "VEL? %s" % axis.channel)
        # _ans should look like "A=+0012.0000"
        # removes 'X=' prefix
        _velocity = float(_ans[2:])

        elog.debug("read_velocity : %g " % _velocity)
        return _velocity

    def set_velocity(self, axis, new_velocity):
        self.send_no_ans(axis, "VEL %s %f" %
                         (axis.channel, new_velocity))
        elog.debug("velocity set : %g" % new_velocity)
        return self.read_velocity(axis)

    """ STATE """
    def state(self, axis):
        elog.debug("axis.closed_loop for axis %s is %s" % (axis.name, axis.closed_loop))

        if axis.closed_loop:
            if self._get_on_target_status(axis):
                return AxisState("READY")
            else:
                return AxisState("MOVING")
        else:
            elog.debug("CLOSED-LOOP is False")
            # ok for open loop mode...
            return AxisState("READY")

    """ MOVEMENTS """
    def prepare_move(self, motion):
        elog.debug("pass")
        pass

    def start_one(self, motion):
        """
        - Sends 'MOV' or 'SVA' depending on closed loop mode.

        Args:
            - <motion> : Bliss motion object.

        Returns:
            - None
        """

###
###  hummm a bit dangerous to mix voltage and microns for the same command isnt'it ?
###
        if motion.axis.closed_loop:
            # Command in position.
            self.send_no_ans(motion.axis, "MOV %s %g" %
                             (motion.axis.channel, motion.target_pos))
            elog.debug("Command to piezo MOV %s %g"%
                             (motion.axis.channel, motion.target_pos))

        else:
            # Command in voltage.
            self.send_no_ans(motion.axis, "SVA %s %g" %
                             (motion.axis.channel, motion.target_pos))
            elog.debug("Command to piezo SVA %s %g"%
                             (motion.axis.channel, motion.target_pos))

    def stop(self, axis):
        """
        * HLT -> stop smoothly
        * STP -> stop asap
        * 24    -> stop asap
        """
        elog.debug("Stopping Piezo by opening loop")
        self._set_closed_loop(self, axis, False)
        #self.send_no_ans(axis, "SVO %s" % axis.channel)

    """ RAW COMMANDS """
    def raw_write(self, axis, com):
        self.sock.write("%s\n" % com)

    def raw_write_read(self, axis, com):
        return self.sock.write_read("%s\n" % com)

    def get_identifier(self, axis):
        """
        Returns Identification information (\*IDN? command).
        """
        return self.send(axis, "*IDN?\n")

    """
    E712 specific
    """
    def send(self, axis, cmd):
        """
        - Adds the 'newline' terminator character : "\\\\n"
        - Sends command <cmd> to the PI controller.
        - Channel is defined in <cmd>.
        - <axis> is passed for debugging purposes.
        - checks error and in case raises .... what ?
        - Returns answer from controller.

        Args:
            - <axis> : passed for debugging purposes.
            - <cmd> : GCS command to send to controller (Channel is already mentionned  in <cmd>).

        Returns:
            - 1-line answer received from the controller (without "\\\\n" terminator).

        Raises:
            -
        """
        _cmd = cmd + "\n"
        #elog.debug("Send %s" % (cmd))
        _t0 = time.time()

        # PC
        _ans = "toto"
        _ans = self.sock.write_readline(_cmd)
        #elog.debug("Answer %s" % (_ans))
        _duration = time.time() - _t0
        if _duration > 0.05:
            elog.info("%s Received %s from Send \"%s\" (duration : %g ms) " % (self.cname, repr(_ans), _cmd.rstrip(), _duration * 1000))

        # ZARBI :  _ans = self.sock.write_readline(_cmd)

        if axis is not None and axis.paranoia_mode:
            self.get_error()  # should raise exc.

        return _ans

    def send_no_ans(self, axis, cmd):
        """
        - Adds the 'newline' terminator character : "\\\\n"
        - Sends command <cmd> to the PI controller.
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
        if axis is not None and axis.paranoia_mode:
            self.get_error()  # should raise exc.


    def _get_pos(self, axis):
        """
        Args:
            - <axis> :
        Returns:
            - <position> Returns real position (POS? command) 

        Raises:
            ?
        """
        _ans = self.send(axis, "POS? %s" % axis.channel)
        _pos = float(_ans[2:])

        return _pos

    def _get_target_pos(self, axis):
        """
        Returns last valid position setpoint ('MOV?' command).
        """
        axis.closed_loop = self._get_closed_loop_status(axis)
        if axis.closed_loop:
            _ans = self.send(axis, "MOV? %s" % axis.channel)
        else:
            _ans = self.send(axis, "SVA? %s" % axis.channel)

        _pos = float(_ans[2:])
        return _pos

    def _get_target_voltage(self, axis):
        """
        Returns last valid voltage setpoint ('SVA?' command).
        """
        _ans = self.send(axis, "SVA? %s" % axis.channel)
        _pos = float(_ans[2:])
        return _pos

    def _get_voltage(self, axis):
        """
        Returns Read Voltage Of Output Signal Channel (VOL? command)
        """
        _ans = self.send(axis, "VOL? %s" % axis.channel)
        _vol = float(_ans.split("=")[-1])
        return _vol

    def _set_closed_loop(self, axis, onoff = True):
        """
        Sets Closed loop status (Servo state) (SVO command)
        """

        axis.closed_loop = onoff
        self.send_no_ans(axis, "SVO %s %d" % (axis.channel, onoff))
        elog.debug("Piezo Servo %r" % onoff)


        # Only when closing loop: waits to be ON-Target.
        if onoff:
            _t0 = time.time()
            cl_timeout = .5

            _ont_state = self._get_on_target_status(axis)
            elog.info(u'axis {0:s} waiting to be ONTARGET'.format(axis.name))
            while((not _ont_state)  and  (time.time() - _t0) < cl_timeout):
                time.sleep(0.01)
                print ".",
                _ont_state = self._get_on_target_status(axis)
            if not _ont_state:
                elog.error('axis {0:s} NOT on-target'.format(axis.name))
                raise RuntimeError("Unable to close the loop : not ON-TARGET after %gs :( " % cl_timeout)
            else:
                elog.info('axis {0:s} ONT ok after {1:g} s'.format(axis.name, time.time() - _t0))

        # Updates bliss setting (internal cached) position.
        axis._position()  # "POS?"


    def _get_closed_loop_status(self, axis):
        """
        Returns Closed loop status (Servo state) (SVO? command)
        -> True/False
        """
        _ans = self.send(axis, "SVO? %s" % axis.channel)
        _status = int(_ans[2:])

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
        _ans = self.send(axis, "ONT? %s" % axis.channel)
        _status = float(_ans[2:])

        if _status == 1:
            return True
        else:
            return False

    def gate_on(self, axis, state):
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
            _cmd = "CTO %d 3 3 1 5 0 1 6 100 1 7 1" % (axis.channel)
        else:
            _cmd = "CTO %d 3 3 1 5 0 1 6 100 1 7 0" % (axis.channel)

        self.send_no_ans(axis, _cmd)

    def get_error(self):
        _t0 = time.time()
        _error_number = self.sock.write_readline("ERR?\n")
        _duration = time.time() - _t0
        #if _duration > 0.005:
            #print "%s Received %s from Send %s (duration : %g ms) " % \
                    #(self.cname, repr(_error_number), "ERR?", _duration * 1000)

        _error_str = pi_gcs.get_error_str(_error_number)

        return (_error_number, _error_str)

    def get_info(self, axis):
        """
        Returns a set of useful information about controller.
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
            ("Real Position              ", "POS? %s" % axis.channel),
            ("Position low limit         ", "NLM? %s" % axis.channel),
            ("Position high limit        ", "PLM? %s" % axis.channel),
            ("Closed loop status         ", "SVO? %s" % axis.channel),
            ("Voltage output high limit  ", "VMA? %s" % axis.channel),
            ("Voltage output low limit   ", "VMI? %s" % axis.channel),
            ("Output Voltage             ", "VOL? %s" % axis.channel),
            ("Setpoint Position          ", "MOV? %s" % axis.channel),
            ("Drift compensation Offset  ", "DCO? %s" % axis.channel),
            ("Online                     ", "ONL? %s" % axis.channel),
            ("On target                  ", "ONT? %s" % axis.channel),
            ("On target window           ", "SPA? %s 0x07000900" % axis.channel),
            ("On target settling time    ", "SPA? %s 0x07000901" % axis.channel),
            ("ADC Value of input signal  ", "TAD? %s" % axis.channel),
            ("Input Signal Position value", "TSP? %s" % axis.channel),
            ("Velocity control mode      ", "VCO? %s" % axis.channel),
            ("Velocity                   ", "VEL? %s" % axis.channel),
            ("sensor Offset              ", "SPA? %s 0x02000200" % axis.channel),
            ("sensor Gain                ", "SPA? %s 0x02000300" % axis.channel),
            ("sensor gain 2nd order      ", "SPA? %s 0x02000400" % axis.channel),
            ("sensor gain 3rd order      ", "SPA? %s 0x02000500" % axis.channel),
            ("sensor gain 4th order      ", "SPA? %s 0x02000600" % axis.channel),

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
            ("\nCommunication parameters",
            "\n".join(self.sock.write_readlines("IFC?\n", 5)))

        """ my e712 didn't answer anything here
#         _txt = _txt + "    %s  \n%s\n" % \
#             ("\nFirmware version",
#                 "\n".join(self.sock.write_readlines("VER?\n", 1)))
        """
        return _txt

    def check_power_cut(self, axis):
        """
        checks if command level is on 1, if 0 means power has been cut
        in that case, set command level to 1
        """
        _ans = self.send(None, "CCL?")  # get command level
        elog.debug("command_level was : %d " % int(_ans))
        if _ans is "0":
            self.send_no_ans(None, "CCL 1 advanced")

    def get_sensor_coeffs(self, axis):
        """
        Returns a list with sensor coefficients:
        *Offset
        *Gain constant order
        *Gain 2nd order
        *Gain 3rd order
        *Gain 4th order
        """
        axis.coeffs = list()

        for ii in range(5):
            _ans = self.send(axis, "SPA? %d 0x2000%d00" % (axis.channel, ii+2))
            # _ans looks like : "2 0x2000200=-2.25718141e+005"
            axis.coeffs.append(float(_ans.split("=")[1]))
        return axis.coeffs

    def set_sensor_coeffs(self, axis, coeff, value):
        """
        Needed, when in the table, when senson works the opposite way
        Returns a list with sensor coefficients:
        *Offset
        *Gain constant order
        *Gain 2nd order
        *Gain 3rd order
        *Gain 4th order
        """
        self.send_no_ans(axis, "SPA %s 0x2000%d00 %f" % (axis.channel, coeff+2, value))

    def _get_tns(self, axis):
        """Get Normalized Input Signal Value. Loop 10 times to straighten out noise"""
        accu = 0
        for _ in range(10):
            time.sleep(0.01)
            _ans = self.send(axis, "TNS? %s" % axis.channel)
            #elog.debug("TNS? %d : %r" % (axis.channel, _ans))
            if _ans != '0':
                accu += float(_ans[2:])
                accu /= 2
        elog.debug("TNS? %r" % accu)
        # during tests with the piezojack, problems with a blocked socket
        # towards the controller were encountered. Usually, that was 
        # manifesting with 0 TNS readings. If The accumulated value of
        # TNS is 0, we're pretty sure the connection is broken.
        # Use self.finalize() to close the socket, it should be reopened
        # by the next communication attempt.
        if accu == 0:
            elog.info("%s##########################################################%s" % (bcolors.GREEN+bcolors.BOLD, bcolors.ENDC))
            elog.info("%sPIEZO READ TNS, accu is zero, resetting socket connection!%s" % (bcolors.GREEN+bcolors.BOLD, bcolors.ENDC))
            elog.info("%s##########################################################%s" % (bcolors.GREEN+bcolors.BOLD, bcolors.ENDC))
            self.finalize()
        return accu

    def _get_tsp(self, axis):
        """Get Input Signal Position Value"""
        _ans = self.send(axis, "TSP? %s" % axis.channel)
        elog.debug("TSP? %s" % _ans)
        _ans = float(_ans[2:])
        return _ans

    def _get_sva(self, axis):
        """Get Input Signal Position Value"""
        _ans = self.send(axis, "SVA? %s" % axis.channel)
        elog.debug("SVA? %s" % _ans)
        _ans = float(_ans[2:])
        return _ans

    def _get_vol(self, axis):
        """Get Input Signal Position Value"""
        _ans = self.send(axis, "VOL? %s" % axis.channel)
        elog.debug("VOL? %s" % _ans)
        _ans = float(_ans[2:])
        return _ans

    def _get_mov(self, axis):
        """Get Input Signal Position Value"""
        _ans = self.send(axis, "MOV? %s" % axis.channel)
        elog.debug("MOV? %s" % _ans)
        _ans = float(_ans[2:])
        return _ans

    def _get_offset(self, axis):
        """read the offset SPA? 4 0x2000200 will yield 4 0x2000200=0.yxyxyxy+00"""
        _ans = self.send(axis, "SPA? %s 0x2000200" % axis.channel)
        offs = float(_ans.split("=")[-1])
        return offs

    def _put_offset(self, axis, value):
        """write offset"""
        self.send_no_ans(axis, "SPA %s 0x2000200 %f" % (axis.channel, value))
        axis.coeffs[0] = value

    def _get_tad(self, axis):
        """ TAD? delivers the ADC value"""

        accu = 0
        for _ in range(10):
            time.sleep(0.01)
            _ans = self.send(axis, "TAD? %s" % axis.channel)
            #elog.debug("TAD? %d : %r" % (axis.channel, _ans))
            if _ans != '0':
                accu += float(_ans[2:])
                accu /= 2
        elog.debug("TAD? %r" % accu)
        return accu

class bcolors:
    CSI="\x1B["
    BOLD = CSI + '1m'
    GREY = CSI + '100m'
    RED = CSI + '101m'
    GREEN = CSI + '102m'
    YELLOW = CSI + '103m'
    BLUE = CSI + '104m'
    MAGENTA = CSI + '105m'
    LIGHTBLUE = CSI + '106m'
    WHITE = CSI + '107m'
    ENDC = CSI + '0m'

