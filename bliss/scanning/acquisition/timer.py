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
import weakref

class SoftwareTimerMaster(AcquisitionMaster):
    def __init__(self,count_time,sleep_time=None, **keys):
        AcquisitionMaster.__init__(self,None,"timer","zerod",
                                   **keys)
        self.count_time = count_time
        self.sleep_time = sleep_time
        self.channels.append(AcquisitionChannel('timestamp', numpy.double, (1,)))
        
        self._nb_point = 0
    
    def __iter__(self):
        npoints = self.npoints
        if npoints > 0:
            for i in range(npoints):
                self._nb_point = i
                yield self
        else:
            self._nb_point = 0
            while True:
                yield self
                self._nb_point += 1

    def prepare(self):
        pass

    def start(self):
        #if we are the top master
        if self.parent is None:
            self.trigger()

    def trigger(self):
        if self._nb_point > 0 and self.sleep_time:
            gevent.sleep(self.sleep_time)

        start_trigger = time.time()
        dispatcher.send("new_data",self,
                        {"channel_data":{'timestamp':numpy.double(time.time())}})

        self.trigger_slaves()
        elapsed_trigger = time.time()-start_trigger
        gevent.sleep(self.count_time - elapsed_trigger)

    def stop(self):
        pass

class IntegratingTimerMaster(object):
    def __init__(self):
        self.__count_time = 1.
    @property
    def count_time(self):
        return self.__count_time
    @count_time.setter
    def count_time(self,value):
        self.__count_time = value
    def prepare(self):
        integrated_devices = [x.device for x in self.slaves]
        self._prepare(integrated_devices)

    def start(self):
        self._start()

    def trigger(self):
        pass

    def _prepare(self,integrated_devices):
        """ Overwrite in your class if you need it """
        pass

    def _start(self):
        """ Overwrite in your class if you need it """
        pass
