# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import time
import types
import pytest
import gevent
import logging
import numpy
from unittest import mock
from math import pi as _PI_

from bliss.common.utils import all_equal
from bliss.common.image_tools import draw_arc, draw_rect, array_to_file, file_to_array
from bliss.scanning.acquisition.timer import SoftwareTimerMaster
from bliss.common.tango import DevFailed
from bliss.common.counter import Counter
from bliss.controllers.lima.roi import Roi, ArcRoi, RoiProfile, ROI_PROFILE_MODES
from bliss.controllers.lima.roi import RoiProfileCounter, RoiStatCounter
from bliss.common.scans import loopscan, timescan, sct, ct, DEFAULT_CHAIN
from bliss.controllers.lima.limatools import load_simulator_frames, reset_cam

from ..conftest import lima_simulator_context
from bliss.config.channels import Cache


def test_lima_simulator(beacon, lima_simulator):
    simulator = beacon.get("lima_simulator")

    assert simulator.camera
    assert simulator.acquisition
    assert simulator.image

    trigger_mode = simulator.acquisition.trigger_mode
    try:
        simulator.acquisition.trigger_mode = "INTERNAL_TRIGGER_MULTI"
        assert simulator.acquisition.trigger_mode == "INTERNAL_TRIGGER_MULTI"
        assert (
            simulator.acquisition.trigger_mode
            == simulator.acquisition.trigger_mode_enum.INTERNAL_TRIGGER_MULTI
        )
    finally:
        simulator.acquisition.trigger_mode = trigger_mode

    assert isinstance(simulator.image, Counter)

    assert simulator.camera.test == "test"


def patched_simulator(simulator, monkeypatch):
    simulator.bpm.start_time = 0
    simulator.bpm.stop_time = 0
    orig_bpm_start = simulator.bpm.start
    orig_bpm_stop = simulator.bpm.stop

    def patched_bpm_start(self):
        self.start_time = time.time()
        return orig_bpm_start()

    def patched_bpm_stop(self):
        self.stop_time = time.time()
        return orig_bpm_stop()

    monkeypatch.setattr(
        simulator.bpm, "start", types.MethodType(patched_bpm_start, simulator.bpm)
    )
    monkeypatch.setattr(
        simulator.bpm, "stop", types.MethodType(patched_bpm_stop, simulator.bpm)
    )

    return simulator


@pytest.fixture
def lima_sim_with_bpm_start_stop_time(beacon, lima_simulator, monkeypatch):
    simulator = beacon.get("lima_simulator")
    yield patched_simulator(simulator, monkeypatch)


@pytest.fixture
def lima_sim_no_bpm_with_bpm_start_stop_time(beacon, lima_simulator2, monkeypatch):
    simulator = beacon.get("lima_simulator_no_bpm")
    yield patched_simulator(simulator, monkeypatch)


def test_lima_sim_bpm(default_session, lima_sim_with_bpm_start_stop_time):
    simulator = lima_sim_with_bpm_start_stop_time

    assert not simulator.disable_bpm
    assert "fwhm_x" in simulator.counters._fields
    assert "bpm" in simulator.counter_groups._fields

    s = loopscan(1, 0.1, simulator.counter_groups.bpm, save=False)

    # check that bpm was stopped, then started
    assert simulator.bpm.stop_time > 0
    assert simulator.bpm.start_time > 0
    assert simulator.bpm.stop_time < simulator.bpm.start_time

    data = s.get_data()
    assert f"{simulator.name}:bpm:x" in s.get_data()
    assert len(data) == 6 + 2  # 6 bpm counters + 2 timer


def test_lima_sim_no_bpm(default_session, lima_sim_no_bpm_with_bpm_start_stop_time):
    simulator = lima_sim_no_bpm_with_bpm_start_stop_time
    print(simulator.__info__())
    assert simulator.disable_bpm
    assert "fwhm_x" not in simulator.counters._fields
    assert "bpm" not in simulator.counter_groups._fields

    s = loopscan(1, 0.1, simulator.counters, save=False)

    # check bpm was stopped, but not started
    assert simulator.bpm.stop_time > 0
    assert simulator.bpm.start_time == 0

    data = s.get_data()
    assert len(data) == 3  # 2 timer (elapsed time, epoch) and image


def assert_lima_rois(simulator, rois):

    simulator.roi_counters.upload_rois()

    roi_names = simulator.roi_counters._proxy.getNames()
    raw_rois = simulator.roi_counters._proxy.getRois(roi_names)

    assert set(rois.keys()) == set(roi_names)

    lima_rois = {
        name: Roi(*raw_rois[i * 5 + 1 : i * 5 + 4 + 1], name=name)
        for i, name in enumerate(roi_names)
    }
    assert rois == lima_rois


def test_rect_rois(beacon, lima_simulator):
    cam = beacon.get("lima_simulator")

    rois = cam.roi_counters
    proxy = cam.roi_counters._proxy
    assert len(rois) == 0

    r1 = Roi(0, 0, 100, 200)
    r2 = Roi(10, 20, 200, 500)
    r3 = Roi(20, 60, 500, 500)
    r4 = Roi(60, 20, 50, 10)

    # clear and start the roicounter proxy
    proxy.clearAllRois()
    proxy.Start()

    rois["r1"] = r1
    assert_lima_rois(cam, dict(r1=r1))
    rois["r2"] = r2
    assert_lima_rois(cam, dict(r1=r1, r2=r2))
    rois["r3", "r4"] = r3, r4
    assert_lima_rois(cam, dict(r1=r1, r2=r2, r3=r3, r4=r4))

    assert len(rois) == 4
    assert rois["r1"] == r1
    assert rois.get("r1") == r1
    assert rois["r4", "r1"] == [r4, r1]
    assert set(rois.keys()) == {"r1", "r2", "r3", "r4"}

    with pytest.raises(KeyError):
        rois["r5"]
    assert rois.get("r5") is None

    assert "r1" in rois
    assert not "r5" in rois

    del rois["r1"]
    assert len(rois) == 3
    assert_lima_rois(cam, dict(r2=r2, r3=r3, r4=r4))

    del rois["r3", "r2"]
    assert len(rois) == 1
    assert_lima_rois(cam, dict(r4=r4))

    # test classic interface

    rois.set("r1", r1)
    assert len(rois) == 2
    assert_lima_rois(cam, dict(r1=r1, r4=r4))

    rois.remove("r4")
    assert len(rois) == 1
    assert_lima_rois(cam, dict(r1=r1))


