# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.scanning.writer.file import FileWriter


class Writer(FileWriter):
    def __init__(self, *args, **keys):
        FileWriter.__init__(self, "", "", "")

    def new_file(self, *args):
        pass

    def new_scan(self, *args):
        pass

    def create_path(self, scan_recorder):
        return

    def new_master(self, *args):
        return

    def get_scan_entries(self):
        return []

    @property
    def filename(self):
        return "<no saving>"
