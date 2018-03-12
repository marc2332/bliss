# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2018 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""This module defines the tools and standards for integrating specific
counters into the default chain.

Counters have two ways to define a specific behavior:

- `create_acquisition_master` method: called (if it exists) with the scan
    parameters as arguments. It has to return an acquisition master.

- `default_chain_plugin` static method: gathered for all counters
    (if it exists) at default chain creation. Each distinct plugin
    function is then called exactly once. It takes the current tree,
    the counters set and the scan parameters as arguments. It returns
    a possibly altered set of counters.

Example::

    def my_default_chain_plugin(tree, counters, scan_pars):
        # Do something
        return counters

    class MyCounter(object):

        default_chain_plugin = staticmethod(my_default_chain_plugin)

        def create_acquisition_master(self, scan_pars):
            # Do something
            return acquisition_master
"""

from bliss.controllers.lima import Lima
from bliss.scanning.acquisition.lima import LimaAcquisitionMaster
from bliss.scanning.acquisition.ct2 import CT2AcquisitionMaster


__all__ = ['default_master_configuration', 'default_chain_plugins']


def default_master_configuration(counter, scan_pars):
    """Create and configure an acquisition device which could also be a master
    for other devices.

    Returns the acqisition device and counters parameters as a dictionary.
    """
    try:
        device = counter.acquisition_controller
    except AttributeError:
        device = counter

    npoints = scan_pars.get('npoints', 1)
    acq_expo_time = scan_pars['count_time']
    if isinstance(device, Lima):
        multi_mode = 'INTERNAL_TRIGGER_MULTI' in device.available_triggers
        save_flag = scan_pars.get('save', False)
        acq_nb_frames = npoints if multi_mode else 1
        acq_trigger_mode = scan_pars.get('acq_trigger_mode',
                                         'INTERNAL_TRIGGER_MULTI'
                                         if multi_mode else 'INTERNAL_TRIGGER')
        acq_device = LimaAcquisitionMaster(device,
                                           acq_nb_frames=acq_nb_frames,
                                           acq_expo_time=acq_expo_time,
                                           acq_trigger_mode=acq_trigger_mode,
                                           save_flag=save_flag,
                                           prepare_once=multi_mode)
        return acq_device, {"prepare_once": multi_mode, "start_once": multi_mode}
    elif type(device).__name__ == 'CT2':
        acq_device = CT2AcquisitionMaster(device, npoints=npoints,
                                          acq_expo_time=acq_expo_time)
        return acq_device, {"prepare_once": acq_device.prepare_once,
                            "start_once": acq_device.start_once}
    else:
        try:
            master_create_func = counter.create_acquisition_master
        except KeyError:
            raise TypeError(
                "{!r} is not a supported acquisition controller for counter {!r}"
                .format(device, counter.name))
        else:
            master_device = master_create_func(scan_pars)
            return master_device, {"prepare_once": master_device.prepare_once,
                                   "start_once": master_device.start_once}


def default_chain_plugins(tree, counters, scan_pars,
                          default_plugin=None):
    """Fill the counter tree and return the counter which are not managed.

    The tree argument is a dictionary with default acquisition masters as keys
    and lists of acquisition devices as values.

    The default acquisition master may be None.
    """
    # Get the plugins
    plugins = {getattr(counter, 'default_chain_plugin', default_plugin)
               for counter in counters}
    plugins = list(filter(None, plugins))
    # Call the plugins
    for plugin in plugins:
        counters = plugin(tree, counters, scan_pars)
    return counters
