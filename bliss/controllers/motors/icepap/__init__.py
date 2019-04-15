# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2017 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import re
import time
import gevent
import hashlib
import functools
from bliss.common.greenlet_utils import protect_from_kill
from bliss.config.channels import Cache
from bliss.controllers.motor import Controller
from bliss.common.axis import AxisState, Axis
from bliss.common.utils import object_method
from bliss.common import mapping
from bliss.common.logtools import LogMixin
from bliss.comm.tcp import Command
import struct
import numpy
import sys


def _object_method_filter(obj):
    if isinstance(obj, (LinkedAxis, TrajectoryAxis)):
        return False
    return True


class Icepap(Controller, LogMixin):
    """
    IcePAP stepper controller without Deep Technology of Communication.
    But if you prefer to have it (DTC) move to IcePAP controller class.
    Use this class controller at your own risk, because you won't
    have any support...
    """

    STATUS_DISCODE = {
        0: ("POWERENA", "power enabled"),
        1: ("NOTACTIVE", "axis configured as not active"),
        2: ("ALARM", "alarm condition"),
        3: ("REMRACKDIS", "remote rack disable input signal"),
        4: ("LOCRACKDIS", "local rack disable switch"),
        5: ("REMAXISDIS", "remote axis disable input signal"),
        6: ("LOCAXISDIS", "local axis disable switch"),
        7: ("SOFTDIS", "software disable"),
    }

    STATUS_MODCODE = {
        0: ("OPER", "operation mode"),
        1: ("PROG", "programmation mode"),
        2: ("TEST", "test mode"),
        3: ("FAIL", "fail mode"),
    }
    STATUS_STOPCODE = {
        0: ("SCEOM", "end of movement"),
        1: ("SCSTOP", "last motion was stopped"),
        2: ("SCABORT", "last motion was aborted"),
        3: ("SCLIMPOS", "positive limitswitch reached"),
        4: ("SCLINNEG", "negative limitswitch reached"),
        5: ("SCSETTLINGTO", "settling timeout"),
        6: ("SCAXISDIS", "axis disabled (no alarm)"),
        7: ("SCBIT7", "n/a"),
        8: ("SCINTFAIL", "internal failure"),
        9: ("SCMOTFAIL", "motor failure"),
        10: ("SCPOWEROVL", "power overload"),
        11: ("SCHEATOVL", "driver overheating"),
        12: ("SCCLERROR", "closed loop error"),
        13: ("SCCENCERROR", "control encoder error"),
        14: ("SCBIT14", "n/a"),
        15: ("SCEXTALARM", "external alarm"),
    }

    def __init__(self, *args, **kwargs):
        Controller.__init__(self, *args, **kwargs)
        self._cnx = None
        self._last_axis_power_time = dict()
        mapping.register(self, parents_list=["devices"])

    def initialize(self):
        hostname = self.config.get("host")
        self._cnx = Command(hostname, 5000, eol="\n")
        mapping.register(self, children_list=[self._cnx], parents_list=["devices"])

        self._icestate = AxisState()
        self._icestate.create_state("POWEROFF", "motor power is off")
        self._icestate.create_state("HOMEFOUND", "home signal found")
        self._icestate.create_state("HOMENOTFOUND", "home signal not found")
        for codes in (self.STATUS_DISCODE, self.STATUS_MODCODE, self.STATUS_STOPCODE):
            for state, desc in codes.values():
                self._icestate.create_state(state, desc)

    def close(self):
        if self._cnx is not None:
            self._cnx.close()

    def initialize_axis(self, axis):
        if not isinstance(axis, TrajectoryAxis):
            axis.address = axis.config.get("address", lambda x: x)
            axis._trajectory_cache = Cache(axis, "trajectory_cache")

        if hasattr(axis, "_init_software"):
            axis._init_software()

    def initialize_hardware_axis(self, axis):
        if axis.config.get("autopower", converter=bool, default=True):
            try:
                self.set_on(axis)
            except:
                sys.excepthook(*sys.exc_info())

        if hasattr(axis, "_init_hardware"):
            axis._init_hardware()

    # Axis power management
    def set_on(self, axis):
        """
        Put the axis power on
        """
        try:
            self._power(axis, True)
        except Exception as e:
            raise type(e)("Axis '%s`: %s" % (axis.name, e.message))

    def set_off(self, axis):
        """
        Put the axis power off
        """
        self._power(axis, False)

    def _power(self, axis, power):
        if isinstance(axis, TrajectoryAxis):
            return

        _ackcommand(self._cnx, "POWER %s %s" % ("ON" if power else "OFF", axis.address))
        self._last_axis_power_time[axis] = time.time()

    def read_position(self, axis, cache=True):
        if isinstance(axis, TrajectoryAxis):
            return axis._read_position()

        pos_cmd = "FPOS" if cache else "POS"
        return int(_command(self._cnx, "?%s %s" % (pos_cmd, axis.address)))

    def set_position(self, axis, new_pos):
        if isinstance(axis, NoSettingsAxis):
            pre_cmd = "%d:DISPROT LINKED;" % axis.address
        else:
            pre_cmd = None
        _ackcommand(
            self._cnx,
            "POS %s %d" % (axis.address, int(round(new_pos))),
            pre_cmd=pre_cmd,
        )
        return self.read_position(axis, cache=False)

    def read_velocity(self, axis):
        if isinstance(axis, TrajectoryAxis):
            return axis._get_velocity()

        return float(_command(self._cnx, "?VELOCITY %s" % axis.address))

    def set_velocity(self, axis, new_velocity):
        if isinstance(axis, TrajectoryAxis):
            return axis._set_velocity(new_velocity)
        current_acc_time = axis.acctime
        current_acc = float(axis.acceleration)
        future_acc_time = new_velocity / (current_acc * axis.steps_per_unit)
        try:
            _command(self._cnx, "ACCTIME %s %f" % (axis.address, future_acc_time))
            _ackcommand(self._cnx, "VELOCITY %s %f" % (axis.address, new_velocity))
        except:
            future_acc_time = current_acc_time
            raise
        finally:
            _command(self._cnx, "ACCTIME %s %f" % (axis.address, future_acc_time))

        return self.read_velocity(axis)

    def read_acceleration(self, axis):
        if isinstance(axis, TrajectoryAxis):
            acctime = axis._get_acceleration_time()
        else:
            acctime = float(_command(self._cnx, "?ACCTIME %s" % axis.address))
        velocity = self.read_velocity(axis)
        return velocity / float(acctime)

    def set_acceleration(self, axis, new_acc):
        velocity = self.read_velocity(axis)
        new_acctime = velocity / new_acc

        if isinstance(axis, TrajectoryAxis):
            return axis._set_acceleration_time(new_acctime)

        _ackcommand(self._cnx, "ACCTIME %s %f" % (axis.address, new_acctime))
        return self.read_acceleration(axis)

    def state(self, axis):
        if isinstance(axis, TrajectoryAxis):
            status = axis._state()
        else:
            last_power_time = self._last_axis_power_time.get(axis, 0)
            if time.time() - last_power_time < 1.0 and not isinstance(axis, LinkedAxis):
                status = int(_command(self._cnx, "%s:?STATUS" % axis.address), 16)
            else:
                self._last_axis_power_time.pop(axis, None)
                status = int(_command(self._cnx, "?FSTATUS %s" % axis.address), 16)
        status ^= 1 << 23  # neg POWERON FLAG
        state = self._icestate.new()
        for mask, value in (
            ((1 << 9), "READY"),
            ((1 << 10 | 1 << 11), "MOVING"),
            ((1 << 18), "LIMPOS"),
            ((1 << 19), "LIMNEG"),
            ((1 << 20), "HOME"),
            ((1 << 23), "POWEROFF"),
        ):
            if status & mask:
                state.set(value)

        state_mode = (status >> 2) & 0x3
        if state_mode:
            state.set(self.STATUS_MODCODE.get(state_mode)[0])

        stop_code = (status >> 14) & 0xf
        if stop_code:
            state.set(self.STATUS_STOPCODE.get(stop_code)[0])

        disable_condition = (status >> 4) & 0x7
        if disable_condition:
            state.set(self.STATUS_DISCODE.get(disable_condition)[0])

        if state.READY:
            # if motor is ready then no need to investigate deeper
            return state

        if not (stop_code != 7 and stop_code != 14 and stop_code):
            state.set("MOVING")

        if not state.MOVING:
            # it seems it is not safe to call warning and/or alarm commands
            # while homing motor, so let's not ask if motor is moving
            if status & (1 << 13):
                try:
                    warning = _command(self._cnx, "%d:?WARNING" % axis.address)
                except (TypeError, AttributeError):
                    pass
                else:
                    warn_str = "Axis %s warning condition: \n" % axis.name
                    warn_str += warning
                    state.create_state("WARNING", warn_str)
                    state.set("WARNING")

            try:
                alarm = _command(self._cnx, "%d:?ALARM" % axis.address)
            except (RuntimeError, TypeError, AttributeError):
                pass
            else:
                if alarm != "NO":
                    alarm_dsc = "alarm condition: " + str(alarm)
                    state.create_state("ALARMDESC", alarm_dsc)
                    state.set("ALARMDESC")

        return state

    def get_info(self, axis):
        pre_cmd = "%s:" % axis.address
        r = "MOTOR   : %s\n" % axis.name
        r += "SYSTEM  : %s (ID: %s) (VER: %s)\n" % (
            self._cnx._host,
            _command(self._cnx, "0:?ID"),
            _command(self._cnx, "?VER"),
        )
        r += "DRIVER  : %s\n" % axis.address
        r += "POWER   : %s\n" % _command(self._cnx, pre_cmd + "?POWER")
        r += "CLOOP   : %s\n" % _command(self._cnx, pre_cmd + "?PCLOOP")
        r += "WARNING : %s\n" % _command(self._cnx, pre_cmd + "?WARNING")
        r += "ALARM   : %s\n" % _command(self._cnx, pre_cmd + "?ALARM")
        return r

    def raw_write(self, message, data=None):
        return _command(self._cnx, message, data)

    def raw_write_read(self, message, data=None):
        return _ackcommand(self._cnx, message, data)

    def prepare_move(self, motion):
        pass

    def start_one(self, motion):
        if isinstance(motion.axis, TrajectoryAxis):
            return motion.axis._start_one(motion)
        elif isinstance(motion.axis, NoSettingsAxis):
            pre_cmd = "%d:DISPROT LINKED;" % motion.axis.address
        else:
            pre_cmd = None

        _ackcommand(
            self._cnx,
            "MOVE %s %d" % (motion.axis.address, (motion.target_pos + 0.5)),
            pre_cmd=pre_cmd,
        )

    def start_all(self, *motions):
        if len(motions) > 1:
            cmd = "MOVE GROUP "
            cmd += " ".join(
                ["%s %d" % (m.axis.address, (m.target_pos + 0.5)) for m in motions]
            )
            _ackcommand(self._cnx, cmd)
        elif motions:
            self.start_one(motions[0])

    def stop(self, axis):
        if isinstance(axis, TrajectoryAxis):
            return axis._stop()
        else:
            _command(self._cnx, "STOP %s" % axis.address)

    def stop_all(self, *motions):
        if len(motions) > 1:
            axes_addr = " ".join("%s" % m.axis.address for m in motions)
            _command(self._cnx, "STOP %s" % axes_addr)
        else:
            self.stop(motions[0].axis)

    def home_search(self, axis, switch):
        cmd = "HOME " + ("+1" if switch > 0 else "-1")
        _ackcommand(self._cnx, "%s:%s" % (axis.address, cmd))
        # IcePAP status is not immediately MOVING after home search command is sent
        gevent.sleep(0.2)

    def home_state(self, axis):
        home_state = _command(self._cnx, "%s:?HOMESTAT" % axis.address)
        s = self._icestate.new()
        if home_state.startswith("MOVING"):
            s.set("MOVING")
        else:
            s.set("READY")
            if home_state.startswith("FOUND"):
                s.set("HOMEFOUND")
            else:
                s.set("HOMENOTFOUND")
        return s

    def limit_search(self, axis, limit):
        cmd = "SRCH LIM" + ("+" if limit > 0 else "-")
        _ackcommand(self._cnx, "%s:%s" % (axis.address, cmd))
        # TODO: MG18Nov14: remove this sleep (state is not immediately MOVING)
        gevent.sleep(0.1)

    def initialize_encoder(self, encoder):
        # Get axis config from bliss config
        # address form is XY : X=rack {0..?} Y=driver {1..8}
        encoder.address = encoder.config.get("address", int)

        # Get optional encoder input to read
        enctype = encoder.config.get("type", str, "ENCIN").upper()
        # Minium check on encoder input
        if enctype not in ["ENCIN", "ABSENC", "INPOS", "MOTOR", "AXIS", "SYNC"]:
            raise ValueError("Invalid encoder type")
        encoder.enctype = enctype

    def read_encoder(self, encoder):
        value = _command(self._cnx, "?ENC %s %d" % (encoder.enctype, encoder.address))
        return int(value)

    def set_encoder(self, encoder, steps):
        _ackcommand(
            self._cnx, "ENC %s %d %d" % (encoder.enctype, encoder.address, steps)
        )

    def set_event_positions(self, axis_or_encoder, positions):
        int_position = numpy.array(positions, dtype=numpy.int32)
        # position has to be ordered
        int_position.sort()
        address = axis_or_encoder.address
        if not len(int_position):
            _ackcommand(self._cnx, "%s:ECAMDAT CLEAR" % address)
            return

        if isinstance(axis_or_encoder, Axis):
            source = "AXIS"
        else:  # encoder
            source = "MEASURE"

        # load trigger positions
        _ackcommand(self._cnx, "%s:*ECAMDAT %s DWORD" % (address, source), int_position)
        # send the trigger on the multiplexer
        _ackcommand(self._cnx, "%s:SYNCAUX eCAM" % address)

    def get_event_positions(self, axis_or_encoder):
        """
        For this controller this method should be use
        for debugging purposed only...
        """
        address = axis_or_encoder.address
        # Get the number of positions
        reply = _command(self._cnx, "%d:?ECAMDAT" % address)
        reply_exp = re.compile(r"(\w+) +([+-]?\d+) +([+-]?\d+) +(\d+)")
        m = reply_exp.match(reply)
        if m is None:
            raise RuntimeError("Reply Didn't expected: %s" % reply)
        source = m.group(1)
        nb = int(m.group(4))

        if isinstance(axis_or_encoder, Axis):
            nb = nb if source == "AXIS" else 0
        else:  # encoder
            nb = nb if source == "MEASURE" else 0

        positions = numpy.zeros((nb,), dtype=numpy.int32)
        if nb > 0:
            reply_exp = re.compile(r".+: +([+-]?\d+)")
            reply = _command(self._cnx, "%d:?ECAMDAT %d" % (address, nb))
            for i, line in enumerate(reply.split("\n")):
                m = reply_exp.match(line)
                if m:
                    pos = int(m.group(1))
                    positions[i] = pos
        return positions

    def get_linked_axis(self):
        reply = _command(self._cnx, "?LINKED")
        linked = dict()
        for line in reply.strip().split("\n"):
            values = line.split()
            linked[values[0]] = [int(x) for x in values[1:]]
        return linked

    def has_trajectory(self):
        return True

    def prepare_trajectory(self, *trajectories):
        if not trajectories:
            raise ValueError("no trajectory provided")

        update_cache = list()
        data = numpy.array([], dtype=numpy.int8)
        for traj in trajectories:
            pvt = traj.pvt
            axis = traj.axis
            axis_data = _vdata_header(pvt["position"], axis, POSITION)
            axis_data = numpy.append(
                axis_data, _vdata_header(pvt["time"], axis, PARAMETER)
            )
            axis_data = numpy.append(
                axis_data, _vdata_header(pvt["velocity"], axis, SLOPE)
            )
            h = hashlib.md5()
            h.update(axis_data.tobytes())
            digest = h.hexdigest()
            if axis._trajectory_cache.value != digest:
                data = numpy.append(data, axis_data)
                update_cache.append((axis._trajectory_cache, digest))

        if not data.size:  # nothing to do
            return

        _command(self._cnx, "#*PARDAT", data=data)
        # update axis trajectory cache
        for cache, value in update_cache:
            cache.value = value

        axes_str = " ".join(("%s" % traj.axis.address for traj in trajectories))
        _command(self._cnx, "#PARVEL 1 %s" % axes_str)
        _command(self._cnx, "#PARACCT 0 {}".format(axes_str))

    def move_to_trajectory(self, *trajectories):
        axes_str = " ".join(("%s" % traj.axis.address for traj in trajectories))
        # Doesn't work yet
        # _command(self._cnx,"#MOVEP 0 GROUP %s" % axes_str)
        _command(self._cnx, "#MOVEP 0 %s" % axes_str)

    def start_trajectory(self, *trajectories):
        axes_str = " ".join(("%s" % traj.axis.address for traj in trajectories))
        traj1 = trajectories[0]
        endtime = traj1.pvt["time"][-1]
        # Doesn't work yet
        # _command(self._cnx,"#PMOVE %lf GROUP %s" % (endtime,axes_str))
        _command(self._cnx, "#PMOVE {} {}".format(endtime, axes_str))

    def stop_trajectory(self, *trajectories):
        axes_str = " ".join(("%s" % traj.axis.address for traj in trajectories))
        _command(self._cnx, "STOP %s" % axes_str)

    @object_method(types_info=("bool", "bool"), filter=_object_method_filter)
    def activate_closed_loop(self, axis, active):
        _command(self._cnx, "#%s:PCLOOP %s" % (axis.address, "ON" if active else "OFF"))
        return active

    @object_method(types_info=("None", "bool"), filter=_object_method_filter)
    def is_closed_loop_activate(self, axis):
        return (
            True if _command(self._cnx, "%s:?PCLOOP" % axis.address) == "ON" else False
        )

    @object_method(types_info=("None", "None"), filter=_object_method_filter)
    def reset_closed_loop(self, axis):
        measure_position = int(_command(self._cnx, "%s:?POS MEASURE" % axis.address))
        self.set_position(axis, measure_position)
        if axis.config.get("autopower", converter=bool, default=True):
            self.set_on(axis)
        axis.sync_hard()

    @object_method(types_info=("None", "int"), filter=_object_method_filter)
    def temperature(self, axis):
        return int(_command(self._cnx, "%s:?MEAS T" % axis.address))

    @object_method(types_info=(("float", "bool"), "None"), filter=_object_method_filter)
    def set_tracking_positions(self, axis, positions, cyclic=False):
        """
        Send position to the controller which will be tracked.

        positions --  are expressed in user unit
        cyclic -- cyclic position or not default False

        @see activate_track method
        """
        address = axis.address
        if not len(positions):
            _ackcommand(self._cnx, "%s:LISTDAT CLEAR" % address)
            return

        dial_positions = axis.user2dial(numpy.array(positions, dtype=numpy.float))
        step_positions = numpy.array(
            dial_positions * axis.steps_per_unit, dtype=numpy.int32
        )
        _ackcommand(
            self._cnx,
            "%d:*LISTDAT %s DWORD" % (address, "CYCLIC" if cyclic else "NOCYCLIC"),
            step_positions,
        )

    @object_method(types_info=("None", ("float", "bool")), filter=_object_method_filter)
    def get_tracking_positions(self, axis):
        """
        Get the tacking positions.
        This method should only be use for debugging
        return a tuple with (positions,cyclic flag)
        """
        address = axis.address
        # Get the number of positions
        reply = _command(self._cnx, "%d:?LISTDAT" % address)
        reply_exp = re.compile(r"(\d+) *(\w+)?")
        m = reply_exp.match(reply)
        if m is None:
            raise RuntimeError("Reply didn't expected: %s" % reply)
        nb = int(m.group(1))
        positions = numpy.zeros((nb,), dtype=numpy.int32)
        cyclic = True if m.group(2) == "CYCLIC" else False
        if nb > 0:
            reply_exp = re.compile(r".+: +([+-]?\d+)")
            reply = _command(self._cnx, "%d:?LISTDAT %d" % (address, nb))
            for i, line in enumerate(reply.split("\n")):
                m = reply_exp.match(line)
                if m:
                    pos = int(m.group(1))
                    positions[i] = pos
            dial_positions = positions / axis.steps_per_unit
            positions = axis.dial2user(dial_positions)
        return positions, cyclic

    @object_method(types_info=(("bool", "str"), "None"), filter=_object_method_filter)
    def activate_tracking(self, axis, activate, mode=None):
        """
        Activate/Deactivate the tracking position depending on
        activate flag
        mode -- default "INPOS" if None.
        mode can be :
           - SYNC   -> Internal SYNC signal
           - ENCIN  -> ENCIN signal
           - INPOS  -> INPOS signal
           - ABSENC -> ABSENC signal
        """
        address = axis.address

        if not activate:
            _ackcommand(self._cnx, "STOP %d" % address)
            axis.sync_hard()
        else:
            if mode is None:
                mode = "INPOS"
            possibles_modes = ["SYNC", "ENCIN", "INPOS", "ABSENC"]
            if mode not in possibles_modes:
                raise ValueError(
                    "mode %s is not managed, can only choose %s"
                    % (mode, possibles_modes)
                )
            if mode == "INPOS":
                _ackcommand(self._cnx, "%d:POS INPOS 0" % address)
            _ackcommand(self._cnx, "%d:LTRACK %s" % (address, mode))

    @object_method(types_info=("float", "None"), filter=_object_method_filter)
    def blink(self, axis, second=3.):
        """
        Blink axis driver
        """
        _command(self._cnx, "%d:BLINK %f" % (axis.address, second))

    def reset(self):
        _command(self._cnx, "RESET")

    def mdspreset(self):
        """
        Reset the MASTER DSP
        """
        _command(self._cnx, "_dsprst")

    def reboot(self):
        _command(self._cnx, "REBOOT")
        self._cnx.close()


