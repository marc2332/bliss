# -*- coding: utf-8 -*-
#
# This file is part of the nexus writer service of the BLISS project.
#
# Code is maintained by the ESRF Data Analysis Unit.
#
# Original author: Wout de Nolf
#
# Copyright (c) 2015-2020 ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Writer configuration to be published in Redis
"""

import logging
from bliss import global_map
from bliss.common.counter import SamplingMode
from bliss.controllers.mca.base import (
    SpectrumMcaCounter,
    StatisticsMcaCounter,
    RoiMcaCounter,
)
from bliss.controllers.mca.mythen import MythenCounter
from bliss.controllers.lima.bpm import LimaBpmCounter
from bliss.controllers.lima.image import ImageCounter
from bliss.controllers.lima.roi import RoiStatCounter
from bliss.common.counter import SamplingCounter
from ..utils import config_utils
from ..utils import scan_utils


logger = logging.getLogger(__name__)


CATEGORIES = ["NEXUSWRITER", "INSTRUMENT"]


def register_metadata_generators(generators):
    """
    Create the metadata generators for the configurable writer

    :param bliss.scanning.scan_meta.ScanMeta generators:
    """
    instrument = generators.instrument
    generators = generators.nexuswriter
    generators.set("instrument", fill_instrument_name)
    generators.set("device_info", fill_device_info)
    generators.set("technique", fill_technique_info)
    generators.set("masterfiles", fill_masterfiles)


def fill_instrument_name(scan):
    """
    :param bliss.scanning.scan.Scan scan:
    """
    logger.debug("fill instrument name")
    instrument = config_utils.institute()
    beamline = config_utils.beamline()
    beamline = config_utils.scan_saving_get("beamline", beamline)
    if beamline:
        if instrument:
            instrument += ": " + beamline
        else:
            instrument = beamline
    return {"instrument": instrument}


def fill_technique_info(scan):
    """
    :param bliss.scanning.scan.Scan scan:
    """
    logger.debug("fill technique info")
    return {"technique": current_technique_definition()}


def fill_masterfiles(scan):
    """
    :param bliss.scanning.scan.Scan scan:
    """
    logger.debug("fill master filenames")
    if scan.scan_info["save"]:
        return {"masterfiles": scan_utils.session_master_filenames()}
    else:
        return {}


def fill_device_info(scan):
    """
    :param bliss.scanning.scan.Scan scan:
    """
    logger.debug("fill device info")
    return {"devices": device_info(scan)}


def _mca_device_info(ctr):
    """
    :param BaseMcaCounter ctr:
    :returns str:
    """
    description = (
        ctr._counter_controller.detector_brand.name
        + "/"
        + ctr._counter_controller.detector_type.name
    )
    return {"type": "mca", "description": description}


def _samplingcounter_device_info(ctr):
    """
    :param SamplingCounter ctr:
    :returns str:
    """
    return {"type": "samplingcounter", "mode": ctr.mode.name}


def device_info(scan):
    """
    Publish information on devices (defines types and groups counters).
    Bliss has the concept of controllers and data nodes, but the intermediate
    device level is missing so we need to create it here.

    :param bliss.scanning.scan.Scan scan:
    :returns dict:
    """
    devices = {}
    for ctr in global_map.get_counters_iter():
        _device_info_add_ctr(devices, ctr)
    return devices


def _device_info_add_ctr(devices, ctr):
    """
    :param dict devices: str -> dict
    :param ctr:
    """
    try:
        fullname = ctr.fullname.replace(".", ":")  # Redis name
    except AttributeError:
        logger.info(
            "{} does not have a fullname (most likely not a channels)".format(repr(ctr))
        )
        return
    alias = global_map.aliases.get_alias(ctr)
    if isinstance(ctr, SpectrumMcaCounter):
        device_info = {"type": "mca"}
        device = {"device_info": device_info, "device_type": "mca"}
        devices[fullname] = device
    elif isinstance(ctr, StatisticsMcaCounter):
        device_info = {"type": "mca"}
        device = {"device_info": device_info, "device_type": "mca"}
        devices[fullname] = device
    elif isinstance(ctr, RoiMcaCounter):
        device_info = {"type": "mca"}
        device = {"device_info": device_info, "device_type": "mca"}
        devices[fullname] = device
    elif isinstance(ctr, LimaBpmCounter):
        device_info = {"type": "lima"}
        device = {"device_info": device_info, "device_type": "lima"}
        devices[fullname] = device
    elif isinstance(ctr, ImageCounter):
        device_info = {"type": "lima"}
        device = {"device_info": device_info, "device_type": "lima"}
        devices[fullname] = device
    elif isinstance(ctr, RoiStatCounter):
        device_info = {"type": "lima"}
        device = {"device_info": device_info, "device_type": "lima"}
        devices[fullname] = device
    elif isinstance(ctr, MythenCounter):
        device_info = {"type": "mythen"}
        device = {"device_info": device_info, "device_type": "mythen"}
        devices[fullname] = device
    elif isinstance(ctr, SamplingCounter):
        device_info = _samplingcounter_device_info(ctr)
        device = {
            "device_info": device_info,
            "device_type": "samplingcounter",
            "data_type": "signal",
        }
        devices[fullname] = device
        if ctr.mode == SamplingMode.SAMPLES:
            device = {"device_info": device_info, "device_type": "samplingcounter"}
            devices[fullname + "_samples"] = device
            if alias:
                devices[fullname + "_samples"]["alias"] = alias + "_samples"
        elif ctr.mode == SamplingMode.STATS:
            for stat in "N", "std", "var", "min", "max", "p2v":
                device = {"device_info": device_info, "device_type": "samplingcounter"}
                devices[fullname + "_" + stat] = device
                if alias:
                    devices[fullname + "_" + stat]["alias"] = alias + "_" + stat
    else:
        logger.info(
            "Counter {} {} published as generic detector".format(
                fullname, ctr.__class__.__qualname__
            )
        )
        devices[fullname] = {}
    if alias:
        devices[fullname]["alias"] = alias


def writer_config():
    """
    Get writer configuration from the static session configuration

    :returns dict:
    """
    return config_utils.static_root_find("nexus_definitions", default={})


def writer_config_get(name, default=None):
    """
    Get attribute from the writer configuration

    :returns str:
    """
    return writer_config().get(name, default)


def technique_info():
    """
    Information on techniques from the static writer configuration

    :returns dict:
    """
    return writer_config_get("technique", {})


def technique_info_get(name, default=None):
    """
    Get attribute from the technique info

    :returns str:
    """
    return technique_info().get(name, default)


def default_technique():
    """
    Default technique from the technique info

    :returns str:
    """
    return technique_info_get("default", "undefined")


def current_technique():
    """
    Active technique from the session's scan saving object

    :returns str:
    """
    return config_utils.scan_saving_get("technique", default_technique())


def techniques():
    """
    List of available techniques from the technique info

    :returns list:
    """
    return list(technique_info_get("techniques", {}).keys())


def technique_definition(technique):
    """
    Technique definition from the technique info

    :param str techique:
    :returns dict: {'name': str,
                    'applications': dict(dict),
                    'plots': dict(list),
                    'plotselect': str}
    """
    applications = {}
    plots = {}
    ret = {
        "name": technique,
        "applications": applications,
        "plots": plots,
        "plotselect": "",
    }
    technique_info = technique_info_get("techniques", {}).get(technique, {})
    if technique_info is None:
        technique_info = {}

    # Get the application definitions selected for this technique
    applicationdict = technique_info_get("applications", {})
    for name in technique_info.get("applications", []):
        definition = applicationdict.get(name, {})
        # for example {'xrf':{'I0': 'iodet',
        #                     'It': 'idet',
        #                     'mca': [...]}, ...}
        if definition:
            name = definition.pop("personal_name", name)
            applications[name] = definition

    # Get the plots selected for this technique
    plotdict = technique_info_get("plots", {})
    plotselect = ""  # this first one is the default
    for name in technique_info.get("plots", []):
        plotdefinition = plotdict.get(name, {})
        # for examples:
        #   {'personal_name': 'counters', 'items': ['iodet', 'xmap1:deadtime_det2', ...]}
        #   {'personal_name': 'counters', 'ndim': 2, 'grid': True}
        items = plotdefinition.get("items", [])
        ndim = plotdefinition.get("ndim", -1)
        grid = plotdefinition.get("grid", False)
        if not items and ndim < 0:
            continue
        name = plotdefinition.get("personal_name", name)
        if name in applications:
            name = name + "_plot"
        if not plotselect:
            plotselect = name
        plots[name] = {"items": items, "grid": grid, "ndim": ndim}
    ret["plotselect"] = plotselect
    return ret


def current_technique_definition():
    """
    Current technique definition from the technique info

    :returns dict(dict): technique:definition (str:dict)
    """
    return technique_definition(current_technique())