def test_arc_rois(beacon, default_session, lima_simulator, images_directory):
    cam = beacon.get("lima_simulator")
    img_path = os.path.join(str(images_directory), "chart_2.edf")
    load_simulator_frames(cam, 1, img_path)
    reset_cam(cam, roi=[0, 0, 0, 0])

    radius = 60
    cam.roi_counters.clear()
    cam.roi_counters["a1"] = 316, 443, 50, 88, -120, -180
    cam.roi_counters["a2"] = 130, 320, 0, radius, 0, 360

    s = ct(0.1, cam)

    assert s.get_data("a1_sum")[0] == 0.0

    asum = s.get_data("a2_sum")[0]
    assert asum <= _PI_ * radius ** 2
    assert asum >= _PI_ * (radius - 1) ** 2


def test_roi_counters_api(beacon, default_session, lima_simulator):

    cam = beacon.get("lima_simulator")
    cnt_per_roi = 5

    # check there is no registered roi
    assert len(cam.roi_counters) == 0
    assert len(cam.roi_counters._roi_ids) == 0
    assert len(cam.roi_counters.counters) == 0

    # add a roi and check that 2 rois with same values and names are equal
    cam.roi_counters["r1"] = 20, 20, 20, 20
    assert "r1" in cam.roi_counters.keys()
    assert cam.roi_counters["r1"] == Roi(20, 20, 20, 20, name="r1")
    assert cam.roi_counters["r1"] != Roi(20, 20, 20, 20, name="other")
    src = list(cam.roi_counters.iter_single_roi_counters())
    assert len(src) == 1
    assert len(list(src[0])) == cnt_per_roi
    assert len(cam.roi_counters.counters) == cnt_per_roi

    # add multiple rois in a raw and check that 'bad' name is overwritten with the good name
    cam.roi_counters["r2", "r3"] = (
        Roi(20, 20, 20, 20),
        Roi(20, 20, 20, 20, name="bad"),
    )
    assert "r2" in cam.roi_counters.keys()
    assert "r3" in cam.roi_counters.keys()
    assert "bad" not in cam.roi_counters.keys()
    assert cam.roi_counters["r3"].name == "r3"
    assert len(cam.roi_counters.counters) == 3 * cnt_per_roi

    # add multiple rois in a raw as tuple
    cam.roi_counters["r4", "r5"] = (20, 20, 20, 20), (60, 20, 40, 40)
    assert "r4" in cam.roi_counters.keys()
    assert "r5" in cam.roi_counters.keys()
    assert cam.roi_counters["r4"] == Roi(20, 20, 20, 20, name="r4")
    assert cam.roi_counters["r5"] == Roi(60, 20, 40, 40, name="r5")
    assert len(cam.roi_counters.counters) == 5 * cnt_per_roi

    # check counters are added to the Lima.counter_groups
    assert len(cam.counter_groups["r5"]) == 5
    assert isinstance(cam.counter_groups["r5"]["r5_sum"], RoiStatCounter)

    # check it is not possible to use a name for a roi_counter if already used by a roi_profile
    cam.roi_profiles["s1"] = 20, 20, 20, 20
    try:
        cam.roi_counters["s1"] = 20, 20, 20, 20
        assert False
    except ValueError as e:
        assert e.args[0].startswith("Names conflict")

    # perform a scan to push rois to TangoDevice (roi_ids are retrieved at that time)
    assert len(cam.roi_counters._roi_ids) == 0
    ct(0.1, cam)
    assert len(cam.roi_counters._roi_ids) == 5

    # del one roi
    del cam.roi_counters["r5"]
    assert "r5" not in cam.roi_counters.keys()
    assert len(cam.roi_counters) == 4
    assert len(cam.roi_counters._roi_ids) == 4
    assert len(cam.roi_counters.counters) == 4 * cnt_per_roi

    # remove one roi
    cam.roi_counters.remove("r4")
    assert "r4" not in cam.roi_counters.keys()
    assert len(cam.roi_counters) == 3
    assert len(cam.roi_counters._roi_ids) == 3
    assert len(cam.roi_counters.counters) == 3 * cnt_per_roi

    # clear all
    cam.roi_counters.clear()
    assert len(cam.roi_counters) == 0
    assert len(cam.roi_counters._roi_ids) == 0
    assert len(cam.roi_counters.counters) == 0


def test_roi_profiles_api(beacon, default_session, lima_simulator):

    cam = beacon.get("lima_simulator")
    hmode = ROI_PROFILE_MODES["horizontal"].name
    vmode = ROI_PROFILE_MODES["vertical"].name

    # check there is no registered roi
    assert len(cam.roi_profiles) == 0
    assert len(cam.roi_profiles._roi_ids) == 0
    assert len(cam.roi_profiles.counters) == 0

    # add a roi and check that 2 rois with same values and names are equal
    cam.roi_profiles["s1"] = 20, 20, 20, 20
    assert "s1" in cam.roi_profiles.keys()
    assert cam.roi_profiles["s1"] == RoiProfile(20, 20, 20, 20, name="s1")
    assert cam.roi_profiles["s1"] != RoiProfile(20, 20, 20, 20, name="other")
    assert len(cam.roi_profiles.counters) == 1

    # add multiple rois in a raw and check that 'bad' name is overwritten with the good name
    cam.roi_profiles["s2", "s3"] = (
        RoiProfile(20, 20, 20, 20),
        RoiProfile(20, 20, 20, 20, name="bad"),
    )
    assert "s2" in cam.roi_profiles.keys()
    assert "s3" in cam.roi_profiles.keys()
    assert "bad" not in cam.roi_profiles.keys()
    assert cam.roi_profiles["s3"].name == "s3"
    assert len(cam.roi_profiles.counters) == 3

    # add multiple rois in a raw as tuple and check that mode is properly applied
    cam.roi_profiles["s4", "s5"] = (20, 20, 20, 20), (60, 20, 40, 40, vmode)
    assert "s4" in cam.roi_profiles.keys()
    assert "s5" in cam.roi_profiles.keys()
    assert cam.roi_profiles["s4"].mode == hmode
    assert cam.roi_profiles["s5"].mode == vmode
    assert len(cam.roi_profiles.counters) == 5

    # check counters are added to the Lima.counter_groups
    assert isinstance(cam.counter_groups["s5"], RoiProfileCounter)

    # check it is not possible to use a name for a roi_profile if already used by a roi_counter
    cam.roi_counters["r1"] = 20, 20, 20, 20
    try:
        cam.roi_profiles["r1"] = 20, 20, 20, 20
        assert False
    except ValueError as e:
        assert e.args[0].startswith("Names conflict")

    # perform a scan to push rois to TangoDevice (roi_ids are retrieved at that time)
    assert len(cam.roi_profiles._roi_ids) == 0
    ct(0.1, cam)
    assert len(cam.roi_profiles._roi_ids) == 5

    # check get_roi_mode/set_roi_mode
    cam.roi_profiles.set_roi_mode("horizontal", "s1")
    assert cam.roi_profiles.get_roi_mode("s1") == hmode
    cam.roi_profiles.set_roi_mode("vertical", "s1", "s2")
    assert cam.roi_profiles.get_roi_mode("s1", "s2") == {"s1": vmode, "s2": vmode}
    cam.roi_profiles.set_roi_mode("horizontal", "s1")
    assert cam.roi_profiles.get_roi_mode("s1") == hmode

    # test mode aliases
    cam.roi_profiles["s1"] = 20, 20, 20, 20, "v"
    assert cam.roi_profiles["s1"].mode == vmode
    cam.roi_profiles["s1"] = 20, 20, 20, 20, "h"
    assert cam.roi_profiles["s1"].mode == hmode
    cam.roi_profiles["s1"] = 20, 20, 20, 20, 1
    assert cam.roi_profiles["s1"].mode == vmode
    cam.roi_profiles["s1"] = 20, 20, 20, 20, 0
    assert cam.roi_profiles["s1"].mode == hmode

    cam.roi_profiles.set_roi_mode("v", "s1")
    assert cam.roi_profiles.get_roi_mode("s1") == vmode
    cam.roi_profiles.set_roi_mode("h", "s1")
    assert cam.roi_profiles.get_roi_mode("s1") == hmode
    cam.roi_profiles.set_roi_mode(1, "s1")
    assert cam.roi_profiles.get_roi_mode("s1") == vmode
    cam.roi_profiles.set_roi_mode(0, "s1")
    assert cam.roi_profiles.get_roi_mode("s1") == hmode

    # del one roi
    del cam.roi_profiles["s5"]
    assert "s5" not in cam.roi_profiles.keys()
    assert len(cam.roi_profiles) == 4
    assert len(cam.roi_profiles._roi_ids) == 4
    assert len(cam.roi_profiles.counters) == 4

    # remove one roi
    cam.roi_profiles.remove("s4")
    assert "s4" not in cam.roi_profiles.keys()
    assert len(cam.roi_profiles) == 3
    assert len(cam.roi_profiles._roi_ids) == 3
    assert len(cam.roi_profiles.counters) == 3

    # clear all
    cam.roi_profiles.clear()
    assert len(cam.roi_profiles) == 0
    assert len(cam.roi_profiles._roi_ids) == 0
    assert len(cam.roi_profiles.counters) == 0


