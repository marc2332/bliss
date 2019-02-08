# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import sys
import time

import numpy
import gevent.event

import bliss
from bliss.common import axis
from bliss.common import event
from bliss.common.event import dispatcher
from bliss.common.cleanup import error_cleanup
from bliss.common.utils import grouped
from bliss.common.motor_group import Group, TrajectoryGroup
from bliss.physics.trajectory import find_pvt

from ..chain import AcquisitionMaster, AcquisitionChannel


class UndershootMixin(object):
    def __init__(self, undershoot=None, start_margin=0, end_margin=0):
        self._undershoot = undershoot
        self._undershoot_start_margin = start_margin
        self._undershoot_end_margin = end_margin

    @property
    def undershoot(self):
        if self._undershoot is not None:
            return self._undershoot
        acctime = float(self.velocity) / self.movable.acceleration
        return self.velocity * acctime / 2

    def _calculate_undershoot(self, pos, end=False):
        d = 1 if self.end_pos >= self.start_pos else -1
        d *= -1 if end else 1
        pos -= d * self.undershoot
        if end:
            margin = d * self._undershoot_end_margin
        else:
            margin = d * self._undershoot_start_margin
        return pos - margin


class MotorMaster(AcquisitionMaster, UndershootMixin):
    def __init__(
        self,
        axis,
        start,
        end,
        time=0,
        undershoot=None,
        undershoot_start_margin=0,
        undershoot_end_margin=0,
        trigger_type=AcquisitionMaster.SOFTWARE,
        backnforth=False,
        **keys
    ):
        AcquisitionMaster.__init__(
            self, axis, "axis", trigger_type=trigger_type, **keys
        )
        UndershootMixin.__init__(
            self, undershoot, undershoot_start_margin, undershoot_end_margin
        )

        self.movable = axis
        self.start_pos = start
        self.end_pos = end
        self.velocity = (
            abs(self.end_pos - self.start_pos) / float(time)
            if time > 0
            else self.movable.velocity
        )
        self.backnforth = backnforth

    def prepare(self):
        start = self._calculate_undershoot(self.start_pos)
        self.movable.move(start)

    def start(self):
        if self.parent:
            return
        self.trigger()

    def trigger(self):
        self.trigger_slaves()
        return self._start_move()

    def _start_move(self):
        self.initial_velocity = self.movable.velocity
        try:
            self.movable.velocity = self.velocity
            end = self._calculate_undershoot(self.end_pos, end=True)
            self.movable.move(end)
            if self.backnforth:
                self.start_pos, self.end_pos = self.end_pos, self.start_pos
        finally:
            self.movable.velocity = self.initial_velocity

    def trigger_ready(self):
        return not self.movable.is_moving

    def wait_ready(self):
        self.movable.wait_move()

    def stop(self):
        self.movable.stop()


class SoftwarePositionTriggerMaster(MotorMaster):
    def __init__(self, axis, start, end, npoints=1, **kwargs):
        # remove trigger type kw arg, since in this case it is always software
        kwargs.pop("trigger_type", None)
        self._positions = numpy.linspace(start, end, npoints + 1)[:-1]
        MotorMaster.__init__(
            self, axis, start, end, trigger_type=AcquisitionMaster.SOFTWARE, **kwargs
        )
        self.channels.append(AcquisitionChannel(axis.name, numpy.double, ()))
        self.__nb_points = npoints
        self.task = None
        self.started = gevent.event.Event()

    @property
    def npoints(self):
        return self.__nb_points

    def start(self):
        self.started.clear()
        self.task = gevent.spawn(self.timer_task)
        event.connect(self.movable, "internal_state", self.on_state_change)
        MotorMaster.start(self)

    def on_state_change(self, state):
        if state == "MOVING":
            self.started.set()

    def stop(self):
        self.movable.stop()
        event.disconnect(self.movable, "internal_state", self.on_state_change)
        if self.task:
            self.task.kill()

    def trigger(self):
        return self._start_move()

    def get_trigger(self, position):
        t0 = self.velocity / (2. * self.movable.acceleration)
        t0 += abs(self.undershoot) / float(self.velocity)
        distance = abs(self.start_pos - position)
        return t0 + distance / float(self.velocity)

    def timer_task(self):
        # Wait for motor start
        self.started.wait()
        # Take a time reference
        ref = time.time()
        # Iterate over trigger
        for position in self._positions:
            # Sleep
            trigger = self.get_trigger(position)
            current_time = time.time() - ref
            gevent.sleep(trigger - current_time)
            # Trigger the slaves
            try:
                self.trigger_slaves()
            # Handle slave exception
            except Exception:
                self.movable.stop(wait=False)
                raise
            # Emit motor position
            else:
                self.channels[0].emit(position)

    def trigger_ready(self):
        return MotorMaster.trigger_ready() and (self.task is None or self.task.ready())

    def wait_ready(self):
        MotorMaster.wait_ready(self)
        if self.task is not None:
            try:
                self.task.get()
            finally:
                self.task = None


