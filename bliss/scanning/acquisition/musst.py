# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import time
import gevent
from gevent import event
import numpy

from bliss.scanning.chain import AcquisitionMaster, AcquisitionSlave
from bliss.scanning.channel import AcquisitionChannel
from bliss.scanning.acquisition.counter import IntegratingCounterAcquisitionSlave


class MusstIntegratingAcquisitionSlave(IntegratingCounterAcquisitionSlave):
    def reading(self):

        musst = self.device.master_controller

        while not self._stop_flag and musst.STATE != musst.RUN_STATE:
            gevent.sleep(0.01)

        while musst.STATE == musst.RUN_STATE:
            gevent.sleep(0.01)

        counters = list(self._counters.keys())
        data = self.device.get_values(0, *counters)
        self._emit_new_data(data)


class MusstDefaultAcquisitionMaster(AcquisitionMaster):
    def __init__(self, controller, count_time=None, npoints=1, ctrl_params=None):

        super().__init__(controller, ctrl_params=ctrl_params)

        self._running_state = False
        self._event = event.Event()
        self.count_time = count_time

    @property
    def running_state(self):
        return self._running_state

    @property
    def name(self):
        return f"{self.device.name}_master"

    def prepare(self):
        self._running_state = False
        self._event.set()

    def start(self):
        self._running_state = True
        self._event.set()

    def stop(self):
        if self.device.STATE == self.device.RUN_STATE:
            self.device.ABORT

    def trigger(self):
        self.device.ct(self.count_time, wait=False)
        self.trigger_slaves()

    def trigger_ready(self):
        return self.device.STATE != self.device.RUN_STATE

    def wait_ready(self):
        while self.device.STATE == self.device.RUN_STATE:
            gevent.idle()
        self._running_state = False
        self._event.set()


class MusstAcquisitionMaster(AcquisitionMaster):
    def __init__(
        self,
        musst_dev,
        program=None,
        program_data=None,
        program_start_name=None,
        program_abort_name=None,
        vars=None,
        program_template_replacement=None,
        ctrl_params=None,
        **keys,
    ):
        """
        Acquisition master for the musst card.

        program -- program filename you need to load for your scan
        program_data -- program data string you need to load for you scan
            Either program or program_data needs to be specified. 
            If both are set, program_data is used rather than program.
        program_start_name -- name of program to be started (RUN musst command)
        program_abort_name -- name of program called on cleanup
        program_template_replacement -- substitution variable before sending it to the card
        vars -- all variable you want to set before the musst program starts
        """
        AcquisitionMaster.__init__(
            self,
            musst_dev,
            name=musst_dev.name,
            trigger_type=AcquisitionMaster.HARDWARE,
            ctrl_params=ctrl_params,
            **keys,
        )
        self.musst = musst_dev
        self.program = program
        self.program_data = program_data
        if self.program is None and self.program_data is None:
            raise ValueError("Either program or program_data needs to be set")
        self.program_start_name = program_start_name
        self.program_abort_name = program_abort_name
        if program_template_replacement is not None:
            self.program_template_replacement = program_template_replacement
        else:
            self.program_template_replacement = dict()
        self.vars = vars if vars is not None else dict()

        self.next_vars = None
        self._iter_index = 0
        self._running_state = False
        self._event = event.Event()
        self._start_epoch = None

    @property
    def running_state(self):
        return self._running_state

    @property
    def name(self):
        return f"{self.device.name}_master"

    def __iter__(self):
        self._iter_index = 0
        if isinstance(self.vars, (list, tuple)):
            vars_iter = iter(self.vars)
            while True:
                self.next_vars = next(vars_iter)
                yield self
                self._iter_index += 1
        else:
            self.next_vars = self.vars
            while True:
                yield self
                self._iter_index += 1
                if not self.parent:
                    break

    def prepare(self):
        if self._iter_index == 0:
            if self.program_data is not None:
                self.musst.upload_program(
                    self.program_data,
                    template_replacement=self.program_template_replacement,
                )
            else:
                self.musst.upload_file(
                    self.program, template_replacement=self.program_template_replacement
                )

        for var_name, value in self.next_vars.items():
            self.musst.putget("VAR %s %s" % (var_name, value))
        self._start_epoch = None
        self._running_state = False
        self._event.set()

    def start(self):
        self.musst.run(self.program_start_name)
        self._start_epoch = time.time()
        self._running_state = True
        self._event.set()

    def stop(self):
        if self.musst.STATE == self.musst.RUN_STATE:
            self.musst.ABORT
            if self.program_abort_name:
                self.musst.run(self.program_abort_name)
                self.wait_ready()

    def trigger_ready(self):
        return self.musst.STATE != self.musst.RUN_STATE

    def wait_ready(self):
        while self.musst.STATE == self.musst.RUN_STATE:
            gevent.idle()
        self._running_state = False
        self._event.set()


