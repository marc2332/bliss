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


from bliss.scanning.chain import AcquisitionMaster
from bliss.scanning.channel import AcquisitionChannel
from bliss.controllers import lima
from bliss.common.tango import get_fqn


from bliss.scanning.chain import ChainNode

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
        acq_mode="SINGLE",
        acq_nb_frames=1,
        acq_expo_time=1,
        acq_trigger_mode="INTERNAL_TRIGGER",
        acc_time_mode="LIVE",
        acc_max_expo_time=1,
        latency_time=0,
        save_flag=False,
        prepare_once=False,
        start_once=False,
        wait_frame_id=None,
        ctrl_params=None,
        **keys,
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
            wait_frame_id = [acq_nb_frames - 1]
        trigger_type = (
            AcquisitionMaster.SOFTWARE
            if "INTERNAL" in acq_trigger_mode
            else AcquisitionMaster.HARDWARE
        )

        AcquisitionMaster.__init__(
            self,
            device,
            name=device.name,
            npoints=acq_nb_frames,
            trigger_type=trigger_type,
            prepare_once=prepare_once,
            start_once=start_once,
            ctrl_params=ctrl_params,
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
            if self.npoints == 0:
                wait_frame_id_iter = count()
            image_waiting_number = 0
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
        return bool(self._save_flag and self._image_channel)

    def set_image_saving(self, directory, prefix, force_no_saving=False):
        if self._save_flag and not force_no_saving:
            self.parameters["saving_mode"] = self.parameters.setdefault(
                "saving_mode", "AUTO_FRAME"
            )
            assert self.parameters["saving_mode"] != "MANUAL"
            self.parameters["saving_directory"] = self._lima_controller.get_mapped_path(
                directory
            )
            self.parameters.setdefault("saving_format", "EDF")
            self.parameters.setdefault("saving_frame_per_file", 1)
            self.parameters.setdefault("saving_prefix", prefix)
            self.parameters.setdefault("saving_suffix", ".edf")
        else:
            self.parameters["saving_mode"] = "MANUAL"

    def prepare(self):
        if self.__sequence_index > 0 and self.prepare_once:
            return

        if self._image_channel:
            self._image_channel.description.update(self.parameters)

        for param_name, param_value in self.parameters.items():
            setattr(self.device.proxy, param_name, param_value)

        self.wait_slaves_prepare()
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
                    attr_names, self.device.proxy.read_attributes(attr_names)
                )
            }

    def reading(self):
        acq_trigger_mode = self.parameters.get("acq_trigger_mode", "INTERNAL_TRIGGER")
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
                    gevent.sleep(max(self.parameters["acq_expo_time"] / 10.0, 10e-3))
                else:
                    break
            if self._image_channel:
                self._image_channel.emit(status)
            if acq_state == "fault":
                raise RuntimeError(
                    "Device %s (%s) is in Fault state"
                    % (self.device.proxy, self.device.user_detector_name)
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
        scan_meta.instrument.set(
            self,
            {self.name: {"lima_parameters": self.parameters, "NX_class": "NXdetector"}},
        )


class LimaChainNode(ChainNode):
    def _get_default_chain_parameters(self, scan_params, acq_params):

        # Extract information
        npoints = acq_params.get("acq_nb_frames", scan_params.get("npoints", 1))

        try:
            acq_expo_time = acq_params["acq_expo_time"]
        except:
            acq_expo_time = scan_params["count_time"]

        if "INTERNAL_TRIGGER_MULTI" in self.controller.available_triggers:
            default_trigger_mode = "INTERNAL_TRIGGER_MULTI"
        else:
            default_trigger_mode = "INTERNAL_TRIGGER"

        acq_trigger_mode = acq_params.get("acq_trigger_mode", default_trigger_mode)

        prepare_once = acq_trigger_mode in (
            "INTERNAL_TRIGGER_MULTI",
            "EXTERNAL_GATE",
            "EXTERNAL_TRIGGER_MULTI",
        )
        start_once = acq_trigger_mode not in (
            "INTERNAL_TRIGGER",
            "INTERNAL_TRIGGER_MULTI",
        )

        data_synchronisation = scan_params.get("data_synchronisation", False)
        if data_synchronisation:
            prepare_once = start_once = False

        acq_nb_frames = npoints if prepare_once else 1

        stat_history = npoints

        # ---Temporary fix should be moved to controller parameters --------
        saving_format = acq_params.get("saving_format", "EDF")
        saving_frame_per_file = acq_params.get("saving_frame_per_file", 1)
        saving_suffix = acq_params.get("saving_suffix", ".edf")

        # Return required parameters
        params = {}
        params["acq_nb_frames"] = acq_nb_frames
        params["acq_expo_time"] = acq_expo_time
        params["acq_trigger_mode"] = acq_trigger_mode
        params["acq_mode"] = acq_params.get("acq_mode", "SINGLE")
        params["acc_max_expo_time"] = acq_params.get("acc_max_expo_time", 1.)
        params["save"] = acq_params.get(
            "save", True
        )  # => key != AcqObj keyword and location not well defined  !
        params["wait_frame_id"] = range(acq_nb_frames)
        params["prepare_once"] = prepare_once
        params["start_once"] = start_once
        params["stat_history"] = stat_history

        # ---Temporary fix should be moved to controller parameters --------
        params["saving_format"] = saving_format
        params["saving_frame_per_file"] = saving_frame_per_file
        params["saving_suffix"] = saving_suffix

        return params

    def get_acquisition_object(self, acq_params, ctrl_params=None):

        # --- Warn user if an unexpected is found in acq_params
        expected_keys = [
            "acq_mode",
            "acq_nb_frames",
            "acq_expo_time",
            "acq_trigger_mode",
            "acc_max_expo_time",
            "prepare_once",
            "start_once",
            "wait_frame_id",
            "acc_time_mode",
            "latency_time",
            "save",
            "stat_history",
            "saving_format",  # ---Temporary fix should be moved to controller parameters
            "saving_frame_per_file",  # ---Temporary fix should be moved to controller parameters
            "saving_suffix",  # ---Temporary fix should be moved to controller parameters
        ]
        for key in acq_params.keys():
            if key not in expected_keys:
                print(
                    f"=== Warning: unexpected key '{key}' found in acquisition parameters for LimaAcquisitionMaster({self.controller}) ==="
                )

        # --- MANDATORY PARAMETERS -------------------------------------
        acq_mode = acq_params["acq_mode"]
        acq_nb_frames = acq_params["acq_nb_frames"]
        acq_expo_time = acq_params["acq_expo_time"]
        acq_trigger_mode = acq_params["acq_trigger_mode"]
        prepare_once = acq_params["prepare_once"]
        start_once = acq_params["start_once"]
        # wait_frame_id = acq_params["wait_frame_id"]

        if acq_mode == "ACCUMULATION":
            acc_max_expo_time = acq_params["acc_max_expo_time"]
        else:
            # acc_max_expo_time = self.controller.acc_max_expo_time
            acc_max_expo_time = 1.0

        # --- PARAMETERS WITH DEFAULT VALUE -----------------------------
        stat_history = acq_params.get("stat_history", acq_nb_frames)
        wait_frame_id = acq_params.get("wait_frame_id", range(acq_nb_frames))
        acc_time_mode = acq_params.get("acc_time_mode", "LIVE")
        latency_time = acq_params.get("latency_time", 0)
        save_flag = acq_params.get(
            "save", True
        )  # => key != AcqObj keyword  and location not well defined  !

        # ---Temporary fix should be moved to controller parameters --------
        saving_format = acq_params.get("saving_format", "EDF")
        saving_frame_per_file = acq_params.get("saving_frame_per_file", 1)
        saving_suffix = acq_params.get("saving_suffix", ".edf")

        return LimaAcquisitionMaster(
            self.controller,
            acq_mode=acq_mode,
            acq_nb_frames=acq_nb_frames,
            acq_expo_time=acq_expo_time,
            acq_trigger_mode=acq_trigger_mode,
            acc_time_mode=acc_time_mode,
            acc_max_expo_time=acc_max_expo_time,
            latency_time=latency_time,
            save_flag=save_flag,
            prepare_once=prepare_once,
            start_once=start_once,
            wait_frame_id=wait_frame_id,
            saving_statistics_history=stat_history,
            saving_format=saving_format,  # => temp fix should be moved to controller parameters
            saving_frame_per_file=saving_frame_per_file,  # => temp fix should be moved to controller parameters
            saving_suffix=saving_suffix,  # => temp fix should be moved to controller parameters
            ctrl_params=ctrl_params,
        )
