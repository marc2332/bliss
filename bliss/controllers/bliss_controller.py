# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from time import perf_counter, sleep
from itertools import chain
from gevent import event, sleep as gsleep

from bliss import global_map
from bliss.common.protocols import CounterContainer
from bliss.common.counter import (
    Counter,
    CalcCounter,
    SamplingCounter,
    IntegratingCounter,
)
from bliss.common.protocols import counter_namespace
from bliss.common.utils import autocomplete_property
from bliss.comm.util import get_comm
from bliss.controllers.motors.mockup import Mockup, MockupAxis
from bliss.controllers.counter import (
    CounterController,
    SamplingCounterController,
    IntegratingCounterController,
)
from bliss.scanning.acquisition.counter import BaseCounterAcquisitionSlave

# from bliss.config.beacon_object import BeaconObject

from bliss.common.logtools import log_info, log_debug, log_debug_data, log_warning


# ============ Note about BlissController ==============
#
## --- BlissController ---
# The BlissController base class is designed for the implementation of all controllers in Bliss.
# It ensures that all controllers have the following properties:
#
# class BlissController:
#    @name     (can be None if only sub-items are named)
#    @config   (yml config)
#    @hardware (associated hardware controller object, can be None if no hardware)
#    @counters (associated counters)
#    @axes     (associated axes: real/calc/soft/pseudo)
#
# Nothing else from the base class methods will be exposed at the first level object API.
#
# The BlissController is designed to ease the management of sub-objects that depend on a common device (@hardware).
# The sub-objects are declared in the yml configuration of the bliss controller under dedicated sub-sections.
#
# A sub-object is considered as a sub-item if it has a name (key 'name' in a sub-section of the config).
# Most of the time sub-items are counters and/or axes but could be anything else (known by the custom bliss controller).
#
# The BlissController has 2 properties (@counters, @axes) to retrieve sub-items that can be identified
# as counters (Counter) or axes (Axis).
#
## --- Plugin ---
# BlissController objects are created from the yml config using the bliss_controller plugin.
# Any sub-item with a name can be imported in a Bliss session with config.get('name').
# The plugin ensures that the controller and sub-items are only created once.
# The bliss controller itself can have a name (optional) and can be imported in the session.

# The plugin resolves dependencies between the BlissController and its sub-items.
# It looks for the 'class' key in the config to instantiate the BlissController.
# While importing any sub-item in the session, the bliss controller is instantiated first (if not alive already).
#
# !!! The effective creation of the sub-items is performed by the BlissController itself and the plugin just ensures
# that the controller is always created before sub-items and only once, that's all !!!
# The sub-items can be created during the initialization of the BlissController or via
# BlissController._create_sub_item(itemname, itemcfg, parentkey) which is called only on the first config.get('itemname')
#
## --- yml config ---
#
# - plugin: bliss_controller    <== use the dedicated bliss controller plugin
#   module: custom_module       <== module of the custom bliss controller
#   class: BCMockup             <== class of the custom bliss controller
#   name: bcmock                <== name of the custom bliss controller  (optional)
#
#   com:                        <== communication config for associated hardware (optional)
#     tcp:
#       url: bcmock
#
#   custom_param_1: value       <== a parameter for the custom bliss controller creation (optional)
#   custom_param_2: value       <== another parameter for the custom bliss controller creation (optional)
#
#   sub-section-1:              <== a sub-section where sub-items can be declared (optional) (ex: 'counters')
#     - name: sub_item_1        <== config of the sub-item
#       tag : item_tag_1        <== a tag for this item (known and interpreted by the custom bliss controller)
#       sub_param_1: value      <== a custom parameter for the item creation
#
#   sub-section-2:              <== a sub-section where sub-items can be declared (optional) (ex: 'axes')
#     - name: sub_item_2        <== config of the sub-item
#       tag : item_tag_2        <== a tag for this item (known and interpreted by the custom bliss controller)
#
#       sub-section-2-1:        <== nested sub-sections are possible (optional)
#         - name: sub_item_21
#           tag : item_tag_21
#
#   sub-section-3 :             <== a third sub-section without sub-items (no 'name' key) (optional)
#     - anything_but_name: foo  <== something interpreted by the custom bliss controller
#       something: value


