# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import functools

from bliss.common.measurementgroup import (
    MeasurementGroup,
    get_active as get_active_mg,
    _get_counters_from_measurement_group,
    _get_counters_from_object,
)
from bliss.common.counter import CalcCounter, Counter
from bliss.controllers.counter import CalcCounterController, CounterController
from bliss.scanning.chain import AcquisitionChain
from bliss.scanning.acquisition.timer import SoftwareTimerMaster


def get_all_counters(counter_args):
    # Initialize
    all_counters, missing = [], []

    # Process all counter arguments
    for obj in counter_args:
        try:
            if isinstance(obj, MeasurementGroup):
                all_counters += _get_counters_from_measurement_group(obj)
            else:
                all_counters += _get_counters_from_object(obj)
        except AttributeError as exc:
            missing += exc.args

    # Missing counters
    if missing:
        raise ValueError(
            "Missing counters, not in global_map: {}.\n"
            "Hint: disable inactive counters.".format(
                ", ".join([x if type(x) == type("") else x.name for x in missing])
            )
        )

    for cnt in all_counters:
        if not isinstance(cnt, Counter):
            raise TypeError(f"{cnt} is not a Counter object")

    return all_counters


def sort_counter_by_dependency_level(counters):
    def cmp_sort(cnt1, cnt2):
        if cnt1 in cnt2._counter_controller.counters:
            return -1
        elif cnt2 in cnt1._counter_controller.counters:
            return 1
        else:
            return len(cnt1._counter_controller.counters) - len(
                cnt2._counter_controller.counters
            )

    counters.sort(key=functools.cmp_to_key(cmp_sort))


class ChainBuilder:
    """ Helper object to build the acquisition chain from a list of (measurementgroup, controllers, counter_groups, counters) objects """

    def __init__(self, counters):

        self._counter_list = None
        self._cached_nodes = {}
        self._build_counter_list(counters)
        self._introspect()

    def _build_counter_list(self, counters):
        """ Build the list of counters from a list of [measurementgroup, controllers, counter_groups, counters].
            The list is sorted from the less dependent counter to the most dependent counter (see CalcCounters).
            Duplicated counters are removed.
        """
        if not counters:
            active_mg = get_active_mg()
            if active_mg:
                counters = [active_mg]
        # print(f"=== counters: {counters}")

        # --- counters = [MG, cnt, ctrl, cnt_grp]
        counter_list = get_all_counters(
            counters
        )  # => also add the counters dependecies of CalcCounterController
        # print("===== received counter_list", [x.name for x in counter_list ])

        # --- Remove duplicates ----------------------------------
        counter_dct = {counter.fullname: counter for counter in counter_list}

        # --- Sort counters ------------------------------------------------------
        counter_list = [counter for name, counter in sorted(counter_dct.items())]

        # --- Separate real and calc counters
        real_counters = [
            cnt for cnt in counter_list if not isinstance(cnt, CalcCounter)
        ]
        calc_counters = [cnt for cnt in counter_list if isinstance(cnt, CalcCounter)]

        # --- sort calc counters from the less dependent to the most dependent ------------
        sort_counter_by_dependency_level(calc_counters)

        # print("===== real_counters", [x.name for x in real_counters ])
        # print("===== calc_counters", [x.name for x in calc_counters ])

        counter_list = real_counters + calc_counters
        # print("===== counter_list", [x.name for x in counter_list ])

        # --- if no counters --------------------------------------------------------------
        if not counter_list:
            raise ValueError("No counters for scan. Hint: are all counters disabled ?")

        self._counter_list = counter_list

    def _get_node_from_controller(self, controller):
        return controller.create_chain_node()

    def _create_node(self, controller):
        """ Create and store the ChainNode associated to a controller.
            Return the cached node if it already exist.
            Register the CalcCounterController dependencies into the node.
        """

        if self._cached_nodes.get(controller) is None:
            node = self._get_node_from_controller(controller)
            self._cached_nodes[controller] = node

            # --- add dependencies knowledge to calc_nodes -----------------------------
            if isinstance(controller, CalcCounterController):
                for cnt in node.controller.inputs:
                    node._calc_dep_nodes[cnt._counter_controller] = self._cached_nodes[
                        cnt._counter_controller
                    ]
        else:
            node = self._cached_nodes.get(controller)

        return node

    def _introspect(self):
        """ Build the chain nodes from the counter list """

        for cnt in self._counter_list:

            if cnt._counter_controller is None:
                raise AttributeError(f"counter: {cnt} must have a controller")

            master_ctrl = cnt._counter_controller._master_controller
            master_node = None

            if master_ctrl is not None:
                master_node = self._create_node(master_ctrl)

            node = self._create_node(cnt._counter_controller)
            node.add_counter(cnt)

            if master_node is not None:
                master_node.add_child(node)

    @property
    def nodes(self):
        return self.get_top_level_nodes()

    # ---------- Nodes filtering tools -------------------------------
    def get_all_nodes(self):
        """ return all nodes (top_level and children nodes)"""
        return self._cached_nodes.values()

    def get_top_level_nodes(self, nodes=None):
        """return top level nodes"""
        if nodes is None:
            nodes = self.get_all_nodes()
        return [node for node in nodes if node.is_top_level]

    # ------- Filtering methods which by default works on the top_level_nodes only -----------
    def get_nodes_by_controller_type(self, ctrl_class, nodes=None):
        if nodes is None:
            nodes = self.nodes
        return [node for node in nodes if isinstance(node.controller, ctrl_class)]

    def get_nodes_by_acquisition_type(self, acq_obj_class, nodes=None):
        if nodes is None:
            nodes = self.nodes
        return [
            node for node in nodes if isinstance(node.acquisition_obj, acq_obj_class)
        ]

    def get_nodes_by_node_type(self, node_class, nodes=None):
        if nodes is None:
            nodes = self.nodes
        return [node for node in nodes if isinstance(node, node_class)]

    def get_nodes_not_ready(self, nodes=None):
        if nodes is None:
            nodes = self.nodes
        return [node for node in nodes if node.acquisition_obj is None]

    def get_nodes_with_cildren(self, nodes=None):
        if nodes is None:
            nodes = self.nodes
        return [node for node in nodes if len(node.children) > 0]

    def get_nodes_by_controller_name(self, name, nodes=None):
        if nodes is None:
            nodes = self.nodes
        return [node for node in nodes if node.controller.name == name]

    def print_tree(self, nodes=None, not_ready_only=True):
        if nodes is None:
            nodes = self.get_all_nodes()

        if not_ready_only:
            if len(self.get_nodes_not_ready(nodes)) == 0:
                return

        top_nodes = self.get_top_level_nodes(nodes)

        print("\n")

        for node in top_nodes:

            print(f"-->{ node.get_repr_str() }")

            for child in node.children:
                print("      |")
                print(f"      { child.get_repr_str() }")

            print("\n")