def test_roi_profiles_measurements(
    beacon, default_session, lima_simulator, images_directory
):

    # chart_3.edf (200x100) => 2 patterns
    #
    # 1 stairs shape in box (20,20,20+20,20+20)  => Horizontal lineProfile is [0,1,2,3,4,5,...]
    #
    #  HHHHHH
    #   HHHHH
    #    HHHH
    #     HHH
    #      HH
    #       H

    # 1 code-bar shape in box (60,20,60+40,20+40) => Horizontal lineProfile is [40,0,40,0,40,0,...]
    #  H  H  H  H  H
    #  H  H  H  H  H
    #  H  H  H  H  H
    #  H  H  H  H  H
    #  H  H  H  H  H
    #  H  H  H  H  H

    cam = beacon.get("lima_simulator")
    img_path = os.path.join(str(images_directory), "chart_3.edf")
    load_simulator_frames(cam, 1, img_path)
    reset_cam(cam, roi=[0, 0, 0, 0])

    debug = 0
    if debug:
        import matplotlib.pyplot as plt

        plt.imshow(file_to_array(img_path))
        plt.show()

        from bliss.shell.standard import flint

        pf = flint()

    cam.roi_profiles.clear()
    cam.roi_profiles["sp1"] = [20, 20, 18, 20]
    cam.roi_profiles["sp2"] = [60, 20, 38, 40]

    w1 = cam.roi_profiles["sp1"].width
    h1 = cam.roi_profiles["sp1"].height
    w2 = cam.roi_profiles["sp2"].width
    h2 = cam.roi_profiles["sp2"].height

    # TEST WITH HORIZONTAL LINE PROFILE
    # (mode=0, pixels are summed along the vertical axis and the spectrum is along horizontal axis)
    cam.roi_profiles.set_roi_mode("horizontal", "sp1", "sp2")

    s = ct(0.1, cam)
    if debug:
        pf.wait_end_of_scans()
        time.sleep(1)

    d1 = s.get_data("sp1")[0]
    d2 = s.get_data("sp2")[0]

    # check it is really an horizontal line profile
    assert len(d1) == w1
    assert len(d2) == w2

    # check measured spectrums are as expected
    assert list(d1) == list(range(1, w1 + 1))
    assert all_equal(list(d2[::2])) and d2[::2][0] == h2
    assert all_equal(list(d2[1::2])) and d2[1::2][0] == 0

    # DO THE SAME BUT WITH VERTICAL LINE PROFILE
    cam.roi_profiles["sp1"] = [20, 20, 20, 20]
    cam.roi_profiles.set_roi_mode("vertical", "sp1")
    cam.roi_profiles.set_roi_mode("vertical", "sp2")

    s = ct(0.1, cam)

    if debug:
        pf.wait_end_of_scans()
        time.sleep(1)

    d1 = s.get_data("sp1")[0]
    d2 = s.get_data("sp2")[0]

    # check it is really an horizontal line profile
    assert len(d1) == h1
    assert len(d2) == h2

    # check measured spectrums are as expected
    res1 = list(d1)
    res1.reverse()
    assert res1 == list(range(1, h1 + 1))
    assert all_equal(list(d2)) and d2[0] == w2 / 2

    # MIX VERTICAL and HORIZONTAL LINE PROFILE
    cam.roi_profiles.set_roi_mode("vertical", "sp1")
    cam.roi_profiles.set_roi_mode("horizontal", "sp2")

    s = ct(0.1, cam)
    if debug:
        pf.wait_end_of_scans()
        time.sleep(1)
    d1 = s.get_data("sp1")[0]
    d2 = s.get_data("sp2")[0]

    # check it is really an horizontal line profile
    assert len(d1) == h1
    assert len(d2) == w2

    # check measured spectrums are as expected
    assert res1 == list(range(1, h1 + 1))
    assert all_equal(list(d2[::2])) and d2[::2][0] == h2
    assert all_equal(list(d2[1::2])) and d2[1::2][0] == 0

    # MULTIPLE IMAGES

    frames = 3
    s = loopscan(frames, 0.1, cam)
    d1 = s.get_data("sp1")

    assert len(d1) == frames
    assert all_equal([len(x) for x in d1])


