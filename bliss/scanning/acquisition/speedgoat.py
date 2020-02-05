# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import gevent

from bliss.scanning.chain import AcquisitionMaster, AcquisitionSlave


class SpeedgoatAcquisitionSlave(AcquisitionSlave):
    # trigger option: trigger_type=AcquisitionMaster.HARDWARE | AcquisitionMaster.SOFTWARE

    def __init__(self, acq_controller, npoints=1, ctrl_params=None):
        """
        Acquisition device for the speedgoat counters.
        """

        AcquisitionSlave.__init__(
            self,
            acq_controller,
            npoints=npoints,
            trigger_type=AcquisitionMaster.HARDWARE,
            ctrl_params=ctrl_params,
        )

        self.__stop_flag = False
        self.speedgoat = acq_controller.speedgoat
        self.daq = self.speedgoat.get_daq()
        self.nb_points = npoints

    def add_counter(self, counter):
        super().add_counter(counter)  # self.speedgoat.counters[counter.name])

    def wait_ready(self):
        # return only when ready
        return True

    def prepare(self):
        self.daq.daq_prepare(list(self._counters.keys()), self.nb_points)
        self.__stop_flag = False
        self.read_points = 0

    def start(self):
        # Start speedgoat DAQ device
        pass

    def stop(self):
        # stop the speedgoat DAQ system

        # Set the stop flag to stop the reading process
        self.__stop_flag = True

    def reading(self):

        # while not self.__stop_flag and self.speedgoat.DAQ.is_running():
        #    new_read_event = self
        #    if new_read_event != last_read_event:
        #        last_read_event = new_read_event
        #        gevent.sleep(100e-6)  # be able to ABORT the musst card
        #    else:
        #        gevent.sleep(10e-3)  # relax a little bit.
        # self._send_data(last_read_event)  # final send
        point_acquired = 0
        speedgoat_failed = 0
        while (not self.__stop_flag) and (not self.daq.daq_is_finished()):
            # print(f"acquired:{point_acquired}  read:{self.read_points}   total:{self.nb_points}")
            point_acquired = self.daq.daq_points_acquired()
            if point_acquired > 5:
                # print(f"Read {point_acquired} Points on the scope", end=" ... ")
                data = self.daq.scope_read(point_acquired)
                if data is not None:
                    # print("Done")
                    self.channels.update_from_array(data)
                    self.read_points = self.read_points + point_acquired
                else:
                    speedgoat_failed = speedgoat_failed + 1
                gevent.sleep(100e-6)  # be able to ABORT the musst card
            else:
                gevent.sleep(0.2)  # relax a little bit.

        point_acquired = self.daq.daq_points_acquired()
        self.read_points = self.read_points + point_acquired
        # print(f"LAST => acquired:{point_acquired}  read:{self.read_points}  total:{self.nb_points}   FAILED:{speedgoat_failed}")
        if point_acquired > 0:
            data = self.daq.scope_read(point_acquired)
            if data is None:
                data = self.daq.scope_read(point_acquired)
                if data is None:
                    data = self.daq.scope_read(point_acquired)
            self.channels.update_from_array(data)
