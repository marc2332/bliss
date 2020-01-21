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


def test_config_withoutpolicy(nexus_base_session_nopolicy):
    session, scan_tmpdir = nexus_base_session_nopolicy
    scan_tmpdir = str(scan_tmpdir)
    validate_writer_config(scan_writer_publish.writer_config())
    assert config_utils.beamline() == "id00"
    assert config_utils.institute() == "ESRF"
    assert scan_writer_publish.default_technique() == "none"
    assert scan_writer_publish.current_technique() == "none"
    directory = scan_utils.current_directory()
    expected_directory = os.path.join(scan_tmpdir, session.name)
    assert directory == expected_directory
    filenames = scan_utils.current_filenames()
    expected_filenames = [os.path.join(scan_tmpdir, session.name, "a_b_external.h5")]
    assert filenames == expected_filenames


def test_config_withpolicy(nexus_base_session_policy):
    session, scan_tmpdir = nexus_base_session_policy
    scan_tmpdir = str(scan_tmpdir)
    validate_writer_config(scan_writer_publish.writer_config())
    assert config_utils.beamline() == "id00"
    assert config_utils.institute() == "ESRF"
    assert scan_writer_publish.default_technique() == "none"
    assert scan_writer_publish.current_technique() == "xrfxrd"
    directory = scan_utils.current_directory()
    expected_directory = os.path.join(
        scan_tmpdir, "prop123", "id00", "sample", "sample_dataset"
    )
    assert directory == expected_directory
    filenames = scan_utils.current_filenames()
    expected_filenames = [
        os.path.join(
            scan_tmpdir,
            "prop123",
            "id00",
            "sample",
            "sample_dataset",
            "sample_dataset.h5",
        ),
        os.path.join(scan_tmpdir, "prop123", "id00", "sample", "prop123_sample.h5"),
        os.path.join(scan_tmpdir, "prop123", "id00", "prop123_id00.h5"),
    ]
    assert filenames == expected_filenames


def validate_writer_config(cfg):
    assert {"name", "technique"} == set(cfg.keys())
    assert {"default", "techniques", "applications", "plots"} == set(
        cfg["technique"].keys()
    )
