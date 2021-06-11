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
import contextlib

from typing import Dict

from bliss.common.counter import Counter
from bliss.common.axis import Axis
from bliss.data.nodes.scan import get_data_from_nodes
from bliss.data.nodes.channel import ChannelDataNode
from bliss.data.node import get_or_create_node
from bliss.data.events import Event
from bliss.data.events import EventType
from bliss.common.utils import get_matching_names
from bliss.config.streaming import DataStreamReaderStopHandler


def get_counter_names(scan):
    """
    Return a list of counter names
    """
    return [
        node.name for node in scan.nodes.values() if isinstance(node, ChannelDataNode)
    ]


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

    def on_event_received(self, event: Event):
        """
        Called upon new event

        Mostly used for backward compatibility with `DefaultScanObserver`.
        """
        pass

    def on_scan_created(self, scan_db_name: str, scan_info: Dict):
        """
        Called upon scan created (devices are not yet prepared).

        Arguments:
            scan_db_name: Identifier of the scan
            scan_info: Dictionary containing scan metadata
        """
        pass

    def on_scan_started(self, scan_db_name: str, scan_info: Dict):
        """
        Called upon scan started (the devices was prepared).

        Arguments:
            scan_db_name: Identifier of the scan
            scan_info: Dictionary containing scan metadata updated with metadata
                       prepared metadata from controllers
        """
        pass

    def on_child_created(self, scan_db_name: str, node):
        """
        Called upon scan child creation (e.g. channel node)

        Arguments:
            scan_db_name: Identifier of the parent scan
            node: Redis node of this child
        """
        pass

    def on_scalar_data_received(
        self,
        scan_db_name: str,
        channel_name: str,
        index: int,
        data_bunch: typing.Union[list, numpy.ndarray],
    ):
        """
        Called upon a bunch of scalar data (0dim) from a `top_master` was
        received.

        Arguments:
            scan_db_name: Identifier of the parent scan
            channel_name: Name of the updated channel
            index: Start index of the data bunch in the real data stream.
                   There could be wholes between 2 bunches of data.
            data_bunch: The list of data received, as a bunch of data.
        """
        pass

    def on_ndim_data_received(
        self,
        scan_db_name: str,
        channel_name: str,
        dim: int,
        index: int,
        data_bunch: typing.Union[list, numpy.ndarray],
    ):
        """Called upon a ndim data (except 0dim, except data ref) data was
        received.

        - For 0dim data, see `on_scalar_data_received`.

        Arguments:
            scan_db_name: Identifier of the parent scan
            channel_name: Name of the channel emitting the data
            dim: Dimension of this data (MCA is 1, image is 2)
            index: Start index of the data bunch in the real data stream.
                   There could be wholes between 2 bunches of data.
            data_bunch: The list of data received, as a bunch of data.
        """
        pass

    def on_lima_ref_received(
        self, scan_db_name: str, channel_name: str, dim: int, source_node, event_data
    ):
        """Called upon a ndim (except 0dim) data was received.

        For 0dim data, see `on_scalar_data_received`.

        Arguments:
            scan_db_name: Identifier of the parent scan
            channel_name: Name of the channel emitting the data
            dim: Dimension of this data
            source_node: Node containing the updated data
            event_data: Data of the event
        """
        pass

    def on_scan_finished(self, scan_db_name: str, scan_info: Dict):
        """
        Called upon scan end.

        Arguments:
            scan_db_name: Identifier of the parent scan
            scan_info: Dictionary containing scan metadata updated with
                       prepared and finished metadata from controllers
                       Other fields like positioners and datetime are also
                       updated.
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

        self._running = False
        """True if the watcher was started."""

        self._running_scans = set()
        """Store running scans"""

        self._ready_event = gevent.event.Event()
        """Handle the ready event"""

        self._terminated_event = gevent.event.Event()
        """Handle the end event"""

        self._no_scans_event = gevent.event.Event()
        """Handle the amount of listened scans"""

        self._stop_handler = DataStreamReaderStopHandler()
        """Handler to be able to stop the event loop"""

        self._no_scans_event.set()

    def wait_ready(self, timeout: float = None):
        """Wait until the scan watcher is ready to receive new event.

        The steps between `started` and `ready` can takes few seconds depending
        on the amount of data and the load of Redis.

        Arguments:
            timeout: If not `None`, it should be a floating point number
                     specifying a timeout for the operation in seconds
                     (or fractions thereof).
        """
        self._ready_event.wait(timeout=timeout)

    def wait_no_more_running_scans(self, timeout: float = None):
        """Wait until there is no more running scans in this watcher.
        """
        self._no_scans_event.wait(timeout=timeout)

    def wait_terminated(self, timeout: float = None):
        """Wait until the scan watcher is terminated.

        The steps between `started` and `ready` can takes few seconds depending
        on the amount of data and the load of Redis.

        Arguments:
            timeout: If not `None`, it should be a floating point number
                     specifying a timeout for the operation in seconds
                     (or fractions thereof).
        """
        self._terminated_event.wait(timeout=timeout)

    def running_scan_names(self) -> typing.Sequence[str]:
        """
        Returns the known running scans with there db names.

        Only managed scans are listed here. For example, if `watch_scan_group`
        was set to False, this scans will not be shown.
        """
        return list(self._running_scans)

    def set_exclude_existing_scans(self, exclude: bool):
        """
        Include or exclude existing scans. Default is False.

        Will become True by default in the future.

        It have to be set before start.
        """
        assert not self._running
        self._exclude_existing_scans = exclude

    def set_watch_scan_group(self, watch: bool):
        """
        Set to True to include scan groups like any other scans. Default is False.

        It have to be set before start.
        """
        assert not self._running
        self._watch_scan_group = watch

    def set_observer(self, observer: ScansObserver):
        """
        Set the observer to use with this watcher process.

        If not set, the `run` method will raise an exception.
        """
        assert not self._running
        self._observer = observer

    def _set_stop_handler(self, stop_handler):
        """
        Backward compatibility code with `watch_session_scans`.

        This function have to be removed with `watch_session_scans`.
        """
        assert not self._running
        self._stop_handler = stop_handler

    def _get_scan_db_name_from_child(self, db_name: str) -> str:
        """
        Returns the scan_db_name from the db_name of a child.

        It also works with the `scan_db_name`.
        """
        for key in self._running_scans:
            if db_name.startswith(key):
                return key
        return None

    @contextlib.contextmanager
    def watch(self):
        """Context manager to start and stop the watcher.

        It uses a gevent spawn.

        Yield:
            The spawned greenlet
        """
        try:
            gwatcher = gevent.spawn(self.run)
            gwatcher.name = "bliss_scans_watcher"
            self.wait_ready(timeout=3)
            yield gwatcher
        finally:
            self.wait_no_more_running_scans(timeout=2)
            self.stop()
            try:
                self.wait_terminated(timeout=1)
            finally:
                gwatcher.kill()

    def run(self):
        """
        Run watching scan events.

        This method is blocking. But can be terminated by calling `stop`.

        Any scan node that is created before the `ready_event` will not be watched
        when `exclude_existing_scans` is True.
        """
        assert not self._running
        self._terminated_event.clear()
        self._running = True
        try:
            session_node = get_or_create_node(self._session_name, node_type="session")
            if session_node is None:
                return

            observer = self._observer
            if observer is None:
                raise RuntimeError("No observer was set")

            if self._exclude_existing_scans:
                exclude_existing_children = "scan", "scan_group"
            else:
                exclude_existing_children = None

            for event in session_node.walk_on_new_events(
                stop_handler=self._stop_handler,
                exclude_existing_children=exclude_existing_children,
                started_event=self._ready_event,
            ):
                event_type, node, event_data = event
                try:
                    observer.on_event_received(event)
                except Exception:
                    sys.excepthook(*sys.exc_info())

                if event_type == EventType.NEW_NODE:
                    node_type = node.type
                    db_name = node.db_name
                    if node_type == "scan":
                        # New scan was created
                        scan_info = node.info.get_all()
                        self._running_scans.add(db_name)
                        self._no_scans_event.clear()
                        observer.on_scan_created(db_name, scan_info)
                    elif node_type == "scan_group":
                        if self._watch_scan_group:
                            # New scan was created
                            scan_info = node.info.get_all()
                            self._running_scans.add(db_name)
                            self._no_scans_event.clear()
                            observer.on_scan_created(db_name, scan_info)
                    else:
                        scan_db_name = self._get_scan_db_name_from_child(db_name)
                        if scan_db_name is not None:
                            try:
                                observer.on_child_created(scan_db_name, node)
                            except Exception:
                                sys.excepthook(*sys.exc_info())
                elif event_type == EventType.NEW_DATA:
                    db_name = node.db_name
                    if not hasattr(node, "fullname"):
                        # not a node we want to do anything with here
                        continue

                    fullname = node.fullname

                    scan_db_name = self._get_scan_db_name_from_child(db_name)
                    if scan_db_name is not None:
                        if node.type == "channel":
                            description = event_data.description
                            shape = description.get("shape")
                            dim = len(shape)
                            is_scalar = dim == 0
                        else:
                            is_scalar = False

                        if is_scalar:
                            try:
                                observer.on_scalar_data_received(
                                    scan_db_name=scan_db_name,
                                    channel_name=fullname,
                                    index=event_data.first_index,
                                    data_bunch=event_data.data,
                                )
                            except Exception:
                                sys.excepthook(*sys.exc_info())
                        else:
                            if node.type == "lima":
                                # Lima and only Lima deals with ref for now
                                # FIXME: It would be good to have a dedicated event type for that
                                try:
                                    observer.on_lima_ref_received(
                                        scan_db_name=scan_db_name,
                                        channel_name=fullname,
                                        source_node=node,
                                        dim=2,
                                        event_data=event_data,
                                    )
                                except Exception:
                                    sys.excepthook(*sys.exc_info())
                            else:
                                try:
                                    observer.on_ndim_data_received(
                                        scan_db_name=scan_db_name,
                                        channel_name=fullname,
                                        dim=dim,
                                        index=event_data.first_index,
                                        data_bunch=event_data.data,
                                    )
                                except Exception:
                                    sys.excepthook(*sys.exc_info())
                elif event_type == EventType.PREPARED_SCAN:
                    node_type = node.type
                    if self._watch_scan_group or node_type == "scan":
                        db_name = node.db_name
                        if db_name in self._running_scans:
                            scan_info = node.info.get_all()
                            try:
                                observer.on_scan_started(db_name, scan_info)
                            except Exception:
                                sys.excepthook(*sys.exc_info())
                elif event_type == EventType.END_SCAN:
                    node_type = node.type
                    if self._watch_scan_group or node_type == "scan":
                        db_name = node.db_name
                        if db_name in self._running_scans:
                            try:
                                scan_info = node.info.get_all()
                                try:
                                    observer.on_scan_finished(db_name, scan_info)
                                except Exception:
                                    sys.excepthook(*sys.exc_info())
                            finally:
                                self._running_scans.discard(db_name)
                                if len(self._running_scans) == 0:
                                    self._no_scans_event.set()
                gevent.idle()
        finally:
            self._running = False
            self._terminated_event.set()

    def stop(self):
        """Call it to stop the event loop."""
        if self._running:
            self._stop_handler.stop()


class DefaultScansObserver(ScansObserver):
    """Default scan observer.

    This observer provides a compatibility with the previous implementation:

    - Backward compatible API for callbacks (BLISS <= 1.7)
    - Storing scan_info per scans
    - Storing the whole data for each scalar channels
    """

    class _ScanDescription(typing.NamedTuple):
        scan_info: Dict
        """Scan_info of the scan"""
        channels_to_master: Dict[str, str]
        """Describe the master for each channels"""
        channels_data: Dict[str, numpy.ndarray]
        """Store the full data per scalar channels"""

    def __init__(self):
        self._running_scans: Dict[str, self._ScanDescription] = {}
        self.scan_new_callback: typing.Callable[[Dict], None] = None
        self.scan_new_child_callback: typing.Callable[[Dict, typing.Any], None] = None
        self.scan_data_callback: typing.Callable[[str, str, Dict], None] = None
        self.scan_end_callback: typing.Callable[[Dict], None] = None
        self._current_event: Event = None
        """
        Used to store a tuple with `event_type`, `node`, `event_data`
        during a callback event.

        Never None inside callbacks
        """

    def _get_scan_description(self, scan_db_name) -> _ScanDescription:
        return self._running_scans.get(scan_db_name)

    def on_event_received(self, event):
        """
        Called upon new event

        Mostly used for backward compatibility with `DefaultScanObserver`.
        """
        self._current_event = event

    def on_scan_created(self, scan_db_name: str, scan_info: Dict):
        # Pre-compute mapping from each channels to its master
        top_master_per_channels = {}
        for top_master, meta in scan_info["acquisition_chain"].items():
            for device_name in meta["devices"]:
                device_meta = scan_info["devices"][device_name]
                for channel_name in device_meta.get("channels", []):
                    top_master_per_channels[channel_name] = top_master
        self._running_scans[scan_db_name] = self._ScanDescription(
            scan_info, top_master_per_channels, {}
        )
        if self.scan_new_callback is not None:
            self.scan_new_callback(scan_info)

    def on_scan_finished(self, scan_db_name: str, scan_info: Dict):
        self._running_scans.pop(scan_db_name)
        if self.scan_end_callback is not None:
            self.scan_end_callback(scan_info)

    def on_child_created(self, scan_db_name: str, node):
        scan_desciption = self._get_scan_description(scan_db_name)
        if scan_desciption is None:
            # Scan not part of the listened scans
            return

        if self.scan_new_child_callback is not None:
            self.scan_new_child_callback(scan_desciption.scan_info, node)

    def on_scalar_data_received(
        self,
        scan_db_name: str,
        channel_name: str,
        index: int,
        data_bunch: typing.Union[list, numpy.ndarray],
    ):
        if self.scan_data_callback is None:
            return

        scan_desciption = self._get_scan_description(scan_db_name)
        if scan_desciption is None:
            # Scan not part of the listened scans
            return

        # in case of zerod, we keep all data value during the scan
        prev_data = scan_desciption.channels_data.get(channel_name, [])
        data = numpy.concatenate((prev_data, data_bunch))
        scan_desciption.channels_data[channel_name] = data

        top_master = scan_desciption.channels_to_master[channel_name]
        self.scan_data_callback(
            "0d",
            top_master,
            {
                "data": scan_desciption.channels_data,
                "scan_info": scan_desciption.scan_info,
            },
        )

    def on_ndim_data_received(
        self,
        scan_db_name: str,
        channel_name: str,
        dim: int,
        index: int,
        data_bunch: typing.Union[list, numpy.ndarray],
    ):
        if self.scan_data_callback is None:
            return

        scan_desciption = self._get_scan_description(scan_db_name)
        if scan_desciption is None:
            # Scan not part of the listened scans
            return

        source_node = self._current_event.node
        event_data = self._current_event.data

        top_master = scan_desciption.channels_to_master[channel_name]
        self.scan_data_callback(
            f"{dim}d",
            top_master,
            {
                "index": index,
                "data": data_bunch,
                "description": event_data.description,
                "channel_name": channel_name,
                "channel_data_node": source_node,
                "scan_info": scan_desciption.scan_info,
            },
        )

    def on_lima_ref_received(
        self, scan_db_name: str, channel_name: str, dim: int, source_node, event_data
    ):
        if self.scan_data_callback is None:
            return

        scan_desciption = self._get_scan_description(scan_db_name)
        if scan_desciption is None:
            # Scan not part of the listened scans
            return

        top_master = scan_desciption.channels_to_master[channel_name]
        self.scan_data_callback(
            f"{dim}d",
            top_master,
            {
                "index": event_data.first_index,
                "data": event_data.data,
                "description": event_data.description,
                "channel_name": channel_name,
                "channel_data_node": source_node,
                "scan_info": scan_desciption.scan_info,
            },
        )


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
    if stop_handler is not None:
        watcher._set_stop_handler(stop_handler)

    if ready_event is not None:

        def wait_ready():
            nonlocal ready_event
            watcher.wait_ready()
            ready_event.set()

        local_store_g = gevent.spawn(wait_ready)
    else:
        local_store_g = None

    observer = DefaultScansObserver()
    observer.scan_new_callback = scan_new_callback
    observer.scan_new_child_callback = scan_new_child_callback
    observer.scan_data_callback = scan_data_callback
    observer.scan_end_callback = scan_end_callback

    watcher.set_observer(observer)
    watcher.run()
    if local_store_g is not None:
        local_store_g.kill()
