# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import textwrap
import numpy
from .roi import Roi
from bliss.common.counter import Counter
from bliss.common.utils import autocomplete_property
from bliss.config.beacon_object import BeaconObject


class LimaImageParameters(BeaconObject):
    def __init__(self, config, proxy, name):
        self._proxy = proxy
        self._max_width, self._max_height = self._tmp_get_max_width_height()

        super().__init__(config, name=name, share_hardware=False, path=["image"])

    def _tmp_get_max_width_height(self):
        """TODO: this function should be removed once the equivalent of it 
           is exposed directly on the lima tango server"""
        try:
            tmp_roi = self._proxy.image_roi
            tmp_bin = self._proxy.image_bin
            self._proxy.image_bin = [1, 1]
            self._proxy.image_roi = [0, 0, 0, 0]
            _, _, width, height = self._proxy.image_roi
            self._proxy.image_bin = tmp_bin
            self._proxy.image_roi = tmp_roi

            return width, height
        except AttributeError:
            return 0, 0

    def check_init(self):
        """workaround to make sure that lima object can be
           instantiated without running device server
           TODO: to be removed
        """
        if self._max_width == 0 or self._max_height == 0:
            self._max_width, self._max_height = self._tmp_get_max_width_height()
            if self._max_width == 0 or self._max_height == 0:
                raise RuntimeError("There is a problem with the device server!")

    @property
    def _max_dim_full_frame_ref(self):
        self.check_init()
        return (self._max_width, self._max_height)

    @property
    def _max_dim_lima_ref(self):
        self.check_init()
        tmp = self._calc_roi(
            numpy.array([0, 0, self._max_width, self._max_height]),
            self.rotation,
            self.flip,
            self.binning,
        )
        return (tmp[2], tmp[3])

    def _calc_roi(self, roi, rot, flip, binning, inverse=False):
        """transformation for roi from raw full frame reference to 
           lima style reference with rot and flip applied.
           inverse calculation if inverse=True

           inverse = False  : full frame ref -> lima ref
           inverse = True   : lima ref -> full frame ref

           TODO: this calculation should be one in the lima server!
           see https://gitlab.esrf.fr/bliss/bliss/-/merge_requests/2176#note_65379
        """
        self.check_init()

        assert isinstance(roi, numpy.ndarray)

        def roi2pos(roi):
            """trasform roi(x,y,width,height) -> pos(x1,y1,x2,y2) top-left, bottom-right"""
            pos = roi.copy()
            pos[2] += pos[0]
            pos[3] += pos[1]
            return pos

        def pos2roi(pos):
            """trasform pos(x1,y1,x2,y2) top-left, bottom-right -> roi(x,y,width,height)"""
            roi = pos.copy()
            roi[2] -= roi[0]
            roi[3] -= roi[1]
            return roi.astype(numpy.int)

        def check_bondary(pos, i, maxx):
            if pos[i] < 0:
                pos[i] += maxx
            elif pos[i] > maxx:
                pos[i] -= maxx

        # to disable black on a block of code use fmt: off, fmt: on
        # fmt: off
        rot_mat = {'NONE' : numpy.array([[1,0],
                                         [0,1]]),
                     '90' : numpy.array([[0,-1],
                                         [1,0 ]]),
                    '180' : numpy.array([[-1,0 ],
                                         [0 ,-1]]),
                    '270' : numpy.array([[0 ,1],
                                         [-1,0]])}
                                
        flip_mat = {str([False,False]):numpy.array([[1,0],
                                                    [0,1]]),
                    str([False,True ]):numpy.array([[1 ,0],
                                                    [0,-1]]),
                    str([True, False]):numpy.array([[-1,0],
                                                    [0 ,1]]),
                    str([True, True ]):numpy.array([[-1,0 ],
                                                    [0 ,-1]])}
                                        
        bin_mat = numpy.array([[1./binning[0],0         ],
                               [0,         1./binning[1]]])
        # fmt: on

        # init stuff
        pos = roi2pos(roi)
        res = numpy.zeros(4)

        # define full transformation matrix
        op = numpy.dot(flip_mat[str(flip)], bin_mat)
        op = numpy.dot(rot_mat[rot], op)

        if inverse:
            op = numpy.linalg.inv(op)

        # calc top-left, bottom-right
        res[0:2] = numpy.dot(op, pos[0:2])
        res[2:4] = numpy.dot(op, pos[2:4])

        # check boundaries
        if inverse:
            mw = self._max_width
            mh = self._max_height
        else:
            mw, mh = numpy.abs(
                numpy.dot(op, numpy.array([self._max_width, self._max_height]))
            )

        check_bondary(res, 0, mw)
        check_bondary(res, 1, mh)
        check_bondary(res, 2, mw)
        check_bondary(res, 3, mh)

        # swap if needed
        if res[0] > res[2]:
            res[0:4:2] = numpy.flip(res[0:4:2])
        if res[1] > res[3]:
            res[1:4:2] = numpy.flip(res[1:4:2])

        # fix zero
        r_w, r_h = numpy.abs(numpy.dot(op, roi[2:4]))
        if res[0] == 0 and res[2] - pos[0] > r_w:
            res[0] = res[2]
            res[2] += r_w
        if res[1] == 0 and res[3] - pos[1] > r_h:
            res[1] = res[3]
            res[3] += r_h
        if res[2] == 0:
            res[2] = mw
        if res[3] == 0:
            res[3] = mh

        # deal with float / int stuff
        if not inverse:
            res = numpy.ceil(res)

        return pos2roi(res)

    binning = BeaconObject.property_setting("binning", default=[1, 1])

    @binning.setter
    def binning(self, value):
        if isinstance(value, numpy.ndarray):
            value = [int(value[0]), int(value[1])]
        assert isinstance(value, list)
        assert len(value) == 2
        assert isinstance(value[0], int) and isinstance(value[1], int)
        return value

    flip = BeaconObject.property_setting("flip", default=[False, False])

    @flip.setter
    def flip(self, value):
        if isinstance(value, numpy.ndarray):
            value = [bool(value[0]), bool(value[1])]
        assert isinstance(value, list)
        assert len(value) == 2
        assert isinstance(value[0], bool) and isinstance(value[1], bool)
        return value

    rotation = BeaconObject.property_setting("rotation", default="NONE")

    @rotation.setter
    def rotation(self, value):
        if isinstance(value, int):
            value = str(value)
        if value == "0":
            value = "NONE"
        assert isinstance(value, str)
        assert value in ["NONE", "90", "180", "270"]
        return value

    # _roi is saved in chip reference frame (rot,flip,bin) NOT applied!
    _roi = BeaconObject.property_setting("roi", default=[0, 0, 0, 0])

    @property
    def roi(self):
        r = self._roi.copy()
        if r[2] == 0:
            r[2] = self._max_width
        if r[3] == 0:
            r[3] = self._max_height
        return Roi(
            *self._calc_roi(numpy.array(r), self.rotation, self.flip, self.binning)
        )

    def _validate_roi(self, roi_array):
        """roi_array_list is roi in full-frame reference system"""
        assert isinstance(roi_array, numpy.ndarray)
        assert all(roi_array >= 0), "Roi too big!"
        assert roi_array[0] + roi_array[2] <= self._max_width, "Roi too big!"
        assert roi_array[1] + roi_array[3] <= self._max_height, "Roi too big!"

    @roi.setter
    def roi(self, roi_values):
        if roi_values is None:
            self._roi = [0, 0, 0, 0]
        elif isinstance(roi_values, str) and roi_values == "NONE":
            # Check it is an str first to avoid to use == within numpy.array
            self._roi = [0, 0, 0, 0]
        elif len(roi_values) == 4:
            new_roi = self._calc_roi(
                numpy.array(roi_values),
                self.rotation,
                self.flip,
                self.binning,
                inverse=True,
            )
            self._validate_roi(new_roi)
            self._roi = new_roi
        elif isinstance(roi_values[0], Roi):
            roi_obj = roi_values[0]
            r = [roi_obj.x, roi_obj.y, roi_obj.width, roi_obj.height]
            new_roi = self._calc_roi(
                numpy.array(r), self.rotation, self.flip, self.binning, inverse=True
            )
            self._validate_roi(new_roi)
            self._roi = new_roi
        else:
            raise TypeError(
                "Lima.image: set roi only accepts roi (class)"
                " or (x,y,width,height) values"
            )

    def to_dict(self):
        return {
            "image_rotation": self.rotation,
            "image_flip": self.flip,
            "image_bin": self.binning,
            "image_roi": list(self.roi.to_array()),
        }

    def sync(self):
        """applies all image parameters from the tango server to bliss"""
        self.rotation = self._proxy.image_rotation
        self.flip = self._proxy.image_flip
        self.binning = self._proxy.image_bin
        self.roi = self._proxy.image_roi  # it is important that roi comes last!


