# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import enum
import functools

import numpy

from bliss.config import settings
from bliss.common.measurement import IntegratingCounter


class Roi:
    def __init__(self, x, y, width, height, name=None):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.name = name

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

    def to_dict(self):
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return False
        return self.p0 == other.p0 and self.p1 == other.p1 and self.name == other.name

    @classmethod
    def frompoints(cls, p0, p1, name=None):
        return cls.fromcoords(p0[0], p0[1], p1[0], p1[1], name=name)

    @classmethod
    def fromcoords(cls, x0, y0, x1, y1, name=None):
        xmin = min(x0, x1)
        ymin = min(y0, y1)
        xmax = max(x0, x1)
        ymax = max(y0, y1)
        return cls(xmin, ymin, xmax - xmin, ymax - ymin, name=name)


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
        self.parent_roi_counters = kwargs.pop("controller")
        master_controller = kwargs.pop("master_controller")
        IntegratingCounter.__init__(
            self, name, self.parent_roi_counters, master_controller, **kwargs
        )

    def __int__(self):
        # counter statistic ID = roi_id | statistic_id
        # it is calculated everty time because the roi id for a given roi name might
        # change if rois are added/removed from lima
        roi_id = self.parent_roi_counters._roi_ids[self.roi_name]
        return numpy.asscalar(self.roi_stat_id(roi_id, self.stat))

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


class RoiCounterGroupReadHandler(IntegratingCounter.GroupedReadHandler):
    def prepare(self, *counters):
        self.controller.upload_rois()

    def get_values(self, from_index, *counters):
        roi_counter_size = len(RoiStat)
        raw_data = self.controller._proxy.readCounters(from_index)
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


class RoiCounters:
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

    def __init__(self, name, proxy, acquisition_proxy):
        self._proxy = proxy
        # 'acquisition proxy' is the BLISS lima controller
        self._acquisition_proxy = acquisition_proxy
        self._grouped_read_handler = RoiCounterGroupReadHandler(self)
        self.name = "roi_counters"
        full_name = "%s:%s" % (name, self.name)
        self._current_config = settings.SimpleSetting(
            full_name, default_value="default"
        )
        settings_name = "%s:%s" % (full_name, self._current_config.get())
        self._roi_ids = {}
        self.__cached_counters = {}
        self._save_rois = settings.HashObjSetting(settings_name)

    def _set_roi(self, name, roi_values):
        if isinstance(roi_values, Roi):
            roi = roi_values
        elif len(roi_values) == 4:
            roi = Roi(*roi_values, name=name)
        else:
            raise TypeError(
                "Lima.RoiCounters: roi accepts roi (class)"
                " or (x,y,width,height) values"
            )
        roi.name = name
        roi_id = self._proxy.addNames((name,))[0]
        self._proxy.Start()
        self._proxy.setRois((roi_id, roi.x, roi.y, roi.width, roi.height))
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
        return list(self.values())

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
        for roi_id, roi in zip(roi_id_list, roi_list):
            rois_values.extend((roi_id, roi.x, roi.y, roi.width, roi.height))
            self._roi_ids[roi.name] = roi_id
        if rois_values:
            self._proxy.Start()
            self._proxy.setRois(rois_values)

    def load_rois(self):
        """
        Load current ROI counters from Lima and store them in settings
        """
        self._clear_rois_settings()
        roi_names = self._proxy.getNames()
        rois = self._proxy.getRois(roi_names)
        for i, name in enumerate(roi_names):
            roi_id = rois[i * 5]
            idx = i * 5 + 1
            x, y, w, h = rois[idx : idx + 4]
            roi = Roi(x, y, w, h, name=name)
            self._set_roi_settings(roi_id, roi)

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
            counters = SingleRoiCounters(
                name,
                controller=self,
                master_controller=self._acquisition_proxy,
                grouped_read_handler=self._grouped_read_handler,
            )
            self.__cached_counters[name] = (roi_data, counters)

        return counters

    def iter_single_roi_counters(self):
        for roi in self.get_rois():
            yield self.get_single_roi_counters(roi.name)

    @property
    def counters(self):
        return [
            counter
            for counters in self.iter_single_roi_counters()
            for counter in counters
        ]

    # Representation

    def __info__(self):
        name = self.name.rsplit(":", 1)[-1]
        lines = ["[{0}]\n".format(self.config_name)]
        rois = [self[name] for name in sorted(self.keys())]
        if rois:
            header = "Name", "ROI (<X, Y> <W x H>)"
            x = max((len(str(roi.x)) for roi in rois))
            y = max((len(str(roi.y)) for roi in rois))
            w = max((len(str(roi.width)) for roi in rois))
            h = max((len(str(roi.height)) for roi in rois))
            roi_template = (
                "<{{0.x: >{0}}}, {{0.y: >{1}}}> "
                "<{{0.width: >{2}}} x {{0.height: >{3}}}>".format(x, y, w, h)
            )
            name_len = max(max((len(roi.name) for roi in rois)), len(header[0]))
            roi_len = (
                x + y + w + h + 10
            )  # 10 is surrounding characters (<,>,x and spaces)
            template = "{{0: >{0}}}  {{1: >{1}}}".format(name_len, roi_len)
            lines += [
                template.format(*header),
                template.format(name_len * "-", roi_len * "-"),
            ]
            lines += [
                template.format(roi.name, roi_template.format((roi))) for roi in rois
            ]
        else:
            lines.append("*** no ROIs defined ***")
        return "\n".join(lines)
