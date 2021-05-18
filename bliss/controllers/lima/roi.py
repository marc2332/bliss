# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import enum
import itertools
import numpy

from bliss.config import settings
from bliss.common.logtools import log_exception, user_print
from bliss.common.tango import DevFailed
from bliss.common.counter import IntegratingCounter
from bliss.controllers.counter import IntegratingCounterController
from bliss.controllers.counter import counter_namespace
from bliss.controllers.lima.image import raw_roi_to_current_roi, current_roi_to_raw_roi
from bliss.controllers.lima.image import (
    current_coords_to_raw_coords,
    raw_coords_to_current_coords,
)
from bliss.controllers.lima.image import _DEG2RAD
from bliss.scanning.acquisition.lima import RoiProfileAcquisitionSlave
from bliss.shell.formatters.table import IncrementalTable


class ROI_PROFILE_MODES(str, enum.Enum):
    horizontal = "LINES_SUM"
    vertical = "COLUMN_SUM"


_PMODE_ALIASES = {
    "horizontal": ROI_PROFILE_MODES.horizontal,
    "h": ROI_PROFILE_MODES.horizontal,
    0: ROI_PROFILE_MODES.horizontal,
    "vertical": ROI_PROFILE_MODES.vertical,
    "v": ROI_PROFILE_MODES.vertical,
    1: ROI_PROFILE_MODES.vertical,
}

# ============ ROI ===========


class _BaseRoi:
    def __init__(self, name=None):
        self.name = name
        self.check_validity()

    def check_validity(self):
        raise NotImplementedError

    def __repr__(self):
        raise NotImplementedError

    def __eq__(self, other):
        raise NotImplementedError

    def get_coords(self):
        raise NotImplementedError

    def get_points(self):
        raise NotImplementedError

    def to_array(self):
        return numpy.array(self.get_coords())

    def to_dict(self):
        raise NotImplementedError


class Roi(_BaseRoi):
    def __init__(self, x, y, width, height, name=None):

        self.x = int(x)
        self.y = int(y)
        self.width = int(width)
        self.height = int(height)

        super().__init__(name)

    @property
    def p0(self):
        return (self.x, self.y)

    @property
    def p1(self):
        return (self.x + self.width, self.y + self.height)

    def check_validity(self):
        if self.width <= 0:
            raise ValueError(f"Roi {self.name}: width must be > 0, not {self.width}")

        if self.height <= 0:
            raise ValueError(f"Roi {self.name}: height must be > 0, not {self.height}")

    def __repr__(self):
        return "<%s,%s> <%s x %s>" % (self.x, self.y, self.width, self.height)

    def __eq__(self, other):
        if other.__class__ != self.__class__:
            return False
        ans = self.x == other.x and self.y == other.y
        ans = ans and self.width == other.width and self.height == other.height
        ans = ans and self.name == other.name
        return ans

    def get_coords(self):
        return [self.x, self.y, self.width, self.height]

    def get_points(self):
        """ return the coordinates of the top-left and bottom-right corners as a list of points """
        return [self.p0, self.p1]

    def to_dict(self):
        return {
            "kind": "rect",
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }


class ArcRoi(_BaseRoi):
    """ Arc roi defined by coordinates: [center_x, center_y, radius_min, radius_max, angle_min, angle_max]
        Angles are expressed in degrees.
    """

    def __init__(self, cx, cy, r1, r2, a1, a2, name=None):

        self.cx = cx
        self.cy = cy
        self.r1 = r1
        self.r2 = r2
        self.a1 = a1
        self.a2 = a2

        super().__init__(name)

    def check_validity(self):
        if self.r1 < 0:
            raise ValueError(
                f"ArcRoi {self.name}: first radius must be >= 0, not {self.r1}"
            )

        if self.r2 < self.r1:
            raise ValueError(
                f"ArcRoi {self.name}: second radius must be >= first radius, not {self.r2}"
            )

        if self.a1 == self.a2:
            raise ValueError(
                f"ArcRoi {self.name}: first and second angles must be different"
            )

    def __repr__(self):
        return "<%.1f, %.1f> <%.1f, %.1f> <%.1f, %.1f>" % (
            self.cx,
            self.cy,
            self.r1,
            self.r2,
            self.a1,
            self.a2,
        )

    def __eq__(self, other):
        if other.__class__ != self.__class__:
            return False
        ans = self.cx == other.cx and self.cy == other.cy
        ans = ans and self.r1 == other.r1 and self.r2 == other.r2
        ans = ans and self.a1 == other.a1 and self.a2 == other.a2
        ans = ans and self.name == other.name
        return ans

    def get_coords(self):
        return [self.cx, self.cy, self.r1, self.r2, self.a1, self.a2]

    def get_points(self):
        """ return the coordinates of the typical points of the arc region """

        cx, cy, r1, r2, a1, a2 = self.get_coords()
        a3 = a1 + (a2 - a1) / 2
        pts = [[cx, cy]]

        ca1, ca2, ca3 = (
            numpy.cos(_DEG2RAD * a1),
            numpy.cos(_DEG2RAD * a2),
            numpy.cos(_DEG2RAD * a3),
        )
        sa1, sa2, sa3 = (
            numpy.sin(_DEG2RAD * a1),
            numpy.sin(_DEG2RAD * a2),
            numpy.sin(_DEG2RAD * a3),
        )

        pts.append([r1 * ca1 + cx, r1 * sa1 + cy])  # p1 => (r1, a1)
        pts.append([r2 * ca1 + cx, r2 * sa1 + cy])  # p2 => (r2, a1)
        pts.append([r2 * ca2 + cx, r2 * sa2 + cy])  # p3 => (r2, a2)
        pts.append([r1 * ca2 + cx, r1 * sa2 + cy])  # p4 => (r1, a2)
        pts.append([r2 * ca3 + cx, r2 * sa3 + cy])  # p5 => (r2, a1 + (a2 - a1) / 2)

        return pts

    def get_bounding_box(self):
        """ return the coordinates of rectangular box that surrounds the arc roi """
        pts = self.get_points()
        pts = numpy.array(pts[0:])  # exclude center p0
        x0 = numpy.amin(pts[:, 0])
        y0 = numpy.amin(pts[:, 1])
        x1 = numpy.amax(pts[:, 0])
        y1 = numpy.amax(pts[:, 1])
        return [[x0, y0], [x1, y1]]

    def to_dict(self):
        return {
            "kind": "arc",
            "cx": self.cx,
            "cy": self.cy,
            "r1": self.r1,
            "r2": self.r2,
            "a1": self.a1,
            "a2": self.a2,
        }


