# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Writer configuration to be published in Redis
"""

import inspect
import logging
from bliss import global_map
from bliss.common.measurement import SamplingMode
from ..utils import config_utils
from . import scan_utils
logger = logging.getLogger(__name__)


CATEGORIES = ['EXTERNAL', 'INSTRUMENT']


def register_generators(generators):
    """
    Create the scan info generators for the configurable writer

    :param bliss.scanning.scan_meta.ScanMeta generators:
    """
    instrument = generators.instrument
    instrument.set('positioners', fill_positioners)  # start of scan
    external = generators.external
    external.set('instrument', fill_instrument_name)
    external.set('positioners', fill_positioners)  # end of scan
    external.set('device_info', fill_device_info)
    external.set('technique', fill_technique_info)
    external.set('filenames', fill_filenames)


def fill_positioners(scan):
    """
    :param bliss.scanning.scan.Scan scan:
    """
    logger.debug('fill motor positions')
    data = {}
    data['positioners'] = positions = {}
    data['positioners_dial'] = dials = {}
    data['positioners_units'] = units = {}
    for name, pos, dial, unit in global_map.get_axes_positions_iter(on_error='ERR'):
        positions[name] = pos
        dials[name] = dial
        units[name] = unit
    return data


def fill_instrument_name(scan):
    """
    :param bliss.scanning.scan.Scan scan:
    """
    logger.debug('fill instrument name')
    root = config_utils.static_config_root()
    name = root.get('synchrotron', '')
    beamline = root.get('beamline', '')
    beamline = config_utils.scan_saving_get('beamline', beamline)
    if beamline:
        if name:
            name += ': ' + beamline
        else:
            name = beamline
    return {'instrument': name}


def fill_technique_info(scan):
    """
    :param bliss.scanning.scan.Scan scan:
    """
    logger.debug('fill technique info')
    return {'technique': current_technique_definition()}


def fill_filenames(scan):
    """
    :param bliss.scanning.scan.Scan scan:
    """
    logger.debug('fill filename info')
    filenames = [name for name in config_utils.filenames() if name]
    return {'filenames': filenames}


def fill_device_info(scan):
    """
    :param bliss.scanning.scan.Scan scan:
    """
    logger.debug('fill device info')
    return {'devices': device_info(scan)}


def device_info(scan):
    """
    Publish information on devices (defines types and groups counters).

    :param bliss.scanning.scan.Scan scan:
    :returns dict:
    """
    devices = {}
    # This is not all of them
    for ctr in global_map.get_counters_iter():
        fullname = ctr.fullname.replace('.', ':')  # Redis name
        # Derived from: bliss.common.measurement.BaseCounter
        #   bliss.common.measurement.Counter
        #       bliss.common.measurement.SamplingCounter
        #           bliss.common.temperature.TempControllerCounter
        #           bliss.controllers.simulation_diode.SimulationDiodeSamplingCounter
        #   bliss.scanning.acquisition.mca.BaseMcaCounter
        #       bliss.scanning.acquisition.mca.SpectrumMcaCounter
        #       bliss.scanning.acquisition.mca.StatisticsMcaCounter
        ctr_classes = [c.__name__ for c in inspect.getmro(ctr.__class__)]
        #print(ctr.fullname, type(ctr), type(ctr.controller), ctr_classes)
        #controller_classes = [c.__name__ for c in inspect.getmro(ctr.controller.__class__)]
        if 'SpectrumMcaCounter' in ctr_classes:
            device_info = {'type': 'mca',
                           'description': ctr.controller.detector_brand +
                                          '/' + ctr.controller.detector_type}
            device = {'device_info': device_info,
                      'device_type': 'mca'}
            devices[fullname] = device
        elif 'StatisticsMcaCounter' in ctr_classes:
            device_info = {'type': 'mca',
                           'description': ctr.controller.detector_brand +
                                          '/' + ctr.controller.detector_type}
            device = {'device_info': device_info,
                      'device_type': 'mca'}
            devices[fullname] = device
        elif 'RoiMcaCounter' in ctr_classes:
            device_info = {'type': 'mca',
                           'description': ctr.mca.detector_brand +
                                          '/' + ctr.mca.detector_type}
            roi = ctr.mca.rois.resolve(ctr.roi_name)
            data_info = {'roi_start': roi[0],
                         'roi_end': roi[1]}
            device = {'device_info': device_info,
                      'data_info': data_info,
                      'device_type': 'mca'}
            devices[fullname] = device
        elif 'LimaBpmCounter' in ctr_classes:
            device_info = {'type': 'lima'}
            device = {'device_info': device_info,
                      'device_type': 'lima'}
            devices[fullname] = device
        elif 'LimaImageCounter' in ctr_classes:
            device_info = {'type': 'lima'}
            device = {'device_info': device_info,
                      'device_type': 'lima'}
            devices[fullname] = device
        elif 'RoiStatCounter' in ctr_classes:
            device_info = {'type': 'lima'}
            roi = ctr.parent_roi_counters.get(ctr.roi_name)
            data_info = {'roi_' + k: v for k, v in roi.to_dict().items()}
            device = {'device_info': device_info,
                      'device_type': 'lima',
                      'data_info': data_info}
            devices[fullname] = device
        elif 'TempControllerCounter' in ctr_classes:
            device_info = {'type': 'temperature',
                           'description': 'temperature'}
            device = {'device_info': device_info,
                      'device_type': 'temperature'}
            devices[fullname] = device
        elif 'SamplingCounter' in ctr_classes:
            device_info = {'type': 'samplingcounter',
                           'mode': str(ctr.mode).split('.')[-1]}
            device = {'device_info': device_info,
                      'device_type': 'samplingcounter',
                      'data_type': 'signal'}
            devices[fullname] = device
            if ctr.mode == SamplingMode.SAMPLES:
                device = {'device_info': device_info,
                          'device_type': 'samplingcounter'}
                devices[fullname + '_samples'] = device
            elif ctr.mode == SamplingMode.STATS:
                for stat in 'N', 'std', 'var', 'min', 'max', 'p2v':
                    device = {'device_info': device_info,
                              'device_type': 'samplingcounter'}
                    devices[fullname + '_'+stat] = device
        else:
            logger.info('Counter {} {} published as generic detector'
                        .format(fullname, ctr_classes))
            devices[fullname] = {}
    return devices

def static_technique_info():
    """
    Information on techniques from the session configuration

    :returns dict:
    """
    return static_scan_info().get('technique', {})


def default_technique():
    """
    Default technique from the session configuration

    :returns str:
    """
    return static_technique_info().get('default', 'undefined')


def current_technique():
    """
    Active technique from the session's scan saving object

    :returns str:
    """
    return scan_saving_get('technique')  # no default needed


def techniques():
    """
    List of available techniques from the session configuration

    :returns list:
    """
    return list(static_technique_info().get('techniques', {}).keys())


def technique_definition(technique):
    """
    Technique deifnition from the static session configuration

    :param str techique:
    :returns dict: {'name': technique,
                    'applications': dict(dict),
                    'plots': dict(list),
                    'plotselect': str}
    """
    applications = {}
    plots = {}
    ret = {'name': technique,
           'applications': applications,
           'plots': plots,
           'plotselect': ''}
    technique = static_technique_info().get('techniques', {}).get(technique, {})

    # Get the application definitions specified for this technique in YAML
    applicationdict = static_technique_info().get('applications', {})
    for name in technique.get('applications', []):
        definition = applicationdict.get(name, {})
        # for example {'xrf':{'I0': 'iodet',
        #                     'It': 'idet',
        #                     'mca': [...]}, ...}
        if definition:
            name = definition.pop('personal_name', name)
            applications[name] = definition

    # Get the plots specified for this technique in YAML
    plotdict = static_technique_info().get('plots', {})
    plotselect = ''
    for name in technique.get('plots', []):
        plotdefinition = plotdict.get(name, {})
        # for examples:
        #   {'personal_name': 'counters', 'items': ['iodet', 'xmap1:deadtime_det2', ...]}
        #   {'personal_name': 'counters', 'ndim': 2, 'grid': True}
        items = plotdefinition.get('items', [])
        ndim = plotdefinition.get('ndim', -1)
        grid = plotdefinition.get('grid', False)
        if not items and ndim < 0:
            continue
        name = plotdefinition.get('personal_name', name)
        if name in applications:
            name = name + '_plot'
        if not plotselect:
            plotselect = name
        plots[name] = {'items': items, 'grid': grid, 'ndim': ndim}
    ret['plotselect'] = plotselect
    return ret


def current_technique_definition():
    """
    Current technique deifnition from the static session configuration

    :returns dict(dict): technique:definition (str:dict)
    """
    return technique_definition(current_technique())


def filenames(**replace):
    """
    HDF5 file names to be save by the external writer.
    The first is to write and the other are masters to link.

    :returns list(str):
    """
    params = scan_saving_pathinfo()
    for k, v in replace.items():
        params[k] = v
    name_templates = naming.static_filename_templates()
    try:
        base_path = os.path.join(params['base_path'],
                                 params['template'].format(**params))
    except KeyError:
        paths = [''] * len(name_templates)
    else:
        relpath = '.'
        paths = []
        for name_template in name_templates:
            if name_template:
                try:
                    filename = name_template.format(**params)
                except KeyError:
                    paths.append('')
                else:
                    filename = os.path.join(base_path, relpath, filename)
                    paths.append(os.path.normpath(filename))
            else:
                paths.append('')
            relpath = os.path.join('..', relpath)
        if not paths[0]:
            paths = [''] * len(name_templates)
            filename = scan_utils.scan_filename(scan_saving_get('data_filename', ''))
            paths[0] = os.path.join(base_path, filename)
    return paths
