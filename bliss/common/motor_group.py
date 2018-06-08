# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import gevent
import itertools
from bliss.common.axis import Axis, AxisState, DEFAULT_POLLING_TIME, GroupMove
from bliss.common import event
from bliss.common.utils import grouped
from bliss.common.cleanup import capture_exceptions

GROUP_ID = itertools.count()
GROUP_NAMES = {}


def Group(*axes_list):
    axes = dict()
    for axis in axes_list:
        if not isinstance(axis, Axis):
            raise ValueError("invalid axis %r" % axis)
        axes[axis.name] = axis
    # always use the same group name for groups of same axes,
    # this is to make sure master name will stay the same
    # when doing step-by-step scans for example -- this is
    # useful for Flint to know if the 0D live scan plot window
    # can be kept or not
    key = "".join(sorted(axes))
    gid = GROUP_NAMES.setdefault(key, GROUP_ID.next())
    g = _Group("group_%d" % gid, axes)
    return g

class _Group(object):

    def __init__(self, name, axes_dict):
        self.__name = name
        self._group_move = GroupMove(self)
        self._axes = dict(axes_dict)

    @property
    def name(self):
        return self.__name

    @property
    def axes(self):
        return self._axes

    @property
    def is_moving(self):
        return self._group_move.is_moving

    def _start_one_controller_motions(self, controller, motions):
        try:
            controller.start_all(*motions)
        except NotImplementedError:
            for motion in motions:
                controller.start_one(motion)

    def _stop_one_controller_motions(self, controller, motions):
        try:
            controller.stop_all(*motions)
        except NotImplementedError:
            for motion in motions:
                controller.stop(motion.axis)

    def state(self):
        if self.is_moving:
            return AxisState("MOVING")
        grp_state = AxisState("READY")
        for i, (name, state) in enumerate([(axis.name, axis.state())
                                           for axis in self._axes.itervalues()]):
            if state.MOVING:
                new_state = "MOVING"+" "*i
                grp_state.create_state(
                    new_state, "%s: %s" %
                    (name, grp_state._state_desc["MOVING"]))
                grp_state.set("MOVING")
                grp_state.set(new_state)
            for axis_state in state._current_states:
                if axis_state == "READY":
                    continue
                new_state = axis_state+" "*i
                grp_state.create_state(
                    new_state, "%s: %s" %
                    (name, state._state_desc[axis_state]))
                grp_state.set(new_state)
        return grp_state

    def position(self):
        positions_dict = dict()
        for axis in self.axes.itervalues():
            positions_dict[axis] = axis.position()
        return positions_dict

    def dial(self):
        positions_dict = dict()
        for axis in self.axes.itervalues():
            positions_dict[axis] = axis.dial()
        return positions_dict

    def _check_ready(self):
        initial_state = self.state()
        if not initial_state.READY:
            raise RuntimeError("all motors are not ready")

    def rmove(self, *args, **kwargs):
        kwargs["relative"] = True
        return self.move(*args, **kwargs)

    def move(self, *args, **kwargs):
        self._check_ready()

        wait = kwargs.pop("wait", True)
        relative = kwargs.pop("relative", False)
        polling_time = kwargs.pop("polling_time", DEFAULT_POLLING_TIME)
        axis_pos_dict = {}
        motions_dict = {}

        if len(args) == 1:
            axis_pos_dict.update(args[0])
        else:
            for axis, target_pos in grouped(args, 2):
                axis_pos_dict[axis] = target_pos

        for axis, target_pos in axis_pos_dict.iteritems():
            motion = axis.prepare_move(target_pos, relative=relative)
            # motion can be None if axis is not supposed to move
            if motion is not None:
                motions_dict.setdefault(axis.controller, []).append(motion)

        self._group_move.move(
            motions_dict,
            self._start_one_controller_motions,
            self._stop_one_controller_motions,
            wait=wait, polling_time=polling_time)

    def wait_move(self):
        self._group_move.wait()

    def stop(self, wait=True):
        self._group_move.stop(wait)


