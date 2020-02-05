# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.controllers.motor import Controller
from bliss.common.utils import object_method
from bliss.common.axis import AxisState
from bliss.common.utils import object_method
from bliss.common.logtools import *
from bliss import global_map

from . import pi_gcs
from bliss.comm.util import SERIAL

import sys
import time

"""
Bliss controller for ethernet PI E871 piezo controller.
Cyril Guilloud ESRF BLISS  2016
"""


class PI_E871(Controller):
    def __init__(self, *args, **kwargs):
        Controller.__init__(self, *args, **kwargs)

        self.cname = "E871"

    # Init of controller.
    def initialize(self):
        """
        Controller intialization : opens a single serial for all axes.
        """
        self.serial = pi_gcs.get_pi_comm(self.config, SERIAL, baudrate=115200)

        global_map.register(self, children_list=[self.serial])

        self._status = ""
        try:
            _ans = self.serial.write_readline(b"ERR?\n").decode()
            print("err=%r" % _ans)
            _ans = self.serial.write_readline(b"*IDN?\n").decode()
            print(_ans)
            # 871 : '(c)2013 Physik Instrumente (PI) GmbH & Co. KG, E-871.1A1, 0, 01.00'
            # 873 : '(c)2015 Physik Instrumente (PI) GmbH & Co. KG, E-873.1A1, 115072229, 01.09'
            log_debug(self, _ans)

            try:
                id_pos = _ans.index("E-871")
            except:
                log_info(self, "not a 871")
                raise

            try:
                id_pos = _ans.index("E-873")
            except:
                log_info(self, "not a 873")
                raise

            if id_pos > 0 and id_pos < 100:
                log_debug(self, "controller is responsive ID=%s" % _ans)
            elif id_pos == 0:
                log_debug(self, "error : *IDN? -> %r" % _ans)
        except:
            self._status = (
                'communication error : no PI E871 or E873 found on serial "%s"'
                % self.serial_line
            )
            print(self._status)
            log_debug(self, self._status)

    def finalize(self):
        """
        Closes the serial line
        """
        # not called at end of device server ??? :(
        # called on a new axis creation ???

        # do I stop eventual motion ???

        if self.serial:
            self.serial.close()

    # Init of each axis.
    def initialize_axis(self, axis):
        log_debug(self, "axis initialization")
        axis.axis_id = axis.config.get("axis_id", str)
        axis.address = axis.config.get("address", int)

        # Enables servo mode.
        log_debug(self, "Switches %s servo mode ON" % axis.name)
        self._enable_servo_mode(axis)

        # Checks referencing.
        _ref = self._get_referencing(axis)
        if _ref == 0:
            print("axis '%s' must be referenced before being movable" % axis.name)
        else:
            print("axis '%s' is referenced." % axis.name)

    @object_method(types_info=("float", "None"))
    def custom_initialize_axis(self, axis, current_pos):
        """
        If axis is not referenced (after power on) Use this command to 
        avid to do a referencing by moving to the limits.
        * Activates manual referencing mode.
        * Sets <current_pos> as current position.
        * Synchronizes axis position.
        """
        log_debug(self, "custom axis initialization , current_pos=%g" % current_pos)
        self.send_no_ans(axis, "%d SVO %s 1" % (axis.address, axis.axis_id))
        self._check_error(axis)
        self.reference_axis_ref_switch(axis)
        self._check_error(axis)
        axis.sync_hard()

    def initialize_encoder(self, encoder):
        pass

    """
    ON / OFF
    """

    def set_on(self, axis):
        pass

    def set_off(self, axis):
        pass

    def read_position(self, axis):
        _ans = self._get_target_pos(axis)
        log_debug(self, "read_position = %f" % _ans)
        return _ans

    #     def set_position(self, axis, new_pos):
    #         """Set axis position to a new value given in motor units"""
    #         log_debug(self, "set_position = %g" % new_pos)
    #         #l = libicepap.PosList()
    #         #l[axis.libaxis] = new_pos
    #         #self.libgroup.pos(l)
    #         #return self.read_position(axis)

    #    def read_encoder(self, encoder):
    #        _ans = self._get_pos(encoder.axis)
    #        log_debug(self, "read_position measured = %f" % _ans)
    #        return _ans

    """ VELOCITY """

    def read_velocity(self, axis):
        return self._get_velocity(axis)

    def set_velocity(self, axis, new_velocity):
        log_debug(self, "set_velocity new_velocity = %f" % new_velocity)
        log_debug(self, "NO VELOCITY FOR THIS CONTROLLER")
        # self.send_no_ans(axis, "%d VEL %s %f" % (axis.address, axis.axis_id, new_velocity))
        return self.read_velocity(axis)

    """ ACCELERATION """

    def read_acceleration(self, axis):
        """Returns axis current acceleration in uu/sec2"""
        _acc = self._get_acceleration(axis)
        return _acc

    def set_acceleration(self, axis, new_acc):
        """Set axis acceleration given in uu/sec2"""
        self._set_acceleration(axis, new_acc)
        return self.read_acceleration(axis)

    """ STATE """

    def state(self, axis):
        log_debug(self, "in state(%s)" % axis.name)

        # _ref = self._get_referencing(axis)
        # if _ref == 0:
        #     return AxisState(("UNREFERENCED","axis need to be referenced before a motion to be possible"))

        if self._get_on_target_status(axis):
            return AxisState("READY")
        else:
            return AxisState("MOVING")

    """ MOVEMENTS """

    def prepare_move(self, motion):
        pass

    def start_one(self, motion):
        log_debug(self, "start_one target_pos = %f" % motion.target_pos)
        self.send_no_ans(
            motion.axis,
            "%d MOV %s %g"
            % (motion.axis.address, motion.axis.axis_id, motion.target_pos),
        )

    def stop(self, axis):
        # to check : copy of current position into target position ???
        self.send_no_ans(axis, "STP")

    # HOME : GOH

    """ RAW COMMANDS """
    # Adds \n before to send command.
    def raw_write(self, com):
        log_debug(self, "com=%s" % repr(com))
        _com = com + "\n"
        self.serial.write(_com.encode())

    def raw_write_read(self, com):
        log_debug(self, "com=%s" % repr(com))
        _com = com + "\n"
        _ans = self.serial.write_readline(_com.encode()).decode().rstrip()
        log_debug(self, "ans=%s" % repr(_ans))
        return _ans

    def get_id(self, axis):
        return self.send(axis, "%d IDN?" % axis.address)

    """
    E871 specific
    """

    def _get_velocity(self, axis):
        """
         Returns velocity read from controller. (physical unit/s)
         """
        return 1

    def _get_pos(self, axis):
        """
        Returns position read from controller.
        """
        try:
            _ans = self.send(axis, "%d POS?" % axis.address)
            _pos = float(_ans.split("=")[1])
        except:
            _pos = 0

        return _pos

    def _get_acceleration(self, axis):
        """
        Returns acceleration read from controller.
        """
        return 1

    def _set_acceleration(self, axis, value):
        log_info(self, "impossible to set acceleration on this controller")
        return 1

    def _get_target_pos(self, axis):
        """
        Returns last target position (setpoint value).
        """
        _ans = self.send(axis, "%d MOV?" % axis.address)

        # _ans should looks like "<axis_id>=-8.45709419e+01\n"
        _pos = float(_ans.split("=")[1])

        return _pos

    def _get_on_target_status(self, axis):
        _ans = self.send(axis, "%d ONT?" % axis.address)
        # print "_ans on target=", _ans
        # "0 1 M1=1"
        _ans = _ans.split("=")[1]

        if _ans == "1":
            return True
        else:
            return False

    def _enable_servo_mode(self, axis):
        """
        Activates the servo mode for axis <axis>.
        """
        self.send_no_ans(axis, "%d SVO %s 1" % (axis.address, axis.axis_id))
        self._check_error(axis)

    def _get_referencing(self, axis):
        """
        Returns referencing mode from controller.
        """
        try:
            _ans = self.send(axis, "%d FRF?" % axis.address)
            _ref = int(_ans.split("=")[1])
        except:
            _ref = 0

        return _ref

    @object_method(types_info=("None", "None"))
    def reference_axis_ref_switch(self, axis):
        """
        Launches referencing of axis <axis>.
        """
        self.send_no_ans(axis, "%d FRF" % axis.address)
        time.sleep(0.5)

        _ref = self._get_referencing(axis)
        while _ref != 1:
            time.sleep(0.5)
            _ref = self._get_referencing(axis)

        self._check_error(axis)
        axis.sync_hard()

    @object_method(types_info=("None", "None"))
    def reference_axis_neg_lim(self, axis):
        """
        Launches referencing of axis <axis> using NEGATIVE limit switch.
        """
        self.send_no_ans(axis, "%d FNL" % axis.address)
        time.sleep(0.5)

        _ref = self._get_referencing(axis)
        while _ref != 1:
            time.sleep(0.5)
            _ref = self._get_referencing(axis)

        self._check_error(axis)
        axis.sync_hard()

    @object_method(types_info=("None", "None"))
    def reference_axis_pos_lim(self, axis):
        """
        Launches referencing of axis <axis> using POSITIVE limit switch.
        """
        self.send_no_ans(axis, "%d FPL" % axis.address)
        time.sleep(0.5)

        _ref = self._get_referencing(axis)
        while _ref != 1:
            time.sleep(0.5)
            _ref = self._get_referencing(axis)

        self._check_error(axis)
        axis.sync_hard()

    @object_method(types_info=("None", "str"))
    def _get_error(self, axis):
        """
        Returns (err_number, error_string).
        returns (0, 'No Error') if no error.
        """
        _error_number = int(self.send(axis, "%d ERR?" % axis.address).split(" ")[2])
        _error_str = pi_gcs.get_error_str(_error_number)
        return "ERR %d : %s" % (_error_number, _error_str)

    def _check_error(self, axis):
        print("_check_error: axis %s got %s" % (axis.name, self._get_error(axis)))

    def _stop(self):
        self.serial.write(b"STP\n")

    def send(self, axis, cmd):
        """
        - Adds the 'newline' terminator character : "\\\\n"
        - Sends command <cmd> to the Serial line.
        - Axis_id must be defined in <cmd>.
        - <axis> is passed for debugging purposes.
        - Returns answer from controller.

        Args:
            - <axis> : passed for debugging purposes.
            - <cmd> : command to send to controller (Axis_id is already mentionned  in <cmd>).

        Returns:
            - 1-line answer received from the controller (without "\\\\n" terminator).

        Raises:
            ?
        """

        log_debug(self, "cmd=%s" % repr(cmd))
        _cmd = cmd + "\n"
        _ans = self.serial.write_readline(_cmd.encode()).decode().rstrip()
        log_debug(self, "ans=%s" % repr(_ans))
        return _ans

    def send_no_ans(self, axis, cmd):
        """
        - Adds the 'newline' terminator character : "\\\\n"
        - Sends command <cmd> to the Serial device.
        - Axis_id is defined in <cmd>.
        - <axis> is passed for debugging purposes.
        - Used for answer-less commands, then returns nothing.
        """
        log_debug(self, 'cmd="%s" ' % cmd)
        _cmd = cmd + "\n"
        self.serial.write(_cmd.encode())

    @object_method(types_info=("None", "str"))
    def _get_all_params(self, axis):
        self.serial.write(b"1 HPA?\n")
        _txt = ""

        _ans = self.serial.readline().decode()
        _txt += _ans

        while _ans != "end of help\n":
            _ans = self.serial.readline().decode()
            _txt += _ans

        return _txt

    # result of this command:

    # 0 1 The following parameters are valid:
    # 0xA=	0	1	FLOAT	motorcontroller	step velocity maximum
    # 0xB=	0	1	FLOAT	motorcontroller	step acceleration
    # 0xC=	0	1	FLOAT	motorcontroller	step deceleration
    # 0xE=	0	1	INT	motorcontroller	numerator
    # 0xF=	0	1	INT	motorcontroller	denominator
    # 0x13=	0	1	INT	motorcontroller	rotary stage	(0=no 1=yes)
    # 0x14=	0	1	INT	motorcontroller	has reference
    # 0x15=	0	1	FLOAT	motorcontroller	travel range maximum
    # 0x16=	0	1	FLOAT	motorcontroller	reference position
    # 0x17=	0	1	FLOAT	motorcontroller	distance between reference and negative limit
    # 0x18=	0	1	INT	motorcontroller	limit mode
    # 0x1A=	0	1	INT	motorcontroller	has brake
    # 0x2F=	0	1	FLOAT	motorcontroller	distance between reference and positive limit
    # 0x30=	0	1	FLOAT	motorcontroller	travel range minimum
    # 0x31=	0	1	INT	motorcontroller	invert reference
    # 0x32=	0	1	INT	motorcontroller	has limits	(0=limitswitchs 1=no limitswitchs)
    # 0x3C=	0	1	CHAR	motorcontroller	stage name
    # 0x40=	0	1	INT	motorcontroller	holding current
    # 0x41=	0	1	INT	motorcontroller	operating current
    # 0x42=	0	1	INT	motorcontroller	holding current delay
    # 0x47=	0	1	INT	motorcontroller	reference travel direction
    # 0x49=	0	1	FLOAT	motorcontroller	step velocity
    # 0x4A=	0	1	FLOAT	motorcontroller	step acceleration maximum
    # 0x4B=	0	1	FLOAT	motorcontroller	step deceleration maximum
    # 0x50=	0	1	FLOAT	motorcontroller	referencing velocity

    # 0x5C=	0	1	INT	motorcontroller	DIO as REF
    # 0x5D=	0	1	INT	motorcontroller	DIO as NLIM
    # 0x5E=	0	1	INT	motorcontroller	DIO as PLIM
    # 0x5F=	0	1	INT	motorcontroller	invert DIO-NLIM
    # 0x60=	0	1	INT	motorcontroller	invert DIO-PLIM
    # 0x61=	0	1	INT	motorcontroller	invert joystick
    # 0x63=	0	1	FLOAT	motorcontroller	distance between limit and hard stop
    # 0x72=	0	1	INT	motorcontroller	macro ignore error
    # 0x9A=	0	1	INT	motorcontroller	external sensor numerator
    # 0x9B=	0	1	INT	motorcontroller	external sensor denominator

    # 0x7000601=	0	1	CHAR	motorcontroller	axis unit
    # 0x7000000=	0	1	FLOAT	motorcontroller	travel range minimum
    # 0x7000001=	0	1	FLOAT	motorcontroller	travel range maximum
    # end of help

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

        _txt = ""
        _txt = _txt + "###############################\n"
        _txt = _txt + "id                 : " + self.send(axis, "*IDN?") + "\n"
        _txt = (
            _txt
            + "Firmware Ver.      : "
            + self.send(axis, "%d VER?" % axis.address)
            + "\n"
        )
        self._check_error(axis)
        _txt = (
            _txt
            + "Syntax Ver.        : "
            + self.send(axis, "%d CSV?" % axis.address)
            + "\n"
        )
        self._check_error(axis)
        _txt = (
            _txt
            + "axis ID            : "
            + self.send(axis, "%d SAI?" % axis.address)
            + "\n"
        )
        self._check_error(axis)
        _txt = (
            _txt
            + "error              : "
            + self.send(axis, "%d ERR?" % axis.address)
            + "\n"
        )
        self._check_error(axis)
        _txt = (
            _txt
            + "servo ON?          : "
            + self.send(axis, "%d SVO?" % axis.address)
            + "\n"
        )
        self._check_error(axis)
        _txt = (
            _txt
            + "Position           : "
            + self.send(axis, "%d POS?" % axis.address)
            + "\n"
        )
        self._check_error(axis)
        _txt = (
            _txt
            + "Target Pos         : "
            + self.send(axis, "%d MOV?" % axis.address)
            + "\n"
        )
        self._check_error(axis)
        _txt = (
            _txt
            + "On Target          : "
            + self.send(axis, "%d ONT?" % axis.address)
            + "\n"
        )
        #        _txt = _txt + "Velocity           : " + self.send(axis, "%d VEL?" % axis.address) + "\n"
        _txt = (
            _txt
            + "SVO?               : "
            + self.send(axis, "%d SVO?" % axis.address)
            + "\n"
        )
        self._check_error(axis)
        _txt = (
            _txt
            + "LIM?               : "
            + self.send(axis, "%d LIM?" % axis.address)
            + "\n"
        )
        self._check_error(axis)
        _txt = (
            _txt
            + "ref mode (RON?) 1:FRF or F(N/P)L : "
            + self.send(axis, "%d RON?" % axis.address)
            + "\n"
        )
        self._check_error(axis)
        _txt = (
            _txt
            + "referenced?           : "
            + self.send(axis, "%d FRF?" % axis.address)
            + "\n"
        )
        self._check_error(axis)
        _txt = (
            _txt
            + "has ref switch     : "
            + self.send(axis, "%d TRS?" % axis.address)
            + "\n"
        )
        self._check_error(axis)
        _txt = (
            _txt
            + "cppu (num)            : "
            + self.send(axis, "%d SPA? %s  0xE" % (axis.address, axis.axis_id))
            + "\n"
        )
        self._check_error(axis)
        _txt = (
            _txt
            + "cppu (denom)          : "
            + self.send(axis, "%d SPA? %s  0xF" % (axis.address, axis.axis_id))
            + "\n"
        )
        self._check_error(axis)
        _txt = (
            _txt
            + "rotation              : "
            + self.send(axis, "%d SPA? %s 0x13" % (axis.address, axis.axis_id))
            + "\n"
        )
        self._check_error(axis)
        _txt = (
            _txt
            + "has built-in ref      : "
            + self.send(axis, "%d SPA? %s 0x14" % (axis.address, axis.axis_id))
            + "\n"
        )
        self._check_error(axis)
        _txt = (
            _txt
            + "MAX_TRAVEL_RANGE_POS  : "
            + self.send(axis, "%d SPA? %s 0x15" % (axis.address, axis.axis_id))
            + "\n"
        )
        self._check_error(axis)
        _txt = (
            _txt
            + "VALUE_AT_REF_POS      : "
            + self.send(axis, "%d SPA? %s 0x16" % (axis.address, axis.axis_id))
            + "\n"
        )
        self._check_error(axis)
        _txt = (
            _txt
            + "DISTANCE_REF_TO_N_LIM : "
            + self.send(axis, "%d SPA? %s 0x17" % (axis.address, axis.axis_id))
            + "\n"
        )
        self._check_error(axis)
        _txt = (
            _txt
            + "Axis limit mode       : "
            + self.send(axis, "%d SPA? %s 0x18" % (axis.address, axis.axis_id))
            + "\n"
        )
        self._check_error(axis)
        _txt = (
            _txt
            + "DISTANCE_REF_TO_P_LIM : "
            + self.send(axis, "%d SPA? %s 0x2F" % (axis.address, axis.axis_id))
            + "\n"
        )
        self._check_error(axis)
        _txt = (
            _txt
            + "MAX_TRAVEL_RANGE_NEG  : "
            + self.send(axis, "%d SPA? %s 0x30" % (axis.address, axis.axis_id))
            + "\n"
        )
        self._check_error(axis)
        _txt = (
            _txt
            + "invert ref            : "
            + self.send(axis, "%d SPA? %s 0x31" % (axis.address, axis.axis_id))
            + "\n"
        )
        self._check_error(axis)
        _txt = (
            _txt
            + "stage has limit sw.   : "
            + self.send(axis, "%d SPA? %s 0x32" % (axis.address, axis.axis_id))
            + "\n"
        )
        self._check_error(axis)
        _txt = (
            _txt
            + "stage name            : "
            + self.send(axis, "%d SPA? %s 0x3c" % (axis.address, axis.axis_id))
            + "\n"
        )
        self._check_error(axis)
        _txt = (
            _txt
            + "default dir. for ref. : "
            + self.send(axis, "%d SPA? %s 0x47" % (axis.address, axis.axis_id))
            + "\n"
        )
        self._check_error(axis)
        _txt = (
            _txt
            + "axis unit             : "
            + self.send(axis, "%d SPA? %s 0x07000601" % (axis.address, axis.axis_id))
            + "\n"
        )
        self._check_error(axis)

        _txt = _txt + "###############################\n"

        return _txt


