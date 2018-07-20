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

class _EventReceiver(object):
    def __init__(self, parent_entry, callback):
        self.parent_entry = parent_entry
        self.callback = callback

    def __call__(self, event_dict=None, signal=None, sender=None):
        if callable(self.callback):
            self.callback(self.parent_entry, event_dict, signal, sender)

class FileWriter(object):
    def __init__(self, root_path,
                 windows_path_mapping=None,
                 detector_temporay_path=None,
                 master_event_callback=None,
                 device_event_callback=None,
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
        self._master_event_callback = master_event_callback
        self._device_event_callback = device_event_callback
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

    def add_reference(self, master_entry, referenced_master_entry):
        pass

    def _prepare_callbacks(self, device, master_entry, callback):
        ev_receiver = _EventReceiver(master_entry, callback)
        for signal in ('start', 'end'):
            connect(device, signal, ev_receiver)
        for channel in device.channels:
            connect(channel, 'new_data', ev_receiver)
        self._event_receivers.append(ev_receiver)

    def prepare(self, scan_recorder, scan_info, devices_tree):
        if not self.closed:
            self.log.warn(
                'Last write may not have finished correctly. I will cleanup')

        scan_file_dir = self.create_path(scan_recorder)

        self.new_file(scan_file_dir, scan_recorder)
        master_entries = {}
  
        self._event_receivers = []

        for dev, node in scan_recorder.nodes.iteritems():
            if isinstance(dev, AcquisitionMaster):
                try:
                    master_entry = master_entries[dev]
                except KeyError:
                    master_entry = self.new_master(dev, scan_file_dir)
                    master_entries[dev] = master_entry
                
                self._prepare_callbacks(dev, master_entry, self._master_event_callback)

                dev.prepare_saving(scan_recorder.node.name, scan_file_dir)

                for slave in dev.slaves:
                    if isinstance(slave, AcquisitionDevice) and \
                        callable(self._device_event_callback):
                        self._prepare_callbacks(slave, master_entry, self._device_event_callback)
                    elif isinstance(slave, AcquisitionMaster):
                        try:
                            referenced_master_entry = master_entries[slave]
                        except KeyError:
                            referenced_master_entry = self.new_master(slave, scan_file_dir)
                            master_entries[slave] = referenced_master_entry
                        self.add_reference(master_entry, referenced_master_entry)
        self._closed = False

    def close(self):
        self.closed = True

    def get_scan_entries(self):
        """
        Should return all scan entries from this path
        """
        return []
