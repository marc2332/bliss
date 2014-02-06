import unittest
import time
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import bliss
from bliss.common.axis import Axis

config_xml = """
<config>
  <controller class="mockup">
    <host value="mydummyhost2"/>
    <port value="5000"/>
    <axis name="m0">
      <velocity value="500"/>
    </axis>
    <axis name="s1f">
      <velocity value="500"/>
      <step_size value="10"/>
    </axis>
    <axis name="s1b">
      <velocity value="500"/>
      <step_size value="10"/>
    </axis>
    <axis name="s1u">
      <velocity value="500"/>
      <step_size value="10"/>
    </axis>
    <axis name="s1d">
      <velocity value="500"/>
      <step_size value="10"/>
    </axis>
  </controller>
  <controller class="slits" name="test">
    <axis name="s1f" tags="real front"/>
    <axis name="s1b" tags="real back"/>
    <axis name="s1u" tags="real up"/>
    <axis name="s1d" tags="real down"/>
    <axis name="s1vg" tags="vgap"/>
    <axis name="s1vo" tags="voffset"/>
    <axis name="s1hg" tags="hgap"/>
    <axis name="s1ho" tags="hoffset"/>
  </controller>
</config>
"""

class TestSlits(unittest.TestCase):
    def setUp(self):
        bliss.load_cfg_fromstring(config_xml)

    def testTags(self):
        controller = bliss.config.motors["test"]["object"]
        for tag, axis_name in {"front":"s1f",
                               "back": "s1b",
                               "up": "s1u",
                               "down": "s1d",
                               "hgap": "s1hg",
                               "hoffset": "s1ho",
                               "vgap": "s1vg",
                               "voffset": "s1vo" }.iteritems():
          self.assertEquals(controller._tagged[tag], [axis_name])
                   
    def testRealTags(self):
        controller = bliss.config.motors["test"]["object"]
        self.assertEquals(controller._tagged["real"], ["s1f", "s1b", "s1u", "s1d"])

    def testRealsList(self):
        controller = bliss.config.motors["test"]["object"]
        self.assertEquals(len(controller.reals), 4)
        self.assertTrue(all([isinstance(x, Axis) for x in controller.reals]))

    def testPseudosList(self):
        controller = bliss.config.motors["test"]["object"]
        self.assertEquals(len(controller.pseudos), 4)
        self.assertTrue(all([isinstance(x, Axis) for x in controller.pseudos]))

    def testPseudoAxisAreExported(self):
        self.assertTrue(all((bliss.get_axis("s1vg"), 
                             bliss.get_axis("s1vo"),
                             bliss.get_axis("s1hg"),
                             bliss.get_axis("s1ho"))))

    def testRealAxisIsRightObject(self):
        s1f = bliss.get_axis('s1f')
        m0 = bliss.get_axis('m0')
        self.assertEquals(s1f.controller, m0.controller)
        controller = bliss.config.motors["test"]["object"]
        self.assertEquals(s1f, controller.axes['s1f'])

    def testPseudoAxisState(self):
        self.testPseudoAxisAreExported()
        controller = bliss.config.motors["test"]["object"]
        self.assertTrue(all([axis.state()=='READY' for axis in controller.pseudos]))
       
    def testPseudoAxisPosition(self):
        self.testPseudoAxisAreExported()
        controller = bliss.config.motors["test"]["object"]
        s1f = bliss.get_axis("s1f")
        s1b = bliss.get_axis("s1b")
        s1u = bliss.get_axis("s1u")
        s1d = bliss.get_axis("s1d")
        s1f.position(0)
        s1b.position(1)
        s1u.position(0)
        s1d.position(1)
        self.assertEquals(bliss.get_axis("s1vg").position(), 1)
        self.assertEquals(bliss.get_axis("s1vo").position(), -0.5)
        self.assertEquals(bliss.get_axis("s1hg").position(), 1)
        self.assertEquals(bliss.get_axis("s1ho").position(), 0.5)



if __name__ == '__main__':
    unittest.main()
