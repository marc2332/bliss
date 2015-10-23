# -*- coding: utf-8 -*-
#
# This file is part of the CT2 project
#
# Copyright (c) : 2015
# Beamline Control Unit, European Synchrotron Radiation Facility
# BP 220, Grenoble 38043
# FRANCE
#
# Distributed under the terms of the GNU Lesser General Public License,
# either version 3 of the License, or (at your option) any later version.
# See LICENSE.txt for more info.

import numpy
import PyTango.gevent

from ..device import BaseCT2Device, AcqMode

PyTango.requires_pytango('8.1.8')


class CT2Device(BaseCT2Device):
    """
    Helper for a remote TANGO device CT2 card (P201/C208).
    """

    def __init__(self, config, name):
        BaseCT2Device.__init__(self, config, name)
        device_name = self.card_config['tango name']
        
        self.__tango_device = PyTango.gevent.DeviceProxy(device_name)
        self.__tango_device.subscribe_event("last_point_nb",
                                            PyTango.EventType.CHANGE_EVENT,
                                            self.__on_point_nb)
        self.__tango_device.subscribe_event("last_error",
                                            PyTango.EventType.CHANGE_EVENT,
                                            self.__on_error)

    def __on_point_nb(self, event):
        point_nb = event.attr_value.value
        if point_nb < 0:
            self._send_stop()
        else:
            self._send_point_nb(point_nb)

    def __on_error(self, event):
        self._send_error(event.attr_value.value)

    @property
    def _device(self):
        return self.__tango_device

    @property
    def acq_mode(self):
        return AcqMode(self._device.acq_mode)

    @acq_mode.setter
    def acq_mode(self, acq_mode):
        self._device.acq_mode = AcqMode(acq_mode).name

    def apply_config(self):
        self.card_config.save()
        BaseCT2Device.apply_config(self)

    def read_data(self):
        data = Ct2Device.read_data(self)
        if data is None:
            data = numpy.array([[]], dtype=numpy.uint32)
        return data
