"""
This script can be run in the bliss test_session to 
produce some scan output also of more complicated scans
"""
from bliss.scanning.acquisition.counter import SamplingCounterAcquisitionDevice
from bliss.scanning.acquisition.lima import LimaAcquisitionMaster
from bliss.scanning.acquisition import timer
from bliss.scanning.chain import AcquisitionChain, AcquisitionChannel, AcquisitionMaster
from bliss.scanning.scan import Scan

import gevent

## additional imports from beacon:
lima_sim = config.get("lima_simulator")
mca_sim = config.get("simu1")

## a d2scan with simulation counter
scan1 = d2scan(roby, -.1, .1, robz, -.2, .2, 15, .1, sim_ct_gauss)
print(f"scan nr {scan1.scan_number}-> simple d2scan")

## a d2scan with lima simulator
scan1_b = loopscan(5, 0.1, lima_sim, save=True, run=False)
print(f"scan nr {scan1_b.scan_number}-> simple d2scan with lima simulator")
sim_params = scan1_b.acq_chain.nodes_list[1].parameters
sim_params["saving_format"] = "HDF5"
sim_params["saving_frame_per_file"] = 2
sim_params["saving_suffix"] = ".h5"
scan1_b.run()

## a ascan with mca
scan2 = ascan(roby, 0, 1, 10, .1, mca_sim)
print(f"scan nr {scan2.scan_number}-> ascan with mca")

## a scan with multiple top masters
chain = AcquisitionChain()
master1 = timer.SoftwareTimerMaster(1, npoints=2, name="timer1")
diode_device = SamplingCounterAcquisitionDevice(diode, count_time=1, npoints=2)
master2 = timer.SoftwareTimerMaster(0.001, npoints=50, name="timer2")
lima_master = LimaAcquisitionMaster(lima_sim, acq_nb_frames=1, acq_expo_time=0.001)
second_diode_device = SamplingCounterAcquisitionDevice(
    diode2, count_time=.1, npoints=50
)
chain.add(lima_master, second_diode_device)
chain.add(master2, lima_master)
chain.add(master1, diode_device)
master1.terminator = False
scan3 = Scan(chain, "test", save=True)
print(f"scan nr {scan3.scan_number}-> running scan with multiple top masters")
scan3.run()


## run several scans in parallel
def run3():
    s0 = loopscan(1, .1, diode4, wait=False, run=False)
    s1 = loopscan(5, .1, diode, wait=False, run=False)
    s2 = loopscan(3, .05, diode2, wait=False, run=False)
    print(
        f"running scans {s0.scan_number}, {s1.scan_number} and {s2.scan_number} in parallel"
    )
    g0 = gevent.spawn(s0.run)
    g1 = gevent.spawn(s1.run)
    g2 = gevent.spawn(s2.run)
    g0.join()
    g1.join()
    g2.join()


run3()

## test scan with unspecified number of points
try:
    scan4 = timescan(.05, diode2, run=False)
    print(
        f"scan nr {scan4.scan_number} -> running timescan that will be killed automatically after .5 s (there will be an error message bellow!)"
    )
    scan_task = gevent.spawn(scan4.run)
    gevent.sleep(.53)
    scan_task.kill()
except:
    pass