# 873
#
# ###############################
# id                 : (c)2015 Physik Instrumente (PI) GmbH & Co. KG, E-873.1A1, 115072229, 01.09
# Firmware Ver.      : 0 1 FW_DSP: V01.09
# Syntax Ver.        : 0 1 2.0
# axis ID            : 0 1 1
# error              : 0 1 0
# servo ON?          : 0 1 1=1
# Position           : 0 1 1=3.0000000
# Target Pos         : 0 1 1=3.0000000
# On Target          : 0 1 1=1
# SVO?               : 0 1 1=1
# LIM?               : 0 1 1=0
# Brake?             :
# ref mode (RON?) 1:FRF or F(N/P)L : 0 1 1=1
# referenced?           : 0 1 1=1
# has ref switch     : 0 1 1=1
# max velocity          : 0 1
# acceleration          : 0 1
# deceleration          : 0 1
# cppu (num)            : 0 1 1 0XE=1000000
# cppu (denom)          : 0 1 1 0XF=1
# rotation              : 0 1 1 0X13=0
# has built-in ref      : 0 1 1 0X14=1
# MAX_TRAVEL_RANGE_POS  : 0 1 1 0X15=13.0000000
# VALUE_AT_REF_POS      : 0 1 1 0X16=0.0000000
# DISTANCE_REF_TO_N_LIM : 0 1 1 0X17=13.0000000
# Axis limit mode       : 0 1 1 0X18=0
# Has breake            : 0 1
# DISTANCE_REF_TO_P_LIM : 0 1 1 0X2F=13.0000000
# MAX_TRAVEL_RANGE_NEG  : 0 1 1 0X30=-13.0000000
# invert ref            : 0 1 1 0X31=0
# stage has limit sw.   : 0 1 1 0X32=1
# stage name            : 0 1 1 0X3C=Q-545.240
# holding current(mA)   : 0 1
# operating current(mA) : 0 1
# holding current delay : 0 1
# default dir. for ref. : 0 1 1 0X47=0
# step velocity         : 0 1
# max acceleration      : 0 1
# max deceleration      : 0 1
# velocity for ref move : 0 1
# axis unit             : 0 1 1 0X07000601=MM
# ###############################