class HardwareController:
    def __init__(self, config):
        self._config = config
        self._last_cmd_time = perf_counter()
        self._cmd_min_delta_time = 0

        self._init_com()

    @property
    def config(self):
        return self._config

    @property
    def comm(self):
        return self._comm

    def send_cmd(self, cmd, *values):
        now = perf_counter()
        log_info(self, f"@{now:.3f} send_cmd", cmd, values)
        if self._cmd_min_delta_time:
            delta_t = now - self._last_cmd_time
            if delta_t < self._cmd_min_delta_time:
                sleep(self._cmd_min_delta_time - delta_t)

        return self._send_cmd(cmd, *values)

    def _send_cmd(self, cmd, *values):
        if values:
            return self._write_cmd(cmd, *values)
        else:
            return self._read_cmd(cmd)

    def _init_com(self):
        log_info(self, "_init_com", self.config)
        self._comm = get_comm(self.config)
        global_map.register(self._comm, parents_list=[self, "comms"])

    # ========== NOT IMPLEMENTED METHODS ====================
    def _write_cmd(self, cmd, *values):
        # return self._comm.write(cmd, *values)
        raise NotImplementedError

    def _read_cmd(self, cmd):
        # return self._comm.read(cmd)
        raise NotImplementedError


class BlissController(CounterContainer):

    _COUNTER_TAGS = {}

    def __init__(self, config):

        self._config = config
        self._name = config.get("name")

        self._counter_controllers = {}
        self._hw_controller = None

        self._load_config()
        self._build_axes()
        self._build_counters()

        print("=== Create BlissController")

    @autocomplete_property
    def hardware(self):
        if self._hw_controller is None:
            self._hw_controller = self._get_hardware()
            print("=== _get_hardware", self._hw_controller)
        return self._hw_controller

    @property
    def name(self):
        return self._name

    @property
    def config(self):
        return self._config

    # ========== NOT IMPLEMENTED METHODS ====================

    def _get_hardware(self):
        """ Must return an HardwareController object """
        raise NotImplementedError

    def _create_sub_item(self, name, cfg, parent_key):
        """ Create/get and return an object which has a config name and which is owned by this controller
            This method is called by the Bliss Controller Plugin and is called after the controller __init__().
            This method is called only once per item on the first config.get('item_name') call (see plugin).

            args:
                'name': sub item name
                'cfg' : sub item config
                'parent_key': the config key under which the sub item was found (ex: 'counters').

            return: the sub item object
                
        """

        # === Example ===
        # if parent_key == 'counters':  #and name in self.counters._fields
        #     return self.counters[name]

        # elif parent_key == 'axes': # and name in self.axes._fields
        #     return self.axes[name]

        raise NotImplementedError

    def _load_config(self):
        """ Read and apply the YML configuration """

        # for k in self.config.keys():
        #     if k in self._SUB_CLASS:
        #         for cfg in self.config[k]:
        #             if cfg.get('name'):
        #                 self._objects[cfg.get('name')] = self._SUB_CLASS[k](self, cfg)

        raise NotImplementedError

    def _build_counters(self):
        """ Build the CounterControllers and associated Counters"""
        raise NotImplementedError

    def _build_axes(self):
        """ Build the Axes (real and pseudo) """
        raise NotImplementedError

    @autocomplete_property
    def counters(self):
        # cnts = [ctrl.counters for ctrl in self._counter_controllers.values()]
        # return counter_namespace(chain(*cnts))
        raise NotImplementedError

    @autocomplete_property
    def axes(self):
        # axes = [ctrl.axes for ctrl in self._axis_controllers]
        # return dict(ChainMap(*axes))
        raise NotImplementedError


# ========== MOCKUP CLASSES ==============================


class HCMockup(HardwareController):
    class FakeCom:
        def __init__(self, config):
            pass

        def read(self, cmd):
            return 69

        def write(self, cmd, *values):
            print("HCMockup write", cmd, values)
            return True

    def _init_com(self):
        log_info(self, "_init_com", self.config)
        self._comm = HCMockup.FakeCom(self.config)
        global_map.register(self._comm, parents_list=[self, "comms"])

    def _write_cmd(self, cmd, *values):
        return self._comm.write(cmd, *values)

    def _read_cmd(self, cmd):
        return self._comm.read(cmd)