def test_all_rois_validity(beacon, default_session, lima_simulator):

    cam = beacon.get("lima_simulator")
    reset_cam(cam, roi=[0, 0, 0, 0])

    # arc rois
    cx, cy = 250, 350
    r1, r2 = 80, 100
    a1, a2 = 10, 45
    cam.roi_counters["a1"] = cx, cy, r1, r2, a1, a2
    cam.roi_counters["a2"] = cx, cy, r1, r2, a1 + 90, a2 + 90
    cam.roi_counters["a3"] = cx, cy, r1, r2, a1 + 180, a2 + 180
    cam.roi_counters["a4"] = cx, cy, r1, r2, a1 + 270, a2 + 270

    # rect roi
    w0, h0 = 60, 30
    cam.roi_counters["r1"] = cx, cy, w0, h0

    # roi profile
    x1, y1, w1, h1 = 500, 400, 60, 30
    cam.roi_profiles["p1"] = x1, y1, w1, h1

    # roi collection
    w2, h2 = 6, 4
    nx, ny = 3, 3
    for j in range(ny):
        for i in range(nx):
            x = i * 2 * w2 + 500
            y = j * 2 * h2 + 100
            cam.roi_collection[f"c{nx*j+i}"] = [x, y, w2, h2]

    assert len(list(cam.roi_counters.counters)) == 5 * 5  # because 5 counters per roi
    assert len(list(cam.roi_profiles.counters)) == 1
    assert len(list(cam.roi_collection.counters)) == 1  # one for the collection of rois

    # applying this roi should discard 2 rois
    cam.image.roi = 0, 0, 240, 500
    assert len(list(cam.roi_counters.counters)) == 2 * 5
    assert len(list(cam.roi_profiles.counters)) == 0
    assert (
        len(list(cam.roi_collection.counters)) == 0
    )  # if no rois in collection then no counter

    # back to full frame should re-activate the 2 rois discarde previously
    cam.image.roi = 0, 0, 0, 0
    assert len(list(cam.roi_counters.counters)) == 5 * 5
    assert len(list(cam.roi_profiles.counters)) == 1
    assert len(list(cam.roi_collection.counters)) == 1

    assert len(cam.roi_collection.get_rois()) == nx * ny

    cam.roi_collection.clear()
    assert len(cam.roi_collection.get_rois()) == 0
    assert len(list(cam.roi_collection.counters)) == 0

    cam.roi_profiles.clear()
    assert len(cam.roi_profiles.get_rois()) == 0
    assert len(list(cam.roi_profiles.counters)) == 0

    cam.roi_counters.clear()
    assert len(cam.roi_counters.get_rois()) == 0
    assert len(list(cam.roi_counters.counters)) == 0


def test_lima_geometry_and_rois_measurements(
    beacon, default_session, lima_simulator, images_directory
):

    cam = beacon.get("lima_simulator")
    cam.roi_counters.clear()
    cam.roi_profiles.clear()
    cam.roi_collection.clear()
    reset_cam(cam, roi=[0, 0, 0, 0])

    img = cam.image
    img_path = os.path.join(str(images_directory), "testimg.edf")

    arry = numpy.ones((1400, 1200))
    cx, cy = 620, 720

    # --- rect regions
    arry = draw_rect(arry, cx, cy, 40, 10, fill_value=0)
    arry = draw_rect(arry, cx, cy + 10, 40, 10, fill_value=2)

    # --- arc regions (slightly larger than arc rois for binning matters)
    arc_params = [
        (cx, cy, 120, 140, 10, 45),  # a0
        (cx, cy, 160, 180, 10, 90),  # a1
        (cx, cy, 200, 220, 10, 180),  # a2
        (cx, cy, 240, 260, 10, 350),  # a3
        (cx, cy, 280, 300, -20, 20),  # a4
        (cx, cy, 320, 340, 100, 200),  # a5
        (cx, cy, 360, 380, 190, 280),  # a6
        (cx, cy, 400, 420, 170, 380),  # a7
    ]
    arc_rois = {}
    for idx, (cx, cy, r1, r2, a1, a2) in enumerate(arc_params):
        arry = draw_arc(arry, cx, cy, r1 - 4, r2 + 4, a1 - 4, a2 + 4)
        arc_rois[f"a{idx}"] = cx, cy, r1, r2, a1, a2

    # --- collection of rect regions
    w2, h2 = 6, 4
    nx, ny = 10, 10
    collec = {}
    for j in range(ny):
        for i in range(nx):
            x = i * 2 * w2 + 500
            y = j * 2 * h2 + 100
            arry = draw_rect(arry, x, y, w2, h2, fill_value=0)
            collec[f"c{nx*j+i}"] = [x, y, w2, h2]

    array_to_file(arry.astype("uint32"), img_path)
    load_simulator_frames(cam, 1, img_path)

    debug = 0
    if debug:
        import matplotlib.pyplot as plt

        plt.imshow(file_to_array(img_path))
        plt.show()

        from bliss.shell.standard import flint

        pf = flint()

    # ==== measure in raw state ======

    # --- rect rois
    cam.roi_counters["r1"] = cx, cy, 40, 10
    cam.roi_counters["r2"] = cx, cy + 10, 40, 10

    # --- arc rois
    for name, roi in arc_rois.items():
        cam.roi_counters[name] = roi

    # --- roi profiles
    cam.roi_profiles["p1"] = cx, cy, 40, 20, "horizontal"

    # --- roi collectio
    for name, roi in collec.items():
        cam.roi_collection[name] = roi

    s = ct(0.001, cam)

    if debug:
        pf.wait_end_of_scans()
        time.sleep(1)

    assert s.get_data("r1_sum")[0] == 0
    assert s.get_data("r2_sum")[0] == 2 * 40 * 10

    assert numpy.all(s.get_data("p1")[0] == 20)

    for name in arc_rois.keys():
        assert s.get_data(name + "_sum")[0] == 0

    assert numpy.all(s.get_data("roi_collection_counter")[0] == 0)

    print("=== raw rois ==========")
    print(cam.roi_counters.__info__())

    # ==== test recalc on geometry changes ======

    flipvals = [[False, False], [True, False], [True, True], [False, True]]
    binvals = [
        [1, 1],
        [2, 2],
    ]  # lima fails with bin 3,3 for rect roi at rot 90  but not for bin 4,4 !
    rotvals = [0, 90, 180, 270]

    for binning in binvals:
        for flip in flipvals:
            for rotation in rotvals:

                img.set_geometry(binning, flip, rotation)
                s = ct(0.01, cam)

                print("=== ", binning, flip, rotation)
                print(cam.roi_counters.__info__())
                print(cam.roi_profiles.__info__())
                print(cam.roi_collection.__info__())

                assert s.get_data("r1_sum")[0] == 0
                assert s.get_data("r2_sum")[0] == 2 * 40 * 10

                assert numpy.all(s.get_data("p1")[0] == 20 * binning[0])

                for name in arc_rois.keys():
                    assert s.get_data(name + "_sum")[0] == 0

                assert numpy.all(s.get_data("roi_collection_counter")[0] == 0)

                if debug:
                    pf.wait_end_of_scans()
                    time.sleep(1)

    cam.roi_counters.clear()
    cam.roi_profiles.clear()
    cam.roi_collection.clear()


