# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common.task_utils import cleanup, error_cleanup, task
from bliss.common.measurement import SamplingCounter, AverageMeasurement
from bliss.common.greenlet_utils import protect_from_kill
import time
import gevent
import socket

class LSCounter(SamplingCounter):
   def __init__(self, name, parent, index):
     SamplingCounter.__init__(self, parent.name+'.'+name, parent)
     self.parent = parent
     self.index = index

   def count(self, time=None, measurement=None):
     if not self.parent.acquisition_event.is_set():
       self.parent.acquisition_event.wait()
       data = self.parent.last_acq
     else:
       data = self.parent._read(time)
     return data[self.index]


class ls335(object):
   def __init__(self, name, config):
       self.name = name

       self.gpib_controller_host = config.get("gpib_controller_host")
       self.gpib_address = config.get("gpib_address")

       self.acquisition_event = gevent.event.Event()
       self.acquisition_event.set()
       self.__control = None

   def connect(self):
       self.__control = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
       self.__control.connect((self.gpib_controller_host, 1234))
       self.__control.sendall('++mode 1\r\n++addr %d\r\n++auto 0\r\nmode 0\r\n' % self.gpib_address)
       return self._putget("*idn?").startswith("LS")

   @protect_from_kill
   def _putget(self, cmd):
       if self.__control is None:
           self.connect()
       self.__control.sendall("%s\r\n++read eoi\r\n" % cmd)
       return self.__control.recv(1024)

   @property
   def A(self):
       return LSCounter("A", self, 0)

   @property
   def B(self):
       return LSCounter("B", self, 1)

   def _read(self, acq_time=None):
       self.acquisition_event.clear()
       try:
           chan_a_K = float(self._putget("krdg? a"))
           chan_b_K = float(self._putget("krdg? b"))
           self.last_acq = (chan_a_K, chan_b_K)
           return self.last_acq
       finally:
           self.acquisition_event.set()
