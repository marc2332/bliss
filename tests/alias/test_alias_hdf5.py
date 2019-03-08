# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


from bliss.common import scans
from bliss.scanning.acquisition.motor import SoftwarePositionTriggerMaster
from bliss.scanning.acquisition.counter import SamplingCounterAcquisitionDevice
from bliss.scanning.scan import Scan, ScanSaving
from bliss.scanning.chain import AcquisitionChain


import h5py


def _h5dump(scan_file):
    # Get items
    items = []
    with h5py.File(scan_file, "r") as f:
        f.visititems(lambda *args: items.append(args))
        # Yield lines
        for name, obj in items:
            yield name
            for key, val in obj.attrs.items():
                yield "    %s: %s" % (key, val)


def h5dump(scan_file):
    return "\n".join(_h5dump(scan_file))


a2scan_dump = """{a2scan}
    NX_class: NXentry
{a2scan}/instrument
    NX_class: NXinstrument
{a2scan}/instrument/positioners
    NX_class: NXcollection
{a2scan}/instrument/positioners/robyy
{a2scan}/instrument/positioners/robzz
{a2scan}/instrument/positioners_dial
    NX_class: NXcollection
{a2scan}/instrument/positioners_dial/robyy
{a2scan}/instrument/positioners_dial/robzz
{a2scan}/measurement
    NX_class: NXcollection
{a2scan}/measurement/axis:robzz
    fullname: axis:robz
    alias: robzz
    has_alias: True
{a2scan}/measurement/dtime
    fullname: simu1:deadtime_det0
    alias: dtime
    has_alias: True
{a2scan}/measurement/lima_simulator:roi_counters:r2:sum
    fullname: lima_simulator:roi_counters:r2:sum
    alias: None
    has_alias: False
{a2scan}/measurement/myroi
    fullname: lima_simulator:roi_counters:r1:sum
    alias: myroi
    has_alias: True
{a2scan}/measurement/myroi3
    fullname: lima_simulator:roi_counters:r3:sum
    alias: myroi3
    has_alias: True
{a2scan}/measurement/robyy
    fullname: axis:roby
    alias: robyy
    has_alias: True
{a2scan}/measurement/simu1:spectrum_det0
    fullname: simu1:spectrum_det0
    alias: None
    has_alias: False
{a2scan}/measurement/timer:elapsed_time
    fullname: timer:elapsed_time
    alias: None
    has_alias: False
{a2scan}/start_time
{a2scan}/title
"""


def test_alias_hdf5_file_items(alias_session):

    env_dict, session = alias_session

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

    scan_dump = h5dump(s.writer.filename)

    ref_a2scan_dump = a2scan_dump.split("\n")

    i = -1
    in_positioner = False
    in_scan = False
    group_name = None
    for l in scan_dump.split("\n"):
        in_scan = l == s.node.name or l.startswith(s.node.name + "/") or in_scan
        if not in_scan:
            continue
        i += 1
        assert l == ref_a2scan_dump[i].format(a2scan=s.node.name)


con_scan_dump = """{scan}
    NX_class: NXentry
{scan}/instrument
    NX_class: NXinstrument
{scan}/instrument/positioners
    NX_class: NXcollection
{scan}/instrument/positioners/robyy
{scan}/instrument/positioners/robzz
{scan}/instrument/positioners_dial
    NX_class: NXcollection
{scan}/instrument/positioners_dial/robyy
{scan}/instrument/positioners_dial/robzz
{scan}/measurement
    NX_class: NXcollection
{scan}/measurement/myDiode
    fullname: diode:diode
    alias: myDiode
    has_alias: True
{scan}/measurement/robyy
    fullname: axis:roby
    alias: robyy
    has_alias: True
{scan}/start_time
{scan}/title
"""


def test_alias_hdf5_continuous_scan(alias_session):

    env_dict, session = alias_session

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

    scan_dump = h5dump(scan.writer.filename)

    ref_scan_dump = con_scan_dump.split("\n")

    i = -1
    in_positioner = False
    in_scan = False
    group_name = None
    for l in scan_dump.split("\n"):
        in_scan = l == scan.node.name or l.startswith(scan.node.name + "/") or in_scan
        if not in_scan:
            continue
        i += 1
        assert l == ref_scan_dump[i].format(scan=scan.node.name)
