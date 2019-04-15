# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

""" 
    BLISS controller for MICOS motor controller

    Manufacturer manual:
    /segfs/dserver/classes/steppermotor/micos/doc/venus-2_1_9_eng_A4.pdf
    TACO DS:
    /segfs/dserver/classes/steppermotor/micos/src/Micos.c

    Possible contents of YML configuration file (of course there are 
    no comments in real yml file):
    controller:
      class: micos
      package: id10.controllers.motors.micos
      serial:
        url: ser2net://lid102:29000/dev/ttyR0
      name: micos
      description: EH2 micos motor controller
      axes:
				      # Comments/Remarks:
        - name:             ths       # Motor mnemonic
          number:             1       # Axis number. Possible values:[1,99].

	  # STANDARD parameters for a motor:
	  # --------------------------------
          steps_per_unit:     1       # steps/deg
          velocity:          60       # deg/sec
          acceleration:     100       # deg/sec**2 

	  # next one was removed from yml file, since not used
	  #backlash:         50       # deg
	  low_limit:        -10000    # s/w low limit [deg] (used by BLISS
				      # core)
	  high_limit:        10000    # s/w high limit [deg] (used by BLISS
				      # core)

	  # SPECIFIC parameters:
	  # --------------------

	  # related to endswitches: 'cal' (-ve) + 'rm' (+ve)
	  low_endswitch_type:  2      # Set 'cal' endswitch (= low h/w limit)
                                      # function to ignored (i.e. dont care
                                      # if it is closer or opener) so that 
				      # motor can do several turns
	  high_endswitch_type: 2      # Set 'rm' endswitch (= high h/w limit)
                                      # function to ignored (i.e. dont care
                                      # if it is closer or opener) so that 
				      # motor can do several turns
	  hw_low_limit:     -10000    # h/w low limit [deg] (named hardware
				      # limit, to distinguish it from BLISS
				      # core s/w limit and since it can be 
				      # set in Micos controller, though Micos
			 	      # doc names it s/w limit.
				      # What Micos names low h/w limit is
				      # the one defined by 'cal' limit switch.
				      # In initialize_hardware_axis() we do
				      # not call _set_hw_limits(), since low
				      # endswitch ('cal') function is set to
				      # ignored (see low_endswitch_type).
				      # We keep this parameter in config file
				      # in case later function/type of 
				      # endswitch changes and where one can
				      # limit the movement to stop before
				      # 'cal' switch by setting this low 
				      # limit.
	  hw_high_limit:     10000    # h/w high limit [deg] (named hardware
				      # limit, to distinguish it from BLISS 
				      # core s/w limit and since it can be 
				      # set in Micos controller, though Micos
				      # doc names it s/w limit.
				      # What Micos names high h/w limit is
				      # the one defined by 'rm' limit switch
				      # In initialize_hardware_axis() we do
				      # not call _set_hw_limits(), since high
				      # endswitch ('rm') function is set to
				      # ignored (see high_endswitch_type).
				      # We keep this parameter in config file
				      # in case later function/type of 
				      # endswitch changes and where one can
				      # limit the movement to stop before 'rm'
				      # switch by setting this high limit.
	  tofrom_endsw_velocity: 5    # velocity with which approach or go
				      # away from low ('cal') and high ('rm')
				      # switch. We keep this parameter in
				      # low and high endswitch function/type
				      # is changed, when we need this 
				      # velocity to move to / away from limit
				      # switches. Also we use unique/single
				      # value, though the Micos command set
				      # allows to set each of 4 velocities 
				      # (to/from 'cal' and to/from 'rm')
				      # separately so that we could use 4
				      # difference velocities. 

	  # related to seeking a reference position ('home')
          to_reference_velocity: 1    # velocity with which the motor moves
				      # when seeking the reference position
				      # [deg/sec]. Default = 2 deg/sec, but
				      # this is too fast (though ref. position
				      # is found, the ref. status remains at
				      # since when seek for the ref. position
				      # is done with too high speed, the 
				      # motor does not stop exactly at the
				      # reference position, but slightly off
				      # and therefore the ref. status is 0.
                                      # To find reference position in one move
				      # velocity must be low = 1 def/sec, but
                                      # later we changed algorithm in 
				      # _move_to_reference() method, where we
                                      # do several moves and start with the 
                                      # higher speed (= 10 deg/sec).

	  # related to power-up action
          action_at_powerup:  32      # set power-up action to 32 = enable 
				      # closed loop

	  # related to closed loop
	  cloop_on:           True    # closed loop enable/disable. Set it
                                      # to True to be consistent with 
				      # action_at_powerup
          cloop_winsize:      10E-3   # size of the closed-loop window [deg]
          cloop_gstbit5sel:   True    # bit 5 of general status state 
                                      # selection. It is set to 1 if position
                                      # is within closed-loop window for at
                                      # least closed-loop window settling time
          cloop_trigopsel:    0       # output trigger selection. Active 
				      # under the same condition as bit 5 
				      # of general status. Possible values:
				      # 0 (no trigger) or 1 of [1,2,3 or 4] 
				      # (4 Digital Output channels)
          cloop_wintime:      1.2E-3  # closed-loop settling time [sec]
"""


import time
import sys
import traceback
import gevent

from bliss.controllers.motor import Controller
from bliss.comm.util import get_comm
from bliss.common.utils import Null

# from bliss.common import log as elog
# Different debug levels are:
# log.NOTSET = 0, log.DEBUG = 10, log.INFO = 20, log.ERROR=40
import logging

from bliss.common.axis import AxisState
from bliss.common import event

from bliss.common.utils import object_method
from bliss.common.utils import object_attribute_get, object_attribute_set

from bliss.comm.util import SERIAL

# def set_micos_log_level(level):
#    level = level.upper()
#    logging.getLogger('micos').setLevel(level)


# In the motor-controller class 'micos' the functions/methods
# are set in groups according to on-line doc
# (https://bliss.gitlab-pages.esrf.fr/bliss/dev_write_motctrl/index.html)
#
# "private" method names start with underscore


