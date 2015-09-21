# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import sys
import os
import gevent

sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..")))

from bliss.common.continuous_scan import AcquisitionChain
from bliss.common.continuous_scan import Scan
from bliss.common.data_manager import Container, ScanRecorder, get_node
from bliss.acquisition.test import TestAcquisitionDevice
from bliss.acquisition.test import TestAcquisitionMaster
try:
  from bliss.acquisition.motor import  SoftwarePositionTriggerMaster
  from bliss.acquisition.lima import LimaAcquisitionDevice
  import bliss 
  from PyTango.gevent import DeviceProxy
except ImportError:
  sys.excepthook(*sys.exc_info())

#from PyTango import DeviceProxy
from bliss.common.event import dispatcher
from bliss.config.conductor import client
try:
  #P201
  from bliss.acquisition.p201 import P201AcquisitionMaster,P201AcquisitionDevice
  from bliss.controllers.ct2 import P201, Clock
except ImportError:
  sys.excepthook(*sys.exc_info())

try:
  from bliss.data.writer import hdf5
except ImportError:
  sys.excepthook(*sys.exc_info())

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
  chain.add(mono_master,cam1_master)
  chain.add(cam1_master, cam2_dev)
  chain.add(timer_master, c0_dev)
  chain.add(timer_master, c1_dev)
  chain._tree.show()
  
  scan = Scan(chain, ScanRecorder())
  scan.prepare()
  scan.start()

def test2():
  chain = AcquisitionChain()
  musst_master = TestAcquisitionMaster("musst")
  p201_master = TestAcquisitionMaster("P201")
  p201_acq_dev = TestAcquisitionDevice("P201")
  chain.add(musst_master, p201_master)
  chain.add(p201_master, p201_acq_dev)
  chain._tree.show()
  
  scan = Scan(chain, ScanRecorder())
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
  scan = Scan(chain, ScanRecorder())
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
  emotion_master = SoftwarePositionTriggerMaster(m0, 5, 10, 10, time=5)
  lima_dev = DeviceProxy("id30a3/limaccd/simulation")
  params = { "acq_nb_frames": 10,
             "acq_expo_time": 3/10.0,
             "acq_trigger_mode": "INTERNAL_TRIGGER_MULTI" }
  lima_acq_dev = LimaAcquisitionDevice(lima_dev, **params)
  dispatcher.connect(cb, sender=lima_acq_dev) 
  chain.add(emotion_master, lima_acq_dev)
  scan = Scan(chain, ScanRecorder())
  scan.prepare()
  scan.start()
  m0.wait_move()
  print m0.velocity()==10 

def test_dm_lima():
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
  emotion_master = SoftwarePositionTriggerMaster(m0, 5, 10, 5, time=5)
  lima_dev = DeviceProxy("id30a3/limaccd/simulation")
  params = { "acq_nb_frames": 5,
             "acq_expo_time": 3/10.0,
             "acq_trigger_mode": "INTERNAL_TRIGGER_MULTI" }
  lima_acq_dev = LimaAcquisitionDevice(lima_dev, **params)
  chain.add(emotion_master, lima_acq_dev)

  toto = Container('toto')
  dm = ScanRecorder('test_acq', toto)

  scan = Scan(chain, dm)
  scan.prepare()
  scan.start()

def test_hdf5_lima():
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
  emotion_master = SoftwarePositionTriggerMaster(m0, 5, 10, 5, time=5)
  lima_dev = DeviceProxy("id30a3/limaccd/simulation")
  params = { "acq_nb_frames": 5,
             "acq_expo_time": 3/10.0,
             "acq_trigger_mode": "INTERNAL_TRIGGER_MULTI" }
  lima_acq_dev = LimaAcquisitionDevice(lima_dev, **params)
  chain.add(emotion_master, lima_acq_dev)

  file_organizer = Hdf5Organizer(root_path = '/tmp')
  toto = Container('toto',file_organizer = file_organizer)
  dm = ScanRecorder('test_acq', toto)

  scan = Scan(chain, dm)
  scan.prepare()
  scan.start()
    

def test_p201():
  #import logging; logging.basicConfig(level=logging.DEBUG)

  chain = AcquisitionChain()
  p201_device = P201()
  p201_device.request_exclusive_access()
  p201_device.disable_interrupts()
  p201_device.reset()
  p201_device.software_reset()
  p201_device.reset_FIFO_error_flags()
  p201_device.enable_interrupts(100)
  p201_device.set_clock(Clock.CLK_100_MHz)
  p201_master = P201AcquisitionMaster(p201_device,nb_points=100000,acq_expo_time=50e-6)
  p201_counters = P201AcquisitionDevice(p201_device,nb_points=100000,acq_expo_time=50e-6,
                                        channels={"c0":1,"c1":2,"timer":11})
  chain.add(p201_master,p201_counters)
  scan = Scan(chain, ScanRecorder())
  scan.prepare()
  scan.start()

def test_p201_hdf5():
  chain = AcquisitionChain()
  p201_device = P201()
  p201_device.request_exclusive_access()
  p201_device.disable_interrupts()
  p201_device.reset()
  p201_device.software_reset()
  p201_device.reset_FIFO_error_flags()
  p201_device.enable_interrupts(100)
  p201_device.set_clock(Clock.CLK_100_MHz)
  p201_master = P201AcquisitionMaster(p201_device,nb_points=10,acq_expo_time=50e-6)
  p201_counters = P201AcquisitionDevice(p201_device,nb_points=10,acq_expo_time=50e-6,
                                        channels={"c0":1,"c1":2,"timer":11})
  chain.add(p201_master,p201_counters)
  hdf5_writer = hdf5.Writer(root_path = '/tmp')
  toto = Container('toto')
  dm = ScanRecorder('test_acq', toto, writer=hdf5_writer)
  scan = Scan(chain, dm)
  scan.prepare()
  scan.start()


def test_emotion_p201():
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
  emotion_master = SoftwarePositionTriggerMaster(m0, 5, 10, 5, time=1)
  chain = AcquisitionChain()

  p201_device = P201()
  p201_device.request_exclusive_access()
  p201_device.disable_interrupts()
  p201_device.reset()
  p201_device.software_reset()
  p201_device.reset_FIFO_error_flags()
  p201_device.enable_interrupts(100)
  p201_device.set_clock(Clock.CLK_100_MHz)
  p201_master = P201AcquisitionMaster(p201_device,nb_points=10,acq_expo_time=1e-3)
  p201_counters = P201AcquisitionDevice(p201_device,nb_points=10,acq_expo_time=1e-3,
                                        channels={"c0":1,"c1":2})
  chain.add(emotion_master, p201_master)
  chain.add(p201_master,p201_counters)
  chain._tree.show()
  scan = Scan(chain, ScanRecorder())
  scan.prepare()
  scan.start()
  
  
def _walk_children(parent,index = 0) :
  print ' ' * index,parent.db_name(), parent.name(),client.get_cache(db=1).ttl(parent.db_name())
  for child in parent.children():
    _walk_children(child,index = index + 1)

def test_dm_client():
  # run previous test before!
  toto = get_node("toto")
  _walk_children(toto)

if __name__ == '__main__':
  #test()
  #test2()
  #test_emotion_master()
  #test_lima()
  #test_dm_lima()
  #test_dm_client()
  #test_p201()
  #test_emotion_p201()
  test_p201_hdf5()
