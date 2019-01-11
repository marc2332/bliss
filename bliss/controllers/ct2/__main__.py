# -*- coding: utf-8 -*-
#
# This file is part of the CT2 project
#
# Copyright (c) : 2015
# Beamline Control Unit, European Synchrotron Radiation Facility
# BP 220, Grenoble 38043
# FRANCE
#
# Distributed under the terms of the GNU Lesser General Public License,
# either version 3 of the License, or (at your option) any later version.
# See LICENSE.txt for more info.

from bliss.config.static import get_config
from bliss.controllers.ct2 import device
from bliss.controllers import musst

import gevent
from gevent.event import Event
from louie import dispatcher

cfg = None
musst_dev = None
musst_trig_width = None
musst_extra_period = None
acq_timeout = None

import sys
import time
import argparse
import re
import random

musst_prog = """
UNSIGNED T1
UNSIGNED T2
UNSIGNED NPTS
UNSIGNED IPT

PROG PULSES
    CTSTOP TIMER
    TIMER = 0

    CTRESET TIMER
    CTSTART TIMER

    BTRIG 0
    
    BTRIG 1
    DOACTION ATRIG
    
    FOR IPT FROM 1 TO NPTS
        @TIMER= TIMER + T1
        AT TIMER DO STORE BTRIG ATRIG
        @TIMER= TIMER + T2
        AT TIMER DO STORE BTRIG
    ENDFOR

    BTRIG 0

ENDPROG
"""

ExtTrigModes = ["ExtTrigSingle", "ExtTrigMulti", "ExtGate", "ExtTrigReadout"]


def get_ct2_dev(dev_name, in_config):
    global cfg
    if not cfg:
        cfg = get_config()
    else:
        cfg.reload()
    dev = cfg.get(dev_name)
    dev.input_config = in_config
    return dev


def has_soft_trig(acq_mode):
    return acq_mode in ["SoftTrigReadout", "IntTrigMulti"]


def has_ext_start(acq_mode):
    return acq_mode in ExtTrigModes


def has_ext_trig(acq_mode):
    return acq_mode in ["ExtTrigMulti", "ExtGate", "ExtTrigReadout"]


def get_musst_dev(dev_name):
    dev_cfg = cfg.get_config(dev_name)
    dev = musst.musst(dev_name, dev_cfg)
    return dev


def create_musst_dev(dev_name):
    global musst_dev
    musst_dev = get_musst_dev(dev_name)
    musst_dev.upload_program(musst_prog)


def prepare_musst(expo_time, point_period, nb_points):
    t1 = expo_time
    t2 = point_period - expo_time
    musst_dev.putget("VAR T1 %s" % int(t1 * 1e6))
    musst_dev.putget("VAR T2 %s" % int(t2 * 1e6))
    musst_dev.putget("VAR NPTS %s" % nb_points)


def run_musst():
    musst_dev.run()


def wait_musst():
    while musst_dev.STATE != musst.musst.IDLE_STATE:
        gevent.sleep(0.5)


def stop_musst():
    musst_dev.ABORT
    musst_dev.BTRIG = 0


def start_acq(dev, acq_mode, expo_time, point_period, nb_points, static_cb_list=[]):
    acq_end = Event()

    def acq_status_cb(status, **kws):
        if status == device.AcqStatus.Ready:
            acq_end.set()

    static_cb_list.append(acq_status_cb)

    dev.acq_mode = getattr(device.AcqMode, acq_mode)
    dev.acq_expo_time = expo_time
    dev.acq_point_period = point_period
    dev.acq_nb_points = nb_points
    dev.prepare_acq()
    dispatcher.connect(acq_status_cb, device.StatusSignal, dev)
    dev.start_acq()
    return acq_end


def ct2_acq(dev, acq_mode, expo_time, point_period, nb_points, i):

    trig_readout_modes = ["IntTrigReadout", "SoftTrigReadout"]
    if acq_mode in trig_readout_modes:
        if point_period and point_period != expo_time:
            raise ValueError("Invalid point period for trigger/readoud mode")
    else:
        if point_period and point_period <= expo_time:
            raise ValueError("If defined, point period must be > than " "expo. time")

    soft_trig = has_soft_trig(acq_mode)
    ext_start = has_ext_start(acq_mode)
    ext_trig = has_ext_trig(acq_mode)
    if soft_trig or ext_trig:
        sleep_time = max(expo_time, point_period)
        point_period = 0

    acq_end = start_acq(dev, acq_mode, expo_time, point_period, nb_points)

    if soft_trig:
        for i in range(nb_points):
            gevent.sleep(sleep_time)
            if (i < nb_points - 1) or (acq_mode == "SoftTrigReadout"):
                dev.trigger_point()
    elif ext_start and (i == 0):
        run_musst()

    acq_end.wait()


def base_test(dev, acq_mode, expo_time, point_period, acq_nb_points, nb_acqs):

    dev.timer_freq = 1e6

    if has_ext_start(acq_mode):
        ext_exp = acq_mode == "ExtGate"
        musst_expo_time = expo_time if ext_exp else musst_trig_width
        musst_point_period = point_period
        musst_pulses = nb_acqs
        if acq_mode == "ExtTrigSingle":
            musst_point_period *= acq_nb_points
        else:
            extra_pulse = acq_mode == "ExtTrigReadout"
            musst_pulses *= acq_nb_points + (1 if extra_pulse else 0)
        musst_point_period += musst_extra_period
        prepare_musst(musst_expo_time, musst_point_period, musst_pulses)

    t0 = time.time()
    for i in range(nb_acqs):
        ct2_acq(dev, acq_mode, expo_time, point_period, acq_nb_points, i)
    t = time.time()
    print(
        (
            "%-15s Expo=%.4f, Period=%.4f, Points/Acqs=%s/%s, Elapsed=%.4f"
            % (acq_mode, expo_time, point_period, acq_nb_points, nb_acqs, t - t0)
        )
    )


