#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Example script to produce hdf5 based on data collected 
by bliss in an external process
"""

import gevent
import h5py
import datetime
import time
import os.path
import numpy

from bliss.data.node import get_node, _get_or_create_node

# derived from silx function, this could maybe enter into silx again
from bliss.common.utils import dicttoh5


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
        self.file = h5py.File(filename)

        print("Starting to save data for", self.scan_name)
        print("File:", filename)

        # all channels that are involved in this scan will be added here
        self.channels = list()
        self.lima_channels = list()

        # here we will track for each channel how far the data has been written yet
        self.channel_indices = dict()

        # listen and treat events for this scan asynchronously
        self._greenlet = gevent.spawn(self.run)

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

        for event_type, node in self.scan_node.iterator.walk_events():
            # ~ print(self.scan_db_name, event_type, node.type)

            # creating new dataset for channel
            if event_type.name == "NEW_NODE" and node.type == "channel":
                print(self.scan_node.db_name, "create new dataset", node.name)
                self.channels.append(node)
                self.channel_indices[node.fullname] = 0

                maxshape = tuple([None] + list(node.shape))
                npoints = self.scan_info("npoints") or 1
                shape = tuple([npoints] + list(node.shape))

                self.file.create_dataset(
                    self.h5_scan_name(node) + "/measurement/" + node.alias_or_fullname,
                    shape=shape,
                    dtype=node.dtype,
                    compression="gzip",
                    maxshape=maxshape,
                )

            # creating new data set for lima data
            elif event_type.name == "NEW_NODE" and node.type == "lima":
                self.lima_channels.append(node)

            # adding data to channel dataset
            elif event_type.name == "NEW_DATA_IN_CHANNEL" and node.type == "channel":
                print(self.scan_node.db_name, "add data", node.name)
                self.update_data(node)

            # adding data to lima dataset
            elif event_type.name == "NEW_DATA_IN_CHANNEL" and node.type == "lima":
                # could be done in real time during run time of the scan as done for channels
                # in this demo we restrict ourselves to treating the lima data at the end of the scan
                pass

            # creating a new entry in the hdf5 for each 'top-master'
            elif event_type.name == "NEW_NODE" and node.parent.type == "scan":
                print(self.scan_node.db_name, "add subscan", node.name)
                # add a new subscan to this scan (this is to deal with "multiple top master" scans)
                # and the fact that the hdf5 three does not reflect the redis tree in this case
                self.add_subscan(node)

            else:
                print(
                    "DEBUG: untreated event: ",
                    event_type.name,
                    node.type,
                    node.name,
                    node.fullname,
                )

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
        data = numpy.array(node.get(self.channel_indices[node.fullname], -1))
        data_len = data.shape[0]
        if data_len > 0:

            dataset = self.file[
                self.h5_scan_name(node) + "/measurement/" + node.alias_or_fullname
            ]  # caution: alias handling might change in near future!
            new_point_index = self.channel_indices[node.fullname] + data_len
            if dataset.shape[0] < new_point_index:
                dataset.resize(new_point_index, axis=0)

            dataset[self.channel_indices[node.fullname] : new_point_index] = data
            self.channel_indices[node.fullname] += data_len

    def update_lima_data(self, node):
        """Insert lima refs into the hdf5 datasets"""

        data = self.lima_ref_array(node)

        shape = numpy.shape(data)
        dtype = data.dtype

        dataset = self.file.create_dataset(
            self.h5_scan_name(node) + "/measurement/" + node.fullname,
            shape=shape,
            dtype=dtype,
            compression="gzip",
            data=data,
        )

        dataset[:] = data

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

        self._greenlet.kill()

        # make sure that all data was written until the last point
        # in case we missed anything
        for c in self.channels:
            self.update_data(c)

        for c in self.lima_channels:
            self.update_lima_data(c)

        # instrument entry
        instrument = self.file.create_group(f"{self.scan_name}/instrument")
        instrument.attrs["NX_class"] = "NXinstrument"
        dicttoh5(
            self.scan_info_dict["instrument"],
            self.file,
            h5path=f"{self.scan_name}/instrument",
        )

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


def listen_scans_of_session(session):
    """listen to one session and create a HDF5_Writer instance every time
    a new scan is started. Once a END_SCAN event is received the writer 
    instance is informed to finalize."""
    # event: for external synchronization (see e.g. test)

    session_node = get_node(session)

    scan_stack = dict()

    def g():

        # wait for new events on scan
        print("Listening to", session)
        for event_type, node in session_node.iterator.walk_on_new_events(filter="scan"):
            if event_type.name == "NEW_NODE":
                scan_stack[node.db_name] = HDF5_Writer(node)

            elif event_type.name == "END_SCAN":
                s = scan_stack.pop(node.db_name, None)
                if s is not None:
                    s.finalize()

    # gevent.spawn(g) could be used to instead of g() to run in non-blocking fashion
    try:
        g()
    except KeyboardInterrupt:
        for s in scan_stack.values():
            s.finalize()
        print("---- hdf5 writer terminates ----")


if __name__ == "__main__":
    listen_scans_of_session("test_session")
