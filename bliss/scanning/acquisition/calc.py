from __future__ import absolute_import
from ..chain import AcquisitionDevice
from bliss.common.event import dispatcher
import bliss
import numpy
import gevent
import sys


class CalcAcquisitionDevice(AcquisitionDevice):
    def __init__(self, name, src_acq_devices_list, func, output_channels_list, type="zerod"):
        AcquisitionDevice.__init__(
            self, None, name, type, trigger_type=AcquisitionDevice.HARDWARE)
        self.src_acq_devices_list = src_acq_devices_list
        self.func = func
        self.channels.extend(output_channels_list)

    def prepare(self):
        for acq_device in self.src_acq_devices_list:
            dispatcher.connect(self.new_data_received, "new_data", acq_device)

    def new_data_received(self, event_dict=None, signal=None, sender=None):
        channel_data = event_dict.get("channel_data")
        if channel_data is None:
            return

        output_channels_data_dict = self.func(sender, channel_data)

        if output_channels_data_dict:
            dispatcher.send("new_data", self, {
                            "channel_data": output_channels_data_dict})

    def start(self):
        return

    def stop(self):
        return
