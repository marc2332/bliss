# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import absolute_import

import numpy
from bliss.common.tango import PyTango, EventType, DeviceProxy 
from bliss.controllers.ct2 import BaseCT2Device, AcqMode, AcqStatus

PyTango.requires_pytango('8.1.8')


class CT2Device(BaseCT2Device):
    """
    Helper for a remote TANGO device CT2 card (P201/C208).
    """

    def __init__(self, device_name):
        BaseCT2Device.__init__(self)

        self.__tango_device = DeviceProxy(device_name)
#       Uncomment when CT2 server supports events again (tango bug solved)
#        self.__tango_device.subscribe_event("acq_status",
#                                            EventType.CHANGE_EVENT,
#                                            self.__on_status)
#        self.__tango_device.subscribe_event("last_point_nb",
#                                            EventType.CHANGE_EVENT,
#                                            self.__on_point_nb)
#        self.__tango_device.subscribe_event("last_error",
#                                            EventType.CHANGE_EVENT,
#                                            self.__on_error)

    def __on_status(self, event):
        self._send_status(AcqStatus[event.attr_value.value])

    def __on_point_nb(self, event):
        self._send_point_nb(event.attr_value.value)

    def __on_error(self, event):
        self._send_error(event.attr_value.value)

    @property
    def _device(self):
        return self.__tango_device

    def apply_config(self):
        self.card_config.save()
        BaseCT2Device.apply_config(self)

    def read_data(self):
        data = self._device.data
        if data is None:
            data = numpy.array([[]], dtype=numpy.uint32)
        return data

    def dump_memory(self):
        return bytes(super(CT2Device, self).dump_memory().data)
