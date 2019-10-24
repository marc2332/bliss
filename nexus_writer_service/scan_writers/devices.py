# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Compile device information before and after Redis publication
"""

mcanamemap = {'spectrum': 'data',
              'icr': 'input_rate',
              'ocr': 'output_rate',
              'triggers': 'input_counts',
              'events': 'output_counts',
              'deadtime': 'dead_time',
              'livetime': 'live_time',
              'realtime': 'elapsed_time'}

mcatypemap = {'spectrum': 'principal',
              'icr': 'icr',
              'ocr': 'ocr',
              'triggers': 'triggers',
              'events': 'events',
              'deadtime': 'deadtime',
              'livetime': 'livetime',
              'realtime': 'realtime'}

mcaunitmap = {'icr': 'hertz',
              'ocr': 'hertz',
              'livetime': 's',
              'realtime': 's'}

timernamemap = {'elapsed_time': 'value',
                'epoch': 'epoch'}

timertypemap = {'elapsed_time': 'principal',
                'epoch': 'epoch'}

limanamemap = {'image': 'data'}

limatypemap = {'image': 'principal'}

counternamemap = {}

countertypemap = {}


def shortnamemap(names, separator=':'):
    """
    Map full Redis names to short (but still unique) names

    :param lst(str) names:
    :param str separator:
    :returns dict:
    """
    parts = [name.split(separator) for name in names]
    nparts = max(map(len, parts))
    parts = [([''] * (nparts - len(lst))) + lst for lst in parts]
    ret = {}
    for i in reversed(range(-nparts, 0)):
        joinednames = [separator.join(s for s in lst[i:] if s)
                       for lst in parts]
        newnames = joinednames + list(ret.values())
        selection = [(idx, (separator.join(s for s in lst if s), name))
                     for idx, (name, lst) in enumerate(zip(joinednames, parts))
                     if newnames.count(name) == 1]
        if selection:
            idx, tuples = list(zip(*selection))
            ret.update(tuples)
            parts = [lst for j, lst in enumerate(parts) if j not in idx]
    return ret


def fill_device(fullname, device):
    """
    Add missing keys with default values

    :param str fulname:
    :param dict device:
    """
    device['device_type'] = device.get('device_type', '')  # type for the writer (not saved)
                                                           # e.g. positioner, mca
    device['device_name'] = device.get('device_name', fullname)  # HDF5 group name
                                                                 # measurement or positioners when missing
    device['device_info'] = device.get('device_info', {})  # HDF5 group datasets
    device['data_type'] = device.get('data_type', 'principal')  # principal value of this HDF5 group
    device['data_name'] = device.get('data_name', 'data')  # HDF5 dataset name
    device['data_info'] = device.get('data_info', {})  # HDF5 dataset attributes
    device['unique_name'] = device.get('unique_name', fullname)  # Unique name for HDF5 links
    device['master_index'] = -1  # 0> axis order used for plotting


def update_device(devices, fullname, units=None):
    """
    Add missing device and/or keys

    :param dict devices:
    :param str fullname:
    :param dict units:
    """
    devices[fullname] = device = devices.get(fullname, {})
    fill_device(fullname, device)
    if units:
        unit = units.get(fullname, None)
        if unit:
            device['data_info']['units'] = unit
    return device


def parse_devices(devices, multivalue_positioners=False):
    """
    Determine names and types based on device name and type

    :param dict devices:
    :param bool multivalue_positioners:
    """
    namemap = shortnamemap(list(devices.keys()))
    for fullname, device in devices.items():
        device['device_name'] = namemap[fullname]
        if device['device_type'] == 'mca':
            # 'xmap1:xxxxxx_det1'
            #   device_name = 'xmap1:det1'
            #   data_type = mcatypemap('xxxxxx')
            #   data_name = mcanamemap('xxxxxx')
            parts = fullname.split(':')
            lastparts = parts[-1].split('_')
            mcachannel = '_'.join(lastparts[1:])
            if not mcachannel:
                mcachannel = 'sum'
            parts = parts[:-1] + [mcachannel]
            datatype = lastparts[0]  # xxxxxx
            device['device_name'] = ':'.join(parts)
            device['data_type'] = mcatypemap.get(datatype, datatype)
            device['data_name'] = mcanamemap.get(datatype, datatype)
            device['data_info']['units'] = mcaunitmap.get(datatype, None)
        elif device['device_type'] == 'lima':
            # 'frelon1:image'
            # 'frelon1:roi_counters:roi1_min'
            # 'frelon1:xxxx:fwhm_x'
            parts = fullname.split(':')
            datatype = parts[1]  # image, roi_counters or xxxx
            if parts[1] == 'roi_counters':
                datatypedefault = ':'.join(parts[2:])
            else:
                datatypedefault = ':'.join(parts[1:])
            device['device_name'] = parts[0]
            device['data_type'] = limatypemap.get(datatype, datatypedefault)
            device['data_name'] = limanamemap.get(datatype, datatypedefault)
        elif device['device_type'] == 'samplingcounter':
            if device['data_type'] == 'signal':
                device['data_name'] = 'data'
                device['data_type'] = 'principal'
            else:
                # 'simdiodeSAMPLES_xxxxx'
                #   device_name = 'simdiodeSAMPLES'
                #   data_type = countertypemap('xxxxxx')
                #   data_name = counternamemap('xxxxxx')
                parts = device['device_name'].split('_')
                datatype = parts[-1]  # xxxxxx
                parts = ['_'.join(parts[:-1])]
                device['device_name'] = '_'.join(parts)
                device['data_type'] = countertypemap.get(datatype, datatype)
                device['data_name'] = counternamemap.get(datatype, datatype)
        elif device['device_type'] == 'positionergroup':
            # 'timer1:xxxxxx' -> 'xxxxxx'
            #   device_name = 'timer1'
            #   data_type = timertypemap('xxxxxx')
            #   data_name = timernamemap('xxxxxx')
            parts = fullname.split(':')
            timertype = parts[-1]
            device['device_type'] = 'positioner'
            if multivalue_positioners:
                # All of them are masters but only one of them
                # is a principle value
                device['device_name'] = ':'.join(parts[:-1])
                device['data_type'] = timertypemap.get(timertype,
                                                       device['data_type'])
                device['data_name'] = timernamemap.get(timertype,
                                                       device['data_name'])
                # What to do here?
                #if device['data_type'] != 'principal':
                #    device['master_index'] = -1
            else:
                # All of them are principal values but only one of them
                # is a master
                device['data_type'] = timertypemap.get(timertype,
                                                       device['data_type'])
                if device['data_type'] != 'principal':
                    device['master_index'] = -1
                device['data_type'] = 'principal'
                device['data_name'] = 'value'
        elif device['device_type'] == 'positioner':
            device['data_name'] = 'value'
            device['data_type'] = 'principal'
        else:
            device['data_name'] = 'data'
            device['data_type'] = 'principal'
        if device['data_type'] == 'principal':
            device['unique_name'] = device['device_name']
        else:
            device['unique_name'] = device['device_name'] + ':' +\
                                    device['data_name']


def device_info(devices, scan_info, multivalue_positioners=False):
    """
    Merge device information from `scan_info_generators.device_info`
    and from scan info publish by the Bliss core library.

    :param dict devices: as provided by `scan_info_generators.device_info`
    :param dict scan_info:
    :param bool multivalue_positioners:
    :returns dict: subscanname:dict(fullname:dict)
    """
    ret = {}
    for subscan, subscaninfo in scan_info['acquisition_chain'].items():
        subdevices = ret[subscan] = {}
        # These are the "positioners"
        dic = subscaninfo['master']
        units = dic['scalars_units']
        master_index = 0
        for fullname in dic['scalars']:
            subdevices[fullname] = devices.get(fullname, {})
            device = update_device(subdevices, fullname, units)
            if fullname.startswith('timer'):
                device['device_type'] = 'positionergroup'
            else:
                device['device_type'] = 'positioner'
            device['master_index'] = master_index
            master_index += 1
        # These are the 0D, 1D and 2D "detectors"
        dic = subscaninfo
        for key in 'scalars', 'spectra', 'images':
            units = dic.get(key + '_units', {})
            for fullname in dic[key]:
                subdevices[fullname] = devices.get(fullname, {})
                device = update_device(subdevices, fullname, units)
                if fullname.startswith('timer') and key == 'scalars':
                    device['device_type'] = 'positionergroup'
        parse_devices(subdevices, multivalue_positioners=multivalue_positioners)
    return ret