def test_lima_geometry_and_arc_roi_bounding_box(
    beacon, default_session, lima_simulator, images_directory
):

    cam = beacon.get("lima_simulator")
    cam.roi_counters.clear()
    cam.roi_profiles.clear()
    cam.roi_collection.clear()
    reset_cam(cam, roi=[0, 0, 0, 0])

    img = cam.image
    img_path = os.path.join(str(images_directory), "testimg.edf")

    arry = numpy.ones((1400, 1200))
    cx, cy = 600, 300

    # --- arc regions
    arc_params = [
        # head
        (cx, cy, 180, 200, 170, 370),  # a0
        (cx, cy, 140, 160, -10, 190),  # a1
        # tits
        (cx - 100, cy + 300, 60, 80, 4, 355),  # a2
        (cx + 100, cy + 300, 60, 80, -176, 175),  # a3
        # eyes
        (cx - 70, cy - 20, 40, 50, 180, 359),  # a4
        (cx + 70, cy - 20, 40, 50, 180, 359),  # a5
        # mouth
        (cx, cy + 30, 40, 50, 20, 160),  # a6
        # shoulders
        (cx - 200, cy + 200, 60, 80, 135, 270),  # a7
        (cx + 200, cy + 200, 60, 80, 270, 405),  # a8
        # belly
        (cx + 260, cy + 545, 190, 210, 135, 225),  # a9
        (cx - 260, cy + 545, 190, 210, 315, 405),  # a10
        # bottom
        (cx - 130, cy + 780, 80, 100, 110, 270),  # a11
        (cx + 130, cy + 780, 80, 100, 270, 430),  # a12
    ]
    arc_rois = {}
    delta = 4
    for idx, (cx, cy, r1, r2, a1, a2) in enumerate(arc_params):
        arry = draw_arc(arry, cx, cy, r1 - delta, r2 + delta, a1 - delta, a2 + delta)
        arc_rois[f"a{idx}"] = cx, cy, r1, r2, a1, a2

    array_to_file(arry.astype("uint32"), img_path)
    load_simulator_frames(cam, 1, img_path)

    debug = 0
    if debug:
        import matplotlib.pyplot as plt

        plt.imshow(file_to_array(img_path))
        plt.show()

        from bliss.shell.standard import flint

        pf = flint()

    # ==== measure in raw state ======

    # --- arc rois
    for name, roi in arc_rois.items():
        cam.roi_counters[name] = roi
        [[x1, y1], [x2, y2]] = cam.roi_counters[name].bounding_box()
        cam.roi_counters["bb" + name] = x1, y1, x2 - x1, y2 - y1

    s = ct(0.001, cam)

    if debug:
        pf.wait_end_of_scans()
        time.sleep(1)

    for name in arc_rois.keys():
        assert s.get_data(name + "_sum")[0] == 0

    print("=== raw rois ==========")
    print(cam.roi_counters.__info__())

    img.roi = 375, 110, 463, 1090

    s = ct(0.001, cam)

    if debug:
        pf.wait_end_of_scans()
        time.sleep(1)

    assert "a0" not in cam.roi_counters.keys()
    assert "a7" not in cam.roi_counters.keys()
    assert "a8" not in cam.roi_counters.keys()
    assert "a11" not in cam.roi_counters.keys()

    img.roi = 0, 0, 0, 0

    assert "a0" in cam.roi_counters.keys()
    assert "a7" in cam.roi_counters.keys()
    assert "a8" in cam.roi_counters.keys()
    assert "a11" in cam.roi_counters.keys()

    # ==== test recalc on geometry changes ======

    flipvals = [[False, False], [True, False], [True, True], [False, True]]
    binvals = [
        [1, 1],
        [2, 2],
    ]  # lima fails with bin 3,3 for rect roi at rot 90  but not for bin 4,4 !
    rotvals = [0, 90, 180, 270]

    for binning in binvals:
        for flip in flipvals:
            for rotation in rotvals:

                img.set_geometry(binning, flip, rotation)
                s = ct(0.01, cam)

                print("=== ", binning, flip, rotation)
                print(cam.roi_counters.__info__())

                for name in arc_rois.keys():
                    assert s.get_data(name + "_sum")[0] == 0

                if debug:
                    pf.wait_end_of_scans()
                    time.sleep(1)


def test_directories_mapping(beacon, lima_simulator):
    simulator = beacon.get("lima_simulator")

    assert simulator.directories_mapping_names == ["identity", "fancy"]
    assert simulator.current_directories_mapping == "identity"
    assert simulator.get_mapped_path("/tmp/scans/bla") == "/tmp/scans/bla"

    try:
        simulator.select_directories_mapping("fancy")
        assert simulator.current_directories_mapping == "fancy"
        assert simulator.get_mapped_path("/tmp/scans/bla") == "/tmp/fancy/bla"
        assert simulator.get_mapped_path("/data/inhouse") == "/data/inhouse"
    finally:
        simulator.select_directories_mapping("identity")

    with pytest.raises(ValueError):
        simulator.select_directories_mapping("invalid")


def test_lima_mapping_and_saving(session, lima_simulator):
    simulator = session.config.get("lima_simulator")
    scan_saving = session.scan_saving
    scan_saving_dump = scan_saving.to_dict()

    def replace_root_dir():
        # Replace /tmp/scans with scan_saving.base_path
        for mapping in simulator.directories_mapping:
            for k in mapping:
                mapping[k] = mapping[k].replace("/tmp/scans", scan_saving.base_path)

    scan_saving.images_path_template = ""
    scan_saving.images_prefix = "toto"

    saving_directory = None
    try:
        simulator.select_directories_mapping("fancy")
        replace_root_dir()
        mapped_directory = simulator.get_mapped_path(scan_saving.get_path())
        ct_scan = sct(0.1, simulator, save=True, run=False)

        try:
            ct_scan.run()
        except Exception as e:
            # this will fail because directory is not likely to exist
            saving_directory = e.args[0].desc.split("Directory :")[-1].split()[0]
    finally:
        scan_saving.from_dict(scan_saving_dump)
        simulator.select_directories_mapping("identity")
        replace_root_dir()

    # cannot use simulator.proxy.saving_directory because it is reset to ''
    assert mapped_directory.startswith(saving_directory)


def test_images_dir_prefix_saving(session, lima_simulator):
    simulator = session.config.get("lima_simulator")
    scan_saving = session.scan_saving
    scan_saving_dump = scan_saving.to_dict()

    scan_saving.template = "test"
    scan_saving.images_path_template = "{scan_name}_{scan_number}/toto"
    scan_saving.images_prefix = "{img_acq_device}"
    scan_saving.scan_number_format = "%1d"

    try:
        scan_config = scan_saving.get()
        assert scan_config["root_path"] == os.path.join(
            scan_saving.base_path, scan_saving.template
        )
        assert scan_config["images_path"] == os.path.join(
            scan_config["root_path"],
            scan_saving.images_path_template,
            scan_saving.images_prefix,
        )

        loopscan(1, 0.1, simulator)

        assert os.path.isdir(scan_config["root_path"])
        assert os.path.isdir(os.path.join(scan_config["root_path"], "loopscan_1/toto"))
        assert os.path.exists(
            os.path.join(
                scan_config["root_path"], "loopscan_1/toto/lima_simulator0000.edf"
            )
        )
    finally:
        scan_saving.from_dict(scan_saving_dump)


