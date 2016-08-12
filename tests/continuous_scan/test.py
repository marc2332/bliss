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
            os.path.pardir, os.path.pardir)))

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
from bliss.config.static import get_config as beacon_get_config

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
try:
  from bliss.controllers.musst.base import musst
except:
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
  p201_device.set_interrupts()
  p201_device.reset()
  p201_device.software_reset()
  p201_device.reset_FIFO_error_flags()
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

def test_lima_basler_musst():
  config = beacon_get_config()
  m0 = config.get("bcumot2")
  m0_res = m0.steps_per_unit
  m0_acc = m0.acceleration()
  m0_vel = m0.velocity()
  print "m0_acc: %s, m0_vel: %s" % (m0_acc, m0_vel)
  acc_steps = m0_vel ** 2 / (2 * m0_acc) + 1.0 / m0_res
  print "acc_steps: %s" % (acc_steps)

  musst_config = config.get("musst")
  musst_dev = musst('musst', musst_config)

  def print_musst_state():
    state_val = musst_dev.STATE
    state_name = [s for s, v in musst_dev._string2state.items() 
                  if v == state_val][0]
    print "MUSST state: %s [%s]" % (state_name, state_val)

  print_musst_state()
  if musst_dev.STATE == musst_dev.RUN_STATE:
    print "Aborting!"
    musst_dev.ABORT
    while musst_dev.STATE != musst_dev.IDLE_STATE:
      pass
    print_musst_state()

  if musst_dev.get_variable_info('NPAT') == 'ERROR':
    musst_dev.CLEAR
    prog_name = 'id15aeromultiwin.mprg'
    print "Uploading MUSST program: %s ..." % prog_name
    this_dir = os.path.dirname(sys.argv[0])
    musst_prog_fname = os.path.join(this_dir, prog_name)
    musst_prog = ''.join(open(musst_prog_fname).readlines())
    musst_dev.upload_program(musst_prog)
    print " Done!"
  
  ch1 = musst_dev.get_channel(1)
  def musst_pos():
    return float(ch1.value) / m0_res
  def print_pos():
    print m0.position(), musst_pos()

  start_pos = 0
  final_pos = 360
  nb_pts = 100

  point_size = abs(float(final_pos - start_pos) / nb_pts)
  move_dir = 1 if start_pos < final_pos else -1

  patw = point_size * m0_res
  patwi = int(patw)
  patwf = int((patw - patwi) * 2 ** 31)

  scan_start = start_pos - acc_steps * move_dir

  if m0.position() != scan_start:
    m0.move(scan_start)
  if musst_pos() != scan_start:
    ch1.value = scan_start * m0_res
  print_pos()

  musst_dev.VARINIT
  vals = {'SCANCH': 1,
          'E1': start_pos * m0_res,
          'DIR': move_dir, 
          'PATW': patwi, 
          'PATWF': patwf, 
          'NPAT': nb_pts, 
          'UPW': patw / 4, 
          'DOWNW': patw / 2, 
          'NPULSE': 1}

  for varname, val in vals.items():
    print "Setting: %s=%s" % (varname, val)
    musst_dev.set_variable(varname, val)
    print '%s=%s' % (varname, musst_dev.get_variable(varname))

  musst_dev.run()
  m0.move(final_pos + acc_steps * move_dir)
  print_pos()
  while musst_dev.STATE != musst_dev.IDLE_STATE:
    pass
  print_musst_state()

  print "retcode: %s" % musst_dev.RETCODE

def test_lima_basler():
  config = beacon_get_config()
  m0 = config.get("bcumot2")
  m0.velocity(360)
  m0.acceleration(720)

  chain = AcquisitionChain()
  nb_points = 4
  emotion_master = SoftwarePositionTriggerMaster(m0, 0, 360, nb_points, time=1)
  tango_host = "lid00limax:20000"
  lima_dev = DeviceProxy("//%s/id00/limaccds/basler_bcu" % tango_host)
  params = { "acq_nb_frames": nb_points,
             "acq_expo_time": 10e-3,
             "acq_trigger_mode": "INTERNAL_TRIGGER_MULTI" }
  lima_acq_dev = LimaAcquisitionDevice(lima_dev, **params)
  chain.add(emotion_master, lima_acq_dev)

  hdf5_writer = hdf5.Writer(root_path = '/tmp')
  toto = Container('test_lima_basler')
  dm = ScanRecorder('test_acq', toto,writer=hdf5_writer)

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
  p201_device.set_interrupts()
  p201_device.reset()
  p201_device.software_reset()
  p201_device.reset_FIFO_error_flags()
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
  #test_p201_hdf5()
  test_lima_basler()