class JogMotorMaster(AcquisitionMaster):
    def __init__(self, axis, start, jog_speed, end_jog_func=None, undershoot=None):
        """
        Helper to driver a motor in constant speed in jog mode.

        axis -- a motor axis
        start -- position where you want to have your motor in constant speed
        jog_speed -- constant velocity during the movement
        end_jog_func -- function to stop the jog movement.
        Stop the movement if return value != True
        if end_jog_func is None should be stopped externally.
        """
        AcquisitionMaster.__init__(self, axis, axis.name)
        self.movable = axis
        self.start_pos = start
        self.undershoot = undershoot
        self.jog_speed = jog_speed
        self.end_jog_func = end_jog_func
        self.__end_jog_task = None

    def _calculate_undershoot(self, pos):
        if self.undershoot is None:
            acctime = abs(float(self.jog_speed) / self.movable.acceleration)
            undershoot = self.jog_speed * acctime / 2
        pos -= undershoot
        return pos

    def prepare(self):
        if self.__end_jog_task is not None:
            self.__end_jog_task.stop()
            self.__end_jog_task = None

        start = self._calculate_undershoot(self.start_pos)
        self.movable.move(start)

    def start(self, polling_time=axis.DEFAULT_POLLING_TIME):
        with error_cleanup(self.stop):
            self.movable.jog(self.jog_speed)
            self.__end_jog_task = gevent.spawn(self._end_jog_watch, polling_time)
            self.__end_jog_task.join()

    def stop(self):
        self.movable.stop()

    def move_done(self, done):
        if done:
            self.movable.velocity = self.initial_velocity
            event.disconnect(self.movable, "move_done", self.move_done)

    def _end_jog_watch(self, polling_time):
        try:
            while self.movable.is_moving:
                stopFlag = True
                try:
                    if self.end_jog_func is not None:
                        stopFlag = not self.end_jog_func(self.movable)
                    else:
                        stopFlag = False
                    if stopFlag:
                        self.movable.stop()
                        break
                    gevent.sleep(polling_time)
                except:
                    self.movable.stop()
                    raise

        finally:
            self.__end_jog_task = None


class _StepTriggerMaster(AcquisitionMaster):
    """
    Generic motor master helper for step by step acquisition.

    :param *args == mot1,start1,stop1,nb_point,mot2,start2,stop2,nb_point,...
    :param nb_point should be always the same for all motors
    Example::

        _StepTriggerMaster(mota,0,10,20,motb,-1,1,20)
    """

    def __init__(self, *args, **keys):
        trigger_type = keys.pop("trigger_type", AcquisitionMaster.SOFTWARE)
        self.broadcast_len = keys.pop("broadcast_len", 1)
        self.next_mv_cmd_arg = list()
        if len(args) % 4:
            raise TypeError(
                "_StepTriggerMaster: argument is a mot1,start,stop,nb points,mot2,start2..."
            )
        self._motor_pos = []
        self._axes = []
        for axis, start, stop, nb_point in grouped(args, 4):
            self._axes.append(axis)
            self._motor_pos.append(numpy.linspace(start, stop, nb_point))
            axis.controller._check_limits(axis, self._motor_pos[-1])

        mot_group = Group(*self._axes)

        AcquisitionMaster.__init__(
            self, mot_group, "axis", trigger_type=trigger_type, **keys
        )

        self.channels.extend(
            (AcquisitionChannel(axis.name, numpy.double, ()) for axis in self._axes)
        )

    @property
    def npoints(self):
        return min((len(x) for x in self._motor_pos))

    def __iter__(self):
        for positions in zip(*self._motor_pos):
            for axis, position in zip(self._axes, positions):
                self.next_mv_cmd_arg += [axis, position]
            yield self

    def prepare(self):
        self.device.move(*self.next_mv_cmd_arg)

    def start(self):
        self.trigger()

    def stop(self):
        self.device.stop()

    def trigger(self):
        self.trigger_slaves()

        if self.broadcast_len > 1:
            self.channels.update_from_iterable(
                [
                    numpy.ones(self.broadcast_len, numpy.float) * axis.position
                    for axis in self._axes
                ]
            )
        else:
            self.channels.update_from_iterable([axis.position for axis in self._axes])

        self.wait_slaves()


