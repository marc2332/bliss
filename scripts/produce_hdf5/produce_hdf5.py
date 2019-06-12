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

from bliss.data.node import get_node


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

        # tracks for each channel how far the data has been written yet
        self.indices = dict()

        # listen and treat events for this scan asynchronously
        self._greenlet = gevent.spawn(self.run)

    @property
    def h5_scan_name(self):
        return str(self.scan_info("scan_nb")) + "_" + self.scan_info("type")

    def scan_info(self, key):
        return self.parent_node.info.get(key)

    @property
    def scan_info_dict(self):
        return parent_node.info.get_all()

    def run(self):
        # ~ print("writer run", self.parent_db_name)

        n = get_node(self.parent_db_name)
        for event_type, node in n.iterator.walk_events():
            # ~  print(self.parent_db_name, event_type, node.type)

            # creating new dataset for 0d channel
            if event_type.name == "NEW_CHILD" and node.type == "channel":
                # ~ print(self.parent_db_name,"create new dataset",node.name)
                self.channels.append(node)
                self.indices[node.fullname] = 0

                maxshape = tuple([None] + list(node.shape))
                npoints = self.scan_info("npoints") or 1
                shape = tuple([npoints] + list(node.shape))

                self.file.create_dataset(
                    self.h5_scan_name
                    + "/measurement/"
                    + node.fullname,  # node.alias_or_fullname???
                    shape=shape,
                    dtype=node.dtype,
                    compression="gzip",
                    maxshape=maxshape,
                )

            # adding data to 0d channel dataset
            elif event_type.name == "NEW_DATA_IN_CHANNEL":
                # ~ print(self.parent_db_name,"add data",node.name)
                self.update_0d_data(node)

    def update_0d_data(self, node):
        """Insert data until the last available point into the hdf5 datasets"""
        data = node.get(self.indices[node.fullname], -1)
        if len(data) > 0:
            self.file[self.h5_scan_name + "/measurement/" + node.fullname][
                self.indices[node.fullname] : self.indices[node.fullname] + len(data)
            ] = data
            self.indices[node.fullname] += len(data)

    def finalize(self):
        """stop the iterator loop for this scan and pass once through all
        channels to make sure that all data is written """
        print("writer finalize", self.parent_db_name)

        self._greenlet.kill()

        # make sure that all data was written until the last point
        # in case we missed anything
        for c in self.channels:
            self.update_0d_data(c)

        self.file.close()


def listen_to_session_wait_for_scans(session):
    """listen to one session and create a HDF5_Writer instance every time
    a new scan is started. Once a END_SCAN event is received the writer 
    instance is informed to finalize."""

    n = get_node(session)

    ### one could consider to simplify this by introducing a walk_events_from_last
    it = n.iterator
    pubsub = it.children_event_register()

    scan_stack = dict()

    def g(filter="scan"):

        # make all past scans go away
        for last_node in it.walk(filter=filter, wait=False):
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

    # gevent.spawn(g) could be used to encapsulate this, here just run for one session
    try:
        g()
    except KeyboardInterrupt:
        for s in scan_stack.values():
            s.finalize()
        print("---- hdf5 writer terminates ----")


if __name__ == "__main__":
    listen_to_session_wait_for_scans("test_session")
