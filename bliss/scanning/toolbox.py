# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import warnings
import operator
import functools

from bliss import global_map
from bliss import setup_globals
from bliss.common import measurementgroup

from bliss.scanning.chain import AcquisitionChain
from bliss.scanning.acquisition.timer import SoftwareTimerMaster
from bliss.common.measurement import CalcCounter, CalcCounterController, BaseCounter


def _get_object_from_name(name):
    """Get the bliss object corresponding to the given name."""
    try:
        return operator.attrgetter(name)(setup_globals)
    except AttributeError:
        raise AttributeError(name)


def _get_counters_from_measurement_group(mg):
    """Get the counters from a measurement group."""
    counters, missing = [], []
    for name in mg.enabled:
        try:
            obj = _get_object_from_name(name)
        except AttributeError:
            missing.append(name)
        else:
            # Prevent groups from pointing to other groups
            counters += _get_counters_from_object(obj, recursive=False)
    if missing:
        raise AttributeError(*missing)
    return counters


def _get_counters_from_object(arg, recursive=True):
    """Get the counters from a bliss object (typically a scan function
    positional counter argument).

    According to issue #251, `arg` can be:
    - a counter
    - a counter namepace
    - a controller, in which case:
       - controller.groups.default namespace is used if it exists
       - controller.counters namepace otherwise
    - a measurementgroup
    """
    if isinstance(arg, measurementgroup.MeasurementGroup):
        if not recursive:
            raise ValueError("Measurement groups cannot point to other groups")
        return _get_counters_from_measurement_group(arg)
    counters = []
    try:
        counters = list(arg.counter_groups.default)
    except AttributeError:
        try:
            counters = list(arg.counters)
        except AttributeError:
            pass
    if counters:
        # replace counters with their aliased counterpart, if any
        for i, cnt in enumerate(counters):
            alias = global_map.aliases.get_alias(cnt)
            if alias:
                counters[i] = global_map.aliases.get(alias)
        return counters
    else:
        try:
            return list(arg)
        except TypeError:
            return [arg]


def get_all_counters(counter_args):
    # Use active MG if no counter is provided
    if not counter_args:
        active = measurementgroup.get_active()
        if active is None:
            raise ValueError("No measurement group is currently active")
        counter_args = [active]

    # Initialize
    all_counters, missing = [], []

    # Process all counter arguments
    for obj in counter_args:
        try:
            all_counters += _get_counters_from_object(obj)
        except AttributeError as exc:
            missing += exc.args

    # Missing counters
    if missing:
        raise ValueError(
            "Missing counters, not in setup_globals: {}.\n"
            "Hint: disable inactive counters.".format(", ".join(missing))
        )

    for cnt in all_counters:
        if not isinstance(cnt, BaseCounter):
            raise TypeError(f"{cnt} is not a BaseCounter object")

    return all_counters


def sort_counter_by_dependency_level(counters):
    def cmp_sort(cnt1, cnt2):
        if cnt1 in cnt2.controller.counters:
            return -1
        elif cnt2 in cnt1.controller.counters:
            return 1
        else:
            return len(cnt1.controller.counters) - len(cnt2.controller.counters)

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
                for cnt in node.controller.counters[1:]:
                    node._calc_dep_nodes[cnt.controller] = self._cached_nodes[
                        cnt.controller
                    ]

        else:
            node = self._cached_nodes.get(controller)

        return node

    def _introspect(self):
        """ Build the chain nodes from the counter list """

        for cnt in self._counter_list:

            if cnt.controller is None:
                raise AttributeError(f"counter: {cnt} must have a controller")

            master_ctrl = cnt.controller.master_controller
            master_node = None

            if master_ctrl is not None:
                master_node = self._create_node(master_ctrl)

            node = self._create_node(cnt.controller)
            node.add_counter(cnt)

            if master_node is not None:
                master_node.add_child(node)

    @property
    def nodes(self):
        return self._cached_nodes.values()

    # ---------- Nodes filtering tools -------------------------------

    def get_top_level_nodes(self, nodes=None):
        if nodes is None:
            nodes = self.nodes
        return [node for node in nodes if node.is_top_level]

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
            nodes = self.nodes

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


class DefaultChainBuilder(ChainBuilder):
    """ Helper object to build the default acquisition chain from a list of (measurementgroup, controllers, counter_groups, counters) objects """

    def __init__(self, counters):
        super().__init__(counters)

    def _get_node_from_controller(self, controller):
        node = controller.create_chain_node()
        node._default_chain_mode = True
        return node


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
            if isinstance(device, BaseCounter):
                controller = device.controller
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

        builder = DefaultChainBuilder(counter_args)

        # --- create acq obj and populate the chain
        topnodes = builder.get_top_level_nodes()
        for node in topnodes:

            # print(f"====== for {node.controller} {node.controller.counters._asdict().keys()} in topnodes")

            extra_settings = self._settings.get(node.controller)
            if extra_settings:
                acq_params = extra_settings.get("acquisition_settings")
                # print("==== FOUND EXTRA SETTINGS")
                node.set_parameters(scan_params=scan_pars, acq_params=acq_params)

                # --- recursive add master -----------------------------------------------------
                mstr = extra_settings.get("master")
                while mstr:

                    mstr_node = builder._create_node(mstr)
                    mstr_node.set_parameters(scan_params=scan_pars)

                    # -- check if master has params and/or a parent master
                    mstr_settings = self._settings.get(mstr)
                    if mstr_settings:
                        mstr_params = mstr_settings.get("acquisition_settings")
                        mstr_node.set_parameters(acq_params=mstr_params)
                        mstr = mstr_settings.get("master")
                    else:
                        mstr = None

                    chain.add(
                        mstr_node, node
                    )  # => ??? update the toplevel flag of the node ???
                    node = mstr_node

                chain.add(timer, node)

            else:
                node.set_parameters(scan_params=scan_pars)
                chain.add(timer, node)

        # Add presets
        for preset in self._presets.values():
            chain.add_preset(preset)

        # Add top master, if any
        if top_master:
            chain.add(top_master, timer)

        chain.timer = timer

        return chain