class BCMockup(BlissController):

    _COUNTER_TAGS = {
        "current_temperature": ("cur_temp_ch1", "scc"),
        "integration_time": ("int_time", "icc"),
    }

    def _create_sub_item(self, name, cfg, parent_key):
        """ Create/get and return an object which has a config name and which is owned by this controller
            This method is called by the Bliss Controller Plugin and is called after the controller __init__().
            This method is called only once per item on the first config.get('item_name') call (see plugin).

            args:
                'name': sub item name
                'cfg' : sub item config
                'parent_key': the config key under which the sub item was found (ex: 'counters').

            return: the sub item object
                
        """

        if parent_key == "counters":
            return self.counters[name]

        elif parent_key == "axes":
            return self.axes[name]
            # return self._motor_controller.get_axis(name)

    def _get_hardware(self):
        """ Must return an HardwareController object """
        return HCMockup(self.config["com"])

    def _load_config(self):
        """ Read and apply the YML configuration """
        # print("load config", self.config)
        if self.config.get("energy"):
            self.energy = self.config.get("energy")

    def _build_counters(self):
        """ Build the CounterControllers and associated Counters"""
        self._counter_controllers["scc"] = BCSCC("scc", self)
        self._counter_controllers["icc"] = BCICC("icc", self)
        self._counter_controllers["scc"].max_sampling_frequency = self.config.get(
            "max_sampling_frequency", 1
        )

        for cfg in self.config.get("counters"):
            name = cfg["name"]
            tag = cfg["tag"]
            mode = cfg.get("mode")
            unit = cfg.get("unit")
            convfunc = cfg.get("convfunc")

            if self._COUNTER_TAGS[tag][1] == "scc":
                cnt = self._counter_controllers["scc"].create_counter(
                    SamplingCounter, name, unit=unit, mode=mode
                )

                cnt.tag = tag

            elif self._COUNTER_TAGS[tag][1] == "icc":
                cnt = self._counter_controllers["icc"].create_counter(
                    IntegratingCounter, name, unit=unit
                )

                cnt.tag = tag

    def _build_axes(self):
        """ Build the Axes (real and pseudo) """

        axes_cfg = {
            cfg["name"]: (MockupAxis, cfg) for cfg in self.config.get("axes", [])
        }

        self._motor_controller = Mockup(
            "motmock", {}, axes_cfg, [], [], []
        )  # self.config

        # === ??? initialize all now ???
        for name in axes_cfg.keys():
            self._motor_controller.get_axis(name)

    @autocomplete_property
    def counters(self):
        cnts = [ctrl.counters for ctrl in self._counter_controllers.values()]
        return counter_namespace(chain(*cnts))

    @autocomplete_property
    def axes(self):
        return counter_namespace(self._motor_controller.axes)


class BCSCC(SamplingCounterController):
    def __init__(self, name, bctrl):
        super().__init__(name)
        self.bctrl = bctrl

    def read_all(self, *counters):
        values = []
        for cnt in counters:
            tag_info = self.bctrl._COUNTER_TAGS.get(cnt.tag)
            if tag_info:
                values.append(self.bctrl.hardware.send_cmd(tag_info[0]))
            else:
                # returned number of data must be equal to the length of '*counters'
                # so raiseError if one of the received counter is not handled
                raise ValueError(f"Unknown counter {cnt} with tag {cnt.tag} !")
        return values


class BCICC(CounterController):
    def __init__(self, name, bctrl):
        super().__init__(name)
        self.bctrl = bctrl
        self.count_time = None

    def get_acquisition_object(self, acq_params, ctrl_params, parent_acq_params):
        return BCIAS(self, ctrl_params=ctrl_params, **acq_params)

    def get_default_chain_parameters(self, scan_params, acq_params):

        try:
            count_time = acq_params["count_time"]
        except KeyError:
            count_time = scan_params["count_time"]

        try:
            npoints = acq_params["npoints"]
        except KeyError:
            npoints = scan_params["npoints"]

        params = {"count_time": count_time, "npoints": npoints}

        return params

    def read_data(self):
        gsleep(self.count_time)


class BCIAS(BaseCounterAcquisitionSlave):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._reading_event = event.Event()

    def prepare(self):
        self.device.count_time = self.count_time

    def start(self):
        pass

    def stop(self):
        pass

    def trigger(self):
        pass

    def reading(self):
        t0 = perf_counter()
        self.device.read_data()
        dt = perf_counter() - t0
        self._emit_new_data([[dt]])
