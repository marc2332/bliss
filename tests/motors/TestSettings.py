import tempfile
import xml.etree.cElementTree as ElementTree
import unittest
import gevent
import time
import sys
import os

sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..")))

import bliss

config_xml = """<config>
  <controller class="mockup" name="test">
    <host value="mydummyhost1"/>
    <port value="5000"/>
    <axis name="robz">
      <!-- degrees per second -->
      <velocity value="100"/>
    </axis>
  </controller>
  <controller class="mockup">
    <host value="mydummyhost2"/>
    <port value="5000"/>
    <axis name="roby">
      <backlash value="2"/>
      <step_size value="10"/>
      <velocity  value="2500"/>
    </axis>
  </controller>
</config>
"""

class TestSettings(unittest.TestCase):

    def setUp(self):
        self.cfg_file = tempfile.NamedTemporaryFile(delete=False)
        self.cfg_file.write(config_xml)
        self.cfg_file.close()
        bliss.load_cfg(self.cfg_file.name)

    def test_setting_1set(self):
        robz = bliss.get_axis("robz")
        robz.settings.set("init_count", 10)
        self.assertEquals(robz.settings.get("init_count"), 10)
        time.sleep(1) #this is to "synchronize" with the settings writing thread
        config_tree = ElementTree.parse(self.cfg_file.name)
        for axis_node in config_tree.findall("axis"):
            if axis_node.get("name") == "robz":
                settings_node = axis_node.find("settings")
                self.assertNotEquals(settings_node, None)
                init_counts_node = settings_node.find("init_count")
                init_counts_value = int(init_counts_node.get('value'))
                self.assertEquals(init_counts_value, 10)
                break
        global config_xml
        with open(self.cfg_file.name, 'r') as cfg_file:
            config_xml = cfg_file.read()
        print config_xml

    def test_setting_get(self):
        robz = bliss.get_axis("robz")
        self.assertEquals(robz.settings.get("init_count"), 10)

    def tearDown(self):
        os.unlink(self.cfg_file.name)

if __name__ == '__main__':
    unittest.main()
