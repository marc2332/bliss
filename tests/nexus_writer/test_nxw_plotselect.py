# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common import scans
from bliss.common.plot import plotselect, plotinit
from tests.nexus_writer.helpers import nxw_test_utils
from tests.nexus_writer.helpers import nxw_test_data


def test_nxw_plotselect(nexus_writer_config):
    _test_nxw_plotselect(**nexus_writer_config)


@nxw_test_utils.writer_stdout_on_exception
def _test_nxw_plotselect(
    session=None, tmpdir=None, writer=None, save_images=True, **kwargs
):
    scan_saving = session.scan_saving
    env_dict = session.env_dict
    scan_saving.technique = ""
    detectors = [env_dict[name] for name in ["diode3", "diode4", "diode5"]]
    scan_shape = (10,)

    plotselect("diode4", "diode5")

    # Overwrite plotselect for one scan
    plotinit("diode3", "diode4")
    plots = {"plotselect": {"ndim": 0, "type": "grid", "signals": ["diode3", "diode4"]}}
    scan = scans.loopscan(
        scan_shape[0], .1, *detectors, run=False, save_images=save_images
    )
    nxw_test_utils.run_scan(scan)
    nxw_test_utils.wait_scan_data_finished([scan], writer=writer)
    nxw_test_data.assert_scan_nxdata(
        scan,
        plots,
        scan_shape=scan_shape,
        positioners=[["elapsed_time", "epoch"]],
        save_images=save_images,
        **kwargs
    )

    # Fall back to plotselect
    plots = {"plotselect": {"ndim": 0, "type": "grid", "signals": ["diode4", "diode5"]}}
    scan = scans.loopscan(
        scan_shape[0], .1, *detectors, run=False, save_images=save_images
    )
    nxw_test_utils.run_scan(scan)
    nxw_test_utils.wait_scan_data_finished([scan], writer=writer)
    nxw_test_data.assert_scan_nxdata(
        scan,
        plots,
        scan_shape=scan_shape,
        positioners=[["elapsed_time", "epoch"]],
        save_images=save_images,
        **kwargs
    )
