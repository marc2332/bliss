# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import unittest
import sys
import os

sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            os.path.pardir, os.path.pardir)))

from bliss.common.axis import AxisState


class TestStates(unittest.TestCase):

    def setUp(self):
        pass

    def test_states(self):
        # empty state
        s = AxisState()
        self.assertEquals(s, "UNKNOWN")

        # moving
        s.set("MOVING")
        self.assertEquals(s, "MOVING")

        # moving => not ready
        self.assertFalse(s.READY)

        # now ready but no more moving
        s.set("READY")
        self.assertTrue(s.READY)
        self.assertFalse(s.MOVING)

        # custom state
        s.create_state("PARKED", "c'est ma place !!")
        s.set("PARKED")
        # still ready
        self.assertTrue(s.READY)
        self.assertEquals(s, "PARKED")

        # Prints string of states.
        self.assertTrue(isinstance(s.current_states(), str))

        # bad name for a state
        self.assertRaises(ValueError, s.create_state, "A bad state")

    def test_init_state(self):
        self.assertEquals(AxisState(), "UNKNOWN")

    def test_desc(self):
        s = AxisState(("KAPUT", "auff"), "LIMNEG", "READY")
        self.assertTrue(s.READY)
        self.assertEquals(s._state_desc["KAPUT"], "auff")
        self.assertEquals(s._state_desc["LIMNEG"], "Hardware low limit active")

    def test_from_current_states_str(self):
        s = AxisState(("KAPUT", "auff"), "LIMNEG", "READY")
        states_str = s.current_states()
        t = AxisState(states_str)
        self.assertTrue(t.READY)
        self.assertEquals(t._state_desc["KAPUT"], "auff")
        self.assertEquals(t._state_desc["LIMNEG"], "Hardware low limit active")
        self.assertEquals(s.current_states(), t.current_states())
        u = AxisState()
        v = AxisState(u.current_states())
        self.assertEquals(u.current_states(), v.current_states())

    def test_state_from_state(self):
        s = AxisState("READY")
        t = AxisState(s)
        self.assertEquals(s.current_states(), t.current_states())
       
    def test_clear_state(self):
        s = AxisState("READY")
        s.clear()
        self.assertEquals(s, "UNKNOWN")

        s.set("MOVING")
        self.assertEquals(s, "MOVING")

if __name__ == '__main__':
    unittest.main()
