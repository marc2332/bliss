# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
import weakref
import numpy
import gevent
from bliss.common.counter import Counter
from bliss.scanning.chain import AcquisitionSlave
from .card import MODE

INTS_NAMES = ("intensity_A", "intensity_B", "acq_time")


def get_counters(flex):
    mode = flex.mode
    if mode == flex.MODE.SINGLE_AUTO or mode == flex.MODE.SINGLE_CROSS:
        spectrum_size = 1088
        nb_channel = 2
    elif mode == flex.MODE.DUAL_AUTO or mode == flex.MODE.DUAL_CROSS:
        spectrum_size = 608
        nb_channel = 3
    else:
        spectrum_size = 288
        nb_channel = 5

    datas = [Data(flex, i, spectrum_size) for i in range(nb_channel)]
    intensities = [Intensity(flex, name) for name in INTS_NAMES]
    return intensities + datas


class Data(Counter):
    def __init__(self, flex, chan_nb, spectrum_size):
        self._flex = weakref.ref(flex)
        self._chan_nb = chan_nb
        self._spectrum_size = spectrum_size

        super().__init__(self.name, flex)

    @property
    def controller(self):
        return self._flex()

    @property
    def name(self):
        if self._chan_nb:
            return "channel_{}".format(self._chan_nb)
        else:  # channel 0 == delay
            return "delay"

    @property
    def dtype(self):
        return numpy.float

    @property
    def shape(self):
        return (self._spectrum_size,)


class Intensity(Counter):
    def __init__(self, flex, name):
        self._flex = weakref.ref(flex)
        self._name = name
        super().__init__(self.name, flex)

    @property
    def controller(self):
        return self._flex()

    # @property
    # def name(self):
    #     return self._name

    # @property
    # def dtype(self):
    #     return numpy.float

    # @property
    # def shape(self):
    #     return ()


class FlexAcquisitionSlave(AcquisitionSlave):
    MODE = MODE

    def __init__(
        self, flex, count_time=1, mode=None, counters=None, ctrl_params=None, **kwargs
    ):
        prepare_once = kwargs.get("prepare_once", True)
        start_once = kwargs.get("start_once", False)
        AcquisitionSlave.__init__(
            self,
            flex,
            counters=counters,
            npoints=kwargs.get("npoints", 1),
            prepare_once=prepare_once,
            start_once=start_once,
            ctrl_params=ctrl_params,
        )
        self._count_time = count_time
        self._mode = mode
        self._stop_task = None
        self._event = gevent.event.Event()

    def prepare(self):
        if self._mode is not None:
            self.device.mode = self._mode

    def start(self):
        pass

    def stop(self):
        if self._stop_task is not None:
            self._stop_task.kill()
            self._stop_task = None
        self.device.stop_acquisition()

    def trigger(self):
        self.device.start_acquisition()
        self._stop_task = gevent.spawn_later(
            self._count_time, self.device.stop_acquisition
        )
        self._event.set()

    def wait_ready(self):
        if self._reading_task is not None:
            self._reading_task.join()

    def reading(self):
        # trigger wait
        self._event.wait()
        self._event.clear()
        with gevent.Timeout(
            max(1.0, self._count_time * 2),
            "Weird timeouterror (waiting stop_acquisition)",
        ):
            self._stop_task.join()

        data_names = [Data(self, chan_nb, -1).name for chan_nb in range(5)]
        values_dict = {name: data for name, data in zip(data_names, self.device.data)}
        ints_and_acq_time = self.device.intensities_and_acqtime
        values_dict.update(
            {name: data for name, data in zip(INTS_NAMES, ints_and_acq_time)}
        )

        self.channels.update(values_dict)
