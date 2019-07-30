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
from bliss.common.utils import dicttoh5
from bliss.scanning.writer.file import FileWriter
from bliss.scanning.scan_meta import categories_names


class Writer(FileWriter):
    def __init__(self, root_path, images_root_path, data_filename, **keys):
        FileWriter.__init__(
            self,
            root_path,
            images_root_path,
            data_filename,
            master_event_callback=self._on_event,
            device_event_callback=self._on_event,
            **keys,
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

        return measurement

    def _on_event(self, parent, event_dict, signal, sender):
        if signal == "start":
            device = sender
            for channel in device.channels:
                maxshape = tuple([None] + [None] * len(channel.shape))
                npoints = device.npoints or 1
                shape = tuple([npoints] + list(channel.shape))
                if not channel.reference and channel.alias_or_fullname not in parent:
                    dataset = parent.create_dataset(
                        channel.alias_or_fullname,
                        shape=shape,
                        dtype=channel.dtype,
                        # compression="gzip",  to be checked if working with dynamic maxshape issue #880
                        maxshape=maxshape,
                        fillvalue=numpy.nan,
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

            ## needed if # of points per sample is not defined e.g. SamplingMode.SAMPLES
            if len(dataset.shape) > 1 and dataset.shape[1] < sender.shape[0]:
                dataset.resize(sender.shape[0], axis=1)

            if len(dataset.shape) <= 1:
                dataset[last_point_index:new_point_index] = data
            else:
                dataset[last_point_index:new_point_index, 0 : data.shape[1]] = data

            self.last_point_index[channel] += data_len

    def finalize_scan_entry(self, scan):
        scan_name = scan.node.name
        scan_info = scan._scan_info

        ###    fill image references   ###

        for fname, channel in scan.get_channels_dict.items():
            if channel.reference:
                try:
                    data = channel.acq_device.to_ref_array(channel, self.root_path)

                    shape = numpy.shape(data)
                    dtype = data.dtype

                    dataset = self.file.create_dataset(
                        f"{scan_name}/measurement/{channel.alias_or_fullname}",
                        shape=shape,
                        dtype=dtype,
                        compression="gzip",
                    )
                    dataset.attrs.modify("fullname", channel.fullname)
                    dataset.attrs.modify("alias", channel.alias or "None")
                    dataset.attrs.modify("has_alias", channel.has_alias)

                    dataset[:] = data

                except Exception as e:
                    pass

        ####   use scan_meta to fill fields   ####
        hdf5_scan_meta = {
            cat_name: scan_info.get(cat_name, {}) for cat_name in categories_names()
        }

        # pop instrument
        instrument = self.file.create_group(f"{scan_name}/instrument")
        instrument.attrs["NX_class"] = "NXinstrument"
        instrument_meta = hdf5_scan_meta.pop("instrument")
        dicttoh5(instrument_meta, self.file, h5path=f"{scan_name}/instrument")

        dicttoh5(hdf5_scan_meta, self.file, h5path=f"{scan_name}/scan_meta")
        self.file[f"{scan_name}/scan_meta"].attrs["NX_class"] = "NXcollection"

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
