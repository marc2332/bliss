# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import time
from bliss.session import measurementgroup
from bliss import setup_globals
from bliss.common import scans
from bliss.common import measurement

def test_default_session(beacon):
  session = beacon.get("test_session")
  session.setup()
  assert pytest.raises(AttributeError, getattr, setup_globals, "freddy")