def test_images_dir_prefix_saving_absolute(session, lima_simulator):
    simulator = session.config.get("lima_simulator")
    scan_saving = session.scan_saving
    scan_saving_dump = scan_saving.to_dict()

    scan_saving.template = "test"
    scan_saving.images_path_relative = False
    scan_saving.images_path_template = "{base_path}/test/{scan_name}_{scan_number}/toto"
    scan_saving.images_prefix = "{img_acq_device}"
    scan_saving.scan_number_format = "%1d"

    try:
        scan_config = scan_saving.get()
        assert scan_config["root_path"] == os.path.join(
            scan_saving.base_path, scan_saving.template
        )
        assert scan_config["images_path"] == os.path.join(
            scan_saving.base_path,
            scan_saving.template,
            "{scan_name}_{scan_number}/toto/{img_acq_device}",
        )

        timescan(0.1, simulator, npoints=1)

        assert os.path.isdir(scan_config["root_path"])
        assert os.path.isdir(os.path.join(scan_config["root_path"], "timescan_1/toto"))
        assert os.path.exists(
            os.path.join(
                scan_config["root_path"], "timescan_1/toto/lima_simulator0000.edf"
            )
        )
    finally:
        scan_saving.from_dict(scan_saving_dump)


def test_images_dir_saving_null_writer(session, lima_simulator):
    # issue 1010
    simulator = session.config.get("lima_simulator")
    scan_saving = session.scan_saving
    scan_saving_dump = scan_saving.to_dict()

    scan_saving.template = "test"
    scan_saving.images_path_relative = False
    scan_saving.images_path_template = "{base_path}/test/{scan_name}_{scan_number}/tata"
    scan_saving.images_prefix = "{img_acq_device}"
    scan_saving.scan_number_format = "%1d"
    scan_saving.writer = "null"

    try:
        scan_config = scan_saving.get()

        timescan(0.1, simulator, npoints=1)

        assert os.path.exists(
            os.path.join(
                scan_config["root_path"], "timescan_1/tata/lima_simulator0000.edf"
            )
        )
    finally:
        scan_saving.from_dict(scan_saving_dump)


def test_dir_no_saving(session, lima_simulator):
    # issue 1070
    simulator = session.config.get("lima_simulator")
    scan_saving = session.scan_saving
    scan_saving_dump = scan_saving.to_dict()

    try:
        scan_config = scan_saving.get()

        timescan(0.1, simulator, npoints=1, save=False)

        assert not os.path.exists(os.path.join(scan_config["root_path"]))
    finally:
        scan_saving.from_dict(scan_saving_dump)


def test_lima_scan_internal_trigger_with_roi(session, lima_simulator):
    # test for issue #485
    simulator = session.config.get("lima_simulator")

    simulator.roi_counters.set("test", (0, 0, 100, 100))

    # force trigger mode to 'internal trigger' on Lima acq. master,
    # by changing default chain behaviour
    DEFAULT_CHAIN.set_settings(
        [
            {
                "device": simulator,
                "acquisition_settings": {"acq_trigger_mode": "INTERNAL_TRIGGER"},
            }
        ]
    )

    with gevent.Timeout(3, RuntimeError("Timeout waiting for end of scan")):
        scan = loopscan(
            3, 0.1, simulator, simulator.counter_groups.roi_counters, save=False
        )

    assert simulator.acquisition.trigger_mode == "INTERNAL_TRIGGER"

    assert len(scan.get_data()["test_min"]) == 3
    assert len(scan.get_data()["test_max"]) == 3
    assert len(scan.get_data()["test_avg"]) == 3


def test_lima_scan_internal_trigger_with_diode(session, lima_simulator, monkeypatch):
    diode = session.config.get("diode")
    simulator = session.config.get("lima_simulator")

    monkeypatch.setattr(type(simulator.camera), "synchro_mode", "IMAGE")

    assert simulator.camera.synchro_mode == "IMAGE"

    s = loopscan(2, 0.1, simulator, diode, save=False, run=False)

    timer = s.acq_chain.nodes_list[0]
    assert isinstance(timer, SoftwareTimerMaster)

    saved_wait_ready = timer.wait_ready

    def delayed_wait_ready(self, *args, **kwargs):
        gevent.sleep(.2)
        return saved_wait_ready(*args, **kwargs)

    timer.wait_ready = types.MethodType(delayed_wait_ready, timer)

    with gevent.Timeout(3, RuntimeError("Timeout waiting for end of scan")):
        s.run()

    assert simulator.acquisition.trigger_mode == "INTERNAL_TRIGGER_MULTI"


def test_lima_scan_get_data(session, lima_simulator):
    simulator = session.config.get("lima_simulator")
    s = loopscan(3, 0.1, simulator)

    data = s.get_data()

    assert simulator.name + ":image" in data
    view = data[simulator.name + ":image"]

    assert len(view) == 3

    raw_image_data = view.get_image(2)

    assert raw_image_data.shape == (simulator.image.height, simulator.image.width)

    # check that 'image' and 'lima_simulator' give same matches as 'lima_simulator:image'
    # (because image s the only counter of lima_simulator)
    data1 = s.get_data("image").get_image(2)
    data2 = s.get_data("lima_simulator").get_image(2)

    assert data1.shape == (simulator.image.height, simulator.image.width)
    assert data2.shape == data1.shape
    assert numpy.all(data1 == data2)

    # add a roi_counters and check that 'lima_simulator' key has multiple matches now (i.e get_data fails)
    r1 = Roi(0, 0, 100, 200)
    simulator.roi_counters["r1"] = r1

    s = loopscan(3, 0.1, simulator)

    try:
        has_failed = False
        s.get_data("lima_simulator")
    except KeyError as e:
        has_failed = True

    assert has_failed


def test_lima_scan_get_last_data(session, lima_simulator):
    simulator = session.config.get("lima_simulator")
    s = loopscan(3, 0.1, simulator)

    data = s.get_data()

    assert simulator.name + ":image" in data
    view = data[simulator.name + ":image"]

    assert len(view) == 3

    raw_image_data, frame_id = view.get_last_image()

    assert frame_id not in [None, -1]
    assert raw_image_data.shape == (simulator.image.height, simulator.image.width)


def test_lima_scan_get_last_live_image(session, lima_simulator):
    simulator = session.config.get("lima_simulator")
    s = loopscan(3, 0.1, simulator)

    data = s.get_data()

    assert simulator.name + ":image" in data
    view = data[simulator.name + ":image"]

    assert len(view) == 3

    view.from_stream = True
    raw_image_data, frame_id = view.get_last_live_image()

    assert frame_id not in [None, -1]
    assert raw_image_data.shape == (simulator.image.height, simulator.image.width)


