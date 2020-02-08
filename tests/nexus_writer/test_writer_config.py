# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
from nexus_writer_service.utils import config_utils
from nexus_writer_service.utils import scan_utils
from nexus_writer_service.subscribers import scan_writer_publish


def test_config_withoutpolicy(nexus_writer_config_nopolicy):
    session = nexus_writer_config_nopolicy["session"]
    tmpdir = nexus_writer_config_nopolicy["tmpdir"]
    validate_writer_config(scan_writer_publish.writer_config())
    assert config_utils.beamline() == "id00"
    assert config_utils.institute() == "ESRF"
    assert scan_writer_publish.default_technique() == "none"
    assert scan_writer_publish.current_technique() == "none"
    filenames = scan_utils.session_filenames(config=True)
    expected_filenames = {"dataset": tmpdir.join(session.name, "a_b.h5")}
    assert filenames == expected_filenames


def test_config_withpolicy(nexus_writer_config):
    session = nexus_writer_config["session"]
    tmpdir = nexus_writer_config["tmpdir"]
    validate_writer_config(scan_writer_publish.writer_config())
    assert config_utils.beamline() == "id00"
    assert config_utils.institute() == "ESRF"
    assert scan_writer_publish.default_technique() == "none"
    assert scan_writer_publish.current_technique() == "xrfxrd"
    filenames = scan_utils.session_filenames(config=True)
    expected_filenames = {}
    expected_filenames["dataset"] = tmpdir.join(
        session.name,
        "tmp",
        "testproposal",
        "id00",
        "sample",
        "sample_0001",
        "sample_0001.h5",
    )
    expected_filenames["sample"] = tmpdir.join(
        session.name, "tmp", "testproposal", "id00", "sample", "testproposal_sample.h5"
    )
    expected_filenames["proposal"] = tmpdir.join(
        session.name, "tmp", "testproposal", "id00", "testproposal_id00.h5"
    )
    assert filenames == expected_filenames


def validate_writer_config(cfg):
    assert {"name", "technique"} == set(cfg.keys())
    assert {"default", "techniques", "applications", "plots"} == set(
        cfg["technique"].keys()
    )
