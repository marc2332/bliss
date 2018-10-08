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
        self._current_data = None
        self._current_stats = None
        self._realtime = float("inf")

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
        return (PresetMode.NONE,)

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
        pixel = self._generate_pixel(self.delta)
        self._current_data, self._current_stats = pixel

    def is_acquiring(self):
        if self._trigger_mode != TriggerMode.SOFTWARE:
            return self._running
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
        return self._current_data

    def get_acquisition_statistics(self):
        return self._current_stats

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
            self._data_buffer[current - 1] = a
            self._stats_buffer[current - 1] = b
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
        data, stats = {}, {}
        for i in self.elements:
            realtime = delta
            livetime = realtime * numpy.random.normal(0.9, 0.01)
            triggers = int(10000 * numpy.random.normal(livetime, livetime * 0.2))
            events = triggers // 2
            icr = triggers / realtime if realtime else 0.
            ocr = events / livetime if livetime else 0.
            deadtime = 1 - ocr / icr if icr else 0.
            stats[i] = Stats(realtime, livetime, triggers, events, icr, ocr, deadtime)
            size = self._spectrum_size
            data[i] = numpy.zeros(size, dtype=int)
            for _ in range(events):
                loc = numpy.random.normal(size // 2, size // 16)
                e = int(numpy.random.normal(loc, size // 16))
                if e > size:
                    e = size
                elif e < 0:
                    e = 0
                data[i][e] += 1
        return data, stats
