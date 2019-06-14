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
from bliss.common.utils import dicttoh5  # derived from silx function


class HDF5_Writer(object):
    """
    This object is instantiated once per scan and handles
    the hdf5 access for one particular scan
    """

    def __init__(self, parent_node):
        self.parent_node = parent_node
        self.parent_db_name = parent_node.db_name

        print("starting to save data for", self.h5_scan_name)

        filename = self.scan_info("filename")
        # here I modify the filename, so that this script can run
        # in parallel with the bliss filesaving ... just for debugging
        filename = filename.replace(".", "_external.")
        self.file = h5py.File(filename)

        #### create raw structure for hdf5
        scan_entry = self.file.create_group(self.h5_scan_name)
        scan_entry.attrs["NX_class"] = "NXentry"
        scan_entry["title"] = self.scan_info("title")
        timestamp = self.scan_info("start_timestamp")
        local_time = datetime.datetime.fromtimestamp(timestamp).isoformat()
        utc_time = local_time + "%+03d:00" % (time.altzone / 3600)
        scan_entry["start_time"] = utc_time
        measurement = scan_entry.create_group("measurement")
        measurement.attrs["NX_class"] = "NXcollection"

        # all 0d channels that are involved in this scan will be added here
        self.channels = list()
        self.lima_channels = list()

        # tracks for each channel how far the data has been written yet
        self.channel_indices = dict()

        # listen and treat events for this scan asynchronously
        self._greenlet = gevent.spawn(self.run)

    @property
    def h5_scan_name(self):
        return str(self.scan_info("scan_nb")) + "_" + self.scan_info("type")

    def scan_info(self, key):
        return self.parent_node.info.get(key)

    @property
    def scan_info_dict(self):
        # data might be injected during the scan, therefor we do not
        # keep a static reference here
        return self.parent_node.info.get_all()

    def run(self):
        # ~ print("writer run", self.parent_db_name)

        n = get_node(self.parent_db_name)
        for event_type, node in n.iterator.walk_events():
            # ~  print(self.parent_db_name, event_type, node.type)

            # creating new dataset for channel
            if event_type.name == "NEW_CHILD" and node.type == "channel":
                # ~ print(self.parent_db_name,"create new dataset",node.name)
                self.channels.append(node)
                self.channel_indices[node.fullname] = 0

                maxshape = tuple([None] + list(node.shape))
                npoints = self.scan_info("npoints") or 1
                shape = tuple([npoints] + list(node.shape))

                self.file.create_dataset(
                    self.h5_scan_name + "/measurement/" + node.alias_or_fullname,
                    shape=shape,
                    dtype=node.dtype,
                    compression="gzip",
                    maxshape=maxshape,
                )

            # creating new data set for lima data
            elif event_type.name == "NEW_CHILD" and node.type == "lima":
                self.lima_channels.append(node)

            # adding data to channel dataset
            elif event_type.name == "NEW_DATA_IN_CHANNEL" and node.type == "channel":
                # ~ print(self.parent_db_name,"add data",node.name)
                self.update_data(node)

            # adding data to lima dataset
            elif event_type.name == "NEW_DATA_IN_CHANNEL" and node.type == "lima":
                # could be done during the scan as done for channels
                # in this demo we restrict ourselves to treating the lima data at the end of the scan
                pass

            else:
                print(
                    "DEBUG: untreated event: ",
                    event_type.name,
                    node.type,
                    node.name,
                    node.fullname,
                )

    def update_data(self, node):
        """Insert data until the last available point into the hdf5 datasets"""
        data = node.get(self.channel_indices[node.fullname], -1)
        if len(data) > 0:
            self.file[self.h5_scan_name + "/measurement/" + node.alias_or_fullname][
                self.channel_indices[node.fullname] : self.channel_indices[
                    node.fullname
                ]
                + len(data)
            ] = data
            self.channel_indices[node.fullname] += len(data)

    def update_lima_data(self, node):
        """Insert lima refs into the hdf5 datasets"""

        data = self.lima_ref_array(node)

        shape = numpy.shape(data)
        dtype = data.dtype

        dataset = self.file.create_dataset(
            self.h5_scan_name + "/measurement/" + node.fullname,
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
        print("writer finalize", self.parent_db_name)

        self._greenlet.kill()

        # make sure that all data was written until the last point
        # in case we missed anything
        for c in self.channels:
            self.update_data(c)

        for c in self.lima_channels:
            self.update_lima_data(c)

        # instrument entry
        instrument = self.file.create_group(f"{self.h5_scan_name}/instrument")
        instrument.attrs["NX_class"] = "NXinstrument"
        dicttoh5(
            self.scan_info_dict["instrument"],
            self.file,
            h5path=f"{self.h5_scan_name}/instrument",
        )

        # deal with meta-data
        meta_categories = self.scan_info_dict["scan_meta_categories"]
        if "instrument" in meta_categories:
            meta_categories.remove("instrument")

        meta = self.file.create_group(f"{self.h5_scan_name}/scan_meta")
        meta.attrs["NX_class"] = "NXcollection"
        for cat in meta_categories:
            dicttoh5(
                self.scan_info_dict[cat],
                self.file,
                h5path=f"{self.h5_scan_name}/scan_meta/{cat}",
            )

        self.file.close()


def listen_to_session_wait_for_scans(session, event=None):
    """listen to one session and create a HDF5_Writer instance every time
    a new scan is started. Once a END_SCAN event is received the writer 
    instance is informed to finalize."""
    # event: for external synchronization (see test)

    # n = get_node(session) ... raises if it is a 'fresh' session e.g. in tests
    n = _get_or_create_node(session)

    # one could consider to simplify this by introducing a walk_events_from_last
    it = n.iterator
    pubsub = it.children_event_register()

    scan_stack = dict()

    def g(filter="scan"):

        # make all past scans go away
        for x in it.walk_from_last(wait=False, include_last=False, ready_event=event):
            # for last_node in it.walk(filter=filter, wait=False):
            pass

        # wait for new events on scan
        for event_type, node in it.wait_for_event(pubsub, filter=filter):
            if event_type.name == "NEW_CHILD":
                scan_stack[node.db_name] = HDF5_Writer(node)

            elif event_type.name == "END_SCAN":
                s = scan_stack.pop(node.db_name, None)
                if s is not None:
                    s.finalize()

            else:
                print("we are in trouble")

    # gevent.spawn(g) could be used to instead of g()
    try:
        g()
    except KeyboardInterrupt:
        for s in scan_stack.values():
            s.finalize()
        print("---- hdf5 writer terminates ----")


if __name__ == "__main__":
    listen_to_session_wait_for_scans("test_session")