class MeshStepTriggerMaster(_StepTriggerMaster):
    """
    Generic motor master for step by step mesh acquisition.

    :param *args == mot1,start1,stop1,nb_point1,mot2,start2,stop2,nb_point2,...
    :param backnforth if True do back and forth on the first motor
    Example::

        MeshStepTriggerMaster(mota,0,10,20,motb,-1,1,5)
    """

    def __init__(self, *args, **keys):
        backnforth = keys.pop("backnforth", False)
        _StepTriggerMaster.__init__(self, *args, **keys)

        self._motor_pos = numpy.meshgrid(*self._motor_pos)
        if backnforth:
            self._motor_pos[0][::2] = self._motor_pos[0][::2, ::-1]

        for x in self._motor_pos:  # flatten
            x.shape = (-1,)


class LinearStepTriggerMaster(_StepTriggerMaster):
    """
    Generic motor master for step by step acquisition.

    :param nb_point the number of position generated
    :param *args == mot1,start1,stop1,mot2,start2,stop2,...
    Example::

        LinearStepTriggerMaster(20,mota,0,10,motb,-1,1)
    """

    def __init__(self, nb_point, *args, **keys):
        if len(args) % 3:
            raise TypeError(
                "LinearStepTriggerMaster: argument is a nb_point,mot1,start1,stop1,mot2,start2,stop2,..."
            )

        params = list()
        for axis, start, stop in grouped(args, 3):
            params.extend((axis, start, stop, nb_point))
        _StepTriggerMaster.__init__(self, *params, **keys)


class VariableStepTriggerMaster(AcquisitionMaster):
    """
    Generic motor master helper for a variable step by step acquisition.

    :param *args == mot1, positions,...
    Example::

        _VariableStepTriggerMaster(mot1, positions, mot2, positions2)
    """

    def __init__(self, *args, **keys):
        trigger_type = keys.pop("trigger_type", AcquisitionMaster.SOFTWARE)
        self.broadcast_len = keys.pop("broadcast_len", 1)
        self.next_mv_cmd_arg = list()
        if len(args) % 2:
            raise TypeError(
                "_VariableStepTriggerMaster: argument is a mot, positions ..."
            )

        self._motor_pos = list()
        self._axes = list()
        nb_points = None
        for _axis, pos_list in grouped(args, 2):
            self._axes.append(_axis)
            if nb_points is None or nb_points == len(pos_list):
                self._motor_pos.append(pos_list)
                nb_points = len(pos_list)
            else:
                raise RuntimeError(
                    "Motor %s has a %d nbpoints but other has %d nbpoints"
                    % (_axis.name, len(pos_list), nb_points)
                )

        mot_group = Group(*self._axes)

        AcquisitionMaster.__init__(
            self, mot_group, "axis", trigger_type=trigger_type, **keys
        )

        self.channels.extend(
            (AcquisitionChannel(axis.name, numpy.double, ()) for axis in self._axes)
        )

    @property
    def npoints(self):
        return min((len(x) for x in self._motor_pos))

    def __iter__(self):
        for positions in zip(*self._motor_pos):
            for axis, position in zip(self._axes, positions):
                self.next_mv_cmd_arg += [axis, position]
            yield self

    def prepare(self):
        self.device.move(*self.next_mv_cmd_arg)

    def start(self):
        self.trigger()

    def stop(self):
        self.device.stop()

    def trigger(self):
        self.trigger_slaves()

        if self.broadcast_len > 1:
            self.channels.update_from_iterable(
                [
                    numpy.ones(self.broadcast_len, numpy.float) * axis.position
                    for axis in self._axes
                ]
            )
        else:
            self.channels.update_from_iterable([axis.position for axis in self._axes])

        self.wait_slaves()


