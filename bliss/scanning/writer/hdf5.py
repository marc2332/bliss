# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import errno
import h5py
import numpy
import time
import datetime
from bliss.scanning.writer.file import FileWriter


class Writer(FileWriter):
    def __init__(self, root_path, images_root_path, data_filename, **keys):
        FileWriter.__init__(
            self,
            root_path,
            images_root_path,
            data_filename,
            master_event_callback=self._on_event,
            device_event_callback=self._on_event,
            **keys
        )

        self.file = None
        self.last_point_index = {}

    @property
    def filename(self):
        return os.path.join(self.root_path, self.data_filename + ".h5")

    def new_file(self, scan_name, scan_info):
        self.close()
        self.file = h5py.File(self.filename)

    def new_scan(self, scan_name, scan_info):
        scan_entry = self.file.create_group(scan_name)
        scan_entry.attrs["NX_class"] = "NXentry"
        scan_title = scan_info.get("title", "untitled")
        scan_entry["title"] = scan_title
        timestamp = scan_info.get("start_timestamp")
        local_time = datetime.datetime.fromtimestamp(timestamp).isoformat()
        utc_time = local_time + "%+03d:00" % (time.altzone / 3600)
        scan_entry["start_time"] = utc_time
        measurement = scan_entry.create_group("measurement")
        measurement.attrs["NX_class"] = "NXcollection"
        instrument = scan_entry.create_group("instrument")
        instrument.attrs["NX_class"] = "NXinstrument"
        positioners = instrument.create_group("positioners")
        positioners.attrs["NX_class"] = u"NXcollection"
        positioners_dial = instrument.create_group("positioners_dial")
        positioners_dial.attrs["NX_class"] = u"NXcollection"
        positioners_dict = scan_info.get("positioners", {})
        for pname, ppos in positioners_dict.items():
            if isinstance(ppos, float):
                positioners.create_dataset(pname, dtype="float64", data=ppos)
        positioners_dial_dict = scan_info.get("positioners_dial", {})
        for pname, ppos in positioners_dial_dict.items():
            if isinstance(ppos, float):
                positioners_dial.create_dataset(pname, dtype="float64", data=ppos)
        return measurement

    def _on_event(self, parent, event_dict, signal, sender):
        if signal == "start":
            device = sender
            for channel in device.channels:
                maxshape = tuple([None] + list(channel.shape))
                npoints = device.npoints or 1
                shape = tuple([npoints] + list(channel.shape))
                if not channel.reference and channel.alias_or_fullname not in parent:
                    dataset = parent.create_dataset(
                        channel.alias_or_fullname,
                        shape=shape,
                        dtype=channel.dtype,
                        compression="gzip",
                        maxshape=maxshape,
                    )
                    dataset.attrs.modify("fullname", channel.fullname)
                    dataset.attrs.modify("alias", channel.alias or "None")
                    dataset.attrs.modify("has_alias", channel.has_alias)

                    self.last_point_index[channel] = 0
        elif signal == "new_data":
            channel = sender
            if channel.reference:
                return

            data = event_dict.get("data")

            dataset = parent[channel.alias_or_fullname]

            if not dataset.id.valid:
                print("Writer is closed. Spurious data point ignored")
                return

            last_point_index = self.last_point_index[channel]

            data_len = data.shape[0]
            new_point_index = last_point_index + data_len

            if dataset.shape[0] < new_point_index:
                dataset.resize(new_point_index, axis=0)

            dataset[last_point_index:new_point_index] = data

            self.last_point_index[channel] += data_len

    def close(self):
        super(Writer, self).close()
        if self.file is not None:
            self.file.close()
            self.file = None

    def get_scan_entries(self):
        try:
            with h5py.File(self.filename, mode="r") as f:
                return list(f.keys())
        except IOError:  # file doesn't exist
            return []
