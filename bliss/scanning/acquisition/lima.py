# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from ..chain import AcquisitionMaster, AcquisitionChannel
from bliss.common.event import dispatcher
from bliss.controllers import lima
import gevent
import time
import numpy
import os

LIMA_DTYPE = {(0, 2): numpy.uint16,
              (1, 2): numpy.int16,
              (0, 4): numpy.uint32,
              (1, 4): numpy.int32,
              (0, 1): numpy.uint8,
              (1, 1): numpy.int8}


class LimaImageChannel(AcquisitionChannel):
    def __init__(self):
        AcquisitionChannel.__init__(self, 'image', None, ())

    def emit(self, data):
        pass


class LimaAcquisitionMaster(AcquisitionMaster):
    def __init__(self, device,
                 acq_nb_frames=1, acq_expo_time=1,
                 acq_trigger_mode="INTERNAL_TRIGGER", acq_mode="SINGLE",
                 acc_time_mode="LIVE", acc_max_expo_time=1, latency_time=0,
                 save_flag=False,
                 prepare_once=False, start_once=False,
                 **keys):
        """
        Acquisition device for lima camera.

        All parameters are directly matched with the lima device server
        """
        self.parameters = locals().copy()
        del self.parameters['self']
        del self.parameters['device']
        del self.parameters['save_flag']
        del self.parameters['keys']
        self.parameters.update(keys)

        trigger_type = AcquisitionMaster.SOFTWARE if 'INTERNAL' in acq_trigger_mode else AcquisitionMaster.HARDWARE

        if isinstance(device, lima.Lima):
            device = device.proxy

        AcquisitionMaster.__init__(self, device, device.user_detector_name, acq_nb_frames,
                                   trigger_type=trigger_type,
                                   prepare_once=prepare_once, start_once=start_once)

        self._image_channel = LimaImageChannel()
        self.channels.append(self._image_channel)

        self.save_flag = save_flag
        self._reading_task = None

    def prepare_saving(self, scan_name, scan_file_dir):
        camera_name = self.device.camera_type
        full_path = os.path.join(scan_file_dir, self.device.user_detector_name)

        if self.save_flag:
            self.parameters.setdefault('saving_mode', 'AUTO_FRAME')
            self.parameters.setdefault('saving_format', 'EDF')
            self.parameters.setdefault('saving_frame_per_file', 1)
            self.parameters.setdefault('saving_directory', full_path)
            self.parameters.setdefault(
                'saving_prefix', '%s_%s' % (scan_name, camera_name))
            self.parameters.setdefault('saving_suffix', '.edf')
        else:
            self.parameters.setdefault('saving_mode', 'MANUAL')

    def prepare(self):
        for param_name, param_value in self.parameters.iteritems():
            setattr(self.device, param_name, param_value)
        self.device.prepareAcq()
        signed, depth, w, h = self.device.image_sizes
        self.channels[1].dtype = LIMA_DTYPE[(signed, depth)]
        self.channels[1].shape = (h, w)

        self._latency = self.device.latency_time

        if self._reading_task:
            self._reading_task.kill()
            self._reading_task = None

    def start(self):
        if self.trigger_type == AcquisitionMaster.SOFTWARE:
            return
        self.trigger()

        if self._reading_task is None:
            self._reading_task = gevent.spawn(self.reading)

    def stop(self):
        self.device.stopAcq()

    def wait_ready(self):
        wait_start = time.time()
        while not self.device.ready_for_next_image:
            if (wait_start + self._latency) >= time.time():
                break
            else:
                gevent.idle()

        if self._reading_task is not None:
            try:
                # checkfor execption from reading task
                self._reading_task.get(block=False)
            except gevent.Timeout:
                pass

    def trigger(self):
        self.device.startAcq()

        if self.trigger_type == AcquisitionMaster.SOFTWARE:
            if self._reading_task is None:
                self._reading_task = gevent.spawn(self.reading)

    def reading(self):
        parameters = {"type": "lima/parameters", 'channel_data': dict()}
        parameters.update(self.parameters)
        dispatcher.send("new_data", self, parameters)

        while self.device.acq_status.lower() == 'running':
            dispatcher.send("new_ref", self, {"type": "lima/image",
                                              "last_image_acquired": self.device.last_image_acquired,
                                              "last_image_saved": self.device.last_image_saved,
                                              })
            gevent.sleep(max(self.parameters['acq_expo_time'] / 10.0, 10e-3))
        # TODO: self.dm.send_new_ref(self, {...}) ? or DataManager.send_new_ref(...) ?
        dispatcher.send("new_ref", self, {"type": "lima/image",
                                          "last_image_acquired": self.device.last_image_acquired,
                                          "last_image_saved": self.device.last_image_saved,
                                          })
        if self.device.acq_status.lower() == 'fault':
            raise RuntimeError("Device %s (%s) is in Fault state" % (
                self.device, self.device.user_detector_name))
        self._reading_task = None
