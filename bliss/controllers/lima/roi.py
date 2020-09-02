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
from bliss.scanning.acquisition.lima import RoiCountersAcquisitionSlave
from bliss.data.display import FormatedTab


class Roi:
    def __init__(self, x, y, width, height, name=None):
        self.x = int(x)
        self.y = int(y)
        self.width = int(width)
        self.height = int(height)
        self.name = name

        assert self.is_valid()

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
        if not isinstance(other, self.__class__):
            return False
        ans = self.x == other.x and self.y == other.y
        ans = ans and self.width == other.width and self.height == other.height
        ans = ans and self.name == other.name
        return ans

    def get_coords(self):
        return [self.x, self.y, self.width, self.height]

    def to_array(self):
        return numpy.array(self.get_coords())

    def to_dict(self):
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}


class ArcRoi(object):
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
        self.name = name

        assert self.is_valid()

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
        if not isinstance(other, self.__class__):
            return False
        ans = self.cx == other.cx and self.cy == other.cy
        ans = ans and self.r1 == other.r1 and self.r2 == other.r2
        ans = ans and self.a1 == other.a1 and self.a2 == other.a2
        ans = ans and self.name == other.name
        return ans

    def get_coords(self):
        return [self.cx, self.cy, self.r1, self.r2, self.a1, self.a2]

    def to_array(self):
        return numpy.array(self.get_coords())

    def to_dict(self):
        return {
            "cx": self.cx,
            "cy": self.cy,
            "r1": self.r1,
            "r2": self.r2,
            "a1": self.a1,
            "a2": self.a2,
        }


class RoiStat(enum.IntEnum):
    Id = 0
    Frame = 1
    Sum = 2
    Avg = 3
    Std = 4
    Min = 5
    Max = 6


class RoiStatCounter(IntegratingCounter):
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


class RoiCounters(IntegratingCounterController):
    """Lima ROI counters

        Example usage:

        # add/replace a roi
        mpx.roi_counters['r1'] = Roi(10, 10, 100, 200)

        # add/replace multiple rois
        mpx.roi_counters['r2', 'r3'] = Roi(20, 20, 300, 400), Roi(20, 20, 300, 400)

        # get roi info
        r2 = mpx.roi_counters['r2']

        # get multiple roi info
        r2, r1 = mpx.roi_counters['r2', 'r1']

        # remove roi
        del mpx.roi_counters['r1']

        # clear all rois
        mpx.roi_counters.clear()

        # list roi names:
        mpx.roi_counters.keys()

        # loop rois
        for roi_name, roi in mpx.roi_counters.items():
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
        # in case `count_time` is missing in acq_params take it from parent_acq_params
        if "acq_expo_time" in parent_acq_params:
            acq_params.setdefault("count_time", parent_acq_params["acq_expo_time"])
        if "acq_nb_frames" in parent_acq_params:
            acq_params.setdefault("npoints", parent_acq_params["acq_nb_frames"])

        return RoiCountersAcquisitionSlave(self, ctrl_params=ctrl_params, **acq_params)

    def _set_roi(self, name, roi_values):
        if isinstance(roi_values, (Roi, ArcRoi)):
            roi = roi_values
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
        roi.name = name
        roi_id = self._proxy.addNames((name,))[0]
        self._proxy.Start()

        params = [roi_id]
        params.extend(roi.get_coords())

        if isinstance(roi, Roi):
            self._proxy.setRois(params)
        elif isinstance(roi, ArcRoi):
            self._proxy.setArcRois(params)

        self._set_roi_settings(roi_id, roi)

    def _set_roi_settings(self, roi_id, roi):
        self._save_rois[roi.name] = roi
        self._roi_ids[roi.name] = roi_id

    def _clear_rois_settings(self):
        self._remove_rois(roi.name for roi in self.iter_single_roi_counters())

    def _remove_rois(self, names):
        for name in names:
            del self._save_rois[name]
            if name in self._roi_ids:
                del self._roi_ids[name]
        self._proxy.removeRois(list(names))

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
        self._proxy.clearAllRois()
        roi_list = [roi for roi in self.get_rois() if roi.is_valid()]
        roi_id_list = self._proxy.addNames([x.name for x in roi_list])

        rois_values = list()
        arcrois_values = list()
        for roi_id, roi in zip(roi_id_list, roi_list):

            if isinstance(roi, Roi):
                rois_values.extend([roi_id])
                rois_values.extend(roi.get_coords())
            elif isinstance(roi, ArcRoi):
                arcrois_values.extend([roi_id])
                arcrois_values.extend(roi.get_coords())

            self._roi_ids[roi.name] = roi_id

        if rois_values or arcrois_values:
            self._proxy.Start()

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
        self._clear_rois_settings()

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
            raise AttributeError("Unknown ROI counter {!r}".format(name))
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
            tab = FormatedTab([labels])
            [tab.add_line([roi.name, str(roi)]) for roi in rois if isinstance(roi, Roi)]
            [
                tab.add_line([roi.name, str(roi)])
                for roi in rois
                if isinstance(roi, ArcRoi)
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
