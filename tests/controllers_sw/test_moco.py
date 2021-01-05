# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common import measurementgroup


def test_moco(dummy_tango_server, session):
    mymoco = session.config.get("mymoco")
    mg = measurementgroup.MeasurementGroup("local", {"counters": ["mymoco"]})

    assert set(mg.available) == {
        mymoco.counters.outm.fullname,
        mymoco.counters.inm.fullname,
    }
