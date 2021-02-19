# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common import scans
from tests.nexus_writer.helpers import nxw_test_utils
from nexus_writer_service.io import nexus
from nexus_writer_service.utils import scan_utils
from bliss.scanning.scan_meta import get_user_scan_meta


def test_nxw_scaninfo(nexus_writer_config):
    _test_nxw_scaninfo(**nexus_writer_config)


@nxw_test_utils.writer_stdout_on_exception
def _test_nxw_scaninfo(session=None, writer=None, **kwargs):
    diode = session.env_dict["diode3"]

    # Static information
    scan_info = {
        "instrument": {"diode3": {"@myattr": 1, "mydset": [1, 2, 3]}},
        "measurement": {">mylink": "../instrument/diode3/mydset"},
        "scan_meta_categories": ["measurement"],
    }

    # Dynamic informations
    def dynamic_gen1(scan):
        return {"@myattr": 2}

    def dynamic_gen2(scan):
        return {"mydset": [4, 5, 6]}

    usm = get_user_scan_meta()
    usm.add_categories(["mygroup"])
    usm.mygroup.set("dynamic_gen1", dynamic_gen1)
    usm.mygroup.set("dynamic_gen2", dynamic_gen2)

    scan = scans.loopscan(3, .1, diode, run=False, scan_info=scan_info)
    nxw_test_utils.run_scan(scan)
    nxw_test_utils.wait_scan_data_finished([scan], writer=writer)

    uri = scan_utils.scan_uri(scan)
    with nexus.uriContext(uri) as nxentry:
        expected = {"NX_class": "NXdetector", "myattr": 1}
        actual = dict(nxentry["instrument/diode3"].attrs)
        assert actual == expected
        expected = [1, 2, 3]
        actual = nxentry["instrument/diode3/mydset"][()].tolist()
        assert actual == expected
        actual = nxentry["measurement/mylink"][()].tolist()
        assert actual == expected

        expected = {"NX_class": "NXcollection", "myattr": 2}
        actual = dict(nxentry["mygroup"].attrs)
        expected = [4, 5, 6]
        actual = nxentry["mygroup/mydset"][()].tolist()
        assert actual == expected
