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


class MusstAcquisitionMaster(AcquisitionMaster):
    def __init__(
        self,
        musst_dev,
        program=None,
        program_start_name=None,
        program_abort_name=None,
        vars=None,
        program_template_replacement=None,
        **keys
    ):
        """
        Acquisition master for the musst card.

        program -- the program you need to load for your scan
        program_template_replacement -- substitution variable before sending it to the card
        vars -- all variable you want to set before the musst program starts
        """
        AcquisitionMaster.__init__(
            self, musst_dev, trigger_type=AcquisitionMaster.HARDWARE, **keys
        )
        self.musst = musst_dev
        self.program = program
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

    @property
    def running_state(self):
        return self._running_state

    @property
    def name(self):
        return self.device.name

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
            self.musst.upload_file(
                self.program, template_replacement=self.program_template_replacement
            )

        for var_name, value in self.next_vars.items():
            self.musst.putget("VAR %s %s" % (var_name, value))
        self._running_state = False
        self._event.set()

    def start(self):
        self.musst.run(self.program_start_name)
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


def MusstAcquisitionDevice(
    musst_dev,
    program=None,
    program_start_name=None,
    program_abort_name=None,
    store_list=None,
    vars=None,
    program_template_replacement=None,
):
    """
    This will create either a simple MusstAcquisitionDevice or
    MusstAcquisitionMaster + MusstAcquisitionDevice for compatibility reason.
    This chose is made if you provide a **program**.
    """
    if program is None:
        return _MusstAcquisitionDevice(musst_dev, store_list=store_list)
    else:
        master = MusstAcquisitionMaster(
            musst_dev,
            program=program,
            program_start_name=program_start_name,
            program_abort_name=program_abort_name,
            vars=vars,
            program_template_replacement=program_template_replacement,
        )
        return _MusstAcquisitionDevice(master, store_list=store_list)


class _MusstAcquisitionDevice(AcquisitionDevice):
    class Iterator(object):
        def __init__(self, acq_device):
            self.__device = acq_device
            self.__current_iter = iter(acq_device.device)

        def __next__(self):
            next(self.__current_iter)
            return self.__device

    def __init__(self, musst, store_list=None):
        """
        Acquisition device for the musst card.

        store_list -- a list of variable you store in musst memory during the scan
        """
        AcquisitionDevice.__init__(self, musst, trigger_type=AcquisitionMaster.HARDWARE)
        store_list = store_list if store_list is not None else list()
        self.channels.extend(
            (AcquisitionChannel(self, name, numpy.int32, ()) for name in store_list)
        )
        self.__stop_flag = False
        if isinstance(musst, MusstAcquisitionMaster):
            self._master = musst
        else:
            self._master = None
        self.__musst_device = None

    def __iter__(self):
        if isinstance(self.device, MusstAcquisitionMaster):
            return _MusstAcquisitionDevice.Iterator(self)
        raise TypeError("'MusstAcquisitionDevice' is not iterable")

    def prepare(self):
        if isinstance(self.device, MusstAcquisitionMaster):
            self.__musst_device = self._master.device
            self._master.prepare()
        else:
            master = self.parent
            if not isinstance(master, MusstAcquisitionMaster):
                raise RuntimeError(
                    "MusstAcquisitionDevice must have a MusstAcquisitionMaster has"
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