class CalcAxisTrajectoryMaster(AcquisitionMaster):
    def __init__(
        self,
        axis,
        start,
        end,
        nb_points,
        time_per_point,
        trigger_type=AcquisitionMaster.HARDWARE,
        type="axis",
        **keys
    ):
        AcquisitionMaster.__init__(
            self, axis, axis.name, type, trigger_type=trigger_type, **keys
        )
        self.movable = axis
        self.trajectory = axis.scan_on_trajectory(start, end, nb_points, time_per_point)

    def prepare(self):
        self.trajectory.prepare()
        self.trajectory.move_to_start()

    def start(self):
        if self.trigger_type == AcquisitionMaster.SOFTWARE:
            return
        self.trigger()

    def trigger(self):
        if self.trigger_type == AcquisitionMaster.SOFTWARE:
            self.trigger_slaves()

        self.trajectory.move_to_end()

    def trigger_ready(self):
        return not self.trajectory.is_moving

    def wait_ready(self):
        self.trajectory.wait_move()

    def stop(self):
        self.trajectory.stop()


class MeshTrajectoryMaster(AcquisitionMaster, UndershootMixin):
    """
    Generic motor master for continuous mesh acquisition on trajectory.

    :param *args == mot1,start1,stop1,nb_point1,mot2,start2,stop2,nb_point2,...
    :param undershoot use it if passed else calculated with current
           acceleration (first motor only).
    :param undershoot_start_margin added to the calculated undershoot
           for the start (first motor only).
    :param undershoot_end_margin added to the calculated undershoot
           at the end (first motor only).
    Example::

        MeshTrajectoryMaster(0.1,mota,0,10,20,motb,-1,1,5)
    """

    def __init__(
        self,
        axis1,
        start1,
        stop1,
        nb_points1,
        axis2,
        start2,
        stop2,
        nb_points2,
        time_per_point,
        undershoot=None,
        undershoot_start_margin=0,
        undershoot_stop_margin=0,
        trigger_type=AcquisitionMaster.SOFTWARE,
        **kwargs
    ):

        name = "mesh_" + axis1.name + "_" + axis2.name
        AcquisitionMaster.__init__(
            self, None, name, trigger_type=trigger_type, **kwargs
        )
        UndershootMixin.__init__(
            self, undershoot, undershoot_start_margin, undershoot_stop_margin
        )

        # Required by undershoot mixin
        self.movable = axis1
        self.end_pos = stop1
        self.start_pos = start1
        line_duration = time_per_point * nb_points1
        self.velocity = abs(stop1 - start1) / line_duration

        # Main scan trajectory

        sign = 1 if stop1 >= start1 else -1
        p0, p1, p2, p3 = (
            self._calculate_undershoot(start1, end=False),
            start1 - sign * self._undershoot_start_margin,
            stop1 + sign * self._undershoot_end_margin,
            self._calculate_undershoot(stop1, end=True),
        )

        vs, a = self.velocity, self.movable.acceleration
        v0, v1, v2, v3 = 0, vs, vs, 0

        at = float(vs) / a
        full_line_duration = line_duration
        full_line_duration += (
            self._undershoot_start_margin + self._undershoot_end_margin
        ) / vs
        t0, t1, t2, t3 = 0, at, at + full_line_duration, at + full_line_duration + at

        # Main return trajectory

        vr = self.movable.velocity
        rt = axis.LinearTrajectory(p3, p0, vr, a, t3)
        p4, p5, p6 = rt.pa, rt.pb, rt.pf
        v4, v5, v6 = rt.velocity, rt.velocity, 0
        t4, t5, t6 = rt.ta, rt.tb, rt.tf

        # Main trajectory

        ts = t0, t1, t2, t3, t4, t5, t6
        ps = p0, p1, p2, p3, p4, p5, p6
        vs = v0, v1, v2, v3, v4, v5, v6
        main_trajectory = [(p - p0, v, t) for p, v, t in zip(ps, vs, ts)]

        # Second trajectory

        step = float(stop2 - start2) / nb_points2
        sv, sa = axis2.velocity, axis2.acceleration
        st = axis.LinearTrajectory(start2, start2 + step, sv, sa, t2)
        second_trajectory = [
            (st.pi, 0, 0),
            (st.pi, 0, st.ti),
            (st.pa, st.velocity, st.ta),
            (st.pb, st.velocity, st.tb),
            (st.pf, 0, st.tf),
        ]
        second_trajectory = [(p - st.pi, v, t) for p, v, t in second_trajectory]

        # Synchronize trajectories
        main_last_p, _, main_last_t = main_trajectory[-1]
        second_last_p, _, second_last_t = second_trajectory[-1]
        if main_last_t > second_last_t:
            second_trajectory.append((second_last_p, 0, main_last_t))
        elif main_last_t < second_last_t:
            main_trajectory.append((main_last_p, 0, second_last_t))

        # Cyclic trajectories
        dtype = [("position", float), ("velocity", float), ("time", float)]
        nb_cycles = nb_points2
        cyclic_trajectories = [
            axis.CyclicTrajectory(
                axis1, numpy.array(main_trajectory, dtype=dtype), nb_cycles, p0
            ),
            axis.CyclicTrajectory(
                axis2, numpy.array(second_trajectory, dtype=dtype), nb_cycles, start2
            ),
        ]

        # Trajectory group
        self.trajectory = TrajectoryGroup(*cyclic_trajectories)

    def set_event_position(self, axis, position, match_first=True, match_return=False):
        """
        set a events on a position.
        :param match_first if True will add an event on the first part of the trajectory
        :param match_return if True will add an event on the return.
        """
        for t in self.trajectory.trajectories:
            if t.axis == axis:
                diff_pos = position - t.origin
                pvt_trigger = find_pvt(t.pvt_pattern, diff_pos)
                if len(pvt_trigger) < 1:
                    raise RuntimeError(
                        "Could not find position {} an trajectory for axis {}".format(
                            position, axis
                        )
                    )
                if match_return is False:
                    pvt_trigger = pvt_trigger[:1]
                t.events_pattern_positions = pvt_trigger
                break
        else:
            raise RuntimeError("Could not find axis **{}** on trajectory".format(axis))

    def prepare(self):
        self.trajectory.prepare()
        self.trajectory.move_to_start()

    def start(self):
        if self.parent is None:
            self.trigger()

    def trigger(self):
        self.trigger_slaves()

        self.trajectory.move_to_end()

    def wait_ready(self):
        self.trajectory.wait_move()

    def stop(self):
        self.trajectory.stop()


