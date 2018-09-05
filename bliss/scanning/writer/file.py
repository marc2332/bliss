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
from bliss.common.event import connect, disconnect


class _EventReceiver(object):
    def __init__(self, device, parent_entry, callback):
        self.device = device
        self.parent_entry = parent_entry
        self.callback = callback

    def __call__(self, event_dict=None, signal=None, sender=None):
        if callable(self.callback):
            self.callback(self.parent_entry, event_dict, signal, sender)

    def connect(self):
        for signal in ("start", "end"):
            connect(self.device, signal, self)
        for channel in self.device.channels:
            connect(channel, "new_data", self)

    def disconnect(self):
        if self.device is None:
            return
        for signal in ("start", "end"):
            disconnect(self.device, signal, self)
        for channel in self.device.channels:
            disconnect(self.device, "new_data", self)
        self.device = None


class FileWriter(object):
    def __init__(
        self,
        root_path,
        images_root_path,
        master_event_callback=None,
        device_event_callback=None,
        **keys
    ):
        """ A default way to organize file structure
        """
        self._save_images = True
        self._root_path = root_path
        self._images_root_path = images_root_path
        self._master_event_callback = master_event_callback
        self._device_event_callback = device_event_callback
        self._event_receivers = list()

        self.log = logging.getLogger(type(self).__name__)

    @property
    def root_path(self):
        return self._root_path

    @property
    def images_root_path(self):
        return self._images_root_path

    def create_path(self, full_path):
        try:
            os.makedirs(full_path)
        except OSError as exc:  # Python >2.5
            if exc.errno == errno.EEXIST and os.path.isdir(full_path):
                pass
            else:
                raise

    def new_scan(self, scan):
        self.create_path(self._root_path)
        self.new_file(self._root_path, scan.node.name, scan.scan_info)

    def new_file(self, scan_file_dir, scan_name, scan_info):
        pass

    def new_master(self, master, scan_file_dir):
        raise NotImplementedError

    def add_reference(self, master_entry, referenced_master_entry):
        pass

    def prepare_saving(self, device, images_path):
        any_image = any(
            channel.reference and len(channel.shape) == 2 for channel in device.channels
        )
        if any_image and self._save_images:
            directory = os.path.dirname(images_path)
            prefix = os.path.basename(images_path)
            self.create_path(directory)
            device.set_image_saving(directory, prefix)
        else:
            device.set_image_saving(None, None, force_no_saving=True)

    def _prepare_callbacks(self, device, master_entry, callback):
        ev_receiver = _EventReceiver(device, master_entry, callback)
        ev_receiver.connect()
        self._event_receivers.append(ev_receiver)

    def _remove_callbacks(self):
        for ev_receiver in self._event_receivers:
            ev_receiver.disconnect()
        self._event_receivers = []

    def prepare(self, scan):
        self.new_scan(scan)

        self._event_receivers = []
        master_entries = {}

        for dev, node in scan.nodes.iteritems():
            if isinstance(dev, AcquisitionMaster):
                try:
                    master_entry = master_entries[dev]
                except KeyError:
                    master_entry = self.new_master(dev, scan.path)
                    master_entries[dev] = master_entry

                self._prepare_callbacks(dev, master_entry, self._master_event_callback)

                images_path = self._images_root_path.format(
                    scan=scan.node.name, device=dev.name
                )
                self.prepare_saving(dev, images_path)

                for slave in dev.slaves:
                    if isinstance(slave, AcquisitionDevice) and callable(
                        self._device_event_callback
                    ):
                        self._prepare_callbacks(
                            slave, master_entry, self._device_event_callback
                        )
                    elif isinstance(slave, AcquisitionMaster):
                        try:
                            referenced_master_entry = master_entries[slave]
                        except KeyError:
                            referenced_master_entry = self.new_master(slave, scan.path)
                            master_entries[slave] = referenced_master_entry
                        self.add_reference(master_entry, referenced_master_entry)
        self._closed = False

    def close(self):
        self._remove_callbacks()

    def get_scan_entries(self):
        """
        Should return all scan entries from this path
        """
        return []
