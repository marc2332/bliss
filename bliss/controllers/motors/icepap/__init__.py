# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import re
import time
import math
import gevent
import weakref
import hashlib
from collections import namedtuple
from bliss.config.channels import Cache
from bliss.controllers.motor import Controller
from bliss.common.axis import AxisState, Axis
from bliss.common.utils import object_method
from bliss import global_map
from bliss.comm.tcp import Command
from bliss.comm.exceptions import CommunicationError
import numpy
import sys
from bliss.controllers.motors.icepap.comm import _command, _ackcommand, _vdata_header
from bliss.controllers.motors.icepap.linked import LinkedAxis
from bliss.common.logtools import log_warning

# next imports are needed by the emotion plugin
from bliss.common.encoder import Encoder as BaseEncoder
from bliss.controllers.motors.icepap.shutter import Shutter
from bliss.controllers.motors.icepap.switch import Switch

#
from bliss.controllers.motors.icepap.trajectory import (
    TrajectoryAxis,
    PARAMETER,
    POSITION,
    SLOPE,
)


def _object_method_filter(obj):
    if isinstance(obj, (LinkedAxis, TrajectoryAxis)):
        return False
    return True


class Encoder(BaseEncoder):
    @property
    def address(self):
        # address form is XY : X=rack {0..?} Y=driver {1..8}
        return self.config.get("address", int)

    @property
    def enctype(self):
        # Get optional encoder input to read
        enctype = self.config.get("type", str, "ENCIN").upper()
        # Minium check on encoder input
        if enctype not in ["ENCIN", "ABSENC", "INPOS", "MOTOR", "AXIS", "SYNC"]:
            raise ValueError("Invalid encoder type")
        return enctype


