"""Provide an MCA simulator."""

import time

import numpy
import gevent

from bliss.common import event

from .base import BaseMCA, PresetMode, TriggerMode, Stats, Brand, DetectorType


class SimulatedMCA(BaseMCA):

    _init_time = 1.
    _prepare_time = 1e-3
    _cleanup_time = 1e-3
    _read_overhead = 10e-3
    _gate_end = 0.5
    _mapping_modulo = 2

    _fast_channel_dt = 0.9
    _slow_channel_dt = 0.7
    _source_count_rate = 10000

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
        self._bad_counters = False

    def initialize_hardware(self):
        gevent.sleep(self._init_time)

    def finalize(self):
        pass

    # Information

    @property
    def detector_brand(self):
        return Brand.SIMULATED

    @property
    def detector_type(self):
        return DetectorType.SIMULATED

    @property
    def elements(self):
        return (0, 1, 2, 3)

    @property
    def counters(self):
        if self._bad_counters:
            raise RuntimeError("Failed to get counters")
        else:
            return super().counters

    # Settings

    @property
    def spectrum_size(self):
        return self._spectrum_size

    @spectrum_size.setter
    def spectrum_size(self, size):
        self._spectrum_size = size

    @property
    def supported_preset_modes(self):
        return (PresetMode.REALTIME,)

    @property
    def preset_mode(self):
        return PresetMode.REALTIME

    @preset_mode.setter
    def preset_mode(self, mode):
        assert mode is PresetMode.REALTIME

    @property
    def preset_value(self):
        return self._realtime

    @preset_value.setter
    def preset_value(self, value):
        self._realtime = value

    @property
    def supported_trigger_modes(self):
        return TriggerMode.SOFTWARE, TriggerMode.GATE, TriggerMode.SYNC

    @property
    def trigger_mode(self):
        return self._trigger_mode

    @trigger_mode.setter
    def trigger_mode(self, mode):
        if mode is None:
            mode = TriggerMode.SOFTWARE
        assert mode in self.supported_trigger_modes
        self._trigger_mode = mode

    @property
    def hardware_points(self):
        return self._hardware_points

    @hardware_points.setter
    def hardware_points(self, value):
        self._hardware_points = value

    @property
    def block_size(self):
        return self._block_size or 100

    @block_size.setter
    def block_size(self, value=None):
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

    def trigger(self):
        try:
            if not self._running:
                self.start_acquisition()
            while self.is_acquiring():
                gevent.sleep(self._read_overhead)
        finally:
            self.stop_acquisition()
            spectra = self.get_acquisition_data()
            statistics = self.get_acquisition_statistics()
            event.send(self, "data", (spectra, statistics))

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

    # Data generation

    def _generate_pixel(self, realtime):
        data, stats = {}, {}
        nbins = self._spectrum_size
        loc = nbins // 2
        scale = nbins // 16
        bins = numpy.arange(nbins + 1)
        for i in self.elements:
            stats[i] = self._generate_stats(realtime)
            n = stats[i].events
            channels = numpy.random.normal(loc=loc, scale=scale, size=n)
            data[i] = numpy.histogram(channels, bins=bins)[0]
        return data, stats

    def _generate_stats(self, realtime):
        fast_channel_dt = numpy.random.normal(self._fast_channel_dt, 0.01)
        fast_channel_dt = numpy.clip(fast_channel_dt, 0, 1)
        slow_channel_dt = numpy.random.normal(self._slow_channel_dt, 0.01)
        slow_channel_dt = numpy.clip(slow_channel_dt, 0, 1)
        trigger_livetime = realtime * fast_channel_dt
        energy_livetime = realtime * slow_channel_dt
        triggers = int(self._source_count_rate * trigger_livetime)
        events = int(self._source_count_rate * energy_livetime)
        icr = triggers / trigger_livetime if trigger_livetime else 0.
        ocr = events / realtime if realtime else 0.
        deadtime = 1 - ocr / icr if icr else 0.
        return Stats(
            realtime,
            trigger_livetime,
            energy_livetime,
            triggers,
            events,
            icr,
            ocr,
            deadtime,
        )
