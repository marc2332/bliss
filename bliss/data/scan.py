# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import sys
import numpy
import gevent
import typing
from bliss.common.counter import Counter
from bliss.common.axis import Axis
from bliss.data.nodes.scan import get_data_from_nodes
from bliss.data.node import _get_or_create_node

from bliss.common.utils import get_matching_names


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
            return f"DataContainer uses a key [counter], [motor] or [name_pattern] matching one of these names:\n {list(self.keys())}"

        def __getitem__(self, key):
            if isinstance(key, Counter):
                return super().__getitem__(key.fullname)
            elif isinstance(key, Axis):
                return super().__getitem__(f"axis:{key.name}")

            try:  # maybe a fullname
                return super().__getitem__(key)

            except KeyError:

                # --- maybe an axis (comes from config so name is unique)
                axname = f"axis:{key}"
                if axname in self.keys():
                    return super().__getitem__(axname)

                # --- else check if it can match one of the DataContainer keys
                matches = get_matching_names(
                    key, self.keys(), strict_pattern_as_short_name=True
                )[key]

                if len(matches) > 1:
                    raise KeyError(
                        f"Ambiguous key '{key}', there are several matches -> {matches}"
                    )

                elif len(matches) == 1:
                    return super().__getitem__(matches[0])

                else:
                    msg = "%s not found, try one of those %s" % (
                        key,
                        [x.split(":")[-1] for x in self.keys()],
                    )
                    raise KeyError(msg)

    connection = scan.node.db_connection
    pipeline = connection.pipeline()
    data = DataContainer()
    for channel_name, channel_data in get_data_from_nodes(
        pipeline, *scan.nodes.values()
    ):
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
    watch_scan_group: bool = False,
):
    """
    Arguments:
        watch_scan_group: If True the scan groups are also listed like any other
            scans
    """
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
        stop_handler=stop_handler
    ):
        if event_type == event_type.NEW_NODE:
            node_type = node.type
            db_name = node.db_name
            if node_type == "scan":
                # New scan was created
                scan_dictionnary = running_scans.setdefault(db_name, dict())
                if not scan_dictionnary:
                    scan_info = node.info.get_all()
                    scan_dictionnary["info"] = scan_info
                    scan_new_callback(scan_info)
            elif node_type == "scan_group":
                if watch_scan_group:
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
                    except Exception:
                        sys.excepthook(*sys.exc_info())
        elif event_type == event_type.NEW_DATA:
            index, data, description = (
                event_data.first_index,
                event_data.data,
                event_data.description,
            )
            db_name = node.db_name
            if not hasattr(node, "fullname"):
                # not a node we want to do anything with here
                continue

            fullname = node.fullname

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
                                except Exception:
                                    sys.excepthook(*sys.exc_info())
                        continue
                elif node.type == "lima":
                    dim = 2

                for master, channels in scan_info["acquisition_chain"].items():
                    other_names: typing.List[str] = []
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
                        except Exception:
                            sys.excepthook(*sys.exc_info())

        elif event_type == event_type.END_SCAN:
            node_type = node.type
            if watch_scan_group or node_type == "scan":
                db_name = node.db_name
                scan_dict = running_scans.pop(db_name)
                if scan_dict:
                    scan_info = node.info.get_all()
                    if scan_end_callback:
                        try:
                            scan_end_callback(scan_info)
                        except Exception:
                            sys.excepthook(*sys.exc_info())

        gevent.idle()
