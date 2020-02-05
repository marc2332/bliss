# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import enum
import sys
import numpy
import gevent
from bliss.common.counter import Counter
from bliss.common.axis import Axis
from bliss.data.nodes.scan import get_data_from_nodes
from bliss.data.node import DataNodeIterator, _get_or_create_node


def get_counter_names(scan):
    """
    Return a list of counter names
    """
    return [node.name for node in scan.nodes.values() if node.type == "channel"]


def get_data(scan):
    """
    Return a dictionary of { channel_name: numpy array }
    """

    class DataContainer(dict):
        def __info__(self):
            return f"DataContainer use [counter],[motor] or {self.keys()}"

        def __getitem__(self, key):
            if isinstance(key, Counter):
                return super().__getitem__(key.fullname)
            elif isinstance(key, Axis):
                return super().__getitem__(f"axis:{key.name}")

            try:
                return super().__getitem__(key)
            except KeyError as er:
                match_value = [
                    (fullname, data)
                    for fullname, data in self.items()
                    if key in fullname.split(":")
                ]
                if len(match_value) == 1:
                    return match_value[0][1]
                elif len(match_value) > 1:
                    raise KeyError(
                        f"Ambiguous key **{key}**, there is several match ->",
                        [x[0] for x in match_value],
                    )
                else:
                    raise er

    connection = scan.node.db_connection
    pipeline = connection.pipeline()
    data = DataContainer()
    nodes_and_index = [(node, 0) for node in scan.nodes.values()]
    for channel_name, channel_data in get_data_from_nodes(pipeline, *nodes_and_index):
        data[channel_name] = channel_data
    return data


def watch_session_scans(
    session_name,
    scan_new_callback,
    scan_new_child_callback,
    scan_data_callback,
    scan_end_callback=None,
    ready_event=None,
    stop_handler=None,
):
    session_node = _get_or_create_node(session_name, node_type="session")

    if session_node is None:
        return

    data_iterator = session_node.iterator
    running_scans = dict()

    def _get_scan_info(db_name):
        for key, scan_dict in running_scans.items():
            if db_name.startswith(key):
                return scan_dict["info"], key
        return None, None

    if ready_event is not None:
        ready_event.set()
    for event_type, node, event_data in data_iterator.walk_on_new_events(
        stream_stop_reading_handler=stop_handler
    ):
        if event_type == event_type.NEW_NODE:
            node_type = node.type
            db_name = node.db_name
            if node_type in ["scan", "scan_group"]:
                # New scan was created
                scan_dictionnary = running_scans.setdefault(db_name, dict())
                if not scan_dictionnary:
                    scan_info = node.info.get_all()
                    scan_dictionnary["info"] = scan_info
                    scan_new_callback(scan_info)
            else:
                scan_info, scan_db_name = _get_scan_info(db_name)
                if scan_info:  # scan_found
                    try:
                        scan_new_child_callback(scan_info, node)
                    except:
                        sys.excepthook(*sys.exc_info())
        elif event_type == event_type.NEW_DATA:
            index, data, description = (
                event_data.first_index,
                event_data.data,
                event_data.description,
            )
            db_name = node.db_name
            try:
                fullname = node.fullname
            except AttributeError:
                continue

            scan_info, scan_db_name = _get_scan_info(db_name)
            if scan_info:
                nodes_data = running_scans[scan_db_name].setdefault(
                    "nodes_data", dict()
                )
                if node.type == "channel":
                    shape = description[0].get("shape")
                    dim = len(shape)
                    # in case of zerod, we keep all data value during the scan
                    if dim == 0:
                        prev_data = nodes_data.get(fullname, [])
                        nodes_data[fullname] = numpy.concatenate((prev_data, data))
                        for master, channels in scan_info["acquisition_chain"].items():
                            channels_set = channels["master"]["scalars"] + channels.get(
                                "scalars", []
                            )
                            if fullname in channels_set:
                                try:
                                    scan_data_callback(
                                        "0d",
                                        master,
                                        {"data": nodes_data, "scan_info": scan_info},
                                    )
                                except:
                                    sys.excepthook(*sys.exc_info())
                        continue
                elif node.type == "lima":
                    dim = 2

                for master, channels in scan_info["acquisition_chain"].items():
                    other_names = []
                    other_names += channels.get("spectra", [])
                    other_names += channels.get("images", [])
                    other_names += channels.get("master", {}).get("images", [])
                    other_names += channels.get("master", {}).get("spectra", [])
                    if fullname in other_names:
                        try:
                            scan_data_callback(
                                f"{dim}d",
                                master,
                                {
                                    "index": index,
                                    "data": data,
                                    "description": description,
                                    "channel_name": fullname,
                                    "channel_data_node": node,
                                    "scan_info": scan_info,
                                },
                            )
                        except:
                            sys.excepthook(*sys.exc_info())

        elif event_type == event_type.END_SCAN:
            db_name = node.db_name
            scan_dict = running_scans.pop(db_name)
            if scan_dict:
                scan_info = scan_dict["info"]
                if scan_end_callback:
                    try:
                        scan_end_callback(scan_info)
                    except:
                        sys.excepthook(*sys.exc_info())

        gevent.idle()
