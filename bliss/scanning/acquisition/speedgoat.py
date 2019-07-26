# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from ..chain import AcquisitionMaster, AcquisitionDevice, AcquisitionChannel
from bliss.common.event import dispatcher
import gevent
from gevent import event
import numpy

from bliss import setup_globals

from bliss.scanning.scan import Scan
from bliss.scanning.chain import AcquisitionChain, AcquisitionChannel
from bliss.scanning.acquisition.motor import MotorMaster
from bliss.scanning.acquisition.musst import MusstAcquisitionMaster
from bliss.scanning.acquisition.musst import MusstAcquisitionDevice


def sg_test_musst_start(point_nb, point_time):

    chain = AcquisitionChain()

    ##########################
    # MUSST: get mussst object
    #
    musstdcm = setup_globals.musstdcm

    # MUSST: TO BE REMOVED (WORKAROUND)
    musstdcm.ABORT
    musstdcm.CLEAR

    # MUSST: channel(s) to be read
    store_mask = 0
    store_mask |= 1 << 0  # CH0 = time
    store_mask |= 1 << 1  # CH1 = trajectory axis

    schan = 0
    sdata = int(0.1 * musstdcm.get_timer_factor())
    pchan = 0
    pdata = int(point_time * musstdcm.get_timer_factor())
    pscandir = 0
    sscandir = 0

    # MUSST: acquisition master
    musst_master = MusstAcquisitionMaster(
        musstdcm,
        program="zapintgen.mprg",
        program_start_name="HOOK",
        vars={
            "SMODE": 1,  # 0=external trigger / 1=internal channel
            "SCHAN": schan,  # if SMODE=1 0=time 1=ch1 2=ch2 3=ch3 4=ch4 5=ch5 6=ch6
            "SDATA": sdata,
            "PMODE": 1,
            "PCHAN": pchan,
            "PDATA": pdata,
            "NPOINT": int(point_nb),
            "PSCANDIR": pscandir,  # 0=positive direction 1=negative direction
            "SSCANDIR": sscandir,  # 0=positive direction 1=negative direction
            "STOREMSK": store_mask,
        },
    )

    # MUSST: memory configuration
    musstdcm.set_histogram_buffer_size(2048, 1)  # Histogram (MCA)
    musstdcm.set_event_buffer_size(int(524288 / 16), 1)  # Buffers

    # musst_acq = MusstAcquisitionDevice(musstdcm, store_list=["time", "trajmot"])
    # MUSST: add musst in the acquisition chain
    # chain.add(musst_master, musst_acq)
    # musst_master.add_external_channel(musst_acq, 'time', 'mussttime')
    musst_var = iter(musst_master)
    musst_var.next()
    musst_master.prepare()
    musst_master.start()


def sg_test_speedgoat(point_nb, point_time, mg):
    goat = setup_globals.goat1
    daq = goat.get_daq()

    cnt_list = []
    for name in mg.available:
        cnt_list.append(goat.counters[name])

    daq.daq_prepare(cnt_list, point_nb)

    sg_test_musst_start(point_nb, point_time)

    read_points = 0
    point_acquired = 0
    speedgoat_failed = 0

    while not daq.daq_is_finished():

        print(f"Acquired:{point_acquired}  read:{read_points}   total:{point_nb}")

        point_acquired = daq.daq_points_acquired()

        if point_acquired > 5:

            print(f"    Read {point_acquired} Points on the scope", end=" ... ")
            data = daq.scope_read(point_acquired)
            print("Done")

            if data is not None:
                read_points = read_points + point_acquired
            else:
                speedgoat_failed = speedgoat_failed + 1

            gevent.sleep(100e-6)  # be able to ABORT the musst card
        else:
            gevent.sleep(0.2)  # relax a little bit.

    point_acquired = daq.daq_points_acquired()
    read_points = read_points + point_acquired

    print(
        f"LAST => acquired:{point_acquired} read:{read_points} total:{point_nb} FAILED:{speedgoat_failed}",
        end=" ... ",
    )

    if point_acquired > 0:
        data = daq.scope_read(point_acquired)
        if data is None:
            print("FALIED\nRETRY LAST #1", end=" ... ")
            data = daq.scope_read(point_acquired)
            if data is None:
                print("FAILED\nRETRY LAST #2", end=" ... ")
                data = daq.scope_read(point_acquired)
                if data is None:
                    print("FAILED, give up !!!")
                else:
                    print("Done")
            else:
                print("Done")
        else:
            print("Done")


class SpeedgoatAcquisitionDevice(AcquisitionDevice):
    # option de trigger: trigger_type=AcquisitionMaster.HARDWARE | AcquisitionMaster.SOFTWARE
    def __init__(self, speedgoat, npoints, counter_list):
        """
        Acquisition device for the speedgoat counters.
        """
        AcquisitionDevice.__init__(
            self, speedgoat, npoints=npoints, trigger_type=AcquisitionMaster.HARDWARE
        )

        self.channels.extend(
            (AcquisitionChannel(name, numpy.float, ()) for name in counter_list)
        )

        self.__stop_flag = False
        self.speedgoat = speedgoat
        self.daq = self.speedgoat.get_daq()
        self.nb_points = npoints
        self.counters = []
        for name in counter_list:
            self.counters.append(self.speedgoat.counters[name])

    def wait_ready(self):
        # return only when ready
        return True

    def prepare(self):
        self.daq.daq_prepare(self.counters, self.nb_points)
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
        try:
            self._reading()
        except:
            import traceback

            traceback.print_exc()
            import pdb

            pdb.set_trace()
            raise

    def _reading(self):

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
