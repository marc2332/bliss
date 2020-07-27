# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Module to manage scan with automatic filter.

Yaml config may look like this:
- plugin: bliss
  class: AutoFilter
  name: autof_eh1
  package: bliss.common.auto_filter
  detector_counter_name: roi1
  monitor_counter_name: mon
  min_count_rate: 20000
  max_count_rate: 50000
  energy_axis: $eccmono
  filterset: $filtW1

# optionnal parameters
  always_back: True
  counters:
    - counter_name: curratt
      tag: fiteridx
    - counter_name: transm
      tag: transmission
   - counter_name: ratio
     tag: ratio
  suffix_for_corr_counter: "_corr"
  counters_for_correction:
    - det
    - apdcnt
"""

import weakref
import numpy
from tabulate import tabulate
from bliss.config.beacon_object import BeaconObject
from bliss.common import scans
from bliss.scanning import chain, scan
from bliss.common.event import dispatcher
from bliss.common.measurementgroup import _get_counters_from_names
from bliss.common.measurementgroup import get_active as get_active_mg
from bliss.common.counter import SamplingCounter
from bliss.controllers.counter import (
    SamplingCounterController,
    CalcCounterController,
    CalcCounter,
)
from bliss.common.utils import autocomplete_property
from bliss.common.utils import rounder
from bliss import global_map
from bliss.common.session import get_current_session
from bliss.scanning.scan import ScanPreset
from bliss.common.axis import Axis
from bliss.common.cleanup import cleanup, axis as cleanup_axis
from bliss.common.types import _countable
from bliss.common.protocols import counter_namespace
from bliss import global_map
from bliss.common.auto_filter.filterset import FilterSet

from . import acquisition_objects


class AutoFilterCounterController(SamplingCounterController):
    def __init__(self, name, autof):
        super().__init__(name)
        self._autof = autof

    def read_all(self, *counters):
        values = []
        for cnt in counters:
            if cnt.tag == "filteridx":
                values.append(self._autof.filterset.get_filter())
            elif cnt.tag == "transmission":
                values.append(self._autof.transmission)
        return values


class CorrCounterController(CalcCounterController):
    def __init__(self, autof, config):
        self._autof = autof
        super().__init__(autof.name, {}, register_counters=False)
        self._ratio_counter = None

        for counter_config in config.get("counters", []):
            counter_name = counter_config.get("counter_name")
            tag = counter_config.get("tag")
            if tag == "ratio":
                cnt_ratio = CalcCounter(counter_name, self)
                self.tags[cnt_ratio.name] = tag
                self._output_counters.append(cnt_ratio)
                self._ratio_counter = cnt_ratio

    def build_counters(self, config):
        pass

    @property
    def inputs(self):
        mon = self._autof.monitor_counter
        self.tags[mon.name] = "monitor"
        det = self._autof.detector_counter
        self.tags[det.name] = "detector"

        return counter_namespace([mon, det])

    @property
    def outputs(self):
        output_counters = list(self._output_counters)
        det_name = self._autof.detector_counter_name
        if det_name:
            det_name = det_name.split(":")[-1]
            corr_suffix = self._autof.corr_suffix
            det_corr = CalcCounter(f"{det_name}{corr_suffix}", self)
            self.tags[det_corr.name] = "detector_corr"
            self._detector_corr = det_corr
            output_counters.append(det_corr)
        return counter_namespace(output_counters)

    def calc_function(self, input_dict):
        monitor_values = input_dict.get("monitor", [])
        detector_values = input_dict.get("detector", [])
        if len(monitor_values) and len(detector_values):
            transmission = self._autof.transmission
            # calc the corrected counters
            detector_corr_values = detector_values / transmission
            # calc the ration counter
            ratio_values = detector_corr_values / monitor_values

            return {
                self.tags[self._ratio_counter.name]: ratio_values,
                self.tags[self._detector_corr.name]: detector_corr_values,
            }
        else:
            return {}


class AutoFilter(BeaconObject):
    detector_counter_name = BeaconObject.property_setting(
        "detector_counter_name", doc="Detector counter name"
    )
    monitor_counter_name = BeaconObject.property_setting(
        "monitor_counter_name", doc="Monitor counter name"
    )

    @detector_counter_name.setter
    def detector_counter_name(self, counter_name):
        assert isinstance(counter_name, str)
        return counter_name

    @monitor_counter_name.setter
    def monitor_counter_name(self, counter_name):
        assert isinstance(counter_name, str)
        return counter_name

    @property
    def detector_counter(self):
        counters, missing = _get_counters_from_names([self.detector_counter_name])
        if missing:
            raise RuntimeError(
                f"Can't find detector counter named {self.detector_counter_name}"
            )
        return counters[0]

    @detector_counter.setter
    def detector_counter(self, counter):
        if isinstance(counter, str):
            # check that counter exists ... not sure if the next lines work in all cases
            try:
                global_map.get_counter_from_fullname(counter)
                self.detector_counter_name = counter
            except AttributeError:
                raise "unknown detector counter"
        elif isinstance(counter, _countable):
            self.detector_counter_name = counter.fullname
        else:
            raise "unknown detector counter"

    @property
    def monitor_counter(self):
        counters, missing = _get_counters_from_names([self.monitor_counter_name])
        if missing:
            raise RuntimeError(
                f"Can't find detector counter named {self.monitor_counter_name}"
            )
        return counters[0]

    @monitor_counter.setter
    def monitor_counter(self, counter):
        if isinstance(counter, str):
            # check that counter exists ... not sure if the next lines work in all cases
            try:
                global_map.get_counter_from_fullname(counter)
                self.monitor_counter_name = counter
            except AttributeError:
                raise "unknown detector counter"
        elif isinstance(counter, _countable):
            self.monitor_counter_name = counter.fullname
        else:
            raise "unknown detector counter"

    min_count_rate = BeaconObject.property_setting(
        "min_count_rate",
        must_be_in_config=True,
        doc="Minimum allowed count rate on monitor",
    )
    max_count_rate = BeaconObject.property_setting(
        "max_count_rate",
        must_be_in_config=True,
        doc="Maximum allowed count rate on monitor",
    )
    always_back = BeaconObject.property_setting(
        "always_back",
        must_be_in_config=False,
        default=True,
        doc="Always move back the filter to the original position at the end of the scan",
    )
    corr_suffix = BeaconObject.property_setting(
        "corr_suffix",
        must_be_in_config=False,
        default="_corr",
        doc="suffix to be added to the corrected counters",
    )

    filterset = BeaconObject.config_obj_property_setting(
        "filterset", doc="filterset to attached to the autofilter"
    )

    @filterset.setter
    def filterset(self, new_filterset):
        assert isinstance(new_filterset, FilterSet)
        self.initialize(new_filterset)
        # as this is a config_obj_property_setting
        # the setter has to return the name of the
        # corresponding beacon object
        return new_filterset

    def __init__(self, name, config):
        super().__init__(config, share_hardware=False)

        global_map.register(self, tag=self.name, parents_list=["counters"])

        self.__energy_axis = None
        self.__counters_for_corr = set()

        # build counters
        self._create_counters(config)

        # get counters for correction
        counters = config.get("counters_for_correction", [])
        self.counters_for_correction = counters

        # check energy motor is in config
        # this property set calls initialize()
        self.energy_axis = config.get("energy_axis")

    def initialize(self, new_filterset=None):
        """
        intialize the behind filterset
        """
        if new_filterset:
            _filterset = new_filterset
        else:
            _filterset = self.filterset

        self.__initialized = True
        # Synchronize the filterset with countrate range and energy
        # and tell it to store back filter if necessary
        self.__last_energy = self.energy_axis.position
        if self.__last_energy > 0:
            # filterset sync. method return the maximum effective number of filters
            # which will correspond to the maximum number of filter changes
            self.max_nb_iter = _filterset.sync(
                self.min_count_rate,
                self.max_count_rate,
                self.__last_energy,
                self.always_back,
            )
        else:
            self.__initialized = False

    @property
    def energy_axis(self):
        """
        Setter/getter for the energy axis,
        check the instance is an axis
        """
        return self.__energy_axis

    @energy_axis.setter
    def energy_axis(self, energy_axis):
        if energy_axis != self.__energy_axis:
            if isinstance(energy_axis, Axis):
                self.__energy_axis = energy_axis
                # change on energy, so get filterset initialized back
                self.initialize()
            else:
                raise ValueError(f"{energy_axis} is not a Bliss Axis")

    @property
    def counters_for_correction(self):
        """
        Return the list of counters to be added as corrected.
        Internally used by the _Base class to create new channels
        """
        return list(self.__counters_for_corr)

    @counters_for_correction.setter
    def counters_for_correction(self, counters):
        if not isinstance(counters, list):
            counters = list(counters)
        # build the list of counter to be corrected, a new counter will be added
        # using same name + corr_suffix.
        # The monitor counter is the default, remove missing counters.
        cnts, missing = _get_counters_from_names(counters)
        for cnt in cnts:
            self.__counters_for_corr.add(cnt.fullname)

        # Check monitor exists

    @autocomplete_property
    def counters(self):
        """ 
        Standard counter namespace
        """
        counters = []
        if self._cc is not None:
            counters += list(self._cc.counters)
        if self._calc_counter is not None:
            counters += list(self._calc_counter.outputs)
        return counter_namespace(counters)

    @property
    def transmission(self):
        """
        Return the current transmission given by the filter
        """
        if self.__last_energy != self.energy_axis.position:
            self.initialize()
        return self.filterset.transmission

    @property
    def filter(self):
        return self.filterset.filter

    @filter.setter
    def filter(self, new_filter):
        self.filterset.filter = new_filter

    def ascan(self, motor, start, stop, intervals, count_time, *counter_args, **kwargs):
        """
        Basically same as normal ascan with auto filter management
        """
        scan_pars = {"type": "ascan"}
        return self.anscan(
            [(motor, start, stop)],
            intervals,
            count_time,
            *counter_args,
            scan_info=scan_pars,
            **kwargs,
        )

    def a2scan(
        self,
        motor1,
        start1,
        stop1,
        motor2,
        start2,
        stop2,
        intervals,
        count_time,
        *counter_args,
        **kwargs,
    ):
        """
        Basically same as normal ascan with auto filter management
        """
        scan_pars = {"type": "ascan"}
        return self.anscan(
            [(motor1, start1, stop1), (motor2, start2, stop2)],
            intervals,
            count_time,
            *counter_args,
            scan_info=scan_pars,
            **kwargs,
        )

    def dscan(self, motor, start, stop, intervals, count_time, *counter_args, **kwargs):
        """
        Basically same as normal ascan with auto filter management
        """
        scan_pars = {"type": "dscan"}
        with cleanup(motor, restore_list=(cleanup_axis.POS,), verbose=True):
            return self.anscan(
                [(motor, start, stop)],
                intervals,
                count_time,
                *counter_args,
                scan_info=scan_pars,
                scan_type="dscan",
                name="dscan",
                **kwargs,
            )

    def d2scan(
        self,
        motor1,
        start1,
        stop1,
        motor2,
        start2,
        stop2,
        intervals,
        count_time,
        *counter_args,
        **kwargs,
    ):
        """
        Basically same as normal ascan with auto filter management
        """
        scan_pars = {"type": "dscan"}
        with cleanup(motor1, motor2, restore_list=(cleanup_axis.POS,), verbose=True):
            return self.anscan(
                [(motor1, start1, stop1), (motor2, start2, stop2)],
                intervals,
                count_time,
                *counter_args,
                scan_info=scan_pars,
                scan_type="dscan",
                name="dscan",
                **kwargs,
            )

    def anscan(
        self,
        motor_tuple_list,
        intervals,
        count_time,
        *counter_args,
        scan_info=None,
        scan_type=None,
        **kwargs,
    ):
        # initialize the filterset
        # maybe better to use a ScanPreset
        self.initialize()
        if not self.__initialized:
            raise RuntimeError(
                f"Cannot run AutoFilter scan, your energy is not valid: {self.energy_axis.position} keV"
            )
        save_flag = kwargs.get("save", True)
        programed_device_intervals = (intervals + 1) * self.max_nb_iter
        npoints = intervals + 1
        if scan_info is None:
            scan_info = dict()
        scan_info.update(
            {
                "npoints": programed_device_intervals,
                "count_time": count_time,
                "sleep_time": kwargs.get("sleep_time"),
                "save": save_flag,
            }
        )

        # Check detector exists
        detector_counter_name = self.detector_counter_name
        counters, missing = _get_counters_from_names([detector_counter_name])
        if missing:
            raise RuntimeError(
                f"Can't find detector counter named {detector_counter_name}"
            )
        detector_counter = counters[0]
        # Check detector exists
        monitor_counter_name = self.monitor_counter_name
        counters, missing = _get_counters_from_names([monitor_counter_name])
        if missing:
            raise RuntimeError(
                f"Can't find monitor counter named {monitor_counter_name}"
            )
        monitor_counter = counters[0]

        if not counter_args:  # use the default measurement group
            counter_args = [get_active_mg()] + [detector_counter, monitor_counter]
        else:
            counter_args = list(counter_args) + [detector_counter, monitor_counter]

        default_chain = scans.DEFAULT_CHAIN.get(scan_info, counter_args)
        final_chain, detector_channel = self._patch_chain(
            default_chain, npoints, detector_counter
        )

        class Validator:
            def __init__(self, autofilter):
                self.__autofilter = weakref.proxy(autofilter)
                self._point_nb = 0
                dispatcher.connect(
                    self.new_detector_value, "new_data", detector_channel
                )

            def new_detector_value(self, event_dict=None, signal=None, sender=None):
                data = event_dict.get("data")
                if data is not None:
                    # check for filter change, return false
                    # if filter has been changed, and count must be repeated
                    valid = self.__autofilter.check_filter(count_time, data)
                    for node in final_chain.nodes_list:
                        if hasattr(node, "validate_point"):
                            node.validate_point(self._point_nb, valid)
                    self._point_nb += 1

        validator = Validator(self)

        motors_positions = list()
        title_list = list()

        for m_tup in motor_tuple_list:
            mot = m_tup[0]
            d = mot._set_position if scan_type == "dscan" else 0
            start = m_tup[1]
            stop = m_tup[2]
            title_list.extend(
                (mot.name, rounder(mot.tolerance, start), rounder(mot.tolerance, stop))
            )
            start = m_tup[1] + d
            stop = m_tup[2] + d
            motors_positions.extend((mot, numpy.linspace(start, stop, npoints)))

        top_master = acquisition_objects.VariableStepTriggerMaster(*motors_positions)

        # scan type is forced to be either aNscan or dNscan
        if scan_type == "dscan":
            scan_type = (
                f"autof.d{len(title_list)//3}scan"
                if len(title_list) // 3 > 1
                else "autof.dscan"
            )
        else:
            scan_type = (
                f"autof.a{len(title_list)//3}scan"
                if len(title_list) // 3 > 1
                else "autof.ascan"
            )
        name = kwargs.setdefault("name", None)
        if not name:
            name = scan_type

        # build the title
        args = [scan_type]
        args += title_list
        args += [intervals, count_time]
        template = " ".join(["{{{0}}}".format(i) for i in range(len(args))])
        title = template.format(*args)
        scan_info["title"] = title

        #  finally the scan
        timer = final_chain.top_masters.pop(0)
        final_chain.add(top_master, timer)
        s = scan.Scan(
            final_chain,
            scan_info=scan_info,
            name=name,
            save=kwargs.get("save", True),
            save_images=kwargs.get("save_images"),
            data_watch_callback=scan.StepScanDataWatch(),
        )

        # Add a presetscan
        preset = AutoFilterPreset(self)
        s.add_preset(preset)

        if kwargs.get("run", True):
            s.run()
        return s

    def _patch_chain(self, default_chain, npoints, detector_counter):
        final_chain = chain.AcquisitionChain(parallel_prepare=True)
        detector_channel = None
        # use the built **default_chain** and replace all
        # acquisition object with autofilter one.
        for master in (
            x
            for x in default_chain._tree.expand_tree()
            if isinstance(x, chain.AcquisitionMaster)
        ):
            final_master = acquisition_objects.get_new_master(self, master, npoints)
            for slave in default_chain._tree.get_node(master).fpointer:
                final_slave = acquisition_objects.get_new_slave(self, slave, npoints)
                final_chain.add(final_master, final_slave)
                if detector_channel is None:
                    for channel in slave.channels:
                        if channel.fullname == detector_counter.fullname:
                            detector_channel = channel
                            break
        return final_chain, detector_channel

    def __info__(self):
        table_info = []
        for sname in (
            "monitor_counter_name",
            "detector_counter_name",
            "min_count_rate",
            "max_count_rate",
            "always_back",
        ):
            table_info.append([sname, getattr(self, sname)])
        info = str(tabulate(table_info, headers=["Parameter", "Value"]))
        info += "\n\n" + f"Active filterset: {self.filterset.name}"
        info += (
            "\n"
            + f"Energy axis {self.energy_axis.name}: {self.energy_axis.position:.5g} keV"
        )

        # calling transmission can update the filterset info_table if the energy has changed
        transm = self.transmission

        info += (
            "\n\n"
            + f"Active filter idx {self.filterset.filter}, transmission {transm:g}"
        )

        info += "\n\n" + "Table of Effective Filters :"
        if self.__initialized:
            info += "\n" + self.filterset.info_table()
        else:
            info += "\n Cannot get effective filters, check your energy, please !!!"
        return info

    def check_filter(self, count_time, counts):
        """
        Check if filterset needs to be adjusted.
        Return False if the counting must be repeated
        """
        return self.filterset.adjust_filter(count_time, counts)

    def _create_counters(self, config, export_to_session=True):
        """
        """
        cnts_conf = config.get("counters")
        if cnts_conf is None:
            self._cc = None
            self._calc_counter = None
            return

        # create the sampling counters for transm and currfilter
        self._cc = AutoFilterCounterController(self.name, self)
        # create calc counters for det_corr and ratio
        self._calc_counter = CorrCounterController(self, config)

        for conf in cnts_conf:
            name = conf["counter_name"].strip()
            tag = conf["tag"].strip()
            if tag == "ratio":
                continue
            cnt = self._cc.create_counter(SamplingCounter, name, mode="SINGLE")
            cnt.tag = tag
            if export_to_session:
                current_session = get_current_session()
                if current_session is not None:
                    if (
                        name in current_session.config.names_list
                        or name in current_session.env_dict.keys()
                    ):
                        raise ValueError(
                            f"Cannot export object to session with the name '{name}', name is already taken! "
                        )

                    current_session.env_dict[name] = cnt

    def corr_func(self, point_nb, name, data):
        """
        Return the data corrected taking care of the effective transmission.
        """
        return data / self.transmission


class AutoFilterPreset(ScanPreset):
    """
    ScanPreset class for AutoFilter, 
    Manage always_back property
    """

    def __init__(self, auto_filter):
        self.auto_filter = auto_filter
        super().__init__()

        def user_status():
            with self.auto_filter.filterset._user_status():
                yield

        self._user_status = iter(user_status())
        next(self._user_status)

    def stop(self, scan):
        try:
            if self.auto_filter.always_back:
                self.auto_filter.filterset.set_back_filter()
        finally:
            next(self._user_status, None)