class Icepap(Controller):
    """
    IcePAP stepper controller 
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
        hostname = self.config.get("host")
        self._cnx = Command(hostname, 5000, eol="\n")
        global_map.register(self, children_list=[self._cnx])

        # Timestamps of last power command (ON or OFF) for each axis.
        self._last_axis_power_time = {}
        self._limit_search_in_progress = weakref.WeakKeyDictionary()

    def initialize(self):
        self._icestate = AxisState()
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
            axis.address = axis.config.get("address", converter=None)
            axis._trajectory_cache = Cache(axis, "trajectory_cache")

        if hasattr(axis, "_init_software"):
            axis._init_software()

    def initialize_hardware_axis(self, axis):
        if axis.config.get("autopower", converter=bool, default=True):
            try:
                self.set_on(axis)
            except:
                # display error message only if autopower is explicitly in config
                if axis.config.get("autopower", converter=bool, default=False):
                    sys.excepthook(*sys.exc_info())
                axis._update_settings(AxisState(("DISABLED", "OFF")))

        if hasattr(axis, "_init_hardware"):
            axis._init_hardware()

    def steps_position_precision(self, axis):
        """
        IcePap axes are working in steps but traj in float.
        """
        if isinstance(axis, TrajectoryAxis):
            return axis.config.config_dict.get("precision", 1e-6)
        return axis.config.config_dict.get("precision", 1)

    # Axis power management
    def set_on(self, axis):
        """
        Put the axis power on
        """
        try:
            self._power(axis, True)
        except Exception as e:
            raise type(e)("Axis '%s`: %s" % (axis.name, str(e)))

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
        if isinstance(axis, TrajectoryAxis):
            raise NotImplementedError
        if isinstance(axis, LinkedAxis.Real):
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
        except CommunicationError:
            raise
        except BaseException:
            # ensure acctime is set to the previous value
            _command(self._cnx, "ACCTIME %s %f" % (axis.address, current_acc_time))
            raise
        else:
            try:
                _ackcommand(self._cnx, "VELOCITY %s %f" % (axis.address, new_velocity))
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
            # ?STATUS: Query multiple board status.
            # ?FSTATUS: Query multiple board FAST status.

            # (From icepap doc)
            # ?STATUS Returns the current status words of the specified boards
            # as 32-bit values in C-like hexadecimal notation.  Note that in the
            # cases of very frequent status polling, the ?FSTATUS query may be
            # preferred to ?STATUS as ?FSTATUS returns values stored in the
            # system controller and therefore benefits from shorter execution
            # latency. ?STATUS on the other hand returns the status information
            # stored in the boards and therefore guarantees more up to date
            # values.
            # ?FSTATUS is a system query that is managed exclusively by the
            # master system controller. ?FSTATUS returns values stored in the
            # system controller that are updated every time that any bit in the
            # status word of a board changes. The ?FSTATUS query is intended to
            # be used for frequent polling from the control host, as it is
            # faster as it presents less latency than ?STATUS, and it does not
            # load the internal communication bus.

            # If power has been switched ON or OFF less than 1 second ago, use STATUS
            # instead of FSTATUS to avoid reading an invalid cache (T.C.?)
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
            ((1 << 23), "OFF"),
        ):
            if status & mask:
                state.set(value)

        # MODE bits: 2-3
        state_mode = (status >> 2) & 0x3
        if state_mode:
            state.set(self.STATUS_MODCODE.get(state_mode)[0])

        # DISABLE bits: 4-6
        disable_condition = (status >> 4) & 0x7
        if disable_condition:
            state.set(self.STATUS_DISCODE.get(disable_condition)[0])

        stop_code = (status >> 14) & 0xF

        if state.READY:
            # important: stopcode for error cond. has to be examinated when axis is READY only!
            # STOPCODE bits: 14-17
            if stop_code:
                sc_status = self.STATUS_STOPCODE.get(stop_code)[0]
                state.set(sc_status)
                if sc_status == "SCSETTLINGTO":
                    log_warning(self, "Closed loop error: settling timeout")
                    return state
                if sc_status not in ("SCEOM", "SCSTOP", "SCABORT"):
                    in_limit_search = self._limit_search_in_progress.get(axis, 0)
                    if in_limit_search > 0 and sc_status == "SCLIMPOS":
                        # do not put FAULT state, since we reached the limit we wanted
                        return state
                    elif (
                        in_limit_search < 0 and sc_status == "SCLINNEG"
                    ):  # typo here, from icepap firmware
                        # do not put FAULT, since we reached the limit we wanted
                        return state
                    else:
                        # we have a limit hit, or a closed loop error etc. =>
                        # this will raise an exception, if it occurs during a move
                        state.set("FAULT")
            return state

        # This moving consideration is valid only if axis is ENABLED.
        if not disable_condition:
            # STOPCODE 7 and 14 are not affected.
            if stop_code != 7 and stop_code != 14 and stop_code:
                # there is a valid stop code -> not moving
                pass
            else:
                if not state.OFF:
                    # stop_code is 0 -> MOVING (needed for trajectories state)
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

    def get_axis_info(self, axis):
        pre_cmd = "%s:" % axis.address
        # info_str = "MOTOR   : %s\n" % axis.name
        info_str = "ICEPAP:\n"
        info_str += "     host: %s (ID: %s) (VER: %s)\n" % (
            self._cnx._host,
            _command(self._cnx, "0:?ID"),
            _command(self._cnx, "?VER"),
        )
        info_str += "     address: %s\n" % axis.address
        info_str += "     status:"
        info_str += f" POWER: {_command(self._cnx, pre_cmd + '?POWER')}"
        info_str += f"    CLOOP: {_command(self._cnx, pre_cmd + '?PCLOOP')}"
        info_str += f"    WARNING: {_command(self._cnx, pre_cmd + '?WARNING')}"
        info_str += f"    ALARM: {_command(self._cnx, pre_cmd + '?ALARM')}\n"

        info_str += f"     {self.read_encoder_all_types(axis)}\n"

        if isinstance(axis, LinkedAxis):
            info_str += "LINKED AXIS:\n"
            info_str += f"     {self.get_linked_axis()}\n"

        return info_str

    def __info__(self):
        """For CLI help.
        """
        info_str = "ICEPAP CONTROLLER:\n"
        info_str += f"     controller: {self._cnx._host}\n"
        info_str += f"     version: {_command(self._cnx, '?VER')}\n"

        return info_str

    def raw_write(self, message, data=None):
        return _command(self._cnx, message, data)

    def raw_write_read(self, message, data=None):
        return _ackcommand(self._cnx, message, data)

    def prepare_move(self, motion):
        pass

    def start_jog(self, axis, velocity, direction):
        self._limit_search_in_progress[axis] = 0
        _ackcommand(self._cnx, "JOG %s %d" % (axis.address, int(velocity * direction)))

    def start_one(self, motion):
        self._limit_search_in_progress[motion.axis] = 0
        if isinstance(motion.axis, TrajectoryAxis):
            return motion.axis._start_one(motion)
        elif isinstance(motion.axis, LinkedAxis.Real):
            pre_cmd = "%d:DISPROT LINKED;" % motion.axis.address
        else:
            pre_cmd = None

        _ackcommand(
            self._cnx,
            "MOVE %s %d" % (motion.axis.address, round(motion.target_pos)),
            pre_cmd=pre_cmd,
        )

    def start_all(self, *motions):
        if len(motions) > 1:
            for motion in motions:
                self._limit_search_in_progress[motion.axis] = 0
            cmd = "MOVE GROUP "
            cmd += " ".join(
                ["%s %d" % (m.axis.address, round(m.target_pos)) for m in motions]
            )
            _ackcommand(self._cnx, cmd)
        else:
            self.start_one(motions[0])

    def stop(self, axis):
        if isinstance(axis, TrajectoryAxis):
            return axis._stop()
        else:
            _command(self._cnx, "STOP %s" % axis.address)

    def stop_jog(self, axis):
        return self.stop(axis)

    def stop_all(self, *motions):
        if len(motions) > 1:
            axes_addr = " ".join("%s" % m.axis.address for m in motions)
            _command(self._cnx, "STOP %s" % axes_addr)
        else:
            self.stop(motions[0].axis)

    def home_search(self, axis, switch):
        self._limit_search_in_progress[axis] = 0
        home_src = self.home_source(axis)
        if home_src == "Lim+":
            home_dir = "+1"
        elif home_src == "Lim-":
            home_dir = "-1"
        else:
            if switch == 0:
                home_dir = "0"
            elif switch > 0:
                home_dir = "+1"
            else:
                home_dir = "-1"
        _ackcommand(self._cnx, "%s:HOME %s" % (axis.address, home_dir))
        # IcePAP status is not immediately MOVING after home search command is sent
        gevent.sleep(0.2)

    def home_state(self, axis):
        state = self.state(axis)
        if "MOVING" in state:
            return state
        home_state = _command(self._cnx, "%s:?HOMESTAT" % axis.address)
        if not home_state.startswith("FOUND"):
            raise RuntimeError("Home switch not found.")
        hs = self.home_source(axis)
        if hs == "Lim+" and home_state == "FOUND +1":
            state.unset("FAULT")
            state.unset("LIMPOS")
        elif hs == "Lim-" and home_state == "FOUND -1":
            state.unset("FAULT")
            state.unset("LIMNEG")
        return state

    @object_method(types_info=("None", "float"), filter=_object_method_filter)
    def home_found_dial(self, axis):
        if axis.config.get("read_position", str, "controller") == "encoder":
            enctype = axis.encoder.config.get("type", str, "ENCIN").upper()
            home_step = int(_command(self._cnx, f"{axis.address}:?HOMEPOS {enctype}"))
            return home_step / axis.encoder.steps_per_unit
        else:
            home_step = int(_command(self._cnx, f"{axis.address}:?HOMEPOS MEASURE"))
            return home_step / axis.steps_per_unit

    @object_method(types_info=("None", "str"), filter=_object_method_filter)
    def home_source(self, axis):
        home_src = _command(self._cnx, f"{axis.address}:?CFG HOMESRC")
        return home_src.split()[1]

    def limit_search(self, axis, limit):
        self._limit_search_in_progress[axis] = 0
        limit = int(math.copysign(1, limit))  # ensure limit is 1 or -1 only
        searched_lim = "LIMPOS" if limit > 0 else "LIMNEG"
        if searched_lim in self.state(axis):
            # if icepap is already at limit, there might be a stopcode in state,
            # which makes us reporting 'FAULT' => in this case we need to ignore
            # the stopcode, this is done via '_limit_search_in_progress'
            self._limit_search_in_progress[axis] = limit
        else:
            # start limit search
            cmd = "SRCH LIM" + ("+" if limit > 0 else "-")
            _ackcommand(self._cnx, "%s:%s" % (axis.address, cmd))
            # set that we are searching limit
            self._limit_search_in_progress[axis] = limit
            # TODO: can we remove this sleep one day?
            # at the moment state is not immediately MOVING
            gevent.sleep(0.1)

    @object_method(types_info=("None", "float"), filter=_object_method_filter)
    def limit_found_dial(self, axis):
        limit_step = int(_command(self._cnx, f"{axis.address}:?SRCHPOS MEASURE"))
        return limit_step / axis.steps_per_unit

    def initialize_encoder(self, encoder):
        pass

    def read_encoder(self, encoder):
        value = _command(self._cnx, "?ENC %s %d" % (encoder.enctype, encoder.address))
        return int(value)

    def read_encoder_multiple(self, *encoder):
        enc_types = set(enc.enctype for enc in encoder)
        if len(enc_types) > 1:
            # cannot read multiple encoders with different types,
            # so fallback to 'slow' solution with multiple reads
            # 'NotImplementedError' will make the controller use
            # the 'read_encoder' above
            raise NotImplementedError
        enc_type = enc_types.pop()
        values = _command(
            self._cnx,
            f"?ENC {enc_type} {' '.join(f'{enc.address}' for enc in encoder)}",
        )
        return list(map(int, values.split(" ")))

    def read_encoder_all_types(self, axis):
        """Return a named-tuple of all ENC value
        ("ENCIN", "ABSENC", "INPOS", "MOTOR", "AXIS", "SYNC")
        """

        # Create new "type" named IceEncoders.
        IceEncoders = namedtuple(
            "IcepapEncoders", "ENCIN, ABSENC, INPOS, MOTOR, AXIS, SYNC"
        )

        enc_names = ["ENCIN", "ABSENC", "INPOS", "MOTOR", "AXIS", "SYNC"]
        addr = axis.config.get("address")

        enc_values = [
            _command(self._cnx, f"?ENC {enctype} {addr}") for enctype in enc_names
        ]

        return IceEncoders(*enc_values)

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
        Activate/Deactivate the tracking position depending on activate flag

        Arguments:
            mode: Can be one of:

                   - `None`: defaulted with `"INPOS"`
                   - `"SYNC"`: Internal SYNC signal
                   - `"ENCIN"`: ENCIN signal
                   - `"INPOS"`: INPOS signal
                   - `"ABSENC"`: ABSENC signal
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
    def blink(self, axis, second=3.0):
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
