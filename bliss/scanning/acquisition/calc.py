from __future__ import absolute_import
from ..chain import AcquisitionDevice
from bliss.common.event import dispatcher
import bliss
import numpy
import gevent
import sys


class CalcAcquisitionDevice(AcquisitionDevice):
    """
    Helper to do some extra Calculation on counters.
    i.e: compute encoder position to user position
    Args:
        src_acq_devices_list -- list or tuple of acq(device/master) you want to listen to.
        func -- the transformation function. This will have has input a  dictionary
        with the name of counter as the key and the value has the data of source data channel.
        This function should return a dictionary with the name of the destination channel as key,
        and the value as its data.
    """
    def __init__(self, name, src_acq_devices_list, func, output_channels_list):
        AcquisitionDevice.__init__(
            self, None, name, trigger_type=AcquisitionDevice.HARDWARE)
        self._connected = False
        self.src_acq_devices_list = src_acq_devices_list
        self.func = func
        self.channels.extend(output_channels_list)

    def connect(self):
        if self._connected:
            return
        for acq_device in self.src_acq_devices_list:
            for channel in acq_device.channels:
                dispatcher.connect(self.new_data_received, "new_data", channel)
        self._connected = True

    def disconnect(self):
        if not self._connected:
            return
        for acq_device in self.src_acq_devices_list:
            for channel in acq_device.channels:
                dispatcher.disconnect(self.new_data_received, "new_data", channel)
        self._connected = False

    def prepare(self):
        self.connect()

    def trigger(self):
        pass                    # nothing to do

    def new_data_received(self, event_dict=None, signal=None, sender=None):
        channel_data = event_dict.get("data")
        if channel_data is None:
            return
        channel = sender
        output_channels_data_dict = self.func(sender, {channel.name:channel_data})

        if output_channels_data_dict:
            for channel in self.channels:
                channel_data = output_channels_data_dict.get(channel.name)
                if channel_data is not None:
                    channel.emit(channel_data)

    def start(self):
        return

    def stop(self):
        self.disconnect()
