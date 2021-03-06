import gevent
from bliss.controllers.lima.roi import Roi as LimaRoi
from bliss.controllers.lima.roi import ArcRoi as LimaArcRoi
from bliss.controllers.lima.roi import RoiProfile as LimaLineRoi
from bliss.controllers.lima.lima_base import Lima
from bliss.controllers.mca.base import BaseMCA
from bliss.scanning.toolbox import ChainBuilder
from bliss.scanning.acquisition.timer import SoftwareTimerMaster
from bliss.scanning.acquisition.motor import LinearStepTriggerMaster
from bliss.scanning.acquisition.lima import LimaAcquisitionMaster
from bliss.scanning.chain import AcquisitionChain
from bliss.scanning.scan import Scan
from bliss.common.session import get_current_session
from bliss.controllers import simulation_diode
from bliss.controllers.mca import simulation as simulation_mca

# Not required but useful for manual testing:
from nexus_writer_service.session_api import *


def objects_of_type(*classes):
    ret = {}
    session = get_current_session()
    for name in session.object_names:
        try:
            obj = session.env_dict[name]
        except KeyError:
            continue
        if isinstance(obj, classes):
            ret[name] = obj
    return ret


# Add lima ROI's
rois = {
    "roi1": LimaRoi(0, 0, 100, 200),
    "roi2": LimaRoi(10, 20, 200, 500),
    "roi3": LimaArcRoi(500, 500, 10, 100, 0, 135),
}
for lima in objects_of_type(Lima).values():
    lima.roi_counters.update(rois)

rois = {"roi4": LimaLineRoi(100, 200, 100, 300)}
for lima in objects_of_type(Lima).values():
    lima.roi_profiles.update(rois)

rois = {"roi5": LimaRoi(340, 400, 100, 300), "roi6": LimaRoi(120, 200, 200, 150)}
for lima in objects_of_type(Lima).values():
    lima.roi_collection.update(rois)


# Add mca ROI's
rois = {"roi1": (500, 550), "roi2": (600, 650), "roi3": (700, 750)}
for mca in objects_of_type(BaseMCA).values():
    for name, roi in rois.items():
        mca.rois.set(name, *roi)


# Remove simulated overheads
simulation_diode.SimulationDiodeController._read_overhead = 0
simulation_diode.SimulationDiodeIntegrationController._read_overhead = 0
simulation_mca.SimulatedMCA._read_overhead = 0
simulation_mca.SimulatedMCA._init_time = 0
simulation_mca.SimulatedMCA._prepare_time = 0
simulation_mca.SimulatedMCA._cleanup_time = 0


def run_scan(scan, runasync=False, format="hdf5", frames=3):
    """
    :param bliss.scanning.scan.Scan scan:
    :param bool runasync: run in separate Greenlet
    :param str format: for lima
    :param int frames: for lima (frames per file)
    :returns Greenlet or None:
    """
    format = format.lower().replace(".", "")
    for node in scan.acq_chain.nodes_list:
        if isinstance(node.device, Lima):
            if format == "edf":
                ctrl_params = node.ctrl_params
                ctrl_params["saving_format"] = "EDF"
                ctrl_params["saving_frame_per_file"] = frames
                ctrl_params["saving_suffix"] = ".edf"
            else:
                ctrl_params = node.ctrl_params
                ctrl_params["saving_format"] = "HDF5"
                ctrl_params["saving_frame_per_file"] = frames
                ctrl_params["saving_suffix"] = ".h5"
    if runasync:
        return gevent.spawn(scan.run)
    else:
        return scan.run()


def aloopscan(mot, a, b, npoints1, expo1, detectors1, npoints2, expo2, detectors2):
    """Combination of a stepper and a loop scan
    """
    chain = AcquisitionChain()
    chain1 = _stepper_chain("subscan1", mot, a, b, npoints1, expo1, detectors1)
    chain2 = _timer_chain("subscan2", npoints2, expo2, detectors2)
    chain.append(chain1)
    chain.append(chain2)
    return Scan(chain, "aloopscan", save=True)


def limatimescan(lima, npoints1, expo1, detectors1, npoints2, expo2, detectors2):
    """Combination of two loop scans, one with lima as master
    """
    chain = AcquisitionChain()
    chain1 = _lima_chain("subscan1", lima, npoints1, expo1, detectors1)
    chain2 = _timer_chain("subscan2", npoints2, expo2, detectors2)
    chain.append(chain1)
    chain.append(chain2)
    return Scan(chain, "limatimescan", save=True)


def limact(lima, expo):
    """Simple lima image
    """
    chain = _lime_ct_chain(name, lima, expo)
    return Scan(chain, "limact", save=True)


def _timer_chain(name, npoints, expo, detectors):
    chain = AcquisitionChain()
    timer_master = SoftwareTimerMaster(expo, npoints=npoints, name=name + "tmr")
    timer_master.terminator = False
    scan_params = {"npoints": npoints, "count_time": expo, "type": "loopscan"}
    acq_params = {}
    _add_detectors(chain, timer_master, detectors, scan_params, acq_params)
    return chain


def _stepper_chain(name, mot, a, b, npoints, expo, detectors):
    chain = AcquisitionChain()
    timer_master = SoftwareTimerMaster(expo, npoints=npoints, name=name + "tmr")
    timer_master.terminator = False
    top_master = LinearStepTriggerMaster(npoints, mot, a, b, name=name + "ax")
    top_master.terminator = False
    scan_params = {
        "npoints": npoints,
        "start": [a],
        "stop": [b],
        "count_time": expo,
        "type": "ascan",
    }
    acq_params = {}
    _add_detectors(chain, timer_master, detectors, scan_params, acq_params)
    chain.add(top_master, timer_master)
    return chain


def _lima_chain(name, lima, npoints, expo, detectors):
    chain = AcquisitionChain()
    timer_master = SoftwareTimerMaster(expo, npoints=npoints, name=name + "tmr")
    timer_master.terminator = False
    lima_master = LimaAcquisitionMaster(lima, acq_nb_frames=1, acq_expo_time=expo)
    lima_master.terminator = False
    scan_params = {"npoints": npoints, "count_time": expo, "type": "loopscan"}
    acq_params = {}
    _add_detectors(chain, lima_master, detectors, scan_params, acq_params)
    chain.add(timer_master, lima_master)
    return chain


def _lime_ct_chain(name, lima, expo):
    chain = AcquisitionChain()
    scan_params = {"npoints": 1, "type": "loopscan"}
    acq_params = {
        "acq_nb_frames": 10,
        "acq_expo_time": expo / 10,
        "acq_mode": "SINGLE",
        "acq_trigger_mode": "INTERNAL_TRIGGER",
        "prepare_once": True,
        "start_once": False,
    }
    _add_detectors(chain, None, [lima.image], scan_params, acq_params)
    return chain


def _add_detectors(chain, master, detectors, scan_params, acq_params):
    builder = ChainBuilder(detectors)
    for top_node in builder.get_top_level_nodes():
        node_acq_params = top_node._get_default_chain_parameters(
            scan_params, acq_params
        )
        top_node.set_parameters(acq_params=node_acq_params, ctrl_params=None)
        for cnode in top_node.children:
            node_acq_params = cnode._get_default_chain_parameters(
                scan_params, acq_params
            )
            cnode.set_parameters(acq_params=node_acq_params, ctrl_params=None)
        if master is None:
            chain.add(top_node)
        else:
            chain.add(master, slave=top_node)