def MusstAcquisitionSlave(
    musst_dev,
    program=None,
    program_start_name=None,
    program_abort_name=None,
    store_list=None,
    vars=None,
    program_template_replacement=None,
):
    """
    This will create either a simple MusstAcquisitionSlave or
    MusstAcquisitionMaster + MusstAcquisitionSlave for compatibility reason.
    This chose is made if you provide a **program**.
    """
    if program is None:
        return _MusstAcquisitionSlave(musst_dev, store_list=store_list)
    else:
        master = MusstAcquisitionMaster(
            musst_dev,
            program=program,
            program_start_name=program_start_name,
            program_abort_name=program_abort_name,
            vars=vars,
            program_template_replacement=program_template_replacement,
        )
        return _MusstAcquisitionSlave(master, store_list=store_list)


class _MusstAcquisitionSlave(AcquisitionSlave):
    class Iterator(object):
        def __init__(self, acq_device):
            self.__device = acq_device
            self.__current_iter = iter(acq_device.device)

        def __next__(self):
            next(self.__current_iter)
            return self.__device

    def __init__(self, musst, store_list=None, ctrl_params=None):
        """
        Acquisition device for the musst card.

        store_list -- a list of variable you store in musst memory during the scan
        """
        AcquisitionSlave.__init__(
            self, musst, trigger_type=AcquisitionSlave.HARDWARE, ctrl_params=ctrl_params
        )
        store_list = store_list if store_list is not None else list()
        self.channels.extend(
            (
                AcquisitionChannel(f"{self.name}:{name}", numpy.int32, ())
                for name in store_list
            )
        )
        self.__stop_flag = False
        if isinstance(musst, MusstAcquisitionMaster):
            self._master = musst
        else:
            self._master = None
        self.__musst_device = None

    def __iter__(self):
        if isinstance(self.device, MusstAcquisitionMaster):
            return _MusstAcquisitionSlave.Iterator(self)
        raise TypeError("'MusstAcquisitionSlave' is not iterable")

    def prepare(self):
        if isinstance(self.device, MusstAcquisitionMaster):
            self.__musst_device = self._master.device
            self._master.prepare()
        else:
            master = self.parent
            if not isinstance(master, MusstAcquisitionMaster):
                raise RuntimeError(
                    "MusstAcquisitionSlave must have a MusstAcquisitionMaster has"
                    " parent here it's (%r)" % master
                )
            elif master.device != self.device:
                raise RuntimeError(
                    "MusstAcquisitionMaster doesn't have the same musst device"
                    " master has (%s) and device (%s)"
                    % (master.device.name, self.device.name)
                )
            self.__musst_device = self.device
            self._master = master

    @property
    def musst(self):
        return self.__musst_device

    @property
    def start_epoch(self):
        return self._master._start_epoch

    def start(self):
        if isinstance(self.device, MusstAcquisitionMaster):
            self._master.start()

    def stop(self):
        if isinstance(self.device, MusstAcquisitionMaster):
            self._master.stop()
        self.__stop_flag = True
        self._master._event.set()

    def trigger_ready(self):
        if isinstance(self.device, MusstAcquisitionMaster):
            return self.device.trigger_ready()
        return True

    def wait_ready(self):
        if isinstance(self.device, MusstAcquisitionMaster):
            self._master.wait_ready()
        self.wait_reading()

    def reading(self):
        master = self._master
        last_read_event = 0

        # wait the master to start
        while not self.__stop_flag and not master._running_state:
            master._event.clear()
            master._event.wait()

        while not self.__stop_flag and master._running_state:
            new_read_event = self._send_data(last_read_event)
            if new_read_event != last_read_event:
                last_read_event = new_read_event
                gevent.sleep(100e-6)  # be able to ABORT the musst card
            else:
                gevent.sleep(10e-3)  # relax a little bit.
        self._send_data(last_read_event)  # final send

    def _send_data(self, last_read_event):
        data = self.musst.get_data(len(self.channels), last_read_event)
        if data.size > 0:
            self.channels.update_from_array(data)
            nb_event_read = data.shape[0]
            last_read_event += nb_event_read
        return last_read_event
