# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common.utils import add_property
from bliss.common.tango import DeviceProxy, DevFailed
from bliss.common.measurement import SamplingCounter
from bliss.scanning.scan import ScanSaving
from bliss.config.settings import SimpleSetting
from bliss.common import Actuator
import gevent
from gevent import event
import numpy


class BpmGroupedReadHandler(SamplingCounter.GroupedReadHandler):
    def __init__(self, controller):
        SamplingCounter.GroupedReadHandler.__init__(self, controller)
        self.__back_to_live = False
        self.__video = False

    def prepare(self, *counters):
        self.__back_to_live = False
        self.__video = False
        if self.controller.is_video_live():
            self.__back_to_live = True
            self.__video = True
            self.controller.stop(video=True)
        elif self.controller.is_live():
            self.__back_to_live = True
            self.controller.stop()
        # save image if image counter is present
        if any([isinstance(c, BpmImage) for c in counters]):
            self.controller.save_images(True)

    def stop(self, *counters):
        self.controller.save_images(False)
        if self.__back_to_live:
            while self.controller.is_acquiring():
                gevent.idle()
            self.controller.live(video=self.__video)

    def read(self, *counters):
        result = self.controller.tango_proxy.GetPosition()
        return [
            cnt.count if isinstance(cnt, BpmImage) else result[cnt.index]
            for cnt in counters
        ]


class BpmCounter(SamplingCounter):
    def __init__(self, name, controller, index, **kwargs):
        SamplingCounter.__init__(
            self, controller.name + "." + name, controller, **kwargs
        )
        self.__index = index

    @property
    def index(self):
        return self.__index


class BpmDiodeCounter(SamplingCounter):
    def __init__(self, name, controller, control):
        SamplingCounter.__init__(self, controller.name + "." + name, None)
        self.__control = control

    def read(self):
        return self.__control.DiodeCurrent


class BpmImage(BpmCounter):
    def __init__(self, controller, **kwargs):
        BpmCounter.__init__(self, "image", controller, -1, **kwargs)
        self.__image_acq_counter_setting = SimpleSetting(
            self.name, None, int, int, default_value=0
        )

    @property
    def count(self):
        return self.__image_acq_counter_setting.get()


class tango_bpm(object):
    def __init__(self, name, config):
        self.name = name
        self.__counters_grouped_read_handler = BpmGroupedReadHandler(self)

        tango_uri = config.get("uri")
        tango_lima_uri = config.get("lima_uri")
        foil_actuator_name = config.get("foil_name")

        self.__control = DeviceProxy(tango_uri)
        if tango_lima_uri:
            self.__lima_control = DeviceProxy(tango_lima_uri)
        else:
            self.__lima_control = None
        self._acquisition_event = event.Event()
        self._acquisition_event.set()
        self.__diode_actuator = None
        self.__led_actuator = None
        self.__foil_actuator = None

        bpm_properties = self.__control.get_property_list("*")

        if "wago_ip" in bpm_properties:
            self.__diode_actuator = Actuator(
                self.__control.In,
                self.__control.Out,
                lambda: self.__control.YagStatus == "in",
                lambda: self.__control.YagStatus == "out",
            )
            self.__led_actuator = Actuator(
                self.__control.LedOn,
                self.__control.LedOff,
                lambda: self.__control.LedStatus > 0,
            )

            def diode_current(*args):
                return BpmDiodeCounter("diode_current", self, self.__control)

            add_property(self, "diode_current", diode_current)

            def diode_actuator(*args):
                return self.__diode_actuator

            add_property(self, "diode", diode_actuator)

            def led_actuator(*args):
                return self.__led_actuator

            add_property(self, "led", led_actuator)
        if "has_foils" in bpm_properties:
            self.__foil_actuator = Actuator(
                self.__control.FoilIn,
                self.__control.FoilOut,
                lambda: self.__control.FoilStatus == "in",
                lambda: self.__control.FoilStatus == "out",
            )

            def foil_actuator(*args):
                return self.__foil_actuator

            if not foil_actuator_name:
                foil_actuator_name = "foil"
            add_property(self, foil_actuator_name, foil_actuator)

    @property
    def tango_proxy(self):
        return self.__control

    @property
    def x(self):
        return BpmCounter(
            "x", self, 2, grouped_read_handler=self.__counters_grouped_read_handler
        )

    @property
    def y(self):
        return BpmCounter(
            "y", self, 3, grouped_read_handler=self.__counters_grouped_read_handler
        )

    @property
    def intensity(self):
        return BpmCounter(
            "intensity",
            self,
            1,
            grouped_read_handler=self.__counters_grouped_read_handler,
        )

    @property
    def fwhm_x(self):
        return BpmCounter(
            "fwhm_x", self, 4, grouped_read_handler=self.__counters_grouped_read_handler
        )

    @property
    def fwhm_y(self):
        return BpmCounter(
            "fwhm_y", self, 5, grouped_read_handler=self.__counters_grouped_read_handler
        )

    @property
    def image(self):
        return BpmImage(self, grouped_read_handler=self.__counters_grouped_read_handler)

    @property
    def exposure_time(self):
        return self.__control.ExposureTime

    def set_exposure_time(self, exp_time):
        self.__control.ExposureTime = exp_time

    @property
    def diode_range(self):
        return self.__control.DiodeRange

    def set_diode_range(self, range):
        self.__control.DiodeRange = range

    def live(self, video=False):
        if video and self.__lima_control:
            self.__lima_control.video_live = True
        else:
            return self.__control.Live()

    def is_acquiring(self):
        return str(self.__control.State()) == "MOVING"

    def is_live(self):
        return str(self.__control.LiveState) == "RUNNING"

    def is_video_live(self):
        return self.__lima_control and self.__lima_control.video_live

    def stop(self, video=False):
        if video and self.__lima_control:
            self.__lima_control.video_live = False
        else:
            self.__control.Stop()

    def set_in(self):
        return self.__control.In()

    def set_out(self):
        return self.__control.Out()

    def is_in(self):
        return self.__control.YagStatus == "in"

    def is_out(self):
        return self.__control.YagStatus == "out"

    def save_images(self, save):
        if save:
            scan_saving = ScanSaving()
            directory = scan_saving.get_path()
            image_acq_counter_setting = SimpleSetting(
                self.name + ".image", None, int, int, default_value=0
            )
            image_acq_counter_setting += 1
            prefix = self.name + "_image_%d_" % image_acq_counter_setting.get()
            self.__control.EnableAutoSaving([directory, prefix])
        else:
            self.__control.DisableAutoSaving()

    def __repr__(self):
        try:
            msg = (
                "BPM {}\n"
                "Expo time = {}\n"
                "Acquiring = {}\n"
                "Live = {}\n"
                "Video live = {}".format(
                    self.name,
                    self.exposure_time,
                    self.is_acquiring(),
                    self.is_live(),
                    self.is_video_live(),
                )
            )
            if self.__diode_actuator:
                screen_status = "IN" if self.is_in() else "OUT"
                msg += "\nScreen = " + screen_status
            if self.__led_actuator:
                led_status = "ON" if self.led.is_in() else "OFF"
                msg += "\nLed = " + led_status
            if self.__foil_actuator:
                foil_status = "IN" if self.__foil_actuator.is_in() else "OUT"
                msg += "\nFoil = " + foil_status
        except DevFailed:
            msg = "BPM {}: Communication error with {}".format(
                self.name, self.__control.dev_name()
            )
        return msg
