# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

class Camera(object):
    INVALID_SHUTTER,GLOBAL_SHUTTER,ROLLING_SHUTTER = (-1,0,1)
    
    def __init__(self,name,proxy):
        self.name = name
        self._proxy = proxy

        rolling_shutter_conversion = (("-1",self.INVALID_SHUTTER),
                                      ("0",self.GLOBAL_SHUTTER),
                                      ("1",self.ROLLING_SHUTTER))
        self.__rolling_shutter_from_str = dict(rolling_shutter_conversion)
        self.__rolling_shutter_from_enum = dict(((y,x) for x,y in rolling_shutter_conversion))
    @property
    def last_error(self):
        """ Pco last error
        """
        return self._proxy.lastError

    @property
    def cam_info(self):
        """
        general camera information
        """
        return self._proxy.camInfo

    @property
    def cam_type(self):
        """
        camera type
        """
        return self._proxy.camType

    @property
    def cameralink_transfer_parameters(self):
        """
        camera link transfer parameters
        """
        return self._proxy.clXferPar

    @property
    def frame_run_time(self):
        """
        Frame run time (sec)
        """
        return self._proxy.cocRunTime

    @property
    def frame_rate(self):
        """
        Frame Rate (Hz)
        """
        return self._proxy.frameRate

    @property
    def last_image_recorded(self):
        """
        last image recorded (Dimax, 2K, 4K)
        """
        return self._proxy.lastImgRecorded

    @property
    def last_image_acquired(self):
        """
        last image acquired
        """
        return self._proxy.lastImgAcquired

    @property
    def maximum_number_of_images(self):
        """
        Maximum number of images
        """
        return self._proxy.maxNbImages

   @property
    def version(self):
        """
        Pco plugin version
        """
        return self._proxy.version

    @property
    def trace_acq(self):
        """
        Pco cam trace/time acq
        """
        return self._proxy.traceAcq

    @property
    def pixel_rate(self):
        """
        Pco Edge/2K/4K pixel rate
        """
        return int(self._proxy.pixelRate)

    @pixel_rate.setter
    def pixel_rate(self,value):
        int_val = int(value)
        possible_pixel_rate = self.pixel_rate_valid_values
        if int_val not in possible_pixel_rate:
            raise ValueError("Pixel rate on this camera "
                             "can only be those values: " + ','.join(pixel_rate_valid_values))
        else:
            self._proxy.pixelRate = str(int_val)
    
    @property
    def pixel_rate_valid_values(self):
        """
        Possible pixel rate for this camera
        """
        values = self._proxy.pixelRateValidValues
        if values == "invalid":
            return [self.pixel_rate]
        else:
            return [int(x) for x in values.split(' ') if x]

    @property
    def pixel_rate_info(self):
        """
        Pco pixel rate info (MHz)
        """
        return self._proxy.pixelRateInfo

    @property
    def rolling_shutter(self):
        """
        Pco Edge Rolling/Global shutter
        """
        shutter_mode = self._proxy.rollingShutter
        return self.__rolling_shutter_from_str.get(shutter_mode)

    @rolling_shutter.setter
    def rolling_shutter(self,value):
        shutter_mode = self.__rolling_shutter_from_enum.get(value)
        if shutter_mode is None:
            raise ValueError("pco: rolling_shutter can't be set to %d"
                             ", possibles values are:"
                             "%d for %s or %d for %s" % (self.GLOBAL_SHUTTER,"Global",
                                                         self.ROLLING_SHUTTER,"Rolling"))
        self._proxy.rollingShutter = shutter_mode

    @property
    def adc(self):
         """
         Number of present working ADC
         """
         return self._proxy.adc

    @property
    def adc_max_number(self):
        """
        Maximum number of available ADC
        """
        return self._proxy.adcMax

     
