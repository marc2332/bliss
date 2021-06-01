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

from bliss.scanning.acquisition.lima import RoiProfileAcquisitionSlave
from bliss.shell.formatters.table import IncrementalTable


# ============ ROI ===========
class _BaseRoi:
    def __init__(self, name=None):
        self._name = name
        self.check_validity()

    @property
    def name(self):
        return self._name

    def check_validity(self):
        raise NotImplementedError

    def __repr__(self):
        raise NotImplementedError

    def __eq__(self, other):
        raise NotImplementedError

    def get_params(self):
        """ return the list of parameters received at init """
        raise NotImplementedError

    def to_dict(self):
        """ return typical info as a dict """
        raise NotImplementedError


class Roi(_BaseRoi):
    def __init__(self, x, y, width, height, name=None):

        self._x = int(x)
        self._y = int(y)
        self._width = int(width)
        self._height = int(height)

        super().__init__(name)

        self._p0 = (self._x, self._y)
        self._p1 = (self._x + self._width, self._y + self._height)

    @property
    def x(self):
        return self._x

    @property
    def y(self):
        return self._y

    @property
    def width(self):
        return self._width

    @property
    def height(self):
        return self._height

    @property
    def p0(self):
        """ return coordinates of the top left corner """
        return self._p0

    @property
    def p1(self):
        """ return coordinates of the bottom right corner """
        return self._p1

    def check_validity(self):
        if self._width <= 0:
            raise ValueError(f"Roi {self.name}: width must be > 0, not {self._width}")

        if self._height <= 0:
            raise ValueError(f"Roi {self.name}: height must be > 0, not {self._height}")

    def __repr__(self):
        return "<%s,%s> <%s x %s>" % (self.x, self.y, self.width, self.height)

    def __eq__(self, other):
        if other.__class__ != self.__class__:
            return False
        ans = self.x == other.x and self.y == other.y
        ans = ans and self.width == other.width and self.height == other.height
        ans = ans and self.name == other.name
        return ans

    def get_params(self):
        """ return the list of parameters received at init """
        return [self.x, self.y, self.width, self.height]

    def to_dict(self):
        """ return typical info as a dict """
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

        self._cx = cx
        self._cy = cy
        self._r1 = r1
        self._r2 = r2
        self._a1 = a1
        self._a2 = a2

        super().__init__(name)

        self._a3 = a3 = (a1 + a2) / 2  # i.e: a3 = a1 + (a2-a1)/2
        self._aperture = abs(self.a2 - self.a1) / 2
        self._ratio = self.r1 / self.r2

        ca1, ca2, ca3 = (
            numpy.cos(numpy.deg2rad(a1)),
            numpy.cos(numpy.deg2rad(a2)),
            numpy.cos(numpy.deg2rad(a3)),
        )
        sa1, sa2, sa3 = (
            numpy.sin(numpy.deg2rad(a1)),
            numpy.sin(numpy.deg2rad(a2)),
            numpy.sin(numpy.deg2rad(a3)),
        )

        self._p0 = (cx, cy)
        self._p1 = (r1 * ca1 + cx, r1 * sa1 + cy)
        self._p2 = (r2 * ca1 + cx, r2 * sa1 + cy)
        self._p3 = (r2 * ca2 + cx, r2 * sa2 + cy)
        self._p4 = (r1 * ca2 + cx, r1 * sa2 + cy)
        self._p5 = (r2 * ca3 + cx, r2 * sa3 + cy)

    @property
    def cx(self):
        return self._cx

    @property
    def cy(self):
        return self._cy

    @property
    def r1(self):
        return self._r1

    @property
    def r2(self):
        return self._r2

    @property
    def a1(self):
        return self._a1

    @property
    def a2(self):
        return self._a2

    @property
    def a3(self):
        return self._a3

    @property
    def aperture(self):
        return self._aperture

    @property
    def ratio(self):
        return self._ratio

    @property
    def p0(self):
        """ return coordinates of the arc center """
        return self._p0

    @property
    def p1(self):
        """ return coordinates of the point at (r1, a1) """
        return self._p1

    @property
    def p2(self):
        """ return coordinates of the point at (r2, a1) """
        return self._p2

    @property
    def p3(self):
        """ return coordinates of the point at (r2, a2) """
        return self._p3

    @property
    def p4(self):
        """ return coordinates of the point at (r1, a2) """
        return self._p4

    @property
    def p5(self):
        """ return coordinates of the point at (r2, a1 + (a2 - a1) / 2) """
        return self._p5

    def check_validity(self):
        if self._r1 < 0:
            raise ValueError(
                f"ArcRoi {self.name}: first radius must be >= 0, not {self._r1}"
            )

        if self._r2 < self._r1:
            raise ValueError(
                f"ArcRoi {self.name}: second radius must be >= first radius, not {self._r2}"
            )

        if self._a1 == self._a2:
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

    def get_params(self):
        """ return the list of parameters received at init """
        return [self.cx, self.cy, self.r1, self.r2, self.a1, self.a2]

    def to_dict(self):
        """ return typical info as a dict """
        return {
            "kind": "arc",
            "cx": self.cx,
            "cy": self.cy,
            "r1": self.r1,
            "r2": self.r2,
            "a1": self.a1,
            "a2": self.a2,
        }

    def bounding_box(self):
        # get the 4 'corners' points
        pts = [self.p1, self.p2, self.p3, self.p4]

        # add extra points (intersection with X and Y axes)
        # force positive angles and a1 > a2 (so a2 could be greater than 360 and up to 540)
        a1 = self.a1 % 360
        a2 = self.a2 % 360
        if a2 < a1:
            a2 += 360
        for theta in [0, 90, 180, 270, 360, 450, 540]:
            if theta > a1 and theta < a2:
                px = self.r2 * numpy.cos(numpy.deg2rad(theta)) + self.cx
                py = self.r2 * numpy.sin(numpy.deg2rad(theta)) + self.cy
                pts.append([px, py])

        xmini = xmaxi = None
        ymini = ymaxi = None
        for (x, y) in pts:
            if xmini == None or x < xmini:
                xmini = x

            if ymini == None or y < ymini:
                ymini = y

            if xmaxi == None or x > xmaxi:
                xmaxi = x

            if ymaxi == None or y > ymaxi:
                ymaxi = y

        return [[xmini, ymini], [xmaxi, ymaxi]]


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


