# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""\
EMH scan support
=================


The EMH is integrated in continuous scans by instanciating the
`EmhAcquisitionDevice` class. It takes the following arguments:

 - `emh`: the emh controller
 - `npoints`: the number of points to acquire
 - `start`: the start trigger, default is Signal.SOFT
 - `trigger`: the point trigger, default is Signal.SOFT
 - `frequency`: only used in Signal.FREQ trigger mode
 - `counters`: the EMH counters to broadcast


Here's an example of a continuous scan using a Emh electrometer::

# Imports
from bliss.scanning.scan import Scan
from bliss.controllers.emh import Signal.SOFT
from bliss.config.static import get_config
from bliss.scanning.chain import AcquisitionChain
from bliss.scanning.acquisition.motor import MotorMaster
from bliss.scanning.acquisition.emh import EmhAcquisitionDevice

# Get controllers from config
config = get_config()
m0 = config.get("roby")
emh = config.get("emh2")

# Instanciate the acquisition device
device = EmhAcquisitionDevice(emh, 10, 0.001, trigger="DIO_1")

# Counters can be added after instanciation
device.add_counters(emh.counters)

 chain
chain = AcquisitionChain()
chain.add(MotorMaster(m0, 0, 1, time=1.0, npoints=10), device)

# Run scan
scan = Scan(chain)
scan.run()

# Get the data
data = scans.get_data(scan)
print(data['CALC2'])
"""

from ..chain import AcquisitionMaster, AcquisitionDevice
from ..channel import AcquisitionChannel
from bliss.common.measurement import BaseCounter, counter_namespace
from bliss.common.event import dispatcher
import gevent
from gevent import event
import numpy as np

from bliss.controllers.emh import TRIGGER_INPUTS


class EmhAcquisitionDevice(AcquisitionDevice):
    def __init__(self, emh, trigger, int_time, npoints, counter_list):
        """ Acquisition device for EMH counters.
        """
        AcquisitionDevice.__init__(
            self,
            emh,
            emh.name,
            npoints=npoints,
            trigger_type=AcquisitionMaster.HARDWARE,
        )

        self.channels.extend(
            (AcquisitionChannel(self, name, np.float, ()) for name in counter_list)
        )

        if trigger not in TRIGGER_INPUTS:
            raise ValueError("{!r} is not a valid trigger".format(trigger))
        self.trigger = trigger
        # print("TRIGGER %s" % self.trigger)

        int_time = int_time - 0.4
        if int_time < 0.320:
            int_time = 0.320
        self.int_time = int_time

        self.__stop_flag = False
        self.emh = emh
        self.nb_points = npoints

    def wait_ready(self):
        # return only when ready
        return True

    def prepare(self):
        # print("=====  STOP")
        if self.emh.get_acq_state() != "STATE_ON":
            self.emh.stop_acq()
            gevent.sleep(0.1)

        # print("=====  trigger mode")
        self.emh.set_trigger_mode("HARDWARE")
        gevent.sleep(0.1)
        # print("=====  trigger input")
        self.emh.set_trigger_input(self.trigger)
        gevent.sleep(0.1)
        # print("=====  polarity")
        self.emh.set_trigger_polarity("RISING")
        gevent.sleep(0.1)
        # print("=====  inttime")
        self.emh.set_acq_time(self.int_time)
        gevent.sleep(0.1)

        self.emh.set_acq_trig(self.nb_points)
        gevent.sleep(0.1)
        # print("=====  acq_trig (nb_points)  %d" % self.emh.get_acq_trig())
        gevent.sleep(0.1)

        self.emh.start_acq()
        gevent.sleep(0.1)

        self.__stop_flag = False

    def start(self):
        pass

    def stop(self):
        # stop the speedgoat DAQ system

        # Set the stop flag to stop the reading process
        self.__stop_flag = True
        self.emh.stop_acq()
        gevent.sleep(1e-3)

    def reading(self):

        point_acquired = 0
        point_last_read = 0
        """
        while (not self.__stop_flag) and (point_acquired < self.nb_points):
            point_acquired = self.emh.get_acq_counts()


        (timestamps, currents) = self.emh.get_acq_data(
                    point_last_read, (point_acquired - 1) - point_last_read
                )
                
        data_send = np.zeros((7, len(currents[0]) + 1))
        for ch in range(7):
            data_send[ch][0] = currents[ch][0]
            data_send[ch][1:] = currents[ch][:]
        data_send = np.transpose(data_send)

        self.channels.update_from_array(data_send)
        
        
        """
        while (not self.__stop_flag) and (point_acquired < self.nb_points):
            point_acquired = self.emh.get_acq_counts()
            # print("\nEMH %s acquired %d     read %d      total  %d"%(self.emh.name, point_acquired, point_last_read, self.nb_points))
            if ((point_acquired - 1) > point_last_read) and (point_acquired > 1):

                (timestamps, currents) = self.emh.get_acq_data(
                    point_last_read, (point_acquired - 1) - point_last_read
                )

                if point_last_read == 0:
                    data_send = np.zeros((7, len(currents[0]) + 1))
                    for ch in range(7):
                        data_send[ch][0] = currents[ch][0]
                        data_send[ch][1:] = currents[ch][:]
                    data_send = np.transpose(data_send)
                else:
                    data_send = np.transpose(currents)

                self.channels.update_from_array(data_send)
                point_last_read = point_acquired - 1

                gevent.sleep(100e-6)  # be able to ABORT the musst card
                # gevent.sleep(0.1)
            else:
                gevent.sleep(10e-3)  # relax a little bit.

        point_acquired = self.emh.get_acq_counts()
        # gevent.sleep(0.3)
        if (point_acquired - 1) > point_last_read:
            (timestamps, currents) = self.emh.get_acq_data(
                point_last_read, (point_acquired - 1) - point_last_read
            )
            data_send = np.transpose(currents)
            point_last_read = point_acquired - 1
            self.channels.update_from_array(data_send)
            # gevent.sleep(0.3)
            # print("EMH acquired %d     read %d"%(point_acquired, point_last_read))
        # print("\n FINAL EMH %s acquired %d     read %d      total  %d"%(self.emh.name, point_acquired, point_last_read, self.nb_points))
