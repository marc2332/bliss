# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import gevent
import pprint
import collections.abc
import numpy
import h5py

from bliss.common import scans
from silx.io.dictdump import h5todict
from bliss.scanning.acquisition.counter import SamplingCounterAcquisitionDevice
from bliss.scanning.acquisition.lima import LimaAcquisitionMaster
from bliss.scanning.acquisition import timer
from bliss.scanning.chain import AcquisitionChain, AcquisitionChannel, AcquisitionMaster
from bliss.scanning.scan import Scan

from scripts.external_saving_example.external_saving_example import (
    listen_scans_of_session
)

# ~ def h5_scan_name(scan_info):
# ~ return str(scan_info["scan_nb"]) + "_" + scan_info["type"]


## maybe this could be useful for other tests to ... move to conftest.py?
## deep_compare is to be used to compare a dict_dump of e.g. an hdf5 file to
## a scan output
def deep_compare(d, u):
    """using logic of deep update used here to compare two dicts 
    """
    stack = [(d, u)]
    while stack:
        d, u = stack.pop(0)
        assert len(d) == len(u)

        for k, v in u.items():
            assert k in d
            if not isinstance(v, collections.abc.Mapping):
                if isinstance(v, numpy.ndarray) and v.size > 1:
                    assert d[k].shape == v.shape
                    d[k].dtype == v.dtype
                    if d[k].dtype != numpy.object:
                        assert all(
                            numpy.isnan(d[k].flatten()) == numpy.isnan(v.flatten())
                        )
                        mask = numpy.logical_not(numpy.isnan(v.flatten()))
                        assert all((d[k].flatten() == v.flatten())[mask])
                    else:
                        assert all(d[k].flatten() == v.flatten())
                else:
                    assert d[k] == v
            else:
                stack.append((d[k], v))


@pytest.fixture
def alias_session_scans_listener(alias_session, scan_tmpdir):

    env_dict = alias_session.env_dict

    # put scan file in a tmp directory
    alias_session.scan_saving.base_path = str(scan_tmpdir)

    lima_sim = env_dict["lima_simulator"]

    # this scan is only to set up the file path in pytest
    s = scans.ascan(env_dict["robyy"], 0, 1, 3, .1, lima_sim)

    scan_stack = {}
    g = gevent.spawn(listen_scans_of_session, "test_alias", scan_stack=scan_stack)

    yield scan_stack

    g.kill()


