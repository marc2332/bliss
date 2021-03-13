# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from gevent.queue import Queue
import gevent
from contextlib import contextmanager
import numpy
from bliss.scanning.chain import (
    AcquisitionMaster,
    AcquisitionSlave,
    AcquisitionChannel,
    AcquisitionChain,
)
from bliss.scanning.scan import Scan
from bliss.data.nodes.scan import ScanNode
from bliss.scanning.scan import ScanState, ScanPreset
from bliss.scanning.scan_info import ScanInfo
from bliss.common.logtools import user_warning


class ScanGroup(Scan):
    _NODE_TYPE = "scan_group"
    _REDIS_CACHING = False

    def is_flint_recommended(self):
        """Return true if flint is recommended for this scan

        A scan group is usually not displayed, except there is an explicit plot
        """
        scan_info = self._scan_info
        plots = scan_info.get("plots", [])
        return len(plots) >= 1


class ScanSequenceError(RuntimeError):
    pass


class SequenceContext:
    def __init__(self, sequence):
        self.sequence = sequence

    def _wait_before_adding_scan(self, scan):
        scan.wait_state(ScanState.STARTING)
        self.sequence.group_acq_master.new_subscan(scan)

    def _add_via_node(self, scan):
        assert isinstance(scan, ScanNode)
        self.sequence._scans.append(scan)
        self.sequence.group_acq_master.new_subscan(scan)

    def add(self, scan: Scan):
        """Add a scan into the group.

        If the scan was not started, this method also flag the scan
        `scan_info` with the group node_name.

        Argument:
            scan: A scan
        """
        assert isinstance(scan, Scan)
        self.sequence._scans.append(scan)

        if scan.state >= ScanState.STARTING:
            # scan is running / has been running already
            self.sequence.group_acq_master.new_subscan(scan)
        else:
            scan.scan_info["group"] = self.sequence.node.db_name
            self.sequence._waiting_scans.append(
                gevent.spawn(self._wait_before_adding_scan, scan)
            )

    def add_and_run(self, scan: Scan):
        """Add a scan into the group, run it, and wait for
        termination.

        This method also flag the scan `scan_info` with
        the group node_name.

        Argument:
            scan: A scan

        Raise:
            ScanSequenceError: If the scan was already started.
        """
        assert isinstance(scan, Scan)
        if scan.state != 0:
            raise ScanSequenceError(
                f'Error in  add_and_run: scan "{scan.name}" has already been started before!'
            )
        scan.scan_info["group"] = self.sequence.node.db_name

        self.add(scan)
        g = gevent.spawn(scan.run)
        g.join()

    def wait_all_subscans(self, timeout=None):
        self.sequence.wait_all_subscans(timeout=timeout)


class StatePreset(ScanPreset):
    def __init__(self, sequence):
        super().__init__()
        self._sequence = sequence

    def stop(self, scan):
        if len(self._sequence._scans) == 0:
            return
        max_state = ScanState.DONE
        for s in self._sequence._scans:
            if (
                isinstance(s, ScanNode)
                and s.info.get("state", ScanState.DONE) > max_state
            ):
                max_state = s.info.get("state", ScanState.DONE)
            elif isinstance(s, Scan) and s.state > max_state:
                max_state = s.state
        if max_state == ScanState.KILLED:
            user_warning("at least one of the scans in the sequence was KILLED")
            scan._set_state(ScanState.KILLED)
        elif max_state == ScanState.USER_ABORTED:
            user_warning("at least one of the scans in the sequence was USER_ABORTED")
            scan._set_state(ScanState.USER_ABORTED)


class Sequence:
    """
    Should have a scan as internal property that runs
    in a spawned mode in the background. Each new scan
    should publish itself (trigger a master inside the scan)

    There should be a possibility of calc channels.

    TODO: How to handle progress bar for sequence?
    """

    def __init__(self, scan_info=None, title="sequence_of_scans"):
        self.title = title
        self.scan = None
        self._scan_info = ScanInfo.normalize(scan_info)
        self._scan_info["is-scan-sequence"] = True
        self.custom_channels = dict()

        self._scans = list()  # scan objects or scan nodes
        self._waiting_scans = list()

    def add_custom_channel(self, acq_channel):
        assert isinstance(acq_channel, AcquisitionChannel)
        self.custom_channels[acq_channel.name] = acq_channel

    def wait_all_subscans(self, timeout=0):
        if timeout is not None:
            with gevent.timeout.Timeout(timeout):
                gevent.joinall(self._waiting_scans)
        else:
            gevent.joinall(self._waiting_scans)

    @contextmanager
    def sequence_context(self):
        self._build_scan()
        group_scan = gevent.spawn(self.scan.run)

        try:
            with gevent.timeout.Timeout(3):
                self.scan.wait_state(ScanState.STARTING)
                if self.group_custom_slave is not None:
                    self.group_custom_slave.start_event.wait()
            yield SequenceContext(self)
        finally:
            # Stop the iteration over group_acq_master
            self.group_acq_master.scan_queue.put(StopIteration)

            # The subscans should have finished before exiting the context
            try:
                self.wait_all_subscans(timeout=0)
                scans_finished = True
            except gevent.Timeout:
                gevent.killall(self._waiting_scans)
                scans_finished = False

            # Wait until all sequence events are published in Redis
            # Note: publishing is done by iterating over group_acq_master
            events_published = True
            if len(self._scans) > 0:
                try:
                    # Timeout not specified because we have no way of
                    # estimating how long it will take.
                    events_published = self.group_acq_master.wait_all_published()
                except ScanSequenceError:
                    events_published = False

            # Wait until the sequence itself finishes
            group_scan.get(timeout=None)

            # Raise exception when incomplete
            if not scans_finished:
                raise ScanSequenceError(
                    f'Some scans of the sequence "{self.title}" have not finished before exiting the sequence context'
                )
            elif not events_published:
                raise ScanSequenceError(
                    f'Some events of the sequence "{self.title}" were not published in Redis'
                )

    def _build_scan(self):
        self.group_acq_master = GroupingMaster()
        chain = AcquisitionChain()
        chain.add(self.group_acq_master)

        if len(self.custom_channels) > 0:
            self.group_custom_slave = GroupingSlave(
                "custom_channels", self.custom_channels.values()
            )
            chain.add(self.group_acq_master, self.group_custom_slave)
        else:
            self.group_custom_slave = None

        self.scan = ScanGroup(chain, self.title, save=True, scan_info=self._scan_info)
        self.scan.add_preset(StatePreset(self))

    @property
    def node(self):
        return self.scan.node

    @property
    def scan_info(self):
        """Return the scan info of this sequence.

        Which is the initial one, or the one published by the scan which publish
        this sequence.
        """
        if self.scan is None:
            return self._scan_info
        else:
            self.scan.scan_info

    @property
    def state(self):
        if self.scan is None:
            return ScanState.IDLE
        else:
            return self.scan.state


