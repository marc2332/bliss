# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

class Camera(object):
    NO,OFFSET_ONLY,OFFSET_AND_GAIN = range(3)
    
    def __init__(self, lima_device,name,proxy):
        self.name = name
        self._proxy = proxy
        corr_convertion = (("NO",self.NO),
                           ("OFFSET ONLY",self.OFFSET_ONLY),
                           ("OFFSET AND GAIN",self.OFFSET_AND_GAIN))
        
        self.__correction_mode_from_str = dict(corr_convertion)
        self.__correction_mode_from_enum = dict(((y,x) for x,y in corr_convertion))
    @property
    def gain(self):
        return self._proxy.gain
    @gain.setter
    def gain(self,value):
        self._proxy.gain = value

    @property
    def correction_mode(self):
        corr_mode_str = self._proxy.correction_mode
        return self.__correction_mode_from_str.get(corr_mode_str)
    @correction_mode.setter
    def correction_mode(self,value):
        corr_mode_str = self.__correction_mode_from_enum(value)
        if corr_mode_str is None:
            raise ValueError("perkinelmer: correction_mode can't be set to %d" % value)
        self._proxy.correction_mode = corr_mode_str

    @property
    def keep_first_image(self):
        bool_str = self._proxy.keep_first_image
        return bool_str == "YES"
    @keep_first_image.setter
    def keep_first_image(self,value):
        bool_str = "YES" if value else "NO"
        self._proxy.keep_first_image = bool_str

    def start_acq_gain_image(self,nb_frames,exposure_time):
        self._proxy.startAcqGainImage(nb_frames,exposure_time)

    def start_acq_offset_image(self,nb_frames,exposure_time):
        self._proxy.startAcqOffsetImage(nb_frames,exposure_time)
    
