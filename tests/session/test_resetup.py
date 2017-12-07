# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import time
from bliss.common import measurementgroup
from bliss import setup_globals
from bliss.common import scans
from bliss.common import measurement

def test_resetup(beacon):
  session = beacon.get("test_session")
  env_dict = {}
  session.setup(env_dict=env_dict)
  assert "load_script" in env_dict
  assert getattr(setup_globals, "test_session")
  assert getattr(setup_globals, "test_mg")
  assert "test_session" in env_dict
  env_dict["test_session"].sentinel = True
  assert getattr(getattr(setup_globals, "test_session"), "sentinel")
  session.resetup(env_dict=env_dict)
  assert "load_script" in env_dict
  test_session = getattr(setup_globals, "test_session")
  assert pytest.raises(AttributeError, getattr, test_session, "sentinel") 
  assert "test_session" in env_dict
  assert test_session == env_dict["test_session"]

  


