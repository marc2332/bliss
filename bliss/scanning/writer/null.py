# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
from bliss.scanning.writer.file import FileWriter


class Writer(FileWriter):
    FILE_EXTENSION = ""

    def __init__(self, root_path, images_root_path, data_filename, *args, **keys):
        FileWriter.__init__(self, root_path, images_root_path, data_filename)

    def new_file(self, *args):
        pass

    def new_scan(self, *args):
        pass

    def create_path(self, scan_recorder):
        return

    def prepare_saving(self, device, images_path):
        any_image = any(
            channel.reference and len(channel.shape) == 2 for channel in device.channels
        )
        if any_image and self._save_images:
            super().create_path(images_path)
        super().prepare_saving(device, images_path)

    def new_master(self, *args):
        return

    def get_scan_entries(self):
        return []

    @property
    def filename(self):
        return ""
