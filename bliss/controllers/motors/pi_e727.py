# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.controllers.motor import Controller
from bliss.common.utils import object_attribute_get, object_attribute_set, object_method
from bliss.common.axis import AxisState
from bliss.common.logtools import log_debug, log_error, log_info
from bliss import global_map

from . import pi_gcs


class PI_E727(pi_gcs.Communication, pi_gcs.Recorder, Controller):
    """
    Bliss controller for ethernet PI E727 piezo controller.
    """

    model = None

    def __init__(self, *args, **kwargs):
        # Called at session startup
        # No hardware access
        pi_gcs.Communication.__init__(self)
        pi_gcs.Recorder.__init__(self)
        Controller.__init__(self, *args, **kwargs)

    # Init of controller.
    def initialize(self):
        """
        Controller intialization.
        Called at session startup.
        Called Only once per controller even if more than
        one axis is declared in config.
        """
        # acceleration is not mandatory in config
        self.axis_settings.config_setting["acceleration"] = False

        # model of the controller.
        self.model = "E727"
        log_debug(self, "model=%s", self.model)

    def close(self):
        """
        Called at session exit. many times ???
        """
        self.com_close()

    def initialize_hardware(self):
        """
        Called once per controller at first use of any of the axes.

        NB: not initialized if accessing to the controller before the axis:
           ex: LILAB [1]: napix.controller.command("CCL 1 advanced")
               !!! === AttributeError: 'NoneType' object has no attribute 'lock' === !!!
        """
        # Initialize socket communication.
        self.com_initialize()

    def initialize_hardware_axis(self, axis):
        """
        Called once per axis at first use of the axis
        """
        pass

    def initialize_axis(self, axis):
        """
        Called at first access to <axis> (eg: __info__())
        """
        axis.channel = axis.config.get("channel", int)

        # check communication
        _ans = self.get_identifier(axis)

        # Enables the closed-loop.
        # To be imporved.
        self._set_closed_loop(axis, True)

        # supposed that we are on target on init
        axis._last_on_target = True

    def initialize_encoder(self, encoder):
        pass

    """
    ON / OFF
    """

    def set_on(self, axis):
        pass

    def set_off(self, axis):
        pass

    """
    POSITION
    """

    def read_position(self, axis):
        """
        Return position of the axis.
        After movement is finished, return the target position.
        """
        if axis._last_on_target:
            _pos = self._get_target_pos(axis)
            log_debug(self, "position read : %g" % _pos)
        else:
            # if moving return real position
            _pos = self._get_pos(axis)
        return _pos

    def read_encoder(self, encoder):
        _ans = self._get_pos(encoder.axis)
        log_debug(self, "read_position measured = %f" % _ans)
        return _ans

    """
    VELOCITY
    """

    def read_velocity(self, axis):
        return self._get_velocity(axis)

    def set_velocity(self, axis, new_velocity):
        log_debug(self, "set_velocity new_velocity = %f" % new_velocity)
        _cmd = "VEL %s %f" % (axis.channel, new_velocity)
        self.command(_cmd)

        return self.read_velocity(axis)

    """
    STATE
    """

    def state(self, axis):
        # self.trace("axis state")
        if self._get_closed_loop_status(axis):
            if self._get_on_target_status(axis):
                return AxisState("READY")
            else:
                return AxisState("MOVING")
        else:
            raise RuntimeError("closed loop disabled")

    """
    MOVEMENTS
    """

    def prepare_move(self, motion):
        pass

    def start_one(self, motion):
        log_debug(self, "start_one target_pos = %f" % motion.target_pos)

        axis = motion.axis
        _cmd = f"MOV {axis.channel} {motion.target_pos}"
        self.command(_cmd)

    def stop(self, axis):
        """
        * STP -> stop asap
        * 24  -> stop asap
        * HLT -> stop smoothly
        * Copy of current position into target position at stop
        * all 3 commands generate (by default) a 'Disable Error 10'.
          (This can be disabled via parameter 0x0E000301)
        """
        log_debug(self, "stop (HLT) requested")
        self.command("HLT %s" % (axis.channel))

    """
    E727 specific
    """

    @object_method(types_info=("None", "str"))
    def get_identifier(self, axis):
        return self.command("IDN?")

    @object_method(types_info=("None", "float"))
    def get_voltage(self, axis):
        """ Return voltage read from controller."""
        _ans = self.command(f"SVA? {axis.channel}")
        _voltage = float(_ans)
        return _voltage

    @object_method(types_info=("None", "float"))
    def get_output_voltage(self, axis):
        """ Return output voltage read from controller. """
        return float(self.command(f"VOL? {axis.channel}"))

    def set_voltage(self, axis, new_voltage):
        """ Set Voltage to the controller."""
        _cmd = "SVA %s %g" % (axis.channel, new_voltage)
        self.command(_cmd)

    def _get_velocity(self, axis):
        """
        Return velocity taken from controller.
        """
        _ans = self.command(f"VEL? {axis.channel}")
        _velocity = float(_ans)

        return _velocity

    def _get_pos(self, axis):
        """
        Return real position read by capacitive sensor.
        """
        _ans = self.command(f"POS? {axis.channel}")
        _pos = float(_ans)
        return _pos

    """
    CLOSED LOOP
    """

    def _get_target_pos(self, axis):
        """
        Return last target position (setpoint value).
        """
        _ans = self.command(f"MOV? {axis.channel}")
        _pos = float(_ans)
        return _pos

    def _get_on_target_status(self, axis):
        """
        Return 'On-target status' (ONT? command) indicating
        if movement is finished and measured position is within
        on-target window.
        """
        last_on_target = bool(int(self.command(f"ONT? {axis.channel}")))
        axis._last_on_target = last_on_target
        return last_on_target

    def _get_closed_loop_status(self, axis):
        _status = self.command(f"SVO? {axis.channel}")

        if _status == "1":
            return True

        if _status == "0":
            return False

        log_error(self, "ERROR on _get_closed_loop_status, _status=%r" % _status)
        return -1

    def _set_closed_loop(self, axis, state):
        if state:
            _cmd = f"SVO {axis.channel} 1"
        else:
            _cmd = f"SVO {axis.channel} 0"
        self.command(_cmd)

    @object_method(types_info=("None", "None"))
    def open_loop(self, axis):
        self._set_closed_loop(axis, False)

    @object_method(types_info=("None", "None"))
    def close_loop(self, axis):
        self._set_closed_loop(axis, True)

    @object_attribute_get(type_info="bool")
    def get_closed_loop(self, axis):
        return self._get_closed_loop_status(axis)

    """
    INFO
    """

    @object_attribute_get(type_info="str")
    def get_model(self, axis):
        return self.model

    def get_id(self, axis):
        """
        Return controller identifier.
        """
        return self.command("*IDN?")

    def get_axis_info(self, axis):
        """
        Return Controller specific info about <axis> for user.
        Detailed infos are in get_info().
        """
        info_str = "PI AXIS INFO:\n"
        info_str += f"     voltage (SVA) = {self.get_voltage(axis)}\n"
        info_str += f"     output voltage (VOL) = {self.get_output_voltage(axis)}\n"
        info_str += f"     closed loop = {self.get_closed_loop(axis)}\n"

        return info_str

    def __info__(self):
        info_str = "CONTROLLER:\n"

        (_err_nb, _err_str) = self.get_error()
        info_str = f"Last Error: {_err_nb} ({_err_str})\n"
        info_str += "COMMUNICATION CONFIG:\n     "
        info_str += self.sock.__info__()
        return info_str

    @object_method(types_info=("None", "string"))
    def get_info(self, axis):
        """
        Return detailed information about controller.
        Helpful to tune the device.
        """
        axis.position  # force axis initialization

        _tab = 30
        _txt = ""

        # use command "HPA?" to get parameters address + description

        # NB: 0x7000000 used and not 0x07000000
        #     because PI 727 remove first 0 in the command answer
        #     -> cause problem in answer check.
        _infos = [
            ("Real Position", "POS? %s"),
            ("Setpoint Position", "MOV? %s"),
            ("On target", "ONT? %s"),
            ("Velocity", "VEL? %s"),
            ("Closed loop status", "SVO? %s"),
            ("Auto Zero Calibration ?", "ATZ? %s"),
            ("Analog input setpoint", "AOS? %s"),
            ("ADC value of analog input", "TAD? %s"),
            ("Analog setpoints", "TSP? %s"),
            ("AutoZero Low Voltage", "SPA? %s 0x7000A00"),
            ("AutoZero High Voltage", "SPA? %s 0x7000A01"),
            ("Range Limit min", "SPA? %s 0x7000000"),
            ("Range Limit max", "SPA? %s 0x7000001"),
            ("ON Target Tolerance", "SPA? %s 0x7000900"),
            ("Settling time", "SPA? %s 0X7000901"),
        ]

        for i in _infos:
            _cmd = i[1]
            if "%s" in _cmd:
                _cmd = _cmd % (axis.channel)
            _ans = self.command(_cmd)
            _txt = _txt + "%*s: %s\n" % (_tab, i[0], _ans)

        return _txt
