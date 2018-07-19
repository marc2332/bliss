# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import logging
import errno
import os

from bliss.scanning.chain import AcquisitionDevice, AcquisitionMaster
from bliss.common.event import connect

class AcquisitionMasterEventReceiver(object):
    def __init__(self, master, slave, parent):
        self._master = master
        self._parent = parent

        for signal in ('start', 'end'):
            connect(slave, signal, self.on_event)
            for channel in slave.channels:
                connect(channel, 'new_data', self.on_event)
    @property
    def parent(self):
        return self._parent

    @property
    def master(self):
        return self._master

    def on_event(self, event_dict=None, signal=None, sender=None):
        raise NotImplementedError


class AcquisitionDeviceEventReceiver(object):
    def __init__(self, device, parent):
        self._device = device
        self._parent = parent

        for signal in ('start', 'end'):
            connect(device, signal, self.on_event)
            for channel in device.channels:
                connect(channel, 'new_data', self.on_event)

    @property
    def parent(self):
        return self._parent

    @property
    def device(self):
        return self._device

    def on_event(self, event_dict=None, signal=None, sender=None):
        raise NotImplementedError


class FileWriter(object):
    def __init__(self, root_path,
                 windows_path_mapping=None,
                 detector_temporay_path=None,
                 master_event_receiver=None,
                 device_event_receiver=None,
                 **keys):
        """ A default way to organize file structure

        windows_path_mapping -- transform unix path to windows
        i.e: {'/data/visitor/':'Y:/'}
        detector_temporay_path -- temporary path for a detector
        i.e: {detector: {'/data/visitor':'/tmp/data/visitor'}}
        """
        self.log = logging.getLogger(type(self).__name__)
        self._root_path = root_path
        self._windows_path_mapping = windows_path_mapping or dict()
        self._detector_temporay_path = detector_temporay_path or dict()
        if None in (master_event_receiver, device_event_receiver):
            raise ValueError(
                "master_event_receiver and device_event_receiver keyword arguments have to be specified.")
        self._master_event_receiver = master_event_receiver
        self._device_event_receiver = device_event_receiver
        self._event_receivers = list()
        self.closed = True

    @property
    def root_path(self):
        return self._root_path

    def create_path(self, scan_recorder):
        path_suffix = scan_recorder.node.name
        full_path = os.path.join(self._root_path, path_suffix)
        try:
            os.makedirs(full_path)
        except OSError as exc:  # Python >2.5
            if exc.errno == errno.EEXIST and os.path.isdir(full_path):
                pass
            else:
                raise
        return full_path

    def new_file(self, scan_file_dir, scan_recorder):
        pass

    def new_master(self, master, scan_file_dir):
        raise NotImplementedError

    def prepare(self, scan_recorder, scan_info, devices_tree):
        if not self.closed:
            self.log.warn(
                'Last write may not have finished correctly. I will cleanup')

        scan_file_dir = self.create_path(scan_recorder)

        self.new_file(scan_file_dir, scan_recorder)

        self._event_receivers = list()

        for dev, node in scan_recorder.nodes.iteritems():
            if isinstance(dev, AcquisitionMaster):
                master_entry = self.new_master(dev, scan_file_dir)

                dev.prepare_saving(scan_recorder.node.name, scan_file_dir)

                for slave in dev.slaves:
                    if isinstance(slave, AcquisitionDevice):
                        self._event_receivers.append(
                            self._device_event_receiver(slave, master_entry))
                    elif isinstance(slave, AcquisitionMaster):
                        self._event_receivers.append(
                            self._master_event_receiver(slave, slave, master_entry))
                self._event_receivers.append(
                    self._device_event_receiver(dev, master_entry))
        self._closed = False

    def close(self):
        self.closed = True

    def get_scan_entries(self):
        """
        Should return all scan entries from this path
        """
        return []
