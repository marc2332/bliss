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
import functools


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
                chan_name = channel.name
                if not channel.reference and chan_name not in parent:
                    dataset = parent.create_dataset(
                        chan_name,
                        shape=shape,
                        dtype=channel.dtype,
                        # compression="gzip",  to be checked if working with dynamic maxshape issue #880
                        maxshape=maxshape,
                        fillvalue=numpy.nan,
                    )
                    dataset.attrs.modify("fullname", channel.fullname)

                    self.last_point_index[channel] = 0
        elif signal == "new_data":
            channel = sender
            if channel.reference:
                return
            data = event_dict.get("data")

            dataset = parent[channel.name]

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
        if self.file is None:  # nothing to finalize, scan didn't record anything
            return

        scan_name = scan.node.name
        scan_info = scan.scan_info

        ###    fill image references and groups   ###

        for fname, channel in scan.get_channels_dict.items():
            chan_name = channel.name
            if channel.reference and channel.data_node_type == "lima":
                """produce a string version of a lima reference that can be saved in hdf5
                
                At the moment there is only Lima references ;
                something more elaborated will be needed when we will have other
                references.
                """
                lima_data_view = channel.data_node.get(0, -1)

                try:
                    tmp = lima_data_view._get_filenames(
                        channel.data_node.info, *range(0, len(lima_data_view))
                    )
                except Exception:
                    tmp = []

                if tmp:
                    tmp = numpy.array(tmp, ndmin=2)
                    relpath = [
                        os.path.relpath(i, start=self.root_path) for i in tmp[:, 0]
                    ]
                    basename = [os.path.basename(i) for i in tmp[:, 0]]
                    entry = tmp[:, 1]
                    frame = tmp[:, 2]
                    file_type = tmp[:, 3]

                    data = numpy.array(
                        (basename, file_type, frame, entry, relpath),
                        dtype=h5py.special_dtype(vlen=str),
                    ).T

                    shape = numpy.shape(data)
                    dtype = data.dtype
                    dataset = self.file.create_dataset(
                        f"{scan_name}/measurement/{chan_name}",
                        shape=shape,
                        dtype=dtype,
                        compression="gzip",
                    )
                    dataset.attrs.modify("fullname", channel.fullname)
                    dataset[:] = data

            elif channel.reference and channel.data_node_type == "node_ref_channel":
                self.file.create_group(f"{scan_name}/scans")
                self.file[f"{scan_name}/scans"].attrs["NX_class"] = "NXcollection"
                for subscan in channel.data_node.get(0, -1):
                    subscan_names = [subscan.name]

                    # handling multiple top master
                    if len(subscan.info["acquisition_chain"]) > 1:
                        for i in range(1, len(subscan.info["acquisition_chain"])):
                            ### logic taken from
                            ### has to stay in sync!!
                            subsubscan_number, subsubscan_name = subscan.name.split(
                                "_", maxsplit=1
                            )
                            subsubscan_name = (
                                f"{subsubscan_number}{'.%d_' % i}{subsubscan_name}"
                            )
                            subscan_names.append(subsubscan_name)

                    for subscan_name in subscan_names:
                        if subscan_name in self.file.keys():
                            self.file[f"{scan_name}/scans/{subscan_name}"] = self.file[
                                f"{subscan_name}"
                            ]
                        else:
                            # of cause we have to think better what to do in this case...
                            # e.g. external link?
                            print(
                                "ERROR: trying to link to a scan that is not saved in the current file!"
                            )

        ####   use scan_meta to fill fields   ####
        hdf5_scan_meta = {
            cat_name: scan_info.get(cat_name, {}).copy()
            for cat_name in categories_names()
        }

        # pop instrument
        instrument = self.file.create_group(f"{scan_name}/instrument")
        instrument.attrs["NX_class"] = "NXinstrument"
        instrument_meta = hdf5_scan_meta.pop("instrument")

        # pop nexuswriter
        hdf5_scan_meta.pop("nexuswriter")

        dicttoh5(hdf5_scan_meta, self.file, h5path=f"{scan_name}/scan_meta")
        self.file[f"{scan_name}/scan_meta"].attrs["NX_class"] = "NXcollection"

        def new_nx_collection(d, x):
            return d.setdefault(x, {"NX_class": "NXcollection"})

        instrument_meta["chain_meta"] = {"NX_class": "NXcollection"}
        instrument_meta["positioners"] = scan_info.get("positioners", {}).get(
            "positioners_start", {}
        )
        instrument_meta["positioners_dial"] = scan_info.get("positioners", {}).get(
            "positioners_dial_start", {}
        )

        base_db_name = scan.node.db_name
        for dev in scan.acq_chain.nodes_list:
            dev_node = scan.nodes[dev]
            dev_info = dev_node.info.get_all()
            if dev_info:
                dev_path = dev_node.db_name.replace(base_db_name + ":", "").split(":")
                d = functools.reduce(
                    new_nx_collection, dev_path, instrument_meta["chain_meta"]
                )
                d.update(dev_info)

        dicttoh5(instrument_meta, self.file, h5path=f"{scan_name}/instrument")

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
