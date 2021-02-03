# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import time
import gevent.event

from bliss.common import event
from bliss.scanning.chain import AcquisitionSlave
from bliss.controllers.mca import TriggerMode, PresetMode
from bliss.common.logtools import log_debug, get_logger
from bliss import global_map, global_log

# MCA Acquisition Slave


class McaAcquisitionSlave(AcquisitionSlave):

    READY = "READY"
    TRIGGERED = "TRIGGERED"

    SOFT = TriggerMode.SOFTWARE
    SYNC = TriggerMode.SYNC
    GATE = TriggerMode.GATE

    def __init__(
        self,
        *mca_or_mca_counters,
        npoints=1,
        trigger_mode=SOFT,
        preset_time=1.0,
        block_size=None,
        polling_time=0.1,
        refresh_rate=0.1,
        spectrum_size=None,
        prepare_once=True,
        start_once=True,
        read_all_triggers=False,
        ctrl_params=None,
    ):

        # Logging
        global_map.register(self, parents_list=None, tag="McaAcqSlave")

        # logger = get_logger("McaAcqSlave")
        # Activate logging
        #        logger.setLevel("DEBUG")
        #        global_log.debugon("McaAcqSlave")

        log_debug(self, "__init__()")

        # Checks

        # Trigger type
        if isinstance(trigger_mode, str):
            trigger_mode = eval(
                trigger_mode,
                {
                    "TriggerMode": TriggerMode,
                    "SOFTWARE": McaAcquisitionSlave.SOFT,
                    "SYNC": McaAcquisitionSlave.SYNC,
                    "GATE": McaAcquisitionSlave.GATE,
                },
            )
        if trigger_mode == self.SOFT:
            trigger_type = McaAcquisitionSlave.SOFTWARE
        else:
            trigger_type = McaAcquisitionSlave.HARDWARE

        if isinstance(preset_time, list):
            prepare_once = False
            start_once = False
            npoints = 1

        # Parent call
        super().__init__(
            *mca_or_mca_counters,
            npoints=npoints,
            trigger_type=trigger_type,
            prepare_once=prepare_once,
            start_once=start_once,
            ctrl_params=ctrl_params,
        )

        # self.device is now known.
        # print(self.device.name)

        # Internals
        self.acquisition_gen = None

        # Default value
        if spectrum_size is None:
            spectrum_size = self.device.spectrum_size

        # Extra arguments
        self.block_size = block_size
        self.refresh_rate = refresh_rate
        # Manage scans using software trigger with variable preset_time per point
        if isinstance(preset_time, list):
            self.preset_time_list = preset_time
            self.preset_time_index = 0
            self.preset_time = preset_time[0]
        else:
            self.preset_time_list = None
            self.preset_time_index = 0
            self.preset_time = preset_time
        self.trigger_mode = trigger_mode
        self.polling_time = polling_time
        self.spectrum_size = spectrum_size
        self.read_all_triggers = read_all_triggers
        self.expected_npoints = npoints

        # Reading Queue
        self._pending_datas = gevent.queue.Queue()

        # Add counters
        self._trigger_event = gevent.event.Event()
        # should be True for the first wait_ready
        self._trigger_event.set()

    # Counter management

    def _do_add_counter(self, counter):
        super()._do_add_counter(counter)
        counter.register_device(self)

    # Mode properties

    @property
    def soft_trigger_mode(self):
        return self.trigger_mode == self.SOFT

    @property
    def sync_trigger_mode(self):
        return self.trigger_mode == self.SYNC

    @property
    def gate_trigger_mode(self):
        return self.trigger_mode == self.GATE

    # Standard methods

    def prepare(self):
        """Prepare the acquisition."""
        # The MCA should always take mca_params["npoints"] = number of intervals  (i.e x_npoints - 1)
        #
        # Internally if using trigger_mode==SYNC, the mca.hardware_points is set to  mca_params["npoints"] + 1
        # in order to compensate the fact that in this mode the mca starts the acquisition on scan start()
        # and not when receiving the first hard trig when x_mot_pos == x_start.
        # The MCA acqObj handles this internally and it discards the first measure done @ x_mot_pos == x_start
        #
        #
        # (TO BE TESTED) If using trigger_mode==GATE, the acquisition is
        # expected to start when receiving the first trigger (up or down edge of
        # the gate).

        # Generic configuration
        self.device.trigger_mode = self.trigger_mode
        self.device.spectrum_size = self.spectrum_size
        self.device.refresh_rate = self.refresh_rate

        # Mode-specfic configuration
        self.expected_npoints = self.npoints

        if self.soft_trigger_mode:
            # SOFTWARE
            self.device.preset_mode = PresetMode.REALTIME

            # Manage variable integration time.
            # In this mode the mca prepare method is called at each point.
            if self.preset_time_list is not None:
                if self.preset_time_index < len(self.preset_time_list):
                    self.preset_time = self.preset_time_list[self.preset_time_index]
                    self.preset_time_index += 1
            self.device.preset_value = self.preset_time
            self.read_all_triggers = True  # Forced to True with this trig mode.

        elif self.sync_trigger_mode:
            # SYNC
            # With this trigger mode read_all_triggers can be True or False
            # (user choice via acq_params)
            self.device.hardware_points = self.npoints + 1
            self.device.block_size = self.block_size
            self.expected_npoints = self.npoints + 1

        elif self.gate_trigger_mode:
            # GATE
            self.device.hardware_points = self.npoints
            self.device.block_size = self.block_size
            self.read_all_triggers = True  # forced to True with this trig mode

        if self.block_size is None:
            self.block_size = self.device.block_size

        self._pending_datas = gevent.queue.Queue()
        event.connect(self.device, "data", self._data_rx)

    def start(self):
        """Start the acquisition."""
        # log_debug(self, "start()")
        if self.soft_trigger_mode:
            return
        self.device.start_acquisition()
        if not self.soft_trigger_mode:
            self.device.start_hardware_reading()

    def stop(self):
        """Stop the acquistion."""
        # log_debug(self, "stop()")
        self.device.stop_acquisition()
        event.disconnect(self.device, "data", self._data_rx)
        self._pending_datas.put(StopIteration)
        if not self.soft_trigger_mode:
            self.device.wait_hardware_reading()

    def trigger(self):
        """Send a software trigger."""
        self._trigger_event.clear()
        self.device.trigger()
        self._trigger_event.set()

    def wait_ready(self):
        """ ??? """
        if self.preset_time_list is not None:
            self._trigger_event.wait()

    def reading(self):
        """Spawn by the chain."""
        self._init_datas()
        _accum = 0
        log_debug(self, "reading() start")

        for nb, values in enumerate(self._pending_datas):
            if isinstance(values, StopIteration):
                # ???
                return
            elif isinstance(values, Exception):
                # ???
                raise values

            # do not publish first point if read_all_triggers is
            # False (for SYNC mode)
            if self.read_all_triggers is False and nb == 0:
                continue

            spectrums, stats = values
            self._append_datas(spectrums, stats)
            _accum += 1

            if _accum == self.block_size:
                self._publish_datas()
                _accum = 0

            # break when we have received the expected number of points
            # it depends on the trigger_mode and device.hardware_points
            # (see prepare)
            #             - 1 because the 'for-loop+enumerate' start at i=0
            if nb == self.expected_npoints - 1:
                self._publish_datas()
                break

            gevent.sleep(0.)
            log_debug(self, "reading() end")

    def _init_datas(self):
        self._datas = dict()
        for counter in self._counters:
            self._datas[f"{self.name}:{counter.name}"] = list()

    def _append_datas(self, spectrums, stats):
        spectrums = self.device._convert_spectrums(spectrums)
        stats = self.device._convert_statistics(stats)

        for counter in self._counters:
            point = counter.feed_point(spectrums, stats)
            self._datas[f"{self.name}:{counter.name}"].append(point)

    def _publish_datas(self):
        for counter in self._counters:
            name = f"{self.name}:{counter.name}"
            data = self._datas[name]
            if len(data):
                self.channels.update({name: data})
                data.clear()

    def _data_rx(self, values, signal):
        self._pending_datas.put(values)


# HWSCA Acquisition Slave


class HWScaAcquisitionSlave(AcquisitionSlave):
    def __init__(
        self, mca, npoints=0, prepare_once=True, start_once=True, ctrl_params=None
    ):
        # Parent call
        super().__init__(
            mca,
            npoints=npoints,
            prepare_once=prepare_once,
            start_once=start_once,
            ctrl_params=ctrl_params,
        )

        self._time_start = 0
        self._time_stop = 0
        self.mca = mca
        self.spectrum_size = mca.spectrum_size
        self.scas = list()

    def reading(self):
        pass

    def prepare(self):
        self.mca.trigger_mode = TriggerMode.SOFTWARE
        self.mca.set_hardware_scas(self.scas)

    def start(self):
        self.device.start_acquisition()
        self._time_start = time.time()

    def stop(self):
        self.device.stop_acquisition()
        self._time_stop = time.time()

    def trigger(self):
        pass

    def _do_add_counter(self, counter):
        counter.register_device(self)

        (det, start, stop) = (
            counter.detector_channel,
            counter.start_index,
            counter.stop_index,
        )
        self.scas.append(
            (det, min(start, self.spectrum_size - 2), min(stop, self.spectrum_size - 1))
        )
