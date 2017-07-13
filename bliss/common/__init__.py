# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

'''Common functionality (:mod:`~bliss.common.event`, :mod:`~bliss.common.log`, \
:mod:`~bliss.common.axis`, :mod:`~bliss.common.temperature`, etc)

This module gathers most common functionality to bliss (from
:mod:`~bliss.common.event` to :mod:`~bliss.common.axis`)

.. autosummary::
   :toctree:

   axis
   encoder
   event
   log
   measurement
   scans
   standard
   task_utils
   temperature
   utils
'''

import gevent
from .event import dispatcher

class Actuator:
  def __init__(self, set_in=None, set_out=None, is_in=None, is_out=None):
    self.__in = False
    self.__out = False
    if any((set_in,set_out,is_in,is_out)):
      self._set_in = set_in
      self._set_out = set_out
      self._is_in = is_in
      self._is_out = is_out

  def set_in(self,timeout=8):
    # this is to know which command was asked for,
    # in case we don't have a return (no 'self._is_in' or out)
    self.__in = True
    self.__out = False
    try:
        with gevent.Timeout(timeout):
            while True:
                self._set_in()
                if self.is_in():
                    break
                else:
                    gevent.sleep(0.5)
    finally:
        dispatcher.send("state", self, self.state())

  def set_out(self, timeout=8):
    self.__out = True
    self.__in = False
    try:
        with gevent.Timeout(timeout):
            while True:
                self._set_out()
                if self.is_out():
                    break
                else:
                    gevent.sleep(0.5)
    finally:
        dispatcher.send("state", self, self.state())

  def is_in(self):
    if self._is_in is not None:
      return self._is_in()
    else:
      if self._is_out is not None:  
        return not self._is_out()
      else:
        return self.__in

  def is_out(self):
    if self._is_out is not None:
      return self._is_out()
    else:
      if self._is_in is not None:
        return not self._is_in()
      else:
        return self.__out

  def state(self):
      state = ""
      if self.is_in():
          state += "IN"
      if self.is_out():
          state += "OUT"
      if not state or state == "INOUT":
          return "UNKNOWN"
      return state