def test_lima_scan_get_last_live_image_using_internal_trigger_mode(
    session, lima_simulator
):
    simulator = session.config.get("lima_simulator")

    DEFAULT_CHAIN.set_settings(
        [
            {
                "device": simulator,
                "acquisition_settings": {"acq_trigger_mode": "INTERNAL_TRIGGER"},
            }
        ]
    )

    with gevent.Timeout(3, RuntimeError("Timeout waiting for end of scan")):
        scan = loopscan(3, 0.1, simulator, save=False)

    assert simulator.acquisition.trigger_mode == "INTERNAL_TRIGGER"

    data = scan.get_data()

    assert simulator.name + ":image" in data
    view = data[simulator.name + ":image"]

    view.from_stream = True
    raw_image_data, frame_id = view.get_last_live_image()

    assert frame_id is None
    assert raw_image_data.shape == (simulator.image.height, simulator.image.width)


def test_scan_saving_flags_with_lima(default_session, lima_simulator):
    simulator = default_session.config.get("lima_simulator")
    loopscan(3, 0.1, simulator)
    assert simulator.proxy.last_image_saved == 2
    loopscan(3, 0.1, simulator, save=False)
    assert simulator.proxy.last_image_saved == -1
    loopscan(3, 0.1, simulator, save_images=False, save=True)
    assert simulator.proxy.last_image_saved == -1
    loopscan(3, 0.1, simulator, save_images=True, save=False)
    assert simulator.proxy.last_image_saved == 2


def test_lima_beacon_objs(default_session, lima_simulator):
    simulator = default_session.config.get("lima_simulator")
    assert simulator.saving._max_writing_tasks == 4
    assert simulator.saving._managed_mode == "SOFTWARE"

    assert simulator.processing.runlevel_roicounter == 9
    assert simulator.processing.runlevel_background == 2

    assert simulator.image.rotation == 90
    assert simulator.image.flip == [False, False]

    simulator.processing.runlevel_roicounter = 8
    assert simulator.processing.runlevel_roicounter == 8
    simulator.processing.apply_config()
    assert simulator.processing.runlevel_roicounter == 9


def test_lima_ctrl_params_uploading(default_session, lima_simulator, caplog):
    simulator = default_session.config.get("lima_simulator")

    with caplog.at_level(logging.DEBUG, logger="global.controllers.lima_simulator"):
        scan = loopscan(1, 0.1, simulator, save=False)
    # check that lima parameters are resend on the first scan
    assert "All parameters will be refeshed on lima_simulator" in caplog.messages

    # check that config has been applied on lima server
    assert simulator.proxy.saving_max_writing_task == 4

    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger="global.controllers.lima_simulator"):
        scan = loopscan(1, 0.1, simulator, save=False)

    # # check there is no change in ctrl params when repeating the scan
    # Could fail in case of warning in the logs ?
    # assert len(caplog.messages) == 0

    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger="global.controllers.lima_simulator"):
        scan = loopscan(1, 0.1, simulator, run=False)
        scan.update_ctrl_params(simulator, {"saving_max_writing_task": 2})
        scan.run()

    # check that a change in ctrl params leads to update in camera
    assert (
        "apply parameter saving_max_writing_task on lima_simulator to 2"
        in caplog.messages
    ), f"test_lima_ctrl_params_uploading caplog.messages={caplog.messages}"

    assert simulator.proxy.saving_max_writing_task == 2

    # lets see if we can use mask, background and flatfield
    img = scan.get_data()["image"].all_image_references()[0][0]
    simulator.processing.mask = img
    simulator.processing.use_mask = True

    simulator.processing.flatfield = img
    simulator.processing.use_flatfield = True

    simulator.processing.background = img
    assert simulator.processing.background_source == "file"
    simulator.processing.use_background = True

    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger="global.controllers.lima_simulator"):
        scan = loopscan(1, 0.1, simulator, save=False)

    assert " uploading new mask on lima_simulator" in caplog.messages
    assert " uploading flatfield on lima_simulator" in caplog.messages
    assert " uploading background on lima_simulator" in caplog.messages
    assert " starting background sub proxy of lima_simulator" in caplog.messages

    simulator.processing.use_mask = False
    simulator.processing.use_flatfield = False
    simulator.processing.use_background = False

    # check if aqcuistion still works
    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger="global.controllers.lima_simulator"):
        scan = loopscan(1, 0.1, simulator, save=False)

    simulator.processing.background = "not_existing_file"
    simulator.processing.use_background = True
    simulator.bg_sub.take_background(.1)
    assert simulator.processing.background_source == "image"

    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger="global.controllers.lima_simulator"):
        scan = loopscan(1, 0.1, simulator, save=False)

    assert " starting background sub proxy of lima_simulator" in caplog.messages


def test_reapplying_ctrl_params(default_session, caplog):
    simulator = default_session.config.get("lima_simulator")

    with lima_simulator_context("simulator", "id00/limaccds/simulator1"):
        gevent.sleep(1.1)  # wait until the DeviceProxy becomes usable again
        with caplog.at_level(logging.DEBUG, logger="global.controllers.lima_simulator"):
            scan = loopscan(1, 0.1, simulator, save=False)
        assert "All parameters will be refeshed on lima_simulator" in caplog.messages

    with pytest.raises(DevFailed):
        caplog.clear()
        with caplog.at_level(logging.DEBUG, logger="global.controllers.lima_simulator"):
            scan = loopscan(1, 0.1, simulator, save=False)

    with lima_simulator_context("simulator", "id00/limaccds/simulator1"):
        gevent.sleep(1.1)  # wait until the DeviceProxy becomes usable again
        caplog.clear()
        with caplog.at_level(logging.DEBUG, logger="global.controllers.lima_simulator"):
            scan = loopscan(1, 0.1, simulator, save=False)
        assert "All parameters will be refeshed on lima_simulator" in caplog.messages

    with lima_simulator_context("simulator", "id00/limaccds/simulator1"):
        gevent.sleep(1.1)  # wait until the DeviceProxy becomes usable again
        caplog.clear()
        with caplog.at_level(logging.DEBUG, logger="global.controllers.lima_simulator"):
            scan = loopscan(1, 0.1, simulator, save=False)
        assert "All parameters will be refeshed on lima_simulator" in caplog.messages

    # TODO: in this test we should also check if user_instrument_name and user_detector_name
    #      are set correctly once lima version > 1.9.1 is available on CI


