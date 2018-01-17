"""Provide an MCA simulator."""

import time

import numpy
import gevent

from .base import BaseMCA, PresetMode, TriggerMode, Stats


class SimulatedMCA(BaseMCA):

    _init_time = 1.
    _prepare_time = 0.1
    _cleanup_time = 0.1
    _gate_end = 0.5
    _mapping_modulo = 2

    # Initialization

    def initialize_attributes(self):
        self._running = False
        self._block_size = None
        self._spectrum_size = 1024
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
        return (0, 1, 2, 3)

    # Settings

    @property
    def spectrum_size(self):
        return self._spectrum_size

    def set_spectrum_size(self, size):
        self._spectrum_size = size

    @property
    def supported_preset_modes(self):
        return PresetMode.NONE,

    def set_preset_mode(self, mode, value=None):
        assert mode is PresetMode.REALTIME
        self._realtime = value

    @property
    def supported_trigger_modes(self):
        return TriggerMode.SOFTWARE, TriggerMode.GATE, TriggerMode.SYNC

    def set_trigger_mode(self, mode):
        if mode is None:
            mode = TriggerMode.SOFTWARE
        assert mode in self.supported_trigger_modes
        self._trigger_mode = mode

    @property
    def hardware_points(self):
        return self._hardware_points

    def set_hardware_points(self, value):
        self._hardware_points = value

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
            self._data_buffer = {}
            self._stats_buffer = {}
        self._running = True

    def stop_acquisition(self):
        if self._running:
            self._delta = time.time() - self._t0
            gevent.sleep(self._cleanup_time)
        self._running = False

    def is_acquiring(self):
        return self._running and self.delta < self._realtime

    @property
    def delta(self):
        d = time.time() - self._t0 if self._running else self._delta
        if self._trigger_mode == TriggerMode.GATE:
            return min(d, self._gate_end)
        if self._trigger_mode == TriggerMode.SOFTWARE:
            return min(d, self._realtime)
        return d

    # Get data

    def get_acquisition_data(self):
        a, b = self._generate_pixel(self.delta)
        return a

    def get_acquisition_statistics(self):
        a, b = self._generate_pixel(self.delta)
        return b

    def poll_data(self):
        # Update
        self._count += 1
        current = self._count // self._mapping_modulo
        # Realtime
        if self._trigger_mode == TriggerMode.SYNC:
            delta = 0.2 * self._mapping_modulo
        else:
            delta = self._gate_end
        # Flags
        new_pixel = self._count % self._mapping_modulo != 0
        full_buffer = current and current % self.block_size == 0
        finished = current == self.hardware_points
        # A new pixel has been generated
        if current > 0 and new_pixel:
            a, b = self._generate_pixel(delta)
            self._data_buffer[current-1] = a
            self._stats_buffer[current-1] = b
        # Available data
        if new_pixel and (full_buffer or finished):
            a, b = self._data_buffer, self._stats_buffer
            self._data_buffer = {}
            self._stats_buffer = {}
            return current, a, b
        # Nothing to return yet
        return current, {}, {}

    # Data generation

    def _generate_pixel(self, delta):
        realtime = delta
        livetime = realtime * 0.9
        triggers = int(livetime * 10000)
        events = triggers // 2
        icr = triggers / realtime
        ocr = events / livetime
        deadtime = 1 - ocr / icr
        st = Stats(realtime, livetime, triggers, events, icr, ocr, deadtime)
        stats = dict((i, st) for i in self.elements)
        size = self._spectrum_size
        data = dict((i, numpy.zeros(size)) for i in self.elements)
        for _ in range(events):
            loc = numpy.random.normal(size//2, size//16)
            for i in self.elements:
                e = int(numpy.random.normal(loc, size//16))
                data[i][e] += 1
        return data, stats