_check_reply = re.compile(r"^[#?]|^[0-9]+:\?")
PARAMETER, POSITION, SLOPE = (0x1000, 0x2000, 0x4000)


def _vdata_header(data, axis, vdata_type):
    PARDATA_HEADER_FORMAT = "<HBBLLBBHd"
    numpydtype_2_dtype = {
        numpy.dtype(numpy.int8): 0x00,
        numpy.dtype(numpy.int16): 0x01,
        numpy.dtype(numpy.int32): 0x02,
        numpy.dtype(numpy.int64): 0x03,
        numpy.dtype(numpy.float32): 0x04,
        numpy.dtype(numpy.float64): 0x05,
        numpy.dtype(numpy.uint8): 0x10,
        numpy.dtype(numpy.uint16): 0x11,
        numpy.dtype(numpy.uint32): 0x12,
        numpy.dtype(numpy.uint64): 0x13,
    }
    if not data.size:
        raise RuntimeError("Nothing to send")
    elif len(data) > 0xFFFF:
        raise ValueError("too many data values, max: 0xFFFF")

    dtype = numpydtype_2_dtype[data.dtype]
    data_test = data.newbyteorder("<")
    if data_test[0] != data[0]:  # not good endianness
        data = data.byteswap()

    header_size = struct.calcsize(PARDATA_HEADER_FORMAT)
    full_size = header_size + len(data.tostring())
    aligned_full_size = (full_size + 3) & ~3  # alignment 32 bits
    flags = vdata_type | axis.address
    bin_header = struct.pack(
        PARDATA_HEADER_FORMAT,
        0xCAFE,  # vdata signature
        0,  # Version = 0
        header_size // 4,  # Data offset in dwords
        aligned_full_size // 4,  # Full vector size in dwords
        len(data),  # number of values in the vector
        dtype,  # Data type
        0,  # no compression
        flags,  # format + address
        0,
    )  # first data value for incremental coding
    return numpy.fromstring(
        bin_header + data.tostring() + b"\0" * (aligned_full_size - full_size),
        dtype=numpy.int8,
    )


