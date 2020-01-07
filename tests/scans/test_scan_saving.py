# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common.standard import info


def test_scan_saving_template(session, scan_tmpdir):
    # put scan file in a tmp directory
    session.scan_saving.base_path = str(scan_tmpdir)

    session.scan_saving.template = "{scan_name}/{scan_number}"

    scan_saving_info = info(session.scan_saving)
    assert "scan_name" in scan_saving_info
    assert "scan_number" in scan_saving_info
    assert "data.h5" in scan_saving_info

    assert (
        session.scan_saving.get_path() == f"{scan_tmpdir}/{{scan_name}}/{{scan_number}}"
    )
