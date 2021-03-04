# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from numpy import float as npfloat
import numpy
from collections import deque
from bliss.scanning.chain import AcquisitionSlave, ChainNode
from bliss.scanning.channel import AcquisitionChannel
from bliss.common.event import dispatcher


class CalcHook(object):
    def compute(self, sender, data_dict):
        raise NotImplementedError

    def prepare(self):
        pass

    def start(self):
        pass

    def stop(self):
        pass


class CalcChannelAcquisitionSlave(AcquisitionSlave):
    """
    Helper to do some extra Calculation on channels.
    i.e: compute encoder position to user position
    Args:
        src_acq_devices_list -- list or tuple of acq(device/master) you want to listen to.
        func -- the transformation function. This will have has input a  dictionary
        with the name of counter as the key and the value has the data of source data channel.
        This function should return a dictionary with the name of the destination channel as key,
        and the value as its data.
        Can also be an inherited class of **CalcHook**:
         - the transformation function is the **compute** method.
         - optionally you can redefine prepare,start,stop. 
    """

    def __init__(self, name, src_acq_devices_list, func, output_channels_list):
        AcquisitionSlave.__init__(
            self, None, name=name, trigger_type=AcquisitionSlave.HARDWARE
        )

        self._connected = False
        self.src_acq_devices_list = src_acq_devices_list

        if isinstance(func, CalcHook):
            self.cbk = func
        else:

            class CBK(CalcHook):
                def compute(self, sender, data_dict):
                    return func(sender, data_dict)

            self.cbk = CBK()

        for chan_out in output_channels_list:
            if isinstance(chan_out, AcquisitionChannel):
                self.channels.append(chan_out)
            elif isinstance(chan_out, str):
                self.channels.append(AcquisitionChannel(chan_out, npfloat, ()))
            else:
                raise TypeError(f"Object '{chan_out}'' is not an AcquisitionChannel")

    def connect(self):
        if self._connected:
            return
        for acq_device in self.src_acq_devices_list:
            for channel in acq_device.channels:
                if channel.reference:
                    dispatcher.connect(
                        self.new_data_received, "new_data_stored", channel
                    )
                else:
                    dispatcher.connect(self.new_data_received, "new_data", channel)
        self._connected = True

    def disconnect(self):
        if not self._connected:
            return
        for acq_device in self.src_acq_devices_list:
            for channel in acq_device.channels:
                if channel.reference:
                    dispatcher.disconnect(
                        self.new_data_received, "new_data_stored", channel
                    )
                else:
                    dispatcher.disconnect(self.new_data_received, "new_data", channel)

        self._connected = False

    def prepare(self):
        self.cbk.prepare()
        self.connect()

    def new_data_received(self, event_dict=None, signal=None, sender=None):
        channel_data = event_dict.get("data")
        if channel_data is None:
            return
        channel = sender
        output_channels_data_dict = self.cbk.compute(
            sender, {channel.short_name: channel_data}
        )

        if output_channels_data_dict:
            for channel in self.channels:
                channel_data = output_channels_data_dict.get(channel.name)
                if channel_data is not None:
                    channel.emit(channel_data)

    def start(self):
        self.cbk.start()

    def stop(self):
        self.disconnect()
        self.cbk.stop()


