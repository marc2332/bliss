# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from .roi import Roi
from .properties import LimaProperty
from bliss.common.measurement import BaseCounter
import numpy
import h5py
import os


class ImageCounter(BaseCounter):
    def __init__(self, controller, proxy):
        self._proxy = proxy
        self._controller = controller

    # Standard counter interface

    @property
    def name(self):
        return "image"

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

    @LimaProperty
    def roi(self):
        return Roi(*self._proxy.image_roi)

    @roi.setter
    def roi(self, roi_values):
        if len(roi_values) == 4:
            self._proxy.image_roi = roi_values
        elif isinstance(roi_values[0], Roi):
            roi = roi_values[0]
            self._proxy.image_roi = (roi.x, roi.y, roi.width, roi.height)
        else:
            raise TypeError(
                "Lima.image: set roi only accepts roi (class)"
                " or (x,y,width,height) values"
            )

    # handling of reference saving in hdf5

    def to_ref_array(self, channel, root_path):
        """ used to produce a string version of a lima reference that can be saved in hdf5
        """
        # looks like the events are not emitted after saving,
        # therefore we will use 'last_image_ready' instead
        # of "last_image_saved" for now
        # last_image_saved = event_dict["data"]["last_image_saved"]

        lima_data_view = channel.data_node.get(0, -1)

        tmp = lima_data_view._get_filenames(
            channel.data_node.info, *range(0, len(lima_data_view))
        )

        if tmp != []:
            tmp = numpy.array(tmp, ndmin=2)
            relpath = [os.path.relpath(i, start=root_path) for i in tmp[:, 0]]
            basename = [os.path.basename(i) for i in tmp[:, 0]]
            entry = tmp[:, 1]
            frame = tmp[:, 2]
            file_type = tmp[:, 3]

            return numpy.array(
                (basename, file_type, frame, entry, relpath),
                dtype=h5py.special_dtype(vlen=str),
            ).T
        return None
