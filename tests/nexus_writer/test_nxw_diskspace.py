# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
from bliss.common import scans
from tests.nexus_writer.helpers import nxw_test_utils


def test_nxw_diskspace(nexus_writer_limited_disk_space):
    _test_nxw_diskspace(**nexus_writer_limited_disk_space)


@nxw_test_utils.writer_stdout_on_exception
def _test_nxw_diskspace(session=None, **kwargs):
    with pytest.raises(RuntimeError):
        scans.loopscan(1, 0.1, session.env_dict["diode3"])