def test_lima_saving_mode(default_session, lima_simulator):
    simulator = default_session.config.get("lima_simulator")

    simulator.saving.file_format = "HDF5"
    simulator.saving.frames_per_file = 5
    simulator.saving.max_file_size_in_MB = 15

    simulator.saving.mode = "ONE_FILE_PER_FRAME"
    scan = loopscan(10, 0.1, simulator)

    assert 10 == len(
        set([x[0] for x in scan.get_data()["image"].all_image_references()])
    )

    simulator.saving.mode = "ONE_FILE_PER_N_FRAMES"
    scan = loopscan(10, 0.1, simulator)

    assert 2 == len(
        set([x[0] for x in scan.get_data()["image"].all_image_references()])
    )

    simulator.saving.mode = "SPECIFY_MAX_FILE_SIZE"
    scan = loopscan(10, 0.1, simulator)

    assert 3 == len(
        set([x[0] for x in scan.get_data()["image"].all_image_references()])
    )

    simulator.saving.mode = "ONE_FILE_PER_SCAN"
    scan = loopscan(10, 0.1, simulator)

    assert 1 == len(
        set([x[0] for x in scan.get_data()["image"].all_image_references()])
    )


def test_reapplication_image_params(beacon, default_session, lima_simulator, caplog):
    simulator = beacon.get("lima_simulator")
    # do one initial scan to set all caches
    scan = loopscan(1, 0.1, simulator, save=False)

    # reset timestamp
    Cache(simulator, "server_start_timestamp").value = ""

    with caplog.at_level(logging.DEBUG, logger="global.controllers.lima_simulator"):
        scan = loopscan(1, 0.1, simulator, save=False)

    assert "All parameters will be refeshed on lima_simulator" in caplog.messages

    # emulate use of another bliss session
    Cache(simulator, "last_session").value = "toto_session"

    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger="global.controllers.lima_simulator"):
        scan = loopscan(1, 0.1, simulator, save=False)

    assert "All parameters will be refeshed on lima_simulator" in caplog.messages

    # change image parameters from outside of bliss
    simulator.image.roi = [1, 2, 30, 40]
    scan = loopscan(1, 0.1, simulator, save=False)
    old_roi = simulator.proxy.image_roi
    simulator.proxy.image_roi = [5, 6, 70, 80]

    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger="global.controllers.lima_simulator"):
        scan = loopscan(1, 0.1, simulator, save=False)

    new_roi = simulator.proxy.image_roi
    assert "All parameters will be refeshed on lima_simulator" in caplog.messages
    assert all(old_roi == new_roi)


def test_roi_devfailed(default_session, lima_simulator, caplog):
    simulator = default_session.config.get("lima_simulator")
    simulator.roi_counters["r1"] = Roi(0, 0, 100, 200)

    mocked_proxy = mock.MagicMock()
    mocked_proxy.dev_name.return_value = simulator.roi_counters._proxy.dev_name()
    mocked_proxy.readCounters.side_effect = DevFailed()
    simulator.roi_counters._proxy = mocked_proxy
    caplog.clear()

    scan = loopscan(1, 0.1, simulator, save=False)

    assert numpy.array_equal(scan.get_data()["r1_sum"], numpy.array([-1]))
    assert "Cannot read counters" in "\n".join(caplog.messages)


def test_roi_profile_devfailed(default_session, lima_simulator, caplog):
    simulator = default_session.config.get("lima_simulator")
    simulator.roi_profiles["s1"] = 20, 20, 20, 20
    simulator.roi_profiles.set_roi_mode("horizontal", "s1")

    mocked_proxy = mock.MagicMock()
    mocked_proxy.dev_name.return_value = simulator.roi_counters._proxy.dev_name()
    mocked_proxy.readImage.side_effect = DevFailed()
    mocked_proxy.addNames.return_value = [0]
    simulator.roi_profiles._proxy = mocked_proxy
    caplog.clear()

    scan = loopscan(1, 0.1, simulator.roi_profiles, save=False)

    assert "Cannot read profile" in "\n".join(caplog.messages)


def test_roi_collection(default_session, lima_simulator, tmp_path):

    from bliss.common.image_tools import array_to_file, file_to_array

    defdtype = numpy.int32  # uint8  # int32

    def build_rois(roinums, roisize, imsize):
        nx, ny = roinums
        lx, ly = roisize
        w, h = imsize
        dx, dy = int(w / nx), int(h / ny)
        assert dx >= 1
        assert dy >= 1
        assert lx <= dx
        assert ly <= dy

        rois = {}
        mask = numpy.zeros((h, w), dtype=defdtype)
        for idx in range(nx * ny):
            name = f"r{idx}"
            x = (idx % nx) * dx
            y = (idx // nx) * dy
            rois[name] = Roi(x, y, lx, ly)
            mask[y : y + ly, x : x + lx] = idx + 1
        return rois, mask

    def build_images(rois_mask, frames):
        return [rois_mask * (f + 1) for f in range(frames)]

    def save_images(imgdir, imgs):
        for idx, f in enumerate(imgs):
            fpath = os.path.join(imgdir, f"test_rois_{idx:04d}.edf")
            array_to_file(f, fpath)
        return os.path.join(imgdir, "test_rois*")

    # create temp folder to store test images
    imgdir = tmp_path / "test_images"
    imgdir.mkdir()

    # test parameters
    roinums = 80, 75
    roisize = 6, 4
    imsize = 800, 750
    frames = 50  # use a value > 1

    # build the rois
    rois, mask = build_rois(roinums, roisize, imsize)

    # build and save imgs
    imgs = build_images(mask, frames)
    fpat = save_images(imgdir, imgs)

    # load cam
    cam = default_session.config.get("lima_simulator")
    load_simulator_frames(cam, frames, fpat)
    collec = cam.roi_collection

    # load rois collection
    collec.clear()
    for name, roi in rois.items():
        # print(f"Load roi {name} {roi.get_coords}")
        collec[name] = roi

    assert len(collec.counters) == 1
    assert len(collec.get_rois()) == roinums[0] * roinums[1]

    # start loopscan
    t0 = time.time()
    s = loopscan(frames, 0.1, cam)
    print("scan took", time.time() - t0)

    # check results
    imgs = s.get_data("image").as_array()
    croi = s.get_data("*roi_collection_counter")
    assert imgs.shape == (frames, imsize[1], imsize[0])
    assert croi.shape == (frames, roinums[0] * roinums[1])

    if 0:
        import matplotlib.pyplot as plt

        # === check saved image files ======
        for idx in range(frames):
            fpath = os.path.join(imgdir, f"test_rois_{idx:04d}.edf")
            img = file_to_array(fpath)
            print("img info", img.shape, img.dtype)
            # img.dtype = defdtype
            plt.imshow(img)
            plt.show()

        # === check scan images ======
        for idx in range(frames):
            plt.imshow(imgs[idx])
            plt.show()

    for f in range(frames):
        sums = croi[f, :]
        assert numpy.all(
            sums
            == (f + 1)
            * (roisize[0] * roisize[1])
            * numpy.arange(1, roinums[0] * roinums[1] + 1)
        )
