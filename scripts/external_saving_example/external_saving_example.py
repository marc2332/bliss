# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Example script to produce hdf5 based on data collected 
by bliss in an external process
"""

import gevent
import h5py
import datetime
import time
import functools

# import os.path
import os
import numpy

from bliss.data.node import get_session_node

# derived from silx function, this could maybe enter into silx again
from bliss.common.utils import dicttoh5

from bliss.data.nodes.lima import LimaImageChannelDataNode
from bliss.data.nodes.channel import ChannelDataNode


class HDF5_Writer(object):
    """
    This object is instantiated once per scan and handles
    the hdf5 access for one particular scan
    """

    def __init__(self, scan_node):
        self.scan_node = scan_node
        self.scan_name = scan_node.name

        # deal with subscans
        self.subscans = dict()

        filename = self.scan_info("filename")
        # here I modify the filename, so that this script can run
        # in parallel with the bliss filesaving ... just for debugging
        filename = filename.replace(".", "_external.")
        self.file = h5py.File(filename, mode="a")

        print("Starting to save data for", self.scan_name)
        print("File:", filename)

        # all channels that are involved in this scan will be added here
        self.channels = list()
        self.lima_channels = list()
        self.group_channels = list()

        # here we will track for each channel how far the data has been written yet
        self.channel_indices = dict()

        # listen and treat events for this scan asynchronously
        self._greenlet = gevent.spawn(self.run)

    def wait_end(self):
        self._greenlet.get()

    def h5_scan_name(self, node):
        # as we want to produce a NeXus compliment hdf5 the tree structure representing a scan in BLISS
        # might has to be split in several sub-scans.
        l = [value for key, value in self.subscans.items() if key in node.db_name]
        if len(l) != 1:
            raise RuntimeError("Trouble identifying sub-scan: " + node.db_name)
        else:
            return self.inject_subscan_nr(l[0])

    def inject_subscan_nr(self, postfix):
        tmp = self.scan_name.split("_")
        tmp[0] = tmp[0] + postfix
        return "_".join(tmp)

    def scan_info(self, key):
        # get scan related information directly from redis as they might be updated during the scan run time
        return self.scan_node.info.get(key)

    @property
    def scan_info_dict(self):
        # recuperate the full scan_info dict from redis. Might be updated during scan run time
        return self.scan_node.info.get_all()

    def run(self):
        """This function will be used to treat events emitted by the scan."""
        # ~ print("writer run", self.scan_node.db_name)

        scan_iterator = self.scan_node.iterator
        for event_type, node, event_data in scan_iterator.walk_events():
            # ~ print(self.scan_db_name, event_type, node.type)
            # creating new dataset for channel
            if event_type == event_type.NEW_NODE and node.type == "channel":
                print(self.scan_node.db_name, "create new dataset", node.name)
                self.channels.append(node)
                self.channel_indices[node.name] = 0

                maxshape = tuple([None] + [None] * len(node.shape))
                npoints = self.scan_info("npoints") or 1
                shape = tuple([npoints] + list(node.shape))

                self.file.create_dataset(
                    self.h5_scan_name(node) + f"/measurement/{node.name}",
                    shape=shape,
                    dtype=node.dtype,
                    # compression="gzip", #to be checked if working with dynamic maxshape issue #880
                    maxshape=maxshape,
                    fillvalue=numpy.nan,
                )

            # creating new data set for lima data
            elif event_type == event_type.NEW_NODE and node.type == "lima":
                self.lima_channels.append(node)

            # dealing with node_ref_channel
            elif event_type == event_type.NEW_NODE and node.type == "node_ref_channel":
                self.group_channels.append(node)

            # adding data to channel dataset
            elif event_type == event_type.NEW_DATA and node.type == "channel":
                print(self.scan_node.db_name, "add data", node.name)
                self.update_data(node)

            # adding data to lima dataset
            elif event_type == event_type.NEW_DATA and node.type == "lima":
                # could be done in real time during run time of the scan as done for channels
                # in this demo we restrict ourselves to treating the lima data at the end of the scan
                pass

            # dealing with node_ref_channel
            elif event_type == event_type.NEW_DATA and node.type == "node_ref_channel":
                # could be done in real time during run time of the scan as done for channels
                # in this demo we restrict ourselves to treating all reference in the end
                pass
            elif event_type == event_type.NEW_DATA and node.type == "scan_group":
                print("**** NEW_DATA ****", node.db_name)
            # creating a new entry in the hdf5 for each 'top-master'
            elif event_type == event_type.NEW_NODE and (
                node.parent.type == "scan" or node.parent.type == "scan_group"
            ):
                print(self.scan_node.db_name, "add subscan", node.name)
                # add a new subscan to this scan (this is to deal with "multiple top master" scans)
                # and the fact that the hdf5 three does not reflect the redis tree in this case
                self.add_subscan(node)
            elif event_type == event_type.END_SCAN:
                self.finalize()
                break
            else:
                print("DEBUG: untreated event: ", event_type.name, node.type, node.name)

    def add_subscan(self, node):
        """ add a new subscan to this scan 
        --- here node is a direct child of scan"""

        if node.db_name in self.subscans.keys():
            pass
        else:
            if len(self.subscans) == 0:
                self.subscans[node.db_name] = ""
            else:
                self.subscans[node.db_name] = f".{len(self.subscans)}"

            #### create raw structure for hdf5
            scan_entry = self.file.create_group(
                self.inject_subscan_nr(self.subscans[node.db_name])
            )
            scan_entry.attrs["NX_class"] = "NXentry"
            scan_entry["title"] = self.scan_info("title")
            timestamp = self.scan_info("start_timestamp")
            local_time = datetime.datetime.fromtimestamp(timestamp).isoformat()
            utc_time = local_time + "%+03d:00" % (time.altzone / 3600)
            scan_entry["start_time"] = utc_time
            measurement = scan_entry.create_group("measurement")
            measurement.attrs["NX_class"] = "NXcollection"

    def update_data(self, node):
        """Insert data until the last available point into the hdf5 datasets"""
        data = node.get_as_array(self.channel_indices[node.name], -1)
        data_len = data.shape[0]
        if data_len > 0:
            dataset = self.file[self.h5_scan_name(node) + f"/measurement/{node.name}"]

            new_point_index = self.channel_indices[node.name] + data_len
            if dataset.shape[0] < new_point_index:
                dataset.resize(new_point_index, axis=0)

            ## needed if # of points per sample is not defined e.g. SamplingMode.SAMPLES
            if len(dataset.shape) > 1 and dataset.shape[1] < data.shape[-1]:
                dataset.resize(data.shape[-1], axis=1)

            if len(dataset.shape) <= 1:
                dataset[self.channel_indices[node.name] : new_point_index] = data
            else:
                dataset[
                    self.channel_indices[node.name] : new_point_index,
                    0 : data.shape[-1],
                ] = data

            self.channel_indices[node.name] += data_len

    def update_lima_data(self, node):
        """Insert lima refs into the hdf5 datasets"""

        data = self.lima_ref_array(node)

        shape = numpy.shape(data)
        dtype = data.dtype

        dataset = self.file.create_dataset(
            self.h5_scan_name(node) + f"/measurement/{node.name}",
            shape=shape,
            dtype=dtype,
            compression="gzip",
            data=data,
        )

        dataset[:] = data

    def update_node_ref_channel(self, node):
        """insert subscans"""

        self.file.create_group(f"{self.scan_name}/scans")
        self.file[f"{self.scan_name}/scans"].attrs["NX_class"] = "NXcollection"
        for subscan in node.get(0, -1):
            subscan_names = [subscan.name]

            # handling multiple top master
            if len(subscan.info["acquisition_chain"]) > 1:
                for i in range(1, len(subscan.info["acquisition_chain"])):
                    subsubscan_number, subsubscan_name = subscan.name.split(
                        "_", maxsplit=1
                    )
                    subsubscan_name = (
                        f"{subsubscan_number}{'.%d_' % i}{subsubscan_name}"
                    )
                    subscan_names.append(subsubscan_name)

            for subscan_name in subscan_names:
                if subscan_name in self.file.keys():
                    self.file[f"{self.scan_name}/scans/{subscan_name}"] = self.file[
                        f"{subscan_name}"
                    ]
                else:
                    # of cause we have to think better what to do in this case...
                    # e.g. external link?
                    print(
                        "ERROR: trying to link to a scan that is not saved in the current file!"
                    )

    def lima_ref_array(self, node):
        """ used to produce a string version of a lima reference that can be saved in hdf5
        """
        # looks like the events are not emitted after saving,
        # therefore we will use 'last_image_ready' instead
        # of "last_image_saved" for now
        # last_image_saved = event_dict["data"]["last_image_saved"]

        root_path = os.path.dirname(self.file.filename)

        lima_data_view = node.get(0, -1)

        tmp = lima_data_view._get_filenames(node.info, *range(0, len(lima_data_view)))

        if tmp != []:
            tmp = numpy.array(tmp, ndmin=2)
            relpath = [os.path.relpath(i, start=root_path) for i in tmp[:, 0]]
            basename = [os.path.basename(i) for i in tmp[:, 0]]
            entry = tmp[:, 1]
            frame = tmp[:, 2]
            file_type = tmp[:, 3]

            return numpy.array(
                (basename, file_type, frame, entry, relpath),
                dtype=h5py.special_dtype(vlen=str),
            ).T
        return None

    def finalize(self):
        """stop the iterator loop for this scan and pass once through all
        channels to make sure that all data is written """
        print("writer finalize", self.scan_node.db_name)

        # make sure that all data was written until the last point
        # in case we missed anything
        for c in self.channels:
            self.update_data(c)

        for c in self.lima_channels:
            self.update_lima_data(c)

        for c in self.group_channels:
            self.update_node_ref_channel(c)

        # instrument entry
        instrument = self.file.create_group(f"{self.scan_name}/instrument")
        instrument.attrs["NX_class"] = "NXinstrument"

        # add acq_chain meta
        def new_nx_collection(d, x):
            return d.setdefault(x, {"NX_class": "NXcollection"})

        instrument_meta = self.scan_info_dict["instrument"]
        instrument_meta["chain_meta"] = {"NX_class": "NXcollection"}
        if "positioners" in self.scan_info_dict:
            instrument_meta["positioners"] = self.scan_info_dict["positioners"].get(
                "positioners_start"
            )
            instrument_meta["positioners_dial"] = self.scan_info_dict[
                "positioners"
            ].get("positioners_dial_start")

        base_db_name = self.scan_node.db_name
        for node in self.scan_node.iterator.walk(wait=False):
            if node.db_name == base_db_name:
                continue
            if not isinstance(node, ChannelDataNode) and not isinstance(
                node, LimaImageChannelDataNode
            ):
                dev_info = node.info.get_all()
                if dev_info:
                    dev_path = node.db_name.replace(base_db_name + ":", "").split(":")
                    d = functools.reduce(
                        new_nx_collection, dev_path, instrument_meta["chain_meta"]
                    )
                    d.update(dev_info)

        dicttoh5(instrument_meta, self.file, h5path=f"{self.scan_name}/instrument")

        # deal with meta-data
        meta_categories = self.scan_info_dict["scan_meta_categories"]
        if "instrument" in meta_categories:
            meta_categories.remove("instrument")

        meta = self.file.create_group(f"{self.scan_name}/scan_meta")
        meta.attrs["NX_class"] = "NXcollection"
        for cat in meta_categories:
            dicttoh5(
                self.scan_info_dict[cat],
                self.file,
                h5path=f"{self.scan_name}/scan_meta/{cat}",
            )

        # insert references to instrument and scan_meta into subscans
        subscans = list(self.subscans.values())
        subscans.remove("")
        for sub in subscans:
            self.file[self.inject_subscan_nr(sub) + "/instrument"] = self.file[
                self.inject_subscan_nr("") + "/instrument"
            ]
            self.file[self.inject_subscan_nr(sub) + "/scan_meta"] = self.file[
                self.inject_subscan_nr("") + "/scan_meta"
            ]

        self.file.close()


def listen_scans_of_session(session, scan_stack=dict()):
    """listen to one session and create a HDF5_Writer instance every time
    a new scan is started. Once a END_SCAN event is received the writer 
    instance is informed to finalize."""

    session_node = get_session_node(session)

    def g():

        # wait for new events on scan
        print("Listening to", session)
        for event_type, node, event_data in session_node.iterator.walk_on_new_events(
            filter=["scan", "scan_group"]
        ):
            if event_type == event_type.NEW_NODE:
                scan_stack[node.db_name] = HDF5_Writer(node)

            elif event_type == event_type.END_SCAN:
                s = scan_stack.get(node.db_name)
                if s is not None:
                    print("BEFORE wait END SCAN", node.db_name)
                    s.wait_end()
                    print("END SCAN", node.db_name)
                    scan_stack.pop(node.db_name)

    # gevent.spawn(g) could be used to instead of g() to run in non-blocking fashion
    try:
        g()
    except KeyboardInterrupt:
        for s in scan_stack.values():
            s.finalize()
        print("---- hdf5 writer terminates ----")


if __name__ == "__main__":
    listen_scans_of_session("test_session")
