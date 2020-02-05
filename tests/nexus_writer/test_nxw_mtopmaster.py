
# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import nxw_test_utils
import nxw_test_data


def test_nxw_mtopmaster(nexus_writer_config):
    _test_nxw_mtopmaster(**nexus_writer_config)


def test_nxw_mtopmaster_alt(nexus_writer_config_alt):
    _test_nxw_mtopmaster(**nexus_writer_config_alt)


def test_nxw_mtopmaster_nopolicy(nexus_writer_config_nopolicy):
    _test_nxw_mtopmaster(**nexus_writer_config_nopolicy)


def test_nxw_mtopmaster_base(nexus_writer_base):
    _test_nxw_mtopmaster(**nexus_writer_base)


def test_nxw_mtopmaster_base_alt(nexus_writer_base_alt):
    _test_nxw_mtopmaster(**nexus_writer_base_alt)


def test_nxw_mtopmaster_base_nopolicy(nexus_writer_base_nopolicy):
    _test_nxw_mtopmaster(**nexus_writer_base_nopolicy)


@nxw_test_utils.writer_stdout_on_exception
def _test_nxw_mtopmaster(**kwargs):
    _test_aloopscan(**kwargs)
    _test_limatimescan(**kwargs)


def _test_aloopscan(session=None, tmpdir=None, writer=None, **kwargs):
    mot = "robx"
    expo1 = 0.1
    npoints1 = 20
    expo2 = 0.5
    npoints2 = 4
    detectors1 = [
        "diode2alias",
        "diode3",
        "diode4",
        "diode5",
        "thermo_sample",
        "simu1",
        "sim_ct_gauss_noise",
        "lima_simulator",
    ]
    detectors2 = [
        "diode6",
        "diode7",
        "diode8",
        "diode9alias",
        "sim_ct_gauss",
        "simu2",
        "lima_simulator2",
    ]

    omot = session.env_dict[mot]
    odetectors1 = [session.env_dict[d] for d in detectors1]
    odetectors2 = [session.env_dict[d] for d in detectors2]
    odetectors1.append(session.env_dict["lima_simulator"].bpm)
    odetectors2.append(session.env_dict["lima_simulator2"].bpm)
    scan = session.env_dict["aloopscan"](
        omot, 0, 1, npoints1, expo1, odetectors1, npoints2, expo2, odetectors2
    )

    nxw_test_utils.run_scan(scan)
    nxw_test_utils.wait_scan_data_finished([scan], writer=writer)
    nxw_test_data.assert_scan_data(
        scan,
        subscan=1,
        scan_shape=(npoints1,),
        positioners=[[mot]],
        detectors=detectors1,
        master_name="subscan1tmr",
        **kwargs
    )
    nxw_test_data.assert_scan_data(
        scan,
        subscan=2,
        scan_shape=(npoints2,),
        positioners=[["elapsed_time", "epoch"]],
        detectors=detectors2,
        master_name="subscan2tmr",
        **kwargs
    )


def _test_limatimescan(session=None, tmpdir=None, writer=None, **kwargs):
    lima = "lima_simulator"
    expo1 = 0.1
    npoints1 = 20
    expo2 = 0.5
    npoints2 = 4
    detectors1 = [
        "diode2alias",
        "diode3",
        "diode4",
        "diode5",
        "thermo_sample",
        "simu1",
        "sim_ct_gauss_noise",
    ]
    detectors2 = [
        "diode6",
        "diode7",
        "diode8",
        "diode9alias",
        "sim_ct_gauss",
        "simu2",
        "lima_simulator2",
    ]

    olima = session.env_dict[lima]
    odetectors1 = [session.env_dict[d] for d in detectors1]
    odetectors2 = [session.env_dict[d] for d in detectors2]
    odetectors2.append(session.env_dict["lima_simulator2"].bpm)
    scan = session.env_dict["limatimescan"](
        olima, npoints1, expo1, odetectors1, npoints2, expo2, odetectors2
    )

    nxw_test_utils.run_scan(scan)
    nxw_test_utils.wait_scan_data_finished([scan], writer=writer)
    nxw_test_data.assert_scan_data(
        scan,
        subscan=1,
        scan_shape=(npoints1,),
        positioners=[["elapsed_time", "epoch"]],
        detectors=detectors1,
        master_name="subscan1tmr",
        **kwargs
    )
    nxw_test_data.assert_scan_data(
        scan,
        subscan=2,
        scan_shape=(npoints2,),
        positioners=[["elapsed_time", "epoch"]],
        detectors=detectors2,
        master_name="subscan2tmr",
        **kwargs
    )