class TrajectoryGroup(object):
    """
    Group for motor trajectory
    """

    def __init__(self, *trajectories, **kwargs):
        calc_axis = kwargs.pop('calc_axis', None)
        self.__trajectories = trajectories
        self.__trajectories_dialunit = None
        self.__group = Group(*self.axes)
        self.__calc_axis = calc_axis
        self.__disabled_axes = set()

    @property
    def trajectories(self):
        """
        Get/Set trajectories for this movement
        """
        return self.__trajectories

    @trajectories.setter
    def trajectories(self, trajectories):
        self.__trajectories = trajectories
        self.__trajectories_dialunit = None
        self.__group = Group(*self.axes)

    @property
    def axes(self):
        """
        Axes for this motion
        """
        return [t.axis for t in self.__trajectories]

    @property
    def disabled_axes(self):
        """
        Axes which are disabled for the next motion
        """
        return self.__disabled_axes

    def disable_axis(self, axis):
        """
        Disable an axis for the next motion
        """
        self.__disabled_axes.add(axis)

    def enable_axis(self, axis):
        """
        Enable an axis for the next motion
        """
        try:
            self.__disabled_axes.remove(axis)
        except KeyError:        # was already enable
            pass                # should we raise?

    @property
    def calc_axis(self):
        """
        calculation axis if any
        """
        return self.__calc_axis

    @property
    def trajectories_by_controller(self):
        controller_trajectories = dict()
        for traj in self.__trajectories_dialunit:
            if traj.axis in self.__disabled_axes:
                continue
            tlist = controller_trajectories.setdefault(
                traj.axis.controller, [])
            tlist.append(traj)
        return controller_trajectories

    @property
    def is_moving(self):
        return self.__group.is_moving

    def state(self):
        return self.__group.state()

    def prepare(self):
        """
        prepare/load trajectories in controllers
        """
        if self.__trajectories_dialunit is None:
            trajectories = list()
            for trajectory in self.trajectories:
                trajectories.append(trajectory.convert_to_dial())
            self.__trajectories_dialunit = trajectories

        prepare = [gevent.spawn(controller._prepare_trajectory, *trajectories)
                   for controller, trajectories in self.trajectories_by_controller.iteritems()]
        try:
            gevent.joinall(prepare, raise_error=True)
        except:
            gevent.killall(prepare)
            raise

    def _move_to_trajectory(self, controller, motions):
        trajectories = self.trajectories_by_controller[controller]
        controller.move_to_trajectory(*trajectories)

    def _stop_trajectory(self, controller, motions):
        trajectories = self.trajectories_by_controller[controller]
        controller.stop_trajectory(*trajectories)

    def _start_trajectory(self, controller, motions):
        trajectories = self.trajectories_by_controller[controller]
        controller.start_trajectory(*trajectories)

    def move_to_start(self, wait=True, polling_time=DEFAULT_POLLING_TIME):
        """
        Move all enabled motors to the first point of the trajectory
        """
        self.__group._check_ready()

        motions_dict = {}
        for trajectory in self.trajectories:
            pvt = trajectory.pvt
            final_pos = pvt['position'][0]
            motion = trajectory.axis.prepare_move(final_pos)
            if not motion:
                # already at final pos
                continue
            # no backlash to go to the first position
            # otherwise it may break next trajectory motion (move_to_end)
            motion.backlash = 0
            motions_dict.setdefault(motion.axis.controller, []).append(motion)

        self.__group._group_move.move(
            motions_dict,
            self._move_to_trajectory,
            self._stop_trajectory,
            wait=wait,
            polling_time=polling_time)

    def move_to_end(self, wait=True, polling_time=DEFAULT_POLLING_TIME):
        """
        Move all enabled motors to the last point of the trajectory
        """
        self.__group._check_ready()

        motions_dict = {}
        for trajectory in self.trajectories:
            pvt = trajectory.pvt
            final_pos = pvt['position'][-1]
            motion = trajectory.axis.prepare_move(final_pos)
            if not motion:
                continue
            motions_dict.setdefault(motion.axis.controller, []).append(motion)

        self.__group._group_move.move(
            motions_dict,
            self._start_trajectory,
            self._stop_trajectory,
            wait=wait,
            polling_time=polling_time)

    def stop(self, wait=True):
        """
        Stop the motion on all motors
        """
        self.__group.stop(wait)

    def wait_move(self):
        self.__group.wait_move()