class RoiProfile(Roi):
    def __init__(self, x, y, width, height, mode="horizontal", name=None):

        self.mode = mode

        super().__init__(x, y, width, height, name)

    @property
    def mode_vector(self):
        """ returns the profile mode as a unitary vector """
        return self._mode_vector

    @property
    def mode(self):
        return self._mode.name

    @mode.setter
    def mode(self, mode):
        if mode not in _PMODE_ALIASES.keys():
            raise ValueError(f"the mode should be in {_PMODE_ALIASES.keys()}")

        self._mode = _PMODE_ALIASES[mode]

        if self._mode is ROI_PROFILE_MODES.horizontal:
            self._mode_vector = (1, 0)
        else:
            self._mode_vector = (0, 1)

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


def raw_params_to_arc_params(cx, cy, dx, dy, ratio, aperture):
    """ get the arc roi parameters from raw parameters
        args:
            cx, cy: coordinates of the arc center (p0)
            dx, dy: coordinates of the arc 'direction' vector (p5)
            ratio: radius ration r1/r2
            aperture: angular aperture of the arc (half angle)
    """
    theta = numpy.rad2deg(numpy.arctan2((dy - cy), (dx - cx))) % 360
    a1 = theta - aperture
    a2 = theta + aperture
    r2 = numpy.sqrt((dx - cx) ** 2 + (dy - cy) ** 2)
    r1 = r2 * ratio
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

    def scan_metadata(self):
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

    def scan_metadata(self):
        return {self.roi_name: self._counter_controller.get(self.roi_name).to_dict()}

    @property
    def dtype(self):
        """The data type as used by numpy."""
        return numpy.uint32

    @property
    def shape(self):
        """The data shape as used by numpy."""

        roi = self._counter_controller._active_rois[self.name]

        if roi._mode == ROI_PROFILE_MODES.horizontal:
            shape = (roi.width,)
        elif roi._mode == ROI_PROFILE_MODES.vertical:
            shape = (roi.height,)

        return shape


