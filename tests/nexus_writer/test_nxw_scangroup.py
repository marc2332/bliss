# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import gevent
import numpy
from bliss.common import scans
from bliss.scanning.group import Sequence, Group
from bliss.scanning.chain import AcquisitionChannel
import nxw_test_utils
import nxw_test_data


def test_nxw_scangroup(nexus_writer_config):
    _test_nxw_scangroup(**nexus_writer_config)


def test_nxw_scangroup_alt(nexus_writer_config_alt):
    _test_nxw_scangroup(**nexus_writer_config_alt)


def test_nxw_scangroup_nopolicy(nexus_writer_config_nopolicy):
    _test_nxw_scangroup(**nexus_writer_config_nopolicy)


def test_nxw_scangroup_base(nexus_writer_base):
    _test_nxw_scangroup(**nexus_writer_base)


def test_nxw_scangroup_base_alt(nexus_writer_base_alt):
    _test_nxw_scangroup(**nexus_writer_base_alt)


def test_nxw_scangroup_base_nopolicy(nexus_writer_base_nopolicy):
    _test_nxw_scangroup(**nexus_writer_base_nopolicy)


@nxw_test_utils.writer_stdout_on_exception
def _test_nxw_scangroup(session=None, tmpdir=None, writer=None, **kwargs):
    session.scan_saving.add("technique", "none")
    npoints = 10
    detector1 = session.env_dict["diode3"]
    detector2 = session.env_dict["diode4"]
    motor = session.env_dict["robx"]

    seq = Sequence()
    seq.add_custom_channel(AcquisitionChannel("customdata", numpy.float, ()))
    seq.add_custom_channel(AcquisitionChannel("diode34", numpy.float, ()))
    with seq.sequence_context() as scan_seq:
        scan1 = scans.loopscan(npoints, .1, detector1, run=False)
        scan2 = scans.ascan(motor, 0, 1, npoints - 1, .1, detector2, run=False)
        g1 = nxw_test_utils.run_scan(scan1, runasync=True)
        seq.custom_channels["customdata"].emit(numpy.arange(npoints // 2))
        g2 = nxw_test_utils.run_scan(scan2, runasync=True)
        seq.custom_channels["customdata"].emit(numpy.arange(npoints // 2, npoints))
        gevent.joinall([g1, g2])
        diode34 = scan1.get_data()["diode3"] + scan2.get_data()["diode4"]
        seq.custom_channels["diode34"].emit(diode34)
        scan_seq.add(scan1)
        scan_seq.add(scan2)
    scan_grp = Group(scan1, scan2)
    scan_seq.wait_all_subscans(timeout=10)
    scan_grp.wait_all_subscans(timeout=10)

    nxw_test_utils.wait_scan_data_finished(
        [scan1, scan2, scan_seq.sequence.scan, scan_grp.scan], writer=writer
    )
    nxw_test_data.assert_scan_data(
        scan1,
        scan_shape=(npoints,),
        positioners=[["elapsed_time", "epoch"]],
        detectors=["diode3"],
        **kwargs
    )
    nxw_test_data.assert_scan_data(
        scan2,
        scan_shape=(npoints,),
        positioners=[["robx"]],
        detectors=["diode4"],
        **kwargs
    )
    nxw_test_data.assert_scangroup_data(scan_seq.sequence, **kwargs)
    nxw_test_data.assert_scangroup_data(scan_grp, **kwargs)
