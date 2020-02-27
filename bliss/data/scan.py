# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
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


def _watch_data_callback(
    event,
    events_dict,
    scan_new_callback,
    scan_new_child_callback,
    scan_data_callback,
    scan_end_callback,
):
    running_scans = dict()
    while True:
        event.wait()
        event.clear()
        local_events = events_dict.copy()
        events_dict.clear()

        event_data = local_events.pop(_SCAN_EVENT.NEW, [])
        for db_name, scan_info in event_data:
            try:
                scan_new_callback(scan_info)
            except:
                sys.excepthook(*sys.exc_info())
            running_scans.setdefault(db_name, dict())

        event_data = local_events.pop(_SCAN_EVENT.NEW_CHILD, {})
        for (scan_db_name, (scan_info, data_channels_event)) in event_data.items():
            scan_dict = running_scans[scan_db_name]
            nodes_info = scan_dict.setdefault("nodes_info", dict())
            scan_dict.setdefault("nodes_data", dict())
            for (channel_db_name, channel_data_node) in data_channels_event.items():
                try:
                    scan_new_child_callback(scan_info, channel_data_node)
                except:
                    sys.excepthook(*sys.exc_info())
                try:
                    fullname = channel_data_node.fullname
                    nodes_info.setdefault(
                        channel_db_name, (fullname, len(channel_data_node.shape), 0)
                    )

                except AttributeError:
                    nodes_info.setdefault(
                        channel_db_name, (channel_data_node.name, -1, 0)
                    )

        event_data = local_events.pop(_SCAN_EVENT.NEW_DATA, {})
        for (scan_db_name, (scan_info, data_channels_event)) in event_data.items():
            zerod_nodes = list()
            other_nodes = dict()
            scan_dict = running_scans[scan_db_name]
            nodes_info = scan_dict["nodes_info"]
            nodes_data = scan_dict["nodes_data"]
            for (channel_db_name, channel_data_node) in data_channels_event.items():
                fullname, dim, last_index = nodes_info.get(channel_db_name)
                if dim == 0:
                    zerod_nodes.append(
                        (fullname, channel_db_name, channel_data_node, last_index)
                    )
                else:
                    other_nodes[fullname] = (channel_db_name, dim, channel_data_node)
            # fetching all zerod in one go
            zerod_nodes_index = [
                (channel_node, start_index)
                for _, _, channel_node, start_index in zerod_nodes
            ]
            try:
                connection = zerod_nodes_index[0][0].db_connection
                pipeline = connection.pipeline()
            except IndexError:
                connection = pipeline = None
            new_data_flags = False
            for ((fullname, channel_db_name, _, last_index), (_, channel_data)) in zip(
                zerod_nodes, get_data_from_nodes(pipeline, *zerod_nodes_index)
            ):
                new_data_flags = True if len(channel_data) > 0 else new_data_flags
                prev_data = nodes_data.get(fullname, [])
                nodes_data[fullname] = numpy.concatenate((prev_data, channel_data))
                nodes_info[channel_db_name] = (
                    fullname,
                    0,
                    last_index + len(channel_data),
                )
            if zerod_nodes and new_data_flags:
                event_channels_full_name = set(
                    (fullname for fullname, _, _, _ in zerod_nodes)
                )
                for master, channels in scan_info["acquisition_chain"].items():
                    channels_set = set(
                        channels["master"]["scalars"] + channels.get("scalars", [])
                    )
                    if event_channels_full_name.intersection(channels_set):
                        try:
                            scan_data_callback(
                                "0d",
                                master,
                                {"data": nodes_data, "scan_info": scan_info},
                            )
                        except:
                            sys.excepthook(*sys.exc_info())
                        gevent.idle()
            elif zerod_nodes:
                gevent.sleep(.1)  # relax a little bit

            for master, channels in scan_info["acquisition_chain"].items():
                other_names = []
                other_names += channels.get("spectra", [])
                other_names += channels.get("images", [])
                other_names += channels.get("master", {}).get("images", [])
                other_names += channels.get("master", {}).get("spectra", [])

                for i, channel_name in enumerate(set(other_names)):
                    channel_db_name, dim, channel_data_node = other_nodes.get(
                        channel_name, (None, -1, None)
                    )
                    if channel_db_name:
                        try:
                            scan_data_callback(
                                f"{dim}d",
                                master,
                                {
                                    "channel_index": i,
                                    "channel_name": channel_name,
                                    "channel_data_node": channel_data_node,
                                    "scan_info": scan_info,
                                },
                            )
                        except:
                            sys.excepthook(*sys.exc_info())

        event_data = local_events.pop(_SCAN_EVENT.END, [])
        for db_name, scan_info in event_data:
            if scan_end_callback:
                try:
                    scan_end_callback(scan_info)
                except:
                    sys.excepthook(*sys.exc_info())
            running_scans.pop(db_name, None)

        # All the events was processed
        assert len(local_events) == 0

        gevent.idle()


