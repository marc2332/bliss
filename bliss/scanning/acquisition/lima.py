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

        device_name = device.name
        if isinstance(device, lima.Lima):
            device = device.proxy

        AcquisitionMaster.__init__(self, device, device_name, acq_nb_frames, #device.user_detector_name, acq_nb_frames,
                                   trigger_type=trigger_type,
                                   prepare_once=prepare_once, start_once=start_once)

        self._image_channel = AcquisitionChannel('image', None, (0,0), reference=True, data_node_type='lima')
        self.channels.append(self._image_channel)

        self.save_flag = save_flag
        self._reading_task = None
        self._latency = latency_time
        self._last_image_ready = -1
        
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
        self._image_channel.description.update(self.parameters) 

        for param_name, param_value in self.parameters.iteritems():
            setattr(self.device, param_name, param_value)

        self.device.prepareAcq()

        signed, depth, w, h = self.device.image_sizes
        self._image_channel.dtype = LIMA_DTYPE[(signed, depth)]
        self._image_channel.shape = (h, w)

        self._latency = self.device.latency_time
        self._last_image_ready = -1

        if self._reading_task:
            self._reading_task.kill()
            self._reading_task = None

        server_url = self.device.dev_name()
        self._image_channel.emit({ "server_url": server_url })

    def start(self):
        if(self.trigger_type == AcquisitionMaster.SOFTWARE and
           self.parent):    # top master trigger will be never called otherwise
            return

        self.trigger()

    def stop(self):
        self.device.stopAcq()

    def wait_ready(self):
        acq_trigger_mode = self.parameters.get('acq_trigger_mode','INTERNAL_TRIGGER')
        
        if acq_trigger_mode == 'INTERNAL_TRIGGER_MULTI':
            while(self.device.acq_status.lower() == 'running' and
                  not self.device.ready_for_next_image):
                gevent.idle()

        self.wait_reading(block=(acq_trigger_mode!='INTERNAL_TRIGGER_MULTI'))

    def trigger(self):
        self.trigger_slaves()
        
        self.device.startAcq()

        if self._reading_task is None:
            self._reading_task = gevent.spawn(self.reading)

    def _get_lima_status(self):
        attr_names = ['buffer_max_number', 'last_image_acquired',
                      'last_image_ready', 'last_counter_ready', 'last_image_saved']
        return { name: att.value for name, att in zip(attr_names,
                                                      self.device.read_attributes(attr_names)) }

    def reading(self):
        while True:
            try:
                acq_state = self.device.acq_status.lower()
            except Exception:
                acq_state = 'fault'
            try:
                status = self._get_lima_status()
            except Exception:
                status = dict()
            status["acq_state"] = acq_state
            if acq_state == 'running':
                if status['last_image_ready'] != self._last_image_ready:
                    self._image_channel.emit(status)
                    self._last_image_ready = status['last_image_ready']
                gevent.sleep(max(self.parameters['acq_expo_time'] / 10.0, 10e-3))
            else:
                break
        
        try:
            self._image_channel.emit(status)
            if acq_state == 'fault':
                raise RuntimeError("Device %s (%s) is in Fault state" % (
                    self.device, self.device.user_detector_name))
        finally:
            self._reading_task = None
        
    def wait_reading(self, block=True):
        try:
            return self._reading_task.get(block=block) if self._reading_task is not None else True
        except gevent.Timeout:
            return False
