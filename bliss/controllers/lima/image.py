# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from typing import Iterable
import typeguard
import numpy

from bliss import global_map
from bliss.common.counter import Counter
from bliss.config.beacon_object import BeaconObject
from bliss.common.logtools import log_debug

# ========== RULES of Tango-Lima ==================

# Lima rules and order of image transformations:

# 1) binning
# 2) flip
# 3) rotation
# 4) roi (expressed in the current state f(bin, flip, rot))

#  roi is defined in the current image referential (i.e roi = f(rot, flip, bin))
#  raw_roi is defined in the raw image referential (i.e with bin=1,1  flip=False,False, rot=0)
#  flip =  [Left-Right, Up-Down]

# ----------------- helpers for ROI coordinates (x,y,w,h) transformations (flip, rotation, binning) --------------


def current_coords_to_raw_coords(coords_list, img_size, flip, rotation, binning):

    if not isinstance(coords_list, numpy.ndarray):
        pts = numpy.array(coords_list)
    else:
        pts = coords_list.copy()

    w0, h0 = img_size

    # inverse rotation
    if rotation != 0:
        pts = calc_pts_rotation(pts, -rotation, (w0, h0))
        if rotation in [90, 270]:
            w0, h0 = img_size[1], img_size[0]

    # unflipped roi
    if flip[0]:
        pts[:, 0] = w0 - pts[:, 0]

    if flip[1]:
        pts[:, 1] = h0 - pts[:, 1]

    # unbinned roi
    xbin, ybin = binning
    if xbin != 1 or ybin != 1:
        pts[:, 0] = pts[:, 0] * xbin
        pts[:, 1] = pts[:, 1] * ybin

    return pts


def raw_coords_to_current_coords(
    raw_coords_list, raw_img_size, flip, rotation, binning
):

    if not isinstance(raw_coords_list, numpy.ndarray):
        pts = numpy.array(raw_coords_list)
    else:
        pts = raw_coords_list.copy()

    w0, h0 = raw_img_size

    # bin roi
    xbin, ybin = binning
    if xbin != 1 or ybin != 1:
        pts[:, 0] = pts[:, 0] / xbin
        pts[:, 1] = pts[:, 1] / ybin
        w0 = w0 / xbin
        h0 = h0 / ybin

    # flip roi
    if flip[0]:
        pts[:, 0] = w0 - pts[:, 0]

    if flip[1]:
        pts[:, 1] = h0 - pts[:, 1]

    # rotate roi
    if rotation != 0:
        pts = calc_pts_rotation(pts, rotation, (w0, h0))

    return pts


def raw_roi_to_current_roi(raw_roi, raw_img_size, flip, rotation, binning):
    x, y, w, h = raw_roi
    pts = [[x, y], [x + w, y + h]]
    pts = raw_coords_to_current_coords(pts, raw_img_size, flip, rotation, binning)
    x1, y1 = pts[0]
    x2, y2 = pts[1]
    x = min(x1, x2)
    y = min(y1, y2)
    w = abs(x2 - x1)
    h = abs(y2 - y1)

    return [round(x), round(y), round(w), round(h)]


def current_roi_to_raw_roi(current_roi, img_size, flip, rotation, binning):
    x, y, w, h = current_roi
    pts = [[x, y], [x + w, y + h]]
    pts = current_coords_to_raw_coords(pts, img_size, flip, rotation, binning)
    x1, y1 = pts[0]
    x2, y2 = pts[1]
    x = min(x1, x2)
    y = min(y1, y2)
    w = abs(x2 - x1)
    h = abs(y2 - y1)
    return [x, y, w, h]


def calc_pts_rotation(pts, angle, img_size):

    if not isinstance(pts, numpy.ndarray):
        pts = numpy.array(pts)

    # define the camera fullframe
    w0, h0 = img_size
    frame = numpy.array([[0, 0], [w0, h0]])

    # define the rotation matrix
    theta = numpy.deg2rad(angle) * -1  # Lima rotation is clockwise !
    R = numpy.array(
        [[numpy.cos(theta), -numpy.sin(theta)], [numpy.sin(theta), numpy.cos(theta)]]
    )

    new_frame = numpy.dot(frame, R)
    new_pts = numpy.dot(pts, R)

    # find new origin
    ox = numpy.amin(new_frame[:, 0])
    oy = numpy.amin(new_frame[:, 1])

    # apply new origin
    new_pts[:, 0] = new_pts[:, 0] - ox
    new_pts[:, 1] = new_pts[:, 1] - oy

    return new_pts


# -------------------------------------------------------------------------------------------


def _to_list(setting, value):
    if value is None:
        return  # will take the default value
    return list(value)


