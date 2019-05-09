# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


from bliss.common import scans
from bliss.scanning.acquisition.motor import SoftwarePositionTriggerMaster
from bliss.scanning.acquisition.counter import SamplingCounterAcquisitionDevice
from bliss.scanning.scan import Scan, ScanSaving
from bliss.scanning.chain import AcquisitionChain


import h5py


def h5dict(scan_file):
    with h5py.File(scan_file, "r") as f:
        items = []
        f.visititems(lambda *args: items.append(args))
        return {
            name: {key: val for key, val in obj.attrs.items()} for name, obj in items
        }


def test_alias_hdf5_file_items(alias_session, scan_tmpdir):

    env_dict, session = alias_session

    # put scan file in a tmp directory
    env_dict["SCAN_SAVING"].base_path = str(scan_tmpdir)

    s = scans.a2scan(
        env_dict["robyy"],
        0,
        5,
        env_dict["robzz"],
        0,
        5,
        5,
        0.001,
        env_dict["simu1"].counters.spectrum_det0,
        env_dict["dtime"],
        env_dict["lima_simulator"].roi_counters.r1.sum,
        env_dict["lima_simulator"].roi_counters.r2.sum,
        env_dict["myroi3"],
        save=True,
        return_scan=True,
    )
    a2scan = s.node.name
    expected_dict = {
        f"{a2scan}": {"NX_class": "NXentry"},
        f"{a2scan}/instrument": {"NX_class": "NXinstrument"},
        f"{a2scan}/instrument/positioners": {"NX_class": "NXcollection"},
        f"{a2scan}/instrument/positioners/robyy": {},
        f"{a2scan}/instrument/positioners/robzz": {},
        f"{a2scan}/instrument/positioners_dial": {"NX_class": "NXcollection"},
        f"{a2scan}/instrument/positioners_dial/robyy": {},
        f"{a2scan}/instrument/positioners_dial/robzz": {},
        f"{a2scan}/measurement": {"NX_class": "NXcollection"},
        f"{a2scan}/measurement/axis:robzz": {
            "alias": "robzz",
            "fullname": "axis:robz",
            "has_alias": True,
        },
        f"{a2scan}/measurement/dtime": {
            "alias": "dtime",
            "fullname": "simu1:deadtime_det0",
            "has_alias": True,
        },
        f"{a2scan}/measurement/lima_simulator:roi_counters:r2:sum": {
            "alias": "None",
            "fullname": "lima_simulator:roi_counters:r2:sum",
            "has_alias": False,
        },
        f"{a2scan}/measurement/myroi": {
            "alias": "myroi",
            "fullname": "lima_simulator:roi_counters:r1:sum",
            "has_alias": True,
        },
        f"{a2scan}/measurement/myroi3": {
            "alias": "myroi3",
            "fullname": "lima_simulator:roi_counters:r3:sum",
            "has_alias": True,
        },
        f"{a2scan}/measurement/robyy": {
            "alias": "robyy",
            "fullname": "axis:roby",
            "has_alias": True,
        },
        f"{a2scan}/measurement/simu1:spectrum_det0": {
            "alias": "None",
            "fullname": "simu1:spectrum_det0",
            "has_alias": False,
        },
        f"{a2scan}/measurement/timer:elapsed_time": {
            "alias": "None",
            "fullname": "timer:elapsed_time",
            "has_alias": False,
        },
    }

    scan_dict = h5dict(s.writer.filename)
    for key, val in expected_dict.items():
        assert key in scan_dict
        assert val.items() <= scan_dict[key].items()


def test_alias_hdf5_continuous_scan(alias_session, scan_tmpdir):

    env_dict, session = alias_session

    # put scan file in a tmp directory
    env_dict["SCAN_SAVING"].base_path = str(scan_tmpdir)

    diode = session.config.get("diode")
    diode.set_alias("myDiode")

    robyy = env_dict["robyy"]
    counter = env_dict["myDiode"]
    master = SoftwarePositionTriggerMaster(robyy, 0, 1, 10, time=1)
    end_pos = master._calculate_undershoot(1, end=True)
    acq_dev = SamplingCounterAcquisitionDevice(counter, 0.01, npoints=10)
    chain = AcquisitionChain()
    chain.add(master, acq_dev)

    scan = Scan(chain)
    scan.run()

    scan_dict = h5dict(scan.writer.filename)
    scan_name = scan.node.name
    expected_dict = {
        f"{scan_name}": {"NX_class": "NXentry"},
        f"{scan_name}/instrument": {"NX_class": "NXinstrument"},
        f"{scan_name}/instrument/positioners": {"NX_class": "NXcollection"},
        f"{scan_name}/instrument/positioners/robyy": {},
        f"{scan_name}/instrument/positioners/robzz": {},
        f"{scan_name}/instrument/positioners_dial": {"NX_class": "NXcollection"},
        f"{scan_name}/instrument/positioners_dial/robyy": {},
        f"{scan_name}/instrument/positioners_dial/robzz": {},
        f"{scan_name}/measurement": {"NX_class": "NXcollection"},
        f"{scan_name}/measurement/myDiode": {
            "alias": "myDiode",
            "fullname": "diode:diode",
            "has_alias": True,
        },
        f"{scan_name}/measurement/robyy": {
            "alias": "robyy",
            "fullname": "axis:roby",
            "has_alias": True,
        },
    }
    for key, val in expected_dict.items():
        assert key in scan_dict
        assert val.items() <= scan_dict[key].items()
