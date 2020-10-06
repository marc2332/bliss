# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common.utils import autocomplete_property
from bliss.controllers.counter import CounterController
from bliss.common.counter import Counter
from bliss.scanning.acquisition.oscilloscope import (
    OscilloscopeAcquisitionSlave,
    OscAnalogChanData,
    OscMeasData,
)
from bliss.controllers.counter import counter_namespace


class Oscilloscope:
    """Base class for user level objects for oscilloscopes"""

    def __init__(self, name, config):
        # inhereted class should initialise OscilloscopeController that holds the comm as self._device before getting here
        assert self._device is not None

        self._config = config
        self._name = name
        self._counter_controller = OscilloscopeCounterController(self)
        # should initialise a OscilloscopeCounterController

    @autocomplete_property
    def device(self):
        return self._device

    @autocomplete_property
    def counters(self):
        all_counters = list(self.channels)
        all_counters += list(self.measurements)
        return counter_namespace(all_counters)

    @property
    def name(self):
        return self._name

    @autocomplete_property
    def channels(self):
        # should provied access to channel configuration
        chans = list()
        for name in self.device.get_channel_names():
            c = self._channel_counter(name)
            chans.append(c)

        return counter_namespace(chans)

    def _channel_counter(self, name):
        return OscilloscopeAnalogChannel(name, self._counter_controller)

    @autocomplete_property
    def measurements(self):
        # should provied access to channel configuration
        meas = list()
        for name in self.device.get_measurement_names():
            m = self._measurement_counter(name)
            meas.append(m)

        return counter_namespace(meas)

    def _measurement_counter(self, name):
        return OscilloscopeMeasurement(name, self._counter_controller)

    @property
    def idn(self):
        return self.device.idn()

    @autocomplete_property
    def trigger(self):
        return OscilloscopeTrigger()

class OscilloscopeTrigger:
    def __init__(self, device):
        self._device = device

    def __info__(self):
        return "this is trigger info"

    def get_current_setting(self, param):
        raise NotImplementedError

    def set_trigger_setting(self, param, value):
        raise NotImplementedError

    @property
    def type(self):
        return self.get_current_setting("type")

    @type.setter
    def type(self, trig_type):
        self.set_trigger_setting("type", trig_type)

    @property
    def source(self):
        return self.get_current_setting("source")

    @source.setter
    def source(self, ch):
        self.set_trigger_setting("source", ch)

    @property
    def coupling(self):
        # to be implemented
        return None

    @property
    def level(self):
        # to be implemented
        return None

    @property
    def slope(self):
        # to be implemented
        return None



class OscilloscopeHardwareController:
    """functions tha deal with hardware related stuff"""

    # holds the comm

    def __init__(self, name, config):
        raise NotImplementedError

    @property
    def comm(self):
        return self._comm


class OscilloscopeMeasurement(Counter):
    pass


class OscilloscopeAnalogChannel(Counter):

    # ~ @property
    # ~ def xdiv(self):  # should find a better name
    # ~ raise NotImplementedError

    # ~ @property
    # ~ def tdiv(self):  # should find a better name
    # ~ raise NotImplementedError

    @property
    def shape(self):
        """The data shape as used by numpy."""
        return (1,)


class OscilloscopeCounterController(CounterController):
    # this should be generic for all oscilloscops
    # there should be no need to reimplement this one every time
    # comm should not be handeled directly in here...
    def __init__(self, scope):
        self._scope = scope
        CounterController.__init__(self, self._scope.name)

    # self._counters = {"Ch1": Counter("Ch1", self)}

    #  @property
    #  def _counters(self):
    #      return {c.name: c for c in self._scope.counters}

    #    @_counters.setter
    #    def _counters(self, value):
    #        # just a fake setter
    #        pass

    @property
    def counters(self):
        return self._scope.counters

    def get_acquisition_object(self, acq_params, ctrl_params, parent_acq_params):
        return OscilloscopeAcquisitionSlave(self, ctrl_params=ctrl_params, **acq_params)

    def get_default_chain_parameters(self, scan_params, acq_params):
        try:
            npoints = acq_params["npoints"]
        except KeyError:
            npoints = scan_params["npoints"]

        trigger = acq_params.get("trigger_type", "SOFTWARE")

        params = {}
        params["npoints"] = npoints
        params["trigger_type"] = trigger
        params["count_time"] = scan_params["count_time"]

        return params
