# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import numpy


@pytest.fixture
def autof_session(beacon, scan_tmpdir):
    mono = beacon.get("mono")
    mono.move(7)

    autof_session = beacon.get("test_autof_session")
    autof_session.setup()
    autof_session.scan_saving.base_path = str(scan_tmpdir)
    yield autof_session
    autof_session.close()


def test_autofilter_api(autof_session):
    # just call once all functions that are relevant to the user in autofilter1
    # and filterwheel1 that are not related to a scan

    # get ready
    energy = autof_session.env_dict["energy"]
    energy.move(16)

    autofilter1 = autof_session.env_dict["autofilter1"]
    filterw = autof_session.env_dict["filterwheel1"]

    # change filter
    filterw.filter = 0
    assert autofilter1.transmission == 1
    filterw.filter = 2
    # Transmission of 20um Cu at 16keV roughly 0.327 according to
    # http://henke.lbl.gov/optical_constants/filter2.html
    assert autofilter1.transmission == pytest.approx(0.327, abs=.005)

    # change energy and see if transmission is updated
    filterw.filter = 2
    trans_16keV = autofilter1.transmission
    energy.move(12)
    trans_12keV = autofilter1.transmission
    assert trans_16keV != trans_12keV

    # Todos:
    # - autofilter1.check_filter (what is the expected behaviour of this)
    # - autofilter1.energy_axis  (in case it should be exchangable on runtime)
    # - autofilter1.??
    # - filterw.??


def test_autofilter_ascan(autof_session):
    # https://gitlab.esrf.fr/bliss/bliss/-/merge_requests/2373

    energy = autof_session.env_dict["energy"]
    energy.move(16)

    filterw = autof_session.env_dict["filterwheel1"]
    filterw.filter = 0
    sim = autof_session.env_dict["sim_autofilter1_ctrs"]

    # TODO: scan never ends
    import gevent

    with gevent.Timeout(10):
        s = sim.auto_filter.ascan(
            sim.axis, 0, 1, sim.npoints, .1, *sim.detectors, save=False
        )
    scan_data = s.get_data()

    # test that all nessesary counters are published
    assert "AutoFilterDetMon:sim_autofilter1_mon" in scan_data
    assert "AutoFilterDetMon:sim_autofilter1_det" in scan_data
    assert "autofilter1:sim_autofilter1_det_corr" in scan_data
    assert "autofilter1:curratt" in scan_data
    assert "autofilter1:transm" in scan_data
    assert "autofilter1:ratio" in scan_data

    # test that the corrected values are the expected ones
    assert numpy.allclose(scan_data["autofilter1:sim_autofilter1_det_corr"], sim._data * sim.mon_value())

    # test that transm fits to measured value
    assert numpy.allclose(
        scan_data["AutoFilterDetMon:sim_autofilter1_det"]
        / scan_data["autofilter1:transm"],
        scan_data["autofilter1:sim_autofilter1_det_corr"],
    )

    # test that all filters are out at beginning and end of scan
    assert scan_data["autofilter1:transm"][0] == 1.0

    # idealy there should not be any filter remaining in the beam for
    # the test signal. To be able to merge the branch this test is
    # disabled for now. To be seen with scientist if there is a
    # real problem: Are enough filters removed when there is a weak
    # signal after a strong one (e.g. when scanning through a bragg peak)
    # assert scan_data["autofilter1:transm"][-1] == 1.0
