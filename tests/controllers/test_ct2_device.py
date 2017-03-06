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

import gevent
from gevent.event import Event
from louie import dispatcher

cfg = None

import sys
import time
import argparse

def get_dev(dev_name):
    global cfg
    if not cfg:
        cfg = get_config()
    else:
        cfg.reload()
    dev = ct2.CT2Device(config=cfg, name=dev_name)
    return dev

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


def ct2_acq(dev, acq_mode, expo_time, point_period, nb_points):

    trig_readout_modes = ['IntTrigReadout', 'SoftTrigReadout']
    if acq_mode in trig_readout_modes:
        if point_period and point_period != expo_time:
            raise ValueError('Invalid point period for trigger/readoud mode')
    else:
        if point_period and point_period <= expo_time:
            raise ValueError('If defined, point period must be > than '
                             'expo. time')

    soft_trig_modes = ['SoftTrigReadout', 'IntTrigMulti']
    soft_trig = acq_mode in soft_trig_modes
    if soft_trig:
        sleep_time = max(expo_time, point_period)
        point_period = 0
        
    acq_end = start_acq(dev, acq_mode, expo_time, point_period, nb_points)

    if soft_trig:
        for i in range(nb_points):
            gevent.sleep(sleep_time)
            if (i < nb_points - 1) or (acq_mode == 'SoftTrigReadout'):
                dev.trigger_point()

    acq_end.wait()


def test(dev, acq_mode, expo_time, point_period, acq_nb_points, nb_acqs,
         sleep_time=0):

    dev.timer_freq = 1e6

    t0 = time.time()
    for i in range(nb_acqs):
        ct2_acq(dev, acq_mode, expo_time, point_period, acq_nb_points)
    t = time.time()
    print ("%-15s Expo=%.4f, Period=%.4f, Points/Acqs=%s/%s, Elapsed=%.4f" %
           (acq_mode, expo_time, point_period, acq_nb_points, nb_acqs, t - t0))

    if sleep_time:
        gevent.sleep(sleep_time)

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
    parser.add_argument('--all_tests', default=0, type=int,
                        help='Execute all tests')
    parser.add_argument('--sleep_time', default=2, type=float,
                        help='Sleep time between test')

    args = parser.parse_args()

    try:
        getattr(ct2.AcqMode, args.acq_mode)
    except:
        raise ValueError('Invalid acquisition mode: %s' % args.acq_mode)
        
    dev = get_dev(args.dev_name)
    if args.hard_reset:
        dev.reset()
        del dev
        dev = get_dev(args.dev_name)

    if args.all_tests:
        if args.nb_acqs != 1:
            raise ValueError('all_tests requires nb_acqs=1')

        mode_lists = ((False, ['IntTrigReadout', 'SoftTrigReadout']),
                      (True, ['IntTrigSingle', 'IntTrigMulti']))
        for has_point_period, mode_list in mode_lists:
            point_period = args.point_period if has_point_period else 0
            for acq_mode in mode_list:
                test(dev, acq_mode, args.expo_time, point_period,
                     args.acq_nb_points, 1, args.sleep_time)
            acq_mode = mode_list[0]
            test(dev, acq_mode, args.expo_time, point_period, 1,
                 args.acq_nb_points, args.sleep_time)
            
    else:
        test(dev, args.acq_mode, args.expo_time, args.point_period,
             args.acq_nb_points, args.nb_acqs)

if __name__ == '__main__':
    main()    
