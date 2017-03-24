# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import absolute_import
from ..chain import AcquisitionMaster, AcquisitionChannel
from bliss.common import axis
from bliss.common import event
from bliss.common.event import dispatcher
from bliss.common.task_utils import error_cleanup
from bliss.common.utils import grouped
from bliss.controllers import motor_group
import bliss
import numpy
import gevent
import sys

class MotorMaster(AcquisitionMaster):
    def __init__(self, axis, start, end, time=0, undershoot=None,
                 trigger_type=AcquisitionMaster.HARDWARE,
                 backnforth=False,type="axis",**keys):
        AcquisitionMaster.__init__(self, axis, axis.name, type,
                                   trigger_type=trigger_type,**keys)
        self.movable = axis    
        self.start_pos = start
        self.end_pos = end
        self.undershoot = undershoot
        self.velocity = abs(end-start)/float(time) if time > 0 else axis.velocity()
        self.backnforth = backnforth

    def _calculate_undershoot(self, pos, end = False):
        if self.undershoot is None:
            acctime = float(self.velocity)/self.movable.acceleration()
            undershoot = self.velocity*acctime/2
        d = 1 if self.end_pos >= self.start_pos else -1
        d *= -1 if end else 1
        pos -= d*undershoot
        return pos

    def prepare(self):
        start = self._calculate_undershoot(self.start_pos)
        self.movable.move(start)

    def start(self):
        if self.trigger_type == AcquisitionMaster.SOFTWARE:
            return
        self.trigger()

    def trigger(self):
        self.initial_velocity = self.movable.velocity()
        self.movable.velocity(self.velocity) 
        end = self._calculate_undershoot(self.end_pos,end=True)
        event.connect(self.movable, "move_done", self.move_done)
        self.movable.move(end)
        if self.backnforth:
            self.start_pos,self.end_pos = self.end_pos,self.start_pos

    def wait_ready(self) :
        return self.movable.wait_move()

    def stop(self):
        self.movable.stop()

    def move_done(self, done):
        if done:
            self.movable.velocity(self.initial_velocity)
            event.disconnect(self.movable, "move_done", self.move_done)    

class SoftwarePositionTriggerMaster(MotorMaster):
    def __init__(self, axis, start, end, npoints=1, **kwargs):
	self._positions = numpy.linspace(start, end, npoints+1)[:-1]
        MotorMaster.__init__(self, axis, start, end,type="zerod", **kwargs)
        self.channels.append(AcquisitionChannel(axis.name,numpy.double, (1,)))
        self.__nb_points = npoints

    @property
    def npoints(self):
        return self.__nb_points

    def start(self):
        self.exception = None
        self.index = 0
        event.connect(self.movable, "position", self.position_changed)
        MotorMaster.start(self)
        if self.exception:
            raise self.exception[0], self.exception[1], self.exception[2]
        
    def stop(self):
        self.movable.stop()

    def position_changed(self, position):
        try:
            next_trigger_pos = self._positions[self.index]
        except IndexError:
            return
        if ((self.end_pos >= self.start_pos and position >= next_trigger_pos) or
            (self.start_pos > self.end_pos and position <= next_trigger_pos)):
          self.index += 1
          try:
              self.trigger_slaves()
          except Exception:
              event.disconnect(self.movable, "position", self.position_changed)
              self.movable.stop(wait=False)
              self.exception = sys.exc_info()
          else:
              dispatcher.send("new_data",self,
                              {"channel_data": {self.movable.name : numpy.double(position)}})

    def move_done(self, done):
        if done:
            event.disconnect(self.movable, "position", self.position_changed)
        MotorMaster.move_done(self, done) 
       

