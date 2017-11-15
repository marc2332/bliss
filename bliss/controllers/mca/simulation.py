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
    _mapping_modulo = 2

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
        return TriggerMode.SOFTWARE, TriggerMode.GATE, TriggerMode.EXTERNAL

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

    def set_block_size(self, value=None):
        self._block_size = value

    # Acquisition control

    def start_acquisition(self):
        if not self._running:
            gevent.sleep(self._prepare_time)
            self._t0 = time.time()
            self._count = -1
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
        a, b = self._generate_pixel(self.delta)
        return a

    def get_acquisition_statistics(self):
        a, b = self._generate_pixel(self.delta)
        return b

    def poll_data(self):
        self._count += 1
        current = self._count // self._mapping_modulo
        # Nothing happened
        if self._count % self._mapping_modulo != 0:
            return current, {}, {}
        # New buffer
        if current and current % self.block_size == 0:
            a, b = self._generate_pixels(current-self.block_size, current)
            return current, a, b
        # Finished
        if current == self.acquisition_number:
            start = (current // self.block_size) * self.block_size
            a, b = self._generate_pixels(start, current)
            return current, a, b
        # A new pixel has been generated
        return current, {}, {}

    # Data generation

    def _generate_pixels(self, start, stop):
        da, db = {}, {}
        for i in range(start, stop):
            da[i], db[i] = self._generate_pixel(0.2 * self._mapping_modulo)
        return da, db

    def _generate_pixel(self, delta):
        realtime = delta
        livetime = realtime * 0.9
        triggers = int(livetime * 10000)
        events = triggers // 2
        icr = triggers / realtime
        ocr = events / livetime
        deadtime = 1 - ocr / icr
        st = Stats(realtime, livetime, triggers, events, icr, ocr, deadtime)
        stats = dict((i, st) for i in range(self.elements))
        data = dict((i, numpy.zeros(1024)) for i in range(self.elements))
        for _ in range(events):
            loc = numpy.random.normal(512, 64)
            for i in range(self.elements):
                e = int(numpy.random.normal(loc, 64))
                data[i][e] += 1
        return data, stats