def watch_session_scans(
    session_name,
    scan_new_callback,
    scan_new_child_callback,
    scan_data_callback,
    scan_end_callback=None,
    ready_event=None,
    exit_read_fd=None,
):
    session_node = _get_or_create_node(session_name, node_type="session")

    if session_node is None:
        return

    data_iterator = DataNodeIterator(session_node, wakeup_fd=exit_read_fd)
    events_dict = dict()
    callback_event = gevent.event.Event()
    watch_data_callback = gevent.spawn(
        _watch_data_callback,
        callback_event,
        events_dict,
        scan_new_callback,
        scan_new_child_callback,
        scan_data_callback,
        scan_end_callback,
    )

    try:
        pubsub = data_iterator.children_event_register()
        [
            x
            for x in data_iterator.walk_from_last(
                wait=False, include_last=False, ready_event=ready_event
            )
        ]

        running_scans = dict()

        def _get_scan_info(db_name):
            for key, scan_dict in running_scans.items():
                if db_name.startswith(key):
                    return scan_dict["info"], key
            return None, None

        for event_type, node in data_iterator.wait_for_event(pubsub):
            if event_type == data_iterator.EVENTS.EXTERNAL_EVENT:
                break

            elif event_type == data_iterator.EVENTS.NEW_NODE:
                node_type = node.type
                db_name = node.db_name
                if node_type == "scan":
                    # New scan was created
                    scan_dictionnary = running_scans.setdefault(db_name, dict())
                    if not scan_dictionnary:
                        scan_info = node.info.get_all()
                        scan_dictionnary["info"] = scan_info
                        new_event = events_dict.setdefault(_SCAN_EVENT.NEW, list())
                        new_event.append((db_name, scan_info))
                        callback_event.set()
                else:
                    scan_info, scan_db_name = _get_scan_info(db_name)
                    if scan_info:  # scan_found
                        new_child_event = events_dict.setdefault(
                            _SCAN_EVENT.NEW_CHILD, dict()
                        )
                        _, scan_data_event = new_child_event.setdefault(
                            scan_db_name, (scan_info, dict())
                        )
                        scan_data_event.setdefault(db_name, node)
                        callback_event.set()
            elif event_type == data_iterator.EVENTS.NEW_DATA_IN_CHANNEL:
                db_name = node.db_name
                scan_info, scan_db_name = _get_scan_info(db_name)
                if scan_info:
                    new_data_event = events_dict.setdefault(
                        _SCAN_EVENT.NEW_DATA, dict()
                    )
                    _, new_event = new_data_event.setdefault(
                        scan_db_name, (scan_info, dict())
                    )
                    new_event.setdefault(db_name, node)
                    callback_event.set()
            elif event_type == data_iterator.EVENTS.END_SCAN:
                if node.type == "scan":
                    db_name = node.db_name
                    scan_dict = running_scans.pop(db_name)
                    if scan_dict:
                        scan_info = scan_dict["info"]
                        new_event = events_dict.setdefault(_SCAN_EVENT.END, list())
                        new_event.append((db_name, scan_info))
                        callback_event.set()

            # check watch_data_callback is still running
            try:
                watch_data_callback.get(block=False)
            except BaseException as e:
                if e.__class__.__name__ == "Timeout":
                    pass
                else:
                    raise
    finally:
        watch_data_callback.kill()