class RoiCollectionCounter(IntegratingCounter):
    """ A Counter object used for a collection of Rois """

    def __init__(self, name, controller):
        super().__init__(name, controller)

    def scan_metadata(self):
        params = [roi.get_params() for roi in self._counter_controller.get_rois()]
        xs, ys, ws, hs = zip(*params)
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

        raw_params_settings_name = "%s_raw_params:%s" % (
            self.fullname,
            self._current_config.get(),
        )
        self._raw_params = settings.HashObjSetting(raw_params_settings_name)

        self._active_rois = {}
        self._roi_ids = {}
        self.__cached_counters = {}
        self._needs_update = True  # a flag to indicates that rois must be refreshed

        self._stored_names = set(self._raw_params.keys())

        # ---- tmp code until old _save_rois settings disappear ----
        if not self._stored_names:
            old_settings_name = "%s:%s" % (self.fullname, self._current_config.get())
            save_rois = settings.HashObjSetting(old_settings_name)
            old_rois = save_rois.get_all()
            errors = 0
            for name, roi in old_rois.items():
                try:

                    if isinstance(roi, ArcRoi):
                        roi = ArcRoi(**roi.__dict__)

                    elif isinstance(roi, Roi):
                        roi = Roi(**roi.__dict__)

                    self._store_roi(roi)
                    user_print(f"converting old roi {name}: {roi}")

                except Exception as e:
                    user_print(f"Failed to convert old roi {name}: {roi}")
                    user_print(e)
                    errors += 1

            if errors == 0:
                save_rois.clear()

        # --------------------------------------------------

        # create counters from keys found in redis
        for name in self._stored_names:
            self._create_single_roi_counters(name)

        # compute rois positions for current camera geometry (bin, flip, rotation, camera_roi)
        # and discard uncompatible rois and associated counters
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
            pts = numpy.array([roi.p0, roi.p5])

            # take into account the offset of current image roi
            pts[:, 0] += img.roi[0]
            pts[:, 1] += img.roi[1]

            pts = current_coords_to_raw_coords(
                pts, img.fullsize, img.flip, img.rotation, img.binning
            )

            cx, cy = list(pts[0, :])
            dx, dy = list(pts[1, :])
            raw_params = [cx, cy, dx, dy, roi.ratio, roi.aperture]

        elif isinstance(roi, Roi):
            x, y, w, h = roi.get_params()
            # take into account the offset of current image roi
            x += img.roi[0]
            y += img.roi[1]
            raw_params = current_roi_to_raw_roi(
                [x, y, w, h], img.fullsize, img.flip, img.rotation, img.binning
            )

        else:
            raise ValueError(f"Unknown roi type {type(roi)}")

        self._raw_params[roi.name] = raw_params
        self._active_rois[roi.name] = roi
        self._stored_names.add(roi.name)

    def _restore_rois_from_settings(self):
        self._active_rois = {}
        self._inactive_rois = {}
        img = self._master_controller.image
        src = self._raw_params.get_all()
        for name, raw_params in src.items():
            if len(raw_params) == 4:
                x, y, w, h = raw_roi_to_current_roi(
                    raw_params,
                    img._get_detector_max_size(),
                    img.flip,
                    img.rotation,
                    img.binning,
                )

                # take into account the offset of current image roi
                x -= img.roi[0]
                y -= img.roi[1]

                roi = Roi(x, y, w, h, name=name)

            elif len(raw_params) == 6:
                cx, cy, dx, dy, ratio, aperture = raw_params
                pts = raw_coords_to_current_coords(
                    numpy.array([[cx, cy], [dx, dy]]),
                    img._get_detector_max_size(),
                    img.flip,
                    img.rotation,
                    img.binning,
                )

                # take into account the offset of current image roi
                pts[:, 0] -= img.roi[0]
                pts[:, 1] -= img.roi[1]

                cx, cy = list(pts[0, :])
                dx, dy = list(pts[1, :])

                params = raw_params_to_arc_params(cx, cy, dx, dy, ratio, aperture)
                roi = ArcRoi(*params, name=name)

            else:
                raise ValueError(
                    f"Unexpected number of roi parameters '{name}': {raw_params}"
                )

            if self._check_roi_validity(roi):
                self._active_rois[name] = roi
                self._activate_single_roi_counters(name)

            else:
                # user_print(
                #     f"Roi {roi.name} {roi.get_params()} has been temporarily deactivated (outside image)"
                # )
                self._inactive_rois[name] = roi
                self._deactivate_single_roi_counters(name)

        self._needs_update = False

    def _check_roi_name_is_unique(self, name):
        if name in self._master_controller.roi_profiles._stored_names:
            raise ValueError(
                f"Names conflict: '{name}' is already used by a roi_profile, please use another name"
            )

        if self._master_controller.roi_collection is not None:
            if name in self._master_controller.roi_collection._stored_names:
                raise ValueError(
                    f"Names conflict: '{name}' is already used in roi_collection, please use another name"
                )

    def _check_roi_validity(self, roi):

        _, _, w0, h0 = self._master_controller.image.roi

        if isinstance(roi, Roi):
            x, y, w, h = roi.get_params()

            if x < 0 or x >= w0 or y < 0 or y >= h0:
                return False

            if (x + w) > w0 or (y + h) > h0:
                return False

            return True

        elif isinstance(roi, ArcRoi):
            for (x, y) in roi.bounding_box():

                if x < 0 or x >= w0:
                    return False

                if y < 0 or y >= h0:
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
            roi._name = name
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
                f"Roi parameters {roi.get_params()} are not valid (outside image)"
            )

        self._store_roi(roi)
        self._create_single_roi_counters(roi.name)

    def _remove_rois(self, names):
        # rois pushed on proxy have an entry in self._roi_ids
        on_proxy = []
        for name in names:
            del self._raw_params[name]
            self._stored_names.remove(name)
            self._active_rois.pop(name, None)
            self._inactive_rois.pop(name, None)
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

    def get_rois(self):
        """alias to values()"""
        cache = self._active_rois
        return [cache[name] for name in sorted(cache.keys())]

    def remove(self, name):
        """alias to: del <lima obj>.roi_counters[name]"""
        # calls _remove_rois
        del self[name]

    @property
    def config_name(self):
        return self._current_config.get()

    def upload_rois(self):
        if self._needs_update:
            self._restore_rois_from_settings()

        roi_list = self.get_rois()
        roi_id_list = self._proxy.addNames([x.name for x in roi_list])

        rois_values = list()
        arcrois_values = list()
        for roi_id, roi in zip(roi_id_list, roi_list):
            if roi.__class__ == Roi:
                rois_values.extend([roi_id])
                rois_values.extend(roi.get_params())
            elif roi.__class__ == ArcRoi:
                arcrois_values.extend([roi_id])
                arcrois_values.extend(roi.get_params())
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

    def set(self, name, roi_values):
        """alias to: <lima obj>.roi_counters[name] = roi_values"""
        self[name] = roi_values

    def get(self, name, default=None):
        return self._active_rois.get(name, default)

    def __getitem__(self, names):
        if isinstance(names, str):
            return self._active_rois[names]
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
        return name in self._active_rois

    def __len__(self):
        return len(self._active_rois)

    def clear(self):
        self._remove_rois(self._stored_names.copy())

    def keys(self):
        return self._active_rois.keys()

    def values(self):
        return self._active_rois.values()

    def items(self):
        return self._active_rois.items()

    def has_key(self, name):
        return name in self._active_rois

    def update(self, rois):
        for name, roi in rois.items():
            self[name] = roi

    def __info__(self):
        header = f"ROI Counters: {self.config_name}"
        if self._stored_names:
            labels = ["Name", "Parameters", "State"]
            tab = IncrementalTable([labels])

            for name in sorted(self._active_rois.keys()):
                roi = self._active_rois[name]
                tab.add_line([name, str(roi), "Enabled"])

            for name in sorted(self._inactive_rois.keys()):
                roi = self._inactive_rois[name]
                tab.add_line([name, str(roi), "Disabled"])

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

        raw_params_settings_name = "%s_raw_params:%s" % (
            self.fullname,
            self._current_config.get(),
        )
        self._raw_params = settings.HashObjSetting(raw_params_settings_name)
        self._active_rois = {}
        self._roi_ids = {}
        self.__cached_counters = {}
        self._needs_update = True  # a flag to indicates that rois must be refreshed

        self._stored_names = set(self._raw_params.keys())

        # ---- tmp code until old _save_rois settings disappear ----
        if not self._stored_names:
            old_settings_name = "%s:%s" % (self.fullname, self._current_config.get())
            save_rois = settings.HashObjSetting(old_settings_name)
            old_rois = save_rois.get_all()
            errors = 0
            for name, roi in old_rois.items():
                try:
                    roi = RoiProfile(**roi.__dict__)
                    self._store_roi(roi)
                    user_print(f"converting old roi {name}: {roi}")
                except Exception as e:
                    user_print(f"Failed to convert old roi {name}: {roi}")
                    errors += 1

            if errors == 0:
                save_rois.clear()
        # --------------------------------------------------

        # create counters from keys found in redis
        for name in self._stored_names:
            self._create_roi_profile_counter(name)

        # compute rois positions for current camera geometry (bin, flip, rotation, camera_roi)
        # and discard uncompatible rois and associated counters
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
            x, y, w, h = roi.get_params()
            # take into account the offset of current image roi
            x += img.roi[0]
            y += img.roi[1]
            # compute raw params
            raw_params = current_roi_to_raw_roi(
                [x, y, w, h], img.fullsize, img.flip, img.rotation, img.binning
            )
            # compute raw profile mode
            pts = numpy.array([roi.mode_vector])
            pts = current_coords_to_raw_coords(
                pts, img.fullsize, [False, False], img.rotation, [1, 1]
            )
            raw_params.extend(list(pts[0, :]))

        else:
            raise ValueError(f"Unknown roi type {type(roi)}")

        self._raw_params[roi.name] = raw_params
        self._active_rois[roi.name] = roi
        self._stored_names.add(roi.name)

    def _restore_rois_from_settings(self):
        self._active_rois = {}
        self._inactive_rois = {}
        img = self._master_controller.image
        src = self._raw_params.get_all()

        for name, raw_params in src.items():
            x, y, w, h, px, py = raw_params

            # compute roi in current geometry
            x, y, w, h = raw_roi_to_current_roi(
                [x, y, w, h],
                img._get_detector_max_size(),
                img.flip,
                img.rotation,
                img.binning,
            )

            # take into account the offset of current image roi
            x -= img.roi[0]
            y -= img.roi[1]

            # transform profile mode vector
            pts = raw_coords_to_current_coords(
                numpy.array([[px, py]]),
                img._get_detector_max_size(),
                [False, False],
                img.rotation,
                [1, 1],
            )

            # find the profile mode from vector
            w0, h0 = img._get_detector_max_size()
            if round(abs(pts[0, 0])) not in [w0, h0, 0]:
                mode = "horizontal"
            else:
                mode = "vertical"

            roi = RoiProfile(x, y, w, h, mode, name=name)

            if self._check_roi_validity(roi):
                self._active_rois[name] = roi
                self._activate_roi_profile_counter(name)

            else:
                # user_print(
                #     f"RoiProfile {roi.name} {roi.get_params()} has been temporarily deactivated (outside image)"
                # )
                self._inactive_rois[name] = roi
                self._deactivate_roi_profile_counter(name)

        self._needs_update = False

    def _check_roi_name_is_unique(self, name):
        if name in self._master_controller.roi_counters._stored_names:
            raise ValueError(
                f"Names conflict: '{name}' is already used by a roi_counter, please use another name"
            )

        if self._master_controller.roi_collection is not None:
            if name in self._master_controller.roi_collection._stored_names:
                raise ValueError(
                    f"Names conflict: '{name}' is already used in roi_collection, please use another name"
                )

    def _check_roi_validity(self, roi):

        x0, y0, w0, h0 = self._master_controller.image.roi

        if isinstance(roi, RoiProfile):
            x, y, w, h = roi.get_params()

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
            roi._name = name
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
                f"Roi parameters {roi.get_params()} are not valid (outside image)"
            )

        self._store_roi(roi)
        self._create_roi_profile_counter(roi.name)

    def _remove_rois(self, names):
        # rois pushed on proxy have an entry in self._roi_ids
        on_proxy = []
        for name in names:
            del self._raw_params[name]
            self._stored_names.remove(name)
            self._active_rois.pop(name, None)
            self._inactive_rois.pop(name, None)
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
            names = self._active_rois.keys()

        for name in names:
            roi = self._active_rois[name]
            roi.mode = mode  # mode is checked here
            self._store_roi(roi)

    def get_roi_mode(self, *names):
        """get the mode (0: horizontal, 1:vertical) of all rois or for a list of given roi names"""

        if len(names) == 1:
            return self._active_rois[names[0]].mode
        elif not names:
            names = self._active_rois.keys()

        return {name: self._active_rois[name].mode for name in names}

    def get_rois(self):
        """alias to values()"""
        cache = self._active_rois
        return [cache[name] for name in sorted(cache.keys())]

    def remove(self, name):
        """alias to: del <lima obj>.roi_profiles[name]"""
        # calls _remove_rois
        del self[name]

    @property
    def config_name(self):
        return self._current_config.get()

    def upload_rois(self):
        if self._needs_update:
            self._restore_rois_from_settings()

        roi_list = self.get_rois()
        roi_id_list = self._proxy.addNames([x.name for x in roi_list])

        rois_values = list()
        for roi_id, roi in zip(roi_id_list, roi_list):
            rois_values.append(roi_id)
            rois_values.extend(roi.get_params())
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
        return self._active_rois.get(name, default)

    def __getitem__(self, names):
        if isinstance(names, str):
            return self._active_rois[names]
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
        return name in self._active_rois

    def __len__(self):
        return len(self._active_rois)

    def clear(self):
        self._remove_rois(self._stored_names.copy())

    def keys(self):
        return self._active_rois.keys()

    def values(self):
        return self._active_rois.values()

    def items(self):
        return self._active_rois.items()

    def has_key(self, name):
        return name in self._active_rois

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
        if self._stored_names:
            labels = ["Name", "<x, y> <w, h> <mode>", "State"]
            tab = IncrementalTable([labels])

            for name in sorted(self._active_rois.keys()):
                roi = self._active_rois[name]
                tab.add_line([name, str(roi), "Enabled"])

            for name in sorted(self._inactive_rois.keys()):
                roi = self._inactive_rois[name]
                tab.add_line([name, str(roi), "Disabled"])

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

        raw_params_settings_name = "%s_raw_params:%s" % (
            self.fullname,
            self._current_config.get(),
        )
        self._raw_params = settings.HashObjSetting(raw_params_settings_name)
        self._active_rois = {}
        self._roi_ids = {}
        self._needs_update = True  # a flag to indicates that rois must be refreshed

        self._stored_names = set(self._raw_params.keys())

        # ---- tmp code until old _save_rois settings disappear ----
        if not self._stored_names:
            old_settings_name = "%s:%s" % (self.fullname, self._current_config.get())
            save_rois = settings.HashObjSetting(old_settings_name)
            old_rois = save_rois.get_all()
            errors = 0
            for name, roi in old_rois.items():
                try:
                    roi = Roi(**roi.__dict__)
                    self._store_roi(roi)
                    print(f"converting old roi {name}: {roi}")
                except Exception as e:
                    print(f"Failed to convert old roi {name}: {roi}")
                    errors += 1

            if errors == 0:
                save_rois.clear()

        # --------------------------------------------------

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
            x, y, w, h = roi.get_params()
            # take into account the offset of current image roi
            x += img.roi[0]
            y += img.roi[1]
            raw_params = current_roi_to_raw_roi(
                [x, y, w, h], img.fullsize, img.flip, img.rotation, img.binning
            )

        else:
            raise ValueError(f"Unknown roi type {type(roi)}")

        self._raw_params[roi.name] = raw_params
        self._active_rois[roi.name] = roi
        self._stored_names.add(roi.name)

    def _restore_rois_from_settings(self):
        self._active_rois = {}
        self._inactive_rois = {}
        img = self._master_controller.image
        src = self._raw_params.get_all()
        for name, raw_params in src.items():
            x, y, w, h = raw_roi_to_current_roi(
                raw_params,
                img._get_detector_max_size(),
                img.flip,
                img.rotation,
                img.binning,
            )

            # take into account the offset of current image roi
            x -= img.roi[0]
            y -= img.roi[1]

            roi = Roi(x, y, w, h, name=name)

            if self._check_roi_validity(roi):
                self._active_rois[name] = roi
            else:
                # user_print(
                #     f"Roi {roi.name} {roi.get_params()} has been temporarily deactivated (outside image)"
                # )
                self._inactive_rois[name] = roi

        self._needs_update = False

    def _check_roi_name_is_unique(self, name):
        if name in self._master_controller.roi_profiles._stored_names:
            raise ValueError(
                f"Names conflict: '{name}' is already used by a roi_profile, please use another name"
            )

        if name in self._master_controller.roi_counters._stored_names:
            raise ValueError(
                f"Names conflict: '{name}' is already used by a roi_counter, please use another name"
            )

    def _check_roi_validity(self, roi):

        _, _, w0, h0 = self._master_controller.image.roi

        if isinstance(roi, Roi):
            x, y, w, h = roi.get_params()

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
            roi._name = name
        elif len(roi_values) == 4:
            roi = Roi(*roi_values, name=name)
        else:
            raise TypeError(
                "Lima.RoiCollectionController: accepts Roi objects"
                " or (x, y, width, height) values"
                # " or (cx, cy, r1, r2, a1, a2) values"
            )

        if not self._check_roi_validity(roi):
            raise ValueError(
                f"Roi parameters {roi.get_params()} are not valid (outside image)"
            )

        self._store_roi(roi)

    def _remove_rois(self, names):
        # rois pushed on proxy have an entry in self._roi_ids
        on_proxy = []
        for name in names:
            del self._raw_params[name]
            self._stored_names.remove(name)
            self._active_rois.pop(name, None)
            self._inactive_rois.pop(name, None)
            if name in self._roi_ids:
                on_proxy.append(name)
                del self._roi_ids[name]
        if on_proxy:
            self._proxy.removeRois(on_proxy)

    def get_rois(self):
        """alias to values()"""
        cache = self._active_rois
        return [cache[name] for name in cache.keys()]

    def remove(self, name):
        """alias to: del <lima obj>.roi_counters[name]"""
        # calls _remove_rois
        del self[name]

    @property
    def config_name(self):
        return self._current_config.get()

    def upload_rois(self):
        if self._needs_update:
            self._restore_rois_from_settings()

        roicoords = []
        for roi in self.get_rois():
            roicoords.extend(roi.get_params())

        if roicoords:
            self._proxy.setRois(roicoords)

    # dict like API
    def set(self, name, roi_values):
        """alias to: <lima obj>.roi_counters[name] = roi_values"""
        self[name] = roi_values

    def get(self, name, default=None):
        return self._active_rois.get(name, default)

    def __getitem__(self, names):
        if isinstance(names, str):
            return self._active_rois[names]
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
        return name in self._active_rois

    def __len__(self):
        return len(self._active_rois)

    def clear(self):
        self._remove_rois(self._stored_names.copy())

    def keys(self):
        return self._active_rois.keys()

    def values(self):
        return self._active_rois.values()

    def items(self):
        return self._active_rois.items()

    def has_key(self, name):
        return name in self._active_rois

    def update(self, rois):
        for name, roi in rois.items():
            self[name] = roi

    def __info__(self):
        header = f"ROI Collection: {self.config_name}"
        nb_rois = len(self._stored_names)
        if nb_rois:
            txt = f"Collection of {nb_rois} rois\n"
            txt += f"{len(self._inactive_rois)} are currently disabled"
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
        if len(self._active_rois):
            return super().counters
        else:
            return counter_namespace([])
