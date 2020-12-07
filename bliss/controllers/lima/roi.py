# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import enum
import functools
import numpy

from bliss.config import settings
from bliss.common.counter import IntegratingCounter
from bliss.controllers.counter import IntegratingCounterController
from bliss.controllers.counter import counter_namespace
from bliss.scanning.acquisition.lima import RoiProfileAcquisitionSlave
from bliss.shell.formatters.table import IncrementalTable


# ----------------- helpers for ROI transformation (flip, rotation, binning) --------------

_DEG2RAD = numpy.pi / 180.0
_RAD2DEG = 180.0 / numpy.pi


def raw_roi_to_current_roi(raw_roi, raw_img_size, flip, rotation, binning):

    """ Computes the new roi after applying the transformations {flip, rotation, binning} on the raw_roi.
    args:
        - raw_roi: roi coordinates expressed in the {unbinned, unflipped, unrotated} image referential (i.e camera chip size).
        - raw_img_size: size of the {unbinned, unflipped, unrotated} image where the roi is defined.
        - flip: flipping to apply (e.g. [1,0])
        - rotation: rotation to apply
        - binning: binning to apply (e.g. [1,1])
         
    """
    assert raw_roi[2] != 0
    assert raw_roi[3] != 0

    new_roi = raw_roi
    w0, h0 = raw_img_size

    # bin roi
    xbin, ybin = binning
    if xbin != 1 or ybin != 1:
        x, y, w, h = new_roi
        new_roi = [x // xbin, y // ybin, w // xbin, h // ybin]
        w0, h0 = w0 // xbin, h0 // ybin

    # flip roi
    if flip[0]:
        x, y, w, h = new_roi
        new_roi = [w0 - w - x, y, w, h]

    if flip[1]:
        x, y, w, h = new_roi
        new_roi = [x, h0 - h - y, w, h]

    # rotate roi
    if rotation != 0:
        new_roi = calc_roi_rotation(new_roi, rotation, (w0, h0))

    x, y, w, h = new_roi
    return [int(x), int(y), int(w), int(h)]


def current_roi_to_raw_roi(current_roi, img_size, flip, rotation, binning):

    """ computes the raw_roi (without flip, rot, bin) from the current_roi (with flip, rot, bin)
        args:
            - current_roi: roi coordinates expressed in the {binned, flipped, rotated} image referential.
            - img_size: the actual size of the image where the roi is defined (taking into account binning and rotation)
            - flip: current image flipping (e.g. [1,0])
            - rotation: current image rotation
            - binning: current image binning (e.g. [1,1])

    """

    assert current_roi[2] != 0
    assert current_roi[3] != 0

    raw_roi = [
        float(current_roi[0]),
        float(current_roi[1]),
        float(current_roi[2]),
        float(current_roi[3]),
    ]
    w0, h0 = img_size

    # inverse rotation
    if rotation != 0:
        raw_roi = calc_roi_rotation(raw_roi, -rotation, (w0, h0))
        if rotation in [90, 270]:
            w0, h0 = img_size[1], img_size[0]

    # unflipped roi
    if flip[0]:
        x, y, w, h = raw_roi
        raw_roi = [w0 - w - x, y, w, h]

    if flip[1]:
        x, y, w, h = raw_roi
        raw_roi = [x, h0 - h - y, w, h]

    # unbinned roi
    xbin, ybin = binning
    if xbin != 1 or ybin != 1:
        x, y, w, h = raw_roi
        raw_roi = x * xbin, y * ybin, w * xbin, h * ybin

    return raw_roi


def calc_roi_rotation(roi, angle, img_size):
    """ computes the roi rotation.
        args:
            - roi: roi coordinates
            - angle: the angle of the rotation (degree)
            - img_size: size of the image where the roi is defined
    """

    assert roi[2] != 0
    assert roi[3] != 0

    # define the camera fullframe
    w0, h0 = img_size
    p0 = (0, 0)
    p1 = (w0, h0)
    frame = numpy.array([p0, p1], dtype="float32")

    # define the subarea
    x, y, w, h = roi
    r0 = (x, y)
    r1 = (x + w, y + h)
    rect = numpy.array([r0, r1], dtype="float32")

    # define the rotation matrix
    theta = _DEG2RAD * angle * -1  # Lima rotation is clockwise !
    R = numpy.array(
        [[numpy.cos(theta), -numpy.sin(theta)], [numpy.sin(theta), numpy.cos(theta)]],
        dtype="float32",
    )

    new_frame = numpy.dot(frame, R)
    new_rect = numpy.dot(rect, R)

    # find top left corner of rotated fullframe (new origin)
    ox = numpy.amin(new_frame[:, 0])
    oy = numpy.amin(new_frame[:, 1])

    # find top left corner of the subarea and reset origin to ox,oy
    x0 = numpy.amin(new_rect[:, 0]) - ox
    y0 = numpy.amin(new_rect[:, 1]) - oy

    # find the new subarea width
    w = abs(new_rect[0, 0] - new_rect[1, 0])
    h = abs(new_rect[0, 1] - new_rect[1, 1])

    new_roi = [x0, y0, w, h]

    return new_roi


# -------------------------------------------------------------------------------------------


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
        assert self.is_valid()

    def is_valid(self):
        raise NotImplementedError

    def __repr__(self):
        raise NotImplementedError

    def __eq__(self, other):
        raise NotImplementedError

    def get_coords(self):
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

    def is_valid(self):
        return self.x >= 0 and self.y >= 0 and self.width >= 0 and self.height >= 0

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

    def is_valid(self):
        ans = self.r1 >= 0 and self.r2 > 0
        ans = ans and self.a1 != self.a2
        ans = ans and self.r1 != self.r2
        return ans

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
        self.factory = functools.partial(RoiStatCounter, name, **keys)

    @property
    def sum(self):
        return self.factory(RoiStat.Sum)

    @property
    def avg(self):
        return self.factory(RoiStat.Avg)

    @property
    def std(self):
        return self.factory(RoiStat.Std)

    @property
    def min(self):
        return self.factory(RoiStat.Min)

    @property
    def max(self):
        return self.factory(RoiStat.Max)

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

    def __init__(self, proxy, acquisition_proxy):
        # leave counters registration to the parent object
        super().__init__(
            "roi_counters", master_controller=acquisition_proxy, register_counters=False
        )
        self._proxy = proxy
        self._current_config = settings.SimpleSetting(
            self.fullname, default_value="default"
        )
        settings_name = "%s:%s" % (self.fullname, self._current_config.get())
        self._roi_ids = {}
        self.__cached_counters = {}
        self._save_rois = settings.HashObjSetting(settings_name)

    def get_acquisition_object(self, acq_params, ctrl_params, parent_acq_params):
        # avoid cyclic import
        from bliss.scanning.acquisition.lima import RoiCountersAcquisitionSlave

        # in case `count_time` is missing in acq_params take it from parent_acq_params
        if "acq_expo_time" in parent_acq_params:
            acq_params.setdefault("count_time", parent_acq_params["acq_expo_time"])
        if "acq_nb_frames" in parent_acq_params:
            acq_params.setdefault("npoints", parent_acq_params["acq_nb_frames"])

        return RoiCountersAcquisitionSlave(self, ctrl_params=ctrl_params, **acq_params)

    def _set_roi(self, name, roi_values):

        if name in self._master_controller.roi_profiles._save_rois.keys():
            raise ValueError(
                f"Names conflict: '{name}' is already used by a roi_profile, please use another name"
            )

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

        self._save_rois[roi.name] = roi

    def _remove_rois(self, names):
        # rois pushed on proxy have an entry in self._roi_ids
        on_proxy = []
        for name in names:
            del self._save_rois[name]
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
        return [cache[name] for name in sorted(cache.keys())]

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
        self._save_rois = settings.HashObjSetting("%s:%s" % (self.name, name))

    def upload_rois(self):

        roi_list = [roi for roi in self.get_rois() if roi.is_valid()]
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

    # Counter access

    def get_single_roi_counters(self, name):
        roi_data = self._save_rois.get(name)
        if roi_data is None:
            raise AttributeError(
                "Can't find a roi_counter with name: {!r}".format(name)
            )
        cached_roi_data, counters = self.__cached_counters.get(name, (None, None))
        if cached_roi_data != roi_data:
            counters = SingleRoiCounters(name, controller=self)
            self.__cached_counters[name] = (roi_data, counters)

        return counters

    def iter_single_roi_counters(self):
        for roi in self.get_rois():
            yield self.get_single_roi_counters(roi.name)

    @property
    def counters(self):
        return counter_namespace(
            [
                counter
                for counters in self.iter_single_roi_counters()
                for counter in counters
            ]
        )

    # Representation

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

    def get_values(self, from_index, *counters):
        roi_counter_size = len(RoiStat)
        raw_data = self._proxy.readCounters(from_index)
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

    def __init__(self, proxy, acquisition_proxy):
        # leave counters registration to the parent object
        super().__init__(
            "roi_profiles", master_controller=acquisition_proxy, register_counters=False
        )
        self._proxy = proxy
        self._current_config = settings.SimpleSetting(
            self.fullname, default_value="default"
        )
        settings_name = "%s:%s" % (self.fullname, self._current_config.get())
        self._roi_ids = {}
        self.__cached_counters = {}
        self._save_rois = settings.HashObjSetting(settings_name)

    def get_acquisition_object(self, acq_params, ctrl_params, parent_acq_params):
        # in case `count_time` is missing in acq_params take it from parent_acq_params
        if "acq_expo_time" in parent_acq_params:
            acq_params.setdefault("count_time", parent_acq_params["acq_expo_time"])
        if "acq_nb_frames" in parent_acq_params:
            acq_params.setdefault("npoints", parent_acq_params["acq_nb_frames"])

        return RoiProfileAcquisitionSlave(self, ctrl_params=ctrl_params, **acq_params)

    def _set_roi(self, name, roi_values):
        if name in self._master_controller.roi_counters._save_rois.keys():
            raise ValueError(
                f"Names conflict: '{name}' is already used by a roi_counter, please use another name"
            )

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

        self._save_rois[roi.name] = roi

    def _remove_rois(self, names):
        # rois pushed on proxy have an entry in self._roi_ids
        on_proxy = []
        for name in names:
            del self._save_rois[name]
            if name in self._roi_ids:
                on_proxy.append(name)
                del self._roi_ids[name]
        if on_proxy:
            self._proxy.removeRois(on_proxy)

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
            self._save_rois[name] = roi  # to dump the new mode (settings)

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
        roi_list = [roi for roi in self.get_rois() if roi.is_valid()]
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

    def get_roi_counter(self, name):
        roi = self._save_rois.get(name)
        if roi is None:
            raise AttributeError(
                "Can't find a roi_profile with name: {!r}".format(name)
            )
        cached_roi, counter = self.__cached_counters.get(name, (None, None))
        if roi != cached_roi:
            counter = RoiProfileCounter(name, controller=self)
            self.__cached_counters[name] = (roi, counter)

        return counter

    def iter_roi_counters(self):
        for roi in self.get_rois():
            yield self.get_roi_counter(roi.name)

    @property
    def counters(self):
        return counter_namespace([counter for counter in self.iter_roi_counters()])

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
        blank = [[] for cnt in counters]
        profiles = [[] for cnt in counters]

        last_num_of_spec = None
        for i, cnt in enumerate(counters):
            size = cnt.shape[0]
            cid = self._roi_ids[cnt.name]
            spec = self._proxy.readImage([int(cid), int(from_index)])

            if spec != []:
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
