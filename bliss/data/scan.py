# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import time
import datetime
import numpy
import pickle
import gevent
from bliss.common.cleanup import excepthook
from bliss.common.task import task
from bliss.data.node import DataNodeIterator, _get_or_create_node, DataNodeContainer
import logging
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
            self._data.start_time = self._info["start_time"]
            self._data.start_time_str = self._info["start_time_str"]
            self._data.start_timestamp = self._info["start_timestamp"]

    def end(self):
        if self.new_node:
            end_timestamp = time.time()
            end_time = datetime.datetime.fromtimestamp(end_timestamp)
            self._data.end_time = end_time
            self._data.end_time_str = end_time.strftime("%a %b %d %H:%M:%S %Y")
            self._data.end_timestamp = end_timestamp


def get_counter_names(scan):
    """
    Return a list of counter names
    """
    return [node.name for node in scan.nodes.values() if node.type == "channel"]


def get_data(scan):
    """
    Return a numpy structured array

    tips: to get the list of channels: data.dtype.names
          to get data of a channel: data["channel_name"]
    """
    dtype = list()
    chanlist = list()
    max_channel_len = 0
    connection = scan.node.db_connection
    pipeline = connection.pipeline()
    for device, node in scan.nodes.items():
        if node.type == "channel":
            channel_name = node.name
            chan = node
            try:
                saved_db_connection = chan.db_connection
                chan.db_connection = pipeline
                # append channel name and get all data from channel;
                # as it is in a Redis pipeline, get returns the
                # conversion function only - data will be received
                # after .execute()
                chanlist.append((channel_name, chan.get(0, -1)))
            finally:
                chan.db_connection = saved_db_connection

    result = pipeline.execute()

    structured_array_dtype = []
    for i, (channel_name, get_data_func) in enumerate(chanlist):
        channel_data = get_data_func(result[i])
        result[i] = channel_data
        structured_array_dtype.append(
            (channel_name, channel_data.dtype, channel_data.shape[1:])
        )

    max_channel_len = max((len(values) for values in result))

    data = numpy.zeros(max_channel_len, dtype=structured_array_dtype)

    for i, (channel_name, _) in enumerate(chanlist):
        data[channel_name] = result[i]

    return data


def _watch_data(scan_node, scan_info, scan_new_child_callback, scan_data_callback):
    scan_data = dict()
    data_indexes = dict()

    scan_data_iterator = DataNodeIterator(scan_node)
    for event_type, data_channel in scan_data_iterator.walk_events():
        if event_type == scan_data_iterator.NEW_CHILD_EVENT:
            scan_new_child_callback(scan_info, data_channel)
        elif event_type == scan_data_iterator.NEW_DATA_IN_CHANNEL_EVENT:
            data = data_channel.get(
                data_indexes.setdefault(data_channel.db_name, 0), -1
            )
            if not data:  # already received
                continue
            data_indexes[data_channel.db_name] += len(data)

            for master, channels in scan_info["acquisition_chain"].items():
                master_channels = channels["master"]
                scalars = channels.get("scalars", [])
                spectra = channels.get("spectra", [])
                images = channels.get("images", [])

                try:
                    for channel_name in master_channels["scalars"]:
                        scan_data.setdefault(channel_name, [])
                        data_channel_name = "%s:%s" % (
                            data_channel.parent.name,
                            data_channel.name,
                        )
                        if data_channel_name == channel_name:
                            scan_data[channel_name] = numpy.concatenate(
                                (scan_data[channel_name], data)
                            )
                            raise StopIteration

                    for i, channel_name in enumerate(scalars):
                        scan_data.setdefault(channel_name, [])
                        data_channel_name = "%s:%s" % (
                            data_channel.parent.name,
                            data_channel.name,
                        )
                        if data_channel_name == channel_name:
                            scan_data[channel_name] = numpy.concatenate(
                                (scan_data.get(channel_name, []), data)
                            )
                            with excepthook():
                                scan_data_callback(
                                    "0d",
                                    master,
                                    {
                                        "master_channels": master_channels["scalars"],
                                        "channel_index": i,
                                        "channel_name": channel_name,
                                        "data": scan_data,
                                    },
                                )
                            raise StopIteration

                    for i, channel_name in enumerate(spectra):
                        if data_channel.db_name.endswith(channel_name):
                            with excepthook():
                                scan_data_callback(
                                    "1d",
                                    master,
                                    {
                                        "channel_index": i,
                                        "channel_name": channel_name,
                                        "data": data,
                                    },
                                )
                            raise StopIteration
                    for i, channel_name in enumerate(images):
                        if data_channel.db_name.endswith(channel_name):
                            with excepthook():
                                scan_data_callback(
                                    "2d",
                                    master,
                                    {
                                        "channel_index": i,
                                        "channel_name": channel_name,
                                        "data": data,
                                    },
                                )
                            raise StopIteration
                except StopIteration:
                    break


def safe_watch_data(*args):
    with excepthook():
        _watch_data(*args)


@task
def watch_session_scans(
    session_name,
    scan_new_callback,
    scan_new_child_callback,
    scan_data_callback,
    ready_event=None,
):
    session_node = _get_or_create_node(session_name, node_type="session")

    if session_node is None:
        return

    data_iterator = DataNodeIterator(session_node)
    watch_data_task = None

    try:
        for scan_node in data_iterator.walk_from_last(
            filter="scan", include_last=False, ready_event=ready_event
        ):
            if watch_data_task:
                watch_data_task.kill()

            scan_info = scan_node.info.get_all()

            # call user callbacks and start data watch task for this scan
            with excepthook():
                # call 'scan_new' callback, if an exception happens in user
                # code the data watch task is *not* started -- it will be
                # retried at next scan
                scan_new_callback(scan_info)

                # spawn watching task: incoming scan data triggers
                # corresponding user callbacks (see code in '_watch_data')
                watch_data_task = gevent.spawn(
                    safe_watch_data,
                    scan_node,
                    scan_info,
                    scan_new_child_callback,
                    scan_data_callback,
                )
    finally:
        if watch_data_task is not None:
            watch_data_task.kill()
