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
`EmhAcquisitionSlave` class. It takes the following arguments:

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
from bliss.scanning.acquisition.emh import EmhAcquisitionSlave

# Get controllers from config
config = get_config()
m0 = config.get("roby")
emh = config.get("emh2")

# Instanciate the acquisition device
device = EmhAcquisitionSlave(emh, 10, 0.001, trigger="DIO_1")

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

from bliss.scanning.chain import AcquisitionSlave
import gevent
import numpy as np

from bliss.controllers.emh import TRIGGER_INPUTS


class EmhAcquisitionSlave(AcquisitionSlave):
    """ TO BE USED IN HARDWARE TRIGGERED MODE ONLY """

    def __init__(self, emh, trigger, int_time, npoints, counter_list, ctrl_params=None):
        """ Acquisition device for EMH counters.
        """
        AcquisitionSlave.__init__(
            self,
            emh,
            counters=counter_list,
            name=emh.name,
            npoints=npoints,
            trigger_type=AcquisitionSlave.HARDWARE,
            ctrl_params=ctrl_params,
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

    # def add_counter(self, counter):
    #    self.channels.append(AcquisitionChannel(counter.name, np.float, ()))

    def wait_ready(self):
        # return only when ready
        return True

    def prepare(self):
        # print("=====  STOP")
        if self.device.get_acq_state() != "STATE_ON":
            self.device.stop_acq()
            gevent.sleep(0.1)

        self.device.set_trigger_mode("HARDWARE")
        # self.device.set_trigger_mode(self.trigger_type)
        gevent.sleep(0.1)

        # print("=====  trigger input")
        self.device.set_trigger_input(self.trigger)
        gevent.sleep(0.1)
        # print("=====  polarity")
        self.device.set_trigger_polarity("RISING")
        gevent.sleep(0.1)

        # print("=====  inttime")
        self.device.set_acq_time(self.int_time)
        gevent.sleep(0.1)

        self.device.set_acq_trig(self.npoints)
        gevent.sleep(0.1)
        # print("=====  acq_trig (nb_points)  %d" % self.device.get_acq_trig())
        gevent.sleep(0.1)

        self.device.start_acq()
        gevent.sleep(0.1)

        self.__stop_flag = False

    def start(self):
        pass

    def stop(self):
        # stop the speedgoat DAQ system

        # Set the stop flag to stop the reading process
        self.__stop_flag = True
        self.device.stop_acq()
        gevent.sleep(1e-3)

    def reading(self):

        point_acquired = 0
        point_last_read = 0
        """
        while (not self.__stop_flag) and (point_acquired < self.npoints):
            point_acquired = self.device.get_acq_counts()


        (timestamps, currents) = self.device.get_acq_data(
                    point_last_read, (point_acquired - 1) - point_last_read
                )
                
        data_send = np.zeros((7, len(currents[0]) + 1))
        for ch in range(7):
            data_send[ch][0] = currents[ch][0]
            data_send[ch][1:] = currents[ch][:]
        data_send = np.transpose(data_send)

        self.channels.update_from_array(data_send)
        
        
        """
        while (not self.__stop_flag) and (point_acquired < self.npoints):
            point_acquired = self.device.get_acq_counts()
            # print("\nEMH %s acquired %d     read %d      total  %d"%(self.device.name, point_acquired, point_last_read, self.npoints))
            if ((point_acquired - 1) > point_last_read) and (point_acquired > 1):

                (timestamps, currents) = self.device.get_acq_data(
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

        point_acquired = self.device.get_acq_counts()
        # gevent.sleep(0.3)
        if (point_acquired - 1) > point_last_read:
            (timestamps, currents) = self.device.get_acq_data(
                point_last_read, (point_acquired - 1) - point_last_read
            )
            data_send = np.transpose(currents)
            point_last_read = point_acquired - 1
            self.channels.update_from_array(data_send)
            # gevent.sleep(0.3)
            # print("EMH acquired %d     read %d"%(point_acquired, point_last_read))
        # print("\n FINAL EMH %s acquired %d     read %d      total  %d"%(self.device.name, point_acquired, point_last_read, self.npoints))
