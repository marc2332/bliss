# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common.standard import info
from bliss.common.scans import loopscan


def test_scan_saving(session, scan_saving):
    scan_saving.base_path = "/tmp"
    scan_saving.template = "{session}/toto"
    parent_node = scan_saving.get_parent_node()
    assert parent_node.name == "toto"
    assert parent_node.parent is not None
    assert parent_node.parent.parent.name == scan_saving.session
    assert parent_node.parent.parent.db_name == scan_saving.session
    assert parent_node.db_name == "%s:%s" % (parent_node.parent.db_name, "toto")

    scan_saving.template = "toto"
    parent_node = scan_saving.get_parent_node()
    assert parent_node.name == "toto"
    assert parent_node.parent is not None
    assert parent_node.parent.parent.name == scan_saving.session
    assert parent_node.parent.parent.db_name == scan_saving.session
    assert parent_node.db_name == "%s:tmp:%s" % (scan_saving.session, "toto")

    scan_saving_repr = """\
Parameters (default) - 

  .base_path            = '/tmp'
  .data_filename        = 'data'
  .user_name            = '{user_name}'
  .template             = 'toto'
  .images_path_relative = True
  .images_path_template = 'scan{{scan_number}}'
  .images_prefix        = '{{img_acq_device}}_'
  .date_format          = '%Y%m%d'
  .scan_number_format   = '%04d'
  .session              = '{session}'
  .date                 = '{date}'
  .scan_name            = 'scan name'
  .scan_number          = 'scan number'
  .img_acq_device       = '<images_* only> acquisition device name'
  .writer               = 'hdf5'
  .creation_date        = '{creation_date}'
  .last_accessed        = '{last_accessed}'
--------------  ---------  -----------------
does not exist  filename   /tmp/toto/data.h5
does not exist  root_path  /tmp/toto
--------------  ---------  -----------------""".format(
        creation_date=scan_saving.creation_date,
        date=scan_saving.date,
        last_accessed=scan_saving.last_accessed,
        session=scan_saving.session,
        user_name=scan_saving.user_name,
    )


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

    loopscan(1, 0.1, session.env_dict["diode"])