@protect_from_kill
def _command(cnx, cmd, data=None, pre_cmd=None):
    reply_flag = _check_reply.match(cmd)
    cmd = cmd.encode()
    if data is not None:
        uint16_view = data.view(dtype=numpy.uint16)
        data_checksum = uint16_view.sum()
        header = struct.pack(
            "<III",
            0xa5aa555a,  # Header key
            len(uint16_view),
            int(data_checksum) & 0xffffffff,
        )

        data_test = data.newbyteorder("<")
        if len(data_test) and data_test[0] != data[0]:  # not good endianness
            data = data.byteswap()

        full_cmd = b"%s\n%s%s" % (cmd, header, data.tostring())
        transaction = cnx._write(full_cmd)
    else:
        if pre_cmd:
            full_cmd = b"%s%s\n" % (pre_cmd.encode(), cmd)
        else:
            full_cmd = b"%s\n" % cmd
        transaction = cnx._write(full_cmd)
    with cnx.Transaction(cnx, transaction):
        if reply_flag:
            msg = cnx._readline(transaction=transaction, clear_transaction=False)
            cmd = cmd.strip(b"#").split(b" ")[0]
            msg = msg.replace(cmd + b" ", b"")
            if msg.startswith(b"$"):
                msg = cnx._readline(
                    transaction=transaction, clear_transaction=False, eol=b"$\n"
                )
            elif msg.startswith(b"ERROR"):
                raise RuntimeError(msg.replace(b"ERROR ", b"").decode())
            elif msg.startswith(b"?*"):
                # a binary reply
                header = cnx._read(transaction, size=12, clear_transaction=False)
                dfmt, magic, size, checksum = struct.unpack("<HHII", header)
                assert magic == 0xa5a5
                dsize = dfmt & 0xF  # data size (bytes)
                data = cnx._read(
                    transaction, size=dsize * size, clear_transaction=False
                )
                return numpy.fromstring(data, dtype="u{0}".format(dsize))
            return msg.strip(b" ").decode()


def _ackcommand(cnx, cmd, data=None, pre_cmd=None):
    if not cmd.startswith("#") and not cmd.startswith("?"):
        cmd = "#" + cmd
    return _command(cnx, cmd, data, pre_cmd)


from .shutter import Shutter
from .switch import Switch
from .linked import LinkedAxis, NoSettingsAxis
from .trajectory import TrajectoryAxis
