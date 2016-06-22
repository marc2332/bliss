# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import absolute_import
from bliss.common.continuous_scan import AcquisitionMaster
from bliss.common import axis
from bliss.common import event
import bliss
import numpy
import gevent
import sys

class MotorMaster(AcquisitionMaster):
    def __init__(self, axis, start, end, time=0, undershoot=None):
        AcquisitionMaster.__init__(self, axis, axis.name, "axis")
        self.movable = axis    
        self.start_pos = start
        self.end_pos = end
        self.undershoot = undershoot
        self.velocity = abs(end-start)/float(time) if time > 0 else axis.velocity()

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

    def start(self, polling_time=axis.DEFAULT_POLLING_TIME):
        self.initial_velocity = self.movable.velocity()
        self.movable.velocity(self.velocity) 
        end = self._calculate_undershoot(self.end_pos,end=True)
        event.connect(self.movable, "move_done", self.move_done)
        self.movable.move(end, polling_time=polling_time)

    def stop(self):
        self.movable.stop()

    def move_done(self, done):
        if done:
            self.movable.velocity(self.initial_velocity)
            event.disconnect(self.movable, "move_done", self.move_done)    

class SoftwarePositionTriggerMaster(MotorMaster):
    def __init__(self, axis, start, end, npoints=1, **kwargs):
	self._positions = numpy.linspace(start, end, npoints+1)[:-1]
        MotorMaster.__init__(self, axis, start, end, **kwargs)

    def start(self):
        self.exception = None
        self.index = 0
        event.connect(self.movable, "position", self.position_changed)
        MotorMaster.start(self, 1E-6)
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
        
    def move_done(self, done):
        if done:
            event.disconnect(self.movable, "position", self.position_changed)
        MotorMaster.move_done(self, done) 
       