class CalcCounterAcquisitionSlave(AcquisitionSlave):
    """
    Helper to do some extra Calculation on counters.
    i.e: compute encoder position to user position
    Args:
        controller -- CalcCounterController Object
        src_acq_devices_list -- list or tuple of acq(device/master) you want to listen to.
    """

    def __init__(self, controller, src_acq_devices_list, acq_params, ctrl_params=None):

        name = controller.name
        npoints = acq_params.get("npoints", 1)

        super().__init__(
            controller,
            name=name,
            npoints=npoints,
            trigger_type=AcquisitionSlave.HARDWARE,
            ctrl_params=ctrl_params,
        )

        self._connected = False
        self._frame_index = {}
        self.build_input_channel_list(src_acq_devices_list)

    def build_input_channel_list(self, src_acq_devices_list):
        self._inputs_channels = {}
        for acq_device in src_acq_devices_list:
            for cnt, channels in acq_device._counters.items():
                # filter unwanted counters and extra channels
                if cnt in self.device._input_counters:
                    # ignore multi channels per counter (see sampling)
                    self._inputs_channels[channels[0]] = cnt

        self._inputs_data_buffer = {chan: deque() for chan in self._inputs_channels}

    def connect(self):
        if self._connected:
            return

        for channel in self._inputs_channels:
            if channel.reference:
                dispatcher.connect(self.new_data_received, "new_data_stored", channel)
            else:
                dispatcher.connect(self.new_data_received, "new_data", channel)

        self._connected = True

    def disconnect(self):
        if not self._connected:
            return

        for channel in self._inputs_channels:
            if channel.reference:
                dispatcher.disconnect(
                    self.new_data_received, "new_data_stored", channel
                )
            else:
                dispatcher.disconnect(self.new_data_received, "new_data", channel)

        self._connected = False

    def prepare(self):
        self.connect()

    def compute(self, sender, sender_data):
        """
        This method works only if all input_counters will generate the same number of points !!!
        It registers all data comming from the input counters.
        It calls calc_function with input counters data which have reach the same index
        This function is called once per counter (input and output).

        * <sender> = AcquisitionChannel 
        * <data_dict> = {'em1ch1': array([0.00256367])}
        """

        # buffering: tmp storage of received newdata
        self._inputs_data_buffer[sender].extend(sender_data)

        # Find the amount of aligned data (i.e the smallest newdata len among all inputs)
        # Build the input_data_dict (indexed by tags and containing aligned data for all inputs)
        # Pop data from _inputs_data_buffer while building input_data_dict

        aligned_data_index = min(
            [len(data) for data in self._inputs_data_buffer.values()]
        )
        if aligned_data_index > 0:
            input_data_dict = {}
            for chan, cnt in self._inputs_channels.items():
                aligned_data = [
                    self._inputs_data_buffer[chan].popleft()
                    for i in range(aligned_data_index)
                ]
                input_data_dict[self.device.tags[cnt.name]] = numpy.array(aligned_data)

            output_data_dict = self.device.calc_function(input_data_dict)

            return output_data_dict

    def new_data_received(self, event_dict=None, signal=None, sender=None):
        # Handle Lima image reference
        if event_dict["description"]["reference"]:
            if event_dict["data"].get("in_prepare"):
                return

            curidx = self._frame_index.setdefault(sender, 0)
            input_data = sender.data_node.get_as_array(curidx, -1)

            # if there is no data to grab
            if input_data.size == 0:
                return

            # case of a single frame without a stacking dimension (only happen with references)
            if input_data.ndim == 2:
                input_data = input_data[numpy.newaxis,]

            self._frame_index[sender] += input_data.shape[0]

        else:
            input_data = event_dict.get("data")
            if input_data is None or input_data.size == 0:
                return

        output_channels_data_dict = self.compute(sender, input_data)

        if output_channels_data_dict:
            for chan in self.channels:
                output_data = output_channels_data_dict.get(
                    self.device.tags[chan.short_name]
                )
                if output_data is not None:
                    chan.shape = output_data.shape[1:]
                    chan.dtype = output_data.dtype
                    chan.emit(output_data)

    def start(self):
        pass

    def stop(self):
        self.disconnect()


class CalcCounterChainNode(ChainNode):
    def get_acquisition_object(
        self, acq_params, ctrl_params=None, parent_acq_params=None
    ):

        # Check if Acquisition Devices of dependant counters already exist
        acq_devices = []
        for node in self._calc_dep_nodes.values():
            acq_obj = node.acquisition_obj
            if acq_obj is None:
                raise ValueError(
                    f"cannot create CalcCounterAcquisitionSlave: acquisition object of {node}({node.controller}) is None!"
                )
            else:
                acq_devices.append(acq_obj)

        return self.controller.get_acquisition_object(
            acq_params, ctrl_params, parent_acq_params, acq_devices
        )
