import sys
import os

sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..")))

from bliss.common.continuous_scan import AcquisitionChain
from bliss.common.continuous_scan import Scan
from bliss.common.data_manager import DataManager
from bliss.acquisition.test import TestAcquisitionDevice
from bliss.acquisition.test import TestAcquisitionMaster
from bliss.acquisition.motor import  SoftwarePositionTriggerMaster
from bliss.acquisition.lima import LimaAcquisitionDevice
import bliss 
#from PyTango.gevent import DeviceProxy
from PyTango import DeviceProxy
from louie import dispatcher
import gevent

def test():
  chain = AcquisitionChain()
  mono_master = TestAcquisitionMaster("mono")
  cam1_dev = TestAcquisitionDevice("cam1")
  cam1_master = TestAcquisitionMaster("cam1")
  cam2_dev = TestAcquisitionDevice("cam2")
  timer_master = TestAcquisitionMaster("timer")
  c0_dev = TestAcquisitionDevice("c0")
  c1_dev = TestAcquisitionDevice("c1")
  chain.add(mono_master, cam1_dev)
  chain.add(cam1_master, cam2_dev)
  chain.add(timer_master, c0_dev)
  chain.add(timer_master, c1_dev)
  scan = Scan(DataManager())
  scan.set_acquisition_chain(chain)
  scan.prepare()
  scan.start()

def test_emotion_master():
  config_xml = """
<config>
  <controller class="mockup">
    <axis name="m0">
      <steps_per_unit value="10000"/>
      <!-- degrees per second -->
      <velocity value="10"/>
      <acceleration value="100"/>
    </axis>
  </controller>
</config>"""

  emotion.load_cfg_fromstring(config_xml)
  m0 = emotion.get_axis("m0")
 
  chain = AcquisitionChain()
  emotion_master = SoftwarePositionTriggerMaster(m0, 5, 10, 7)
  test_acq_dev = TestAcquisitionDevice("c0", 0)
  chain.add(emotion_master, test_acq_dev)
  scan = Scan(DataManager())
  scan.set_acquisition_chain(chain)
  scan.prepare()
  scan.start()

def test_lima():
  config_xml = """
<config>
  <controller class="mockup">
    <axis name="m0">
      <steps_per_unit value="10000"/>
      <!-- degrees per second -->
      <velocity value="10"/>
      <acceleration value="100"/>
    </axis>
  </controller>
</config>"""

  emotion.load_cfg_fromstring(config_xml)
  m0 = emotion.get_axis("m0")

  def cb(*args, **kwargs):
    print args, kwargs

  chain = AcquisitionChain()
  emotion_master = SoftwarePositionTriggerMaster(m0, 5, 10, 7, time=5)
  lima_dev = DeviceProxy("id30a3/limaccd/simulation")
  params = { "acq_nb_frames": 7,
             "acq_expo_time": 4/7.0,
             "acq_trigger_mode": "INTERNAL_TRIGGER_MULTI" }
  lima_acq_dev = LimaAcquisitionDevice(lima_dev, **params)
  dispatcher.connect(cb, sender=lima_acq_dev) 
  chain.add(emotion_master, lima_acq_dev)
  scan = Scan(DataManager())
  scan.set_acquisition_chain(chain)
  scan.prepare()
  scan.start()
  m0.wait_move()
  print m0.velocity()==10 
  gevent.sleep(5)


if __name__ == '__main__':
  #test()
  #test_emotion_master()
  test_lima()
