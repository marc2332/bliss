import unittest
import sys
import os

sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..")))

from bliss.common.axis import AxisState


class TestStates(unittest.TestCase):

    def setUp(self):
        pass

    def test_states(self):

        s = AxisState("MOVING")
        self.assertEquals(s, "MOVING")

        s.create_state("PARKED", "c'est ma place !!")
        s.set("PARKED")
        self.assertTrue(s.PARKED)
        self.assertEquals(s, "PARKED")

        self.assertFalse(s.READY)
        s.set("READY")
        self.assertTrue(s.READY)
        self.assertFalse(s.MOVING)

        self.assertEquals(s, "READY")
        self.assertEquals(s, "PARKED")

        print s.current_states()

        # bad name for a state
        self.assertRaises(ValueError, s.create_state, "A bad state")

    def test_init_state(self):
        self.assertEquals(AxisState(), "UNKNOWN")

    def test_desc(self):
        s = AxisState(("KAPUT", "auff"), "LIMNEG", "READY")
        self.assertTrue(s.READY)
        print s.current_states()
        self.assertEquals(s._state_desc["KAPUT"], "auff")
        self.assertEquals(s._state_desc["LIMNEG"], "Hardware low limit active")


if __name__ == '__main__':
    unittest.main()