class RoiProfile(Roi):
    def __init__(self, x, y, width, height, mode="horizontal", name=None):

        self.profile_mode = mode

        super().__init__(x, y, width, height, name)

    @property
    def profile_mode(self):
        return self.mode

    @profile_mode.setter
    def profile_mode(self, mode):
        if mode not in _PMODE_ALIASES.keys():
            raise ValueError(f"the mode should be in {_PMODE_ALIASES.keys()}")

        self.mode = _PMODE_ALIASES[mode].name

    def __repr__(self):
        return "<%s,%s> <%s x %s> <%s>" % (
            self.x,
            self.y,
            self.width,
            self.height,
            self.mode,
        )

    def __eq__(self, other):
        if other.__class__ != self.__class__:
            return False
        ans = self.x == other.x and self.y == other.y
        ans = ans and self.width == other.width and self.height == other.height
        ans = ans and self.name == other.name
        ans = ans and self.mode == other.mode
        return ans

    def to_dict(self):
        return {
            "kind": "profile",
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "mode": self.mode,
        }


def dict_to_roi(dico: dict) -> _BaseRoi:
    """Convert a dictionary generated by `_BaseRoi.to_dict()` into an object ROI

    Argument:
        dico: Description of a ROI as a flat dictionary

    Raises:
        ValueError: If the dictionary do not represent a ROI
    """
    roiClasses = {"rect": Roi, "arc": ArcRoi, "profile": RoiProfile}

    # Do not edit the base object
    dico = dict(dico)

    try:
        kind = dico.pop("kind")
    except KeyError:
        raise ValueError("ROI kind is expected")

    roiClass = roiClasses.get(kind)
    if roiClass is None:
        raise ValueError("Unknown ROI kind '%s'" % kind)

    try:
        roi = roiClass(**dico)
    except Exception as e:
        raise ValueError("Wrong ROI dictionary") from e
    return roi


def coords_to_arc(coords):
    cx, cy = coords[0]
    x1, y1 = coords[1]
    x3, y3 = coords[2]

    a1 = numpy.arctan2((y1 - cy), (x1 - cx)) / _DEG2RAD
    a2 = numpy.arctan2((y3 - cy), (x3 - cx)) / _DEG2RAD

    r1 = numpy.sqrt((x1 - cx) ** 2 + (y1 - cy) ** 2)
    r2 = numpy.sqrt((x3 - cx) ** 2 + (y3 - cy) ** 2)

    return [cx, cy, r1, r2, a1, a2]


# ============ ROI COUNTERS ===========


class RoiStat(enum.IntEnum):
    Id = 0
    Frame = 1
    Sum = 2
    Avg = 3
    Std = 4
    Min = 5
    Max = 6


class RoiStatCounter(IntegratingCounter):
    """ A Counter object used for the statitics counters associated to one Roi """

    def __init__(self, roi_name, stat, **kwargs):
        self.roi_name = roi_name
        self.stat = stat
        name = f"{self.roi_name}_{stat.name.lower()}"
        super().__init__(name, kwargs.pop("controller"), **kwargs)

    def get_metadata(self):
        return {self.roi_name: self._counter_controller.get(self.roi_name).to_dict()}

    def __int__(self):
        # counter statistic ID = roi_id | statistic_id
        # it is calculated everty time because the roi id for a given roi name might
        # change if rois are added/removed from lima
        roi_id = self._counter_controller._roi_ids[self.roi_name]
        return self.roi_stat_id(roi_id, self.stat).item()

    @staticmethod
    def roi_stat_id(roi_id, stat):
        return (roi_id << 8) | stat


class SingleRoiCounters:
    """ an iterable container (associated to one roi.name) that yield the RoiStatCounters """

    def __init__(self, name, **keys):
        self.name = name
        self._sum = RoiStatCounter(name, RoiStat.Sum, **keys)
        self._avg = RoiStatCounter(name, RoiStat.Avg, **keys)
        self._std = RoiStatCounter(name, RoiStat.Std, **keys)
        self._min = RoiStatCounter(name, RoiStat.Min, **keys)
        self._max = RoiStatCounter(name, RoiStat.Max, **keys)

    @property
    def sum(self):
        return self._sum

    @property
    def avg(self):
        return self._avg

    @property
    def std(self):
        return self._std

    @property
    def min(self):
        return self._min

    @property
    def max(self):
        return self._max

    def __iter__(self):
        yield self.sum
        yield self.avg
        yield self.std
        yield self.min
        yield self.max


class RoiProfileCounter(IntegratingCounter):
    def __init__(self, roi_name, controller, conversion_function=None, unit=None):
        self.roi_name = roi_name
        super().__init__(roi_name, controller, conversion_function, unit)

    def get_metadata(self):
        return {self.roi_name: self._counter_controller.get(self.roi_name).to_dict()}

    @property
    def dtype(self):
        """The data type as used by numpy."""
        return numpy.uint32

    @property
    def shape(self):
        """The data shape as used by numpy."""

        roi = self._counter_controller._save_rois[self.name]

        if roi.mode == ROI_PROFILE_MODES.horizontal.name:
            shape = (roi.width,)
        elif roi.mode == ROI_PROFILE_MODES.vertical.name:
            shape = (roi.height,)

        return shape


