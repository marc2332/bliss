# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from ..chain import AcquisitionMaster, AcquisitionChannel
from bliss.common.event import dispatcher
import time
import gevent
import numpy

class SoftwareTimerMaster(AcquisitionMaster):
    def __init__(self,count_time,**keys):
        AcquisitionMaster.__init__(self,None,"timer","zerod",
                                   **keys)
        self.count_time = count_time
        self.channels.append(AcquisitionChannel('timestamp',numpy.double, (1,)))
        
        self._nb_point = 0
        self._timescan_mode = False

    @property
    def timescan_mode(self):
        return self._timescan_mode
    @timescan_mode.setter
    def timescan_mode(self,value):
        self._timescan_mode = value
        self.one_shot = False
        self._nb_point = 0

    def prepare(self):
        pass

    def start(self):
        if self._timescan_mode and self.npoints > 0:
            self.one_shot = self.npoints == self._nb_point + 1
            self._nb_point += 1

        #if we are the main master
        if self.one_shot or self.timescan_mode:
            self.trigger()

    def trigger(self):
        dispatcher.send("new_data",self,
                        {"channel_data":{'timestamp':numpy.double(time.time())}})

        self.trigger_slaves()
        gevent.sleep(self.count_time)

    def stop(self):
        pass
