# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import itertools
import errno
import os

from bliss.scanning.chain import AcquisitionSlave, AcquisitionMaster
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
    FILE_EXTENSION = None

    def __init__(
        self,
        root_path,
        images_root_path,
        data_filename,
        master_event_callback=None,
        device_event_callback=None,
        **keys,
    ):
        """ A default way to organize file structure
        """
        self._save_images = True
        self._root_path_template = root_path
        self._data_filename_template = data_filename
        self._template_dict = {}
        self._images_root_path_template = images_root_path
        self._master_event_callback = master_event_callback
        self._device_event_callback = device_event_callback
        self._event_receivers = list()

    @property
    def template(self):
        return self._template_dict

    @property
    def root_path(self):
        """File directory
        """
        return self._root_path_template.format(**self._template_dict)

    @property
    def data_filename(self):
        """File name without extension
        """
        return self._data_filename_template.format(**self._template_dict)

    @property
    def filename(self):
        """Full file path
        """
        return os.path.join(
            self.root_path,
            os.path.extsep.join((self.data_filename, self.FILE_EXTENSION)),
        )

    def create_path(self, full_path):
        try:
            os.makedirs(full_path)
        except OSError as exc:  # Python >2.5
            if exc.errno == errno.EEXIST and os.path.isdir(full_path):
                pass
            else:
                raise

    def new_file(self, scan_name, scan_info):
        """Create a new scan file

        Filename is stored in the class as the 'filename' property
        """
        raise NotImplementedError

    def finalize_scan_entry(self, scan):
        """Called at the end of a scan
        """
        pass

    def new_scan(self, scan_name, scan_info):
        raise NotImplementedError

    def new_master(self, master, scan_entry):
        return scan_entry

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
        self.create_path(self.root_path)
        self.new_file(scan.node.name, scan.scan_info)
        scan_entry = self.new_scan(scan.node.name, scan.scan_info)

        self._event_receivers = []

        scan_counter = itertools.count()

        for dev, node in scan.nodes.items():
            if isinstance(dev, AcquisitionMaster):
                if dev.parent is None:
                    # top-level master
                    scan_index = next(scan_counter)
                    if scan_index > 0:
                        # multiple top-level masters: create a new scan with sub-scan
                        # convention: scan number will get a .1, .2, etc suffix
                        scan_number, scan_name = scan.node.name.split("_", maxsplit=1)
                        subscan_name = f"{scan_number}{'.%d_' % scan_index}{scan_name}"
                        scan_entry = self.new_scan(subscan_name, scan.scan_info)

                master_entry = self.new_master(dev, scan_entry)
                self._prepare_callbacks(dev, master_entry, self._master_event_callback)

                images_path = self._images_root_path_template.format(
                    scan_name=scan.name,
                    img_acq_device=dev.name,
                    scan_number=scan.scan_number,
                )
                self.prepare_saving(dev, images_path)

                for slave in dev.slaves:
                    if isinstance(slave, AcquisitionSlave) and callable(
                        self._device_event_callback
                    ):
                        self._prepare_callbacks(
                            slave, master_entry, self._device_event_callback
                        )

    def close(self):
        self._remove_callbacks()

    def get_scan_entries(self):
        """
        Should return all scan entries from this path
        """
        return []
