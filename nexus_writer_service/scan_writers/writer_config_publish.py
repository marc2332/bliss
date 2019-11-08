# -*- coding: utf-8 -*-
#
# This file is part of the nexus writer service of the BLISS project.
#
# Code is maintained by the ESRF Data Analysis Unit.
#
# Original author: Wout de Nolf
#
# Copyright (c) 2015-2019 ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Writer configuration to be published in Redis
"""

import inspect
import logging
from bliss import global_map
from bliss.common.counter import SamplingMode
from ..utils import config_utils
from ..utils import scan_utils


logger = logging.getLogger(__name__)


CATEGORIES = ["EXTERNAL", "INSTRUMENT"]


def register_metadata_generators(generators):
    """
    Create the metadata generators for the configurable writer

    :param bliss.scanning.scan_meta.ScanMeta generators:
    """
    instrument = generators.instrument
    instrument.set("positioners", fill_positioners)  # start of scan
    external = generators.external
    external.set("instrument", fill_instrument_name)
    external.set("positioners", fill_positioners)  # end of scan
    external.set("device_info", fill_device_info)
    external.set("technique", fill_technique_info)
    external.set("filenames", fill_filenames)


def fill_positioners(scan):
    """
    :param bliss.scanning.scan.Scan scan:
    """
    logger.debug("fill motor positions")
    data = {}
    data["positioners"] = positions = {}
    data["positioners_dial"] = dials = {}
    data["positioners_units"] = units = {}
    for name, pos, dial, unit in global_map.get_axes_positions_iter(on_error="ERR"):
        positions[name] = pos
        dials[name] = dial
        units[name] = unit
    return data


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


def fill_filenames(scan):
    """
    :param bliss.scanning.scan.Scan scan:
    """
    logger.debug("fill filename info")
    return {"filenames": scan_utils.filenames()}


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
    description = ctr.controller.detector_brand.name + "/" + \
                  ctr.controller.detector_type.name
    return {"type": "mca",
            "description": description}


def _mca_roi_data_info(ctr):
    """
    :param RoiMcaCounter ctr:
    :returns dict:
    """
    roi = ctr.controller.rois.get(ctr.roi_name)
    return {"roi_start": roi[0],
            "roi_end": roi[1]}


def _lima_roi_data_info(ctr):
    """
    :param RoiStatCounter ctr:
    :returns dict:
    """
    roi = ctr.controller.get(ctr.roi_name)
    return {"roi_" + k: v for k, v in roi.to_dict().items()}


def device_info(scan):
    """
    Publish information on devices (defines types and groups counters).
    Bliss has the concept of controllers and data nodes, but the intermediate
    device level is missing so we need to create it here.

    :param bliss.scanning.scan.Scan scan:
    :returns dict:
    """
    devices = {}
    # This is not all of them
    for ctr in global_map.get_counters_iter():
        fullname = ctr.fullname.replace(".", ":")  # Redis name
        # Derived from: bliss.common.counter.BaseCounter
        #   bliss.common.counter.Counter
        #       bliss.common.counter.SamplingCounter
        #           bliss.common.temperature.TempControllerCounter
        #           bliss.controllers.simulation_diode.SimulationDiodeSamplingCounter
        #   bliss.scanning.acquisition.mca.BaseMcaCounter
        #       bliss.scanning.acquisition.mca.SpectrumMcaCounter
        #       bliss.scanning.acquisition.mca.StatisticsMcaCounter
        ctr_classes = [c.__name__ for c in inspect.getmro(ctr.__class__)]
        # print(ctr.fullname, type(ctr), type(ctr.controller), ctr_classes)
        # controller_classes = [c.__name__ for c in inspect.getmro(ctr.controller.__class__)]
        if "SpectrumMcaCounter" in ctr_classes:
            device_info = _mca_device_info(ctr)
            device = {"device_info": device_info, "device_type": "mca"}
            devices[fullname] = device
        elif "StatisticsMcaCounter" in ctr_classes:
            device_info = _mca_device_info(ctr)
            device = {"device_info": device_info, "device_type": "mca"}
            devices[fullname] = device
        elif "RoiMcaCounter" in ctr_classes:
            device_info = _mca_device_info(ctr)
            data_info = _mca_roi_data_info(ctr)
            device = {
                "device_info": device_info,
                "data_info": data_info,
                "device_type": "mca",
            }
            devices[fullname] = device
        elif "LimaBpmCounter" in ctr_classes:
            device_info = {"type": "lima"}
            device = {"device_info": device_info, "device_type": "lima"}
            devices[fullname] = device
        elif "LimaImageCounter" in ctr_classes:
            device_info = {"type": "lima"}
            device = {"device_info": device_info, "device_type": "lima"}
            devices[fullname] = device
        elif "RoiStatCounter" in ctr_classes:
            device_info = {"type": "lima"}
            data_info = _lima_roi_data_info(ctr)
            device = {
                "device_info": device_info,
                "device_type": "lima",
                "data_info": data_info,
            }
            devices[fullname] = device
        elif "TempControllerCounter" in ctr_classes:
            device_info = {"type": "temperature", "description": "temperature"}
            device = {"device_info": device_info, "device_type": "temperature"}
            devices[fullname] = device
        elif "SamplingCounter" in ctr_classes:
            device_info = {
                "type": "samplingcounter",
                "mode": str(ctr.mode).split(".")[-1],
            }
            device = {
                "device_info": device_info,
                "device_type": "samplingcounter",
                "data_type": "signal",
            }
            devices[fullname] = device
            if ctr.mode == SamplingMode.SAMPLES:
                device = {"device_info": device_info, "device_type": "samplingcounter"}
                devices[fullname + "_samples"] = device
            elif ctr.mode == SamplingMode.STATS:
                for stat in "N", "std", "var", "min", "max", "p2v":
                    device = {
                        "device_info": device_info,
                        "device_type": "samplingcounter",
                    }
                    devices[fullname + "_" + stat] = device
        else:
            logger.info(
                "Counter {} {} published as generic detector".format(
                    fullname, ctr_classes
                )
            )
            devices[fullname] = {}
    return devices


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
