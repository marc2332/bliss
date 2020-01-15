# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.scanning.chain import AcquisitionChain, AcquisitionMaster, AcquisitionSlave
from bliss.scanning.scan import Scan
from bliss.controllers.lima.roi import Roi
from bliss.common.scans import ascan


def check_acq_chan_unique_name(acq_chain):
    channels = []

    for n in acq_chain._tree.is_branch(acq_chain._tree.root):
        check_chan_name(acq_chain, n, channels)


def check_chan_name(acq_chain, node, channels):
    # TODO: check if name or fullname should be used below
    if node.channels:
        for c in node.channels:
            assert not c.name in channels
            channels.append(c.name)

    for n in acq_chain._tree.is_branch(node):
        check_chan_name(acq_chain, n, channels)


def test_unique_channel_names_in_scan(
    beacon, default_session, lima_simulator, lima_simulator2
):
    lima_sim = default_session.config.get("lima_simulator")
    lima_sim2 = default_session.config.get("lima_simulator2")
    diode2 = default_session.config.get("diode2")
    diode = default_session.config.get("diode")
    roby = default_session.config.get("roby")
    robz = default_session.config.get("robz")
    r2 = Roi(100, 100, 100, 200)
    lima_sim2.roi_counters["r2"] = r2
    lima_sim.roi_counters["r2"] = r2
    l2 = ascan(roby, 0, 1, 5, .1, lima_sim2, diode2, run=False)
    l1 = ascan(robz, 0, 1, 5, .1, lima_sim, diode, run=False)
    ac1 = l1.acq_chain
    ac2 = l2.acq_chain

    def add_to_chain(chain1, chain2, node):
        for child in chain2._tree.children(node):
            if child.bpointer == "root":
                chain1.add(child.identifier)
            else:
                chain1.add(node, child.identifier)
            add_to_chain(chain1, chain2, child.identifier)

    a = ac2._tree.children("root")[0].identifier
    a._AcquisitionObject__name = "myaxis"
    a.terminator = False
    add_to_chain(ac1, ac2, ac2._tree.root)
    myscan = Scan(ac1)
    check_acq_chan_unique_name(myscan.acq_chain)
