# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common.continuous_scan import AcquisitionDevice
import gevent

class MusstAcquisitionDevice(AcquisitionDevice):
  def __init__(self, musst_dev, program=None, store_list=None, vars=None):
    AcquisitionDevice.__init__(self, musst_dev)
    self.musst = musst_dev
    self.vars = vars
    self.store_list = store_list

  def prepare(self):
    #self.musst.putget("#ABORT")
    with file(program, "r") as prog:
      self.musst.upload_program(prog.read())
    if vars:
      for var_name, value in vars.iteritems():	
        self.musst.putget("VAR %s %s" %  (var_name,value))

  def start(self):
    self.musst.start()
    self._buffer_reading_task = gevent.spawn(self.read_buffer)

  def read_buffer(self):
    last_read_event = 0
    while self.musst.STATUS != self.musst.RUN_STAT:
	data = self.musst.get_data(last_read_event,len(self.store_list))
	nb_event_read = data.shape[-1]
        last_read_event += nb_event_read

