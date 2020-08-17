# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import types
import pytest
import logging
import io
import numpy
from bliss.scanning.acquisition.timer import SoftwareTimerMaster
from bliss.common.tango import DeviceProxy, DevFailed
from bliss.common.counter import Counter
from bliss.controllers.lima.roi import Roi
from bliss.common.scans import loopscan, timescan, sct, ct, DEFAULT_CHAIN
import gevent
from contextlib import contextmanager
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


def test_lima_sim_bpm(beacon, default_session, lima_simulator):
    simulator = beacon.get("lima_simulator")

    assert "fwhm_x" in simulator.counters._fields
    assert "bpm" in simulator.counter_groups._fields

    s = loopscan(1, 0.1, simulator.counter_groups.bpm, save=False)

    data = s.get_data()
    assert f"{simulator.name}:bpm:x" in s.get_data()
    assert len(data) == 6 + 2  # 6 bpm counters + 2 timer


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

    assert simulator.image.rotation == "90"
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
    # check there is no change in ctrl params when repeating the scan
    assert len(caplog.messages) == 0

    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger="global.controllers.lima_simulator"):
        scan = loopscan(1, 0.1, simulator, run=False)
        scan.update_ctrl_params(simulator, {"saving_max_writing_task": 2})
        scan.run()

    # check that a change in ctrl params leads to update in camera
    assert len(caplog.messages) == 1
    assert "updating saving_max_writing_task on lima_simulator to 2" in caplog.messages
    assert simulator.proxy.saving_max_writing_task == 2

    # lets see if we can use mask, background and flatfield
    img = scan.get_data()["image"].all_image_references()[0][0]
    simulator.processing.mask = img
    simulator.processing.use_mask = True

    simulator.processing.flatfield = img
    simulator.processing.use_flatfield = True

    simulator.processing.background = img
    simulator.processing.use_background_substraction = "enable_file"

    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger="global.controllers.lima_simulator"):
        scan = loopscan(1, 0.1, simulator, save=False)

    assert " uploading new mask on lima_simulator" in caplog.messages
    assert " uploading flatfield on lima_simulator" in caplog.messages
    assert " uploading background on lima_simulator" in caplog.messages
    assert " starting background sub proxy of lima_simulator" in caplog.messages

    simulator.processing.use_mask = False
    simulator.processing.use_flatfield = False
    simulator.processing.use_background_substraction = "disable"

    # check if aqcuistion still works
    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger="global.controllers.lima_simulator"):
        scan = loopscan(1, 0.1, simulator, save=False)

    simulator.processing.background = "not_existing_file"
    simulator.processing.use_background_substraction = "enable_on_fly"
    simulator.bg_sub.take_background(.1)

    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger="global.controllers.lima_simulator"):
        scan = loopscan(1, 0.1, simulator, save=False)

    assert " starting background sub proxy of lima_simulator" in caplog.messages


def test_reapplying_ctrl_params(default_session, caplog):
    simulator = default_session.config.get("lima_simulator")

    with lima_simulator_context("simulator", "id00/limaccds/simulator1"):
        with caplog.at_level(logging.DEBUG, logger="global.controllers.lima_simulator"):
            scan = loopscan(1, 0.1, simulator, save=False)
        assert "All parameters will be refeshed on lima_simulator" in caplog.messages

    with pytest.raises(DevFailed):
        caplog.clear()
        with caplog.at_level(logging.DEBUG, logger="global.controllers.lima_simulator"):
            scan = loopscan(1, 0.1, simulator, save=False)

    with lima_simulator_context("simulator", "id00/limaccds/simulator1"):
        caplog.clear()
        with caplog.at_level(logging.DEBUG, logger="global.controllers.lima_simulator"):
            scan = loopscan(1, 0.1, simulator, save=False)
        assert "All parameters will be refeshed on lima_simulator" in caplog.messages

    with lima_simulator_context("simulator", "id00/limaccds/simulator1"):
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


def test_lima_simulator_dialogs(beacon, lima_simulator, clean_gevent):
    clean_gevent["end-check"] = False
    simulator = beacon.get("lima_simulator")
    with pytest.raises(io.UnsupportedOperation):
        simulator.configure_image()
        simulator.configure_saving()
        simulator.configure_processing()


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
    Cache(simulator, "last_session_used").value = "toto_session"

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


def test_image_param_sync(beacon, default_session, lima_simulator):
    simulator = beacon.get("lima_simulator")

    # do one initial scan to set all caches and tango properties
    loopscan(1, 0.1, simulator, save=False)
    assert list(simulator.image.roi.to_array()) == [0, 0, 1024, 1024]
    assert simulator.image.flip == [False, False]
    assert simulator.image.rotation == "90"
    assert simulator.image.bin == [1, 1]

    simulator.proxy.image_bin = [2, 2]
    simulator.proxy.image_roi = [1, 2, 30, 40]
    simulator.proxy.image_flip = [True, False]
    simulator.proxy.image_rotation = "180"

    assert simulator.image.bin == [1, 1]
    assert list(simulator.image.roi.to_array()) == [0, 0, 1024, 1024]
    assert simulator.image.flip == [False, False]
    assert simulator.image.rotation == "90"

    simulator.image.sync()

    # have in mind that rotation is applied on roi...
    assert simulator.image.bin == [2, 2]
    assert list(simulator.image.roi.to_dict().values()) == [2, 1, 40, 30]
    assert simulator.image.flip == [True, False]
    assert simulator.image.rotation == "180"
