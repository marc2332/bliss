# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


from bliss.common import scans
from bliss.scanning.acquisition.motor import SoftwarePositionTriggerMaster
from bliss.scanning.acquisition.counter import SamplingCounterAcquisitionSlave
from bliss.scanning.scan import Scan, ScanSaving
from bliss.scanning.chain import AcquisitionChain
from bliss import global_map

import h5py


def h5dict(scan_file):
    with h5py.File(scan_file, mode="r") as f:
        items = []
        f.visititems(lambda *args: items.append(args))
        return {
            name: {key: val for key, val in obj.attrs.items()} for name, obj in items
        }


def test_alias_hdf5_file_items(alias_session):
    env_dict = alias_session.env_dict

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
        env_dict["myroi"],
        env_dict["lima_simulator"].counters.r2_sum,
        env_dict["myroi3"],
        save=True,
        return_scan=True,
    )
    a2scan = s.node.name
    expected_dict = {
        f"{a2scan}": {"NX_class": "NXentry"},
        f"{a2scan}/instrument": {"NX_class": "NXinstrument"},
        f"{a2scan}/instrument/chain_meta": {"NX_class": "NXcollection"},
        f"{a2scan}/instrument/positioners": {"NX_class": "NXcollection"},
        f"{a2scan}/instrument/positioners/robyy": {},
        f"{a2scan}/instrument/positioners/robzz": {},
        f"{a2scan}/instrument/positioners_dial": {"NX_class": "NXcollection"},
        f"{a2scan}/instrument/positioners_dial/robyy": {},
        f"{a2scan}/instrument/positioners_dial/robzz": {},
        f"{a2scan}/measurement": {"NX_class": "NXcollection"},
        f"{a2scan}/measurement/axis:robzz": {},
        f"{a2scan}/measurement/simu1:dtime": {},
        f"{a2scan}/measurement/lima_simulator:roi_counters:r2_sum": {},
        f"{a2scan}/measurement/lima_simulator:roi_counters:myroi": {},
        f"{a2scan}/measurement/lima_simulator:roi_counters:myroi3": {},
        f"{a2scan}/measurement/axis:robyy": {},
        f"{a2scan}/measurement/simu1:spectrum_det0": {},
        f"{a2scan}/measurement/timer:elapsed_time": {},
    }

    scan_dict = h5dict(s.writer.filename)
    for key, val in expected_dict.items():
        assert key in scan_dict
        assert val.items() <= scan_dict[key].items()


def test_alias_hdf5_continuous_scan(alias_session):
    env_dict = alias_session.env_dict

    diode = alias_session.config.get("diode")
    global_map.aliases.add("myDiode", diode)

    robyy = env_dict["robyy"]
    counter = env_dict["myDiode"]
    master = SoftwarePositionTriggerMaster(robyy, 0, 1, 10, time=1)
    end_pos = master._calculate_undershoot(1, end=True)
    acq_dev = SamplingCounterAcquisitionSlave(counter, count_time=0.01, npoints=10)
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
        f"{scan_name}/measurement/simulation_diode_sampling_controller:myDiode": {},
        f"{scan_name}/measurement/axis:robyy": {},
    }
    for key, val in expected_dict.items():
        assert key in scan_dict
        assert val.items() <= scan_dict[key].items()
