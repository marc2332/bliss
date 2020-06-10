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
Compile device information before and after Redis publication
"""

from collections import OrderedDict

mcanamemap = {
    "spectrum": "data",
    "icr": "input_rate",
    "ocr": "output_rate",
    "triggers": "input_counts",
    "events": "output_counts",
    "deadtime": "dead_time",
    "trigger_livetime": "input_live_time",
    "energy_livetime": "output_live_time",
    "realtime": "elapsed_time",
}

mcatypemap = {
    "spectrum": "principal",
    "icr": "icr",
    "ocr": "ocr",
    "triggers": "triggers",
    "events": "events",
    "deadtime": "deadtime",
    "trigger_livetime": "trigger_livetime",
    "energy_livetime": "livetime",
    "realtime": "realtime",
}

mcaunitmap = {
    "rate": "hertz",
    "livetime": "s",
    "trigger_livetime": "s",
    "realtime": "s",
}

limanamemap = {"image": "data", "sum": "data"}

limatypemap = {"image": "principal", "sum": "principal"}

mythennamemap = {"spectrum": "data"}

mythentypemap = {"spectrum": "principal"}

counternamemap = {}

countertypemap = {}


def shortnamemap(names, separator=":"):
    """
    Map full Redis names to short (but still unique) names

    :param list(str) names:
    :param str separator:
    :returns dict:
    """
    if not names:
        return {}
    names = set(names)
    parts = [name.split(separator) for name in names]
    nparts = max(map(len, parts))
    parts = [([""] * (nparts - len(lst))) + lst for lst in parts]
    ret = {}
    for i in reversed(range(-nparts, 0)):
        joinednames = [separator.join(s for s in lst[i:] if s) for lst in parts]
        newnames = joinednames + list(ret.values())
        selection = [
            (idx, (separator.join(s for s in lst if s), name))
            for idx, (name, lst) in enumerate(zip(joinednames, parts))
            if newnames.count(name) == 1
        ]
        if selection:
            idx, tuples = list(zip(*selection))
            ret.update(tuples)
            parts = [lst for j, lst in enumerate(parts) if j not in idx]
    return ret


def fill_device(fullname, device, device_info=None, data_info=None):
    """
    Add missing keys with default values

        device_type: type for the writer (not saved), e.g. positioner, mca, lima
        device_name: HDF5 group name (measurement or positioners when missing)
        device_info: HDF5 group datasets
        data_type: maximal one device dataset has type "principal"
                   a principal's data_name is either "data" (detector) or "value" (positioner)
        data_name: HDF5 dataset name
        data_info: HDF5 dataset attributes
        unique_name: Unique name for HDF5 links
        master_index: >=0 axis order used for plotting
        single: only data of this device
                a single's data_name is either "data" (detector) or "value" (positioner)
        dependencies: fullnames

    :param str fulname:
    :param dict device:
    :param dict device_info:
    :param dict data_info:
    """
    if device_info is None:
        device_info = {}
    if data_info is None:
        data_info = {}
    device["device_type"] = device.get("device_type", "")
    device["device_name"] = device.get("device_name", fullname)
    device["device_info"] = device.get("device_info", device_info)
    device["data_type"] = device.get("data_type", "principal")
    device["data_name"] = device.get("data_name", "data")
    device["data_info"] = device.get("data_info", data_info)
    device["unique_name"] = device.get("unique_name", fullname)
    device["master_index"] = -1
    device["single"] = None
    device["dependencies"] = {}
    device["metadata_keys"] = {}


def update_device(devices, fullname, device_info=None, data_info=None):
    """
    Add missing device and/or keys

    :param dict devices:
    :param str fullname:
    :param dict device_info:
    :param dict data_info:
    """
    devices[fullname] = device = devices.get(fullname, {})
    fill_device(fullname, device, device_info=device_info, data_info=data_info)
    return device


def parse_devices(devices, short_names=True, multivalue_positioners=False):
    """
    Determine names and types based on device name and type

    :param dict devices:
    :param bool short_names:
    :param bool multivalue_positioners:
    """
    namemap = shortnamemap(list(devices.keys()))
    for fullname, device in devices.items():
        device["device_name"] = namemap.get(fullname, fullname)
        if device["device_type"] == "mca":
            # 'xmap1:xxxxxx_det1'
            # 'xmap1:roi1'
            #   xxxxxx: spectrum, icr, ocr, triggers, events,
            #           deadtime, trigger_livetime, energy_livetime,
            #           realtime, roi1, roi2, ...
            #   device_name = 'xmap1:det1'
            #   data_type = mcatypemap('xxxxxx')
            #   data_name = mcanamemap('xxxxxx')
            parts = fullname.split(":")
            lastparts = parts[-1].split("_")
            if len(lastparts) == 1:
                mcachannel = "sum"
                datatype = lastparts[-1]
            else:
                mcachannel = lastparts[-1]
                datatype = "_".join(lastparts[:-1])  # xxxxxx
            parts = parts[:-1] + [mcachannel]
            device["device_name"] = ":".join(parts)
            device["data_name"] = mcanamemap.get(datatype, datatype)
            if datatype.startswith("roi"):
                datatype = "roi"
            device["data_type"] = mcatypemap.get(datatype, datatype)
            device["data_info"]["units"] = mcaunitmap.get(datatype, None)
        elif device["device_type"] == "mythen":
            # 'mythen1:spectrum'
            parts = fullname.split(":")
            device_name = parts[0]
            datatype = ":".join(parts[1:])
            device["device_name"] = device_name
            device["data_type"] = mythentypemap.get(datatype, datatype)
            device["data_name"] = mythennamemap.get(datatype, datatype)
        elif device["device_type"] == "lima":
            # 'frelon1:image'
            # 'frelon1:roi_counters:roi1_min'
            # 'frelon1:bpm:fwhm_x'
            parts = fullname.split(":")
            if len(parts) == 3:
                device["dependencies"] = {parts[0] + ":image": "image"}
                if parts[1] == "roi_counters":
                    subparts = parts[-1].split("_")
                    device_name = ":".join([parts[0], subparts[0]])
                    datatype = ":".join(subparts[1:])
                    device["metadata_keys"] = {subparts[0]: "selection"}
                else:
                    device_name = ":".join(parts[:2])
                    datatype = ":".join(parts[2:])
            else:
                device_name = parts[0]
                datatype = ":".join(parts[1:])
            device["device_name"] = device_name
            device["data_type"] = limatypemap.get(datatype, datatype)
            device["data_name"] = limanamemap.get(datatype, datatype)
        elif device["device_type"] == "samplingcounter":
            if device["data_type"] == "signal":
                device["data_name"] = "data"
                device["data_type"] = "principal"
            else:
                # 'simdiodeSAMPLES_xxxxx'
                #   device_name = 'simdiodeSAMPLES'
                #   data_type = countertypemap('xxxxxx')
                #   data_name = counternamemap('xxxxxx')
                parts = device["device_name"].split("_")
                datatype = parts[-1]  # xxxxxx
                parts = ["_".join(parts[:-1])]
                device["device_name"] = "_".join(parts)
                device["data_type"] = countertypemap.get(datatype, datatype)
                device["data_name"] = counternamemap.get(datatype, datatype)
        elif device["device_type"] == "positionergroup":
            parts = fullname.split(":")
            if device["data_type"] != "principal":
                device["data_type"] = parts[-1]
            if multivalue_positioners:
                device["device_name"] = ":".join(parts[:-1])
                if device["data_type"] == "principal":
                    device["data_name"] = "value"
                else:
                    device["data_name"] = device["data_type"]
            else:
                device["data_name"] = "value"
                device["single"] = True
        elif device["device_type"] == "positioner":
            device["data_name"] = "value"
            device["data_type"] = "principal"
        else:
            device["data_name"] = "data"
            device["data_type"] = "principal"
        if device["single"] is None:
            device["single"] = device["data_type"] == "principal"
        if device["single"]:
            device["unique_name"] = device["device_name"]
        else:
            device["unique_name"] = device["device_name"] + ":" + device["data_name"]


def device_info(
    devices, scan_info, ndim=1, short_names=True, multivalue_positioners=False
):
    """
    Merge device information from `writer_config_publish.device_info`
    and from the scan info published by the Bliss core library.

    :param dict devices: as provided by `writer_config_publish.device_info`
    :param dict scan_info:
    :param int ndim: number of scan dimensions
    :param bool short_names:
    :param bool multivalue_positioners:
    :returns dict: subscanname:dict(fullname:dict)
                   ordered according to position in
                   acquisition chain
    """
    ret = OrderedDict()
    config = bool(devices)
    for subscan, subscaninfo in scan_info["acquisition_chain"].items():
        subdevices = ret[subscan] = {}
        masterinfo = subscaninfo["master"]
        _extract_device_info(
            devices,
            subdevices,
            masterinfo,
            ["scalars"],
            ndim=ndim,
            config=config,
            master=True,
        )
        _extract_device_info(
            devices,
            subdevices,
            masterinfo,
            ["spectra", "images"],
            ndim=ndim,
            config=config,
            master=True,
        )
        _extract_device_info(
            devices,
            subdevices,
            subscaninfo,
            ["scalars", "spectra", "images"],
            ndim=ndim,
            config=config,
            master=False,
        )
        parse_devices(
            subdevices,
            short_names=short_names,
            multivalue_positioners=multivalue_positioners,
        )
    return ret


def _extract_device_info(
    devices, subdevices, info, keys, ndim=1, config=True, master=False
):
    for key in keys:
        units = info.get(key + "_units", {})
        lst = info.get(key, [])
        for i, fullname in enumerate(lst):
            subdevices[fullname] = devices.get(fullname, {})
            data_info = {"units": units.get(fullname, None)}
            device = update_device(subdevices, fullname, data_info=data_info)
            if key == "scalars":
                if master:
                    if len(lst) > 1 and ndim <= 1:
                        device["device_type"] = "positionergroup"
                        device["master_index"] = 0
                    else:
                        device["device_type"] = "positioner"
                        device["master_index"] = i
                    if i == 0:
                        device["data_type"] = "principal"
                    else:
                        device["data_type"] = ""