class ImageCounter(Counter):
    def __init__(self, controller, proxy):
        self._proxy = proxy
        super().__init__("image", controller)

    # Standard counter interface

    def __info__(self):
        return textwrap.dedent(
            f"""       flip:     {self.flip}
       rotation: {self.rotation}
       roi:      {self.roi}
       binning:  {self.binning}
       width:    {self.width}
       height:   {self.height}
       type:     {self.type}"""
        )

    @property
    def dtype(self):
        # Because it is a reference
        return None

    @property
    def shape(self):
        # Because it is a reference
        return (0, 0)

    # Specific interface

    @autocomplete_property
    def proxy(self):
        return self._proxy

    @property
    def flip(self):
        return self._counter_controller._image_params.flip

    @flip.setter
    def flip(self, value):
        self._counter_controller._image_params.flip = value

    @property
    def rotation(self):
        return self._counter_controller._image_params.rotation

    @rotation.setter
    def rotation(self, value):
        self._counter_controller._image_params.rotation = value

    @autocomplete_property
    def roi(self):
        return self._counter_controller._image_params.roi

    @roi.setter
    def roi(self, value):
        self._counter_controller._image_params.roi = value

    @property
    def binning(self):
        return self._counter_controller._image_params.binning

    @binning.setter
    def binning(self, value):
        self._counter_controller._image_params.binning = value

    @property
    def bin(self):
        return self._counter_controller._image_params.binning

    @bin.setter
    def bin(self, value):
        self._counter_controller._image_params.binning = value

    def sync(self):
        """applies all image parameters from the tango server to bliss"""
        return self._counter_controller._image_params.sync()

    @property
    def width(self):
        return self.roi.width

    @property
    def height(self):
        return self.roi.height
