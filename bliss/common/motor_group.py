# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import gevent
import itertools
import numpy
from bliss.common.task import task
from bliss.common.cleanup import error_cleanup
from bliss.common.axis import Axis, AxisState, DEFAULT_POLLING_TIME
from bliss.common.axis import Trajectory
from bliss.common import event
from bliss.common.utils import grouped


def Group(*axes_list):
    axes = dict()
    g = _Group(id(axes), {})
    for axis in axes_list:
        if not isinstance(axis, Axis):
            raise ValueError("invalid axis %r" % axis)
        axes[axis.name] = axis
    g._axes.update(axes)
    return g


class _Group(object):

    def __init__(self, name, config):
        self.__name = name
        self._axes = dict()
        self._motions_dict = dict()
        self.__move_done = gevent.event.Event()
        self.__move_done.set()
        self.__move_task = None

    @property
    def name(self):
        return self.__name

    @property
    def axes(self):
        return self._axes

    @property
    def is_moving(self):
        return not self.__move_done.is_set()

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

    def stop(self, wait=True):
        if self.is_moving:
            self._do_stop(wait=False)
            if wait:
                self.wait_move()

    def _stop_one_controller_motions(self, controller, motions):
        try:
            controller.stop_all(*motions)
        except NotImplementedError:
            for motion in motions:
                controller.stop(motion.axis)
        for motion in motions:
            if self.__move_task:
                motion.axis._set_stopped()
            else:
                motion.axis._move_loop()
                motion.axis.sync_hard()

    def _do_stop(self, wait=True):
        all_motions = []
        if len(self._motions_dict) == 1:
            for controller, motions in self._motions_dict.iteritems():
                all_motions.extend(motions)
                self._stop_one_controller_motions(controller, motions)
        else:
            controller_tasks = list()
            for controller, motions in self._motions_dict.iteritems():
                all_motions.extend(motions)
                controller_tasks.append(
                    gevent.spawn(
                        self._stop_one_controller_motions, controller,
                        motions))
            gevent.joinall(controller_tasks, raise_error=True)

        if wait:
            motions_wait = [gevent.spawn(motion.axis.wait_move)
                            for motion in all_motions]
            gevent.joinall(motions_wait, raise_error=True)

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

    @task
    def _handle_move(self, motions, polling_time):
        try:
            for motion in motions:
                motion_task = motion.axis._start_move_task(
                    motion.axis._do_move, motion, polling_time)
                motion_task._motions = [motion]
            motions_wait = [gevent.spawn(motion.axis.wait_move)
                            for motion in motions]
            gevent.joinall(motions_wait, raise_error=True)
        except:
            self._do_stop()
            raise
        finally:
            self._set_move_done()

    def rmove(self, *args, **kwargs):
        kwargs["relative"] = True
        return self.move(*args, **kwargs)

    def _reset_motions_dict(self):
        self._motions_dict = dict()

    def _start_one_controller_motions(self, controller, motions):
        try:
            controller.start_all(*motions)
        except NotImplementedError:
            for motion in motions:
                controller.start_one(motion)

    def _start_motion(self, motions_dict):
        all_motions = []
        event.send(self, "move_done", False)

        with error_cleanup(self._do_stop):
            if(len(motions_dict) == 1):  # only one controller for the motion
                for controller, motions in motions_dict.iteritems():
                    all_motions.extend(motions)
                    self._start_one_controller_motions(controller, motions)
            else:               # parallel start
                controller_tasks = list()
                for controller, motions in motions_dict.iteritems():
                    all_motions.extend(motions)
                    controller_tasks.append(
                        gevent.spawn(
                            self._start_one_controller_motions, controller,
                            motions))
                gevent.joinall(controller_tasks, raise_error=True)
        return all_motions

    def _set_move_done(self):
        self._reset_motions_dict()
        self.__move_done.set()
        event.send(self, "move_done", True)

    def _check_ready(self):
        initial_state = self.state()
        if not initial_state.READY:
            raise RuntimeError("all motors are not ready")

    def move(self, *args, **kwargs):
        self._check_ready()
        self._reset_motions_dict()
        self.__move_task = None

        wait = kwargs.pop("wait", True)
        relative = kwargs.pop("relative", False)
        polling_time = kwargs.pop("polling_time", DEFAULT_POLLING_TIME)

        axis_pos_dict = dict()

        if len(args) == 1:
            axis_pos_dict.update(args[0])
        else:
            for axis, target_pos in grouped(args, 2):
                axis_pos_dict[axis] = target_pos

        for axis, target_pos in axis_pos_dict.iteritems():
            motion = axis.prepare_move(target_pos, relative=relative)
            if motion is not None:
                # motion can be None if axis is not supposed to move,
                # let's filter it
                self._motions_dict.setdefault(
                    axis.controller, []).append(
                    motion)

        all_motions = self._start_motion(self._motions_dict)
        self._handle_motions(all_motions, wait, polling_time)

    def _handle_motions(self, all_motions, wait, polling_time):
        self.__move_done.clear()
        self.__move_task = self._handle_move(
            all_motions, polling_time, wait=False)
        self.__move_task._motions = all_motions

        if wait:
            self.wait_move()

    def wait_move(self):
        if self.__move_task:
            move_task = self.__move_task
            with error_cleanup(self.stop):
                self.__move_done.wait()
            self.__move_task = None
            try:
                move_task.get()
            except gevent.GreenletExit:
                pass


