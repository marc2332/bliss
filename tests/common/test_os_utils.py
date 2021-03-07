# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import pytest
from bliss.common import os_utils
from ..utils.os_utils import disable_write_permissions


@pytest.fixture
def prepare_files(tmpdir):
    d = tmpdir / "dir"
    d.mkdir()

    f = tmpdir / "file.txt"
    f.write_text("content", "utf8")

    ro_d = tmpdir / "ro_dir"
    ro_d.mkdir()

    ro_f = tmpdir / "ro_file.txt"
    ro_f.write_text("content", "utf8")
    with disable_write_permissions(str(ro_d)) as disabled:
        if not disabled:
            ro_d = None
        with disable_write_permissions(str(ro_f)) as disabled:
            if not disabled:
                ro_f = None
            yield d, f, ro_d, ro_f


def test_find_existing(prepare_files):
    for path in prepare_files:
        if path is None:
            continue
        assert os_utils.find_existing(str(path)) == path
    for path in prepare_files:
        if path is None:
            continue
        path2 = path / "non_existing"
        assert os_utils.find_existing(str(path2)) == path
    for path in prepare_files:
        if path is None:
            continue
        path2 = path / "a" / ".." / "b" / "." / "c" / ""
        assert os_utils.find_existing(str(path2)) == path


def test_has_write_permissions(prepare_files):
    assert os_utils.has_write_permissions("")

    d, f, ro_d, ro_f = prepare_files

    for path in [d, f]:
        if path is None:
            continue
        assert os_utils.has_write_permissions(str(path))
    for path in [ro_d, ro_f]:
        if path is None:
            continue
        assert not os_utils.has_write_permissions(str(path))

    for path in [d]:
        if path is None:
            continue
        path = path / "non_existing"
        assert os_utils.has_write_permissions(str(path))
    for path in [f, ro_d, ro_f]:
        if path is None:
            continue
        path = path / "non_existing"
        assert not os_utils.has_write_permissions(str(path))

    for path in [d]:
        if path is None:
            continue
        path = path / "a" / ".." / "b" / "." / "c" / ""
        assert os_utils.has_write_permissions(str(path))

    for path in [f, ro_d, ro_f]:
        if path is None:
            continue
        path = path / "a" / ".." / "b" / "." / "c" / ""
        assert not os_utils.has_write_permissions(str(path))


def test_has_required_disk_space(prepare_files, tmpdir):
    statvfs = os.statvfs(tmpdir)
    free_space = statvfs.f_frsize * statvfs.f_bavail / 1024 ** 2
    less = free_space / 2
    more = free_space * 2

    assert os_utils.has_required_disk_space("", 1)

    for path in prepare_files:
        if path is None:
            continue
        assert os_utils.has_required_disk_space(str(path), less)
        assert not os_utils.has_required_disk_space(str(path), more)
    for path in prepare_files:
        if path is None:
            continue
        path2 = path / "non_existing"
        assert os_utils.has_required_disk_space(str(path2), less)
        assert not os_utils.has_required_disk_space(str(path2), more)
    for path in prepare_files:
        if path is None:
            continue
        path2 = path / "a" / ".." / "b" / "." / "c" / ""
        assert os_utils.has_required_disk_space(str(path2), less)
        assert not os_utils.has_required_disk_space(str(path2), more)
