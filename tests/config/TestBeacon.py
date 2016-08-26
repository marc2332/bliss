"""Beacon test module

Database structure:

.
|-- __init__.yml
`-- oh
    |-- bpms.yml
    |-- __init__.yml
    |-- motors
    |   `-- @iceid301
    |       |-- axes
    |       |   |-- m0.yml
    |       |   `-- m1.yml
    |       `-- __init__.yml
    |-- transfocator.yml
    `-- wagos.yml
"""
import os
import unittest
import sys

sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            os.path.pardir, os.path.pardir)))

from bliss.config import static

test_db = [('__init__.yml', 'synchrotron: ESRF\nbeamline: id30b\n'),
 ('oh/wagos.yml',
  '-\n    name: wcid30q\n    class: wago\n    controller_ip: 160.103.50.53\n    mapping:\n        -\n            type: 750-517\n            logical_names: _,_\n        -\n            type: 750-469\n            logical_names: th_311_in, th_311_out\n        -\n            type: 750-469\n            logical_names: th_111_in, th_111_out\n        -\n            type: 750-469\n            logical_names: th_mask, _\n'),
 ('oh/transfocator.yml',
  'name: tfmad\nclass: transfocator\ncontroller_ip: 160.103.50.57\nlenses: 7\npinhole: 2\n'),
 ('oh/__init__.yml', 'plugin: bliss\n'),
 ('oh/bpms.yml',
  '-\n    name: wbvg\n    class: tango_bpm\n    uri: id30/id30b/wbvg\n-\n    name: mbv1\n    class: tango_bpm\n    uri: id30/id30b/mbv1\n\n'),
 ('oh/motors/@iceid301/__init__.yml',
  'controller: icepap\nhost: iceid301\nport: 5000\n'),
 ('oh/motors/@iceid301/axes/m1.yml',
  'name: m1\nchannel: 2\nvelocity: 1200\nacceleration: 6\n'),
 ('oh/motors/@iceid301/axes/m0.yml',
  'name: m0\nchannel: 1\nvelocity: 1000\nacceleration: 4\n')]

class TestBeacon(unittest.TestCase):
    def setUp(self):
        self.cfg = static.Config(test_db)

    def testRootNode(self):
        root_node = self.cfg.root
        self.assertEquals(root_node.parent, None)

    def testParent(self):
        root_node = self.cfg.root
        oh_node = root_node["oh"]
        self.assertEquals(oh_node.parent, root_node)
        motors_node = oh_node["motors"]
        self.assertEquals(motors_node.parent, oh_node)
        #axes_node = motors_node["axes"]
        #self.assertEquals(axes_node.parent, motors_node)
        
        wbvg_node = self.cfg.get_config("wbvg")
        self.assertEquals(wbvg_node.parent, oh_node)
        #m0_node = self.cfg.get_config("m0")
        #self.assertEquals(m0_node.parent, axes_node)

    def testFilename(self):
        root_node = self.cfg.root
        self.assertEquals(root_node.filename, "__init__.yml")
        self.assertEquals(root_node["oh"].filename, "oh/__init__.yml")
        self.assertEquals(self.cfg.get_config("wcid30q").filename, "oh/wagos.yml")
        self.assertEquals(self.cfg.get_config("wbvg").filename, "oh/bpms.yml")
        self.assertEquals(self.cfg.get_config("mbv1").filename, "oh/bpms.yml")
        self.assertEquals(self.cfg.get_config("tfmad").filename, "oh/transfocator.yml")

    def testFilenameWithArobase(self):
        root_node = self.cfg.root
        self.assertEquals(root_node["oh"]["motors"].filename, "oh/motors/@iceid301/__init__.yml")
        self.assertEquals(self.cfg.get_config("m0").filename, "oh/motors/@iceid301/axes/m0.yml")

    def testPlugin(self):
        self.assertEquals(self.cfg.root["oh"].plugin, "bliss")
        self.assertEquals(self.cfg.get_config("wcid30q").plugin, "bliss")
        self.assertEquals(self.cfg.get_config("wbvg").plugin, "bliss")
        self.assertEquals(self.cfg.get_config("mbv1").plugin, "bliss")
        self.assertEquals(self.cfg.get_config("tfmad").plugin, "bliss")
        self.assertEquals(self.cfg.get_config("m0").plugin, "bliss")
        self.assertEquals(self.cfg.get_config("m1").plugin, "bliss")

    def testChildren(self):
        root_node = self.cfg.root
        self.assertEquals(len(root_node["oh"].children), 4)

    def testChildrenWithArobase(self):
        root_node = self.cfg.root
        self.assertEquals(len(root_node["oh"]["motors"]["axes"]), 2)
        self.assertEquals(root_node["oh"]["motors"]["controller"], "icepap")

    def test__init__(self):
        root_node = self.cfg.root
        self.assertEquals(root_node["beamline"], "id30b")
        self.assertEquals(root_node["oh"]["plugin"], "bliss")

    def test__init__arobase(self):
        root_node = self.cfg.root
        self.assertEquals(root_node["oh"]["motors"]["controller"], "icepap")

    def testGetConfig(self):
        self.assertEquals(self.cfg.get_config("wcid30q").get("class"), "wago")
        self.assertEquals(self.cfg.get_config("mbv1").get("class"), "tango_bpm")
        self.assertEquals(self.cfg.get_config("wbvg").get("uri"), "id30/id30b/wbvg")
        self.assertEquals(self.cfg.get_config("tfmad").get("class"), "transfocator")
        self.assertEquals(self.cfg.get_config("tfmad").get("pinhole"), 2)
        self.assertEquals(self.cfg.get_config("m0").get("velocity"), 1000)
        self.assertEquals(self.cfg.get_config("m1").get("velocity"), 1200)

    def testGetControllerFromAxisForEmotion(self):
        """Code from emotion:
        
        def create_objects_from_config_node(node):
            ...
            controller_config = node.get_parent()

            controller_class_name = controller_config.get('class')
            ...
            for axis_config in controller_config.get("axes"):
               axis_name = axis_config.get("name")
               ...
        """
        controller_config = self.cfg.get_config("m0").parent
        self.assertEquals(controller_config.get("controller"), "icepap")
        self.assertEquals(len(list(controller_config.get("axes"))), 2)
    
if __name__ == '__main__':
    unittest.main()
