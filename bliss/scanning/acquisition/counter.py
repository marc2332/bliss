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
from bliss.common.measurement import SamplingCounter

class CounterAcqDevice(AcquisitionDevice):
    SIMPLE_AVERAGE,TIME_AVERAGE,INTEGRATE = range(3)

    def __init__(self,counter,
                 count_time=None,npoints=1,
                 mode=SIMPLE_AVERAGE,**keys):
        """
        Helper to manage acquisition of a sampling counter.

        count_time -- the master integration time.
        npoints -- number of point for this acquisition
        mode -- three mode are available *SIMPLE_AVERAGE* (the default)
        which sum all the sampling values and divide by the number of read value.
        the *TIME_AVERAGE* which sum all integration  then divide by the sum
        of time spend to measure all values. And *INTEGRATION* which sum all integration
        and then normalize it when the *count_time*.
        """
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
        if not isinstance(counter,SamplingCounter.ReadAllHandler):
            self.channels.append(AcquisitionChannel(counter.name,numpy.double, (1,)))
        self._nb_acq_points = 0
        self._event = event.Event()
        self._stop_flag = False
        self._ready_event = event.Event()
        self._ready_flag = True
        self.__mode = mode
        self.__counters_list = list()

    @property
    def mode(self):
        return self.__mode
    @mode.setter
    def mode(self,value):
        self.__mode = value

    def add_counter_to_read(self,counter):
        self.__counters_list.append(counter)
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
        if isinstance(self.device, SamplingCounter.GroupedReadHandler):
            def read():
                return numpy.array(self.device.read(*self.__counters_list),
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
                read_value = read()
                end_read = time.time()
                read_time = end_read - start_read
                
                if self.__mode != CounterAcqDevice.TIME_AVERAGE:
                    acc_value += read_value
                else:
                    acc_value += read_value * (end_read - start_read)
                nb_read += 1
                acc_read_time += end_read - start_read

                current_time = time.time()
                if (current_time + (acc_read_time / nb_read)) > stop_time:
                    break
                sleep(0) # Be able to kill the task
            self._nb_acq_points += 1
            if self.__mode == CounterAcqDevice.TIME_AVERAGE:
                data = acc_value / nb_read
            else:
                data = acc_value / acc_read_time
                
            if self.__mode == CounterAcqDevice.INTEGRATE:
                data *= self._count_time
            
            channel_data = {name:data[index] for index,name in enumerate(counter_name)}
            dispatcher.send("new_data",self,
                            {"channel_data": channel_data})
            self._ready_flag = True
            self._ready_event.set()
            

class IntegratingAcqDevice(AcquisitionDevice):
    def __init__(self,integrating_device,
                 count_time=None,npoints=1,**keys):
        prepare_once = keys.pop('prepare_once',npoints > 1 and True or False)
        start_once = keys.pop('start_once',npoints > 1 and True or False)
        npoints = max(1,npoints)
        AcquisitionDevice.__init__(self, counter, integrating_device.name, "zerod",
                                   npoints=npoints,
                                   trigger_type=AcquisitionDevice.SOFTWARE,
                                   prepare_once=prepare_once,
                                   start_once=start_once,
                                   **keys)
        self._count_time = count_time
        self.channels.append(AcquisitionChannel(integrating_device.name,numpy.double, (1,)))
        self._nb_acq_points = 0

    def prepare(self):
        self._nb_acq_points = 0
        self._stop_flag = False

    def start(self):
        pass

    def stop(self):
        self._stop_flag = True

    def trigger(self):
        pass
    
    def reading(self):
        from_point_index = 0
        while self._nb_acq_points < self.npoints and not self._stop_flag:
            data = self.device.get_value(from_point_index)
            if data:
                from_point_index += len(data)
                self._nb_acq_points += len(data)
                channel_data = {self.name:data}
                dispatcher.send("new_data",self,
                                {"channel_data": channel_data})
                gevent.idle()
            else:
                gevent.sleep(count_time/2.)
            