def TrajectoryGroup(*trajectories, **keys):
    """
    Create an helper for a trajectory movement
    Keys:
        calc_axis -- calc axis link which has created this trajectory
    """
    calc_axis = keys.pop('calc_axis', None)
    traj = _TrajectoryGroup(calc_axis=calc_axis)
    traj.trajectories = trajectories
    return traj


class _TrajectoryGroup(object):
    """
    Group for motor trajectory
    """

    def __init__(self, calc_axis=None):
        self.__trajectories = None
        self.__trajectories_dialunit = None
        self.__group = None
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
        self.__group.stop = self.stop

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

    def prepare(self):
        """
        prepare/load trajectories in controllers
        """
        if self.__trajectories_dialunit is None:
            trajectories = list()
            for trajectory in self.__trajectories:
                trajectories.append(trajectory.convert_to_dial())
            self.__trajectories_dialunit = trajectories
        self._exec_func_on_controller('prepare_trajectory')

    def move_to_start(self, wait=True, polling_time=DEFAULT_POLLING_TIME):
        """
        Move all enabled motors to the first point of the trajectory
        """
        self.__group._check_ready()
        all_motions = list()
        for trajectory in self.__trajectories:
            pvt = trajectory.pvt
            final_pos = pvt['position'][0]
            motion = trajectory.axis.prepare_move(final_pos)
            if not motion:
                # already at final pos
                continue
            # no backlash to go to the first position
            # otherwise it may break next trajectory motion (move_to_end)
            motion.backlash = 0
            all_motions.append(motion)

        self._exec_func_on_controller('move_to_trajectory')
        self.__group._handle_motions(all_motions, wait, polling_time)

    def move_to_end(self, wait=True, polling_time=DEFAULT_POLLING_TIME):
        """
        Move all enabled motors to the last point of the trajectory
        """
        self.__group._check_ready()
        all_motions = list()
        for trajectory in self.__trajectories:
            pvt = trajectory.pvt
            final_pos = pvt['position'][-1]
            motion = trajectory.axis.prepare_move(final_pos)
            if not motion:
                continue
            all_motions.append(motion)

        self._exec_func_on_controller('start_trajectory')
        self.__group._handle_motions(all_motions, wait, polling_time)

    def stop(self, wait=True):
        """
        Stop the motion an all motors
        """
        self._exec_func_on_controller('stop_trajectory')
        if wait:
            self.__group.wait_move()

    def state(self):
        """
        Get the trajectory group status
        """
        return self.__group.state()

    def wait_move(self):
        """
        Wait the end of motion
        """
        self.__group.wait_move()

    def _exec_func_on_controller(self, funct_name):
        tasks = list()
        for ctrl, trajectories in self._group_per_controller().iteritems():
            funct = getattr(ctrl, funct_name)
            tasks.append(gevent.spawn(funct, *trajectories))
        gevent.joinall(tasks, raise_error=True)

    def _group_per_controller(self):
        controller_trajectories = dict()
        for traj in self.__trajectories_dialunit:
            if traj.axis in self.__disabled_axes:
                continue
            tlist = controller_trajectories.setdefault(
                traj.axis.controller, [])
            tlist.append(traj)
        return controller_trajectories
