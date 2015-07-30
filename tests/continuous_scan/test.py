from bliss.common.continuous_scan import AcquisitionChain
from bliss.common.continuous_scan import Scan
from bliss.common.data_manager import DataManager
from bliss.acquisition.test import TestAcquisitionDevice
from bliss.acquisition.test import TestAcquisitionMaster

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


if __name__ == '__main__':
  test()
