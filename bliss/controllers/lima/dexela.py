# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from .properties import LimaProperty
from .lima_base import CameraBase


class Camera(CameraBase):
    @LimaProperty
    def synchro_mode(self):
        return "IMAGE"
