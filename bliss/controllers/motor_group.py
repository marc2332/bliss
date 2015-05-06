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
    def config(self):
        return self.__config

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

        states = [axis.state() for axis in self._axes.itervalues()]
        if any([state.MOVING for state in states]):
            return AxisState("MOVING")

        return AxisState("READY")

    def stop(self, exception=gevent.GreenletExit, wait=True):
        if self.is_moving:
            self.__move_task.kill(exception, block=False)
            if wait:
                self.wait_move()

    def _do_stop(self):
        all_motions = []
        for controller, motions in self._motions_dict.iteritems():
            all_motions.extend(motions)
            try:
                controller.stop_all(*motions)
            except NotImplementedError:
                pass
            for motion in motions:
                motion.axis.stop(wait=False)
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

    def single_axis_move_task(self, motion):
        with error_cleanup(motion.axis._do_stop):
            motion.axis._handle_move(motion)
        if motion.axis.encoder is not None:
            motion.axis._do_encoder_reading()

    def _handle_move(self, motions):
        move_tasks = []
        for motion in motions:
            move_task = gevent.spawn(self.single_axis_move_task, motion)
            motion.axis._Axis__move_task = move_task
            move_task._being_waited = True
            move_task.link(motion.axis._set_move_done)
            move_tasks.append(move_task)
        for move_task in gevent.iwait(move_tasks):
            move_task.get()

    def rmove(self, *args, **kwargs):
        kwargs["relative"] = True
        return self.move(*args, **kwargs)

    def _reset_motions_dict(self):
        self._motions_dict = dict()

    @task
    def _do_move(self, motions_dict):
        all_motions = []
        event.send(self, "move_done", False)

        with error_cleanup(self._do_stop): 
            for controller, motions in motions_dict.iteritems():
                all_motions.extend(motions)
                try:
                    controller.start_all(*motions)
                except NotImplementedError:
                    for motion in motions:
                        controller.start_one(motion)

            self._handle_move(all_motions)

    def _set_move_done(self, move_task):
        self._reset_motions_dict()
        event.send(self, "move_done", True)
        self.__move_done.set()

    def move(self, *args, **kwargs):
        initial_state = self.state()
        if initial_state != "READY":
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
                axis._set_moving_state()

        self.__move_done.clear() 
        self.__move_task = self._do_move(self._motions_dict, wait=False)
        self.__move_task.link(self._set_move_done)
        gevent.sleep(0)
 
        if wait:
            self.wait_move()

    def wait_move(self):
        try:
            self.__move_done.wait()
        except KeyboardInterrupt:
            self.stop()
            raise
        else:
            try:
                if self.__move_task is not None:
                    return self.__move_task.get()
            except (KeyboardInterrupt, gevent.GreenletExit):
                pass

