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
from bliss.controllers import ct2
from bliss.controllers import musst

import gevent
from gevent.event import Event
from louie import dispatcher

cfg = None
musst_dev = None
musst_trig_width = None
musst_extra_period = None

import sys
import time
import argparse

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

ExtTrigModes = ['ExtTrigSingle', 'ExtTrigMulti', 'ExtGate', 'ExtTrigReadout']

def get_ct2_dev(dev_name, in_config):
    global cfg
    if not cfg:
        cfg = get_config()
    else:
        cfg.reload()
    dev = ct2.CT2Device(config=cfg, name=dev_name, in_config=in_config)
    return dev

def has_soft_trig(acq_mode):
    return acq_mode in ['SoftTrigReadout', 'IntTrigMulti']

def has_ext_start(acq_mode):
    return acq_mode in ExtTrigModes

def has_ext_trig(acq_mode):
    return acq_mode in ['ExtTrigMulti', 'ExtGate', 'ExtTrigReadout']

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

def start_acq(dev, acq_mode, expo_time, point_period, nb_points,
              static_cb_list=[]):
    acq_end = Event()
    def acq_status_cb(status, **kws):
        if status == ct2.AcqStatus.Ready:
            acq_end.set()
    static_cb_list.append(acq_status_cb)
    
    dev.acq_mode = getattr(ct2.AcqMode, acq_mode)
    dev.acq_expo_time = expo_time
    dev.acq_point_period = point_period
    dev.acq_nb_points = nb_points
    dev.prepare_acq()
    dispatcher.connect(acq_status_cb, ct2.StatusSignal, dev)
    dev.start_acq()
    return acq_end


def ct2_acq(dev, acq_mode, expo_time, point_period, nb_points, i):

    trig_readout_modes = ['IntTrigReadout', 'SoftTrigReadout']
    if acq_mode in trig_readout_modes:
        if point_period and point_period != expo_time:
            raise ValueError('Invalid point period for trigger/readoud mode')
    else:
        if point_period and point_period <= expo_time:
            raise ValueError('If defined, point period must be > than '
                             'expo. time')

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
            if (i < nb_points - 1) or (acq_mode == 'SoftTrigReadout'):
                dev.trigger_point()
    elif ext_start and (i == 0):
        run_musst()
    
    acq_end.wait()


def test(dev, acq_mode, expo_time, point_period, acq_nb_points, nb_acqs,
         sleep_time=0):

    dev.timer_freq = 1e6

    ext_start = has_ext_start(acq_mode)
    ext_exp = acq_mode == 'ExtGate'
    if ext_start:
        musst_expo_time = expo_time if ext_exp else musst_trig_width
        musst_point_period = point_period
        musst_pulses = nb_acqs
        if acq_mode == 'ExtTrigSingle':
            musst_point_period *= acq_nb_points
        else:
            extra_pulse = (acq_mode == 'ExtTrigReadout')
            musst_pulses *= acq_nb_points + (1 if extra_pulse else 0)
        musst_point_period += musst_extra_period
        prepare_musst(musst_expo_time, musst_point_period, musst_pulses)

    t0 = time.time()
    for i in range(nb_acqs):
        ct2_acq(dev, acq_mode, expo_time, point_period, acq_nb_points, i)
    t = time.time()
    print ("%-15s Expo=%.4f, Period=%.4f, Points/Acqs=%s/%s, Elapsed=%.4f" %
           (acq_mode, expo_time, point_period, acq_nb_points, nb_acqs, t - t0))

    if sleep_time:
        gevent.sleep(sleep_time)
    if ext_start:
        wait_musst()

def main():
    parser = argparse.ArgumentParser(description='Test the CT2Device class')
    
    parser.add_argument('--dev_name', default='p201_lid00c_0', type=str,
                        help='Device name in config')
    parser.add_argument('--hard_reset', default=0, type=int,
                        help='Perform a hard reset')
    parser.add_argument('--acq_mode', default='IntTrigSingle', type=str,
                        help='Acquisition mode')
    parser.add_argument('--expo_time', default=0.10, type=float,
                        help='Exposure time')
    parser.add_argument('--point_period', default=0.15, type=float,
                        help='Point period (0=expo_time)')
    parser.add_argument('--acq_nb_points', default=4, type=int,
                        help='Acq. number of points')
    parser.add_argument('--nb_acqs', default=1, type=int,
                        help='Number of acq.s')
    parser.add_argument('--in_chan', default=7, type=int,
                        help='Input channel for ext trig')
    parser.add_argument('--musst_name', default='musst_bculab', type=str,
                        help='Config name of the MUSST pulse generator')
    parser.add_argument('--musst_trig_width', default=1e-3, type=float,
                        help='MUSST trigger pulse width')
    parser.add_argument('--musst_extra_period', default=10e-3, type=float,
                        help='Extra MUSST point period')
    parser.add_argument('--all_tests', default=0, type=int,
                        help='Execute all tests: 1=Int+Soft, 2=Int+Soft+Ext')
    parser.add_argument('--sleep_time', default=2, type=float,
                        help='Sleep time between test')

    args = parser.parse_args()

    try:
        getattr(ct2.AcqMode, args.acq_mode)
    except:
        raise ValueError('Invalid acquisition mode: %s' % args.acq_mode)

    use_ext_trig = has_ext_start(args.acq_mode) or (args.all_tests >= 2)

    in_config = {'chan': args.in_chan} if use_ext_trig else None
    dev = get_ct2_dev(args.dev_name, in_config)
    if args.hard_reset:
        dev.reset()
        del dev
        dev = get_ct2_dev(args.dev_name)

    if use_ext_trig:
        create_musst_dev(args.musst_name)
        global musst_trig_width, musst_extra_period
        musst_trig_width = args.musst_trig_width
        musst_extra_period = args.musst_extra_period

    if args.all_tests == 0:
        test(dev, args.acq_mode, args.expo_time, args.point_period,
             args.acq_nb_points, args.nb_acqs)

    if args.all_tests & 1:
        mode_lists = ((False, ['IntTrigReadout', 'SoftTrigReadout']),
                      (True, ['IntTrigSingle', 'IntTrigMulti']))
        for has_point_period, mode_list in mode_lists:
            point_period = args.point_period if has_point_period else 0
            for acq_mode in mode_list:
                test(dev, acq_mode, args.expo_time, point_period,
                     args.acq_nb_points, args.nb_acqs, args.sleep_time)
            acq_mode = mode_list[0]
            test(dev, acq_mode, args.expo_time, point_period, 1,
                 args.acq_nb_points * args.nb_acqs, args.sleep_time)
            
    if args.all_tests & 2:
        for acq_mode in ExtTrigModes:
            test(dev, acq_mode, args.expo_time, args.point_period,
                 args.acq_nb_points, args.nb_acqs, args.sleep_time)
                

if __name__ == '__main__':
    main()    
