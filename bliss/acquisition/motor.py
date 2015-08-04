from __future__ import absolute_import
from bliss.common.continuous_scan import AcquisitionMaster
import bliss
import numpy
import gevent
import sys

class MotorMaster(AcquisitionMaster):
    def __init__(self, axis, start, end, time=0, undershoot=None):
        AcquisitionMaster.__init__(self, axis)
        self.movable = axis    
        self.start_pos = start
        self.end_pos = end
        self.undershoot = undershoot
        self.velocity = abs(end-start)/float(time) if time > 0 else axis.velocity()

    def _calculate_undershoot(self, pos, end = False):
        if self.undershoot is None:
            acctime = float(self.velocity)/self.movable.acceleration()
            undershoot = self.velocity*acctime
        d = 1 if self.end_pos >= self.start_pos else -1
        d *= -1 if end else 1
        pos -= d*undershoot
        else:
        return pos

    def prepare(self):
        start = self._calculate_undershoot(self.start_pos)
        self.movable.move(start)

    def start(self, polling_time=emotion.axis.DEFAULT_POLLING_TIME):
        self.initial_velocity = self.movable.velocity()
        self.movable.velocity(self.velocity) 
        end = self._calculate_undershoot(self.end_pos,end=True)
        emotion.event.connect(self.movable, "move_done", self.move_done)
        self.movable.move(end, polling_time=polling_time)

    def move_done(self, done):
        if done:
            self.movable.velocity(self.initial_velocity)
            emotion.event.disconnect(self.movable, "move_done", self.move_done)    

class SoftwarePositionTriggerMaster(MotorMaster):
    def __init__(self, axis, start, end, npoints=1, **kwargs):
	positions = numpy.linspace(start, end, npoints, retstep=True)
        if isinstance(positions, tuple):
            self._positions = positions[0]
            end += positions[1]
        else:
            self._positions = positions
        MotorMaster.__init__(self, axis, start, end, **kwargs)

    def start(self):
        self.exception = None
        self.index = 0
        emotion.event.connect(self.movable, "position", self.position_changed)
        MotorMaster.start(self, 0)
        if self.exception:
            raise self.exception[0], self.exception[1], self.exception[2]
        
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
              emotion.event.disconnect(self.movable, "position", self.position_changed)
              self.movable.stop(wait=False)
              self.exception = sys.exc_info()
        
    def move_done(self, done):
        if done:
            emotion.event.disconnect(self.movable, "position", self.position_changed)
        MotorMaster.move_done(self, done) 
       
