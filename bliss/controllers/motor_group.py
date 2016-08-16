# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import gevent
import itertools
from bliss.common.task_utils import *
from bliss.common.axis import Axis, AxisRef, AxisState, DEFAULT_POLLING_TIME
from bliss.common import event


def grouped(iterable, n):
    """s -> (s0,s1,s2,...sn-1), (sn,sn+1,sn+2,...s2n-1),
            (s2n,s2n+1,s2n+2,...s3n-1), ..."""
    return itertools.izip(*[iter(iterable)] * n)


def Group(*axes_list):
    axes = dict()
    g = _Group(id(axes), {}, [])
    for axis in axes_list:
        if not isinstance(axis, Axis):
            raise ValueError("invalid axis %r" % axis)
        axes[axis.name] = axis
    g._axes.update(axes)
    return g


class _Group(object):

    def __init__(self, name, config, axes):
        self.__name = name
        self._axes = dict()
        self._motions_dict = dict()
        self.__move_done = gevent.event.Event()
        self.__move_done.set()
        self.__move_task = None

        for axis_name, axis_config in axes:
            axis = AxisRef(axis_name, self, axis_config)
            self._axes[axis_name] = axis

    @property
    def name(self):
        return self.__name

    @property
    def axes(self):
        return self._axes

    @property
    def is_moving(self):
        return not self.__move_done.is_set()

    def _update_refs(self):
        config = __import__("config", globals(), locals(), [], 1)
        for axis in self._axes.itervalues():
            referenced_axis = config.get_axis(axis.name)
            self._axes[axis.name] = referenced_axis

    def state(self):
        if self.is_moving:
            return AxisState("MOVING")

        grp_state = AxisState("READY")
        for i, (name, state) in enumerate([(axis.name, axis.state()) for axis in self._axes.itervalues()]):
            if state.MOVING:
                new_state = "MOVING"+" "*i
                grp_state.create_state(new_state, "%s: %s" % (name, grp_state._state_desc["MOVING"]))
                grp_state.set("MOVING")
                grp_state.set(new_state) 
            for axis_state in state._current_states:
                if axis_state == "READY":
                    continue
                new_state = axis_state+" "*i
                grp_state.create_state(new_state, "%s: %s" % (name, state._state_desc[axis_state]))     
                grp_state.set(new_state) 

        return grp_state

    def stop(self, wait=True):
        if self.is_moving:
            self._do_stop(wait=False)
            if wait:
                self.wait_move()

    def _stop_one_controller_motions(self,controller,motions):
        try:
            controller.stop_all(*motions)
        except NotImplementedError:
            for motion in motions:
                controller.stop(motion.axis)
        for motion in motions:
            motion.axis._set_stopped()
        
    def _do_stop(self,wait=True):
        all_motions = []
        if len(self._motions_dict) == 1:
            for controller, motions in self._motions_dict.iteritems():
                all_motions.extend(motions)
                self._stop_one_controller_motions(controller,motions)
        else:
            controller_tasks = list()
            for controller, motions in self._motions_dict.iteritems():
                all_motions.extend(motions)
                controller_tasks.append(gevent.spawn(self._stop_one_controller_motions,
                                                    controller,motions))
            gevent.joinall(controller_tasks, raise_error=True)

        if wait:
            for motion in all_motions:
                motion.axis.wait_move()

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
        with error_cleanup(self._do_stop): 
            for motion in motions:
                move_task = motion.axis._do_handle_move(motion, polling_time,
                                                        wait=False)
                motion.axis._Axis__move_task = move_task
                move_task._being_waited = True
                move_task.link(motion.axis._set_move_done)
            for motion in motions:
                motion.axis.wait_move()

    def rmove(self, *args, **kwargs):
        kwargs["relative"] = True
        return self.move(*args, **kwargs)

    def _reset_motions_dict(self):
        self._motions_dict = dict()

    def _start_one_controller_motions(self,controller,motions):
        try:
            controller.start_all(*motions)
        except NotImplementedError:
            for motion in motions:
                controller.start_one(motion)
        for motion in motions:
            motion.axis._set_moving_state()

    def _start_motion(self, motions_dict):
        all_motions = []
        event.send(self, "move_done", False)

        with error_cleanup(self._do_stop):
            if(len(motions_dict) == 1): # only one controller for the motion
                for controller, motions in motions_dict.iteritems():
                    all_motions.extend(motions)
                    self._start_one_controller_motions(controller,motions)
            else:               # parallel start
                controller_tasks = list()
                for controller, motions in motions_dict.iteritems():
                    all_motions.extend(motions)
                    controller_tasks.append(gevent.spawn(self._start_one_controller_motions,
                                                         controller,motions))
                gevent.joinall(controller_tasks, raise_error=True)
        return all_motions

    def _set_move_done(self, move_task):
        self._reset_motions_dict()

        if move_task is not None:
            if not move_task._being_waited:
                try:
                    move_task.get()
                except gevent.GreenletExit:
                    pass
                except:
                    sys.excepthook(*sys.exc_info())

        self.__move_done.set()
        event.send(self, "move_done", True)

    def move(self, *args, **kwargs):
        initial_state = self.state()
        if initial_state != "READY":
            raise RuntimeError("all motors are not ready")

        self._reset_motions_dict()

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
        self.__move_done.clear() 
        self.__move_task = self._handle_move(all_motions, polling_time,wait=False)
        self.__move_task._being_waited = wait
        self.__move_task.link(self._set_move_done)
 
        if wait:
            self.wait_move()

    def wait_move(self):
        if not self.is_moving:
            return
        self.__move_task._being_waited = True
        with error_cleanup(self.stop):
            self.__move_done.wait()
        try:
            self.__move_task.get()
        except gevent.GreenletExit:
            pass
