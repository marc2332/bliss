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

cfg = get_config()
dev = ct2.CT2Device(cfg, 'p201_lid002_0', out_config={'chan': 10})
dev.timer_freq = 1e6


def ct2_acq(expo_time, point_period, nb_points):

    acq_end = Event()
    def acq_status_cb(status, **kws):
        if status == ct2.AcqStatus.Ready:
            acq_end.set()

    dev.acq_expo_time = expo_time
    dev.acq_point_period = point_period
    dev.acq_nb_points = nb_points
    dev.prepare_acq()

    dispatcher.connect(acq_status_cb, ct2.StatusSignal, dev)

    dev.start_acq()
    acq_end.wait()

ct2_acq(0.1, 0.150, 4)
