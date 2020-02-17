# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
from bliss.common.standard import info
from bliss.common.scans import ct
from bliss.scanning import scan_saving as scan_saving_module


def test_scan_saving_parent_node(session, scan_saving):
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


@pytest.mark.parametrize("writer", ["hdf5", "nexus", "null"])
def test_scan_saving_path(writer, session, scan_tmpdir):
    scan_saving = session.scan_saving
    scan_saving.base_path = str(scan_tmpdir)
    scan_saving.template = "{session}/{scan_name}/{scan_number}"
    scan_saving.data_filename = "{session}_{scan_name}_data"
    scan_saving.writer = writer

    assert scan_saving.base_path == str(scan_tmpdir)
    assert scan_saving.template == "{session}/{scan_name}/{scan_number}"
    assert scan_saving.data_filename == "{session}_{scan_name}_data"

    # Test all path related methods and properties
    root_path = f"{scan_tmpdir}/{session.name}/{{scan_name}}/{{scan_number}}"
    assert scan_saving.get_path() == root_path
    assert scan_saving.root_path == root_path
    images_path = f"{scan_tmpdir}/{session.name}/{{scan_name}}/{{scan_number}}/scan{{scan_number}}/{{img_acq_device}}_"
    assert scan_saving.images_path == images_path
    data_path = f"{scan_tmpdir}/{session.name}/{{scan_name}}/{{scan_number}}/{session.name}_{{scan_name}}_data"
    assert scan_saving.data_path == data_path
    if writer == "null":
        data_fullpath = data_path + "."
    else:
        data_fullpath = data_path + ".h5"
    assert scan_saving.data_fullpath == data_fullpath
    assert scan_saving.eval_data_filename == f"{session.name}_{{scan_name}}_data"
    if writer == "null":
        filename = ""
    else:
        filename = data_fullpath
    assert scan_saving.filename == filename

    getdict = scan_saving.get()
    getdict.pop("writer")
    getdict.pop("db_path_items")
    expected = {
        "root_path": root_path,
        "data_path": data_path,
        "images_path": images_path,
    }
    assert getdict == expected

    scan_saving_repr = """Parameters (default) - 

  .base_path            = '{base_path}'
  .data_filename        = '{{session}}_{{scan_name}}_data'
  .user_name            = '{user_name}'
  .template             = '{{session}}/{{scan_name}}/{{scan_number}}'
  .images_path_relative = True
  .images_path_template = 'scan{{scan_number}}'
  .images_prefix        = '{{img_acq_device}}_'
  .date_format          = '%Y%m%d'
  .scan_number_format   = '%04d'
  .session              = '{session}'
  .date                 = '{date}'
  .scan_name            = '{{scan_name}}'
  .scan_number          = '{{scan_number}}'
  .img_acq_device       = '<images_* only> acquisition device name'
  .writer               = '{writer}'
  .data_policy          = 'None'
  .creation_date        = '{creation_date}'
  .last_accessed        = '{last_accessed}'
--------------  ---------  -----------
does not exist  filename   {filename}
does not exist  directory  {root_path}
--------------  ---------  -----------""".format(
        base_path=str(scan_tmpdir),
        session=session.name,
        user_name=scan_saving.user_name,
        date=scan_saving.date,
        writer=writer,
        creation_date=scan_saving.creation_date,
        last_accessed=scan_saving.last_accessed,
        filename=filename,
        root_path=root_path,
    )

    expected = scan_saving_repr.split("\n")
    actual = info(scan_saving).split("\n")
    if writer == "null":
        expected = expected[:-1]
        expected[-3:] = ["---------", "NO SAVING", "---------"]
    else:
        add = "-" * (len(actual[-1]) - len(expected[-1]))
        expected[-4] += add
        expected[-1] += add
    assert actual == expected

    # Test scan saving related things after a scan
    if writer == "nexus":
        s = ct(0.1, session.env_dict["diode"])
        assert s.scan_info["filename"] == ""
    else:
        s = ct(0.1, session.env_dict["diode"], save=True, name="sname")
    assert s.scan_info["data_policy"] == "None"
    assert s.scan_info["data_writer"] == writer
    assert s.node.parent.db_name == scan_saving.scan_parent_db_name


class CustomWardrobe(scan_saving_module.EvalParametersWardrobe):
    PROPERTY_ATTRIBUTES = ["p1", "p2"]
    PROPS = {"p1": "p1", "p2": "p2"}

    def __init__(self, name):
        default_values = {
            "a": "va",
            "b": "vb",
            "c": "vc",
            "d": "{a}+{b}+{p1}",
            "e": "{d}+{d}+{b}+{p2}",
            "f": "{f}",
            "g": "{f}_{f}",
            "circlea1": "{a}_{circlea1}",
            "circleb1": "{b}_{circleb2}",
            "circleb2": "{circleb1}_{b}",
            "circlec1": "{c}_{circlec2}",
            "circlec2": "{circlec3}_{c}",
            "circlec3": "{c}_{circlec1}",
            "circled1": "{circled1}_{a}",
        }
        super().__init__(
            name, default_values=default_values, property_attributes=["p1", "p2"]
        )

    @scan_saving_module.property_with_eval_dict
    def p1(self, eval_dict=None):
        return self.PROPS["p1"]

    @scan_saving_module.property_with_eval_dict
    def p2(self, eval_dict=None):
        return self.PROPS["p2"]

    def func1(self):
        return "func1" + self.p1 + self.func2()

    def func2(self):
        return "func2" + self.p2

    def func3(self):
        return "{e}"


