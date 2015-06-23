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

        self.host = self.config.get("host")
        self.cname = "E712"
        self.__encoders = {}


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
        elog.info("initialize_axis() called for axis %r" % axis.name)

        self._hw_status = AxisState("READY")


        """ Documentation uses the word AxisID instead of channel
            Note: any function used as axis method must accept axis as an argument! Otherwise
                  you will see:
                  TypeError: check_power_cut() takes exactly 1 argument (2 given)
        """
        axis.channel = axis.config.get("channel", int)

        add_axis_method(axis, self.get_id, name = "GetId", types_info = (None, str))
        add_axis_method(axis, self.raw_com, name = "RawCom", types_info = (str, str))

        add_axis_method(axis, self.check_power_cut, name = "CheckPowerCut", types_info = (None, None))
        add_axis_method(axis, self._get_tns, name = "Get_TNS", types_info = (None, float))
        add_axis_method(axis, self._get_tsp, name = "Get_TSP", types_info = (None, float))
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

            #self.__encoders.setdefault(axis.encoder, {})["axis"] = axis


    #def initialize_encoder(self, encoder):
        #self.__encoders.setdefault(encoder, {})["measured_noise"] = 0.0
        #self.__encoders[encoder]["steps"] = None

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

    def read_velocity(self, axis):
        """
        Args:
            - <axis> : Bliss axis object.
        Returns:
            - <velocity> : float
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

    def state(self, axis):
        # if self._get_closed_loop_status(axis):
#        elog.debug("axis.closed_loop is %s" % axis.closed_loop)
#        if axis.closed_loop:
#            elog.debug("CLOSED-LOOP on axis %s is True" % axis.name)
#            if self._get_on_target_status(axis):
#                return AxisState("READY")
#            else:
#                return AxisState("MOVING")
#        else:
#            elog.debug("CLOSED-LOOP is False")
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
        * to check : copy of current position into target position ???
        """
        self.send_no_ans(axis, "HLT %s" % axis.channel)

    """
    E712 specific
    """

    def raw_com(self, axis, cmd):
        return self.send(axis, cmd)

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
        _t0 = time.time()

        # PC
        _ans = "toto"
        _ans = self.sock.write_readline(_cmd)
        _duration = time.time() - _t0
        if _duration > 0.05:
            print "%s Received %s from Send \"%s\" (duration : %g ms) " % (self.cname, repr(_ans), _cmd.rstrip(), _duration * 1000)

        _ans = self.sock.write_readline(_cmd)


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
            - <position> Returns real position (POS? command) read by capacitive sensor.

        Raises:
            ?
        """
        _ans = self.send(axis, "POS? %s" % axis.channel)
        _pos = float(_ans[2:])

        return _pos

    def _get_target_pos(self, axis):
        """
        Returns last target position (MOV?/SVA? command) (setpoint value).
            - SVA? : Query the commanded output voltage (voltage setpoint).
            - MOV? : Returns the last valid commanded target position.
        Args:
            - <>
        Returns:
            -
        Raises:
            ?
        """
        _ans = self.send(axis, "MOV? %s" % axis.channel)
        _pos = float(_ans[2:])
        return _pos

    def _get_voltage(self, axis):
        """
        Returns Voltage Of Output Signal Channel (VOL? command)
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

    def get_id(self, axis):
        """
        Returns Identification information (\*IDN? command).
        """
        return self.send(axis, "*IDN?\n")

    def get_error(self):
        _t0 = time.time()
        _error_number = self.sock.write_readline("ERR?\n")
        _duration = time.time() - _t0
        #if _duration > 0.005:
            #print "%s Received %s from Send %s (duration : %g ms) " % \
                    #(self.cname, repr(_error_number), "ERR?", _duration * 1000)

        _error_str = pi_gcs.get_error_str(_error_number)

        return (_error_number, _error_str)

    def _stop(self):
        """
        Sends a stop to the controller (STP command).
        """
        self.sock.write("STP\n")

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
            ("ADC Value of input signal  ", "TAD? %s" % axis.channel),
            ("Input Signal Position value", "TSP? %s" % axis.channel),
            ("Velocity control mode      ", "VCO? %s" % axis.channel),
            ("Velocity                   ", "VEL? %s" % axis.channel),
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

    def _get_tns(self, axis):
        """Get Normalized Input Signal Value. Loop 10 times to straighten out noise"""
        accu = 0
        for _ in range(10):
            _ans = self.send(axis, "TNS? %s" % axis.channel)
            #elog.debug("TNS? %d : %r" % (axis.channel, _ans))
            if _ans != '0':
                accu += float(_ans[2:])
                accu /= 2
        elog.debug("TNS? %r" % accu)
        return accu

    def _get_tsp(self, axis):
        """Get Input Signal Position Value"""
        _ans = self.send(axis, "TSP? %s" % axis.channel)
        elog.debug("TSP? %s" % _ans)
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

    def _get_tad(self, axis):
        """ TAD? delivers the ADC value"""
        _ans = self.send(axis, "TAD? %s" % axis.channel)
        _ans = float(_ans[2:])
        return _ans
