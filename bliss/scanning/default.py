# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import warnings
import operator

from bliss import setup_globals
from bliss.scanning.chain import AcquisitionChain
from bliss.scanning.acquisition.timer import SoftwareTimerMaster
from bliss.common import measurementgroup
from bliss.common.measurement import BaseCounter
from bliss.common.utils import OrderedDict as ordereddict

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
            raise ValueError(
                'Measurement groups cannot point to other groups')
        return _get_counters_from_measurement_group(arg)
    try:
        return arg.counter_groups.default
    except AttributeError:
        pass
    try:
        return arg.counters
    except AttributeError:
        pass
    try:
        return list(arg)
    except TypeError:
        return [arg]


def get_all_counters(counter_args):
    # Use active MG if no counter is provided
    if not counter_args:
        active = measurementgroup.get_active()
        if active is None:
            raise ValueError(
                'No measurement group is currently active')
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
            "Hint: disable inactive counters."
            .format(', '.join(missing)))

    return all_counters


def master_to_devices_mapping(root, counters, scan_pars,
                              acquisition_settings, master_settings):
    """Create the mapping between acquisition masters and acquisition devices

    It relies on four standard methods:
    - counter.master_controller.create_master_device
    - counter.create_acquisition_device
    - acquisition_master.add_counter
    - acquisition_device.add_counter
    """
    # Initialize structures
    device_dict = {None: None}
    master_dict = {None: root}
    mapping_dict = ordereddict({root: []})

    # Recursive master handling
    def add_master(master_controller):
        # Existing master
        if master_controller in master_dict:
            return master_dict[master_controller]
        # Create master
        settings = acquisition_settings.get(master_controller, {})
        master_dict[master_controller] = acquisition_master = \
            master_controller.create_master_device(
                scan_pars, **settings)
        # Parent handling
        parent_controller = master_settings.get(master_controller)
        parent = add_master(parent_controller)
        # Fill mapping dict
        mapping_dict[acquisition_master] = []
        mapping_dict[parent].append(acquisition_master)
        # Return master
        return acquisition_master

    # Non-recursive device handling
    def add_device(device_controller, master_controller):
        # Existing device
        if device_controller in device_dict:
            return device_dict[device_controller]
        # Create acquisition_device
        settings = acquisition_settings.get(device_controller, {})
        device_dict[device_controller] = acquisition_device = \
            counter.create_acquisition_device(
                scan_pars, **settings)
        # Parent handling
        if master_controller is None:
            master_controller = master_settings.get(device_controller)
        acquisition_master = add_master(master_controller)
        # Fill mapping dict
        mapping_dict[acquisition_master].append(acquisition_device)
        # Return device
        return acquisition_device

    # Loop over counters
    for counter in counters:

        # Master settings shortcuts
        if counter in master_settings and counter.controller:
            if counter.controller in master_settings:
                raise ValueError('Conflict in master settings')
            master_settings[counter.controller] = master_settings[counter]

        # Acquisition settings shortcuts
        if counter in acquisition_settings and counter.controller:
            if counter.controller in acquisition_settings:
                raise ValueError('Conflict in acquisition settings')
            acquisition_settings[counter.controller] = \
                acquisition_settings[counter]

        # Get acquisition master
        master_controller = counter.master_controller
        acquisition_master = add_master(master_controller)

        # Get acquisition device
        device_controller = counter.controller
        acquisition_device = add_device(device_controller, master_controller)

        # Add counter
        if device_controller:
            acquisition_device.add_counter(counter)
        elif master_controller:
            acquisition_master.add_counter(counter)

        # Special case: counters without controllers
        else:
            warnings.warn(
                'Counter {!r} has no associated controller'.format(counter))
            add_device(counter, None)

    return mapping_dict

class DefaultAcquisitionChain(object):
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
            default_settings[device_settings['device']] = {"acquisition_settings": acq_settings, "master": master }
        self._settings = default_settings
        
    def add_preset(self, preset):
        self._presets[id(preset)]=preset

    def get(self, scan_pars, counter_args, top_master=None, chain=None):
        # Scan parameters
        count_time = scan_pars.get('count_time', 1)
        sleep_time = scan_pars.get('sleep_time')
        npoints = scan_pars.get('npoints', 1)

        settings = self._settings
        acquisition_settings = {
            controller: settings['acquisition_settings']
            for controller, settings in settings.items()
            if 'acquisition_settings' in settings}
        master_settings = {
            controller: settings['master']
            for controller, settings in settings.items()
            if 'master' in settings}

        # Issue warning for non BaseCounter instance (for the moment)
        def get_name(counter):
            if not isinstance(counter, BaseCounter):
                warnings.warn('{!r} is not a counter'.format(counter))
                return counter.name
            return counter.fullname

        # Remove duplicates
        counter_dct = {
            get_name(counter): counter
            for counter in get_all_counters(counter_args)}

        # Sort counters
        counters = [
            counter for name, counter in
            sorted(counter_dct.items())]

        # No counters
        if not counters:
            raise ValueError(
                "No counters for scan. Hint: are all counters disabled ?")

        # Build default master
        timer = SoftwareTimerMaster(
            count_time,
            npoints=npoints,
            sleep_time=sleep_time)

        # Build counter tree
        mapping = master_to_devices_mapping(
            timer, counters, scan_pars, acquisition_settings, master_settings)

        if chain is None:
            chain = AcquisitionChain(parallel_prepare=True)

        # Build chain
        for acq_master, acq_devices in mapping.iteritems():
            for acq_device in acq_devices:
                chain.add(acq_master, acq_device)

        # Add presets
        for preset in self._presets.itervalues():
            chain.add_preset(preset)

        # Add top master, if any
        if top_master:
            chain.add(top_master, timer)

        chain.timer = timer

        # Return chain
        return chain