class JogMotorMaster(AcquisitionMaster):
    def __init__(self, axis, start, jog_speed, end_jog_func = None,
                 undershoot=None):
        """
        Helper to driver a motor in constant speed in jog mode.
        
        axis -- a motor axis
        start -- position where you want to have your motor in constant speed
        jog_speed -- constant velocity during the movement
        end_jog_func -- function to stop the jog movement. 
        Stop the movement if return value != True
        if end_jog_func is None should be stopped externally.
        """
        AcquisitionMaster.__init__(self, axis, axis.name, "axis")
        self.movable = axis    
        self.start_pos = start
        self.undershoot = undershoot
        self.jog_speed = jog_speed
        self.end_jog_func = end_jog_func
        self.__end_jog_task = None
        
    def _calculate_undershoot(self, pos) :
        if self.undershoot is None:
            acctime = abs(float(self.jog_speed)/self.movable.acceleration())
            undershoot = self.jog_speed*acctime/2
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
            self.__end_jog_task = gevent.spawn(self._end_jog_watch,polling_time)
            self.__end_jog_task.join()

    def stop(self):
        self.movable.stop()

    def move_done(self, done):
        if done:
            self.movable.velocity(self.initial_velocity)
            event.disconnect(self.movable, "move_done", self.move_done)

    def _end_jog_watch(self,polling_time):
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
    def __init__(self,*args,**keys):
        trigger_type= keys.pop('trigger_type',AcquisitionMaster.SOFTWARE)
        self.next_mv_cmd_arg = list()
        if len(args) % 4:
            raise TypeError('_StepTriggerMaster: argument is a mot1,start,stop,nb points,mot2,start2...')
        self._motor_pos = list()
        self._axes = list()
        for axis,start,stop,nb_point in grouped(args,4):
            self._axes.append(axis)
            self._motor_pos.append(numpy.linspace(start,stop,nb_point))

        mot_group = motor_group.Group(*self._axes)
        group_name = '/'.join((x.name for x in self._axes))

        AcquisitionMaster.__init__(self,mot_group,group_name,"zerod",
                                   trigger_type=trigger_type,**keys)

        self.channels.extend((AcquisitionChannel(axis.name,numpy.double, (1,)) for axis in self._axes))

    @property
    def npoints(self):
        return min((len(x) for x in self._motor_pos))

    def __iter__(self):
        iter_pos = [iter(x) for x in self._motor_pos]
        while True:
            self.next_mv_cmd_arg = list()
            for axis,pos in zip(self._axes,iter_pos):
                self.next_mv_cmd_arg.extend((axis,pos.next()))
            yield self

    def prepare(self):
        self.device.move(*self.next_mv_cmd_arg)

    def start(self):
        self.trigger()
            
    def stop(self):
        self.device.stop()

    def trigger(self):
        self.trigger_slaves()

        dispatcher.send("new_data",self,
                        {"channel_data":dict((axis.name,numpy.double(axis.position()))
                                             for axis in self._axes)})

        self.wait_slaves()

class MeshStepTriggerMaster(_StepTriggerMaster):
    """
    Generic motor master for step by step mesh acquisition.

    :param *args == mot1,start1,stop1,nb_point1,mot2,start2,stop2,nb_point2,...
    :param backnforth if True do back and forth on the first motor
    Example::

        MeshStepTriggerMaster(mota,0,10,20,motb,-1,1,5)
    """
    def __init__(self,*args,**keys):
        backnforth = keys.pop('backnforth',False)
        _StepTriggerMaster.__init__(self,*args,**keys)
        
        self._motor_pos = numpy.meshgrid(*self._motor_pos)
        if backnforth:
            self._motor_pos[0][::2] = self._motor_pos[0][::2,::-1]

        for x in self._motor_pos:       # flatten
            x.shape = -1,
 

class LinearStepTriggerMaster(_StepTriggerMaster):
    """
    Generic motor master for step by step acquisition.
    
    :param nb_point the number of position generated
    :param *args == mot1,start1,stop1,mot2,start2,stop2,...
    Example::

        LinearStepTriggerMaster(20,mota,0,10,motb,-1,1)
    """
    def __init__(self,nb_point,*args,**keys):
        if len(args) % 3:
            raise TypeError('LinearStepTriggerMaster: argument is a nb_point,mot1,start1,stop1,mot2,start2,stop2,...')

        params = list()
        for axis,start,stop in grouped(args,3):
            params.extend((axis,start,stop,nb_point))
        _StepTriggerMaster.__init__(self,*params,**keys)