class LimaImageParameters(BeaconObject):
    def __init__(self, controller, name):
        config = controller._config_node
        super().__init__(config, name=name, share_hardware=False, path=["image"])
        # properly put in map, to have "parameters" under the corresponding Lima controller node
        # (and not in "controllers")
        global_map.register(self, parents_list=[controller], tag="image_parameters")

    binning = BeaconObject.property_setting(
        "binning", default=[1, 1], set_marshalling=_to_list, set_unmarshalling=_to_list
    )

    @binning.setter
    @typeguard.typechecked
    def binning(self, value: Iterable[int]):
        log_debug(self, f"set binning {value}")
        assert len(value) == 2
        value = [int(value[0]), int(value[1])]
        return value

    flip = BeaconObject.property_setting(
        "flip",
        default=[False, False],
        set_marshalling=_to_list,
        set_unmarshalling=_to_list,
    )

    @flip.setter
    @typeguard.typechecked
    def flip(self, value: Iterable[bool]):
        log_debug(self, f"set flip {value}")
        assert len(value) == 2
        value = [bool(value[0]), bool(value[1])]
        return value

    rotation = BeaconObject.property_setting("rotation", default="NONE")

    @rotation.setter
    def rotation(self, value):
        log_debug(self, f"set rotation {value}")
        if isinstance(value, int):
            value = str(value)
        if value == "0":
            value = "NONE"
        assert isinstance(value, str)
        assert value in ["NONE", "90", "180", "270"]
        return value

    _roi = BeaconObject.property_setting(
        "_roi",
        default=[0, 0, 0, 0],
        set_marshalling=_to_list,
        set_unmarshalling=_to_list,
    )

    @_roi.setter
    @typeguard.typechecked
    def _roi(self, value: Iterable[int]):
        log_debug(self, f"set _roi {value}")
        assert len(value) == 4
        value = [int(value[0]), int(value[1]), int(value[2]), int(value[3])]
        return value


