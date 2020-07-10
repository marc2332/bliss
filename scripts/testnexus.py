#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Run Nexus service stress tests.

Setup test environment first with `python scripts/testenv.py`
"""

import gevent
import sys
import os
import random
import shutil
import numpy
from contextlib import contextmanager
from fabio.edfimage import EdfImage
from bliss.config import static
from bliss.common import scans
from bliss.data.scan import watch_session_scans
from bliss.scanning.group import Sequence, Group
from bliss.common.tango import DeviceProxy
from nexus_writer_service.io import nexus


def run_scans(*scns):
    """
    :param bliss.scanning.scan.Scan:
    """
    print(f"\nRunning {len(scns)} scans ...")
    glts = [gevent.spawn(s.run) for s in scns]
    try:
        gevent.joinall(glts)
    except KeyboardInterrupt:
        gevent.killall(glts, KeyboardInterrupt)
        raise
    else:
        for g in glts:
            g.get()
    finally:
        print("\nScans finished.")


def stress_many_parallel(test_session, filename, titles, checkoutput=True):
    """
    :param bliss.common.session.Session test_session:
    :param str filename: for data saving
    :param list(str) titles: keep track of the number of scans
    :param bool checkoutput:
    """
    scan_funcs = get_scan_funcs(test_session)
    scanseq = Sequence()
    with scanseq.sequence_context() as scan_seq:
        # Create as many scans as possible
        detectors = get_detectors(test_session)
        motors = get_motors(test_session)
        scns = []

        while detectors:
            s = get_scan(detectors, motors, scan_funcs)
            scan_seq.add(s)
            scns.append(s)
        # Run all in parallel
        run_scans(*scns)

    # Group the scans
    g = Group(*scns)
    g.wait_all_subscans(timeout=10)
    scns.append(g.scan)
    scanseq.wait_all_subscans(timeout=10)
    scns.append(scanseq.scan)

    if checkoutput:
        check_output(scns, titles)


def stress_bigdata(test_session, filename, titles, checkoutput=True):
    """
    :param bliss.common.session.Session test_session:
    :param str filename: for data saving
    :param list(str) titles: keep track of the number of scans
    :param bool checkoutput:
    """
    detectors = get_detectors(test_session)
    lima_saving(test_session, frames=100)
    motors = get_motors(test_session)

    mot1, mot2 = motors[:2]
    with print_scan_progress(test_session):
        scan = scans.amesh(
            mot1, 0, 10, 200, mot2, 1, 20, 300, 1e-6, *detectors, run=False
        )
        run_scans(scan)

    if checkoutput:
        check_output([scan], titles)


def stress_fastdata(test_session, filename, titles, checkoutput=True):
    """
    :param bliss.common.session.Session test_session:
    :param str filename: for data saving
    :param list(str) titles: keep track of scans
    :param bool checkoutput:
    """
    detectors = (test_session.env_dict["lima_simulator"],)
    lima_saving(test_session, frames=1000)

    with print_scan_progress(test_session):
        scan = scans.loopscan(1000, 1e-6, *detectors, run=False)
        run_scans(scan)

    if checkoutput:
        check_output([scan], titles)


def get_motors(test_session):
    """
    :param bliss.common.session.Session test_session:
    :returns list: Bliss scannable objects
    """
    env_dict = test_session.env_dict
    return [env_dict[name] for name in ["robx", "roby", "robz"]]


def get_detectors(test_session):
    """
    :param bliss.common.session.Session test_session:
    :returns list: Bliss controller objects
    """
    env_dict = test_session.env_dict
    detectors = ["sim_ct_gauss", "sim_ct_gauss_noise", "thermo_sample"]
    detectors = [env_dict.get(d) for d in detectors]
    detectors += [
        env_dict.get(f"diode{i}", env_dict.get(f"diode{i}alias")) for i in range(2, 10)
    ]
    detectors += [
        env_dict.get(f"simu{i}", env_dict.get(f"simu{i}alias")) for i in [1, 2]
    ]
    detectors += [
        env_dict.get(f"lima_simulator{i}", env_dict.get(f"lima_simulator{i}alias"))
        for i in ["", 2]
    ]
    lima_saving(test_session)
    return detectors


def get_scan_funcs(test_session):
    """
    :param bliss.common.session.Session test_session:
    :returns list: Bliss scan functions
    """
    env_dict = test_session.env_dict
    return {
        "ct": scans.sct,
        "loopscan": scans.loopscan,
        "ascan": scans.ascan,
        "amesh": scans.amesh,
        "aloopscan": env_dict.get("aloopscan"),
    }


def lima_saving(test_session, frames=100):
    """Prepare lima controllers for data saving

    :param bliss.common.session.Session test_session:
    :param int frames:
    """
    env_dict = test_session.env_dict
    limas = [
        env_dict.get(f"lima_simulator{i}", env_dict.get(f"lima_simulator{i}alias"))
        for i in ["", 2]
    ]
    for lima in limas:
        lima.saving.initialize()
        lima.saving.file_format = "HDF5"
        lima.saving.mode = "ONE_FILE_PER_N_FRAMES"
        lima.saving.frames_per_file = frames
        lima.proxy.set_timeout_millis(60000)
        simulator = lima._get_proxy("simulator")
        simulator.mode = "LOADER_PREFETCH"
        simulator.nb_prefetched_frames = 10
        # simulator.file_pattern = '/data/id21/inhouse/wout/dev/blissscripts/limapreloaddata/*.edf'
        # root = test_session.scan_saving.base_path
        simulator.file_pattern = lima_simulator_images(dirname=lima.name)


def lima_simulator_images(
    nimages=10, root=None, dirname=None, shape=(1024, 1024), dtype=numpy.uint16
):
    """Generate images for preloading the lima simulator

    :param num nimages: simulator loops of these number of images
    :param str root:
    :param str dirname:
    :param 2-tuple shape: data shape
    :param dtype: data type
    """
    if not root:
        root = "/tmp/lima_preload_data"
    if not dirname:
        dirname = "lima"
    root = os.path.join(root, dirname)
    try:
        shutil.rmtree(root)
    except FileNotFoundError:
        pass
    os.makedirs(root)
    ndigits = int(numpy.ceil(numpy.log10(nimages + 1)))
    fmt = "img{{:0{}d}}.edf".format(max(ndigits, 4))
    for i in range(1, nimages + 1):
        data = numpy.full(shape, i, dtype=dtype)
        edf = EdfImage(data=data, header=None)
        edf.write(os.path.join(root, fmt.format(i)))
    return os.path.join(root, "*.edf")


def prepare_saving(test_session, root=None):
    """
    :param bliss.common.session.Session test_session:
    :param str root:
    :returns str: file name
    """
    scan_saving = test_session.scan_saving
    scan_saving.writer = "nexus"
    scan_saving.data_filename = "stresstest_0"
    if root:
        scan_saving.base_path = root
    shutil.rmtree(scan_saving.root_path, ignore_errors=True)
    return scan_saving.filename


def next_file(test_session):
    """
    :param bliss.common.session.Session test_session:
    :returns str: file name
    """
    scan_saving = test_session.scan_saving
    i = int(scan_saving.data_filename.split("_")[1]) + 1
    scan_saving.data_filename = f"stresstest_{i}"
    return scan_saving.filename


def get_scan(detectors, motors, scan_funcs):
    """
    :param list detectors: Bliss controller objects
    :param list motors: Bliss scannable objects
    :param list scan_funcs: Bliss scan functions
    :returns bliss.scanning.scan.Scan:
    """
    expotime = 1e-6
    options = ["ct", "loopscan"]
    if motors:
        options.append("ascan")
    if motors and len(detectors) >= 2:
        options.append("aloopscan")
    if len(motors) >= 2:
        options.append("amesh")
    scan = random.choice(options)
    func = scan_funcs[scan]
    detector = detectors.pop()
    if scan == "ct":
        return func(expotime, detector, save=True, run=False)
    elif scan == "loopscan":
        return func(11, expotime, detector, run=False)
    elif scan == "ascan":
        mot = motors.pop()
        return func(mot, 0.5, 1.5, 10, expotime, detector, run=False)
    elif scan == "amesh":
        mot1 = motors.pop()
        mot2 = motors.pop()
        return func(mot1, 0, 1, 3, mot2, 1, 2, 2, expotime, detector, run=False)
    elif scan == "aloopscan":
        mot = motors.pop()
        detector2 = detectors.pop()
        return func(mot, 0.5, 1.5, 5, expotime, [detector], 4, expotime, [detector2])


@contextmanager
def print_scan_progress(test_session):
    """Add session scan watcher that prints the
    channel point progress.

    :param bliss.common.session.Session test_session:
    """
    data = {}

    def new_data(ndim, master, info):
        nonlocal data
        if ndim == "0d":
            for cname, cdata in info["data"].items():
                data[cname] = len(cdata)
        elif ndim == "1d":
            cname = info["channel_name"]
            data[cname] = len(info["channel_data_node"])
        else:
            cname = info["channel_name"]
            data[cname] = len(info["channel_data_node"].get(0, -1))
        pmin, pmax = min(data.values()), max(data.values())
        sys.stdout.write("\rScan progress {}-{} pts".format(pmin, pmax))
        sys.stdout.flush()

    def nullhandler(*args):
        pass

    ready_event = gevent.event.Event()
    session_watcher = gevent.spawn(
        watch_session_scans,
        test_session.name,
        nullhandler,
        nullhandler,
        new_data,
        nullhandler,
        ready_event=ready_event,
    )
    ready_event.wait(timeout=3)
    try:
        yield
    finally:
        session_watcher.kill()


def check_output(scans, titles):
    """
    :param list(bliss.scanning.scan.Scan) scans:
    :param list(str): keep track of scans
    """
    subscans = {"aloopscan": 2}

    # Minimal output check
    titles += [
        f"{int(s.scan_number)}.{i}"
        for s in scans
        for i in range(1, subscans.get(s.name, 1) + 1)
    ]
    try:
        f = None
        print("Getting scan names from file ...")
        with gevent.Timeout(60):
            while True:
                try:
                    f = nexus.File(filename, mode="r")
                    entrees = set(f.keys())
                    break
                except OSError:
                    try:
                        f.close()
                    except (AttributeError, OSError):
                        pass
    finally:
        try:
            f.close()
        except (AttributeError, OSError):
            pass
    expected = set(titles)
    unexpected = entrees - expected
    missing = expected - entrees
    err_msg = f"{filename}:\n missing: {missing}\n unexpected: {unexpected}\n expected: {expected}"
    assert entrees == expected, err_msg

    # Progress report
    print("{} scans done.".format(len(titles)))


def reader(filename, mode):
    """HDF5 reader polling a file.

    :param str filename:
    :param str mode:
    """
    while True:
        gevent.sleep(0.1)
        try:
            with nexus.File(filename, mode=mode) as f:
                for entry in f:
                    list(f[entry]["instrument"].keys())
                    list(f[entry]["measurement"].keys())
        except (KeyboardInterrupt, gevent.GreenletExit):
            break
        except Exception:
            pass


def tangoclient():
    """Tango client polling the Nexus writer tango device.
    """
    proxy = DeviceProxy("id00/bliss_nxwriter/nexus_writer_session")
    tango_attributes = [
        "scan_states",
        "scan_uris",
        "scan_names",
        "scan_start",
        "scan_end",
        "scan_duration",
        "scan_info",
        "scan_progress",
        "scan_states_info",
        "scan_event_buffers",
        "resources",
    ]
    while True:
        try:
            for attr in tango_attributes:
                getattr(proxy, attr)
                gevent.sleep(0.1)
        except (KeyboardInterrupt, gevent.GreenletExit):
            break


@contextmanager
def client_context(n, *args, **kwargs):
    """Launch clients polling the writer ot the file
    """
    glts = [gevent.spawn(*args, **kwargs) for _ in range(max(n, 0))]
    try:
        yield
    finally:
        if glts:
            gevent.killall(glts)
            gevent.joinall(glts)
            for g in glts:
                g.get()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run Nexus writer stress tests")
    parser.add_argument(
        "--type",
        default="many",
        type=str.lower,
        help="Stress type",
        choices=["many", "big", "fast"],
    )
    parser.add_argument("--root", default="", help="Data root directory")
    parser.add_argument(
        "--readers", default=0, type=int, help="Number of parallel readers"
    )
    parser.add_argument(
        "--tangoclients", default=0, type=int, help="Number of tango clients"
    )
    parser.add_argument(
        "--niter", default=0, type=int, help="Number iterations (unlimited by default)"
    )
    parser.add_argument(
        "--nscans_per_file",
        default=1000,
        type=int,
        help="Maximum number of scans per file",
    )
    args, unknown = parser.parse_known_args()

    # Select stress test
    if args.type == "many":
        test_func = stress_many_parallel
    elif args.type == "big":
        test_func = stress_bigdata
    elif args.type == "fast":
        test_func = stress_fastdata
    else:
        test_func = stress_fastdata

    # Prepare session
    config = static.get_config()
    test_session = config.get("nexus_writer_session")
    test_session.setup()
    root = args.root
    if not root:
        root = "/tmp/testnexus/"
    root = os.path.join(root, args.type)
    filename = prepare_saving(test_session, root=root)

    # Repeat stress test with HDF5 readers and tango clients
    with client_context(args.tangoclients, tangoclient):
        keeprunning = True
        while keeprunning:
            filename = next_file(test_session)
            with client_context(args.readers, reader, filename, "r"):
                titles = []
                n = 1
                while len(titles) < args.nscans_per_file:
                    if test_func(test_session, filename, titles):
                        keeprunning = False
                        break
                    if args.niter and n == args.niter:
                        keeprunning = False
                        break
                    n += 1
