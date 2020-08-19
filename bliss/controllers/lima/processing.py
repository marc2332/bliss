# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.config.beacon_object import BeaconObject
import textwrap
import enum


class LimaProcessing(BeaconObject):

    BG_SUB_MODES = {
        "disable": "Disabled",
        "enable_on_fly": "Enabled (Take bg-image on demand)",
        "enable_file": "Enabled (Take bg-image from file)",
    }

    def __init__(self, config, proxy, name):
        self._proxy = proxy
        self._mask_changed = False
        self._flatfield_changed = False
        self._background_changed = False
        super().__init__(config, name=name, share_hardware=False, path=["processing"])

    mask = BeaconObject.property_setting("mask", default="")

    @mask.setter
    def mask(self, value):
        assert isinstance(value, str)
        if self.mask != value:
            self._mask_changed = True
        return value

    use_mask = BeaconObject.property_setting("use_mask", default=False)

    @use_mask.setter
    def use_mask(self, value):
        assert isinstance(value, bool)
        return value

    flatfield = BeaconObject.property_setting("flatfield", default="")

    @flatfield.setter
    def flatfield(self, value):
        assert isinstance(value, str)
        if self.flatfield != value:
            self._flatfield_changed = True
        return value

    use_flatfield = BeaconObject.property_setting("use_flatfield", default=False)

    @use_flatfield.setter
    def use_flatfield(self, value):
        assert isinstance(value, bool)
        return value

    runlevel_mask = BeaconObject.property_setting("runlevel_mask", default=0)
    runlevel_flatfield = BeaconObject.property_setting("runlevel_flatfield", default=1)
    runlevel_background = BeaconObject.property_setting(
        "runlevel_background", default=2
    )
    runlevel_roicounter = BeaconObject.property_setting(
        "runlevel_roicounter", default=10
    )
    runlevel_bpm = BeaconObject.property_setting("runlevel_bpm", default=10)

    @runlevel_mask.setter
    def runlevel_mask(self, value):
        assert isinstance(value, int)
        return value

    @runlevel_flatfield.setter
    def runlevel_flatfield(self, value):
        assert isinstance(value, int)
        return value

    @runlevel_background.setter
    def runlevel_background(self, value):
        assert isinstance(value, int)
        return value

    @runlevel_roicounter.setter
    def runlevel_roicounter(self, value):
        assert isinstance(value, int)
        return value

    @runlevel_bpm.setter
    def runlevel_bpm(self, value):
        assert isinstance(value, int)
        return value

    background = BeaconObject.property_setting("background", default="")

    @background.setter
    def background(self, value):
        assert isinstance(value, str)
        if self.background != value:
            self._background_changed = True
        return value

    use_background_substraction = BeaconObject.property_setting(
        "use_background_substraction", default="disable"
    )

    @use_background_substraction.setter
    def use_background_substraction(self, value):
        assert isinstance(value, str)
        assert value in self.BG_SUB_MODES.keys()
        return value

    def to_dict(self):
        return {
            "use_mask": self.use_mask,
            "use_flatfield": self.use_flatfield,
            "use_background_substraction": self.use_background_substraction,
        }

    def __info__(self):
        return textwrap.dedent(
            f"""            Mask
            ----
            use mask: {self.use_mask}
            mask image path: {self.mask}
            
            Flatfield
            ---------
            use flatfield: {self.use_flatfield}
            flatfield image path: {self.flatfield} 
            
            Background Substraction
            -----------------------
            mode: {self.BG_SUB_MODES[self.use_background_substraction]}
            background_image_path: {self.background}
            
            Expert Settings
            ---------------
            Lima Run-Level:
               Mask           {self.runlevel_mask}
               Flatfield:     {self.runlevel_flatfield}
               Bg-Sub:        {self.runlevel_background}
               Roi Counters:  {self.runlevel_roicounter}
               BPM:           {self.runlevel_bpm}
            """
        )
