# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import types
import pytest
from bliss.scanning.acquisition.timer import SoftwareTimerMaster
from bliss.common.tango import DeviceProxy
from bliss.common.counter import Counter
from bliss.controllers.lima.roi import Roi
from bliss.common.scans import loopscan, DEFAULT_CHAIN
from bliss import setup_globals
import gevent


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


def test_lima_sim_bpm(beacon, lima_simulator):
    simulator = beacon.get("lima_simulator")

    assert "fwhm_x" in simulator.counters._fields
    assert "bpm" in simulator.counter_groups._fields


def assert_lima_rois(lima_roi_counter, rois):
    roi_names = lima_roi_counter.getNames()
    raw_rois = lima_roi_counter.getRois(roi_names)

    assert set(rois.keys()) == set(roi_names)

    lima_rois = {
        name: Roi(*raw_rois[i * 5 + 1 : i * 5 + 4 + 1], name=name)
        for i, name in enumerate(roi_names)
    }
    assert rois == lima_rois


def test_rois(beacon, lima_simulator):
    simulator = beacon.get("lima_simulator")
    rois = simulator.roi_counters

    dev_name = lima_simulator[0].lower()
    roi_dev = DeviceProxy(dev_name.replace("limaccds", "roicounter"))

    assert len(rois) == 0

    r1 = Roi(0, 0, 100, 200)
    r2 = Roi(10, 20, 200, 500)
    r3 = Roi(20, 60, 500, 500)
    r4 = Roi(60, 20, 50, 10)

    rois["r1"] = r1
    assert_lima_rois(roi_dev, dict(r1=r1))
    rois["r2"] = r2
    assert_lima_rois(roi_dev, dict(r1=r1, r2=r2))
    rois["r3", "r4"] = r3, r4
    assert_lima_rois(roi_dev, dict(r1=r1, r2=r2, r3=r3, r4=r4))

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
    assert_lima_rois(roi_dev, dict(r2=r2, r3=r3, r4=r4))

    del rois["r3", "r2"]
    assert len(rois) == 1
    assert_lima_rois(roi_dev, dict(r4=r4))

    # test classic interface

    rois.set("r1", r1)
    assert len(rois) == 2
    assert_lima_rois(roi_dev, dict(r1=r1, r4=r4))

    rois.remove("r4")
    assert len(rois) == 1
    assert_lima_rois(roi_dev, dict(r1=r1))


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

    scan_saving.base_path = "/tmp/scans"
    scan_saving.images_path_template = ""
    scan_saving.images_prefix = "toto"

    saving_directory = None
    try:
        simulator.select_directories_mapping("fancy")
        mapped_directory = simulator.get_mapped_path(scan_saving.get_path())
        ct = setup_globals.ct(0.1, simulator, save=True, run=False)

        try:
            ct.run()
        except Exception as e:
            # this will fail because directory is not likely to exist
            saving_directory = e.args[0].desc.split("Directory :")[-1].split()[0]
    finally:
        scan_saving.from_dict(scan_saving_dump)
        simulator.select_directories_mapping("identity")

    # cannot use simulator.proxy.saving_directory because it is reset to ''
    assert mapped_directory.startswith(saving_directory)


def test_images_dir_prefix_saving(lima_simulator, scan_tmpdir, session):
    simulator = session.config.get("lima_simulator")
    scan_saving = session.scan_saving
    scan_saving_dump = scan_saving.to_dict()

    scan_saving.base_path = str(scan_tmpdir)
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

        setup_globals.loopscan(1, 0.1, simulator)

        assert os.path.isdir(scan_config["root_path"])
        assert os.path.isdir(os.path.join(scan_config["root_path"], "loopscan_1/toto"))
        assert os.path.exists(
            os.path.join(
                scan_config["root_path"], "loopscan_1/toto/lima_simulator0000.edf"
            )
        )
    finally:
        scan_saving.from_dict(scan_saving_dump)


def test_images_dir_prefix_saving_absolute(lima_simulator, scan_tmpdir, session):
    simulator = session.config.get("lima_simulator")
    scan_saving = session.scan_saving
    scan_saving_dump = scan_saving.to_dict()

    scan_saving.base_path = str(scan_tmpdir)
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

        setup_globals.timescan(0.1, simulator, npoints=1)

        assert os.path.isdir(scan_config["root_path"])
        assert os.path.isdir(os.path.join(scan_config["root_path"], "timescan_1/toto"))
        assert os.path.exists(
            os.path.join(
                scan_config["root_path"], "timescan_1/toto/lima_simulator0000.edf"
            )
        )
    finally:
        scan_saving.from_dict(scan_saving_dump)


def test_images_dir_saving_null_writer(lima_simulator, scan_tmpdir, session):
    # issue 1010
    simulator = session.config.get("lima_simulator")
    scan_saving = session.scan_saving
    scan_saving_dump = scan_saving.to_dict()

    scan_saving.base_path = str(scan_tmpdir)
    scan_saving.template = "test"
    scan_saving.images_path_relative = False
    scan_saving.images_path_template = "{base_path}/test/{scan_name}_{scan_number}/tata"
    scan_saving.images_prefix = "{img_acq_device}"
    scan_saving.scan_number_format = "%1d"
    scan_saving.writer = "null"

    try:
        scan_config = scan_saving.get()

        setup_globals.timescan(0.1, simulator, npoints=1)

        assert os.path.exists(
            os.path.join(
                scan_config["root_path"], "timescan_1/tata/lima_simulator0000.edf"
            )
        )
    finally:
        scan_saving.from_dict(scan_saving_dump)


def test_dir_no_saving(lima_simulator, scan_tmpdir, session):
    # issue 1070
    simulator = session.config.get("lima_simulator")
    scan_saving = session.scan_saving
    scan_saving_dump = scan_saving.to_dict()

    scan_saving.base_path = str(scan_tmpdir)

    try:
        scan_config = scan_saving.get()

        setup_globals.timescan(0.1, simulator, npoints=1, save=False)

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
