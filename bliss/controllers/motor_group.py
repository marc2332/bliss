import gevent
from bliss.common.task_utils import *
from bliss.config.motors.static import StaticConfig
import types
from bliss.common.axis import AxisRef, READY, MOVING, FAULT, UNKNOWN

class Group(object):

    def __init__(self, name, config, axes):
        self.__name = name
        self.__config = StaticConfig(config)
        self._axes = dict()
      
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
        if any([state == MOVING for state in states]):
          return MOVING
        if all([state == READY for state in states]):
          return READY
        if any([state == FAULT for state in states]):
          return FAULT
        else:
          return UNKNOWN

    def stop(self):
        for axis in self.axes.itervalues():
            axis.stop()

    @task
    def _handle_move(self, motions):
        move_tasks = []
        with error_cleanup(self.stop):
            for motion in motions:
                move_task = gevent.spawn(motion.axis._handle_move, motion)
                move_task.link(motion.axis._set_move_done)
                move_tasks.append(move_task)
            for move_task in gevent.iwait(move_tasks):
                move_task.get()

    def rmove(self, *args, **kwargs):
        kwargs["relative"]=True
        return self.move(*args, **kwargs)


    def move(self, *args, **kwargs):
        initial_state = self.state()
        if initial_state != READY:
          raise RuntimeError("all motors are not ready")

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

        axis_name_pos_dict = kwargs

        if len(args) > 1:
          raise RuntimeError("Too many arguments")
        elif len(args) == 1:
          if type(args[0])==types.DictType:
            axis_name_pos_dict.update(args[0])
          else:
            raise ValueError("Dictionary { axis_name: target_pos } is expected")
       
        motions_dict = dict() 
        for axis_name, target_pos in axis_name_pos_dict.iteritems():
          if not axis_name in self._axes:
            continue
          axis = self._axes[axis_name] 
          motions_dict.setdefault(axis.controller, []).append(axis.prepare_move(target_pos, relative=relative))
          axis._Axis__move_done.clear()
 
        all_motions = []
        for controller, motions in motions_dict.iteritems():
            try:
                controller.start_all(*motions)
            except NotImplementedError:
                for motion in motions:
                  controller.start_one(motion)
                  all_motions.append(motion)
            else:
                all_motions.extend(motions)

        return self._handle_move(all_motions, wait=wait)
