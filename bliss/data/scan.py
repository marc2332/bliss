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
import warnings

from typing import Dict

from bliss.common.counter import Counter
from bliss.common.axis import Axis
from bliss.data.nodes.scan import get_data_from_nodes
from bliss.data.node import get_or_create_node
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


class ScansObserver:
    """
    Observer for the `ScansWatcher`.

    Provides methods which can be inherited to follow the life cycle of the
    scans of a session.
    """

    def on_scan_started(self, scan_info: Dict):
        """
        Called upon scan start.

        Arguments:
            scan_info: Dictionary containing scan metadata
        """
        pass

    def on_child_created(self, scan_info: Dict, node):
        """
        Called upon scan child creation (e.g. channel node)

        Arguments:
            scan_info: Dictionary containing metadata of this child
            node: Redis node of this child
        """
        pass

    def on_data_received(self, dim: str, top_master: str, data: Dict):
        """
        Data processing callback.

        Arguments:
            dim: One of "0d", "1d", "2d". (for now there is no 3 or 4d data)
            top_master: Name of the top master
            data: Structure containing the data, which is not the same for 0d
                  and for others.
        """
        pass

    def on_scan_finished(self, scna_info: Dict):
        """
        Called upon scan end.

        Arguments:
            scan_info: Dictionary containing scan metadata. It can be different
                       from the one at start.
        """
        pass


class ScansWatcher:
    """
    Watch scans from a specific session.

    Arguments:
        session_name: Name of the BLISS session
    """

    def __init__(self, session_name: str):
        self._session_name = session_name
        self._exclude_existing_scans = False
        self._watch_scan_group = False
        self._observer: ScansObserver = None

        self._started = False
        """True if processing"""

        self._running_scans = {}
        """Store running scans"""

    def set_exclude_existing_scans(self, exclude: bool):
        """
        Include or exclude existing scans. Default is False.

        Will become True by default in the future.

        It have to be set before start.
        """
        assert not self._started
        self._exclude_existing_scans = exclude

    def set_watch_scan_group(self, watch: bool):
        """
        Set to True to include scan groups like any other scans. Default is False.

        It have to be set before start.
        """
        assert not self._started
        self._watch_scan_group = watch

    def set_observer(self, observer: ScansObserver):
        """
        Set the observer to use with this watcher process.

        If not set, the `run` method will raise an exception.
        """
        assert not self._started
        self._observer = observer

    def run(self, ready_event=None, stop_handler=None):
        """
        Run watching scan events. This method will never ending.

        Any scan node that is created before the `ready_event` will not be watched
        when `exclude_existing_scans` is True.

        :param Event ready_event: started listening to Redis
        :param DataStreamReaderStopHandler stop_handler:
        """
        assert not self._started
        self._started = True

        session_node = get_or_create_node(self._session_name, node_type="session")
        if session_node is None:
            return

        observer = self._observer
        if observer is None:
            raise RuntimeError("No observer was set")

        def _get_scan_info(db_name):
            for key, scan_dict in self._running_scans.items():
                if db_name.startswith(key):
                    return scan_dict["info"], key
            return None, None

        if self._exclude_existing_scans:
            exclude_existing_children = "scan", "scan_group"
        else:
            exclude_existing_children = None

        for event_type, node, event_data in session_node.walk_on_new_events(
            stop_handler=stop_handler,
            exclude_existing_children=exclude_existing_children,
            started_event=ready_event,
        ):
            if event_type == event_type.NEW_NODE:
                node_type = node.type
                db_name = node.db_name
                if node_type == "scan":
                    # New scan was created
                    scan_dictionnary = self._running_scans.setdefault(db_name, dict())
                    if not scan_dictionnary:
                        scan_info = node.info.get_all()
                        scan_dictionnary["info"] = scan_info
                        observer.on_scan_started(scan_info)
                elif node_type == "scan_group":
                    if self._watch_scan_group:
                        # New scan was created
                        scan_dictionnary = self._running_scans.setdefault(
                            db_name, dict()
                        )
                        if not scan_dictionnary:
                            scan_info = node.info.get_all()
                            scan_dictionnary["info"] = scan_info
                            observer.on_scan_started(scan_info)
                else:
                    scan_info, scan_db_name = _get_scan_info(db_name)
                    if scan_info:  # scan_found
                        try:
                            observer.on_child_created(scan_info, node)
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
                    nodes_data = self._running_scans[scan_db_name].setdefault(
                        "nodes_data", dict()
                    )
                    if node.type == "channel":
                        shape = description.get("shape")
                        dim = len(shape)
                        # in case of zerod, we keep all data value during the scan
                        if dim == 0:
                            prev_data = nodes_data.get(fullname, [])
                            nodes_data[fullname] = numpy.concatenate((prev_data, data))
                            for master, channels in scan_info[
                                "acquisition_chain"
                            ].items():
                                channels_set = channels["master"][
                                    "scalars"
                                ] + channels.get("scalars", [])
                                if fullname in channels_set:
                                    try:
                                        observer.on_data_received(
                                            "0d",
                                            master,
                                            {
                                                "data": nodes_data,
                                                "scan_info": scan_info,
                                            },
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
                                observer.on_data_received(
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
                if self._watch_scan_group or node_type == "scan":
                    db_name = node.db_name
                    scan_dict = self._running_scans.pop(db_name, None)
                    if scan_dict:
                        scan_info = node.info.get_all()
                        try:
                            observer.on_scan_finished(scan_info)
                        except Exception:
                            sys.excepthook(*sys.exc_info())

            gevent.idle()


def watch_session_scans(
    session_name,
    scan_new_callback,
    scan_new_child_callback,
    scan_data_callback,
    scan_end_callback=None,
    ready_event=None,
    stop_handler=None,
    watch_scan_group: bool = False,
    exclude_existing_scans=None,
):
    """Any scan node that is created before the `ready_event` will not be watched
    when `exclude_existing_scans=True`.

    :param str session_name:
    :param callable scan_new_callback: called upon scan start
    :param callable scan_new_child_callback: called upon scan child creation (e.g. channel node)
    :param callable scan_data_callback: data processing callback
    :param callable scan_end_callback: called upon scan end
    :param Event ready_event: started listening to Redis
    :param DataStreamReaderStopHandler stop_handler:
    :param bool watch_scan_group: If True the scan groups are also listed like any other scans
    :param bool exclude_existing_scans: False by default (will become True by default in the future)
    """
    if exclude_existing_scans is None:
        exclude_existing_scans = False
        warnings.warn("'exclude_existing_scans' will be True by default", FutureWarning)

    watcher = ScansWatcher(session_name)
    watcher.set_exclude_existing_scans(exclude_existing_scans)
    watcher.set_watch_scan_group(watch_scan_group)

    class Observer(ScansObserver):
        def on_scan_started(self, scan_info: Dict):
            scan_new_callback(scan_info)

        def on_scan_finished(self, scna_info: Dict):
            if scan_end_callback is not None:
                scan_end_callback(scna_info)

        def on_child_created(self, scan_info: Dict, node):
            scan_new_child_callback(scan_info, node)

        def on_data_received(self, dim: str, top_master: str, data: Dict):
            scan_data_callback(dim, top_master, data)

    observer = Observer()
    watcher.set_observer(observer)
    watcher.run(ready_event=ready_event, stop_handler=stop_handler)
