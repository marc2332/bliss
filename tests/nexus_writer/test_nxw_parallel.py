# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import nxw_test_utils
import nxw_test_data
from bliss.common import scans


def test_nxw_parallel(nexus_writer_config):
    _test_nxw_parallel(**nexus_writer_config)


@nxw_test_utils.writer_stdout_on_exception
def _test_nxw_parallel(session=None, tmpdir=None, writer=None, **kwargs):
    detectors = (
        "diode2alias",
        "diode3",
        "diode4",
        "diode5",
        "diode6",
        "diode7",
        "diode8",
        "diode9alias",
        "sim_ct_gauss",
        "sim_ct_gauss_noise",
        "thermo_sample",
    )
    lst = [
        scans.loopscan(npoints, 0.1, session.env_dict[name], run=False)
        for npoints, name in enumerate(detectors, 10)
    ]
    greenlets = [nxw_test_utils.run_scan(scan, runasync=True) for scan in lst]
    nxw_test_utils.assert_async_scans_success(lst, greenlets)
    nxw_test_utils.wait_scan_data_finished(lst, writer=writer)
    for npoints, (scan, detector) in enumerate(zip(lst, detectors), 10):
        nxw_test_data.assert_scan_data(
            scan,
            scan_shape=(npoints,),
            positioners=[["elapsed_time", "epoch"]],
            detectors=[detector],
            **kwargs
        )
