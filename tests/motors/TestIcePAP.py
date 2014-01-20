import unittest
import sys
import os
import optparse




"""
Bliss generic library
"""
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import bliss




"""
IcePAP specific library
"""
sys.path.insert(0, os.path.abspath("/segfs/bliss/source/hardware/IcePAP/client/python/"))
import icepap.lib




"""
Example of Bliss configuration
"""
config_xml = """
<config>
  <controller class="IcePAP" name="test">
    <host value="%s"/>
    <libdebug value="1"/>
    <axis name="mymot">
      <address value="%s"/>
      <step_size value="2000"/>
    </axis>
  </controller>
</config>
"""



"""
Global resources, yes, I know it's bad
"""
hostname = ""
address  = ""



"""
UnitTest list of tests
"""
class TestIcePAPController(unittest.TestCase):
  global hostname
  global address

  # called for each test
  def setUp(self):
    bliss.load_cfg_fromstring(config_xml%(hostname, address))

  def test_get_axis(self):
    mymot = bliss.get_axis("mymot")
    self.assertTrue(mymot)

  def test_get_position(self):
    mymot = bliss.get_axis("mymot")
    print "\"mymot\" position :", mymot.position()

  """
  def test_get_id(self):
    mymot = bliss.get_axis("mymot")
    print "\"mymot\" ID:", mymot.controller._get_identifier()
  """


#     def test_axis_move(self):
#         mymot = bliss.get_axis("mymot")
#         self.assertEqual(mymot.state(), "READY")
#         move_greenlet=mymot.move(10, wait=False)
#         self.assertEqual(mymot.state(), "MOVING")
#         move_greenlet.join()
#         self.assertEqual(mymot.state(), "READY")



"""
Main entry point
"""
if __name__ == '__main__':

  # Get arguments
  usage  = "Usage: %prog [options] hostname mot_address"
  parser = optparse.OptionParser(usage)
  argv   = sys.argv
  (settings, args) = parser.parse_args(argv)

  # Minimum check on arguements
  if len(args) <= 2:
    parser.error("Missing mandatory IcePAP hostname and motor address")
    sys.exit(-1)

  # Mandatory argument is the IcePAP hostname
  hostname = args[1]
  address  = args[2]

  # Avoid interaction of our arguments with unittest class
  del sys.argv[1:]

  # Launch the tests sequence
  unittest.main()


'''
Interactive test :

load_cfg_fromstring("""<config>
  <controller class="IcePAP" name="testid16">
    <host value="e753id16ni-mlm"/>
    <axis name="mymot">
    </axis>
  </controller>
</config>
""")

a=get_axis("mymot")

print a.controller.sock.write_readline("IDN?\n")
print a.controller._get_infos()



'''