class RoiCollectionCounter(IntegratingCounter):
    """ A Counter object used for a collection of Rois """

    def __init__(self, name, controller):
        super().__init__(name, controller)

    def get_metadata(self):
        coords = [roi.get_coords() for roi in self._counter_controller.get_rois()]
        xs, ys, ws, hs = zip(*coords)
        meta = {"kind": "collection", "x": xs, "y": ys, "width": ws, "height": hs}
        return {self.name: meta}

    @property
    def shape(self):
        """The data shape as used by numpy."""
        return (len(self._counter_controller),)

    @property
    def dtype(self):
        """The data type as used by numpy."""
        return numpy.int32


# ============ ROI COUNTER CONTROLLERS ===========


class RoiCounters(IntegratingCounterController):
    """ A CounterController to manage the roi_counters defined on a Lima camera.

        Each Roi object is associated to a SingleRoiCounter which yield the RoiStatCounters (like sum, avg, ...)

        Example usage:

        # add/replace a roi
        cam.roi_counters['r1'] = Roi(10, 10, 100, 200)
        cam.roi_counters['r1'] = (10, 10, 100, 200)

        # add/replace multiple rois
        cam.roi_counters['r2', 'r3'] = Roi(20, 20, 300, 400), Roi(20, 20, 300, 400)
        cam.roi_counters['r2', 'r3'] = (20, 20, 300, 400), (20, 20, 300, 400)

        # print roi info
        cam.roi_counters['r2']

        # return the roi object
        # !!! WARNING the instance is different at each call !!!
        # (use '==' instead of 'is' to check if 2 rois are the same )
        r2 = cam.roi_counters['r2']

        # return multiple roi objects
        r2, r1 = cam.roi_counters['r2', 'r1']

        # remove roi
        del cam.roi_counters['r1']

        # clear all rois
        cam.roi_counters.clear()

        # list roi names:
        cam.roi_counters.keys()

        # loop rois
        for roi_name, roi in cam.roi_counters.items():
            pass
    """

    def __init__(self, proxy, acquisition_proxy, name="roi_counters"):
        # leave counters registration to the parent object
        super().__init__(
            name, master_controller=acquisition_proxy, register_counters=False
        )
        self._proxy = proxy
        self._initialize()

    def _initialize(self):
        self._current_config = settings.SimpleSetting(
            self.fullname, default_value="default"
        )
        settings_name = "%s:%s" % (self.fullname, self._current_config.get())
        settings_name_raw_coords = "%s_raw_coords:%s" % (
            self.fullname,
            self._current_config.get(),
        )
        self._stored_raw_coodinates = settings.HashObjSetting(settings_name_raw_coords)
        self._save_rois = settings.HashObjSetting(settings_name)
        self._roi_ids = {}
        self.__cached_counters = {}
        self._needs_update = True  # a flag to indicates that rois must be refreshed

        # create counters from keys found in redis
        for name in self._stored_raw_coodinates.keys():
            self._create_single_roi_counters(name)

        self._restore_rois_from_settings()

    def get_acquisition_object(self, acq_params, ctrl_params, parent_acq_params):
        # avoid cyclic import
        from bliss.scanning.acquisition.lima import RoiCountersAcquisitionSlave

        # in case `count_time` is missing in acq_params take it from parent_acq_params
        if "acq_expo_time" in parent_acq_params:
            acq_params.setdefault("count_time", parent_acq_params["acq_expo_time"])
        if "acq_nb_frames" in parent_acq_params:
            acq_params.setdefault("npoints", parent_acq_params["acq_nb_frames"])

        return RoiCountersAcquisitionSlave(self, ctrl_params=ctrl_params, **acq_params)

    def _store_roi(self, roi):
        """ Transform roi coordinates to raw coordinates and store them as settings """

        img = self._master_controller.image

        if isinstance(roi, ArcRoi):
            pts = roi.get_points()
            pts = numpy.array([pts[0], pts[1], pts[3]])
            # take into account the offset of current image roi
            pts[:, 0] = pts[:, 0] + img.roi[0]
            pts[:, 1] = pts[:, 1] + img.roi[1]
            raw_coords = current_coords_to_raw_coords(
                pts, img.fullsize, img.flip, img.rotation, img.binning
            )
        elif isinstance(roi, Roi):
            coords = roi.get_coords()
            # take into account the offset of current image roi
            coords[0] = coords[0] + img.roi[0]
            coords[1] = coords[1] + img.roi[1]
            raw_coords = current_roi_to_raw_roi(
                coords, img.fullsize, img.flip, img.rotation, img.binning
            )

        else:
            raise ValueError(f"Unknown roi type {type(roi)}")

        self._stored_raw_coodinates[roi.name] = raw_coords
        self._save_rois[roi.name] = roi

    def _restore_rois_from_settings(self):

        user_print("updating roi counters...")

        img = self._master_controller.image
        for name in self._stored_raw_coodinates.keys():
            raw_coords = self._stored_raw_coodinates[name]
            if len(raw_coords) == 4:
                coords = raw_roi_to_current_roi(
                    raw_coords,
                    img._get_detector_max_size(),
                    img.flip,
                    img.rotation,
                    img.binning,
                )
                coords[0] = coords[0] - img.roi[0]
                coords[1] = coords[1] - img.roi[1]
                roi = Roi(*coords, name=name)
            else:

                coords = raw_coords_to_current_coords(
                    raw_coords,
                    img._get_detector_max_size(),
                    img.flip,
                    img.rotation,
                    img.binning,
                )
                coords = coords_to_arc(list(coords))
                coords[0] = coords[0] - img.roi[0]
                coords[1] = coords[1] - img.roi[1]
                roi = ArcRoi(*coords, name=name)

            if self._check_roi_validity(roi):
                self._save_rois[name] = roi
                self._activate_single_roi_counters(name)

            else:
                user_print(
                    f"Roi {roi.name} has been temporarily deactivated (outside image)"
                )  # {roi.get_coords()}
                del self._save_rois[name]
                self._deactivate_single_roi_counters(name)

        self._needs_update = False

    def _check_roi_name_is_unique(self, name):
        if name in self._master_controller.roi_profiles._save_rois:
            raise ValueError(
                f"Names conflict: '{name}' is already used by a roi_profile, please use another name"
            )

        if self._master_controller.roi_collection is not None:
            if name in self._master_controller.roi_collection._save_rois:
                raise ValueError(
                    f"Names conflict: '{name}' is already used in roi_collection, please use another name"
                )

    def _check_roi_validity(self, roi):

        x0, y0, w0, h0 = self._master_controller.image.roi

        if isinstance(roi, Roi):
            x, y, w, h = roi.get_coords()
            if x < 0 or x >= w0 or y < 0 or y >= h0:
                return False
            if (x + w) > w0 or (y + h) > h0:
                return False
            return True

        elif isinstance(roi, ArcRoi):
            # pts = roi.get_bounding_box() # This returns a bounding box around the arc roi (would be more accurate than next line but would prevent portion of the arc to be off image)
            pts = roi.get_points()[
                1:5
            ]  # Lima only checks if the corners of the arc roi are in image (i.e only checks p1, p2, p3, p4) so part of the roi could be out of image.
            x0, y0 = pts[0]
            x1, y1 = pts[1]

            if x0 < 0 or x0 >= w0:
                return False

            if y0 < 0 or y0 >= h0:
                return False

            if x1 < 0 or x1 > w0:
                return False

            if y1 < 0 or y1 > h0:
                return False

            return True

        else:
            raise NotImplementedError

    def _set_roi(self, name, roi_values):

        self._check_roi_name_is_unique(name)

        if roi_values.__class__ in [
            Roi,
            ArcRoi,
        ]:  # we don t want others like RoiProfile
            roi = roi_values
            roi.name = name
        elif len(roi_values) == 4:
            roi = Roi(*roi_values, name=name)
        elif len(roi_values) == 6:
            roi = ArcRoi(*roi_values, name=name)
        else:
            raise TypeError(
                "Lima.RoiCounters: accepts Roi or ArcRoi objects"
                " or (x, y, width, height) values"
                " or (cx, cy, r1, r2, a1, a2) values"
            )

        if not self._check_roi_validity(roi):
            raise ValueError(
                f"Roi coordinates {roi.get_coords()} are not valid (outside image)"
            )

        self._store_roi(roi)
        self._create_single_roi_counters(roi.name)

    def _remove_rois(self, names):
        # rois pushed on proxy have an entry in self._roi_ids
        on_proxy = []
        for name in names:
            del self._save_rois[name]
            del self._stored_raw_coodinates[name]
            self._remove_single_roi_counters(name)
            if name in self._roi_ids:
                on_proxy.append(name)
                del self._roi_ids[name]
        if on_proxy:
            self._proxy.removeRois(on_proxy)

    def _create_single_roi_counters(self, roiname):
        """ Create the multiple counters associated to one roi """
        self.__cached_counters[roiname] = SingleRoiCounters(roiname, controller=self)

    def _get_single_roi_counters(self, roiname):
        """ Return the multiple counters associated to one roi as an iterator """
        return self.__cached_counters[roiname]

    def _activate_single_roi_counters(self, roiname):
        for cnt in self.__cached_counters[roiname]:
            self._counters[cnt.name] = cnt

    def _deactivate_single_roi_counters(self, roiname):
        keys = list(self._counters.keys())
        for k in keys:
            if k.startswith(roiname):
                del self._counters[k]

    def _remove_single_roi_counters(self, roiname):
        self._deactivate_single_roi_counters(roiname)
        del self.__cached_counters[roiname]

    def set(self, name, roi_values):
        """alias to: <lima obj>.roi_counters[name] = roi_values"""
        self[name] = roi_values

    def get_rois(self):
        """alias to values()"""
        cache = self._save_rois
        return [cache[name] for name in sorted(cache.keys())]  # ??? sorted ???

    def remove(self, name):
        """alias to: del <lima obj>.roi_counters[name]"""
        # calls _remove_rois
        del self[name]

    def get_saved_config_names(self):
        return list(settings.scan(match="%s:*" % self.name))

    @property
    def config_name(self):
        return self._current_config.get()

    @config_name.setter
    def config_name(self, name):
        self._current_config.set(name)
        self._save_rois = settings.HashObjSetting(
            "%s:%s" % (self.name, name)
        )  # ??? self.name or self.fullname (see settings_name in __init__)???

    def upload_rois(self):
        if self._needs_update:
            self._restore_rois_from_settings()

        roi_list = [roi for roi in self.get_rois()]
        roi_id_list = self._proxy.addNames([x.name for x in roi_list])

        rois_values = list()
        arcrois_values = list()
        for roi_id, roi in zip(roi_id_list, roi_list):
            if roi.__class__ == Roi:
                rois_values.extend([roi_id])
                rois_values.extend(roi.get_coords())
            elif roi.__class__ == ArcRoi:
                arcrois_values.extend([roi_id])
                arcrois_values.extend(roi.get_coords())
            self._roi_ids[roi.name] = roi_id

        if rois_values or arcrois_values:
            # --- just before calling upload_rois the RoiCountersAcquisitionSlave calls:
            # self._proxy.clearAllRois()
            # self._proxy.start()          # after the clearAllRois (unlike 'roi2spectrum' proxy)!

            if rois_values:
                self._proxy.setRois(rois_values)

            if arcrois_values:
                self._proxy.setArcRois(arcrois_values)

    # dict like API

    def get(self, name, default=None):
        return self._save_rois.get(name, default=default)

    def __getitem__(self, names):
        if isinstance(names, str):
            return self._save_rois[names]
        else:
            return [self[name] for name in names]

    def __setitem__(self, names, rois):
        if isinstance(names, str):
            self._set_roi(names, rois)
        else:
            for name, value in zip(names, rois):
                self[name] = value

    def __delitem__(self, names):
        if isinstance(names, str):
            names = (names,)
        self._remove_rois(names)

    def __contains__(self, name):
        return name in self._save_rois

    def __len__(self):
        return len(self._save_rois)

    def clear(self):
        self._remove_rois(self._save_rois.keys())

    def keys(self):
        return self._save_rois.keys()

    def values(self):
        return self._save_rois.values()

    def items(self):
        return self._save_rois.items()

    def has_key(self, name):
        return name in self._save_rois

    def update(self, rois):
        for name, roi in rois.items():
            self[name] = roi

    def __info__(self):
        header = f"ROI Counters: {self.config_name}"
        rois = self.get_rois()
        if rois:
            labels = ["Name", "ROI coordinates"]
            tab = IncrementalTable([labels])
            [tab.add_line([roi.name, str(roi)]) for roi in rois if roi.__class__ == Roi]
            [
                tab.add_line([roi.name, str(roi)])
                for roi in rois
                if roi.__class__ == ArcRoi
            ]
            tab.resize(minwidth=10, maxwidth=100)
            tab.add_separator(sep="-", line_index=1)
            return "\n".join([header, str(tab)])

        else:
            return "\n".join([header, "*** no ROIs defined ***"])

    # Counter access

    def iter_single_roi_counters(self):
        for roi in self.get_rois():
            yield self._get_single_roi_counters(roi.name)

    @property
    def counters(self):
        return counter_namespace(itertools.chain(*self.iter_single_roi_counters()))

    @property
    def buffer_size(self):
        return self._proxy.BufferSize

    @buffer_size.setter
    def buffer_size(self, value):
        self._proxy.BufferSize = int(value)

    @property
    def mask_file(self):
        filename = self._proxy.MaskFile
        if not len(filename):
            return None
        else:
            return filename

    @mask_file.setter
    def mask_file(self, filename):
        if filename is None:
            self._proxy.MaskFile = ""
        else:
            self._proxy.MaskFile = filename

    def get_values(self, from_index, *counters):
        roi_counter_size = len(RoiStat)
        try:
            raw_data = self._proxy.readCounters(from_index)
        except DevFailed:
            log_exception(
                self, "Cannot read counters from Lima device %s", self._proxy.dev_name()
            )
            return [numpy.array([-1])] * len(counters)
        if not raw_data.size:
            return len(counters) * (numpy.array(()),)
        raw_data.shape = (raw_data.size) // roi_counter_size, roi_counter_size
        result = dict([int(counter), []] for counter in counters)

        for roi_counter in raw_data:
            roi_id = int(roi_counter[0])
            for stat in range(roi_counter_size):
                full_id = RoiStatCounter.roi_stat_id(roi_id, stat)
                counter_data = result.get(full_id)
                if counter_data is not None:
                    counter_data.append(roi_counter[stat])
        return list(map(numpy.array, result.values()))