class ImageCounter(Counter):
    def __init__(self, controller):
        self._proxy = controller._proxy
        self._max_width = 0
        self._max_height = 0
        self._cur_roi = None
        self._raw_roi = (
            None
        )  # caching self._image_params._roi to avoid unecessary access to redis

        super().__init__("image", controller)

        self._image_params = LimaImageParameters(
            controller, f"{controller._name_prefix}:image"
        )

    def __info__(self):

        lines = []

        lines.append(f"width:    {self.width}")
        lines.append(f"height:   {self.height}")
        lines.append(f"depth:    {self.depth}")
        lines.append(f"bpp:      {self.bpp}")

        lines.append(f"binning:  {self.binning}")
        lines.append(f"flip:     {self.flip}")
        lines.append(f"rotation: {self.rotation}")
        lines.append(f"roi:      {self.roi}")

        return "\n".join(lines)

    @property
    def dtype(self):
        # Because it is a reference
        return None

    @property
    def shape(self):
        # Because it is a reference
        return (0, 0)

    # ------- Specific interface ----------------------------------

    @property
    def fullsize(self):
        """return the detector size taking into account the current binning and rotation"""

        w0, h0 = self._get_detector_max_size()

        xbin, ybin = self.binning
        w0 = int(w0 / xbin)
        h0 = int(h0 / ybin)

        if (abs(self.rotation) % 360) // 90 in [0, 2]:
            fw, fh = w0, h0
        else:
            fw, fh = h0, w0  # switch w and h if rotation in [90, 270]

        return fw, fh

    @property
    def depth(self):
        return self._proxy.image_sizes[1]

    @property
    def bpp(self):
        return self._proxy.image_type

    @property
    def width(self):
        return self.roi[2]

    @property
    def height(self):
        return self.roi[3]

    @property
    def binning(self):
        return self._image_params.binning

    @binning.setter
    def binning(self, value):
        self._image_params.binning = value
        self._update_roi()

    @property
    def flip(self):
        return self._image_params.flip

    @flip.setter
    def flip(self, value):
        self._image_params.flip = value
        self._update_roi()

    @property
    def rotation(self):
        if self._image_params.rotation == "NONE":
            return 0
        else:
            return int(self._image_params.rotation)

    @rotation.setter
    def rotation(self, value):
        self._image_params.rotation = value
        self._update_roi()

    @property
    def raw_roi(self):
        # raw_roi is defined in the raw image referential (i.e with bin=1,1  flip=False,False, rot=0)
        # roi is defined in the current image referential (i.e roi = f(rot, flip, bin))

        # handle lazy init
        if self._raw_roi is None:
            _roi = self._image_params._roi

            # # handle the default raw_roi = [0,0,0,0]
            if _roi[2] == 0 or _roi[3] == 0:
                w0, h0 = self._get_detector_max_size()
                if _roi[2] == 0:
                    _roi[2] = w0
                if _roi[3] == 0:
                    _roi[3] = h0
                self._image_params._roi = _roi

            self._raw_roi = _roi

        return self._raw_roi

    @property
    def roi(self):
        # roi is defined in the current image referential (i.e roi = f(rot, flip, bin))
        # raw_roi is defined in the raw image referential (i.e with bin=1,1  flip=False,False, rot=0)

        # handle lazy init
        if self._cur_roi is None:
            self._update_roi()

        return self._cur_roi

    @roi.setter
    def roi(self, value):
        roi = self._check_roi_validity(value)
        self._raw_roi = self._calc_raw_roi(roi)  # computes the new _raw_roi
        self._image_params._roi = (
            self._raw_roi
        )  # store the new _raw_roi in redis/settings
        self._cur_roi = roi

        self._counter_controller._update_lima_rois()

    @property
    def subarea(self):
        """ Returns the active area of the detector (like 'roi').
            The rectangular area is defined by the top-left corner and bottom-right corner positions.
            Example: subarea = [x0, y0, x1, y1] 
        """
        x, y, w, h = self.roi
        return [x, y, x + w, y + h]

    @subarea.setter
    def subarea(self, value):
        """ Define a reduced active area on the detector chip (like 'roi').
            The rectangular area is defined by the top-left corner and bottom-right corner positions.
            Example: subarea = [x0, y0, x1, y1] 
        """
        px0, py0, px1, py1 = value
        x0 = min(px0, px1)
        x1 = max(px0, px1)
        y0 = min(py0, py1)
        y1 = max(py0, py1)
        w = x1 - x0
        h = y1 - y0
        self.roi = [x0, y0, w, h]

    def _update_roi(self, update_dependencies=True):
        detector_size = self._get_detector_max_size()
        self._cur_roi = raw_roi_to_current_roi(
            self.raw_roi, detector_size, self.flip, self.rotation, self.binning
        )
        if update_dependencies:
            self._counter_controller._update_lima_rois()

    def _calc_raw_roi(self, roi):
        """ computes the raw_roi from a given roi and current bin, flip, rot """

        img_size = self.fullsize  #!!!! NOT _get_detector_max_size() !!!
        return current_roi_to_raw_roi(
            roi, img_size, self.flip, self.rotation, self.binning
        )

    def _read_detector_max_size(self):
        log_debug(self, "get proxy.max_size")
        w, h = self._proxy.image_max_dim
        return int(w), int(h)

    def _get_detector_max_size(self):
        """read and return the detector size (raw value without considering binning and rotation) """

        if self._max_width == 0 or self._max_height == 0:
            self._max_width, self._max_height = self._read_detector_max_size()

            if self._max_width == 0 or self._max_height == 0:
                raise RuntimeError("There is a problem with the device server!")

        return self._max_width, self._max_height

    def _check_roi_validity(self, roi):
        """ check if the roi coordinates are valid, else trim the roi to fits image size """

        w0, h0 = self.fullsize
        x, y, w, h = roi

        if w == 0:
            w = w0

        if h == 0:
            h = h0

        # bx = x < 0 or x >= w0
        # by = y < 0 or y >= h0
        # bw = w < 1 or (x + w) > w0
        # bh = h < 1 or (y + h) > h0

        # if bx or by or bw or bh:
        #     raise ValueError(
        #         f"the given roi {roi} is not fitting the current image size {(w0, h0)}"
        #     )

        # --- In case we don t want to raise an error
        # --- we can just trim the roi so that it fits the current image size
        x = max(x, 0)
        x = min(x, w0 - 1)
        y = max(y, 0)
        y = min(y, h0 - 1)
        w = max(w, 1)
        w = min(w, w0 - x)
        h = max(h, 1)
        h = min(h, h0 - y)

        return [int(x), int(y), int(w), int(h)]

    def to_dict(self):
        return {
            "image_bin": self.binning,
            "image_flip": self.flip,
            "image_rotation": self._image_params.rotation,  # as str (to apply to proxy)
            "image_roi": self.roi,
        }

    def get_geometry(self):
        w, h = self.fullsize
        return {
            "fullwidth": w,
            "fullheight": h,
            "binning": self.binning,
            "flip": self.flip,
            "rotation": self.rotation,
            "roi": self.roi,
        }

    def set_geometry(self, binning, flip, rotation, roi=None):

        self._image_params.binning = binning
        self._image_params.flip = flip
        self._image_params.rotation = rotation
        if roi is None:
            self._update_roi()
        else:
            self._update_roi(update_dependencies=False)
            self.roi = roi

    def update_max_size(self):
        """ Update the image maximum size (reading the device proxy) 
            and reset the ROI to the new full frame.
        """
        w, h = self._read_detector_max_size()
        if (w, h) != (self._max_width, self._max_height):
            self._max_width, self._max_height = w, h
            self.roi = 0, 0, 0, 0  # reset roi to full frame
            # but keep current rotation, binning, flipping