# ---------------------- DEFAULT CHAIN ---------------------------------------------------


class DefaultAcquisitionChain:
    def __init__(self):
        self._settings = dict()
        self._presets = dict()

    def set_settings(self, settings_list):
        """
        Set the default acquisition parameters for devices in the default scan
        chain

        Args:
            `settings_list` is a list of dictionaries. Each dictionary has:

            * 'device' key, with the device object parameters corresponds to
            * 'acquisition_settings' dictionary, that will be passed as keyword args
              to the acquisition device
            * 'master' key (optional), points to the master device

            Example YAML:

            -
                device: $frelon
                acquisition_settings:
                    acq_trigger_type: EXTERNAL
                    ...
                master: $p201
        """
        default_settings = dict()
        for device_settings in settings_list:
            acq_settings = device_settings.get("acquisition_settings", {})
            master = device_settings.get("master")

            device = device_settings["device"]
            if isinstance(device, Counter):
                controller = device._counter_controller
            else:
                controller = device

            default_settings[controller] = {
                "acquisition_settings": acq_settings,
                "master": master,
            }

        self._settings = default_settings

    def add_preset(self, preset):
        self._presets[id(preset)] = preset

    def get(self, scan_pars, counter_args, top_master=None):

        # Scan parameters
        count_time = scan_pars.get("count_time", 1)
        sleep_time = scan_pars.get("sleep_time")
        npoints = scan_pars.get("npoints", 1)

        chain = AcquisitionChain(parallel_prepare=True)

        # Build default master
        timer = SoftwareTimerMaster(count_time, npoints=npoints, sleep_time=sleep_time)

        builder = ChainBuilder(counter_args)

        # --- create acq obj and populate the chain
        topnodes = builder.get_top_level_nodes()
        for node in topnodes:

            # print(f"====== for {node.controller} {node.controller.counters._asdict().keys()} in topnodes")

            extra_settings = self._settings.get(node.controller)
            if extra_settings:
                # print("==== FOUND EXTRA SETTINGS")
                acq_params = extra_settings.get("acquisition_settings", {})
                acq_params = node._get_default_chain_parameters(scan_pars, acq_params)
                node.set_parameters(acq_params=acq_params)

                # DEAL WITH CHILDREN NODES PARAMETERS
                for cnode in node.children:
                    acq_params = cnode._get_default_chain_parameters(scan_pars, {})
                    cnode.set_parameters(acq_params=acq_params)

                # --- recursive add master -----------------------------------------------------
                mstr = extra_settings.get("master")
                while mstr:

                    mstr_node = builder._create_node(mstr)

                    # -- check if master has params and/or a parent master
                    mstr_settings = self._settings.get(mstr)
                    if mstr_settings:
                        mstr_params = mstr_settings.get("acquisition_settings")
                        mstr = mstr_settings.get("master")
                    else:
                        mstr_params = {}
                        mstr = None

                    mstr_params = mstr_node._get_default_chain_parameters(
                        scan_pars, mstr_params
                    )
                    mstr_node.set_parameters(acq_params=mstr_params)

                    chain.add(mstr_node, node)
                    node = mstr_node

                chain.add(timer, node)

            else:
                acq_params = node._get_default_chain_parameters(scan_pars, {})
                node.set_parameters(acq_params=acq_params)

                # DEAL WITH CHILDREN NODES PARAMETERS
                for cnode in node.children:
                    acq_params = cnode._get_default_chain_parameters(scan_pars, {})
                    cnode.set_parameters(acq_params=acq_params)

                chain.add(timer, node)

        # Add presets
        for preset in self._presets.values():
            chain.add_preset(preset)

        # Add top master, if any
        if top_master:
            chain.add(top_master, timer)

        chain.timer = timer

        # builder.print_tree(not_ready_only=False)
        # print(chain._tree)

        return chain
