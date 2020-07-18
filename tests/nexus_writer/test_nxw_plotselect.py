# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common import scans
import nxw_test_utils
import nxw_test_data


def test_nxw_plotselect(nexus_writer_config):
    _test_nxw_plotselect(**nexus_writer_config)


@nxw_test_utils.writer_stdout_on_exception
def _test_nxw_plotselect(
    session=None, tmpdir=None, writer=None, save_images=True, **kwargs
):
    scan_saving = session.scan_saving
    env_dict = session.env_dict
    scan_display = session.scan_display
    scan_saving.technique = ""
    detectors = [env_dict[name] for name in ["diode3", "diode4", "diode5"]]
    names = [env_dict[name].fullname for name in ["diode3", "diode4"]]
    scan_display._plotselect(names)
    plots = {}
    plots["plotselect"] = {"ndim": 0, "type": "grid", "signals": ["diode3", "diode4"]}

    scan_shape = (10,)
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
