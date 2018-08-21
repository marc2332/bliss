# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from ..chain import AcquisitionMaster, AcquisitionChannel
from bliss.controllers import lima
from bliss.common.tango import get_fqn
import gevent
from gevent import event
import numpy
import os

LIMA_DTYPE = {
    (0, 2): numpy.uint16,
    (1, 2): numpy.int16,
    (0, 4): numpy.uint32,
    (1, 4): numpy.int32,
    (0, 1): numpy.uint8,
    (1, 1): numpy.int8,
}


class LimaAcquisitionMaster(AcquisitionMaster):
    def __init__(
        self,
        device,
        acq_nb_frames=1,
        acq_expo_time=1,
        acq_trigger_mode="INTERNAL_TRIGGER",
        acq_mode="SINGLE",
        acc_time_mode="LIVE",
        acc_max_expo_time=1,
        latency_time=0,
        save_flag=False,
        prepare_once=False,
        start_once=False,
        **keys
    ):
        """
        Acquisition device for lima camera.

        All parameters are directly matched with the lima device server
        """
        if not isinstance(device, lima.Lima):
            raise TypeError(
                "Device for LimaAcquisitionMaster must be an"
                " instance of a BLISS Lima controller"
            )

        self.parameters = locals().copy()
        del self.parameters["self"]
        del self.parameters["device"]
        del self.parameters["save_flag"]
        del self.parameters["keys"]
        del self.parameters["prepare_once"]
        del self.parameters["start_once"]
        self.parameters.update(keys)

        trigger_type = (
            AcquisitionMaster.SOFTWARE
            if "INTERNAL" in acq_trigger_mode
            else AcquisitionMaster.HARDWARE
        )

        AcquisitionMaster.__init__(
            self,
            device.proxy,
            device.name,
            acq_nb_frames,
            trigger_type=trigger_type,
            prepare_once=prepare_once,
            start_once=start_once,
        )

        self._lima_controller = device
        self._reading_task = None
        self._image_channel = None
        self._last_image_ready = -1
        self._save_flag = save_flag
        self._latency = latency_time
        self.__sequence_index = 0
        self.__new_point_ready = 0
        self.__point_synchro = event.Event()

    def __iter__(self):
        nbpoints = self.npoints
        if nbpoints > 0:
            while self._last_image_ready < nbpoints:
                yield self
                self.__sequence_index += 1
        else:
            while True:
                yield self
                self.__sequence_index += 1

    def add_counter(self, counter):
        if counter.name != "image":
            raise ValueError("Lima master only supports the 'image' counter")
        self._image_channel = AcquisitionChannel(
            counter.name,
            counter.dtype,
            counter.shape,
            reference=True,
            data_node_type="lima",
        )
        self.channels.append(self._image_channel)

    @property
    def save_flag(self):
        return bool(self._save_flag and self._image_channel)

    def set_image_saving(self, directory, prefix, force_no_saving=False):
        if self._save_flag and not force_no_saving:
            self.parameters.setdefault("saving_mode", "AUTO_FRAME")
            self.parameters.setdefault("saving_format", "EDF")
            self.parameters.setdefault("saving_frame_per_file", 1)
            self.parameters.setdefault(
                "saving_directory", self._lima_controller.get_mapped_path(directory)
            )
            self.parameters.setdefault("saving_prefix", prefix)
            self.parameters.setdefault("saving_suffix", ".edf")
        else:
            self.parameters.setdefault("saving_mode", "MANUAL")

    def prepare(self):
        if self.__sequence_index > 0 and self.prepare_once:
            return
        self.__new_point_ready = 0.

        if self._image_channel:
            self._image_channel.description.update(self.parameters)

        for param_name, param_value in self.parameters.iteritems():
            setattr(self.device, param_name, param_value)

        self.device.prepareAcq()

        signed, depth, w, h = self.device.image_sizes
        if self._image_channel:
            self._image_channel.dtype = LIMA_DTYPE[(signed, depth)]
            self._image_channel.shape = (h, w)
            status = self._get_lima_status()
            status["server_url"] = get_fqn(self.device)
            self._image_channel.emit(status)

        self._latency = self.device.latency_time
        self._last_image_ready = -1

        if self._reading_task:
            self._reading_task.kill()
            self._reading_task = None

    def start(self):
        if (
            self.trigger_type == AcquisitionMaster.SOFTWARE and self.parent
        ):  # otherwise top master trigger would never be called
            return

        self.trigger()

    def stop(self):
        self.device.stopAcq()
        self.__point_synchro.set()

    def wait_ready(self):
        acq_trigger_mode = self.parameters.get("acq_trigger_mode", "INTERNAL_TRIGGER")
        if self.prepare_once and acq_trigger_mode in (
            "INTERNAL_TRIGGER_MULTI",
            "EXTERNAL_GATE",
            "EXTERNAL_TRIGGER_MULTI",
        ):
            if self._lima_controller.camera.synchro_mode == "TRIGGER":
                while (
                    self.device.acq_status.lower() == "running"
                    and not self.device.ready_for_next_image
                ):
                    gevent.idle()
            else:
                if self.device.acq_status.lower() == "running":
                    while (
                        self.__new_point_ready == 0
                        and self.device.acq_status.lower() == "running"
                    ):
                        self.__point_synchro.clear()
                        self.__point_synchro.wait()
                    self.__new_point_ready -= 1
        # Just read if there is an exception
        # in the reading task
        self.wait_reading(block=self.npoints == 1)

    def trigger(self):
        self.trigger_slaves()

        if self.__sequence_index > 0 and self.start_once:
            return

        self.device.startAcq()

        if self._reading_task is None:
            self._reading_task = gevent.spawn(self.reading)

    def _get_lima_status(self):
        attr_names = [
            "buffer_max_number",
            "last_image_acquired",
            "last_image_ready",
            "last_counter_ready",
            "last_image_saved",
        ]
        return {
            name: att.value
            for name, att in zip(attr_names, self.device.read_attributes(attr_names))
        }

    def reading(self):
        try:
            last_image_acquired = -1
            while True:
                acq_state = self.device.acq_status.lower()
                status = self._get_lima_status()
                status["acq_state"] = acq_state
                if acq_state == "running":
                    if status["last_image_ready"] != self._last_image_ready:
                        if self._image_channel:
                            self._image_channel.emit(status)
                        self._last_image_ready = status["last_image_ready"]
                    if status["last_image_acquired"] != last_image_acquired:
                        last_image_acquired = status["last_image_acquired"]
                        self.__new_point_ready += 1
                        self.__point_synchro.set()

                    gevent.sleep(max(self.parameters["acq_expo_time"] / 10.0, 10e-3))
                else:
                    break
            if self._image_channel:
                self._image_channel.emit(status)
            if acq_state == "fault":
                raise RuntimeError(
                    "Device %s (%s) is in Fault state"
                    % (self.device, self.device.user_detector_name)
                )
            self._reading_task = None
        except:
            if self._image_channel:
                self._image_channel.emit({"acq_state": "fault"})
            raise
        finally:
            self.__point_synchro.set()

    def wait_reading(self, block=True):
        if self._reading_task is None:
            return True
        try:
            return self._reading_task.get(block=block)
        except gevent.Timeout:
            return False