class SweepMotorMaster(AcquisitionMaster):
    def __init__(
        self,
        axis,
        start,
        end,
        npoints=1,
        time=0,
        undershoot=None,
        undershoot_start_margin=0,
        undershoot_stop_margin=0,
        trigger_type=AcquisitionMaster.SOFTWARE,
        **keys
    ):
        AcquisitionMaster.__init__(
            self, axis, axis.name, trigger_type=trigger_type, **keys
        )
        self.movable = axis

        self._nb_points = npoints

        self.sweep_move = float(end - start) / self._nb_points
        self.start_pos = numpy.linspace(start, end, npoints + 1)[:-1]

        self.initial_speed = self.movable.velocity
        if time > 0:
            self.sweep_speed = abs(self.sweep_move) / float(time)
        else:
            self.sweep_speed = self.initial_speed

        if undershoot is not None:
            self._undershoot = undershoot
        else:
            acctime = float(self.sweep_speed) / axis.acceleration
            self._undershoot = self.sweep_speed * acctime / 2
        self._undershoot_start_margin = undershoot_start_margin
        self._undershoot_stop_margin = undershoot_stop_margin

    def _get_real_start_pos(self, pos):
        sign = 1 if self.sweep_move > 0 else -1
        pos = pos - sign * self._undershoot - sign * self._undershoot_start_margin
        return pos

    def _get_real_stop_pos(self, pos):
        sign = 1 if self.sweep_move > 0 else -1
        pos = (
            pos
            + self.sweep_move
            + sign * self._undershoot
            + sign * self._undershoot_stop_margin
        )
        return pos

    @property
    def npoints(self):
        return self._nb_points

    def __iter__(self):
        for start_pos in self.start_pos:
            self.next_start_pos = start_pos
            yield self

    def prepare(self):
        if self.sweep_speed > self.initial_speed:
            self.movable.velocity = self.sweep_speed
        real_start = self._get_real_start_pos(self.next_start_pos)
        self.movable.move(real_start)

    def start(self):
        if self.parent is None:
            self.trigger()

    def trigger(self):
        self.movable.velocity = self.sweep_speed
        real_end = self._get_real_stop_pos(self.next_start_pos)
        self.movable.move(real_end, wait=False)
        self.trigger_slaves()

    def trigger_ready(self):
        return not self.movable.is_moving

    def wait_ready(self):
        self.movable.wait_move()

    def stop(self):
        self.movable.stop()
        self.movable.velocity = self.initial_speed
