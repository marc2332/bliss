# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common.continuous_scan import AcquisitionDevice, AcquisitionChannel
from bliss.common.event import dispatcher
import gevent
import numpy

class MusstAcquisitionDevice(AcquisitionDevice):
  def __init__(self, musst_dev, program=None, store_list=None, vars=None):
    AcquisitionDevice.__init__(self, musst_dev, "musst", "zerod", trigger_type=AcquisitionDevice.HARDWARE)
    self.musst = musst_dev
    self.program = program
    self.vars = vars
    self.channels.extend((AcquisitionChannel(name,numpy.uint32, (1,)) for name in store_list))

  def prepare(self):
    #self.musst.putget("#ABORT")
    with file(self.program, "r") as prog:
      self.musst.upload_program(prog.read())
    if vars:
      for var_name, value in self.vars.iteritems():	
        self.musst.putget("VAR %s %s" %  (var_name,value))

  def start(self):
    self.musst.run()
    self._buffer_reading_task = gevent.spawn(self.read_buffer)

  def stop(self):
    self.musst.ABORT

  def read_buffer(self):
    last_read_event = 0
    while self.musst.STATE == self.musst.RUN_STATE:
	data = self.musst.get_data(len(self.channels),last_read_event)
        if data.size > 0:
          channel_data = dict(zip((c.name for c in self.channels), [data[:,i] for i in range(len(self.channels))]))
          dispatcher.send("new_data", self, { "channel_data": channel_data })
          nb_event_read = data.shape[0]
          last_read_event += nb_event_read