class RoiProfileController(IntegratingCounterController):
    """
        A CounterController to manage Lima RoiProfileCounters

        Example usage:

        # add/replace a roi
        cam.roi_profiles['r1'] = Roi(10, 10, 100, 200)
        cam.roi_profiles['r1'] = (10, 10, 100, 200)

        # add/replace multiple rois
        cam.roi_profiles['r2', 'r3'] = Roi(20, 20, 300, 400), Roi(20, 20, 300, 400)
        cam.roi_profiles['r2', 'r3'] = (20, 20, 300, 400), (20, 20, 300, 400)

        # print roi info
        cam.roi_profiles['r2']

        # return the roi object
        # !!! WARNING the instance is different at each call !!!
        # (use '==' instead of 'is' to check if 2 rois are the same )
        r2 = cam.roi_profiles['r2']

        # return multiple roi objects
        r2, r1 = cam.roi_profiles['r2', 'r1']

        # remove roi
        del cam.roi_profiles['r1']

        # clear all rois
        cam.roi_profiles.clear()

        # list roi names:
        cam.roi_profiles.keys()

        # loop rois
        for roi_name, roi in cam.roi_profiles.items():
            pass
    """

    def __init__(self, proxy, acquisition_proxy, name="roi_profiles"):
        # leave counters registration to the parent object
        super().__init__(
            name, master_controller=acquisition_proxy, register_counters=False
        )
        self._proxy = proxy
        self._initialize()

    def _initialize(self):
        self._current_config = settings.SimpleSetting(
            self.fullname, default_value="default"
        )
        settings_name = "%s:%s" % (self.fullname, self._current_config.get())
        settings_name_raw_coords = "%s_raw_coords:%s" % (
            self.fullname,
            self._current_config.get(),
        )
        self._roi_ids = {}
        self.__cached_counters = {}
        self._save_rois = settings.HashObjSetting(settings_name)
        self._stored_raw_coodinates = settings.HashObjSetting(settings_name_raw_coords)
        self._needs_update = True  # a flag to indicates that rois must be refreshed

        # create counters from keys found in redis
        for name in self._stored_raw_coodinates.keys():
            self._create_roi_profile_counter(name)

        self._restore_rois_from_settings()

    def get_acquisition_object(self, acq_params, ctrl_params, parent_acq_params):
        # in case `count_time` is missing in acq_params take it from parent_acq_params
        if "acq_expo_time" in parent_acq_params:
            acq_params.setdefault("count_time", parent_acq_params["acq_expo_time"])
        if "acq_nb_frames" in parent_acq_params:
            acq_params.setdefault("npoints", parent_acq_params["acq_nb_frames"])

        return RoiProfileAcquisitionSlave(self, ctrl_params=ctrl_params, **acq_params)

    def _store_roi(self, roi):
        """ Transform roi coordinates to raw coordinates and store them as settings """

        img = self._master_controller.image

        if isinstance(roi, RoiProfile):
            coords = roi.get_coords()
            # take into account the offset of current image roi
            coords[0] = coords[0] + img.roi[0]
            coords[1] = coords[1] + img.roi[1]
            raw_coords = current_roi_to_raw_roi(
                coords, img.fullsize, img.flip, img.rotation, img.binning
            )

        else:
            raise ValueError(f"Unknown roi type {type(roi)}")

        raw_coords.append(roi.profile_mode)
        self._stored_raw_coodinates[roi.name] = raw_coords
        self._save_rois[roi.name] = roi

    def _restore_rois_from_settings(self):

        user_print("updating roi profiles...")

        img = self._master_controller.image
        for name in self._stored_raw_coodinates.keys():
            raw_coords = self._stored_raw_coodinates[name]
            profile_mode = raw_coords.pop()
            if len(raw_coords) == 4:
                coords = raw_roi_to_current_roi(
                    raw_coords,
                    img._get_detector_max_size(),
                    img.flip,
                    img.rotation,
                    img.binning,
                )
                coords[0] = coords[0] - img.roi[0]
                coords[1] = coords[1] - img.roi[1]

                roi = RoiProfile(*coords, profile_mode, name=name)

            if self._check_roi_validity(roi):
                self._save_rois[name] = roi
                self._activate_roi_profile_counter(name)

            else:
                user_print(
                    f"RoiProfile {roi.name} has been temporarily deactivated (outside image)"
                )  # {roi.get_coords()}
                del self._save_rois[name]
                self._deactivate_roi_profile_counter(name)

        self._needs_update = False

    def _check_roi_name_is_unique(self, name):
        if name in self._master_controller.roi_counters._save_rois:
            raise ValueError(
                f"Names conflict: '{name}' is already used by a roi_counter, please use another name"
            )

        if self._master_controller.roi_collection is not None:
            if name in self._master_controller.roi_collection._save_rois:
                raise ValueError(
                    f"Names conflict: '{name}' is already used in roi_collection, please use another name"
                )

    def _check_roi_validity(self, roi):

        x0, y0, w0, h0 = self._master_controller.image.roi

        if isinstance(roi, RoiProfile):
            x, y, w, h = roi.get_coords()
            if x < 0 or x >= w0 or y < 0 or y >= h0:
                return False
            if (x + w) > w0 or (y + h) > h0:
                return False
            return True

        else:
            raise NotImplementedError

    def _set_roi(self, name, roi_values):

        self._check_roi_name_is_unique(name)

        if roi_values.__class__ == RoiProfile:
            roi = roi_values
            roi.name = name
        elif len(roi_values) in [4, 5]:
            roi = RoiProfile(*roi_values, name=name)
        else:
            raise TypeError(
                "Expect a RoiProfile object"
                " or (x, y, width, height) values"
                f" or (x, y, width, height, mode) values with mode in {_PMODE_ALIASES.keys()}"
            )

        if not self._check_roi_validity(roi):
            raise ValueError(
                f"Roi coordinates {roi.get_coords()} are not valid (outside image)"
            )

        self._store_roi(roi)
        self._create_roi_profile_counter(roi.name)

    def _remove_rois(self, names):
        # rois pushed on proxy have an entry in self._roi_ids
        on_proxy = []
        for name in names:
            del self._save_rois[name]
            del self._stored_raw_coodinates[name]
            self._remove_roi_profile_counter(name)
            if name in self._roi_ids:
                on_proxy.append(name)
                del self._roi_ids[name]
        if on_proxy:
            self._proxy.removeRois(on_proxy)

    def _create_roi_profile_counter(self, roiname):
        """ Create the RoiProfileCounter associated to one roi """
        self.__cached_counters[roiname] = RoiProfileCounter(roiname, controller=self)

    def _get_roi_profile_counter(self, roiname):
        """ Return the multiple counters associated to one roi as an iterator """
        return self.__cached_counters[roiname]

    def _activate_roi_profile_counter(self, roiname):
        cnt = self.__cached_counters[roiname]
        self._counters[cnt.name] = cnt

    def _deactivate_roi_profile_counter(self, roiname):
        self._counters.pop(roiname, None)

    def _remove_roi_profile_counter(self, roiname):
        self._deactivate_roi_profile_counter(roiname)
        del self.__cached_counters[roiname]

    def set_roi_mode(self, mode, *names):
        """ set the mode of all rois or for a list of given roi names.
            Args:
                mode = 'horizontal' or 'vertical'
                *names = roi names 
        """

        if not names:
            names = self._save_rois.keys()

        for name in names:
            roi = self._save_rois[name]
            roi.profile_mode = mode  # mode is checked here
            self._store_roi(roi)

    def get_roi_mode(self, *names):
        """get the mode (0: horizontal, 1:vertical) of all rois or for a list of given roi names"""

        if len(names) == 1:
            return self._save_rois[names[0]].mode
        elif not names:
            names = self._save_rois.keys()

        # ??? for multiple rois should it returns a dict or a list ???
        return {name: self._save_rois[name].mode for name in names}

    def get_rois(self):
        """alias to values()"""
        cache = self._save_rois
        return [cache[name] for name in sorted(cache.keys())]

    def remove(self, name):
        """alias to: del <lima obj>.roi_profiles[name]"""
        # calls _remove_rois
        del self[name]

    def get_saved_config_names(self):
        return list(settings.scan(match="%s:*" % self.name))

    @property
    def config_name(self):
        return self._current_config.get()

    @config_name.setter
    def config_name(self, name):
        self._current_config.set(name)
        self._save_rois = settings.HashObjSetting("%s:%s" % (self.name, name))

    def upload_rois(self):
        if self._needs_update:
            self._restore_rois_from_settings()

        roi_list = [roi for roi in self.get_rois()]
        roi_id_list = self._proxy.addNames([x.name for x in roi_list])

        rois_values = list()
        for roi_id, roi in zip(roi_id_list, roi_list):
            rois_values.append(roi_id)
            rois_values.extend(roi.get_coords())
            self._roi_ids[roi.name] = roi_id

        roi_modes = list()
        for roi in roi_list:
            roi_modes.append(roi.name)
            roi_modes.append(ROI_PROFILE_MODES[roi.mode].value)

        if rois_values:
            # --- just before calling upload_rois the RoiCountersAcquisitionSlave calls:
            # self._proxy.start()         # before the clear (unlike 'roicounter' proxy) !
            # self._proxy.clearAllRois()

            self._proxy.setRois(rois_values)
            self._proxy.setRoiModes(roi_modes)

    # dict like API

    def set(self, name, roi_values):
        """alias to: <lima obj>.roi_profiles[name] = roi_values"""
        self[name] = roi_values

    def get(self, name, default=None):
        return self._save_rois.get(name, default=default)

    def __getitem__(self, names):
        if isinstance(names, str):
            return self._save_rois[names]
        else:
            return [self[name] for name in names]

    def __setitem__(self, names, rois):
        if isinstance(names, str):
            self._set_roi(names, rois)
        else:
            for name, value in zip(names, rois):
                self[name] = value

    def __delitem__(self, names):
        if isinstance(names, str):
            names = (names,)
        self._remove_rois(names)

    def __contains__(self, name):
        return name in self._save_rois

    def __len__(self):
        return len(self._save_rois)

    def clear(self):
        self._remove_rois(self._save_rois.keys())

    def keys(self):
        return self._save_rois.keys()

    def values(self):
        return self._save_rois.values()

    def items(self):
        return self._save_rois.items()

    def has_key(self, name):
        return name in self._save_rois

    def update(self, rois):
        for name, roi in rois.items():
            self[name] = roi

    # Counter access

    def iter_roi_counters(self):
        for roi in self.get_rois():
            yield self._get_roi_profile_counter(roi.name)

    @property
    def counters(self):
        return counter_namespace(self.iter_roi_counters())

    # Representation

    def __info__(self):
        header = f"Roi Profile Counters: {self.config_name}"
        rois = self.get_rois()
        if rois:
            labels = ["Name", "<x, y> <w, h> <mode>"]
            tab = IncrementalTable([labels])
            [tab.add_line([roi.name, str(roi)]) for roi in rois]
            tab.resize(minwidth=10, maxwidth=100)
            tab.add_separator(sep="-", line_index=1)
            return "\n".join([header, str(tab)])

        else:
            return "\n".join([header, "*** no ROIs defined ***"])

    def get_values(self, from_index, *counters):
        # caution in the two next lines: in case we need a list of different list objects,
        # [[]]*len(counters) is not applicable
        blank = [[] for cnt in counters]
        profiles = [[] for cnt in counters]

        last_num_of_spec = None
        for i, cnt in enumerate(counters):
            size = cnt.shape[0]
            cid = self._roi_ids[cnt.name]
            try:
                spec = self._proxy.readImage([int(cid), int(from_index)])
            except DevFailed:
                log_exception(
                    self,
                    "Cannot read profile from Lima device %s",
                    self._proxy.dev_name(),
                )
                # do not return a blank list => put -1 values, to indicate
                # Lima reading failed, without stopping acquisition
                return [numpy.array([-1] * size)] * len(counters)

            if len(spec):
                num_of_spec = len(spec) // size

                if last_num_of_spec and num_of_spec != last_num_of_spec:
                    # Not the same number of ready frames per counter
                    # 'reading' won t accept that, so return blank
                    return blank

                # collect the spectrum per frames (j=>frame, i=>cnt)
                for j in range(num_of_spec):
                    profiles[i].append(list(spec[j * size : (j + 1) * size]))

                # remember the number of ready frames for that counter
                # to compare with next counter and return blank if different
                last_num_of_spec = num_of_spec

            else:
                # if no profiles ready yet for that counter then return
                # and let the 'reading' polling call this function again
                return blank

        return profiles


