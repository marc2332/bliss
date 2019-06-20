# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import time
import datetime
import enum
import numpy
import pickle
import gevent
from bliss.common.cleanup import excepthook
from bliss.data.node import DataNodeIterator, _get_or_create_node, DataNodeContainer
from bliss.config import settings
import sys


def _transform_dict_obj(dict_object):
    return_dict = dict()
    for key, value in dict_object.items():
        return_dict[key] = _transform(value)
    return return_dict


def _transform_iterable_obj(iterable_obj):
    return_list = list()
    for value in iterable_obj:
        return_list.append(_transform(value))
    return return_list


def _transform_obj_2_name(obj):
    return obj.name if hasattr(obj, "name") else obj


def _transform(var):
    if isinstance(var, dict):
        var = _transform_dict_obj(var)
    elif isinstance(var, (tuple, list)):
        var = _transform_iterable_obj(var)
    else:
        var = _transform_obj_2_name(var)
    return var


def pickle_dump(var):
    var = _transform(var)
    return pickle.dumps(var)


class Scan(DataNodeContainer):
    def __init__(self, name, create=False, **keys):
        DataNodeContainer.__init__(self, "scan", name, create=create, **keys)
        self._info._write_type_conversion = pickle_dump
        if self.new_node:
            with settings.pipeline(self._data, self._info) as p:
                self._info["start_time"]
                self._info["start_time_str"]
                self._info["start_timestamp"]

                self._data.start_time, self._data.start_time_str, self._data.start_timestamp = (
                    self._info._read_type_conversion(x) for x in p.execute()
                )

    def end(self):
        if self.new_node:
            db_name = self.db_name
            # to avoid to have multiple modification events
            with settings.pipeline(self._data, self._info) as p:
                end_timestamp = time.time()
                end_time = datetime.datetime.fromtimestamp(end_timestamp)
                self._data.end_time = end_time
                self._data.end_time_str = end_time.strftime("%a %b %d %H:%M:%S %Y")
                self._data.end_timestamp = end_timestamp
                self._info["end_time"] = end_time
                self._info["end_time_str"] = end_time.strftime("%a %b %d %H:%M:%S %Y")
                self._info["end_timestamp"] = end_timestamp
                p.publish(f"__scans_events__:{db_name}", "END")


def get_counter_names(scan):
    """
    Return a list of counter names
    """
    return [node.name for node in scan.nodes.values() if node.type == "channel"]


def get_data(scan):
    """
    Return a dictionary of { channel_name: numpy array }
    """
    dtype = list()
    max_channel_len = 0
    connection = scan.node.db_connection
    pipeline = connection.pipeline()
    data = dict()
    nodes_and_index = [(node, 0) for node in scan.nodes.values()]
    for channel_name, channel_data in get_data_from_nodes(pipeline, *nodes_and_index):
        data[channel_name] = channel_data
    return data


def get_data_from_nodes(pipeline, *nodes_and_start_index):
    scan_channel_get_data_func = dict()  # { channel_name: function }
    for node, start_index in nodes_and_start_index:
        if node.type == "channel":
            channel_name = node.name
            i = 2
            while channel_name in scan_channel_get_data_func:
                # name conflict: channel with same name already added
                channel_name = ":".join(node.db_name.split(":")[-i:])
                i += 1

            chan = node
            try:
                saved_db_connection = chan.db_connection
                chan.db_connection = pipeline
                # append channel name and get all data from channel;
                # as it is in a Redis pipeline, get returns the
                # conversion function only - data will be received
                # after .execute()
                scan_channel_get_data_func[channel_name] = chan.get(start_index, -1)
            finally:
                chan.db_connection = saved_db_connection

    result = pipeline.execute()

    data = {}
    for i, (channel_name, get_data_func) in enumerate(
        scan_channel_get_data_func.items()
    ):
        yield channel_name, get_data_func(result[i])


_SCAN_EVENT = enum.IntEnum("SCAN_EVENT", "NEW NEW_CHILD NEW_DATA END")


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
        for event_type, event_data in local_events.items():
            if event_type == _SCAN_EVENT.NEW:
                for db_name, scan_info in event_data:
                    scan_new_callback(scan_info)
                    running_scans.setdefault(db_name, dict())
            elif event_type == _SCAN_EVENT.NEW_CHILD:
                for (
                    scan_db_name,
                    (scan_info, data_channels_event),
                ) in event_data.items():
                    scan_dict = running_scans[scan_db_name]
                    nodes_info = scan_dict.setdefault("nodes_info", dict())
                    scan_dict.setdefault("nodes_data", dict())
                    for (
                        channel_db_name,
                        channel_data_node,
                    ) in data_channels_event.items():
                        scan_new_child_callback(scan_info, channel_data_node)
                        try:
                            fullname = channel_data_node.fullname
                            nodes_info.setdefault(
                                channel_db_name,
                                (fullname, len(channel_data_node.shape), 0),
                            )

                        except AttributeError:
                            nodes_info.setdefault(
                                channel_db_name, (channel_data_node.name, -1, 0)
                            )

            elif event_type == _SCAN_EVENT.NEW_DATA:
                zerod_nodes = list()
                other_nodes = dict()
                for (
                    scan_db_name,
                    (scan_info, data_channels_event),
                ) in event_data.items():
                    scan_dict = running_scans[scan_db_name]
                    nodes_info = scan_dict["nodes_info"]
                    nodes_data = scan_dict["nodes_data"]
                    for (
                        channel_db_name,
                        channel_data_node,
                    ) in data_channels_event.items():
                        fullname, dim, last_index = nodes_info.get(channel_db_name)
                        if dim == 0:
                            zerod_nodes.append(
                                (
                                    fullname,
                                    channel_db_name,
                                    channel_data_node,
                                    last_index,
                                )
                            )
                        else:
                            other_nodes[fullname] = (
                                channel_db_name,
                                dim,
                                channel_data_node,
                            )
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
                    for (
                        (fullname, channel_db_name, _, last_index),
                        (_, channel_data),
                    ) in zip(
                        zerod_nodes, get_data_from_nodes(pipeline, *zerod_nodes_index)
                    ):
                        new_data_flags = (
                            True if len(channel_data) > 0 else new_data_flags
                        )
                        prev_data = nodes_data.get(fullname, [])
                        nodes_data[fullname] = numpy.concatenate(
                            (prev_data, channel_data)
                        )
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
                                channels["master"]["scalars"]
                                + channels.get("scalars", [])
                            )
                            if event_channels_full_name.intersection(channels_set):
                                scan_data_callback(
                                    "0d",
                                    master,
                                    {"data": nodes_data, "scan_info": scan_info},
                                )
                                gevent.idle()
                    elif zerod_nodes:
                        gevent.sleep(.1)  # relax a little bit
                    for master, channels in scan_info["acquisition_chain"].items():
                        other_names = channels.get("spectra", []) + channels.get(
                            "images", []
                        )
                        for i, channel_name in enumerate(other_names):
                            channel_db_name, dim, channel_data_node = other_nodes.get(
                                channel_name, (None, -1, None)
                            )
                            if channel_db_name:
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

            elif event_type == _SCAN_EVENT.END:
                for db_name, scan_info in event_data:
                    if scan_end_callback:
                        scan_end_callback(scan_info)
                    running_scans.pop(db_name, None)
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
        current_scan_node = None

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