def test_external_hdf5_writer(
    alias_session_scans_listener, alias_session, dummy_acq_device
):

    env_dict = alias_session.env_dict
    scan_stack = alias_session_scans_listener

    lima_sim = env_dict["lima_simulator"]

    ## a simple scan
    s1 = scans.ascan(env_dict["robyy"], 0, 1, 3, .1, lima_sim)

    ## a scan with multiple top masters
    chain = AcquisitionChain()
    master1 = timer.SoftwareTimerMaster(0.1, npoints=2, name="timer1")
    diode_sim = alias_session.config.get("diode")
    diode_device = SamplingCounterAcquisitionDevice(diode_sim, count_time=0.1)
    master2 = timer.SoftwareTimerMaster(0.001, npoints=50, name="timer2")
    lima_master = LimaAcquisitionMaster(lima_sim, acq_nb_frames=1, acq_expo_time=0.0005)
    # note: dummy device has 2 channels: pi and nb
    dummy_device = dummy_acq_device.get(None, "dummy_device", npoints=1)
    chain.add(lima_master, dummy_device)
    chain.add(master2, lima_master)
    chain.add(master1, diode_device)
    master1.terminator = False

    s2 = Scan(chain, "test", save=True)
    s2.run()

    diode2 = alias_session.config.get("diode2")
    # TEST NOT RELIALE when excuting kill ... has to be fixed
    ### test scan with undefined number of points
    s3 = scans.timescan(.05, diode2, run=False)
    gevent.sleep(.2)
    ## just to see if there is no event created before the scan runs...
    scan_task = gevent.spawn(s3.run)
    # todo add synchronisatin once !1594 is merged
    # for now .. incrase sleep time
    gevent.sleep(1)

    try:
        scan_task.kill(KeyboardInterrupt)
    except:
        assert scan_task.ready()

    # just until the test above is reliable
    # ~ s3 = scans.timescan(.05, diode2, npoints=1)

    ## scan with counter that exports individual samples (SamplingMode.Samples)
    scan5_a = scans.loopscan(5, 0.1, alias_session.config.get("diode9"), save=True)

    ## artifical scan that forces different length of datasets in SamplingMode.Samples
    from bliss.common.measurement import SoftCounter, SamplingMode
    from bliss.common.soft_axis import SoftAxis

    class A:
        def __init__(self):
            self.val = 0
            self.i = 0

        def read(self):
            gevent.sleep((self.val % 5 + 1) * 0.002)
            self.i += 1
            return self.i

        @property
        def position(self):
            return self.val

        @position.setter
        def position(self, val):
            self.val = val
            self.i = 0

    a = A()
    ax = SoftAxis("test-sample-pos", a)
    c_samp = SoftCounter(a, "read", name="test-samp", mode=SamplingMode.SAMPLES)
    scan5_b = scans.ascan(ax, 1, 9, 9, .1, c_samp)

    ##wait for all scan entries
    external_writer_file = s1.scan_info["filename"].replace(".", "_external.")
    bliss_writer_file = s1.scan_info["filename"]

    # check that external writer has at least started to procces all scans
    for i in range(0, 20):
        if len(h5py.File(external_writer_file).keys()) < 6:
            print("##### external writer not done yet")
            gevent.sleep(1)

    # check that all scans have been finalized
    for i in range(0, 20):
        if len(scan_stack) > 0:
            print("##### waiting for finalization")
            gevent.sleep(1)

    ## check if external file is the same as the one of bliss writer for simple scan
    external_writer = h5todict(external_writer_file)["2_ascan"]
    bliss_writer = h5todict(bliss_writer_file)["2_ascan"]
    deep_compare(external_writer, bliss_writer)

    # ~ ## check if external file is the same as the one of bliss writer for multiple top master
    external_writer_mult_top_master = h5todict(external_writer_file)["3_test"]
    bliss_writer_mult_top_master = h5todict(bliss_writer_file)["3_test"]
    deep_compare(external_writer_mult_top_master, bliss_writer_mult_top_master)

    # ~ ## check if external file is the same as the one of bliss writer for multiple top master (part 2)
    external_writer_mult_top_master2 = h5todict(external_writer_file)["3.1_test"]
    bliss_writer_mult_top_master2 = h5todict(bliss_writer_file)["3.1_test"]
    # bliss writer does not pot the references to scan_meta and instrument into the subscans ... in this test
    # we will just pop them
    external_writer_mult_top_master2.pop("instrument")
    external_writer_mult_top_master2.pop("scan_meta")
    deep_compare(external_writer_mult_top_master2, bliss_writer_mult_top_master2)

    ## check if external file is the same as the one of bliss writer for scan with undefined number of points
    external_writer = h5todict(external_writer_file)["4_timescan"]
    bliss_writer = h5todict(bliss_writer_file)["4_timescan"]
    # lets allow one point difference due to the kill
    if (
        bliss_writer["measurement"]["timer:epoch"].size
        == external_writer["measurement"]["timer:epoch"].size - 1
    ):
        bliss_writer["measurement"]["timer:epoch"] = numpy.append(
            bliss_writer["measurement"]["timer:epoch"],
            external_writer["measurement"]["timer:epoch"][-1],
        )
    deep_compare(external_writer, bliss_writer)

    ## check scans with dynamic sample size
    external_writer = h5todict(external_writer_file)["5_loopscan"]
    bliss_writer = h5todict(bliss_writer_file)["5_loopscan"]
    deep_compare(external_writer, bliss_writer)

    external_writer = h5todict(external_writer_file)["6_ascan"]
    bliss_writer = h5todict(bliss_writer_file)["6_ascan"]
    deep_compare(external_writer, bliss_writer)