def get_acq_timeout(s):
    if not s:
        return None

    nb_re_str = "[-+.0-9eE]+"
    re_obj = re.compile(nb_re_str)
    m = re_obj.match(s)
    if m:
        return float(s)

    random_re_str = "random\((?P<n1>{0}),[ ]*(?P<n2>{0})\)".format(nb_re_str)
    re_obj = re.compile(random_re_str)
    m = re_obj.match(s)
    if m:

        def usec(x):
            return int(float(x) * 1e6)

        n1, n2 = map(usec, m.groups())
        return random.randrange(n1, n2) * 1e-6

    raise ValueError("Invalid acq_timeout: %s" % s)


def test(dev, acq_mode, *args, **kws):
    sleep_time = 0
    if len(args) > 4:
        sleep_time = args[4]
        args = list(args)
        args.pop(4)
    elif "sleep_time" in kws:
        sleep_time = kws.pop("sleep_time")

    t0 = time.time()
    try:
        t = get_acq_timeout(acq_timeout)
        if t:
            print("- Timeout=%s" % t)
        with gevent.Timeout(t):
            base_test(dev, acq_mode, *args, **kws)
        if has_ext_start(acq_mode):
            wait_musst()
    except gevent.Timeout:
        print("%-15s - Timeout: Interrupting!" % acq_mode)
        dev.stop_acq()
        t = time.time()
        if has_ext_start(acq_mode):
            stop_musst()
        print("%-15s - Elapsed: %s" % ("", t - t0))

    if sleep_time:
        gevent.sleep(sleep_time)


def main():
    parser = argparse.ArgumentParser(description="Test the CT2 device class")

    parser.add_argument(
        "--dev_name", default="p201", type=str, help="Device name in config"
    )
    parser.add_argument(
        "--hard_reset", default=0, type=int, help="Perform a hard reset"
    )
    parser.add_argument(
        "--acq_mode", default="IntTrigSingle", type=str, help="Acquisition mode"
    )
    parser.add_argument("--expo_time", default=0.050, type=float, help="Exposure time")
    parser.add_argument(
        "--point_period", default=0.075, type=float, help="Point period (0=expo_time)"
    )
    parser.add_argument(
        "--acq_nb_points", default=4, type=int, help="Acq. number of points"
    )
    parser.add_argument("--nb_acqs", default=2, type=int, help="Number of acq.s")
    parser.add_argument(
        "--in_chan", default=7, type=int, help="Input channel for ext trig"
    )
    parser.add_argument(
        "--musst_name",
        default="musst_bculab",
        type=str,
        help="Config name of the MUSST pulse generator",
    )
    parser.add_argument(
        "--musst_trig_width", default=1e-3, type=float, help="MUSST trigger pulse width"
    )
    parser.add_argument(
        "--musst_extra_period",
        default=10e-3,
        type=float,
        help="Extra MUSST point period",
    )
    parser.add_argument(
        "--acq_timeout",
        default="",
        type=str,
        help="Timeout aborting acquisition sequence",
    )
    parser.add_argument(
        "--all_tests",
        default=1,
        type=int,
        help="Execute all tests: 1=Int+Soft, 2=Ext, " "3=Int+Soft+Ext",
    )
    parser.add_argument(
        "--sleep_time", default=2, type=float, help="Sleep time between test"
    )

    args = parser.parse_args()

    try:
        getattr(device.AcqMode, args.acq_mode)
    except:
        raise ValueError("Invalid acquisition mode: %s" % args.acq_mode)

    use_ext_trig = has_ext_start(args.acq_mode) or (args.all_tests >= 2)

    in_config = {"chan": args.in_chan} if use_ext_trig else None
    dev = get_ct2_dev(args.dev_name, in_config)
    if args.hard_reset:
        dev.reset()
        del dev
        dev = get_ct2_dev(args.dev_name, in_config)

    global acq_timeout
    acq_timeout = args.acq_timeout

    if use_ext_trig:
        create_musst_dev(args.musst_name)
        global musst_trig_width, musst_extra_period
        musst_trig_width = args.musst_trig_width
        musst_extra_period = args.musst_extra_period

    if args.all_tests == 0:
        test(
            dev,
            args.acq_mode,
            args.expo_time,
            args.point_period,
            args.acq_nb_points,
            args.nb_acqs,
        )

    if args.all_tests & 1:
        mode_lists = (
            (False, ["IntTrigReadout", "SoftTrigReadout"]),
            (True, ["IntTrigSingle", "IntTrigMulti"]),
        )
        strict_multi_point_modes = ["IntTrigMulti"]
        for has_point_period, mode_list in mode_lists:
            point_period = args.point_period if has_point_period else 0
            for acq_mode in mode_list:
                # multi-point acquisitions
                test(
                    dev,
                    acq_mode,
                    args.expo_time,
                    point_period,
                    args.acq_nb_points,
                    args.nb_acqs,
                    args.sleep_time,
                )
                # multiple single-point acquisitions
                if acq_mode not in strict_multi_point_modes:
                    test(
                        dev,
                        acq_mode,
                        args.expo_time,
                        point_period,
                        1,
                        args.acq_nb_points * args.nb_acqs,
                        args.sleep_time,
                    )

    if args.all_tests & 2:
        for acq_mode in ExtTrigModes:
            test(
                dev,
                acq_mode,
                args.expo_time,
                args.point_period,
                args.acq_nb_points,
                args.nb_acqs,
                args.sleep_time,
            )


if __name__ == "__main__":
    main()
