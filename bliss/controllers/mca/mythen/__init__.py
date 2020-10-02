"""Controller for the mythen 1d detector."""

import enum
import numpy
import gevent


from bliss.common.counter import Counter
from bliss.scanning.chain import AcquisitionSlave
from bliss.controllers.counter import CounterController
from bliss.controllers.mca.roi import RoiConfig
from .lib import MythenInterface, MythenCompatibilityError
from bliss.common.utils import autocomplete_property
from bliss.controllers.counter import counter_namespace
from bliss.controllers.mca.base import RoiMcaCounter
from bliss.comm import tcp


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


class RoiMythenCounter(RoiMcaCounter):
    pass


class Mythen(CounterController):

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
        "selected_module",
        "element_settings",
    ]

    def __init__(self, name, config):
        super().__init__(name)
        self._config = config
        self._hostname = config["hostname"]
        self._interface = MythenInterface(self._hostname)
        self._apply_configuration()
        self._spectrum = self.create_counter(MythenCounter)
        self._rois = RoiConfig(self)

    def get_acquisition_object(self, acq_params, ctrl_params, parent_acq_params):
        trigger_mode = acq_params.pop("trigger_mode", None)
        if trigger_mode is not None:
            if isinstance(trigger_mode, str):
                if trigger_mode.upper() == "SOFTWARE":
                    acq_params["trigger_type"] = AcquisitionSlave.SOFTWARE
                else:
                    acq_params["trigger_type"] = AcquisitionSlave.HARDWARE

        return MythenAcquistionSlave(self, ctrl_params=ctrl_params, **acq_params)

    def get_default_chain_parameters(self, scan_params, acq_params):
        try:
            count_time = acq_params["count_time"]
        except KeyError:
            count_time = scan_params["count_time"]

        if "trigger_type" not in acq_params:
            trigger_mode = acq_params.get(
                "trigger_mode", MythenAcquistionSlave.TriggerMode.SOFTWARE
            )
            if trigger_mode == MythenAcquistionSlave.TriggerMode.SOFTWARE:
                trigger_type = AcquisitionSlave.SOFTWARE
            else:
                trigger_type = AcquisitionSlave.HARDWARE
        else:
            trigger_type = acq_params["trigger_type"]

        prepare_once = acq_params.get("prepare_once", True)

        npoints = acq_params.get("npoints", scan_params.get("npoints", 1))
        if npoints == 0:
            npoints = 1
            start_once = True  # <= ???
        else:
            start_once = acq_params.get(
                "start_once", trigger_type == AcquisitionSlave.HARDWARE
            )

        params = {}
        params["count_time"] = count_time
        params["npoints"] = npoints
        params["trigger_type"] = trigger_type
        params["prepare_once"] = prepare_once
        params["start_once"] = start_once

        return params

    def finalize(self):
        self._interface.close()

    # Manage configuration

    def _apply_configuration(self):
        if self._config.get("apply_defaults"):
            self.reset()
        for key, value in self._config.items():
            if key in self._settings:
                setattr(self, key, value)

    def _get_configuration(self):
        conf = []
        for key in self._settings:
            try:
                value = getattr(self, key)
                conf.append((key, value))
            except MythenCompatibilityError:
                continue
        return conf

    def __info__(self):
        lines = ["Mythen on {}:".format(self._hostname)]
        lines += [
            "  {:<25s} = {}".format(key, value)
            for key, value in self._get_configuration()
        ]

        info_str = "\n".join(lines)
        info_str += "\nROIS:\n"

        info_str_shifted = ""
        for line in self.rois.__info__().split("\n"):
            info_str_shifted += "    " + line + "\n"
        info_str += info_str_shifted
        info_str += "\n"

        return info_str

    @property
    def hostname(self):
        return self._hostname

    # Roi handling

    @autocomplete_property
    def rois(self):
        return self._rois

    @autocomplete_property
    def counters(self):
        counters = [self._spectrum]
        counters.extend(
            [RoiMythenCounter(self, roi, None) for roi in self.rois.get_names()]
        )

        return counter_namespace(counters)

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

    selected_module = interface_property("selected_module")

    element_settings = interface_property("element_settings")

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

    def run(self, acquisition_number=1, acquisition_time=1.0):
        self.nframes = acquisition_number
        self.exposure_time = acquisition_time
        try:
            self.start()
            for _ in range(acquisition_number):
                yield self.readout()
        finally:
            self.stop()


# Mythen counter


class MythenCounter(Counter):

    # Initialization

    def __init__(self, controller):
        super().__init__("spectrum", controller)

    # Data properties

    @property
    def dtype(self):
        return numpy.int32

    @property
    def shape(self):
        return (self._counter_controller.get_nchannels(),)


class MythenAcquistionSlave(AcquisitionSlave):
    status = enum.Enum("status", "STOPPED RUNNING FAULT")
    TriggerMode = enum.Enum("TriggerMode", "SOFTWARE GATE")

    # Initialization
    def __init__(
        self,
        *mca_or_mca_counters,
        count_time=0,
        npoints=1,
        trigger_type=AcquisitionSlave.HARDWARE,
        prepare_once=False,
        start_once=False,
        ctrl_params=None,
    ):

        self.count_time = count_time

        super().__init__(
            *mca_or_mca_counters,
            npoints=npoints,
            trigger_type=trigger_type,
            prepare_once=prepare_once,
            start_once=start_once,
            ctrl_params=ctrl_params,
        )

        self._software_acquisition = None
        self._acquisition_status = self.status.STOPPED
        self._event = gevent.event.Event()
        self._trigger_event = gevent.event.Event()

    # Counter management

    def _do_add_counter(self, counter):
        super()._do_add_counter(counter)
        if not isinstance(counter, MythenCounter):
            counter.register_device(self)
        else:
            self._spectrum_counter = counter

    # Flow control

    def prepare(self):
        self.device.nframes = self.npoints
        self.device.exposure_time = self.count_time
        self.device.gate_mode = self.trigger_type == AcquisitionSlave.HARDWARE

    def start(self):
        if self.trigger_type == AcquisitionSlave.HARDWARE:
            self.device.start()
            self._trigger_event.set()
        self._acquisition_status = self.status.RUNNING

    def trigger(self):
        try:
            self._trigger_event.clear()
            self._event.clear()
            try:
                self.device.start()
                self._event.wait(self.count_time)
            finally:
                self._acquisition_status = self.status.STOPPED
                self._software_acquisition = None
                self.device.stop()
            self._publish()
        finally:
            self._trigger_event.set()

    def reading(self):
        if self.trigger_type == AcquisitionSlave.SOFTWARE:
            return

        for spectrum_nb in range(self.npoints):
            if self._acquisition_status != self.status.RUNNING:
                break
            while self._acquisition_status == self.status.RUNNING:
                try:
                    self._publish()
                except tcp.SocketTimeout:
                    self.device._interface.close_data_socket()
                    continue
                else:
                    break

    def _publish(self):
        spectrum = self.device.readout()
        spectrum_channel = self._counters[self._spectrum_counter][0]
        spectrum_channel.emit(spectrum)

        for counter, channels in self._counters.items():
            if counter is self._spectrum_counter:
                continue
            channel = channels[0]
            point = counter.compute_roi(spectrum)
            channel.emit(point)

    def stop(self):
        self._event.set()
        if self.trigger_type != AcquisitionSlave.SOFTWARE:
            self.device.stop()
            self._acquisition_status = self.status.STOPPED
            self.wait_reading()  # let the last point to be published
        self._trigger_event.wait(1.5)
