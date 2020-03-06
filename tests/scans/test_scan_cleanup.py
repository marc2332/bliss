# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
from bliss.scanning.writer.file import FileWriter
from bliss.scanning.scan_saving import BasicScanSaving, property_with_eval_dict
from bliss.common import scans


class CustomWriter(FileWriter):
    FILE_EXTENSION = ""

    def __init__(
        self, root_path, images_root_path, data_filename, exception_on, *args, **keys
    ):
        self.exception_on = exception_on
        FileWriter.__init__(
            self,
            root_path,
            images_root_path,
            data_filename,
            master_event_callback=self._on_master_event,
            device_event_callback=self._on_device_event,
            **keys
        )

    def new_file(self, *args):
        if "new_file" in self.exception_on:
            raise RuntimeError("Raise on 'new_file' for testing scan cleanup")

    def new_scan(self, *args):
        if "new_scan" in self.exception_on:
            raise RuntimeError("Raise on 'new_scan' for testing scan cleanup")

    def create_path(self, scan_recorder):
        if "create_path" in self.exception_on:
            raise RuntimeError("Raise on 'create_path' for testing scan cleanup")

    def _on_master_event(self, parent, event_dict, signal, sender):
        if "_on_master_event" in self.exception_on:
            raise RuntimeError("Raise on '_on_master_event' for testing scan cleanup")

    def _on_device_event(self, parent, event_dict, signal, sender):
        if "_on_device_event" in self.exception_on:
            raise RuntimeError("Raise on '_on_device_event' for testing scan cleanup")

    def prepare_saving(self, device, images_path):
        if "prepare_saving" in self.exception_on:
            raise RuntimeError("Raise on 'prepare_saving' for testing scan cleanup")
        any_image = any(
            channel.reference and len(channel.shape) == 2 for channel in device.channels
        )
        if any_image and self._save_images:
            super().create_path(images_path)
        super().prepare_saving(device, images_path)

    def new_master(self, *args):
        if "new_master" in self.exception_on:
            raise RuntimeError("Raise on 'new_master' for testing scan cleanup")

    def finalize_scan_entry(self, scan):
        if "finalize_scan_entry" in self.exception_on:
            raise RuntimeError(
                "Raise on 'finalize_scan_entry' for testing scan cleanup"
            )

    def get_scan_entries(self):
        if "get_scan_entries" in self.exception_on:
            raise RuntimeError("Raise on 'get_scan_entries' for testing scan cleanup")
        return []

    @property
    def filename(self):
        if "filename" in self.exception_on:
            raise RuntimeError("Raise on 'filename' for testing scan cleanup")
        return ""


class CustomScanSaving(BasicScanSaving):

    DEFAULT_VALUES = BasicScanSaving.DEFAULT_VALUES.copy()
    DEFAULT_VALUES["exception_on"] = ""

    def _get_writer_class(self, *args):
        return CustomWriter

    @property_with_eval_dict
    def writer_object(self, eval_dict=None):
        """This instantiates the writer class

        :returns bliss.scanning.writer.File:
        """
        root_path = self.get_cached_property("root_path", eval_dict)
        images_path = self.get_cached_property("images_path", eval_dict)
        data_filename = self.get_cached_property("eval_data_filename", eval_dict)
        exception_on = self.exception_on.split(",")
        writer = CustomWriter(root_path, images_path, data_filename, exception_on)
        return writer


@pytest.mark.parametrize(
    "exception_on",
    [
        "new_file",
        "new_scan",
        "create_path",
        "_on_master_event",
        "_on_device_event",
        "prepare_saving",
        "new_master",
        "finalize_scan_entry",
    ],
)
def test_scan_cleanup_writerexceptions(exception_on, session):
    session._set_scan_saving_class(CustomScanSaving)
    detectors = (session.env_dict["diode"],)
    session.scan_saving.exception_on = exception_on
    with pytest.raises(RuntimeError):
        s = scans.loopscan(5, 0.1, *detectors)
