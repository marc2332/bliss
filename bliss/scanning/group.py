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
from bliss.data.node import get_session_node
from bliss.scanning.scan import ScanState, ScanPreset
from bliss.scanning.scan_info import ScanInfo
from bliss.data.node import create_node
from bliss import current_session
from bliss.common.logtools import user_warning


class ScanGroup(Scan):
    def _create_data_node(self, node_name):
        self._Scan__node = create_node(
            node_name, "scan_group", parent=self.root_node, info=self._scan_info
        )

    def is_flint_recommended(self):
        """Return true if flint is recommended for this scan

        A scan group is usually not displayed, except there is an explicit plot
        """
        scan_info = self._scan_info
        plots = scan_info.get("plots", [])
        return len(plots) >= 1


class Sequence:
    """ should have a scan as internal property that runs
    in a spawned mode in the background. Each new scan
    should publish itself (trigger a master inside the scan)
    
    there should be a possibiltiy of calc channels.
    
    progressbar for sequence??
            """

    def __init__(self, scan_info=None, title="sequence_of_scans"):

        self.title = title
        self.scan = None
        self._scan_info = ScanInfo.normalize(scan_info)
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
                RuntimeError: If the scan was already started.
            """
            assert isinstance(scan, Scan)
            if scan.state != 0:
                raise RuntimeError(
                    f'Error in  add_and_run: scan "{scan.name}" has already been started before!'
                )
            scan.scan_info["group"] = self.sequence.node.db_name

            self.add(scan)
            g = gevent.spawn(scan.run)
            g.join()

        def wait_all_subscans(self, timeout=None):
            self.sequence.wait_all_subscans(timeout)

    @contextmanager
    def sequence_context(self):
        self._build_scan()
        group_scan = gevent.spawn(self.scan.run)

        try:
            with gevent.timeout.Timeout(3):
                self.scan.wait_state(ScanState.STARTING)
                if self.group_custom_slave is not None:
                    self.group_custom_slave.start_event.wait()
            yield self.SequenceContext(self)
        finally:
            self.group_acq_master.queue.put(StopIteration)

            err = False
            try:
                self.wait_all_subscans(0)
            except gevent.Timeout:
                gevent.killall(self._waiting_scans)
                err = True

            if len(self._scans) > 0:
                # waiting for the last point to be published before killing the scan greenlet
                while self.group_acq_master.queue.qsize() > 0:
                    self.group_acq_master.publish_event.wait()
                    gevent.sleep(0)
                self.group_acq_master.publish_event.wait()

            group_scan.get()

            if err:
                raise RuntimeError(
                    f'Some scans of the sequence "{self.title}" have not been excecuted! \n The dataset will be incomplete!'
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

        class StatePreset(ScanPreset):
            def __init__(self, sequence):
                ScanPreset.__init__(self)
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
                    user_warning(
                        "at least one of the scans in the sequence was USER_ABORTED"
                    )
                    scan._set_state(ScanState.USER_ABORTED)

        self.scan = ScanGroup(chain, self.title, save=True, scan_info=self._scan_info)
        state_preset = StatePreset(self)
        self.scan.add_preset(state_preset)

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
                        raise RuntimeError("Only scans can be added to group!")
                    scan = s
                elif isinstance(s, Scan):
                    if s.state < ScanState.STARTING:
                        raise RuntimeError(
                            "Only scans that have been run before can be added to group!"
                        )
                    scan = s.node
                elif type(s) == int:
                    node_found = False
                    for node in get_session_node(current_session.name).walk(
                        filter="scan", wait=False
                    ):
                        if node.info["scan_nb"] == s:
                            scan = node
                            node_found = True
                            break
                    if not node_found:
                        raise RuntimeError(f"Scan {s} not found!")
                else:
                    raise RuntimeError(
                        f"Invalid argument: no scan node found that corresponds to {s}!"
                    )

                seq_context._add_via_node(scan)


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

        self.queue = Queue()

        self._node_channel = AcquisitionChannel(
            "scans", numpy.str, (), reference=True, data_node_type="node_ref_channel"
        )

        self.channels.append(self._node_channel)

        self._number_channel = AcquisitionChannel("scan_numbers", numpy.int, ())
        self.channels.append(self._number_channel)

        self.publish_event = gevent.event.Event()
        self.publish_event.set()

    def prepare(self):
        pass

    def __iter__(self):
        yield self
        for scan in self.queue:
            self._new_subscan(scan)
            yield self

    def _new_subscan(self, scan):
        self.publish_event.clear()

        if isinstance(scan, Scan):
            scan = scan.node

        self._number_channel.emit(int(scan.info["scan_nb"]))
        self._node_channel.emit(scan.db_name)

        # handling of ttl of subscan
        if scan.connection.ttl(scan.db_name) > 0:
            for n in scan.walk(wait=False):
                if n.connection.ttl(n.db_name) > 0:
                    n.set_ttl()

        self.publish_event.set()

    def new_subscan(self, scan):
        self.queue.put(scan)

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
