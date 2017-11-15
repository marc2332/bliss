"""Provide an MCA simulator."""

import time

import numpy
import gevent

from .base import BaseMCA, PresetMode, TriggerMode, Stats


class SimulatedMCA(BaseMCA):

    _init_time = 1.
    _prepare_time = 0.5
    _cleanup_time = 0.5
    _gate_end = 0.5

    # Initialization

    def initialize_attributes(self):
        self._running = False
        self._block_size = None
        self._acquistion_number = 1
        self._trigger_mode = TriggerMode.SOFTWARE

    def initialize_hardware(self):
        gevent.sleep(self._init_time)

    def finalize(self):
        pass

    # Information

    @property
    def detector_brand(self):
        return "SIMULATION"

    @property
    def detector_type(self):
        return "SIMULATION"

    @property
    def elements(self):
        return 4

    # Settings

    @property
    def supported_preset_modes(self):
        return PresetMode.NONE,

    def set_preset_mode(self, mode):
        assert mode in (None, PresetMode.NONE)

    @property
    def supported_trigger_modes(self):
        return TriggerMode.SOFTWARE, TriggerMode.GATE

    def set_trigger_mode(self, mode):
        if mode is None:
            mode = TriggerMode.SOFTWARE
        assert mode in self.supported_trigger_modes
        self._trigger_mode = mode

    @property
    def acquisition_number(self):
        return self._acquistion_number

    def set_acquisition_number(self, value):
        self._acquistion_number = value

    @property
    def block_size(self):
        return self._block_size or 100

    def set_block_size(elf, value=None):
        self._block_size = value

    # Acquisition control

    def start_acquisition(self):
        if not self._running:
            gevent.sleep(self._prepare_time)
            self._t0 = time.time()
        self._running = True

    def stop_acquisition(self):
        if self._running:
            self._delta = time.time() - self._t0
            gevent.sleep(self._cleanup_time)
        self._running = False

    def is_acquiring(self):
        return self._running

    @property
    def delta(self):
        d = time.time() - self._t0 if self.is_acquiring() else self._delta
        if self._trigger_mode == TriggerMode.GATE:
            return min(d, self._gate_end)
        return d

    # Get data

    def get_acquisition_data(self):
        data = dict((i, numpy.zeros(1024)) for i in range(self.elements))
        events = int(0.9 * 10000 * self.delta / 2)
        for _ in range(events):
            loc = numpy.random.normal(512, 64)
            for i in range(self.elements):
                e = int(numpy.random.normal(loc, 64))
                data[i][e] += 1
        return data

    def get_acquisition_statistics(self):
        realtime = self.delta
        livetime = realtime * 0.9
        triggers = int(livetime * 10000)
        events = triggers // 2
        icr = triggers / realtime
        ocr = events / livetime
        deadtime = 1 - ocr / icr
        stats = Stats(realtime, livetime, triggers, events, icr, ocr, deadtime)
        return dict((i, stats) for i in range(self.elements))

    def poll_data(self):
        raise RuntimeError
