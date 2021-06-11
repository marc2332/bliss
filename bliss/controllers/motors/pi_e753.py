# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
import contextlib
import numpy

from bliss.controllers.motor import Controller
from bliss.common.utils import object_attribute_get, object_attribute_set, object_method
from bliss.common.axis import AxisState
from bliss.common import axis as axis_module
from bliss.common.logtools import log_debug, log_info

from . import pi_gcs
import gevent.lock


"""
Bliss controller for ethernet PI E753 piezo controller.
Model PI E754 should be compatible.. to be tested.
"""

"""
Special commands, e.g. fast polling commands, consist only of one
character. The 24th ASCII character e.g. is called #24. Note that
these commands are not followed by a termination character (but the
responses to them are).

* #5: Request Motion Status
* #9: Get Wave Generator Status
* #24: Stop All Motion
"""


class PI_E753(pi_gcs.Communication, pi_gcs.Recorder, Controller):
    def __init__(self, *args, **kwargs):
        pi_gcs.Communication.__init__(self)
        pi_gcs.Recorder.__init__(self)
        Controller.__init__(self, *args, **kwargs)

    # Init of controller.
    def initialize(self):
        """
        Controller intialization.
        * 
        """
        self.com_initialize()

        # acceleration is not mandatory in config
        self.axis_settings.config_setting["acceleration"] = False

        # Check model.
        try:
            idn_ans = self.command("*IDN?")
            log_info(self, "IDN?: %s", idn_ans)
            if idn_ans.find("E-753") > 0:
                self.model = "E-753"
            elif idn_ans.find("E-754") > 0:
                self.model = "E-754"
            else:
                self.model = "UNKNOWN"
        except:
            self.model = "UNKNOWN"

        log_debug(self, "model=%s", self.model)

    def initialize_axis(self, axis):
        log_debug(self, "axis initialization")

        # Enables the closed-loop.
        # Can be dangerous ??? test diff between target and position before ???
        # self._set_closed_loop(axis, True)

        # ?
        self._add_recoder_enum_on_axis(axis)

    def initialize_encoder(self, encoder):
        pass

    """ ON / OFF """

    def set_on(self, axis):
        pass

    def set_off(self, axis):
        pass

    """ Position """

    def read_position(self, axis):
        _ans = self._get_target_pos(axis)
        log_debug(self, "read_position = %f" % _ans)
        return _ans

    def read_encoder(self, encoder):
        _ans = self._get_pos()

        # log_info(self, "read encodeer")
        # log_warning(self, "read encod")
        log_debug(self, "read_position measured = %f" % _ans)
        return _ans

    """ VELOCITY """

    def read_velocity(self, axis):
        return self._get_velocity(axis)

    def set_velocity(self, axis, new_velocity):
        """
        - <new_velocity>: 'float'
        """
        log_debug(self, "set_velocity new_velocity = %f" % new_velocity)
        self.command("VEL 1 %f" % new_velocity)

        return self.read_velocity(axis)

    """ STATE """

    def state(self, axis):
        # check if WAV motion is active  #9
        if self.sock.write_readline(chr(9).encode()) != b"0":
            return AxisState("MOVING")

        if self._get_closed_loop_status(axis):
            if self._get_on_target_status(axis):
                return AxisState("READY")
            else:
                return AxisState("MOVING")
        else:
            # open-loop => always ready.
            return AxisState("READY")

    def check_ready_to_move(self, axis, state):
        return True  # Can always move

    """ MOVEMENTS """

    def prepare_move(self, motion):
        pass

    def start_one(self, motion):
        """
        - Sends 'MOV' or 'SVA' depending on closed loop mode.

        Args:
            - <motion> : Bliss motion object.

        Return:
            - None
        """
        if self._get_closed_loop_status(motion.axis):
            # Command in position.
            self.command("MOV 1 %g" % motion.target_pos)
        else:
            # Command in voltage.
            self.command("SVA 1 %g" % motion.target_pos)

    def stop(self, axis):
        """
        * STP -> stop asap
        * 24    -> stop asap
        * to check : copy of current position into target position ???
        * NB: 'HLT' command does not exist for pi e-753
        """
        if self._get_closed_loop_status(axis):
            self.command("STP")

    """
    E753 specific
    """

    @object_method(types_info=("None", "float"))
    def get_voltage(self, axis):
        """ Return voltage read from controller."""
        return float(self.command("SVA? 1"))

    @object_method(types_info=("None", "float"))
    def get_output_voltage(self, axis):
        """ Return output voltage read from controller. """
        return float(self.command("VOL? 1"))

    def set_voltage(self, axis, new_voltage):
        """ Sets Voltage to the controller."""
        self.command("SVA 1 %g" % new_voltage)

    def _get_velocity(self, axis):
        """
        Return velocity taken from controller.
        """
        return float(self.command("VEL? 1"))

    def _get_pos(self):
        """
        - no <axis> parameter as _get_pos() is also used by encoder object.

        Returns : float
            Real position of axis read by capacitive sensor.
        """
        return float(self.command("POS? 1"))

    def _get_target_pos(self, axis):
        """
        Return last target position (MOV?/SVA?/VOL? command) (setpoint value).
            - SVA? : Query the commanded output voltage (voltage setpoint).
            - VOL? : Query the current output voltage (real voltage).
            - MOV? : Return the last valid commanded target position.
        """
        if self._get_closed_loop_status(axis):
            return float(self.command("MOV? 1"))
        else:
            return float(self.command("SVA? 1"))

    def _get_on_target_status(self, axis):
        _status = self.command("ONT? 1")
        if _status == "1":
            return True
        elif _status == "0":
            return False
        else:
            return -1

    """ CLOSED LOOP"""

    def _get_closed_loop_status(self, axis):
        _status = self.command("SVO? 1")
        if _status == "1":
            return True
        elif _status == "0":
            return False
        else:
            return -1

    def _set_closed_loop(self, axis, state):
        """
        Activate closed-loop if <state> is True.
        """
        self.command("SVO 1 %d" % bool(state))

    @object_method(types_info=("None", "None"))
    def open_loop(self, axis):
        self._set_closed_loop(axis, False)

    @object_method(types_info=("None", "None"))
    def close_loop(self, axis):
        self._set_closed_loop(axis, True)

    @object_attribute_get(type_info="bool")
    def get_closed_loop(self, axis):
        return self._get_closed_loop_status(axis)

    @object_attribute_set(type_info="bool")
    def set_closed_loop(self, axis, value):
        print("set_closed_loop DISALBED FOR SECURITY ... ")
        # self._set_closed_loop(axis, True)

    def _stop(self, axis):
        print("????????? PI_E753.py received _stop ???")
        self.command("STP")

    """
    ID/INFO
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
        """Return Controller specific info about <axis>
        """
        info_str = "PI AXIS INFO:\n"
        info_str += f"     voltage (SVA) = {self.get_voltage(axis)}\n"
        info_str += f"     output voltage (VOL) = {self.get_output_voltage(axis)}\n"
        info_str += f"     closed loop = {self.get_closed_loop(axis)}\n"

        return info_str

    def __info__(self):
        """

        IPSTART:
        If a DHCP server is present in the network, the
        IPSTART setting is ignored and the IP address is
        always obtained from the DHCP server.
        If the E-753 is directly connected to the Ethernet card in
        the PC (no DHCP server is present), the current IP
        address of the E-753 will be as follows:
        for IPSTART = 0, the IPADR setting will be used
        for IPSTART = 1, the default value 192.168.0.1 will be
        used.
        """

        idn = self.command("*IDN?")
        # ifc = self.command("IFC? IPADR MACADR IPSTART", 3)
        ifc = [
            bs.decode()
            for bs in self.sock.write_readlines(b"IFC?  IPADR MACADR IPSTART\n", 3)
        ]

        info_str = "CONTROLLER:\n"
        info_str += f"     ID: {idn}\n"
        info_str += f"     MAC address: {ifc[1]}\n"
        info_str += f"     IP address: {ifc[0]}\n"
        _start_mode = "use IPADR" if ifc[2] == "0" else "use default -> 192.168.0.1"
        info_str += f"     IP start: IPSTART={ifc[2]}({_start_mode})\n"
        info_str += "COMMUNICATION CONFIG:\n     "
        info_str += self.sock.__info__()
        return info_str

    @object_method(types_info=("None", "string"))
    def get_info(self, axis):
        return self.get_hw_info()

    def get_hw_info(self):
        """
        Helpful parameter to tune the device.

        Args:
            None
        Return: str
            information about controller.

        IDN? for e753:
             Physik Instrumente, E-753.1CD, 111166712, 08.00.02.00

        IDN? for e754:
             (c)2016 Physik Instrumente (PI) GmbH & Co. KG, E-754.1CD, 117045756, 1.01

        0xffff000* parameters are not valid for 754
        """

        _infos = [
            ("Identifier                 ", "*IDN?"),
            ("Com level                  ", "CCL?"),
            ("Real Position              ", "POS? 1"),
            ("Setpoint Position          ", "MOV? 1"),
            ("Position low limit         ", "SPA? 1 0X07000000"),
            ("Position High limit        ", "SPA? 1 0X07000001"),
            ("Velocity                   ", "VEL? 1"),
            ("On target                  ", "ONT? 1"),
            ("Target tolerance           ", "SPA? 1 0X07000900"),
            ("Settling time              ", "SPA? 1 0X07000901"),
            ("Sensor Offset              ", "SPA? 1 0X02000200"),
            ("Sensor Gain                ", "SPA? 1 0X02000300"),
            ("Closed loop status         ", "SVO? 1"),
            ("Auto Zero Calibration ?    ", "ATZ? 1"),
            ("Analog input setpoint      ", "AOS? 1"),
            ("Voltage Low Limit          ", "SPA? 1 0X07000A00"),
            ("Voltage High Limit         ", "SPA? 1 0X07000A01"),
        ]

        if self.model == "E-753":
            _infos.append(("Firmware name              ", "SEP? 1 0xffff0007"))
            _infos.append(("Firmware version           ", "SEP? 1 0xffff0008"))
            _infos.append(("Firmware description       ", "SEP? 1 0xffff000d"))
            _infos.append(("Firmware date              ", "SEP? 1 0xffff000e"))
            _infos.append(("Firmware developer         ", "SEP? 1 0xffff000f"))

        (error_nb, err_str) = self.get_error()
        _txt = '      ERR nb=%d  : "%s"\n' % (error_nb, err_str)

        # Reads pre-defined infos (1-line answers only)
        for i in _infos:
            _ans = self.command(i[1])
            _txt += f"        {i[0]} {_ans} \n"

        # Reads multi-lines infos.

        # IFC
        _ans = [bs.decode() for bs in self.sock.write_readlines(b"IFC?\n", 5)]
        _txt = _txt + "        %s    \n%s\n" % (
            "Communication parameters",
            "\n".join(_ans),
        )

        if self.model == "E-753":
            _tad_nb_lines = 2
            _tsp_nb_lines = 2
        elif self.model == "E-754":
            _tad_nb_lines = 3
            _tsp_nb_lines = 3

        # TSP
        _ans = [
            bs.decode() for bs in self.sock.write_readlines(b"TSP?\n", _tsp_nb_lines)
        ]
        _txt = _txt + "        %s    \n%s\n" % ("Analog setpoints", "\n".join(_ans))

        # TAD
        _ans = [
            bs.decode() for bs in self.sock.write_readlines(b"TAD?\n", _tad_nb_lines)
        ]
        _txt = _txt + "        %s    \n%s\n" % (
            "ADC value of analog input",
            "\n".join(_ans),
        )

        # ###  TAD[1]==131071  => broken cable ??
        # 131071 = pow(2,17)-1

        return _txt

    @object_method
    def start_wave(
        self, axis, wavetype, offset, amplitude, nb_cycles, wavelen, wait=True
    ):
        """
        Start a simple wav trajectory,
        -- wavetype can be LIN for a Linear  or
           SIN for a sinusoidal.
        -- offset: 
        -- amplitude motor displacement
        -- nb_cycles the number of time the motion is repeated.
        -- wavelen the time in second that should last the motion
        -- wait if you want to wait the end of the motion
        """

        # check wavetype can be "LIN" or "SIN"
        if wavetype not in ("LIN", "SIN"):
            raise ValueError('wavetype can only be "SIN" or "LIN"')

        offset *= axis.steps_per_unit
        amplitude *= axis.steps_per_unit
        servo_cycle = float(self.command("SPA? 1 0xe000200"))
        number_of_points = int(self.command("SPA? 1 0x13000004"))
        freq_faction = int(numpy.ceil((wavelen / number_of_points) / servo_cycle))
        wavelen = round(wavelen / (servo_cycle * freq_faction))

        if wavetype == "SIN":
            if amplitude < 0:  # cycle starting from max
                cmd = b"WAV 1 X SIN_P %d %d %d %d %d %d" % (
                    wavelen,
                    -amplitude,
                    offset - amplitude,
                    wavelen,
                    0,
                    (0.5 * wavelen),
                )
            else:
                cmd = b"WAV 1 X SIN_P %d %f %f %d %d %d" % (
                    wavelen,
                    +amplitude,
                    offset - amplitude / 2,
                    wavelen,
                    0,
                    (0.5 * wavelen),
                )
        else:
            cmd = b"WAV 1 X LIN %d %d %d %d %d %d" % (
                wavelen,
                amplitude,
                offset,
                wavelen,
                0,
                2,
            )

        if not axis._is_cache_position_disable:
            # This to be able to read the position
            # during the trajectory
            axis.settings.disable_cache("position")
        if not axis._is_cache_state_disable:
            axis.settings.disable_cache("state")
        commands = [
            b"WSL 1 1\n",
            cmd + b"\n",
            b"WTR 0 %d 1\n" % freq_faction,
            b"WGC 1 %d\n" % nb_cycles,
            b"WGO 1 1\n",
            b"ERR?\n",
        ]

        err = self.sock.write_readline(b"".join(commands))
        log_debug(self, "Error code %s", err)

        if wait:
            try:
                while self.state(axis) == AxisState("MOVING"):
                    gevent.sleep(0.1)
            except:
                self.stop_wave(axis)
                raise

    @object_method
    def stop_wave(self, axis):
        try:
            self.sock.write(b"WGO 1 0\n")
        finally:
            if not axis._is_cache_position_disable:
                axis.settings.disable_cache("position", flag=False)
            if not axis._is_cache_state_disable:
                axis.settings.disable_cache("state", flag=False)


class Axis(axis_module.Axis):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.channel = 1
        self._is_cache_position_disable = "position" in self.settings._disabled_settings
        self._is_cache_state_disable = "state" in self.settings._disabled_settings

    @contextlib.contextmanager
    @axis_module.lazy_init
    def run_wave(self, wavetype, offset, amplitude, nb_cycles, wavelen):
        """
        Helper to run a wave (trajectory) during a scan or something like this.
        And stop the trajectory at the end
        """
        self.controller.start_wave(
            self, wavetype, offset, amplitude, nb_cycles, wavelen, wait=False
        )
        try:
            yield
        finally:
            self.controller.stop_wave(self)

    def start_wave(self, wavetype, offset, amplitude, nb_cycles, wavelen, wait=False):
        self.controller.start_wave(
            self, wavetype, offset, amplitude, nb_cycles, wavelen, wait=wait
        )

    def stop_wave(self):
        self.controller.stop_wave(self)
