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
    
    dev.acq_mode = acq_mode
    dev.acq_expo_time = expo_time
    dev.acq_point_period = point_period
    dev.acq_nb_points = nb_points
    dev.prepare_acq()
    dispatcher.connect(acq_status_cb, ct2.StatusSignal, dev)
    dev.start_acq()
    return acq_end

def ct2_acq_hard(dev, expo_time, point_period, nb_points):

    acq_mode = (ct2.AcqMode.IntTrigSingle
                if point_period else ct2.AcqMode.IntTrigReadout)
    acq_end = start_acq(dev, acq_mode, expo_time, point_period, nb_points)
    acq_end.wait()


def ct2_acq_soft(dev, expo_time, point_period, nb_points):

    if point_period and point_period <= expo_time:
        raise ValueError('If defined, point period must be > than expo. time')

    acq_mode = (ct2.AcqMode.IntTrigMulti
                if point_period else ct2.AcqMode.SoftTrigReadout)
    acq_end = start_acq(dev, acq_mode, expo_time, 0, nb_points)
    sleep_time = max(expo_time, point_period)
    nb_trig = nb_points - (1 if acq_mode == ct2.AcqMode.IntTrigMulti else 0)
    for i in range(nb_trig):
        gevent.sleep(sleep_time)
        dev.trigger_point()
    acq_end.wait()

def test(dev, expo_time, point_period, acq_nb_points, nb_acqs, soft_trig,
         sleep_time=0):

    dev.timer_freq = 1e6
        
    ct2_test = ct2_acq_soft if soft_trig else ct2_acq_hard

    t0 = time.time()
    for i in range(nb_acqs):
        ct2_test(dev, expo_time, point_period, acq_nb_points)
    t = time.time()
    print ("Expo=%.4f, Period=%.4f, Points=%s, Soft=%d, Elapsed=%s" %
           (expo_time, point_period, acq_nb_points, soft_trig, t - t0))

    if sleep_time:
        gevent.sleep(sleep_time)

def main():
    parser = argparse.ArgumentParser(description='Test the CT2Device class')
    
    parser.add_argument('--dev_name', default='p201_lid00c_0', type=str,
                        help='Device name in config')
    parser.add_argument('--hard_reset', default=0, type=int,
                        help='Perform a hard reset')
    parser.add_argument('--expo_time', default=0.10, type=float,
                        help='Exposure time')
    parser.add_argument('--point_period', default=0.15, type=float,
                        help='Point period (0=expo_time)')
    parser.add_argument('--acq_nb_points', default=4, type=int,
                        help='Acq. number of points')
    parser.add_argument('--nb_acqs', default=1, type=int,
                        help='Number of acq.s')
    parser.add_argument('--soft_trig', default=0, type=int,
                        help='Use software trigger')
    parser.add_argument('--all_tests', default=0, type=int,
                        help='Execute all tests')
    parser.add_argument('--sleep_time', default=2, type=float,
                        help='Sleep time between test')

    args = parser.parse_args()

    dev = get_dev(args.dev_name)
    if args.hard_reset:
        dev.reset()
        del dev
        dev = get_dev(args.dev_name)

    if args.all_tests:
        if args.nb_acqs != 1:
            raise ValueError('all_tests requires nb_acqs=1')
        
        for point_period in (0, args.point_period):
            for soft_trig in (0, 1):
                test(dev, args.expo_time, point_period, args.acq_nb_points, 1,
                     soft_trig, args.sleep_time)
            test(dev, args.expo_time, point_period, 1, args.acq_nb_points, 0,
                 args.sleep_time)
            
    else:
        test(dev, args.expo_time, args.point_period, args.acq_nb_points,
             args.nb_acqs, args.soft_trig)

if __name__ == '__main__':
    main()    