def test_scan_saving_eval(session):

    wr = CustomWardrobe("test_scan_saving_eval")
    wr.add("pfunc1", CustomWardrobe.func1)
    wr.add("pfunc2", CustomWardrobe.func2)
    wr.add("pfunc3", CustomWardrobe.func3)
    wr.add("afuncs", "{a}_{pfunc1}_{pfunc2}_{pfunc3}")

    # Check template evaluation

    eval_dict = {}
    for _ in range(2):
        assert wr.eval_template(wr.a, eval_dict=eval_dict) == "va"
        assert wr.eval_template(wr.b, eval_dict=eval_dict) == "vb"
        assert wr.eval_template(wr.c, eval_dict=eval_dict) == "vc"

        assert wr.eval_template(wr.d, eval_dict=eval_dict) == "va+vb+p1"
        assert wr.eval_template(wr.d, eval_dict=eval_dict) == "va+vb+p1"

        assert wr.eval_template(wr.e, eval_dict=eval_dict) == "va+vb+p1+va+vb+p1+vb+p2"
        assert wr.eval_template(wr.e, eval_dict=eval_dict) == "va+vb+p1+va+vb+p1+vb+p2"
        assert wr.eval_template(wr.f, eval_dict=eval_dict) == "{f}"
        assert wr.eval_template(wr.f, eval_dict=eval_dict) == "{f}"

        assert wr.eval_template(wr.g, eval_dict=eval_dict) == "{f}_{f}"
        assert wr.eval_template(wr.g, eval_dict=eval_dict) == "{f}_{f}"

        assert wr.eval_template(wr.pfunc1, eval_dict=eval_dict) == "func1p1func2p2"
        assert wr.eval_template(wr.pfunc1, eval_dict=eval_dict) == "func1p1func2p2"

        assert wr.eval_template(wr.pfunc2, eval_dict=eval_dict) == "func2p2"
        assert wr.eval_template(wr.pfunc2, eval_dict=eval_dict) == "func2p2"

        assert (
            wr.eval_template(wr.pfunc3, eval_dict=eval_dict)
            == "va+vb+p1+va+vb+p1+vb+p2"
        )
        assert (
            wr.eval_template(wr.pfunc3, eval_dict=eval_dict)
            == "va+vb+p1+va+vb+p1+vb+p2"
        )

        assert (
            wr.eval_template(wr.afuncs, eval_dict=eval_dict)
            == "va_func1p1func2p2_func2p2_va+vb+p1+va+vb+p1+vb+p2"
        )
        assert (
            wr.eval_template(wr.afuncs, eval_dict=eval_dict)
            == "va_func1p1func2p2_func2p2_va+vb+p1+va+vb+p1+vb+p2"
        )

        assert (
            wr.eval_template(wr.pfunc3, eval_dict=eval_dict)
            == "va+vb+p1+va+vb+p1+vb+p2"
        )
        assert (
            wr.eval_template(wr.pfunc3, eval_dict=eval_dict)
            == "va+vb+p1+va+vb+p1+vb+p2"
        )

        assert wr.eval_template(wr.circlea1, eval_dict=eval_dict) == "va_{circlea1}"
        assert wr.eval_template(wr.circlea1, eval_dict=eval_dict) == "va_{circlea1}"

        assert wr.eval_template(wr.circled1, eval_dict=eval_dict) == "{circled1}_va"
        assert wr.eval_template(wr.circled1, eval_dict=eval_dict) == "{circled1}_va"

        assert wr.eval_template(wr.circleb1, eval_dict=eval_dict) == "vb_{circleb1}_vb"
        assert wr.eval_template(wr.circleb1, eval_dict=eval_dict) == "vb_{circleb1}_vb"

        assert wr.eval_template(wr.circleb2, eval_dict=None) == "vb_{circleb2}_vb"
        assert wr.eval_template(wr.circleb2, eval_dict=None) == "vb_{circleb2}_vb"

        assert wr.eval_template(wr.circlec1, eval_dict=eval_dict) == "vc_{circlec3}_vc"
        assert wr.eval_template(wr.circlec1, eval_dict=eval_dict) == "vc_{circlec3}_vc"

        assert wr.eval_template(wr.circlec2, eval_dict=None) == "vc_{circlec1}_vc"
        assert wr.eval_template(wr.circlec2, eval_dict=None) == "vc_{circlec1}_vc"

        assert wr.eval_template(wr.circlec3, eval_dict=None) == "vc_vc_{circlec2}"
        assert wr.eval_template(wr.circlec3, eval_dict=None) == "vc_vc_{circlec2}"

    # Check caching

    eval_dict = {}
    assert wr.func1() == "func1p1func2p2"
    assert wr.func1() == "func1p1func2p2"
    wr.PROPS["p1"] = "v1"
    wr.PROPS["p2"] = "v2"
    assert wr.func1() == "func1v1func2v2"
    assert wr.func1() == "func1v1func2v2"

    eval_dict = {}
    assert wr.eval_template(wr.a, eval_dict=eval_dict) == "va"
    assert wr.eval_template(wr.b, eval_dict=eval_dict) == "vb"
    assert wr.eval_template(wr.c, eval_dict=eval_dict) == "vc"

    wr.a = wr.b = wr.c = "modify"
    assert wr.eval_template(wr.d, eval_dict=eval_dict) == "va+vb+v1"
    assert wr.eval_template(wr.d, eval_dict=eval_dict) == "va+vb+v1"

    wr.d = "modify"
    assert wr.eval_template(wr.e, eval_dict=eval_dict) == "va+vb+v1+va+vb+v1+vb+v2"
    assert wr.eval_template(wr.e, eval_dict=eval_dict) == "va+vb+v1+va+vb+v1+vb+v2"
