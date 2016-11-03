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
  def __init__(self, musst_dev,
               program=None,
               store_list=None, vars=None,
               program_template_replacement=None):
    """
    Acquisition device for the musst card.

    program -- the program you need to load for your scan
    program_template_replacement -- substitution variable before sending it to the card
    store_list -- a list of variable you store in musst memory during the scan
    vars -- all variable you want to set before the musst program starts
    """
    AcquisitionDevice.__init__(self, musst_dev, "musst", "zerod", trigger_type=AcquisitionDevice.HARDWARE)
    self.musst = musst_dev
    self.program = program
    if program_template_replacement is not None:
      self.program_template_replacement = program_template_replacement
    else:
      self.program_template_replacement = dict()
    self.vars = vars if vars is not None else dict()
    store_list = store_list if store_list is not None else list()
    self.channels.extend((AcquisitionChannel(name,numpy.uint32, (1,)) for name in store_list))

  def prepare(self):
    self.musst.upload_file(self.program,
                           template_replacement=self.program_template_replacement)
    
    for var_name, value in self.vars.iteritems():	
      self.musst.putget("VAR %s %s" %  (var_name,value))

  def start(self):
    self.musst.run()

  def stop(self):
    self.musst.ABORT

  def reading(self):
    last_read_event = 0
    while self.musst.STATE == self.musst.RUN_STATE:
      new_read_event = self._send_data(last_read_event)
      if new_read_event != last_read_event:
        last_read_event = new_read_event
        gevent.sleep(100e-6)   # be able to ABORT the musst card
      else:
        gevent.sleep(10e-3)   # relax a little bit.
    self._send_data(last_read_event) # final send
    
  def _send_data(self,last_read_event):
      data = self.musst.get_data(len(self.channels),last_read_event)
      if data.size > 0:
        channel_data = dict(zip((c.name for c in self.channels), [data[:,i] for i in range(len(self.channels))]))
        dispatcher.send("new_data", self, { "channel_data": channel_data })
        nb_event_read = data.shape[0]
        last_read_event += nb_event_read
      return last_read_event


