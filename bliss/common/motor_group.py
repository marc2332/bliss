# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import gevent
import itertools
import numpy
from bliss.common.axis import Axis, AxisState, DEFAULT_POLLING_TIME
from bliss.common.axis import Trajectory
from bliss.common import event
from bliss.common.utils import grouped

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


class GroupMove(object):
    def __init__(self, parent, start_one_controller_motions, stop_one_controller_motions):
        self.__parent = parent
        self.__move_done = gevent.event.Event()
        self.__move_done.set()
        self.__move_task = None

        self._start_one_controller_motions = start_one_controller_motions
        self._stop_one_controller_motions = stop_one_controller_motions

    @property
    def is_moving(self):
        return not self.__move_done.is_set()

    @property
    def parent(self):
        return self.__parent
    
    def __monitor_move(self, motions_dict, polling_time=DEFAULT_POLLING_TIME):
        monitor_move = []
        for controller, motions in motions_dict.iteritems():
            for motion in motions:
                task = motion.axis._start_move_task(motion.axis._handle_move,
                                                    motion, polling_time)
                task._motions = [motion]
                monitor_move.append(gevent.spawn(motion.axis.wait_move))
        try:
            gevent.joinall(monitor_move, raise_error=True)
        except:
            gevent.killall(monitor_move)
            raise

    def __stop_move(self, motions_dict):
         stop = [gevent.spawn(self._stop_one_controller_motions, controller, motions)
                 for controller, motions in motions_dict.iteritems()]
         gevent.joinall(stop)
         
    def __move(self, motions_dict, started_event=None, polling_time=DEFAULT_POLLING_TIME):
        all_motions = [motion for motions in motions_dict.itervalues()
                       for motion in motions]
        
        try:
            # put axis in MOVING state => wait_move will wait until moving state
            # is cleared, at '_start_move_task' cleanup
            for motion in all_motions:
                motion.axis._set_moving_state(move_type=motion.type)

            if started_event is not None:
                started_event.set()
            
            start = [gevent.spawn(self._start_one_controller_motions, controller, motions)
                     for controller, motions in motions_dict.iteritems()]
            try:
                gevent.joinall(start, raise_error=True)
                self.__monitor_move(motions_dict, polling_time)
            except:
                # something went wrong when starting motors: stop
                # everything !
                # it is important to kill the tasks, otherwise it may send
                # unwanted 'start' to motors
                gevent.killall(start)
                # send stop to axes
                self.__stop_move(motions_dict)
                self.__monitor_move(motions_dict)
                raise
        finally:
                self.__move_done.set()
                event.send(self.parent, "move_done", True)
    
    def start(self, motions_dict, relative=False, wait=True, polling_time=DEFAULT_POLLING_TIME):
        if len(motions_dict) == 0:
            return

        started = gevent.event.Event()

        self.__move_task = gevent.spawn(self.__move, motions_dict, started, polling_time)

        try:
            started.wait()
        except:
            self.__move_task.kill()
            raise
        else:
            if self.__move_task.ready():
                # move task already finished,
                # this can happen if motions_dict is empty
                # (now protected with test on top of this
                # function), but we can imagine it can
                # happen in case of a very small move ?
                # or if something changes in the future in
                # the underlying code ?
                return

        self.__move_done.clear()
        event.send(self.parent, "move_done", False)

        if wait:
            self.wait()

    def wait(self):
        if self.__move_task:
            move_task = self.__move_task
            self.__move_done.wait()
            self.__move_task = None
            try:
                move_task.get()
            except gevent.GreenletExit:
                # ignore if task has been killed (by user)
                pass

    def stop(self, wait=True):
        if self.__move_task is not None:
            self.__move_task.kill()
            if wait:
                self.wait()


class _Group(object):

    def __init__(self, name, axes_dict):
        self.__name = name
        self._group_move = None
        self._axes = dict(axes_dict)

    @property
    def name(self):
        return self.__name

    @property
    def axes(self):
        return self._axes

    @property
    def is_moving(self):
        return self._group_move.is_moving if self._group_move else False

    def _start_one_controller_motions(self, controller, motions):
        try:
            controller.start_all(*motions)
        except NotImplementedError:
            for motion in motions:
                controller.start_one(motion)

    def _stop_one_controller_motions(self, controller, motions):
        try:
            controller.stop_all(*motions)
            for motion in motions:
                motion.axis._user_stopped = True
        except NotImplementedError:
            for motion in motions:
                controller.stop(motion.axis)
                motion.axis._user_stopped = True
                
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

        self._group_move = GroupMove(self,
                                     self._start_one_controller_motions,
                                     self._stop_one_controller_motions)
        self._group_move.start(motions_dict, relative=relative, wait=wait, polling_time=polling_time)

    def wait_move(self):
        if self._group_move:
            self._group_move.wait()

    def stop(self, wait=True):
        if self._group_move:
            self._group_move.stop(wait)


class TrajectoryGroup(object):
    """
    Group for motor trajectory
    """

    def __init__(self, *trajectories, **kwargs):
        calc_axis = kwargs.pop('calc_axis', None)
        self.__trajectories = None
        self.__trajectories_dialunit = None
        self.__group = None
        self.__calc_axis = calc_axis
        self.__disabled_axes = set()
        self.trajectories = trajectories
        
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
        self.__group._group_move = None

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
        if self.__group:
            return self.__group.is_moving
        else:
            return False
        
    def state(self):
        if self.__group:
            return self.__group.state()
        else:
            return AxisState("OFF")
    
    def prepare(self):
        """
        prepare/load trajectories in controllers
        """
        if self.__trajectories_dialunit is None:
            trajectories = list()
            for trajectory in self.trajectories:
                trajectories.append(trajectory.convert_to_dial())
            self.__trajectories_dialunit = trajectories
            
        prepare = [gevent.spawn(controller.prepare_trajectory, *trajectories)
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

        self.__group._group_move = GroupMove(self, self._move_to_trajectory, self._stop_trajectory)
        self.__group._group_move.start(motions_dict, wait=wait, polling_time=polling_time)

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

        self.__group._group_move = GroupMove(self, self._start_trajectory, self._stop_trajectory)
        self.__group._group_move.start(motions_dict, wait=wait, polling_time=polling_time)

    def stop(self, wait=True):
        """
        Stop the motion on all motors
        """
        if self.__group and self.__group._group_move:
            self.__group._group_move.stop(wait)
        
    def wait_move(self):
        if self.__group and self.__group._group_move:
            self.__group._group_move.wait()
