# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from itertools import count
import gevent
from gevent import event
from gevent import lock
import numpy
from collections import OrderedDict

from bliss.scanning.chain import AcquisitionMaster
from bliss.scanning.channel import AcquisitionChannel
from bliss.controllers import lima
from bliss.common.tango import get_fqn
from bliss.scanning.acquisition.counter import IntegratingCounterAcquisitionSlave

LIMA_DTYPE = {
    (0, 2): numpy.uint16,
    (1, 2): numpy.int16,
    (0, 4): numpy.uint32,
    (1, 4): numpy.int32,
    (0, 1): numpy.uint8,
    (1, 1): numpy.int8,
}


class LimaAcquisitionMaster(AcquisitionMaster):
    def __init__(self, device, ctrl_params=None, **acq_params):
        """
        Acquisition device for lima camera.

        All parameters are directly matched with the lima device server

        **wait_frame_id** it's the frame number to wait for the next
        sequence in case the synchronisation is base on data.
        i.e: for a mesh with one fast axes (continous), 
        combine with one slow step motor. if you do 20 images per line,
        the wait_frame_id must be equal to range(0,TOTAL_IMAGE,IMAGE_PER_LINE).
        """

        # ensure that ctrl-params have been completed
        ctrl_params = self.init_ctrl_params(device, ctrl_params)

        # !!! warning: validate params requires a completed ctrl_params dict
        self.acq_params = OrderedDict(self.validate_params(acq_params, ctrl_params))

        # deal with 'ONE_FILE_PER_SCAN' mode
        if ctrl_params.get("saving_frame_per_file") == -1:
            ctrl_params["saving_frame_per_file"] = self.acq_params["acq_nb_frames"]

        trigger_type = (
            AcquisitionMaster.SOFTWARE
            if "INTERNAL" in self.acq_params["acq_trigger_mode"]
            else AcquisitionMaster.HARDWARE
        )

        AcquisitionMaster.__init__(
            self,
            device,
            name=device.name,
            npoints=self.acq_params["acq_nb_frames"],
            trigger_type=trigger_type,
            prepare_once=self.acq_params["prepare_once"],
            start_once=self.acq_params["start_once"],
            ctrl_params=ctrl_params,
        )

        self._lima_controller = device
        self._reading_task = None
        self._image_channel = None
        self._latency = self.acq_params["latency_time"]
        self.__last_image_acquired = -1
        self.__sequence_index = 0
        self.__image_status = (False, -1)
        self.__lock = lock.Semaphore()
        self._ready_event = event.Event()

        wait_frame_id = self.acq_params.pop("wait_frame_id", None)
        if wait_frame_id is None:
            tmp = self.acq_params["acq_nb_frames"]

            def wait_frame_id_iter():
                while True:
                    yield tmp - 1

            self.__wait_frame_id = wait_frame_id_iter()
        else:
            self.__wait_frame_id = wait_frame_id

    @staticmethod
    def get_param_validation_schema():

        # lima_ctrl_param_schema = {}

        lima_master_base_schema = {
            "prepare_once": {"type": "boolean", "default": False},
            "start_once": {"type": "boolean", "default": False},
            "acq_nb_frames": {"type": "integer", "default": 1},
            "acq_expo_time": {"type": "number", "default": 1},
            "acq_trigger_mode": {"type": "string", "default": "INTERNAL_TRIGGER"},
            "latency_time": {"type": "integer", "default": 0},
            "wait_frame_id": {
                "required": True,
                "nullable": True,
                "oneof": [
                    {
                        "default": None,
                        "nullable": True,
                        "dependencies": {"start_once": False},
                    },
                    {"required": True, "dependencies": {"start_once": True}},
                ],
            },
            "saving_statistics_history": {},
            "saving_mode": {"type": "string"},
            "stat_history": {
                "type": "number",
                "default_setter": lambda x: x["acq_nb_frames"],
            },
        }

        lima_master_no_acc_schema = {
            "acq_mode": {"default": "SINGLE", "type": "string", "value": "SINGLE"}
        }

        lima_master_acc_schema = {
            "acq_mode": {"type": "string", "required": True},
            "acc_time_mode": {"default": "LIVE", "allowed": ["LIVE"]},
            "acc_max_expo_time": {"type": "number", "default": 1.},
        }

        lima_master_schema = {
            "acq_params": {
                "type": "dict",
                "oneof": [
                    {
                        "dependencies": {"acq_params.acq_mode": "SINGLE"},
                        "schema": {
                            **lima_master_base_schema,
                            **lima_master_no_acc_schema,
                        },
                    },
                    {
                        "dependencies": {"acq_params.acq_mode": "ACCUMULATION"},
                        "schema": {**lima_master_base_schema, **lima_master_acc_schema},
                    },
                ],
            },
            "ctrl_params": {
                "type": "dict",
                #  "schema": lima_ctrl_param_schema,
                "default": {},
            },
        }
        return lima_master_schema

    @property
    def fast_synchro(self):
        return self._lima_controller.camera.synchro_mode == "TRIGGER"

    def __iter__(self):
        internal_trigger_mode = (
            self.acq_params.get("acq_trigger_mode") == "INTERNAL_TRIGGER"
        )
        wait_frame_id_iter = iter(self.__wait_frame_id)
        if self.npoints == 0 or internal_trigger_mode:
            # infinite number of frames (npoints == 0)
            # or internal trigger (one trigger for all frames)
            # in this case there is only 1 iteration for the
            # whole acquisition
            if self.npoints == 0:
                wait_frame_id_iter = count()
            image_waiting_number = 0
            while True:
                try:
                    self.__current_wait_frame_id = next(wait_frame_id_iter)
                except StopIteration as e:
                    e.args = (
                        self.device.name,
                        *e.args,
                        "Synchronisation error, **wait_frame_id** is wrongly set for this scan",
                    )
                    raise
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
                    try:
                        self.__current_wait_frame_id = next(wait_frame_id_iter)
                    except StopIteration as e:
                        e.args = (
                            self.device.name,
                            *e.args,
                            "Synchronisation error, **wait_frame_id** is wrongly set for this scan",
                        )
                        raise
                    yield self
                    self.__sequence_index += 1
                else:
                    break
        self._ready_event.clear()
        self.__image_status = (False, -1)

    def add_counter(self, counter):
        # def _do_add_counter(self, counter):
        if counter in self._counters:
            return

        if counter.name != "image":
            raise ValueError("Lima master only supports the 'image' counter")

        self._image_channel = AcquisitionChannel(
            f"{self.name}:{counter.name}",
            counter.dtype,
            counter.shape,
            reference=True,
            data_node_type="lima",
        )
        self.channels.append(self._image_channel)
        self._counters[counter].append(self.channels[-1])

    @property
    def save_flag(self):
        return bool(self._image_channel)

    def set_image_saving(self, directory, prefix, force_no_saving=False):
        if self.save_flag and not force_no_saving:
            self.acq_params["saving_mode"] = self.acq_params.setdefault(
                "saving_mode", "AUTO_FRAME"
            )
            assert self.acq_params["saving_mode"] != "MANUAL"
            self.acq_params["saving_directory"] = self._lima_controller.get_mapped_path(
                directory
            )
            self._unmapped_path = directory
            self.acq_params.setdefault("saving_prefix", prefix)
        else:
            self.acq_params["saving_mode"] = "MANUAL"

    def prepare(self):
        if self.__sequence_index > 0 and self.prepare_once:
            return

        if self._image_channel:
            self._image_channel.description.update(
                {"acq_trigger_mode": self.acq_params["acq_trigger_mode"]}
            )

            if self.acq_params["saving_mode"] != "MANUAL":
                if hasattr(self.device.proxy, "lima_version"):
                    lima_version = self.device.proxy.lima_version
                    user_instrument_name = self.device.proxy.user_instrument_name

                else:
                    lima_version = "<1.9.1"
                    user_instrument_name = "instrument"

                self._image_channel.description.update(
                    {
                        "saving_format": self.ctrl_params["saving_format"],
                        "saving_frame_per_file": self.ctrl_params[
                            "saving_frame_per_file"
                        ],
                        "saving_suffix": self.ctrl_params["saving_suffix"],
                        "saving_mode": self.acq_params["saving_mode"],
                        "saving_directory": self._unmapped_path,
                        "saving_prefix": self.acq_params["saving_prefix"],
                        "user_detector_name": self.device.proxy.user_detector_name,
                        "user_instrument_name": user_instrument_name,
                        "lima_version": lima_version,
                    }
                )

        # make sure that parameters are in the good order for lima:
        self.acq_params.move_to_end("acq_mode", last=False)
        if "saving_prefix" in self.acq_params:
            self.acq_params.move_to_end("saving_prefix", last=True)

        for param_name, param_value in self.acq_params.items():
            if not (param_value is None):
                setattr(self.device.proxy, param_name, param_value)

        self.device.proxy.video_source = "LAST_IMAGE"

        self.wait_slaves_prepare()
        if self.device.proxy.video_live is True:
            self._lima_controller.stop_bpm_live()

        self.device.proxy.video_active = True
        self._lima_controller.prepareAcq()

        signed, depth, w, h = self.device.proxy.image_sizes
        if self._image_channel:
            self._image_channel.dtype = LIMA_DTYPE[(signed, depth)]
            self._image_channel.shape = (h, w)
            status = self._get_lima_status()
            status["server_url"] = get_fqn(self.device.proxy)
            self._image_channel.emit(status)

        self._latency = self.device.proxy.latency_time

    def start(self):
        if (
            self.trigger_type == AcquisitionMaster.SOFTWARE and self.parent
        ):  # otherwise top master trigger would never be called
            return

        self.trigger()

    def stop(self):
        self._lima_controller.stopAcq()

    def trigger_ready(self):
        return True

    def wait_ready(self):
        acq_state = self.device.proxy.acq_status.lower()
        while acq_state == "running":
            if self.fast_synchro:
                if self.device.proxy.ready_for_next_image:
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
            acq_state = self.device.proxy.acq_status.lower()

    def trigger(self):
        self.trigger_slaves()

        if self.__sequence_index > 0 and self.start_once:
            return

        with self.__lock:
            self._lima_controller.startAcq()

            acq_trigger_mode = self.acq_params.get(
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
                    attr_names, self.device.proxy.read_attributes(attr_names)
                )
            }

    def reading(self):
        acq_trigger_mode = self.acq_params.get("acq_trigger_mode", "INTERNAL_TRIGGER")
        last_image_ready = -1
        last_image_acquired = -1
        try:
            while True:
                acq_state = self.device.proxy.acq_status.lower()
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
                    gevent.sleep(max(self.acq_params["acq_expo_time"] / 10.0, 10e-3))
                else:
                    break
            if self._image_channel:
                self._image_channel.emit(status)
            if acq_state == "fault":
                raise RuntimeError(
                    "Device %s (%s) is in Fault state"
                    % (self.device.proxy, self.device.proxy.user_detector_name)
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

    def fill_meta_at_scan_end(self, scan_meta):
        return {"acq_parameters": self.acq_params, "ctrl_parameters": self.ctrl_params}


class RoiCountersAcquisitionSlave(IntegratingCounterAcquisitionSlave):
    def prepare_device(self):
        self.device.upload_rois()


class BpmAcquisitionSlave(IntegratingCounterAcquisitionSlave):
    def prepare_device(self):
        self.device._proxy.Start()

    def start_device(self):
        self.device._proxy.Start()

    def stop_device(self):
        self.device._proxy.Stop()
