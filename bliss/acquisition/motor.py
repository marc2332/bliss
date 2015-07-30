from bliss.common.continuous_scan import AcquisitionMaster

class MotorMaster(AcquisitionMaster):
  def __init__(self, axis, start, end, undershoot=None):
    AcquisitionMaster.__init__(self, axis)
    self.movable = axis    
    self.start = start
    self.end = end
    self.undershoot = undershoot

  def prepare(self):
    if self.undershoot is None:
      undershoot = self.movable.velocity()/self.acctime()
    if self.end > self.start:
      start = self.start - undershoot
    else:
      start = self.start + undershoot
    self.movable.move(start)
