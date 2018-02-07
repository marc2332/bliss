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

def test_mg(beacon):
  session = beacon.get("test_session")
  session.setup() 
  default_mg = getattr(setup_globals, 'ACTIVE_MG')
  test_mg = getattr(setup_globals, 'test_mg')
  assert measurementgroup.get_all() == [test_mg]
  assert default_mg.name == 'test_mg'
  assert measurementgroup.get_active_name() == 'test_mg'

def test_mg_states(beacon):
  session = beacon.get("test_session")
  session.setup() 
  default_mg = getattr(setup_globals, 'ACTIVE_MG')
  assert default_mg.active_state_name == 'default'
  default_mg.switch_state("state2")
  default_mg.disable = 'diode'
  assert default_mg.state_names == ['default', "state2"]
  assert default_mg.active_state_name == 'state2'
  assert list(default_mg.enable) == []
  default_mg.switch_state("default")
  assert list(default_mg.enable) == ["diode"]
  assert default_mg.active_state_name == 'default'

def test_mg_enable_disable(beacon):
  session = beacon.get("test_session")
  session.setup() 
  default_mg = getattr(setup_globals, 'ACTIVE_MG')
  assert list(default_mg.available) == ['diode']
  default_mg.disable = 'diode'
  assert list(default_mg.enable) == []
  assert list(default_mg.disable) == ['diode']
  default_mg.enable = 'diode'
  assert list(default_mg.disable) == []
  assert list(default_mg.enable) == ['diode']

def test_scan():
  scans.ct(0.1)

def test_clear_mg():
  default_mg = getattr(setup_globals, 'ACTIVE_MG')
  delattr(setup_globals, 'test_mg')  
  assert default_mg.name is None
  assert measurementgroup.get_active_name() is None

def test_scan_fail():
  with pytest.raises(ValueError):
    scans.ct(0.1)

