# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
import weakref
import numpy
import gevent

from bliss.controllers.counter import CounterController
from bliss.common.counter import Counter
from bliss.scanning.chain import AcquisitionSlave
from bliss.common.protocols import counter_namespace
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

    ctrl = Controller(flex)
    datas = [Data(ctrl, i, spectrum_size) for i in range(nb_channel)]
    intensities = [Intensity(ctrl, name) for name in INTS_NAMES]
    return counter_namespace(intensities + datas)


class Controller(CounterController):
    def __init__(self, flex):
        super().__init__(flex.name, register_counters=False)
        self._flex = flex

    def get_default_chain_parameters(self, scan_params, acq_params):
        count_time = acq_params.get("count_time", scan_params["count_time"])
        npoints = acq_params.get("npoints", scan_params["npoints"])
        prepare_once = acq_params.get("prepare_once", True)
        start_once = acq_params.get("start_once", False)
        return {
            "count_time": count_time,
            "npoints": npoints,
            "prepare_once": prepare_once,
            "start_once": start_once,
        }

    def get_acquisition_object(self, acq_params, ctrl_params, parent_acq_params):
        return FlexAcquisitionSlave(
            self, self._flex, ctrl_params=ctrl_params, **acq_params
        )


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
        self,
        flex_counter_controller,
        flex,
        count_time=1,
        mode=None,
        ctrl_params=None,
        **kwargs,
    ):
        prepare_once = kwargs.get("prepare_once", True)
        start_once = kwargs.get("start_once", False)
        AcquisitionSlave.__init__(
            self,
            flex_counter_controller,
            npoints=kwargs.get("npoints", 1),
            prepare_once=prepare_once,
            start_once=start_once,
            ctrl_params=ctrl_params,
        )
        self._count_time = count_time
        self._mode = mode
        self._stop_task = None
        self._event = gevent.event.Event()
        self._flex = flex

    def prepare(self):
        if self._mode is not None:
            self._flex.mode = self._mode

    def start(self):
        pass

    def stop(self):
        if self._stop_task is not None:
            self._stop_task.kill()
            self._stop_task = None
        self._flex.stop_acquisition()

    def trigger(self):
        self._flex.start_acquisition()
        self._stop_task = gevent.spawn_later(
            self._count_time, self._flex.stop_acquisition
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
        values_dict = {name: data for name, data in zip(data_names, self._flex.data)}
        ints_and_acq_time = self._flex.intensities_and_acqtime
        values_dict.update(
            {name: data for name, data in zip(INTS_NAMES, ints_and_acq_time)}
        )

        self.channels.update(values_dict)
