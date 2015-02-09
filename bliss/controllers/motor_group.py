import gevent
import itertools
from bliss.common.task_utils import *
from .axis import Axis, AxisRef, AxisState
from bliss.common import event


def grouped(iterable, n):
    """s -> (s0,s1,s2,...sn-1), (sn,sn+1,sn+2,...s2n-1),
            (s2n,s2n+1,s2n+2,...s3n-1), ..."""
    return itertools.izip(*[iter(iterable)] * n)


def createGroupFromConfig(name, config, axes):
    return _Group(name, config, axes)


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
        from bliss.config.motors import StaticConfig
        self.__config = StaticConfig(config)
        self._axes = dict()
        self._motions_dict = dict()

        for axis_name, axis_config in axes:
            axis = AxisRef(axis_name, self, axis_config)
            self._axes[axis_name] = axis

    @property
    def name(self):
        return self.__name

    @property
    def config(self):
        return self.__config

    @property
    def axes(self):
        return self._axes

    @property
    def is_moving(self):
        return self.state() == MOVING

    def _update_refs(self):
        config = __import__("config", globals(), locals(), [], 1)
        for axis in self._axes.itervalues():
            referenced_axis = config.get_axis(axis.name)
            self._axes[axis.name] = referenced_axis

    def state(self):
        states = [axis.state() for axis in self._axes.itervalues()]

        if any([state.MOVING for state in states]):
            return AxisState("MOVING")

        if all([state.READY for state in states]):
            return AxisState("READY")

    def stop(self):
        try:
            for controller, motions in self._motions_dict.iteritems():
                try:
                    controller.stop_all(*motions)
                except NotImplementedError:
                    for motion in motions:
                        motion.axis.stop()
                else:
                    for motion in motions:
                        motion.axis._set_move_done(None)
        finally:
            self._reset_motions_dict()

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
    def _handle_move(self, motions):
        move_tasks = []
        try:
            event.send(self, "move_done", False)
            with error_cleanup(self.stop):
                for motion in motions:
                    move_task = gevent.spawn(motion.axis._handle_move, motion)
                    motion.axis._Axis__move_task = move_task
                    move_task._being_waited = True
                    move_task.link(motion.axis._set_move_done)
                    move_tasks.append(move_task)
                for move_task in gevent.iwait(move_tasks):
                    move_task.get()
        finally:
            event.send(self, "move_done", True)

    def rmove(self, *args, **kwargs):
        kwargs["relative"] = True
        return self.move(*args, **kwargs)

    def _reset_motions_dict(self):
        self._motions_dict = dict()

    def move(self, *args, **kwargs):
        initial_state = self.state()
        if not initial_state.READY:
            raise RuntimeError("all motors are not ready")

        self._reset_motions_dict()

        try:
            wait = kwargs['wait']
        except KeyError:
            wait = True
        else:
            del kwargs['wait']
        try:
            relative = kwargs['relative']
        except KeyError:
            relative = False
        else:
            del kwargs['relative']

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
                axis._Axis__move_done.clear()

        all_motions = []
        try:
            for controller, motions in self._motions_dict.iteritems():
                try:
                    controller.start_all(*motions)
                except NotImplementedError:
                    for motion in motions:
                        controller.start_one(motion)
                        all_motions.append(motion)
                else:
                    all_motions.extend(motions)
        except:
            # if something wrong happens when starting motions,
            # let's stop everything and re-raise the exception
            self.stop()
            raise

        return self._handle_move(all_motions, wait=wait)

    def wait_move(self):
        for axis in self._axes.itervalues():
            axis.wait_move()
