# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.controllers.transfocator import Transfocator


def test_transfocator(default_session, transfocator_mockup):
    transfocator = default_session.config.get("transfocator_simulator")
    transfocator.connect()
    # only reading is possible due to simulator limitations
    transfocator.status_read()
    transfocator.status_dict()