# --------------  Micos motor controller class ------------------
class micos(Controller):

    # Actions that can be executed automatically at power up
    # used with "setnpowerup" command
    POWERUP_ACTIONS_DICT = {
        0: "No power-up function defined",
        1: "Activates Joystick, Handwheel, ...",
        2: "Performs move to endswitch cal (-ve hard lim.)",
        4: "Performs move to endswitch rm (+ve hard lim.)",
        8: "Reserved",
        16: "Reserved",
        32: "Activate closed-loop",
    }

    # General errors (used with "getnerror"/"gne" command)
    # a) fill next dictionnary first with 'unique' key:value pairs
    GENERAL_ERROR_DICT = {
        1001: "Wrong Parameter Type",
        1003: "Value Range of Parameter Exceeded",
        1004: "Movement Range should be Exceeded",
        1009: "Not Enough Space on the Stack",
        1010: "No memory Available",
        1015: "Parameter Outside the Movement Range",
        2000: "Unknown Command",
    }
    # b) add cases where different keys have the same value
    for key in [1, 2, 3, 4]:
        GENERAL_ERROR_DICT[key] = "Internal Error"
    for key in [1002, 1008]:
        GENERAL_ERROR_DICT[key] = "Too Few Parameters For the Command"

    # Machine errors (used with "getmerror"/"gme" command after
    # seeing it indicated in the status reply message)
    MACHINE_ERROR_DICT = {
        0: "No Error",
        2: "Scale Error; Sync Pb with sin/cos Measuring System",
        10: "The Axis has been Disabled",
        12: "Overcurrent Occured",
        20: "Scale Error; Amplitued Too Low",
        21: "Scale Error; Velocity Too High",
    }

    # Status byte (used with "nstatus"/"nst" command)
    STATUS_DICT = {
        1: "Command In Execution (ex. motor moving)",
        2: "Manual Operation Mode (Joystick or Handwheel)",
        4: "Machine Error",
        8: "Reserved",
        "16": "Reserved",
        32: "Position In Closed-Loop-Window",
        64: "Limitation of the moving area",
        128: "Motor disabled or overcurrent",
    }

    # Most imprtant status bits that we are concerned with
    CMD_IN_EXEC = 0x01
    HW_ERROR = 0x04  # pointing to one of MACHINE_ERRORs
    IN_CL_WINDOW = 0x20
    MOT_DISABLED = 0x80

    # ---------  Initialization/finalization methods -------------

    def __init__(self, *args, **kwargs):
        """
        Constructor

        Required in the minimal set of motor-controller
        functions to implement.

        Initialization of internal class attributes.
        """

        Controller.__init__(self, *args, **kwargs)
        # self.log = logging.getLogger('micos')
        self.log = logging.getLogger(type(self).__name__)

        # Set initial value of log level to NOTSET --> no logging message
        # The log level can be later changed at any moment by
        # invoking set_log_level() on axis object.
        self.log.setLevel(logging.NOTSET)
        self.log.info("__init__()")
        self._status = "uninitialized"

    #    def get_mandatory_config_parameters(self, axis):
    #        return ('velocity', 'acceleration', 'cloop_winsize', 'cloop_wintime')

    def initialize(self):
        """
	Called when an object of Micos controller class is created
	(called only once, even if many objects are created).

	Before first usage of one axis of this controller object, 
	hardware initialization is performed in the following order:
	 - initialize_hardware()
	 - initialize_axis()
	 - set_velocity() and set_acceleration()
	 - apply software limits
	 - initialize_hardware_axis()

        Opens serial line.
        """

        self.log.info("initialize()")
        try:
            self.serial = get_comm(
                self.config.config_dict, SERIAL, timeout=5, baudrate=19200, eol="\r\n"
            )
            self._status = "SERIAL communication configuration found"
            self.log.debug("initialize(): %s" % (self._status))
            self.log.debug("initialize(): %s" % (self.serial))
        except ValueError:
            try:
                serial_line = self.config.get("serial")
                warn(
                    "'serial_line' keyword is deprecated. Use 'serial' instead",
                    DeprecationWarning,
                )
                comm_cfg = {"serial": {"url": serial_line}}
                self.serial = get_comm(comm_cfg, timeout=1)
            except:
                self._status = "Cannot find serial configuration"
                self.log.error("initialize(): %s" % (self._status))

        self._micos_state = AxisState()
        self._micos_state.create_state("INCLOSEDLOOPWINDOW", "In Closed-loop Window")
        # self._micos_state.create_state("IN_CLOSED_LOOP_WINDOW","In Closed-loop Window")
        # TODO: see if some other special state should be created here

    def initialize_hardware(self):
        """
        Initializes the MICOS controller 
        Called once for this controller whatever the number of axes.
        Executes actions COMMON for all axes.
        """

        self.log.info("initialize_hardware()")

        # Switch ALL axes (though we use only axis number 1) to HOST MODE
        _cmd = "0 nmode "
        self.log.debug("initialize_hardware() : Switch all axes to host mode")
        self.log.debug("initialize_hardware() : cmd=%r" % _cmd)
        self.serial.write(_cmd.encode())
        self.log.debug("initialize_hardware() : After switching to HOST MODE")

    def initialize_axis(self, axis):
        """
	This function serves for the SOFTWARE INITIALIZION of ONE axis.

	Required/mandatory in the minimal set of motor-controller
	functions to implement. If this function is not implemented,
	the initialization of axis is not done.

        Reads axis config and/or settings.

	Remark: When SPEC used TACO DS, in object_initialize() of DS the last
		stored parameters were obtained from TACO DB and applied
		to the hardware, but then SPEC in setup invoked DevReset, 
		which caused DS to execute 'nreset' command, which restored
		the hardware to the values saved in NVRAM with 'nsave', so 
		SPEC by doing this overwrote what DS saved in the TACO DB. 
		---> not very logical; moreover, TACO DS whenever setting
		one parameter, it stored its value in TACO DB. In the end
		this way more parameters than are 'Storable' to NVRAM were
		stored in TACO DB.

        Args:
            - <axis> : Bliss axis object.
        """

        self.log.info("initialize_axis()")

        self.axis_settings.add("cloop_winsize", float)
        self.axis_settings.add("cloop_wintime", float)
        # TODO: understand why they do not appear in setting and when
        #      clear, then perhaps add some others ?

        # 'STANDARD' parameters like: steps_per_unit, velocity,
        #  acceleration, backlash, low_limit, high_limit will
        #  be obtained initially from config (= 'STATIC' configuration)
        #  and later from settings (= 'DYNAMIC' configuration).
        # For these parameters we do not need to code access to them
        # since this is done in the parent controller class.

        # 'MICOS-SPECIFIC' parameters will be obtained from
        # configuration ( = 'STATIC' configuration), but can
        # be added to settings like for ex. cloop_winsize or cloop_wintime.

        # Axis number
        try:
            axnum = axis.config.get("number", int)
        except:
            self.log.error(
                "initialize_axis(): No 'number' defined in config for Micos axis %s"
                % axis.name
            )
        if axnum < 1 or axnum > 99:
            msg = "Axis number %d is not within [1,99]" % axnum
            raise ValueError(msg)
        axis.number = axnum
        self.log.debug("initialize_axis(): axis number = %d" % axis.number)

        # Both endswitch functions/type from config
        # The following functions are possible for 2 endswitches:
        # if NPN switch: 0=closer,1=opener,2=ignored
        # if PNP switch: 1=closer,0=opener,2=ignored
        try:
            loesty = axis.config.get("low_endswitch_type", int)
        except:
            self.log.error(
                "initialize_axis(): No 'low_endswitch_type' defined in config for Micos axis %s"
                % axis.name
            )
        if loesty not in (0, 1, 2):
            raise ValueError("low endswitch type %r not one of [0,1,2]" % loesty)
        axis.low_endswitch_type = loesty
        self.log.debug(
            "initialize_axis(): low endswitch type = %d" % axis.low_endswitch_type
        )

        try:
            hiesty = axis.config.get("high_endswitch_type", int)
        except:
            self.log.error(
                "initialize_axis(): No 'high_endswitch_type' defined in config for Micos axis %s"
                % axis.name
            )
        if hiesty not in (0, 1, 2):
            raise ValueError("high endswitch type %r not one of [0,1,2]" % hiesty)
        axis.high_endswitch_type = hiesty
        self.log.debug(
            "initialize_axis(): high endswitch type = %d" % axis.high_endswitch_type
        )

        if axis.low_endswitch_type != 2 and axis.high_endswitch_type != 2:

            #### Get software limits to be able to compare with them hardware
            #### limits
            ####(sw_lolim, sw_hilim) = axis.limits
            #### Maybe like this:
            #### sw_lolim = axis.config.get("low_limit",float)
            #### sw_hilim = axis.config.get("high_limit",float)

            # Low hardware limit
            try:
                hw_lolim = axis.config.get("hw_low_limit", float)
            except:
                self.log.error(
                    "initialize_axis(): No 'hw_low_limit' defined in config for Micos axis %s"
                    % axis.name
                )
            ####if hw_lolim > sw_lowim:
            ####    msg = "Low hardware limit %f for Axis number %d is higher than low software limit %f" % (hw_lolim, axis.number, sw_lolim)
            ####    raise ValueError(msg)
            axis.hw_low_limit = hw_lolim
            self.log.debug(
                "initialize_axis(): hw_low_limit = %f deg." % axis.hw_low_limit
            )

            # High hardware limit
            try:
                hw_hilim = axis.config.get("hw_high_limit", float)
            except:
                self.log.error(
                    "initialize_axis(): No 'hw_high_limit' defined in config for Micos axis %s"
                    % axis.name
                )
            ####if hw_hilim < sw_hilim:
            ####    msg = "High hardware limit %f for Axis number %d is lower than high software limit %f" % (hw_hilim, axis.number, sw_hilim)
            ####    raise ValueError(msg)
            axis.hw_high_limit = hw_hilim
            self.log.debug(
                "initialize_axis(): hw_high_limit = %f deg." % axis.hw_high_limit
            )

            # Velocity for going to / away from 'cal' and 'rm' limit switch
            try:
                tofrom_endsw_vel = axis.config.get("tofrom_endsw_velocity", float)
            except:
                self.log.error(
                    "initialize_axis(): No 'tofrom_endsw_velocity' defined in config for Micos axis %s"
                    % axis.name
                )
            axis.tofrom_endsw_velocity = tofrom_endsw_vel
            self.log.debug(
                "initialize_axis(): tofrom_endsw_velocity = %f deg/sec"
                % axis.tofrom_endsw_velocity
            )

        # Velocity with which motor moves to find the reference
        # (= home) position
        try:
            torefvel = axis.config.get("to_reference_velocity", float)
        except:
            self.log.error(
                "initialize_axis(): No 'to_reference_velocity' defined in config for Micos axis %s"
                % axis.name
            )
        # Comment next test, which was usefull in the 1st version of the
        # code inside the function _move_to_reference(), where move to
        # reference position was done in 1 go with small velocity to be
        # sure to stop exactly at the reference position where the reference
        # status is 1. Empirically we found that going faster, ths motor
        # detected the reference position, but stopped at the position
        # slightly off the reference position, where the reference position
        # status was 0.
        # In order to speed up the reference position search, the algorithm
        # inside the function _move_to_reference() was changed such that
        # the 1st move is done with rather high velocity and each next
        # move with the 1/10-th of it till the motor stops at the reference
        # position, where the reference position status = 1.
        # if torefvel > 1:
        #    raise ValueError("Velocity for moving to reference position is toohigh %f (should be <= 1.0 deg/sec)" % torefvel)
        axis.to_reference_velocity = torefvel
        self.log.debug(
            "initialize_axis(): Velocity for moving to reference position is %f deg/sec"
            % axis.to_reference_velocity
        )

        # Action(s) at power up expressed as number
        try:
            aapu = axis.config.get("action_at_powerup", int)
        except:
            self.log.error(
                "initialize_axis(): No 'action_at_powerup' defined in config for Micos axis %s"
                % axis.name
            )
        loa = self.POWERUP_ACTIONS_DICT.keys()  # list of actions numbers
        ####loa.sort()  # In python 3 cannot sort within dict_keys type of object!!!
        loalist = sorted(loa)
        ####if loa.count(aapu) == 0:
        if loalist.count(aapu) == 0:
            msg = "Powerup Action number %d unknown" % aapu
            raise ValueError(msg)
        else:
            axis.action_at_powerup = aapu
            # Assume only 1 action is selected among all possibilities
            # (otherwise should expect bitmask with more than just
            #  one power of 2)
            dbgmsg = (
                "initialize_axis(): Powerup Action selected to be %s"
                % self.POWERUP_ACTIONS_DICT.get(aapu)
            )
            self.log.debug(dbgmsg)

        # Closed loop on/off flag
        try:
            clon = axis.config.get("cloop_on", bool)
        except:
            self.log.error(
                "initialize_axis(): No 'cloop_on' defined in config for Micos axis %s"
                % axis.name
            )
        axis.cloop_on = clon
        self.log.debug("initialize_axis(): closed loop flag = %r" % axis.cloop_on)

        # Closed loop window size
        try:
            clwinsize = axis.config.get("cloop_winsize", float)
        except:
            self.log.error(
                "initialize_axis(): No 'cloop_winsize' defined in config for Micos axis %s"
                % axis.name
            )
        if clwinsize <= 0:
            msg = "Closed loop window size is %f = not positive" % clwinsize
            raise ValueError(msg)

        # setting position tolerance to be equal to clwinsize
        axis.config.set("tolerance", clwinsize / axis.steps_per_unit)
        axis.cloop_winsize = clwinsize
        self.log.debug(
            "initialize_axis(): closed loop window size = %f degrees"
            % axis.cloop_winsize
        )

        # Bit 5 of general status byte selection
        try:
            clgstbit5sel = axis.config.get("cloop_gstbit5sel", bool)
        except:
            self.log.exception(
                "initialize_axis(): Invalid or missing 'cloop_gstbit5sel' in config for Micos axis %s"
                % axis.name
            )
        axis.cloop_gstbit5sel = clgstbit5sel
        self.log.debug(
            "initialize_axis(): closed loop general status bit 5 selection = %r"
            % axis.cloop_gstbit5sel
        )

        # Output trigger selection
        try:
            cltrigopsel = axis.config.get("cloop_trigopsel", int)
        except:
            self.log.error(
                "initialize_axis(): No 'cloop_trigopsel' defined in config for Micos axis %s"
                % axis.name
            )
        if cltrigopsel not in [0, 1, 2, 3, 4]:
            msg = "Trigger output selection %d not one of [0,1,2,3,4] " % cltrigopsel
            raise ValueError(msg)
        axis.cloop_trigopsel = cltrigopsel
        self.log.debug(
            "initialize_axis(): closed loop trigger output selection = %d"
            % axis.cloop_trigopsel
        )

        # Closed loop settling time
        try:
            clwintime = axis.config.get("cloop_wintime", float)
        except:
            self.log.error(
                "initialize_axis(): No 'cloop_wintime' defined in config for Micos axis %s"
                % axis.name
            )
        if clwintime <= 0:
            msg = "Closed loop window settling time is %f = not positive" % clwintime
            raise ValueError(msg)
        axis.cloop_wintime = clwintime
        self.log.debug(
            "initialize_axis(): closed loop settling time = %f" % axis.cloop_wintime
        )
        # clwintime = axis.settings.get("cloop_wintime")
        # if clwintime == None:
        #    axis.axis_settings.add("cloop_wintime",float)

    def initialize_hardware_axis(self, axis):
        """
	This function serves for the HARDWARE INITIALIZION of an axis.
	It uses the values of various axis-related parameters as obtained
	in initialize_axis().
	In various set-like functions always check for a general error.

	Remark: In the beginning of this function could do reset to the
	        the last values that were stored in NVRAM, but do not know
		how many times NVRAM can be overwritten, so unlike SPEC
		(where DevReset of TACO DS was called in setup), will not
		do reset here.

        Args:
            - <axis> : Bliss axis object.
        """

        self.log.info("initialize_hardware_axis()")

        ret = self._get_generror(axis)

        # Clear all programmed functions on the axis (= clear
        # the command stack)
        self._clear_axis(axis)

        # Activate axis (otherwise makes no sense to work with it)
        self.set_on(axis)

        # Remark: concerning velocity and acceleration we do not need
        #         to explicitely call here set_velocity() and
        #         set_acceleration(), since this is done 'automatically'
        #         by the parent (Controller).

        # Remark: There is no hardware function on Micos controller
        #         to set backlash.

        # Set types for both endswitches (cal = low, rm = high)
        self._set_endswitch_types(axis)

        if axis.low_endswitch_type != 2 and axis.high_endswitch_type != 2:
            # Set hardware limits as found in config
            self._set_hw_limits(axis)

            self._set_tofrom_endsw_velocity(axis)

        # Set velocity for moving to reference position (can be considered
        # as home position)
        self._set_to_reference_velocity(axis)

        # Choose power-up action (pass numeric value)
        self._set_action_at_powerup(axis, axis.action_at_powerup)

        # Enable/Disable closed loop
        if axis.cloop_on:
            self._set_cloop_on(axis)
        else:
            self._set_cloop_off(axis)

        # Check if closed loop is ON is done inside _set_cloop_window()
        self._set_cloop_window(axis)

        # Check if closed loop is ON is done inside _set_cloop_wintime()
        self._set_cloop_wintime(axis)

    # TODO: set other things in h/w if necessary

    def set_on(self, axis):
        """
        This function enables/activates axis.

	Remark: If for one reason or another bit 7 in status byte 
	        returned by 'nstatus' command is 1 --> state OFF
		then this command does not help to remove the OFF
		state. Only reset_axis() helps, but then need to do 
		the homing again since reset_axis() moves the motor
		to another place (empirically it was found that the
		distance between the position obtained after reset_axis()
		and the reference(= home) position is 19.23526 degrees.
	
        Args:
            - <axis> : Bliss axis object.
        """

        self.log.info("set_on()")

        _cmd = "1 %d setaxis " % axis.number
        self._send_no_ans(axis, _cmd)
        # Check for general/system error
        ret = self._get_generror(axis)
        if ret != 0:
            raise RuntimeError(self.GENERAL_ERROR_DICT.get(ret))
        self.log.debug("set_on(): axis %d activated" % axis.number)
        axis.axis_on = True

    def set_off(self, axis):
        """
        This function disables/desactivate axis

        Args:
            - <axis> : Bliss axis object.
        """

        self.log.info("set_off()")

        _cmd = "0 %d setaxis " % axis.number
        self._send_no_ans(axis, _cmd)
        # Check for general/system error
        ret = self._get_generror(axis)
        if ret != 0:
            raise RuntimeError(self.GENERAL_ERROR_DICT.get(ret))
        self.log.debug("set_off(): axis %d desactivated" % axis.number)
        axis.axis_on = False

    def finalize(self):
        """
        Closes the serial object.
        """
        self.log.info("finalize()")
        self.serial.close()

    def finalize_axis(self, axis):
        """
        Save storable parameters to NVRAM

	Remark: for the moment comment the line with command

        Args:
            - <axis> : Bliss axis object.
        """
        self.log.info("finalize_axis()")
        # self._save_axis_parameters(axis)

    # ----------------  Velocity/Acceleration methods ------------------

    def read_velocity(self, axis):
        """
        Args:
            - <axis> : Bliss axis object.
        Returns:
            - <velocity> : float : axis velocity
        """

        self.log.info("read_velocity()")

        # _cmd = "%d gnv " % axis.number
        _cmd = "%d getnvel " % axis.number
        _ans = self._send(axis, _cmd)
        self.log.debug("read_velocity(): %s" % _ans)
        _vel = float(_ans)
        self.log.debug("read_velocity(): velocity = %f" % _vel)
        return _vel

    def set_velocity(self, axis, new_velocity):
        """
        Args:
            - <axis> : Bliss axis object.
            - <new_velocity> : new velocity to be set for the axis
        """

        self.log.info("set_velocity()")

        # _cmd = "%f %d snv " % (new_velocity, axis.number)
        _cmd = "%f %d setnvel " % (new_velocity, axis.number)
        self._send_no_ans(axis, _cmd)
        # ret = self._get_generror(axis)
        # if ret != 0:
        #    raise RuntimeError(self.GENERAL_ERROR_DICT.get(ret))
        self.log.debug("velocity set to : %g mm/s" % new_velocity)

    def read_acceleration(self, axis):
        """
        Args:
            - <axis> : Bliss axis object.
        Returns:
            - <acceleration> : float : axis acceleration
        """

        self.log.info("read_acceleration()")

        # _cmd = "%d gna " % axis.number
        _cmd = "%d getnaccel " % axis.number
        _ans = self._send(axis, _cmd)
        self.log.debug("read_acceleration(): %s" % _ans)
        _acc = float(_ans)
        self.log.debug("read_acceleration(): acceleration = %f" % _acc)
        return _acc

    def set_acceleration(self, axis, new_acceleration):
        """
        Args:
            - <axis> : Bliss axis object.
            - <new_acceleration> : new acceleration to be set for the axis
        """

        self.log.info("set_acceleration()")

        # _cmd = "%f %d sna " % (new_acceleration, axis.number)
        _cmd = "%f %d setnaccel " % (new_acceleration, axis.number)
        self._send_no_ans(axis, _cmd)
        # ret = self._get_generror(axis)
        # if ret != 0:
        #    raise RuntimeError(self.GENERAL_ERROR_DICT.get(ret))
        self.log.debug("acceleration set to : %g mm/s2" % new_acceleration)

    # ----------------  Status and Position methods ------------------

    def state(self, axis):
        """
        Returns state

        Required/mandatory in the minimal set of motor-controller
        functions to implement.

        Args:
            - <axis> : Bliss axis object.
        Returns:
            - <state> : string : current operation state of axis
        """

        self.log.info("state()")

        _ans = self._get_status(axis)
        # print(_ans)

        # status byte as integer
        status = int(_ans)
        self.log.debug("state(): status byte = 0x%x" % status)

        state = self._micos_state.new()
        # print("State = %r" % state)

        if status & self.HW_ERROR:
            state.set("FAULT")
            # TODO: analyze machine error here
            merrlist = self._get_macherror(axis)
            self.log.debug("state(): Machine error(s): %r" % merrlist)

        if status & self.CMD_IN_EXEC:
            state.set("MOVING")

        if status & self.IN_CL_WINDOW:
            state.set("INCLOSEDLOOPWINDOW")
            # state.set("IN_CLOSED_LOOP_WINDOW")
            if not (status & self.CMD_IN_EXEC):
                state.set("READY")
        else:
            state.set("MOVING")

        if status & self.MOT_DISABLED:
            state.set("OFF")

        # TODO: could make this block only if both endswitch function/type
        #       is not set to 2 (= not ignored)
        (loess, hiess) = self._get_endswitch_status(axis)
        if int(loess) == 1:
            state.set("LIMNEG")
        if int(hiess) == 1:
            state.set("LIMPOS")

        refst = self._get_reference_status(axis)
        if refst == 1:
            state.set("HOME")

        # print("State = %r" % state)
        return state

    def read_position(self, axis):
        """
        Reads axis dial position

        Args:
            - <axis> : bliss axis object.
        Returns:
            - <position> : float : axis dial position
        """

        self.log.info("read_position()")

        # _cmd = "%d np " % axis.number
        _cmd = "%d npos " % axis.number
        _ans = self._send(axis, _cmd)
        self.log.debug("read_position(): %s" % _ans)
        _pos = float(_ans)
        self.log.debug("position=%f" % _pos)
        axis.dial_position = _pos
        return _pos

    def set_position(self, axis, new_position):
        """
        Set new dial position

        Remark: The manual says that the dial position is automatically
	        set to 0, when 'cal' limit switch is reached, but that 
	        that we can use this command to set the 'origin' wherever
	        we want.

        Args:
            - <axis> : bliss axis object.
            - <new_position>: new dial position
        """

        self.log.info("set_position()")

        # use "setnpos" command

        if new_position != None:
            _cmd = "%f %d setnpos " % (new_position, axis.number)
            self._send_no_ans(axis, _cmd)
            # Check for general/system error
            ret = self._get_generror(axis)
            if ret != 0:
                raise RuntimeError(self.GENERAL_ERROR_DICT.get(ret))
            axis.dial_position = new_position
        else:
            _cmd = "%f %d setnpos " % (axis.dial_position, axis.number)
            self._send_no_ans(axis, _cmd)
            # Check for general/system error
            ret = self._get_generror(axis)
            if ret != 0:
                raise RuntimeError(self.GENERAL_ERROR_DICT.get(ret))
        # return new_position
        return self.read_position(axis)

    # ----------------  Single axis motion ------------------

    def prepare_move(self, motion):
        """
        Prepare a movement.
        Can be used to arm a movement.
        Called just before start_one()

        Args:
            - <motion> : Bliss motion object.
        """

        self.log.info("prepare_move()")

        return
        # raise NotImplementedError

    def start_one(self, motion):
        """
        Make an ABSOLUTE move.
        Called in a command like mymot.move(target_pos)

        Required/mandatory in the minimal set of motor-controller
        functions to implement.

        Args:
            - <motion> : Bliss motion object.
        """

        self.log.info("start_one()")

        # _cmd = "%f %d nm " % (motion.target_pos, motion.axis.number)
        _cmd = "%f %d nmove " % (motion.target_pos, motion.axis.number)
        self._send_no_ans(motion.axis, _cmd)

    def stop(self, axis):
        """
        Halt/abort a movement

        Required/mandatory in the minimal set of motor-controller
        functions to implement.

        Args:
            - <axis> : bliss axis object.

        Remark: Maybe send rather CTRL-C since it does not pass via FIFO
        """

        self.log.info("stop()")

        _cmd = "%d nabort " % axis.number
        self._send_no_ans(axis, _cmd)

    # ----------------  Group motion ------------------

    def start_all(self, *motions):
        """
        Called once per controller with all the axis to move.
        Must start all movements for all axes defined in motions.
        motions is tuple of motion.

        returns immediately (= for group move).
        Positions in motor units
        """

        self.log.info("start_all()")

        raise NotImplementedError

    def stop_all(self, *motion_list):
        """
        Called once per controller with all the axis to move
        returns immediately (= for group move).
        Positions in motor units
        """

        self.log.info("stop_all()")

        raise NotImplementedError

    # ----------------  Calibration-related method ------------------

    def limit_search(self, axis, limit):
        """
	Search hardware low (if limit < 0) or high (if limit >= 0) limit
	When search for low hardware limit, the search is done to reach
	so called cal endswitch.
	When search for high hardware limit, the search is done to reach
	so called rm endswitch.

        Args:
            - <axis> : bliss axis object.
	    - <limit>: if >= 0, search for the positive hw limit
	               if < 0, search for the negative hw limit
	"""

        self.log.info("limit_search()")

        # - one for searching +ve hw limit ( rm endswitch)
        # which will be called in this function

        if limit < 0:
            # searching -ve hw limit (cal endswitch)
            self._cal_limit_switch_move(axis)

        if limit > 0:
            # searching +ve hw limit (rm endswitch)
            self._rm_limit_switch_move(axis)

    # ----------------  Home search related methods ------------------

    def home_search(self, axis, switch):
        """
	Search for a reference position in either +ve direction
	if switch is > 0 or -ve direction is switch is < 0.
	For Micos rotative motor the +ve sense is clockwise rotation
	and -ve sense is anti clock-wise rotation.
	This search is done with adapted velocity (see config
	parameter 'to_reference_velocity', which is much lower
        than the velocity for the standard moves.
	In the BLISS shell this function translates to home() for
	a give axis. For ex. on ID10 the Micos rotational motor
	axis name = ths. We then type ths.home(1) or ths.home(-1)
	to make a home search.

        Args:
            - <axis> : bliss axis object.
	    - <switch>: if >= 0, search in the positive sense (= clockwise)_
	                if < 0, search in the negative sense (= ccw)
	"""

        self.log.info("home_search()")

        # Since in this 'standardized' BLISS motor-controller function
        # we cannot pass an additional parameter, which would be the max
        # possible relative displacement required by Micos controller
        # low-level function 'nrefmove' used for the reference (home)
        # search, we fix it here to +/- 370 degrees.
        # Alternative is to use the custom method move_to_reference(),
        # where we can pass max possible relative displacement as
        # argument.

        if switch >= 0:
            self._move_to_reference(axis, 370)
        else:
            self._move_to_reference(axis, -370)

    def home_state(self, axis):
        """
	See the state of reaching or not the reference position
	Attention!! This is INTERNAL function supposed to be used
	inside the function home_search(). At the level of axis
	in BLISS shell there is no method corresponding to this
	function. 

        Args:
            - <axis> : bliss axis object.
	Returns:
	    - <ref.pos. state>: 1 = if motor is at reference(= home) position
				0 = if motor is not at ref.(= home) position
        """

        self.log.info("home_state()")
        axis_state = AxisState("READY")
        if self._home_failed:
            axis_state.set("FAULT")
        else:
            axis_state.set("HOME")
        return axis_state

    # ----------------  Information methods ------------------

    # Remark: renamed this one to _get_id() since did not work as
    #         known method. Added custom method get_id().

    def _get_id(self, axis):
        """
        To get a kind of ID info, 2 commands are sent:
        - nidentify ... returns the name with some code related to
                        axis configuration (ex. 'Pegasus 1 141 0 0')
        - nversion ...  returns the firmware version of the specified
                        axis (ex. 1.60)

        Args:
            - <axis> : bliss axis object.
	Returns:
	    - <id-related info>: string with Micos ID and Firmware version
        """

        self.log.info("_get_id()")

        _cmd = "%d nidentify " % axis.number
        reply1 = self._send(axis, _cmd)
        self.log.debug("_get_id(): Micos equipment id = %s" % reply1)

        _cmd = "%d nversion " % axis.number
        reply2 = self._send(axis, _cmd)
        self.log.debug("_get_id(): Micos firmware version = %s" % reply2)

        retstr = "Micos ID = %s; Firmware version = %s" % (reply1, reply2)
        return retstr

    def get_info(self, axis):
        """
        Get usefull information about axis.

        Args:
            - <axis> : bliss axis object.
	#Returns:
	#    - <useful info>: some useful axis-related info
        """

        self.log.info("get_info()")

        _txt = ""
        aapup = axis.action_at_powerup
        aapup = self.POWERUP_ACTIONS_DICT.get(aapup)
        astate = self._get_status(axis)
        astate = self.STATUS_DICT.get(int(astate))
        velo = self.read_velocity(axis)
        accel = self.read_acceleration(axis)
        refvelo = self._get_to_reference_velocity(axis)
        refstat = self._get_reference_status(axis)
        ctrlpos = self.read_position(axis)
        dialpos = axis.dial
        offset = axis.offset
        userpos = axis.position
        cloop = self._get_cloop_on(axis)
        hcurr = self._get_hold_current(axis)
        mcurr = self._get_move_current(axis)

        _txt = _txt + "###############################\n"
        _txt = _txt + "Action at Power-Up            : " + aapup + "\n"
        _txt = _txt + "Axis status                   : " + astate + "\n"
        _txt = _txt + "Velocity (deg/sec)            : " + str(velo) + "\n"
        _txt = _txt + "Acceleration (deg/sec**2)     : " + str(accel) + "\n"
        _txt = _txt + "Home Search Velocity (deg/sec): " + str(refvelo) + "\n"
        _txt = _txt + "Home Status                   : " + str(refstat) + "\n"
        _txt = _txt + "Controller Position (deg)     : " + str(ctrlpos) + "\n"
        _txt = _txt + "Dial       Position (deg)     : " + str(dialpos) + "\n"
        _txt = _txt + "Offset (deg)                  : " + str(offset) + "\n"
        _txt = _txt + "User       Position (deg)     : " + str(userpos) + "\n"
        _txt = _txt + "Closed Loop                   : " + str(cloop) + "\n"
        _txt = _txt + "Hold Current                  : " + str(hcurr) + "\n"
        _txt = _txt + "Move Current                  : " + str(mcurr) + "\n"
        _txt = _txt + "###############################\n"

        # TODO: add more info if necessary

        print(_txt)

        ##return _txt

    # ----------------  Direct communication methods ------------------

    def raw_write(self, axis, cmd):
        """ 
	Raw write command (useful mostly for the commands that are not
	used in the 'std' methods or not implemented as 'custom' methods).

        Args:
            - <axis> : bliss axis object.
	    - <cmd>  : command string 
        """
        self.log.info("raw_write()")
        self.log.debug("raw_write(): String to write: %s" % cmd)
        self.serial.write(cmd.encode())

    def raw_write_read(self, axis, cmd):
        """
	Raw write_read command (useful mostly for the commands that are not
	used in the 'std' methods or not implemented as 'custom' methods).

        Args:
            - <axis> : bliss axis object.
	    - <cmd>  : command string 
	Returns:
	    - <reply>: reply for the command
        """
        self.log.info("raw_write_read()")
        self.log.debug("raw_write_read(): String to write: %s" % cmd)
        self.serial.write(cmd.encode())
        time.sleep(.2)
        _ans = self.serial.readline().rstrip()
        self.log.debug("raw_write_read(): Answer received: %s" % _ans)
        _ans = _ans.decode()
        return _ans

    # -------------------------------------------------------------
    # --- custom methods ---
    # -------------------------------------------------------------

    # nvram related methods

    @object_method
    def save_axis_parameters(self, axis):
        """
	Save storable axis parameters in NVRAM

        Args:
            - <axis> : bliss axis object.
        """
        self.log.info("save_axis_parameters()")
        self._save_axis_parameters(axis)

    @object_method
    def restore_axis_parameters(self, axis):
        """
	Restore storable axis parameters from NVRAM

        Args:
            - <axis> : bliss axis object.
        """
        self.log.info("restore_axis_parameters()")
        self._restore_axis_parameters(axis)

    @object_method
    def reset_axis(self, axis):
        """
	Makes a software reset of the axis.

        Args:
            - <axis> : bliss axis object.
        """
        self.log.info("reset_axis()")
        self._reset_axis(axis)

    # command stack related method

    @object_method
    def clear_axis(self, axis):
        """
	Clears axis' command stack.

        Args:
            - <axis> : bliss axis object.
        """
        self.log.info("clear_axis()")
        self._clear_axis(axis)

    # axis state related methods

    @object_method
    def set_axis_on(self, axis):
        """
	Enables axis

        Args:
            - <axis> : bliss axis object.
        """
        self.log.info("set_axis_on()")
        self.set_on(axis)

    @object_method
    def set_axis_off(self, axis):
        """
	Disables axis

        Args:
            - <axis> : Bliss axis object.
        """
        self.log.info("set_axis_off()")
        self.set_off(axis)

    # closed loop related

    @object_method
    def set_cloop_on(self, axis):
        """
	Enables closed loop

        Args:
            - <axis> : Bliss axis object.
        """
        self.log.info("set_cloop_on()")
        self._set_cloop_on(axis)

    @object_method
    def set_cloop_off(self, axis):
        """
	Disables closed loop

        Args:
            - <axis> : Bliss axis object.
        """
        self.log.info("set_cloop_off()")
        self._set_cloop_off(axis)

    # relative move related

    @object_method(types_info=("float", "None"))
    def rel_move(self, axis, displacement):
        """
	Make a relative move

        Args:
            - <axis> : Bliss axis object.
            - <displacement> : Relative displacement with the respect to
			       the current position.
        """
        self.log.info("rel_move()")
        self._rel_move(axis, displacement)

    # information method related

    @object_method(types_info=("None", "str"))
    def get_id(self, axis):
        """
	Get a kind of ID-info

	Returns:
	    - <id-info>: string with Micos ID and Firmware version 
        """
        self.log.info("get_id()")
        self._get_id(axis)

    # 'hardware' limits (= end-switches) related

    @object_method
    def calibrate(self, axis):
        """
	Make a move to the negative limit switch ('cal' switch)

        Args:
            - <axis> : Bliss axis object.
        """
        self.log.info("calibrate()")
        self._cal_limit_switch_move(axis)

    @object_method
    def rangemeasure(self, axis):
        """
	Make a move to the positive limit switch ('rm' switch)

        Args:
            - <axis> : Bliss axis object.
        """
        self.log.info("rangemeasure()")
        self._rm_limit_switch_move(axis)

    # closed loop related

    @object_method(types_info=("None", "str"))
    def get_cloop_params(self, axis):
        """
	Get closed loop parameters (P, I, D, ...)

        Args:
            - <axis> : Bliss axis object.
	Returns:
	    - <cloop-params>: String in the form 'P I D' and even some more
			      values, which are not ducumented.
        """
        self.log.info("get_cloop_params()")
        self._get_cloop_params(axis)

    @object_method(types_info=("str", "None"))
    def set_cloop_params(self, axis, cloop_params):
        """
	Set closed loop parameters (P, I, D)

        Args:
            - <axis> : Bliss axis object.
	    - <cloop_params>: string in form 'P I D'
	"""
        self.log.info("set_cloop_params()")
        self._set_cloop_params(axis, cloop_params)

    # move to reference position related

    @object_method(types_info=("float", "None"))
    def move_to_reference(self, axis, max_displacement):
        """
	Move to the reference (= home) position with the velocity
	'to_reference_velocity' as set in the intialize_hardware_axis()
	with the call self._set_to_reference_velocity(axis).

        Args:
            - <axis> : Bliss axis object.
	    - <max_displacament>: maximum displacement (+/-) with respect
		to the current position within which we expect to find the
		reference (= home) position. To be most sure to find it,
		it is convenient to pass +/- 370 degrees as max_displacement
		in the invocation of this method (like in home_search 
		function/method).
	"""
        self.log.info("move_to_reference()")

        # make a move to search for the reference position

        self._move_to_reference(axis, max_displacement)

    ## TODO: add here more custom methods if needed

    # -------------------------------------------------------------
    # --- custom attributes ---
    # -------------------------------------------------------------

    # REMARK: Code for several custom attributes was commented because
    #         BlissAxisManager accepts only simple argument types.

    # axis state related

    @object_attribute_get(type_info="bool")
    def get_axis_on(self, axis):
        """
        Args:
            - <axis> : Bliss axis object.
	Return:
	    - <axis_on>: axis ON(= True)/OFF(= False) state
	"""
        self.log.info("get_axis_on()")
        ret = self._get_axis_on(axis)
        return ret

    # 'hardware' limits (= end-switches) related

    #    @object_attribute_get(type_info=("float", "float"))
    #    def get_hw_limits(self, axis):
    #        self.log.info("get_hw_limits()")
    #        ret = self._get_hw_limits(axis)
    #        return ret

    #    @object_attribute_set(type_info=("float","float"))
    #    def set_hw_limits(self, axis, hw_lolim,hw_hilim):
    #        self.log.info("set_hw_limits()")
    #        self._set_hw_limits(axis, hw_lolim, hw_hilim)

    #    @object_attribute_get(type_info=("int", "int"))
    #    def get_endswitch_types(self, axis):
    #        self.log.info("get_endswitch_types()")
    #        ret = self._get_endswitch_types(axis)
    #        return ret

    #    @object_attribute_set(type_info=("int","int"))
    #    def set_endswitch_types(self, axis, loesty,hiesty):
    #        self.log.info("set_endswitch_types()")
    #        self._set_endswitch_types(axis, loesty, hiesty)

    # power-up action related

    @object_attribute_get(type_info="int")
    def get_action_at_powerup(self, axis):
        """
        Args:
            - <axis> : Bliss axis object.
	Returns:
	    - <action_at_powerup>: numeric value of powerup action
	"""
        self.log.info("get_action_at_powerup()")
        ret = self._get_action_at_powerup(axis)
        return ret

    @object_attribute_set(type_info="int")
    def set_action_at_powerup(self, axis, powerup_action):
        """
        Args:
            - <axis> : Bliss axis object.
	    - <action_at_powerup>: numeric value of powerup action
	"""
        self.log.info("set_action_at_powerup()")
        self.log.debug("Powerup action = %d\n", powerup_action)
        self._set_action_at_powerup(axis, powerup_action)

    # closed loop related

    @object_attribute_get(type_info="bool")
    def get_cloop_on(self, axis):
        """
        Args:
            - <axis> : Bliss axis object.
	Returns:
	    - <cloop_on>: closed loop enabled(True)/disabled(False) state
	"""
        self.log.info("get_cloop_on()")
        ret = self._get_cloop_on(axis)
        return ret

    #    @object_attribute_get(type_info=("float", "bool", "int"))
    #    def get_cloop_window(self, axis):
    #        self.log.info("get_cloop_window()")
    #        (winsize,gstbit5sel,trigopsel) = self._get_cloop_window(axis)
    #        return (winsize,gstbit5sel,trigopsel)

    #    @object_attribute_set(type_info=("float", "bool", "int"))
    #    def set_cloop_window(self, axis, winsize,gstbit5sel,trigopsel):
    #        self.log.info("set_cloop_window()")
    #        self._set_cloop_window(axis,winsize,gstbit5sel,trigopsel)

    @object_attribute_get(type_info="float")
    def get_cloop_wintime(self, axis):
        """
        Args:
            - <axis> : Bliss axis object.
	Returns:
	    - <cloop_wintime>: closed loop settling time (sec)
	"""
        self.log.info("get_cloop_wintime()")
        ret = self._get_cloop_wintime(axis)
        return ret

    @object_attribute_set(type_info="float")
    def set_cloop_wintime(self, axis, wintime):
        """
        Args:
            - <axis> : Bliss axis object.
	    - <cloop_wintime>: closed loop settling time (sec)
	"""
        self.log.info("set_cloop_wintime()")
        self._set_cloop_wintime(axis, wintime)

    # hold and move current related

    @object_attribute_get(type_info="float")
    def get_hold_current(self, axis):
        """
        Args:
            - <axis> : Bliss axis object.
	Returns:
	    - <hold_current>: holding current = current supplied to the
			      motor when not moving (unit not documented!!)
	"""
        self.log.info("get_hold_current()")
        ret = self._get_hold_current(axis)
        return ret

    @object_attribute_set(type_info="float")
    def set_hold_current(self, axis, hold_current):
        """
        Args:
            - <axis> : Bliss axis object.
	    - <hold_current>: holding current = current supplied to the
			      motor when not moving (unit not documented!!)
	"""
        self.log.info("set_hold_current()")
        self._set_hold_current(axis, hold_current)

    @object_attribute_get(type_info="float")
    def get_move_current(self, axis):
        """
        Args:
            - <axis> : Bliss axis object.
	Returns:
	    - <move_current>: moving current = current supplied to the
			      motor when moving (unit not documented!!)
	"""
        self.log.info("get_move_current()")
        ret = self._get_move_current(axis)
        return ret

    @object_attribute_set(type_info="float")
    def set_move_current(self, axis, move_current):
        """
        Args:
            - <axis> : Bliss axis object.
	    - <move_current>: moving current = current supplied to the
			      motor when moving (unit not documented!!)
	"""
        self.log.info("set_move_current()")
        self._set_move_current(axis, move_current)

    # move to reference position velocity and status related

    @object_attribute_get(type_info="float")
    def get_to_reference_velocity(self, axis):
        """
        Args:
            - <axis> : Bliss axis object.
	Returns:
	    - <to_ref_vel>: velocity used in the search for the reference
			    (= home) position
	"""
        self.log.info("get_to_reference_velocity()")
        ret = self._get_to_reference_velocity(axis)
        return ret

    @object_attribute_set(type_info="float")
    def set_to_reference_velocity(self, axis, ref_vel):
        """
        Args:
            - <axis> : Bliss axis object.
	    - <to_ref_vel>: velocity used in the search for the reference
			    (= home) position
	"""
        self.log.info("set_to_reference_velocity()")
        self._set_to_reference_velocity(axis, ref_vel)

    @object_attribute_get(type_info="int")
    def get_reference_status(self, axis):
        """
        Args:
            - <axis> : Bliss axis object.
	Returns:
	    - <ref_status>: status of the reference(= home) position.
			    1 = when the home position is reached
			    0 = at other than reference (= home) position
	"""
        self.log.info("get_reference_status()")
        ret = self._get_reference_status(axis)
        return ret

    # Log-level related

    @object_attribute_get(type_info="str")
    def get_log_level(self, axis):
        """
        Args:
            - <axis> : Bliss axis object.
	Returns:
	    - <loglevel>: log level. Valid values: NOTSET, DEBUG, INFO, WARN(ING), 
                                                    ERROR, FATAL/CRITICAL
	"""
        self.log.info("get_log_level()")
        ret = self._get_log_level(axis)
        return ret

    @object_attribute_set(type_info="str")
    def set_log_level(self, axis, loglevel):
        """
        Args:
            - <axis> : Bliss axis object.
	    - <loglevel>: log level. Valid values: NOTSET, DEBUG, INFO, WARN(ING), 
                                                   ERROR, FATAL/CRITICAL
	"""
        self.log.info("set_log_level()")
        self._set_log_level(axis, loglevel)

    ## TODO: add here more custom attributes if needed

    # -------------------------------------------------------------
    # --- "private/internal methods ---
    # -------------------------------------------------------------

    # ----------------  Micos communiction methods ------------------

    def _send(self, axis, cmd):
        """
        - Sends command <cmd> to the MICOS controller.
        - Axis number is defined in <cmd>.
        - <axis> is passed for debugging purposes.
        - Returns answer from controller.

        Args:
            - <axis> : passed for debugging purposes.
            - <cmd> : command to send to Micos motor controller
                      (axis number is already part of string <cmd>).
                      Command string does not need termination character
                      like \r, since we set the controller in so-called
                      'host-mode' (the \r terminator is only needed in
                      so-called 'terminal-mode').
        Returns:
            - 1-line answer received from the controller (without "\r\n"
              terminator).
        """

        # Make 1st read to get rid of some crap in output buffer
        ##print("****Make 1st read before sending command %r***" % cmd)
        ##_ans = self.serial.readline().rstrip()
        ##if len(_ans) != 0:
        ##   self.serial.flush()
        ###_ans = " "
        ###while len(_ans) > 0:
        ###    _ans = self.serial.readline().rstrip()
        ###    if len(_ans) != 0:
        ###        self.serial.flush()

        # Send command
        self.log.debug("_send() : cmd=%r" % cmd)
        # self.serial.write(cmd)

        # Read the answer

        # Temporarily add sleep here
        # time.sleep(1)

        # _t0 = time.time()
        # rstrip() removes CR LF at the end of the returned string
        _ans = self.serial.write_readline(cmd.encode()).lstrip()
        _ans = _ans.decode()
        self.log.debug("_send(): ans=%s" % repr(_ans))
        # _duration = time.time() - _t0
        # print("    Sending: %r Receiving: %r  (duration : %g sec.)" % (_cmd, _ans, _duration))
        return _ans

    def _send_no_ans(self, axis, cmd):
        """
        - Sends command <cmd> to the MICOS controller.
        - Axis number is defined in <cmd>.
        - <axis> is passed for debugging purposes.
        - Used for answer-less commands, then returns nothing.
        Args:
            - <axis> : passed for debugging purposes.
            - <cmd> : command to send to controller
                      (axis number is already part of string <cmd>).
                      Command string does not need termination character
                      like \r, since we set the controller in so-called
                      'host-mode' (the \r terminator is only needed in
                      so-called 'terminal-mode').
        """
        self.log.debug("_send_no_ans() : cmd=%r" % cmd)
        self.serial.write(cmd.encode())

    # ----------------  Get errors methods ------------------

    def _get_generror(self, axis):
        """
        Get so-called general/system error. Can be considered more like
        the software error.
        The last occured general/system error of the axis is always 
	indicated.
        The error message is deleted on controller once it is read out with
        'getnerror' command.
        The general/system error occurence IS NOT indicated in the status
        byte (reply to 'nstatus' command).
        It is recommended to query general error after each
        parameters-setting type of command.

        Args:
            - <axis> : Bliss axis object.
	Returns:
	    - <gen_error>: general error as number
			   (see GENERAL_ERROR_DICT)
        """

        self.log.info("_get_generror()")

        _cmd = "%d getnerror " % axis.number
        # _cmd = "%d gne " % axis.number

        _ans = int(self._send(axis, _cmd))

        if _ans == 0:
            dbgmsg = "No general error --> OK"
        else:
            dbgmsg = "General erorr = %s " % self.GENERAL_ERROR_DICT.get(_ans)
        self.log.debug(dbgmsg)
        return _ans

    def _get_macherror(self, axis):
        """
        Get so-called machine error. Can be considered more like hardware
        error.
        The machine errors are stored by the controller in a FIFO memory of
        length 10. When a machine error is read out with the 'getmerror'
        command, this entry in the FIFO is deleted.
        In consequence, there can be in total at most 11 error codes on the
        controller waiting to be read out (1 general/system error and up
        to 10 machine errors).
        The machine error occurence IS indicated in the bit 2 of status byte
        (reply to nstatus command).
        When all machine errors are read out, the bit 2 falls back to 0.

        According to the example in the Micos manual after starting a
        movement of axis, it is recommended to execute the commands in order:
        - query position
        - query general error
        - query status --> if machine error, get machine error

        Args:
            - <axis> : Bliss axis object.
	Returns:
	    - <mach_error>: list of machine errors as numbers
			    (see MACHINE_ERROR_DICT)
        """

        self.log.info("_get_macherror()")

        macherrlist = []

        _cmd = "%d getmerror " % axis.number
        # _cmd = "%d gme " % axis.number
        _ans = int(self._send(axis, _cmd))
        macherrlist.append(_ans)

        # Thist function is called from state() when status
        # byte indicates a machine error. So read first that
        # one and aferwards look if there are potentially 9 others
        # (since in total there can be at max 10 machine errors).

        # Try to read 9 more times (if nstatus shows after each
        # getmerror execution that there are more)
        for i in range(9):
            _ans = self._get_status(axis)
            status = int(_ans)
            self.log.debug("_get_macherror(): status byte = 0x%x" % status)
            if status & self.HW_ERROR:
                _cmd = "%d getmerror " % axis.number
                # _cmd = "%d gme " % axis.number
                _ans = int(self._send(axis, _cmd))
                macherrlist.append(_ans)
                dbgmsg = (
                    "_get_macherror(): Machine erorr = %s "
                    % self.MACHINE_ERROR_DICT.get(_ans)
                )
            else:
                dbgmsg = "_get_macherror(): No (more) machine errors --> OK"
                self.log.debug(dbgmsg)
                break
        macherrlist.reverse()
        return macherrlist
        # return _ans

    # ----------------  Get status method ------------------

    def _get_status(self, axis):
        """
        Get status 

        Args:
            - <axis> : Bliss axis object.
	Returns:
	    - <status-byte> : Raw status-byte as string
	"""

        self.log.info("_get_status()")

        # _cmd = "%d nstatus " % axis.number
        _cmd = "%d nst " % axis.number
        _ans = self._send(axis, _cmd)
        self.log.debug("get_status(): raw_status byte = %s" % _ans)
        return _ans

    # ----------------  Other private methods ------------------

    # ----- saving to / restoring from NVRAM related methods -----

    def _save_axis_parameters(self, axis):
        """
        Save parameters (that are marked 'Storable' in manufacturer
        manual) to the NVRAM.
        Args:
            - <axis> : Bliss axis object.
        """

        self.log.info("_save_axis_parameters()")

        _cmd = "%d nsave " % axis.number
        # TODO: should test general error here ?
        self._send_no_ans(axis, _cmd)

    def _restore_axis_parameters(self, axis):
        """
        Restore parameters (that are marked 'Storable' in manufacturer
        manual) from the NVRAM.
        Args:
            - <axis> : Bliss axis object.
        """

        self.log.info("_restore_axis_parameters()")

        _cmd = "%d nrestore " % axis.number
        # TODO: should test general error here ?
        self._send_no_ans(axis, _cmd)

    def _reset_axis(self, axis):
        """
        Makes a software reset of the axis. The axis is intialized
        and active with the last (in NVRAM) saved parameters.

	Important:
	- After switching on the Micos motor controller and the 
	  compressed air we must execute this function (via reset_axis()).
	  This command not only initializes axis with the last saved 
	  parameters, but also moves axis to some place and set position 
	  to be 0 there.
	- Therefore after reset_axis() call we must proceed to home search.

        Args:
            - <axis> : Bliss axis object.
        """

        self.log.info("_reset_axis()")

        _cmd = "%d nreset " % axis.number
        self._send_no_ans(axis, _cmd)
        # TODO: should test general error here ?
        axis.axis_on = True

    # ----- command stack related method -------

    def _clear_axis(self, axis):
        """
        Clears the contents of parameter stack.
        Normally there are only the parameters for the next
        command on the stack. If wrong number of parameters is passed
        for a given command, then it can happen that more data remains
        on the stack than the next command uses. This can lead to an
        overflow fo the stack and to the fact that the controller executes
        uncontrolled functions!!!

        Args:
            - <axis> : Bliss axis object.
        """

        self.log.info("_clear_axis()")

        _cmd = "%d nclear " % axis.number
        self._send_no_ans(axis, _cmd)
        ret = self._get_generror(axis)
        if ret != 0:
            raise RuntimeError(self.GENERAL_ERROR_DICT.get(ret))

    # ----- axis enabled/disabled status related method -------

    def _get_axis_on(self, axis):
        """
        Get active-enabled/nonactive-disabled state for an axis
        Activation-enabling/desactivation-disabling is managed
        by the 'standard' methods set_on() and set_off().

        Args:
            - <axis> : Bliss axis object.
        Returns:
            - <axis_on> : Boolean : axis ON(= True)/OFF(= False) state
        """

        self.log.info("_get_axis_on()")

        _cmd = "%d getaxis " % axis.number
        ret = self._send(axis, _cmd)
        axis_on = True if int(ret) == 1 else False
        self.log.debug("_get_axis_on(): axis enabled = %s" % axis_on)
        return axis_on

    # ------------ endswitch related methods ----------------

    def _get_endswitch_types(self, axis):
        """
	Get both endswitch types

        Args:
            - <axis> : Bliss axis object.
        Returns:
            - <(low-esty, high-esty)> : Tuple of 2 integers: low and high
				        end-switch types. Since our choice
				        in the config/yml file is 2, we'll
					always get both values 2 = ignore
					end-switches, so we can make several
					turns with the motor.
	"""
        self.log.info("_get_endswitch_types()")
        _cmd = "%d getsw " % axis.number
        ret = self._send(axis, _cmd)
        # lohiesty = ret.split(" ")
        lohiesty = ret.split()
        loesty = int(lohiesty[0])
        hiesty = int(lohiesty[1])
        self.log.debug("_get_endswitch_types(): Low endswitch type = %d" % loesty)
        self.log.debug("_get_endswitch_types(): High endswitch type = %d" % hiesty)
        # axis.low_endswitch_type = loesty
        # axis.high_endswitch_type = hiesty
        return (loesty, hiesty)

    def _set_endswitch_types(self, axis, loest=Null(), hiest=Null()):
        """
	Set both endswitch types

        Args:
            - <axis> : Bliss axis object.
	    - <[loest, hiest]>: low and high endswitch types
		If not passed on input of this function then the 
		values obtained from the configuration file are applied.
	"""
        self.log.info("_set_endswitch_types()")

        # If parameters passed, use them.
        if not isinstance(loest, Null) and not isinstance(hiest, Null):
            _cmd = "%d 0 %d setsw " % (loest, axis.number)
            self._send_no_ans(axis, _cmd)
            ##ret = self._get_generror(axis)
            ##if ret != 0:
            ##    raise RuntimeError(self.GENERAL_ERROR_DICT.get(ret))
            _cmd = "%d 1 %d setsw " % (hiest, axis.number)
            self._send_no_ans(axis, _cmd)
            ##ret = self._get_generror(axis)
            ##if ret != 0:
            ##    raise RuntimeError(self.GENERAL_ERROR_DICT.get(ret))
            axis.low_endswitch_type = loest
            axis.high_endswitch_type = hiest
        else:
            _cmd = "%d 0 %d setsw " % (axis.low_endswitch_type, axis.number)
            self._send_no_ans(axis, _cmd)
            _cmd = "%d 1 %d setsw " % (axis.high_endswitch_type, axis.number)
            self._send_no_ans(axis, _cmd)
            ##ret = self._get_generror(axis)
            ##if ret != 0:
            ##    raise RuntimeError(self.GENERAL_ERROR_DICT.get(ret))

    def _get_endswitch_status(self, axis):
        """
        Get status of both endswitches

        Args:
            - <axis> : Bliss axis object.
        Returns:
            - <(loesst, hiesst)> : Tuple with 2 integers: 
		low and high end-switch status. 
		   0 = end-switch not active, 
		   1 = end-switch active
        """
        self.log.info("_get_endswitch_status()")
        _cmd = "%d getswst " % axis.number
        [loesststr, hiesststr] = self._send(axis, _cmd).split()
        self.log.debug("_get_endswitch_status(): Low endswitch status = %s" % loesststr)
        self.log.debug("_get_endswitch_types(): High endswitch status = %s" % hiesststr)
        loesst = int(loesststr)
        hiesst = int(hiesststr)
        return (loesst, hiesst)

    def _get_hw_limits(self, axis):
        """
        Get 'hardware' limits. 

	In Micos terminology these are still named software limits.
	We will name them 'hardware' limits, since we set them in 
	the Micos controller hardware.

	True hardware limits are really the ones at limit switches
	reached by 'ncal' and 'nrm' commands. 

        Args:
            - <axis> : Bliss axis object.
        Returns:
            - <(hw_lolim, hw_hilim)>: tuple with low and high 
				      'hardware' limits
        """

        self.log.info("_get_hw_limits()")

        _cmd = "%d getnlimit " % axis.number
        # The command returns string with low and high hardware limits
        # separated by space
        ret = self._send(axis, _cmd)
        hw_lohi_lim = ret.split()
        hw_lolim = float(hw_lohi_lim[0])
        hw_hilim = float(hw_lohi_lim[1])
        return (hw_lolim, hw_hilim)

    def _set_hw_limits(self, axis, hw_low_limit=Null(), hw_high_limit=Null()):
        """
        Set 'hardware' limits (mm) on the controller.
	The same comment applies as for function _get_hw_limits() above

	TODO: ideally search for low(cal) and high(rm) endswitch should
	      be done first so that hw limits can be checked then to be
	      within the endswitch limits. [still attention should be paied
	      to the fact that user can redefine the positions, so that 
	      the one at low endswitch is not 0 but - something ...] 

        Args:
            - <axis> : Bliss axis object.
	    - <[hw_low_limit, hw_high_limit]>: low and high 'hardware'
		limits. If not passed on input of this function then the 
		values obtained from the configuration file are applied.
        """

        self.log.info("_set_hw_limits()")

        # If parameters passed, use them.
        if not isinstance(hw_low_limit, Null) and not isinstance(hw_high_limit, Null):
            _cmd = "%f %f %d setnlimit " % (hw_low_limit, hw_high_limit, axis.number)
            self._send_no_ans(axis, _cmd)
            ret = self._get_generror(axis)
            if ret != 0:
                raise RuntimeError(self.GENERAL_ERROR_DICT.get(ret))
            axis.hw_low_limit = hw_low_limit
            axis.hw_high_limit = hw_high_limit
        else:
            hw_lolim = axis.hw_low_limit
            hw_hilim = axis.hw_high_limit
            _cmd = "%f %f %d setnlimit " % (hw_lolim, hw_hilim, axis.number)
            self._send_no_ans(axis, _cmd)
            ret = self._get_generror(axis)
            if ret != 0:
                raise RuntimeError(self.GENERAL_ERROR_DICT.get(ret))

    def _get_tofrom_endsw_velocity(self, axis):
        """
	Get velocity used to go to or away from 'cal' (= -ve end limit
	switch) and 'rm' (= +ve end limit switch)
	It is sufficient to read 2 speeds for one switch and take 
	the first since for simplicity we set all 4 velocities:
	to/from 'cal' switch and to/from 'rm' switch to be the same 

        Args:
            - <axis> : Bliss axis object.
        Returns:
	    - <tofrom_endsw_velocity> : endswitches search velocity
					(deg/sec)
	"""

        self.log.info("_get_tofrom_endsw_velocity()")

        _cmd = "%d getncalvel " % axis.number
        cal_2velocities_str = self._send(axis, _cmd)
        cal_2velocities_list = cal_2velocities_str.split()
        axis.tofrom_endsw_velocity = float(cal_2velocities_list[0])
        self.log.debug(
            "_get_tofrom_endsw_velocity(): velocity for searching endswitch = %s (deg/sec)"
            % axis.tofrom_endsw_velocity
        )
        return axis.tofrom_endsw_velocity

    def _set_tofrom_endsw_velocity(self, axis, tofrom_endsw_velocity=Null()):
        """
	Set velocity used to go to or away from 'cal' (= -ve end limit
	switch) and 'rm' (= +ve end limit switch)
	There are 4 distinguished commands: 
	- one for going to 'cal' limit/end switch 
	- one for going away from 'cal' limit/end switch
	- one for going to 'rm' limit/end switch 
	- one for going away from 'rm' limit/end switch

        Args:
            - <axis> : Bliss axis object.
	    - <tofrom_endsw_velocity> : endswitches search velocity
					(deg/sec)
	"""

        self.log.info("_set_tofrom_endsw_velocity()")

        if not isinstance(tofrom_endsw_velocity, Null):
            tofrom_endsw_velocity = float(tofrom_endsw_velocity)
        else:
            tofrom_endsw_velocity = axis.tofrom_endsw_velocity

        # velocity for move to cal switch
        cmd = "%f 1 %d setncalvel " % (tofrom_endsw_velocity, axis.number)
        self._send_no_ans(axis, _cmd)
        ret = self._get_generror(axis)
        if ret != 0:
            raise RuntimeError(self.GENERAL_ERROR_DICT.get(ret))

        # velocity for move away from cal switch
        cmd = "%f 2 %d setncalvel " % (tofrom_endsw_velocity, axis.number)
        self._send_no_ans(axis, _cmd)
        ret = self._get_generror(axis)
        if ret != 0:
            raise RuntimeError(self.GENERAL_ERROR_DICT.get(ret))

        # velocity for move to rm switch
        cmd = "%f 1 %d setnrmvel " % (tofrom_endsw_velocity, axis.number)
        self._send_no_ans(axis, _cmd)
        ret = self._get_generror(axis)
        if ret != 0:
            raise RuntimeError(self.GENERAL_ERROR_DICT.get(ret))

        # velocity for move away from rm switch
        cmd = "%f 2 %d setnrmvel " % (tofrom_endsw_velocity, axis.number)
        self._send_no_ans(axis, _cmd)
        ret = self._get_generror(axis)
        if ret != 0:
            raise RuntimeError(self.GENERAL_ERROR_DICT.get(ret))

    # Remark:
    #  Note there is no special functions to set acceleration
    #  for going to / away from cal and rm limit switches

    def _cal_limit_switch_move(self, axis):
        """
	Make a movement to cal-limit switch (= -ve limit).
	Motor moves in negative direction till cal limit switch
	is reached/active, then it move slightly away in positive
	direction so that the cal limit switch is not more active
	and position is set to 0.

	This is a blocking command (--> therefore do not call
	_get_generror() since would get timeout in communication
	over serial line).

        Args:
            - <axis> : Bliss axis object.
	"""

        self.log.info("_cal_limit_switch_move()")

        # _cmd = "%d ncal " % axis.number
        _cmd = "%d ncalibrate " % axis.number
        self._send_no_ans(axis, _cmd)

        self.log.debug(
            "_cal_limit_switch_move(): Making movement to cal-limit switch (= -ve limit switch)"
        )

    # TODO: check when the movement is over

    def _rm_limit_switch_move(self, axis):
        """
	Make a movement to rm-limit switch (= +ve limit).
	Motor moves in positive direction till rm limit switch
	is reached/active, then it move slightly away in negative
	direction so that the rm limit switch is no more active.
	Position reached is not stored in the controller
	(while position 0 is stored when cal limit switch is reached)
	
	This is a blocking command (--> therefore do not call
	_get_generror() since would get timeout in communication
	over serial line).

        Args:
            - <axis> : Bliss axis object.
	"""

        self.log.info("_rm_limit_switch_move()")

        # _cmd = "%d nrm " % axis.number
        _cmd = "%d nrangemeasure " % axis.number
        self._send_no_ans(axis, _cmd)

        self.log.debug(
            "_rm_limit_switch_move(): Making movement to rm-limit switch (= +ve limit switch)"
        )

    # TODO: check when the movement is over

    # ------------ power-up action related methods ----------------

    def _get_action_at_powerup(self, axis):
        """
	Get function/action which are automatically
	executed after switching on the controller.

        Args:
            - <axis> : Bliss axis object.
        Returns:
            - <action_at_powerup> : numeric value for action at power up
	"""

        self.log.info("_get_action_at_powerup()")

        _cmd = "%d getnpowerup " % axis.number
        ret = int(self._send(axis, _cmd))
        self.log.debug("_get_action_at_powerup(): powerup action = %d" % ret)
        self.log.debug(
            "_get_action_at_powerup(): powerup action = %s"
            % self.POWERUP_ACTIONS_DICT.get(ret)
        )
        return ret

    def _set_action_at_powerup(self, axis, powerup_action):
        """
	Select function/action which is automatically
	executed after switching on the controller.

	The possible functions/actions are listed in the 
	dictionnary PowerupActionDict, which is defined in the 
	initial part of this file (before this micos motor controller
	class definition).
	
        Args:
	    - <powerup_action> : Numeric value of chosen action.
				 (key in PowerupActionDict)
            - <axis> : Bliss axis object.
	"""

        self.log.info("_set_action_at_powerup()")

        loa = self.POWERUP_ACTIONS_DICT.keys()  # list of actions numbers
        loalist = sorted(loa)
        ####if loa.count(powerup_action) == 0:
        if loalist.count(powerup_action) == 0:
            msg = "Powerup Action number %d unknown" % powerup_action
            raise ValueError(msg)

        _cmd = "%d %d setnpowerup " % (powerup_action, axis.number)
        self._send_no_ans(axis, _cmd)

        ##ret = self._get_generror(axis)
        ##if ret != 0:
        ##    raise RuntimeError(self.GENERAL_ERROR_DICT.get(ret))

        axis.action_at_powerup = powerup_action
        dbgmsg = "Powerup Action set to %s" % self.POWERUP_ACTIONS_DICT.get(
            powerup_action
        )
        if powerup_action & 32 and axis.axis_on == True:
            # enable closed loop before next switching on of the controller
            self._set_cloop_on(axis)
        self.log.debug(dbgmsg)

    # ------------ closed loop related methods ----------------

    def _get_cloop_on(self, axis):
        """
	See if closed loop is enabled or disabled.

        Args:
            - <axis> : Bliss axis object.
        Returns:
            - <cloop_on> : Boolean : True if closed loop enabled
	"""

        self.log.info("_get_cloop_on()")

        _cmd = "%d getcloop " % axis.number
        ret = self._send(axis, _cmd)
        cloop_on = True if int(ret) == 1 else False
        self.log.debug("_get_cloop_on(): closed loop enabled = %s" % cloop_on)
        return cloop_on

    def _set_cloop_on(self, axis):
        """
	Enable/activate closed loop.

        Args:
            - <axis> : Bliss axis object.
	"""

        self.log.info("_set_cloop_on()")

        _cmd = "1 %d setcloop " % axis.number
        self._send_no_ans(axis, _cmd)
        # ret = self._get_generror(axis)
        # if ret != 0:
        #    raise RuntimeError(self.GENERAL_ERROR_DICT.get(ret))
        axis.cloop_on = True

    def _set_cloop_off(self, axis):
        """
	Disable/desactivate closed loop.

        Args:
            - <axis> : Bliss axis object.
	"""

        self.log.info("_set_cloop_off()")

        _cmd = "0 %d setcloop " % axis.number
        self._send_no_ans(axis, _cmd)
        ret = self._get_generror(axis)
        if ret != 0:
            raise RuntimeError(self.GENERAL_ERROR_DICT.get(ret))
        axis.cloop_on = True

    def _get_cloop_window(self, axis):
        """
	Get closed loop window parameters, except settle time.
	When closed loop is enabled, then if general status bit 5 
	is enabled this bit will be set when position is close to
	the target position within closed loop window size for at
	least the closed loop settle time. If general status bit 5
	is disabled, then even if this condition is met, the bit 5
	will not be set in general status.
	Similarly the trigger signal can be selected on one of 4
	digital output channels and the signal will appear it the
	condition is met. If trigger output is disabled, then
	there will be no signal on the selected output even if 
	closed loop condition is met. 

        Args:
            - <axis> : Bliss axis object.
        Returns:
            - <(winsize,gstbit5sel,trigopsel)> : Tuple consisting of:
	      Float: closed loop window size (mm),
	      Boolean: False/True: bit5 in general status disabled/enabled)
	      Int 0 (trigger on output disabled) or 
		  one of 1,2,3,4 (trigger selected on output D1,2,3,4)
	"""

        self.log.info("_get_cloop_window()")

        if axis.cloop_on == False:
            raise RuntimeError(
                "Makes no sense to get closed loop window parameters when closed loop is not enabled"
            )

        _cmd = "%d getclwindow " % axis.number
        ret = self._send(axis, _cmd)
        # The returned string ret has the form:
        #     "winsize 0 gstbit5sel trigopsel"
        # Extract different parts:
        ans = ret.split()
        axis.cloop_winsize = ans[0]
        if ans[2] == 0:
            axis.cloop_gstbit5sel = False
        else:
            axis.cloop_gstbit5sel = True
        axis.cloop_trigopsel = ans[3]

        self.log.debug(
            "_get_cloop_window(): closed loop window size = %f mm" % float(ans[0])
        )
        if axis.cloop_gstbit5sel == True:
            self.log.debug("_get_cloop_window(): general status bit 5 is enabled")
        else:
            self.log.debug("_get_cloop_window(): general status bit 5 is disabled")
        if int(axis.cloop_trigopsel) == 0:
            self.log.debug("_get_cloop_window(): trigger output is disabled")
        else:
            self.log.debug(
                "_get_cloop_window(): trigger is enabled on output %d"
                % int(axis.cloop_trigopsel)
            )

        return (axis.cloop_winsize, axis.cloop_gstbit5sel, axis.cloop_trigopsel)

    def _set_cloop_window(
        self, axis, winsize=Null(), gstbit5sel=Null(), trigopsel=Null()
    ):
        """
	Set closed loop window parameters, except settle time.
	For explanation of the meaning of different parameters, see
	the comment in the header of the function _get_cloop_window().
	This function has effect only if closed loop is enabled.

        Args:
            - <axis> : Bliss axis object.
	    - <winsize> : Float: closed loop window size (mm),
	    - <gstbit5sel> : Boolean:  bit5 in general status disabled/enabled
	    - <trigopsel>: Int: 0 (trigger on output disabled) or 
		  one of 1,2,3,4 (trigger selected on output D1,2,3,4)
	"""

        self.log.info("_set_cloop_window()")

        if axis.cloop_on == False:
            raise RuntimeError(
                "Cant set closed loop window parameters when closed loop is not enabled"
            )

        if isinstance(winsize, Null):
            winsize = axis.cloop_winsize
        else:
            if winsize <= 0:
                raise ValueError("Closed loop window size %f is not +ve" % winsize)
            axis.cloop_winsize = winsize

        if isinstance(gstbit5sel, Null):
            gstbit5sel = axis.cloop_gstbit5sel
        else:
            if gstbit5sel != False and gstbit5sel != True:
                raise ValueError(
                    "General status bit 5 enable/disable flag has wrong value %s"
                    % gstbit5sel
                )
            axis.cloop_gstbit5sel = gstbit5sel
        if gstbit5sel == True:
            gstbit5sel = 1
        else:
            gstbit5sel = 0

        if isinstance(trigopsel, Null):
            trigopsel = axis.cloop_trigopsel
        else:
            if trigopsel not in [0, 1, 2, 3, 4]:
                raise ValueError(
                    "Trigger output selector %d is none of [0,4]" % trigopsel
                )
            axis.cloop_trigopsel = trigopsel

        _cmd = "%f 0 %d %d %d setclwindow " % (
            winsize,
            gstbit5sel,
            trigopsel,
            axis.number,
        )
        self._send_no_ans(axis, _cmd)
        # ret = self._get_generror(axis)
        # if ret != 0:
        #    raise RuntimeError(self.GENERAL_ERROR_DICT.get(ret))

    def _get_cloop_wintime(self, axis):
        """
	Get closed loop window settle time

        Args:
            - <axis> : Bliss axis object.
        Returns:
            - <wintime> : Float : closed loop window settle time (sec)
	"""

        self.log.info("_get_cloop_wintime()")

        if axis.cloop_on == False:
            raise RuntimeError(
                "Makes no sense to get closed loop window settle time when closed loop is not enabled"
            )

        _cmd = "%d getclwintime " % axis.number
        axis.cloop_wintime = float(self._send(axis, _cmd))

        self.log.debug(
            "_get_cloop_wintime(): closed loop window settling time = %f sec"
            % axis.cloop_wintime
        )

        return axis.cloop_wintime

    def _set_cloop_wintime(self, axis, wintime=Null()):
        """
	Set closed loop window settling time
	This function has effect only if closed loop is enabled.

        Args:
            - <axis> : Bliss axis object.
	    - <wintime> : Float: closed loop window settling time (sec)
	"""
        self.log.info("_set_cloop_wintime()")

        if axis.cloop_on == False:
            raise RuntimeError(
                "Makes no sense to set closed loop window settle time when closed loop is not enabled"
            )

        if isinstance(wintime, Null):
            wintime = axis.cloop_wintime
        else:
            if wintime <= 0:
                raise ValueError(
                    "Closed loop window settle time %f is not +ve" % wintime
                )
            axis.cloop_wintime = wintime

        _cmd = "%f %d setclwintime " % (float(wintime), axis.number)
        self._send_no_ans(axis, _cmd)
        # ret = self._get_generror(axis)
        # if ret != 0:
        #    raise RuntimeError(self.GENERAL_ERROR_DICT.get(ret))

    def _get_cloop_params(self, axis):
        """
	Get closed loop parameters (P,I,D)
	Remark: When reading these parameters saw that there are 
		some more than only P I D returned (returned strin
		has several more values, which are not ducumented
		in the Venus software manual).

        Args:
            - <axis> : Bliss axis object.
        Returns:
	    - <P I D>: 3 closed loop parameters as 1 string
	"""

        self.log.info("_get_cloop_params()")

        _cmd = "%d getclpara " % axis.number
        cloop_params_str = self._send(axis, _cmd)
        # cloop_params_str = string of form: "P I D"
        self.log.debug("_get_cloop_params(): P I D params = %s" % cloop_params_str)
        cloop_params_list = cloop_params_str.split()
        axis.cloop_p = float(cloop_params_list[0])
        axis.cloop_i = float(cloop_params_list[1])
        axis.cloop_d = float(cloop_params_list[2])
        return cloop_params_str

    def _set_cloop_params(self, axis, cloop_params):
        """
	Set closed loop parameters (P,I,D)
	Remark: For the moment we did not touch/modified these
		values, which keep their factory setting.

        Args:
            - <axis> : Bliss axis object.
	    - <cloop_params> = <"P I D"> as string
	"""

        self.log.info("_set_cloop_params()")

        _cmd = "%s 3 %d setclpara " % (cloop_params, axis.number)
        self._send_no_ans(axis, _cmd)
        ret = self._get_generror(axis)
        if ret != 0:
            raise RuntimeError(self.GENERAL_ERROR_DICT.get(ret))

        cloop_params_list = cloop_params.split()
        axis.cloop_p = float(cloop_params_list[0])
        axis.cloop_i = float(cloop_params_list[1])
        axis.cloop_d = float(cloop_params_list[2])
        self.log.debug("_set_cloop_params(): P I D params = %s" % cloop_params)

    # ------------ relative move related method ----------------

    def _rel_move(self, axis, displacement):
        """
        Make a RELATIVE move.

        Args:
            - <axis> : Bliss axis object.
	    - <displacement> : Float: relative move displacement (mm)
        Returns:
            - None
        """

        self.log.info("_rel_move()")

        # _cmd = "%f %d nr " % (displacement, axis.number)
        _cmd = "%f %d nrmove " % (displacement, axis.number)
        self._send_no_ans(axis, _cmd)

    # ------------ holding current related methods ----------------

    def _get_hold_current(self, axis):
        """
	Get holding current = current consumption when motor is not moving
	TODO: find the unit

        Args:
            - <axis> : Bliss axis object.
        Returns:
            - <hold_current> : Float : holding current (unit = ??)
	"""

        self.log.info("_get_hold_current()")

        _cmd = "%d getumotmin " % axis.number
        axis.hold_current = float(self._send(axis, _cmd))

        self.log.debug(
            "_get_hold_current(): hold current = %f (x)A" % axis.hold_current
        )
        return axis.hold_current

    def _set_hold_current(self, axis, hold_current):
        """
	Set holding current = current consumption when motor is not moving
	TODO: find the unit

        Args:
            - <axis> : Bliss axis object.
	    - <hold_current> : Holding current (unit = ??)
	"""

        self.log.info("_set_hold_current()")

        hold_current = float(hold_current)
        _cmd = "%f %d setumotmin " % (hold_current, axis.number)
        self._send_no_ans(axis, _cmd)
        ret = self._get_generror(axis)
        if ret != 0:
            raise RuntimeError(self.GENERAL_ERROR_DICT.get(ret))

        axis.hold_current = hold_current
        self.log.debug(
            "_set_hold_current(): hold current set to = %f (x)A" % axis.hold_current
        )

    # ------------ moving current related methods ----------------

    def _get_move_current(self, axis):
        """
	Get moving current = current consumption when motor is moving
	TODO: find the unit

        Args:
            - <axis> : Bliss axis object.
        Returns:
            - <move_current> : Float : moving current (unit = ??)
	"""

        self.log.info("_get_move_current()")

        _cmd = "%d getumotgrad " % axis.number
        axis.move_current = float(self._send(axis, _cmd))

        self.log.debug(
            "_get_move_current(): move current = %f (x)A" % axis.move_current
        )
        return axis.move_current

    def _set_move_current(self, axis, move_current):
        """
	Set moving current = current consumption when motor is moving
	TODO: find the unit

        Args:
            - <axis> : Bliss axis object.
	    - <hold_current> : Moving current (unit = ??)
	"""

        self.log.info("_set_move_current()")

        move_current = float(move_current)
        _cmd = "%f %d setumotgrad " % (move_current, axis.number)
        self._send_no_ans(axis, _cmd)
        ret = self._get_generror(axis)
        if ret != 0:
            raise RuntimeError(self.GENERAL_ERROR_DICT.get(ret))

        axis.move_current = move_current
        self.log.debug(
            "_set_move_current(): move current set to = %f (x)A" % axis.move_current
        )

    # ----- search the reference position related methods -----

    def _get_to_reference_velocity(self, axis):
        """
	Get velocity for the move to the reference position
        (default = 2.0 degrees/sec and is too high to stop 
	 exactly at the reference position)
	Remark: Reading this velocity we saw that in the 
	        returned string there is one additional value,
		which is not described in Venus sofware manual.

        Args:
            - <axis> : Bliss axis object.
	Return:
	    - <ref_vel> : velocity with which motor moves to search for
			  reference position (degrees/sec)
	"""

        self.log.info("_get_to_reference_velocity()")

        _cmd = "%d 1 getnrefvel " % axis.number
        to_ref_vel_str = self._send(axis, _cmd)
        to_ref_vel_list = to_ref_vel_str.split()
        to_ref_vel = float(to_ref_vel_list[0])
        self.log.debug(
            "_get_to_reference_velocity(): velocity for move to reference = %f"
            % (to_ref_vel)
        )
        axis.to_reference_velocity = to_ref_vel
        return to_ref_vel

    def _set_to_reference_velocity(self, axis, to_reference_velocity=Null()):
        """
	Set velocity for the move to the reference position
        (default = 2.0 degrees/sec)

        Args:
            - <axis> : Bliss axis object.
	    - <to_reference_velocity> : velocity with which motor moves to
			 search for the reference position (degrees/sec)
	"""

        self.log.info("_set_to_reference_velocity()")

        if not isinstance(to_reference_velocity, Null):
            to_ref_vel = float(to_reference_velocity)
        else:
            to_ref_vel = axis.to_reference_velocity

        _cmd = "%f 1 %d setnrefvel " % (to_ref_vel, axis.number)
        self._send_no_ans(axis, _cmd)
        ret = self._get_generror(axis)
        if ret != 0:
            raise RuntimeError(self.GENERAL_ERROR_DICT.get(ret))
        if not isinstance(to_reference_velocity, Null):
            axis.to_reference_velocity = to_ref_vel

    def _move_to_reference(self, axis, max_relative_path):
        """
	Makes a move to a reference position. Micos' manual terminology
	calls reference position what we usually name home position.

	Initially here below in the body of this function the so called
	'1 pass solution' was implemented, where the search for the 
	reference position was done with small velocity (much lower than
	the one used for the ordinary moves). For search of the reference
	position the lower velocity (parameter 'to_reference_velocity'
	in config file) is used in order to stop EXACTLY at the reference
	position, where the reference position status is 1 (elsewhere 
	it is 0). The default value (in NVRAM) for the home search velocity
	is 2.0 degrees/sec, but empirically we found that this is still 
	too high for '1 pass solution'. So we set it to 1 degree/sec to 
	have more chance that when the reference position is reached,
	the reference position status is 1. If the speed for the reference
	position search is too high, then the motor stops very close to 
	the reference position (passing a bit further after finding it),
        but reference position status is 0. 
	We cannot then distinguish this situation from the case, where 
	the max_relative_path is too small and when motor stops before 
	arriving at/finding the reference position. 
	According to the manual this is supposed to be a blocking command,
	but empirically we found that during the movement in search for 
	the reference position, we can query the reference position status.
	We also found empirically that the controller during movement for
	the reference position search does not like us to query for a 
	general error. Therefore in this function afer sending command
	nrefmove, we do not call _get_generror() since would get timeout
	in communication over serial line.

	To speed up the reference position search we changed the code
	where we allow several moves in a loop till the reference 
	position is found. So in the first pass we use rather high speed,
	which in each subsequent pass (where move is done in the opposite
	direction) is divided by 10 as well as the max. distance to go.
	Empirically we found that with initial reference position search 
	speed of 10 degrees/sec 2 moves were sufficient to find the 
	reference/home position.

        Args:
            - <axis> : Bliss axis object.
	    - <max_relative_path> : +/- max rel. path within which the ref. 
                                    position is expected to be found
	"""

        self.log.info("_move_to_reference()")

        self._wait_home_task = None
        self._home_failed = False

        # to be sure that the command buffer is clear
        self._clear_axis(axis)

        # Restore the velocity for moving to the reference position
        # to the value as was found in the configuration in case
        # home search is done just after calling reset_axis() since
        # calling reset_axis sets this velocity to 1 deg/sec.
        to_ref_vel = axis.config.get("to_reference_velocity", float)
        self._set_to_reference_velocity(axis, to_ref_vel)

        # For the same reason set endswitch types to 2 since
        # if reset_axis() was called before home search it was
        # settting them to 1, which is not good for us (moving then
        # reaches +ve or -ve limit and is blocked).
        _ans = self._set_endswitch_types(axis, 2, 2)

        # - '1 pass solution' suitable when the reference/home position
        #   search is done with very low velocity (ex. 1 degree/sec or less).
        #   To use this '1 pass solution' it is sufficient to uncomment
        #   the next 2 lines and then comment the part with the 'in the
        #   loop solution' implemented further down.
        # _cmd = "%f %d nrefmove " % (max_relative_path, axis.number)
        # self._send_no_ans(axis, _cmd)
        ## Next lines commented since during ref.position search calling
        ## general error gives time-out on the serial line!!
        ##ret = self._get_generror(axis)
        ##if ret != 0:
        ##    raise RuntimeError(self.GENERAL_ERROR_DICT.get(ret))

        # - 'in the loop solution' where 1st move is done with rather
        #   high speed and initial max_relative_path. If after the
        #   1st move the reference position status is 0, then the reference
        #   position search and the max_relative path are divided by 10
        #   and next move is done in the opposite direction etc. till
        #   the reference position status = 1.

        distance = max_relative_path
        to_ref_vel = self._get_to_reference_velocity(axis)

        reference_status = 0
        nb_moves = 1
        # Limit to max 3 moves, since empirically found that the
        # reference position was found in max 2 moves when initial
        # reference position search velocity was 10 degrees/sec.
        while reference_status == 0 and nb_moves < 4:
            self.log.debug(
                "_move_to_reference(): move index (start with 1) = %d" % nb_moves
            )
            self.log.debug("_move_to_reference(): max rel.path = %f degrees" % distance)
            _cmd = "%f %d nrefmove " % (distance, axis.number)
            self._send_no_ans(axis, _cmd)

            # start waiting end of homing
            if self._wait_home_task is None:
                self._wait_home_task = gevent.spawn(self._wait_home_func, axis)

            # Read periodically the status to see when the motor stops
            # (ideally it shoud then be at the reference-position)
            is_moving = 1
            while is_moving == 1:
                _ans = self._get_status(axis)
                status = int(_ans)
                self.log.debug(
                    "_move_to_reference(): move nb = %d, status byte = 0x%x"
                    % (nb_moves, status)
                )
                if status & self.CMD_IN_EXEC:
                    # motor is (still) moving
                    is_moving = 1
                    self.log.debug(
                        "_move_to_reference(): move_nb = %d, motor is moving" % nb_moves
                    )
                    time.sleep(1)
                else:
                    is_moving = 0
                    self.log.debug(
                        "_move_to_reference(): move_nb = %d, motor has stopped"
                        % nb_moves
                    )

            # Motor has stopped, verify the reference position status.

            # If it is 1, then it's OK = reference position reached,
            # otherwise (i.e. if it is 0), need to make additional move.
            # If additional move is needed, reduce the max search distance
            # and velocity to 1/10 and change the direction of movement.
            reference_status = self._get_reference_status(axis)
            self.log.debug(
                "_move_to_reference(): move_nb = %d, reference status = %d"
                % (nb_moves, reference_status)
            )
            if reference_status == 0:
                distance = -distance / 10.
                to_ref_vel = to_ref_vel / 10.
                self._set_to_reference_velocity(axis, to_ref_vel)
                nb_moves = nb_moves + 1
                self.log.debug(
                    "_move_to_reference(): makes move %d with 1/10th of distance (%f) and velocity (%f) in the opposite direction"
                    % (nb_moves, distance, to_ref_vel)
                )

        # Come here when reference_status = 1 or nb_moves too high
        # without reaching the reference position. Therefore check the
        # reference status again.
        reference_status = self._get_reference_status(axis)
        if reference_status != 1:
            self.log.debug(
                "_move_to_reference(): In %d moves motor has NOT reached the reference position"
                % nb_moves
            )
            self.log.debug(
                "_move_to_reference(): Either the initial search speed was too high or max search path was too short"
            )
            self._wait_home_task.kill()
            self._home_failed = True
        else:
            self._home_failed = False
            self.log.debug(
                "_move_to_reference(): motor has reached the reference position in %d moves"
                % nb_moves
            )

    def _wait_home_func(self, axis):
        try:
            # waiting end of movement (during homing)
            axis.wait_move()
            # Come here when reference_status = 1 or nb_moves too high
            # without reaching the reference position. Therefore check the
            # reference status again.
            reference_status = self._get_reference_status(axis)
            if reference_status == 1:
                # save offset to keep it between user and dial position
                # after dial is reset to 0 here.
                current_offset = axis.offset

                # Set dial position to 0
                axis.dial = 0.0

                # Make sync_hard() so that dial value match exactly
                # the controller position value.
                axis.sync_hard()

                # set user position to be equal to the offset
                # axis.position = current_offset
                # axis.position = -120.0
                axis.position = -122.0

                # set endswitch types to 2 since reset_axis() sets them to 1
                # _ans = self._set_endswitch_types(axis,2,2)

            # Restore the velocity for moving to the reference position
            # to the value as was found in the configuration
            to_ref_vel = axis.config.get("to_reference_velocity", float)
            self._set_to_reference_velocity(axis, to_ref_vel)

            # set endswitch types to 2 as was found in the configuration
            _ans = self._set_endswitch_types(axis, 2, 2)

        finally:
            self._wait_home_task = None

    def _get_reference_status(self, axis):
        """
	Get status of reference position
	It is 1 when the reference position is reached

        Args:
            - <axis> : Bliss axis object.
	Return:
	    - <0/1> : reference position not reached / reached
	"""

        self.log.info("_get_reference_status()")

        _cmd = "%d getrefst " % (axis.number)
        ref_status_str = self._send(axis, _cmd)
        self.log.debug("_get_reference_status(): %s" % (ref_status_str))
        return int(ref_status_str)

    def _get_log_level(self, axis):
        """
	Get log level.

        Args:
            - <axis> : Bliss axis object.
	Return:
            - <loglevel>: log level. Valid values: NOTSET, DEBUG, INFO, WARN(ING),
                                                   ERROR, FATAL/CRITICAL
        """
        self.log.info("_get_log_level()")

        loglevel_as_number = int(self.log.level)
        loglevel_as_name = logging._levelToName[loglevel_as_number]

        return loglevel_as_name

    def _set_log_level(self, axis, loglevel):
        """
	Set log level.

        Args:
            - <axis> : Bliss axis object.
            - <loglevel>: log level. Valid values: NOTSET, DEBUG, INFO, WARN(ING),
                                                   ERROR, FATAL/CRITICAL or the 
                                                   same strings in small letters.
	Return:
            None
        """
        self.log.info("_set_log_level()")

        loglevel = loglevel.upper()

        if loglevel not in [
            "NOTSET",
            "DEBUG",
            "INFO",
            "WARNING",
            "WARN",
            "ERROR",
            "CRITICAL",
            "FATAL",
        ]:
            raise ValueError(
                f"""
                Warning!!!: Bad value {loglevel} given for log-level. Should be one of:
                NOTSET/noset, DEBUG/debug, INFO/info, WARNING/warning,
                WARN/warn, ERROR/error, CRITICAL/critical, FATAL/fatal
                WARN=WARNING=warn=warning
                CRITICAL=critical=FATAL=fatal"""
            )

        loglevel_as_number = int(logging._nameToLevel[loglevel])
        self.log.setLevel(loglevel_as_number)
