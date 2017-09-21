# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
import importlib
try:
    from tango.gevent import DeviceProxy
except ImportError:
    try:
        from PyTango.gevent import DeviceProxy
    except ImportError:
        import warnings
        from PyTango import DeviceProxy
        warnings.warn("Tango does not support gevent, please update your Python tango version", RuntimeWarning)
    
from bliss.config import settings
from .bpm import Bpm

class Lima(object):
    ROI_COUNTERS = 'roicounter'
    BPM = 'beamviewer'

    class Roi(object):
        def __init__(self,x,y,width,height,name = None):
            self.x = x
            self.y = y
            self.width = width
            self.height = height
            self.name = name
        def is_valid(self):
            return (self.x >=0 and self.y >= 0 and
                    self.width >= 0 and self.height >=0)
        
        def __repr__(self):
            return "<%s,%s> <%s x %s>" % (self.x,self.y,
                                          self.width,self.height)

    class Image(object):
        ROTATION_0,ROTATION_90,ROTATION_180,ROTATION_270 = range(4)
        
        def __init__(self,proxy):
            self._proxy = proxy
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
            return Lima.Roi(*self._proxy.image_roi)
        @roi.setter
        def roi(self,roi_values):
            if len(roi_values) == 4:
                self._proxy.image_roi = roi_values
            elif isinstance(roi_values[0],Lima.Roi):
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
            
    class RoiCounters(object):
        def __init__(self,name,proxy):
            self._proxy = proxy
            self._proxy.Start()
            self.name = '%s:RoiCounters' % name
            self._current_config = settings.SimpleSetting(self.name,default_value = 'default')
            self._save_rois = settings.HashObjSetting('%s:%s' % (self.name,
                                                                 self._current_config.get()))

        def set_roi(self,name,roi_values):
            if len(roi_values) == 4:
                roi = Lima.Roi(*roi_values)
            elif isinstance(roi_values[0],Lima.Roi):
                roi = roi_values[0]
            else:
                raise TypeError("Lima.RoiCounters: roi accepts roi (class)"
                                " or (x,y,width,height) values")
            roi.name = name
            roi_id = self._proxy.addNames((name,))
            self._proxy.setRois(roi_id,
                                roi.x,roi.y,
                                roi.width,roi.height)
            self._save_rois[name] = roi
            
        def get_rois(self):
            return self._save_rois.values()

        def get_saved_config_names(self):
            return list(settings.scan(match='%s:*' % self.name))

        @property
        def config_name(self):
            return self._current_config.get()
        @config_name.setter
        def config_name(self,name):
            self._current_config.set(name)
            self._save_rois = settings.HashObjSetting('%s:%s' % (self.name,name))

        def upload_rois(self):
            roi_list = [roi for roi in self.get_rois() if roi.is_valid()]
            roi_id_list = self._proxy.addNames([x.name for x in roi_list])
            rois_values = list()
            for roi_id,roi in zip(roi_id_list,roi_list):
                rois_values.extend((roi_id,
                                    roi.x,roi.y,
                                    roi.width,roi.height))
            self._proxy.setRois(rois_values)

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
            self._image = Lima.Image(self._proxy)
        return self._image

    @property
    def acquisition(self):
        if self._acquisition is None:
            self._acquisition = Lima.Acquisition(self._proxy)
        return self._acquisition
    
    @property
    def roi_counters(self):
        if self.__roi_counters is None:
            roi_counters_proxy = self._get_proxy(self.ROI_COUNTERS)
            self.__roi_counters = Lima.RoiCounters(self.name, roi_counters_proxy)
        return self.__roi_counters
    
    @property
    def camera(self):
        if self._camera is None:
            camera_type = self._proxy.lima_type
            proxy = self._get_proxy(camera_type)
            camera_module = importlib.import_module('.%s' % camera_type,__package__)
            self._camera = camera_module.Camera(self.name, proxy)
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

    def _get_proxy(self,type_name):
        device_name = self._proxy.getPluginDeviceNameFromType(type_name)
        if not device_name.startswith("//"):
            # build 'fully qualified domain' name
            # '.get_fqdn()' doesn't work
            db_host = self._proxy.get_db_host()
            db_port = self._proxy.get_db_port()
            device_name = "//%s:%s/%s" % (db_host, db_port, device_name)
        return DeviceProxy(device_name)


