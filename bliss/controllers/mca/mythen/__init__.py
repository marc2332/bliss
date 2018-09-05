"""Controller for the mythen 1d detector."""

import numpy

from .lib import MythenInterface

from bliss.common.measurement import BaseCounter, counter_namespace
from bliss.scanning.chain import AcquisitionDevice, AcquisitionChannel


def interface_property(name, mode=False):
    getter_name = name + "_enabled" if mode else "get_" + name
    setter_name = "enable_" + name if mode else "set_" + name
    assert getter_name in dir(MythenInterface)
    assert setter_name in dir(MythenInterface)

    def getter(self):
        return getattr(self._interface, getter_name)()

    def setter(self, value):
        return getattr(self._interface, setter_name)(value)

    return property(getter, setter)


class Mythen(object):

    _settings = [
        # General configuration
        "nmodules",
        # Acquisition configuration
        "delay_after_frame",
        "nframes",
        "nbits",
        "exposure_time",
        # Detector configuration
        "energy",
        "threshold",
        # Data correction settings
        "bad_channel_interpolation",
        "flat_field_correction",
        "rate_correction",
        "rate_correction_deadtime",
        # Trigger / Gate settings
        "continuous_trigger_mode",
        "single_trigger_mode",
        "delay_before_frame",
        "gate_mode",
        "ngates",
        "input_polarity",
        "output_polarity",
    ]

    def __init__(self, name, config):
        self._name = name
        self._config = config
        self._hostname = config["hostname"]
        self._interface = MythenInterface(self._hostname)
        self._apply_configuration()
        self._counter = MythenCounter(self)

    def finalize(self):
        self._interface.close()

    # Counter access

    @property
    def counters(self):
        return counter_namespace([self._counter])

    # Manage configuration

    def _apply_configuration(self):
        if self._config.get("apply_defaults"):
            self.reset()
        for key, value in self._config.items():
            if key in self._settings:
                setattr(self, key, value)

    def _get_configuration(self):
        return [(key, getattr(self, key)) for key in self._settings]

    def __repr__(self):
        lines = ["Mythen on {}:".format(self._hostname)]
        lines += [
            "  {:<25s} = {}".format(key, value)
            for key, value in self._get_configuration()
        ]
        return "\n".join(lines)

    # Bliss properties

    @property
    def name(self):
        return self._name

    @property
    def hostname(self):
        return self._hostname

    # General configuration

    nmodules = interface_property("nmodules")

    # Acquisition configuration

    delay_after_frame = interface_property("delayafterframe")

    nframes = interface_property("nframes")

    nbits = interface_property("nbits")

    exposure_time = interface_property("exposure_time")

    # Detector configuration

    energy = interface_property("energy")

    threshold = interface_property("kthresh")

    # Data correction configuration

    bad_channel_interpolation = interface_property("badchannelinterpolation", mode=True)

    flat_field_correction = interface_property("flatfieldcorrection", mode=True)

    rate_correction = interface_property("ratecorrection", mode=True)

    rate_correction_deadtime = interface_property("ratecorrection_deadtime")

    # Trigger / Gate configuration

    continuous_trigger_mode = interface_property("continuoustrigger", mode=True)

    single_trigger_mode = interface_property("singletrigger", mode=True)

    gate_mode = interface_property("gatemode", mode=True)

    delay_before_frame = interface_property("delaybeforeframe")

    ngates = interface_property("ngates")

    input_polarity = interface_property("inputpolarity")

    output_polarity = interface_property("outputpolarity")

    # Expose all interface getters

    def __getattr__(self, attr):
        if attr.startswith("get_") and attr in dir(self._interface):
            return getattr(self._interface, attr)
        raise AttributeError(attr)

    def __dir__(self):
        lst = list(self.__dict__)
        lst += dir(type(self))
        lst += [key for key in dir(self._interface) if key.startswith("get_")]
        return sorted(set(lst))

    # Commands

    def reset(self):
        self._interface.reset()

    def start(self):
        self._interface.start()

    def stop(self):
        self._interface.stop()

    def readout(self):
        return self._interface.readout(1)[0]

    # Acquisition routine

    def run(self, acquisition_number=1, acquisition_time=1.):
        self.nframes = acquisition_number
        self.exposure_time = acquisition_time
        try:
            self.start()
            for _ in range(acquisition_number):
                yield self.readout()
        finally:
            self.stop()


# Mythen counter


class MythenCounter(BaseCounter):

    # Initialization

    def __init__(self, controller):
        self._name = "spectrum"
        self._controller = controller

    @property
    def name(self):
        return self._name

    @property
    def controller(self):
        return self._controller

    # Data properties

    @property
    def dtype(self):
        return numpy.int32

    @property
    def shape(self):
        return (self.controller.get_nchannels(),)

    # Get acquisition device

    def create_acquisition_device(self, scan_pars, **settings):
        scan_pars.update(settings)
        count_time = scan_pars.pop("count_time")
        return MythenAcquistionDevice(self, count_time, **scan_pars)


class MythenAcquistionDevice(AcquisitionDevice):

    # Initialization

    def __init__(self, counter, count_time, **kwargs):
        self.kwargs = kwargs
        self.counter = counter
        self.count_time = count_time
        valid_names = ("npoints", "trigger_type", "prepare_once", "start_once")
        valid_kwargs = {
            key: value for key, value in kwargs.items() if key in valid_names
        }
        super(MythenAcquistionDevice, self).__init__(
            counter.controller, counter.controller.name, **valid_kwargs
        )
        self.channels.append(
            AcquisitionChannel(self, counter.name, counter.dtype, counter.shape)
        )

    def add_counter(self, counter):
        assert self.counter == counter

    # Flow control

    def prepare(self):
        self.device.nframes = self.npoints
        self.device.exposure_time = self.count_time

    def start(self):
        self.device.start()

    def trigger(self):
        # Software trigger is not supported by the mythen
        pass

    def reading(self):
        spectrum = self.device.readout()
        self.channels.update({self.counter.name: spectrum})

    def stop(self):
        self.device.stop()
