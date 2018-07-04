# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.scanning.writer.file import FileWriter

class Writer(FileWriter):
    def __init__(self, *args, **keys):
        FileWriter.__init__(self, '',
                            master_event_receiver=None,
                            device_event_receiver=None,
                            **keys)

    def prepare(self, scan_recorder, scan_info, devices_tree):
        return

    def create_path(self, scan_recorder):
        return scan_recorder.path

    def new_file(self, scan_file_dir, scan_recorder):
        return

    def new_master(self, master, scan):
        return

    def close(self):
        return

    def get_scan_entries(self):
        return []
