# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
import importlib

from .bpm import Bpm
from .roi import Roi, RoiCounters

from bliss.common.measurement import BaseCounter
from bliss.common.tango import DeviceProxy, DevFailed


def _attr_str(value, dtype='str', enums=None, err_str='?'):
    if value is None:
        return err_str
    elif dtype == 'str':
        return str(value)
    elif dtype == 'shape':
        return '<{0[0]} x {0[1]} x {0[2]}>'.format(value)
    elif dtype == 'roi':
        return '<{0[0]}, {0[1]}> <{0[2]} x {0[3]}>'.format(value)
    elif dtype == 'flip':
        return '<{0[0]} x {0[1]}>'.format(value)
    elif dtype == 'bin':
        return '<{0[0]} x {0[1]}>'.format(value)
    elif dtype == 'enum':
        return ' '.join([i if i != value else '[{}]'.format(i)
                         for i in sorted(enums)])
    return err_str


class Lima(object):
    ROI_COUNTERS = 'roicounter'
    BPM = 'beamviewer'

    # Standard interface

    def create_master_device(self, scan_pars):
        # Prevent cyclic imports
        from bliss.scanning.acquisition.lima import LimaAcquisitionMaster

        # Extract information
        npoints = scan_pars.get('npoints', 1)
        acq_expo_time = scan_pars['count_time']
        save_flag = scan_pars.get('save', False)
        multi_mode = 'INTERNAL_TRIGGER_MULTI' in self.available_triggers
        acq_nb_frames = npoints if multi_mode else 1
        acq_trigger_mode = scan_pars.get(
            'acq_trigger_mode',
            'INTERNAL_TRIGGER_MULTI' if multi_mode else 'INTERNAL_TRIGGER')

        # Instanciate master
        return LimaAcquisitionMaster(
            self,
            acq_nb_frames=acq_nb_frames,
            acq_expo_time=acq_expo_time,
            acq_trigger_mode=acq_trigger_mode,
            save_flag=save_flag,
            prepare_once=multi_mode)

    # Image counter class

    class ImageCounter(BaseCounter):
        ROTATION_0 = 0
        ROTATION_90 = 1
        ROTATION_180 = 2
        ROTATION_270 = 3

        def __init__(self, controller, proxy):
            self._proxy = proxy
            self._controller = controller

        # Standard counter interface

        @property
        def name(self):
            return 'image'

        @property
        def master_controller(self):
            return self._controller

        @property
        def dtype(self):
            # Because it is a reference
            return None

        @property
        def shape(self):
            # Because it is a reference
            return (0, 0)

        # Specific interface

        @property
        def proxy(self):
            return self._proxy

        @property
        def bin(self):
            return self._proxy.image_bin
        @bin.setter
        def bin(self,values):
            self._proxy.image_bin = values

        @property
        def flip(self):
            return self._proxy.image_flip
        @flip.setter
        def flip(self,values):
            self._proxy.image_flip = values

        @property
        def roi(self):
            return Roi(*self._proxy.image_roi)
        @roi.setter
        def roi(self,roi_values):
            if len(roi_values) == 4:
                self._proxy.image_roi = roi_values
            elif isinstance(roi_values[0],Roi):
                roi = roi_values[0]
                self._proxy.image_roi = (roi.x,roi.y,
                                         roi.width,roi.height)
            else:
                raise TypeError("Lima.image: set roi only accepts roi (class)"
                                " or (x,y,width,height) values")

        @property
        def rotation(self):
            rot_str = self._proxy.image_rotation
            return {'NONE' : self.ROTATION_0,
                    '90' : self.ROTATION_90,
                    '180' : self.ROTATION_180,
                    '270' : self.ROTATION_270}.get(rot_str)
        @rotation.setter
        def rotation(self,rotation):
            if isinstance(rotation,(str,unicode)):
                self._proxy.image_rotation = rotation
            else:
                rot_str = {self.ROTATION_0 : 'NONE',
                           self.ROTATION_90 : '90',
                           self.ROTATION_180 : '180',
                           self.ROTATION_270 : '270'}.get(rotation)
                if rot_str is None:
                    raise ValueError("Lima.image: rotation can only be 0,90,180 or 270")
                self._proxy.image_rotation = rot_str

        def __repr__(self):
            attr_list = ('image_bin', 'image_roi', 'image_rotation',
                         'image_type', 'image_flip',
                         'image_width', 'image_height')
            try:
                data = {attr_value.name: attr_value.value
                        for attr_value in self._proxy.read_attributes(attr_list)}
            except DevFailed:
                return 'Lima Image (Communication error with {!r})' \
                    .format(self._proxy.dev_name())

            shape = _attr_str((data['image_width'], data['image_height'],
                               data['image_type']), 'shape')
            roi = _attr_str(data['image_roi'], 'roi')
            binning = _attr_str(data['image_bin'], 'bin')
            rotation = _attr_str(data['image_rotation'], 'str')
            flip = _attr_str(data['image_flip'], 'flip')
            return 'Shape = {}\n' \
                'ROI = {}\n' \
                'Binning = {}\n' \
                'Rotation = {}\n' \
                'Flip = {}'.format(shape, roi, binning, rotation, flip)


    class Acquisition(object):
        ACQ_MODE_SINGLE,ACQ_MODE_CONCATENATION,ACQ_MODE_ACCUMULATION = range(3)

        def __init__(self,proxy):
            self._proxy = proxy
            acq_mode = (("SINGLE",self.ACQ_MODE_SINGLE),
                        ("CONCATENATION",self.ACQ_MODE_CONCATENATION),
                        ("ACCUMULATION",self.ACQ_MODE_ACCUMULATION))
            self.__acq_mode_from_str = dict(acq_mode)
            self.__acq_mode_from_enum = dict(((y,x) for x,y in acq_mode))
        @property
        def exposition_time(self):
            """
            exposition time for a frame
            """
            return self._proxy.acq_expo_time
        @exposition_time.setter
        def exposition_time(self,value):
            self._proxy.acq_expo_time = value

        @property
        def mode(self):
            """
            acquisition mode (SINGLE,CONCATENATION,ACCUMULATION)
            """
            acq_mode = self._proxy.acq_mode
            return self.__acq_mode_from_str.get(acq_mode)
        @mode.setter
        def mode(self,value):
            mode_str = self.__acq_mode_from_enum.get(value)
            if mode_str is None:
                possible_modes = ','.join(('%d -> %s' % (y,x)
                                           for x,y in self.__acq_mode_from_str.iteritems()))
                raise ValueError("lima: acquisition mode can only be: %s" % possible_modes)
            self._proxy.acq_mode = mode_str
        @property
        def trigger_mode(self):
            """
            Trigger camera mode
            """
            pass
        @trigger_mode.setter
        def trigger_mode(self,value):
            pass

        def __repr__(self):
            attr_list = ('acq_mode', 'acq_trigger_mode',
                         'acq_status', 'acq_expo_time', 'acq_nb_frames')
            try:
                data = [(attr_value.name[4:].replace('_', ' ').capitalize(),
                         attr_value.value)
                        for attr_value in self._proxy.read_attributes(attr_list)]
            except DevFailed:
                return 'Lima Acquisition (Communication error with {!r})' \
                    .format(self._proxy.dev_name())

            lines = ['{0} = {1}'.format(k, v) for k, v in data]
            return '\n'.join(lines)


    def __init__(self,name,config_tree):
        """Lima controller.

        name -- the controller's name
        config_tree -- controller configuration
        in this dictionary we need to have:
        tango_url -- tango main device url (from class LimaCCDs)
        """
        self._proxy = DeviceProxy(config_tree.get("tango_url"))
        self.name = name
        self.__bpm = None
        self.__roi_counters = None
        self._camera = None
        self._image = None
        self._acquisition = None

    @property
    def proxy(self):
        return self._proxy

    @property
    def image(self):
        if self._image is None:
            self._image = Lima.ImageCounter(self, self._proxy)
        return self._image

    @property
    def shape(self):
        return (-1, -1)

    @property
    def acquisition(self):
        if self._acquisition is None:
            self._acquisition = Lima.Acquisition(self._proxy)
        return self._acquisition

    @property
    def roi_counters(self):
        if self.__roi_counters is None:
            roi_counters_proxy = self._get_proxy(self.ROI_COUNTERS)
            self.__roi_counters = RoiCounters(self.name, roi_counters_proxy, self)
        return self.__roi_counters

    @property
    def camera(self):
        if self._camera is None:
            camera_type = self._proxy.lima_type
            proxy = self._get_proxy(camera_type)
            camera_module = importlib.import_module('.%s' % camera_type,__package__)
            self._camera = camera_module.Camera(self.name, self, proxy)
        return self._camera

    @property
    def camera_type(self):
        return self._proxy.camera_type

    @property
    def bpm(self):
        if self.__bpm is None:
            bpm_proxy = self._get_proxy(self.BPM)
            self.__bpm = Bpm(self.name, bpm_proxy, self)
        return self.__bpm

    @property
    def available_triggers(self):
        """
        This will returns all availables triggers for the camera
        """
        return self._proxy.getAttrStringValueList('acq_trigger_mode')

    def prepareAcq(self):
        self._proxy.prepareAcq()

    def startAcq(self):
        self._proxy.startAcq()

    def stopAcq(self):
        self._proxy.stopAcq()

    def _get_proxy(self,type_name):
        device_name = self._proxy.getPluginDeviceNameFromType(type_name)
        if not device_name:
            return
        if not device_name.startswith("//"):
            # build 'fully qualified domain' name
            # '.get_fqdn()' doesn't work
            db_host = self._proxy.get_db_host()
            db_port = self._proxy.get_db_port()
            device_name = "//%s:%s/%s" % (db_host, db_port, device_name)
        return DeviceProxy(device_name)

    def __repr__(self):
        attr_list = ('user_detector_name', 'camera_model',
                     'camera_type', 'lima_type')
        try:
            data = {attr.name: ('?' if attr.has_failed else attr.value)
                    for attr in self._proxy.read_attributes(attr_list)}
        except DevFailed:
            return 'Lima {} (Communication error with {!r})' \
                .format(self.name, self._proxy.dev_name())

        return '{0[user_detector_name]} - ' \
               '{0[camera_model]} ({0[camera_type]}) - Lima {0[lima_type]}\n\n' \
               'Image:\n{1!r}\n\n' \
               'Acquisition:\n{2!r}\n\n' \
               'ROI Counters:\n{3!r}' \
               .format(data, self.image, self.acquisition, self.roi_counters)

    # Expose counters

    @property
    def counters(self):
        all_counters = [self.image]
        all_counters += list(self.roi_counters.counters)
        all_counters += list(self.bpm.counters)
        return counter_namespace(all_counters)

    @property
    def counter_groups(self):
        dct = {}

        # Image counter
        dct['images'] = counter_namespace([self.image])

        # BPM counters
        dct['bpm'] = counter_namespace(self.bpm.counters)

        # Specific ROI counters
        for counters in self.roi_counters.iter_single_roi_counters():
            dct['roi_counters.' + counters.name] = counter_namespace(counters)

        # All ROI counters
        dct['roi_counters'] = counter_namespace(self.roi_counters.counters)

        # Default grouped
        default_counters = list(dct['images']) + list(dct['roi_counters'])
        dct['default'] = counter_namespace(default_counters)

        # Return namespace
        return namespace(dct)


# TODO: This should go somewhere in bliss/common

def counter_namespace(counters):
    return namespace({counter.name: counter for counter in counters})


class namespace(object):
    def __init__(self, dct):
        self.__dict__.update(dct)

    def __iter__(self):
        return (value for name, value in sorted(self.__dict__.items()))

    def __getattr__(self, arg):
        if arg.startswith('__'):
            raise AttributeError(arg)
        if any(name.startswith(arg + '.') for name in dir(self)):
            getter_cls = type('Getter', (object,), {
                '__getattr__': lambda _, key: getattr(self, arg + '.' + key)})
            return getter_cls()
        raise AttributeError(arg)

    def __setattr__(self, key, value):
        raise TypeError('namespace is not mutable')
