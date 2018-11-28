# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from ..chain import AcquisitionMaster, AcquisitionChannel
from bliss.controllers import lima
from bliss.common.tango import get_fqn
import gevent
from gevent import event
from gevent import lock
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
        wait_frame_id=None,
        **keys
    ):
        """
        Acquisition device for lima camera.

        All parameters are directly matched with the lima device server

        **wait_frame_id** it's the frame number to wait for the next
        sequence in case the synchronisation is base on data.
        i.e: for a mesh with one fast axes (continous), 
        combine with one slow step motor. if you do 20 images per line,
        the wait_frame_id must be equal to range(0,TOTAL_IMAGE,IMAGE_PER_LINE).
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
        del self.parameters["wait_frame_id"]
        self.parameters.update(keys)
        if wait_frame_id is None:
            wait_frame_id = range(acq_nb_frames)
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
        self._save_flag = save_flag
        self._latency = latency_time
        self.__last_image_acquired = -1
        self.__sequence_index = 0
        self.__image_status = (False, -1)
        self.__lock = lock.Semaphore()
        self._ready_event = event.Event()
        self.__wait_frame_id = wait_frame_id
        self.__current_wait_frame_id = -1

    @property
    def fast_synchro(self):
        return self._lima_controller.camera.synchro_mode == "TRIGGER"

    def __iter__(self):
        internal_trigger_mode = (
            self.parameters.get("acq_trigger_mode") == "INTERNAL_TRIGGER"
        )
        wait_frame_id_iter = iter(self.__wait_frame_id)
        if self.npoints == 0 or internal_trigger_mode:
            # infinite number of frames (npoints == 0)
            # or internal trigger (one trigger for all frames)
            # in this case there is only 1 iteration for the
            # whole acquisition
            while True:
                self.__current_wait_frame_id = next(wait_frame_id_iter)
                yield self
                if internal_trigger_mode:
                    break
                self.__sequence_index += 1
        else:
            # last image acquired starts at -1, 0 is the first image acquired
            total_frames = self.npoints - 1
            while True:
                # in case of fast synchro, we know we can take a new trigger before
                # last image acquired is updated in Limaself.__current_wait_frame_id
                new_image_acquired, last_image_acquired = self.__image_status
                if self.fast_synchro:
                    if new_image_acquired:
                        last_image_acquired -= 1
                if last_image_acquired < total_frames:
                    self.__current_wait_frame_id = next(wait_frame_id_iter)
                    yield self
                    self.__sequence_index += 1
                else:
                    break

    def add_counter(self, counter):
        if counter.name != "image":
            raise ValueError("Lima master only supports the 'image' counter")
        self._image_channel = AcquisitionChannel(
            counter,
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

        if self._image_channel:
            self._image_channel.description.update(self.parameters)

        for param_name, param_value in self.parameters.items():
            setattr(self.device, param_name, param_value)

        self.wait_slaves_prepare()
        self.device.video_active = True
        self.device.prepareAcq()

        signed, depth, w, h = self.device.image_sizes
        if self._image_channel:
            self._image_channel.dtype = LIMA_DTYPE[(signed, depth)]
            self._image_channel.shape = (h, w)
            status = self._get_lima_status()
            status["server_url"] = get_fqn(self.device)
            self._image_channel.emit(status)

        self._latency = self.device.latency_time

    def start(self):
        if (
            self.trigger_type == AcquisitionMaster.SOFTWARE and self.parent
        ):  # otherwise top master trigger would never be called
            return

        self.trigger()

    def stop(self):
        self.device.stopAcq()

    def trigger_ready(self):
        return True

    def wait_ready(self):
        acq_state = self.device.acq_status.lower()
        while acq_state == "running":
            if self.fast_synchro:
                if self.device.ready_for_next_image:
                    break
                gevent.idle()
            else:
                self._ready_event.clear()
                new_image_acquired, last_image_acquired = self.__image_status
                if self.__current_wait_frame_id == last_image_acquired:
                    break
                elif last_image_acquired > self.__current_wait_frame_id:
                    raise RuntimeError(
                        "Synchronisation error, **wait_frame_id** is wrongly set for this scan"
                    )
                self._ready_event.wait()
            acq_state = self.device.acq_status.lower()

    def trigger(self):
        self.trigger_slaves()

        if self.__sequence_index > 0 and self.start_once:
            return

        with self.__lock:
            self.device.startAcq()

            acq_trigger_mode = self.parameters.get(
                "acq_trigger_mode", "INTERNAL_TRIGGER"
            )

        if not self._reading_task:
            self._reading_task = gevent.spawn(self.reading)

    def _get_lima_status(self):
        with self.__lock:
            attr_names = [
                "buffer_max_number",
                "last_image_acquired",
                "last_image_ready",
                "last_counter_ready",
                "last_image_saved",
                "ready_for_next_image",
            ]
            return {
                name: att.value
                for name, att in zip(
                    attr_names, self.device.read_attributes(attr_names)
                )
            }

    def reading(self):
        acq_trigger_mode = self.parameters.get("acq_trigger_mode", "INTERNAL_TRIGGER")
        last_image_ready = -1
        last_image_acquired = -1
        try:
            while True:
                acq_state = self.device.acq_status.lower()
                status = self._get_lima_status()
                status["acq_state"] = acq_state
                if acq_trigger_mode == "INTERNAL_TRIGGER":
                    for key in (
                        "last_image_acquired",
                        "last_image_ready",
                        "last_counter_ready",
                        "last_image_saved",
                    ):
                        status[key] += self.__sequence_index * self.npoints

                if status["last_image_ready"] != last_image_ready:
                    last_image_ready = status["last_image_ready"]
                    if self._image_channel:
                        self._image_channel.emit(status)

                if self.fast_synchro:
                    if status["ready_for_next_image"]:
                        if status["last_image_acquired"] != last_image_acquired:
                            last_image_acquired = status["last_image_acquired"]
                            new_image_acquired = True
                        else:
                            new_image_acquired = False
                        self.__image_status = (new_image_acquired, last_image_acquired)
                else:
                    if status["last_image_acquired"] != last_image_acquired:
                        last_image_acquired = status["last_image_acquired"]
                        self.__image_status = (True, last_image_acquired)
                        self._ready_event.set()

                if acq_state == "running":
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
        except:
            if self._image_channel:
                self._image_channel.emit({"acq_state": "fault"})
            raise
        finally:
            self._ready_event.set()

    def wait_reading(self):
        if self._reading_task is None:
            return True
        return self._reading_task.get()
