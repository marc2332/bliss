# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2017 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import numpy
import time
from gevent import event,sleep
from bliss.common.event import dispatcher
from ..chain import AcquisitionDevice,AcquisitionChannel
from bliss.common.measurement import CounterBase

class CounterAcqDevice(AcquisitionDevice):
    def __init__(self,counter,
                 count_time=None,npoints=1,**keys):
        prepare_once = keys.pop('prepare_once',npoints > 1 and True or False)
        start_once = keys.pop('start_once',npoints > 1 and True or False)
        npoints = max(1,npoints)
        AcquisitionDevice.__init__(self, counter, counter.name, "zerod",
                                   npoints=npoints,
                                   trigger_type=AcquisitionDevice.SOFTWARE,
                                   prepare_once=prepare_once,
                                   start_once=start_once,
                                   **keys)
        self._count_time = count_time
        if not isinstance(counter,CounterBase.ReadAllHandler):
            self.channels.append(AcquisitionChannel(counter.name,numpy.double, (1,)))
        self._nb_acq_points = 0
        self._event = event.Event()
        self._stop_flag = False
        self._ready_event = event.Event()
        self._ready_flag = True

    def add_counter_to_read(self,counter):
        self.channels.append(AcquisitionChannel(counter.name,numpy.double, (1,)))

    def prepare(self):
        self._nb_acq_points = 0
        self._stop_flag = False
        self._ready_flag = True
        self._event.clear()

    def start(self):
        pass

    def stop(self):
        self._stop_flag = True
        self._trig_time = None
        self._event.set()

    def trigger(self):
        self._trig_time = time.time()
        self._event.set()

    def wait_ready(self):
        """
        will wait until the last triggered point is read
        """
        while not self._ready_flag:
            self._ready_event.wait()
            self._ready_event.clear()

    def reading(self):
        counter_name = [x.name for x in self.channels]
        if isinstance(self.device,CounterBase.ReadAllHandler):
            def read():
                return numpy.array(self.device.read_all(*counter_name),
                                   dtype=numpy.double)
        else:                   # read_all
            def read():
                return numpy.array(self.device.read(),
                                   dtype=numpy.double)
        while self._nb_acq_points < self.npoints:
            #trigger wait
            self._event.wait()
            self._event.clear()
            self._ready_flag = False
            trig_time = self._trig_time
            if trig_time is None: continue
            if self._stop_flag: break

            nb_read = 0
            acc_read_time = 0
            acc_value = numpy.zeros((len(counter_name),),dtype=numpy.double)
            stop_time = trig_time + self._count_time or 0
            #Counter integration loop
            while not self._stop_flag:
                start_read = time.time()
                acc_value += read()
                end_read = time.time()
                nb_read += 1
                acc_read_time += end_read - start_read

                current_time = time.time()
                if (current_time + (acc_read_time / nb_read)) > stop_time:
                    break
                sleep(0) # Be able to kill the task

            self._nb_acq_points += 1
            data = acc_value / nb_read
            channel_data = {name:data[index] for index,name in enumerate(counter_name)}
            dispatcher.send("new_data",self,
                            {"channel_data": channel_data})
            self._ready_flag = True
            self._ready_event.set()
            
