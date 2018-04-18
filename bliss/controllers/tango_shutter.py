# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common.tango import DeviceProxy, DevFailed
import time

class tango_shutter:
   def __init__(self, name, config):
      tango_uri = config.get("uri")
      self.name = name
      self.__control = DeviceProxy(tango_uri)
      try:
         self._manual = config.get("attr_mode")
      except:
         self._manual = False

   def get_status(self):
      print self.__control._status()

   def get_state(self):
      return str(self.__control._state())

   def open(self):
      state = self.get_state()
      if state == 'STANDBY':
         raise RuntimeError('Cannot open shutter in STANDBY state')
      if state == 'CLOSE':
         try:
            self.__control.command_inout("Open")
            self._wait('OPEN', 5)
         except:
            raise RuntimeError("Cannot open shutter")
      else:
         print self.__control._status()

   def close(self):
      state = self.get_state()
      if state == 'OPEN' or state == 'RUNNING':
         try:
            self.__control.command_inout("Close")
            self._wait('CLOSE', 5)
         except:
            raise RuntimeError("Cannot close shutter")
      else:
         print self.__control._status()

   def automatic(self):
      if self._manual:
         state = self.get_state()
         if state == 'CLOSE' or state == 'OPEN':
            try:
               self.__control.command_inout("Automatic")
               self._wait_mode()
            except:
               raise RuntimeError("Cannot open shutter in automatic mode")
         else:
            print self.__control._status()

   def manual(self):
      if self._manual:
         state = self.get_state()
         if state == 'CLOSE' or state == 'RUNNING':
            try:
               self.__control.command_inout("Manual")
               self._wait_mode()
            except:
               raise RuntimeError("Cannot set shutter in manual mode")
         else:
            print self.__control._status()
         
   def _wait(self, state, timeout=3):
      tt = time.time()
      stat = self.get_state()
      while stat != state or time.time() - tt < timeout:
         time.sleep(1)
         stat = self.get_state()

   def _wait_mode(self, timeout=3):
      tt = time.time()
      stat = self.__control.read_attribute(self._manual).value
      while stat is False or time.time() - tt < timeout:
         time.sleep(1)
         stat = self.__control.read_attribute(self._manual).value

   def __repr__(self):
      try:
         return self.__control.status()
      except DevFailed:
         return 'Shutter {}: Communication error with {}' \
            .format(self.name, self.__control.dev_name())

   def __enter__(self):
      self.open()

   def __exit__(self, exc_type, exc_val, exc_tb):
      self.close()
