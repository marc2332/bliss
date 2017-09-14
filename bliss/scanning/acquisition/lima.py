# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from ..chain import AcquisitionDevice, AcquisitionMaster, AcquisitionChannel
from bliss.common.event import dispatcher
from bliss.controllers import lima
import gevent
import time
import numpy

class LimaAcquisitionDevice(AcquisitionDevice):
  def __init__(self, device,
               acq_nb_frames=1, acq_expo_time=1,
               acq_trigger_mode='INTERNAL_TRIGGER', acq_mode="SINGLE",
               acc_time_mode="LIVE", acc_max_expo_time=1, latency_time=0,
               **keys) :
      """
      Acquisition device for lima camera.

      all parameters are directly matched with the lima device server
      """
      self.parameters = locals().copy()
      del self.parameters['self']
      del self.parameters['device']
      del self.parameters['keys']
      self.parameters.update(keys)
      trigger_type = AcquisitionDevice.SOFTWARE if 'INTERNAL' in acq_trigger_mode else AcquisitionDevice.HARDWARE
      if isinstance(device,lima.Lima):
        device = device.proxy
      AcquisitionDevice.__init__(self, device, device.user_detector_name, "lima", acq_nb_frames,
                                 trigger_type = trigger_type)
      self._latency = self.device.latency_time

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
      self._latency = self.device.latency_time

  def start(self):
      if self.trigger_type == AcquisitionDevice.SOFTWARE:
          return
      self.trigger()

  def stop(self):
      self.device.stopAcq()

  def wait_ready(self):
      wait_start = time.time()
      while not self.device.ready_for_next_image:
        if (wait_start + self._latency) >= time.time():
          break

  def trigger(self):
      self.device.startAcq()

  def reading(self):
      parameters = {"type":"lima/parameters"}
      parameters.update(self.parameters)
      dispatcher.send("new_data",self,parameters)
      while self.device.acq_status.lower() == 'running':
          dispatcher.send("new_ref", self, { "type":"lima/image",
                                             "last_image_acquired":self.device.last_image_acquired,
                                             "last_image_saved":self.device.last_image_saved,
                                           })
          gevent.sleep(self.parameters['acq_expo_time']/2.0)
      # TODO: self.dm.send_new_ref(self, {...}) ? or DataManager.send_new_ref(...) ?
      print "end of read_data", self.device.acq_status.lower()
      dispatcher.send("new_ref", self, { "type":"lima/image",
                                         "last_image_acquired":self.device.last_image_acquired,
                                         "last_image_saved":self.device.last_image_saved,
                                       })