class RoiCollectionController(IntegratingCounterController):
    """ A CounterController to manage large number of rectangular rois defined on a Lima camera.
        This controller is based on the Lima RoiCollection plugin.
        All the rois are managed into a single 1D counter (RoiCollectionCounter).
        This unique counter ('roi_collection_counter') handle all the rois sums at once.
        Associated data is a 1D array with all rois sums (one value per roi).
        ex: sums = scan.get_data('*roi_collection_counter')[0,:]  (for frame 0).
    """

    def __init__(self, proxy, acquisition_proxy, name="roi_collection"):
        # leave counters registration to the parent object
        super().__init__(
            name, master_controller=acquisition_proxy, register_counters=False
        )
        self._proxy = proxy
        self._initialize()

    def _initialize(self):
        self._current_config = settings.SimpleSetting(
            self.fullname, default_value="default"
        )
        settings_name = "%s:%s" % (self.fullname, self._current_config.get())
        settings_name_raw_coords = "%s_raw_coords:%s" % (
            self.fullname,
            self._current_config.get(),
        )
        self._save_rois = settings.OrderedHashObjSetting(settings_name)
        self._stored_raw_coodinates = settings.HashObjSetting(settings_name_raw_coords)
        self._roi_ids = {}
        self._needs_update = True  # a flag to indicates that rois must be refreshed

        # create the unique counter that manages the collection of rois
        self.create_counter(RoiCollectionCounter, "roi_collection_counter")

        self._restore_rois_from_settings()

    def get_acquisition_object(self, acq_params, ctrl_params, parent_acq_params):
        # avoid cyclic import
        from bliss.scanning.acquisition.lima import RoiCountersAcquisitionSlave

        # in case `count_time` is missing in acq_params take it from parent_acq_params
        if "acq_expo_time" in parent_acq_params:
            acq_params.setdefault("count_time", parent_acq_params["acq_expo_time"])
        if "acq_nb_frames" in parent_acq_params:
            acq_params.setdefault("npoints", parent_acq_params["acq_nb_frames"])

        return RoiCountersAcquisitionSlave(self, ctrl_params=ctrl_params, **acq_params)

    def _store_roi(self, roi):
        """ Transform roi coordinates to raw coordinates and store them as settings """

        img = self._master_controller.image

        if isinstance(roi, Roi):
            coords = roi.get_coords()
            # take into account the offset of current image roi
            coords[0] = coords[0] + img.roi[0]
            coords[1] = coords[1] + img.roi[1]
            raw_coords = current_roi_to_raw_roi(
                coords, img.fullsize, img.flip, img.rotation, img.binning
            )

        else:
            raise ValueError(f"Unknown roi type {type(roi)}")

        self._stored_raw_coodinates[roi.name] = raw_coords
        self._save_rois[roi.name] = roi

    def _restore_rois_from_settings(self):

        user_print("updating rois collection...")
        disabled = []
        img = self._master_controller.image
        for name in self._stored_raw_coodinates.keys():
            raw_coords = self._stored_raw_coodinates[name]

            if len(raw_coords) == 4:
                coords = raw_roi_to_current_roi(
                    raw_coords,
                    img._get_detector_max_size(),
                    img.flip,
                    img.rotation,
                    img.binning,
                )
                coords[0] = coords[0] - img.roi[0]
                coords[1] = coords[1] - img.roi[1]

                roi = Roi(*coords, name=name)

            if self._check_roi_validity(roi):
                self._save_rois[name] = roi
            else:
                disabled.append(name)
                del self._save_rois[name]

        if disabled:
            user_print(
                f"Some rois have been temporarily deactivated (outside image): {disabled}"
            )
        self._needs_update = False

    def _check_roi_name_is_unique(self, name):
        if name in self._master_controller.roi_profiles._save_rois:
            raise ValueError(
                f"Names conflict: '{name}' is already used by a roi_profile, please use another name"
            )

        if name in self._master_controller.roi_counters._save_rois:
            raise ValueError(
                f"Names conflict: '{name}' is already used by a roi_counter, please use another name"
            )

    def _check_roi_validity(self, roi):

        x0, y0, w0, h0 = self._master_controller.image.roi

        if isinstance(roi, Roi):
            x, y, w, h = roi.get_coords()
            if x < 0 or x >= w0 or y < 0 or y >= h0:
                return False
            if (x + w) > w0 or (y + h) > h0:
                return False
            return True

        else:
            raise NotImplementedError

    def _set_roi(self, name, roi_values):

        self._check_roi_name_is_unique(name)

        if roi_values.__class__ in [
            Roi,
            # ArcRoi,    #exclude ArcRoi (because lima collection plugin doesn t handle them until now).
        ]:  # we don t want others like RoiProfile
            roi = roi_values
            roi.name = name
        elif len(roi_values) == 4:
            roi = Roi(*roi_values, name=name)
        else:
            raise TypeError(
                "Lima.RoiCollectionController: accepts Roi objects"
                " or (x, y, width, height) values"
                # " or (cx, cy, r1, r2, a1, a2) values"
            )

        self._store_roi(roi)

    def _remove_rois(self, names):
        # rois pushed on proxy have an entry in self._roi_ids
        on_proxy = []
        for name in names:
            del self._save_rois[name]
            del self._stored_raw_coodinates[name]
            if name in self._roi_ids:
                on_proxy.append(name)
                del self._roi_ids[name]
        if on_proxy:
            self._proxy.removeRois(on_proxy)

    def set(self, name, roi_values):
        """alias to: <lima obj>.roi_counters[name] = roi_values"""
        self[name] = roi_values

    def get_rois(self):
        """alias to values()"""
        cache = self._save_rois
        return [cache[name] for name in cache.keys()]

    def remove(self, name):
        """alias to: del <lima obj>.roi_counters[name]"""
        # calls _remove_rois
        del self[name]

    def get_saved_config_names(self):
        return list(settings.scan(match="%s:*" % self.name))

    @property
    def config_name(self):
        return self._current_config.get()

    @config_name.setter
    def config_name(self, name):
        self._current_config.set(name)
        settings_name = "%s:%s" % (self.fullname, name)
        self._save_rois = settings.OrderedHashObjSetting(settings_name)

    def upload_rois(self):
        if self._needs_update:
            self._restore_rois_from_settings()

        roicoords = []
        for roi in self.get_rois():
            roicoords.extend(roi.get_coords())

        if roicoords:
            self._proxy.setRois(roicoords)

    # dict like API

    def get(self, name, default=None):
        return self._save_rois.get(name, default=default)

    def __getitem__(self, names):
        if isinstance(names, str):
            return self._save_rois[names]
        else:
            return [self[name] for name in names]

    def __setitem__(self, names, rois):
        if isinstance(names, str):
            self._set_roi(names, rois)
        else:
            for name, value in zip(names, rois):
                self[name] = value

    def __delitem__(self, names):
        if isinstance(names, str):
            names = (names,)
        self._remove_rois(names)

    def __contains__(self, name):
        return name in self._save_rois

    def __len__(self):
        return len(self._save_rois)

    def clear(self):
        self._remove_rois(self._save_rois.keys())

    def keys(self):
        return self._save_rois.keys()

    def values(self):
        return self._save_rois.values()

    def items(self):
        return self._save_rois.items()

    def has_key(self, name):
        return name in self._save_rois

    def update(self, rois):
        for name, roi in rois.items():
            self[name] = roi

    def __info__(self):
        header = f"ROI Collection: {self.config_name}"
        nb_rois = len(self._save_rois)
        if nb_rois:
            txt = f"collection of {nb_rois} rois"
            return "\n".join([header, txt])
        else:
            return "\n".join([header, "*** no ROI defined ***"])

    def get_values(self, from_index, counter):
        numofroi = counter.shape[0]
        raw_data = self._proxy.readSpectrum(from_index)
        if raw_data.shape[0] > 0:
            numofspec, specsize, first_frame_id = list(raw_data[0:3])
            # assert specsize == numofroi
            # assert first_frame_id == from_index
            spectrums = raw_data[3:]
            spectrums.shape = (numofspec, numofroi)
            if numofspec > 0:
                return [spectrums]

        return [[]]

    @property
    def counters(self):
        if len(self._save_rois):
            return super().counters
        else:
            return counter_namespace([])
