# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common.continuous_scan import AcquisitionDevice, AcquisitionMaster, AcquisitionChannel
from bliss.common.event import dispatcher
import gevent
import time
import numpy

class LimaAcquisitionDevice(AcquisitionDevice):
  def __init__(self, device, acq_nb_frames=1, acq_expo_time=1, acq_trigger_mode='INTERNAL_TRIGGER', acq_mode="SINGLE", acc_time_mode="LIVE", acc_max_expo_time=1, latency_time=0):
      self.parameters = locals().copy()
      del self.parameters['self']
      del self.parameters['device']
      trigger_type = AcquisitionDevice.SOFTWARE if 'INTERNAL' in acq_trigger_mode else AcquisitionDevice.HARDWARE
      AcquisitionDevice.__init__(self, device, device.user_detector_name, "lima", acq_nb_frames,
                                 trigger_type = trigger_type)
              
  def prepare(self):
      for param_name, param_value in self.parameters.iteritems():
          setattr(self.device, param_name, param_value)
      self.device.prepareAcq()
      signed, depth, w, h = self.device.image_sizes
      dtype = {(0,2): numpy.uint16, 
               (1,2): numpy.int16, 
               (0,4): numpy.uint32, 
               (1,4): numpy.int32,
               (0,1): numpy.uint8,
               (1,1): numpy.int8 }
      self.channels = [ AcquisitionChannel("image", dtype[(signed, depth)], (h,w)) ] 

  def start(self):
      if self.trigger_type == AcquisitionDevice.SOFTWARE:
          return
      self.trigger()

  def stop(self):
      self.device.stopAcq()

  #def trigger_ready(self):
  #    return self.device.ready_for_next_image

  def trigger(self):
      self.device.startAcq()

  def reading(self):
      while self.device.acq_status.lower() == 'running':
          dispatcher.send("new_ref", self, { "type":"lima/image", "last_image_acquired":self.device.last_image_acquired })
          gevent.sleep(self.parameters['acq_expo_time']/2.0)
      # TODO: self.dm.send_new_ref(self, {...}) ? or DataManager.send_new_ref(...) ?
      print "end of read_data", self.device.acq_status.lower()
      dispatcher.send("new_ref", self, { "type":"lima/image", "last_image_acquired":self.device.last_image_acquired })

