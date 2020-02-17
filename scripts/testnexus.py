#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Run Nexus service stress tests.

Setup test environment first with `python scripts/testenv.py`
"""

import gevent
import sys
import os
import h5py
import random
from contextlib import contextmanager
from bliss.config import static
from bliss.common import scans
from bliss.data.scan import watch_session_scans
from bliss.scanning.group import Group


def get_detectors(test_session):
    env_dict = test_session.env_dict
    detectors = [
        env_dict.get(f"diode{i}", env_dict.get(f"diode{i}alias")) for i in range(2, 10)
    ]
    detectors += [
        env_dict.get(f"simu{i}", env_dict.get(f"simu{i}alias")) for i in [1, 2]
    ]
    detectors += [
        env_dict.get(f"lima_simulator{i}", env_dict.get(f"lima_simulator{i}alias"))
        for i in ["", 2]
    ]
    return detectors


def get_motors(test_session):
    env_dict = test_session.env_dict
    return [env_dict[name] for name in ["robx", "roby", "robz"]]


def get_scan_funcs(test_session):
    env_dict = test_session.env_dict
    return {
        "ct": scans.ct,
        "loopscan": scans.loopscan,
        "ascan": scans.ascan,
        "amesh": scans.amesh,
        "aloopscan": env_dict.get("aloopscan"),
    }


def prepare_saving(test_session, root=None):
    scan_saving = test_session.scan_saving
    scan_saving.writer = "nexus"
    scan_saving.data_filename = "test"
    if root:
        scan_saving.base_path = root
    filename = scan_saving.filename
    try:
        os.remove(filename)
    except FileNotFoundError:
        pass
    return filename


def get_scan(detectors, motors, scan_funcs):
    # TODO: scans not stressful enough
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


def reader(filename, mode):
    while True:
        gevent.sleep(0.1)
        try:
            with h5py.File(filename, mode=mode) as f:
                for entry in f:
                    list(f[entry]["instrument"].keys())
                    list(f[entry]["measurement"].keys())
        except (KeyboardInterrupt, gevent.GreenletExit):
            break
        except Exception:
            pass


def run_scan(test_session, scan):
    env_dict = test_session.env_dict
    return env_dict["run_scan"](scan, runasync=True, format="hdf5", frames=100)


def stress_many_parallel(test_session, filename, titles, checkoutput=True):
    scan_funcs = get_scan_funcs(test_session)

    # Create as many scans as possible
    detectors = get_detectors(test_session)
    motors = get_motors(test_session)
    scns = []
    while detectors:
        scns.append(get_scan(detectors, motors, scan_funcs))

    # Run all in parallel
    glts = [run_scan(test_session, s) for s in scns]
    try:
        gevent.joinall(glts)
    except KeyboardInterrupt:
        try:
            gevent.killall(glts, KeyboardInterrupt)
        except Exception:
            return True
    else:
        for g in glts:
            g.get()

    # Group the scans
    g = Group(*scns)
    g.wait_all_subscans(timeout=10)
    scns.append(g.scan)

    if checkoutput:
        check_output(scns, titles)


@contextmanager
def print_scan_progress(test_session):
    data = {}

    def new_data(ndim, master, info):
        nonlocal data
        if ndim == "0d":
            for cname, cdata in info["data"].items():
                data[cname] = len(cdata)
        else:
            cname = info["channel_name"]
            data[cname] = len(info["channel_data_node"])
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


def stress_bigdata(test_session, filename, titles, checkoutput=True):
    detectors = get_detectors(test_session)
    motors = get_motors(test_session)

    mot1, mot2 = motors[:2]
    with print_scan_progress(test_session):
        # approx 24h
        scan = scans.amesh(
            mot1, 0, 10, 400, mot2, 1, 20, 300, 1e-6, *detectors, run=False
        )
        g = run_scan(test_session, scan)
        try:
            g.join()
        except KeyboardInterrupt:
            try:
                g.kill(KeyboardInterrupt)
            except Exception:
                return True
        else:
            g.get()

    if checkoutput:
        check_output([scan], titles)


def check_output(scans, titles):
    subscans = {"aloopscan": 2}

    # Minimal output check
    titles += [
        "{}.{}".format(int(s.scan_number), i)
        for s in scans
        for i in range(1, subscans.get(s.name, 1) + 1)
    ]
    with h5py.File(filename, mode="r") as f:
        err_msg = "{}: {}/nExpected: {}".format(filename, set(f.keys()), set(titles))
        assert set(f.keys()) == set(titles), err_msg

    # Progress report
    print("{} scans ...".format(len(titles)))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run Nexus writer stress tests")
    parser.add_argument(
        "--type",
        default="many",
        type=str.lower,
        help="Stress type",
        choices=["many", "data"],
    )
    parser.add_argument("--root", default="", help="Data root directory")
    parser.add_argument(
        "--readers", default=0, type=int, help="Number of parallel readers"
    )
    parser.add_argument(
        "--n", default=0, type=int, help="Number iterations (unlimited by default)"
    )
    args, unknown = parser.parse_known_args()
    if args.type == "many":
        test_func = stress_many_parallel
    elif args.type == "data":
        test_func = stress_bigdata
    else:
        test_func = stress_many_parallel

    config = static.get_config()
    test_session = config.get("nexus_writer_session")
    test_session.setup()
    root = args.root
    if not root:
        root = "/tmp/testnexus/" + args.type
    filename = prepare_saving(test_session, root=root)
    readers = [gevent.spawn(reader, filename, "r") for _ in range(max(args.readers, 0))]
    try:
        titles = []
        imax = args.n
        i = 1
        while True:
            gevent.sleep()
            if test_func(test_session, filename, titles):
                break
            if imax and i == imax:
                break
            i += 1
    finally:
        if readers:
            gevent.killall(readers)
            gevent.joinall(readers)