class Group(Sequence):
    def __init__(self, *scans, title="group_of_scans", scan_info=None):
        Sequence.__init__(self, title=title, scan_info=scan_info)

        with self.sequence_context() as seq_context:
            for s in scans:
                if isinstance(s, ScanNode):
                    if s.node_type not in ["scan", "scan_group"]:
                        raise ScanSequenceError("Only scans can be added to group")
                    scan_node = s
                elif isinstance(s, Scan):
                    if s.state < ScanState.STARTING:
                        raise ScanSequenceError(
                            "Only scans that have been run before can be added to group"
                        )
                    scan_node = s.node
                elif type(s) == int:
                    scan_node = self.find_scan_node(s)
                else:
                    raise ScanSequenceError(
                        "Invalid argument: no scan node found that corresponds to "
                        + str(s)
                    )

                seq_context._add_via_node(scan_node)

    def find_scan_node(self, scan_number: int):
        for node in self.scan.root_node.walk(
            include_filter="scan", exclude_children=("scan", "scan_group"), wait=False
        ):
            if node.info["scan_nb"] == scan_number:
                return node
        raise ScanSequenceError(f"Scan number '{scan_number}' not found")


class GroupingMaster(AcquisitionMaster):
    def __init__(self):

        AcquisitionMaster.__init__(
            self,
            None,
            name="GroupingMaster",
            npoints=0,
            prepare_once=True,
            start_once=True,
        )

        self.scan_queue = Queue()

        self._node_channel = AcquisitionChannel(
            "scans", str, (), reference=True, data_node_type="node_ref_channel"
        )

        self.channels.append(self._node_channel)

        self._number_channel = AcquisitionChannel("scan_numbers", int, ())
        self.channels.append(self._number_channel)

        # Synchronize GroupingMaster iteration and wait_all_published
        self._publishing = False
        self._publish_success = True
        self._publish_event = gevent.event.Event()
        self._publish_event.set()

    def prepare(self):
        pass

    def __iter__(self):
        self._publishing = True
        try:
            yield self
            for scan in self.scan_queue:
                self._publish_new_subscan(scan)
                yield self
        finally:
            self._publishing = False

    def _publish_new_subscan(self, scan):
        """Publish group scan events in Redis related to one scan
        """
        self._publish_event.clear()
        try:
            if isinstance(scan, Scan):
                scan = scan.node

            # Emit sequence events
            self._number_channel.emit(int(scan.info["scan_nb"]))
            self._node_channel.emit(scan.db_name)

            # Reset the node TTL's
            if scan.connection.ttl(scan.db_name) > 0:
                scan.set_ttl()
                for n in scan.walk(wait=False):
                    if n.connection.ttl(n.db_name) > 0:
                        n.set_ttl(include_parents=False)
        except BaseException:
            self._publish_success &= False
            raise
        else:
            self._publish_success &= True
        finally:
            self._publish_event.set()

    def wait_all_published(self, timeout=None):
        """Wait until `_publish_new_subscan` is called for all subscans
        that are queued. Publishing is done by iterating over this
        `GroupingMaster`.

        Raises ScanSequenceError upon timeout or when there are scans
        in the queue while nobody is iterating to publish their
        associated sequence events.
        """
        with gevent.Timeout(timeout, ScanSequenceError):
            success = True
            while self.scan_queue.qsize() > 0 and self._publishing:
                self._publish_event.wait()
                success &= self._publish_success
                gevent.sleep()
            if self.scan_queue.qsize() > 0:
                raise ScanSequenceError
            self._publish_event.wait()
            success &= self._publish_success
            return success

    def new_subscan(self, scan):
        self.scan_queue.put(scan)

    def start(self):
        pass

    def stop(self):
        pass


class GroupingSlave(
    AcquisitionSlave
):  # one instance of this for channels published `on the fly` and one that is called after the scan?
    def __init__(self, name, channels):

        AcquisitionSlave.__init__(self, None, name=name)
        self.start_event = gevent.event.Event()
        for channel in channels:
            self.channels.append(channel)

    def prepare(self):
        pass

    def start(self):
        self.start_event.set()

    def trigger(self):
        pass

    def stop(self):
        pass
