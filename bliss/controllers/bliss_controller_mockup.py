# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from time import perf_counter, sleep
from itertools import chain
from collections import ChainMap
from gevent import event, sleep as gsleep

from bliss import global_map
from bliss.common.counter import (
    SamplingCounter
)  # make it available at ctrl level for plugin and tests
from bliss.common.protocols import counter_namespace, IterableNamespace
from bliss.common.utils import autocomplete_property
from bliss.comm.util import get_comm
from bliss.controllers.counter import CounterController, SamplingCounterController
from bliss.scanning.acquisition.counter import BaseCounterAcquisitionSlave

from bliss.common.logtools import log_info, log_debug, log_debug_data, log_warning

from bliss.controllers.bliss_controller import BlissController, from_config_dict
from bliss.controllers.motors.mockup import Mockup, calc_motor_mockup


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

    def _create_hardware(self):
        """ return the low level hardware controller interface """
        return HCMockup(self.config["com"])

    def _get_subitem_default_module(self, class_name, cfg, parent_key):
        if class_name == "IntegratingCounter":
            return "bliss.common.counter"

    def _get_subitem_default_class_name(self, cfg, parent_key):
        if parent_key == "counters":
            tag = cfg["tag"]
            if self._COUNTER_TAGS[tag][1] == "scc":
                return "SamplingCounter"
            elif self._COUNTER_TAGS[tag][1] == "icc":
                return "IntegratingCounter"

    def _create_subitem_from_config(self, name, cfg, parent_key, item_class):
        if parent_key == "counters":
            name = cfg["name"]
            tag = cfg["tag"]
            mode = cfg.get("mode")
            unit = cfg.get("unit")
            convfunc = cfg.get("convfunc")

            if self._COUNTER_TAGS[tag][1] == "scc":
                cnt = self._counter_controllers["scc"].create_counter(
                    item_class, name, unit=unit, mode=mode
                )
                cnt.tag = tag

            elif self._COUNTER_TAGS[tag][1] == "icc":
                cnt = self._counter_controllers["icc"].create_counter(
                    item_class, name, unit=unit
                )
                cnt.tag = tag

            else:
                raise ValueError(f"cannot identify counter tag {tag}")

            return cnt

        elif parent_key == "operators":
            return item_class(cfg)

        elif parent_key == "axes":
            if item_class is None:  # mean it is a referenced axis (i.e external axis)
                axis = name  # the axis instance
                name = axis.name  # the axis name
                tag = cfg[
                    "tag"
                ]  # ask for a tag which only concerns this ctrl (local tag)
                self._tag2axis[tag] = name  # store the axis tag
                return axis
            else:
                raise ValueError(
                    f"{self} only accept referenced axes"
                )  # reject none-referenced axis

    def _load_config(self):
        self._calc_mot = None

        if self.config.get("energy"):
            self.energy = self.config.get("energy")

        # create different counter controllers
        self._counter_controllers = {}
        self._counter_controllers["scc"] = BCSCC("scc", self)
        self._counter_controllers["icc"] = BCICC("icc", self)
        self._counter_controllers["scc"].max_sampling_frequency = self.config.get(
            "max_sampling_frequency", 1
        )

        # create the counter subitems now in order to have all of them immediately available after ctrl init
        for cfg, pkey in self._subitems_config.values():
            if pkey == "counters":
                self._get_subitem(cfg["name"])  # force item creation now

        # prepare a storage for the tags associated to the axes referenced in the config
        if self.config.get("axes") is not None:
            self._tag2axis = {}

    @autocomplete_property
    def counters(self):
        cnts = [ctrl.counters for ctrl in self._counter_controllers.values()]
        return counter_namespace(chain(*cnts))

    @autocomplete_property
    def axes(self):
        return IterableNamespace(
            **{name: self._subitems[name] for name in self._tag2axis.values()}
        )

    def get_axis(self, name):
        return self._get_subitem(name)

    def available_axis_names(self):
        return [k for k, v in self._subitems_config.items() if v[1] == "axes"]

    @property
    def calc_mot(self):
        if self._calc_mot is None:
            self._calc_mot = self.config.get("calc_controller")
        return self._calc_mot


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


class FakeItem:
    def __init__(self, cfg, ctrl):
        self.name = cfg["name"]
        self.tag = cfg.get("tag")
        self.controller = ctrl


class Operator:
    def __init__(self, cfg):
        self.name = cfg["name"]
        self.tag = cfg.get("tag")
        self.factor = cfg["factor"]
        self.input = cfg["input"]


class TestBCMockup(BCMockup):
    def _create_subitem_from_config(self, name, cfg, parent_key, item_class):

        item = super()._create_subitem_from_config(name, cfg, parent_key, item_class)

        if item is None:
            if parent_key in ["fakeitems", "subsection"]:
                return item_class(cfg, self)

        return item

    def _get_subitem_default_class_name(self, cfg, parent_key):
        class_name = super()._get_subitem_default_class_name(cfg, parent_key)
        if class_name is None:
            if parent_key == "fakeitems":
                return "FakeItem"
        return class_name
