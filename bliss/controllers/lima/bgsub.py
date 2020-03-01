# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import time

import gevent.timeout


class BgSub(object):
    """Background substraction"""

    def __init__(self, name, bg_sub_proxy, lima):
        self.name = "bg_sub"
        self.proxy = bg_sub_proxy
        self.lima = lima

    # TODO: missing Start/Stop which is linked with offset

    def upload_background(self, filename, delete_after=False):
        prev_delete_after = self.proxy.delete_dark_after_read
        try:
            self.proxy.delete_dark_after_read = delete_after
            self.proxy.setBackgroudImage(filename)
        finally:
            self.proxy.delete_dark_after_read = prev_delete_after

    def take_background(self, expo_time, nb_frames=1, run_level=0):
        for i in self.gen_take_background(
            expo_time, nb_frames=nb_frames, run_level=run_level
        ):
            pass

    def gen_take_background(self, expo_time, nb_frames=1, run_level=0):
        bg = self.proxy
        lima = self.lima
        acq = self.lima.acquisition
        prev_expo_time = acq.expo_time
        prev_nb_frames = acq.nb_frames
        prev_run_level = bg.RunLevel
        try:
            bg.Stop()
            bg.RunLevel = run_level
            bg.takeNextAcquisitionAsBackground()
            acq.expo_time = expo_time
            acq.nb_frames = nb_frames
            lima.prepareAcq()
            start = time.time()
            lima.startAcq()
            with gevent.timeout.Timeout(expo_time + 1):
                while acq.status.lower() == "running":
                    gevent.sleep(0.1)
                    yield time.time() - start
        finally:
            bg.Stop()
            lima.stopAcq()
            acq.expo_time = prev_expo_time
            acq.nb_frames = prev_nb_frames
            bg.RunLevel = prev_run_level
