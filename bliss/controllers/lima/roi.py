# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import enum
import functools

import numpy

from bliss.config import settings
from bliss.common.utils import grouped, OrderedDict
from bliss.common.measurement import IntegratingCounter


class Roi(object):
    def __init__(self, x, y, width, height, name=None):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.name = name

    def is_valid(self):
        return (self.x >= 0 and self.y >= 0 and
                self.width >= 0 and self.height >= 0)

    def __repr__(self):
        return "<%s,%s> <%s x %s>" % (self.x, self.y,
                                      self.width, self.height)


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
        name = self.roi_name + '.' + stat.name.lower()
        self.controller = kwargs.pop('controller')
        acquisition_controller = kwargs.pop('acquisition_controller')
        IntegratingCounter.__init__(self, name, self.controller,
                                    acquisition_controller, **kwargs)

    def __int__(self):
        # counter statistic ID = roi_id | statistic_id
        # it is calculated everty time because the roi id for a given roi name might
        # change if rois are added/removed from lima
        roi_id = self.controller._roi_ids[self.roi_name]
        return self.roi_stat_id(roi_id, self.stat)

    @staticmethod
    def roi_stat_id(roi_id, stat):
        return (roi_id << 8) | stat


class RoiCounter(object):

    def __init__(self, name, **keys):
        self.name = name
        self.Counter = functools.partial(RoiStatCounter, name, **keys)
    
    @property
    def sum(self):
        return self.Counter(RoiStat.Sum)

    @property
    def avg(self):
        return self.Counter(RoiStat.Avg)

    @property
    def std(self):
        return self.Counter(RoiStat.Std)

    @property
    def min(self):
        return self.Counter(RoiStat.Min)

    @property
    def max(self):
        return self.Counter(RoiStat.Max)


class RoiCounterGroupReadHandler(IntegratingCounter.GroupedReadHandler):

    def prepare(self, *counters):
        self.controller.upload_rois()

    def get_values(self, from_index, *counters):
        roi_counter_size = len(RoiStat)
        raw_data = self.controller._proxy.readCounters(from_index)
        if not raw_data.size:
            return len(counters)*(numpy.array(()),)
        raw_data.shape = (raw_data.size) / roi_counter_size, roi_counter_size
        result = OrderedDict([int(counter), []] for counter in counters)

        for roi_counter in raw_data:
            roi_id = int(roi_counter[0])
            for stat in range(roi_counter_size):
                full_id = RoiStatCounter.roi_stat_id(roi_id, stat)
                counter_data = result.get(full_id)
                if counter_data is not None:
                    counter_data.append(roi_counter[stat])
        return map(numpy.array, result.values())


class RoiCounters(object):

    def __init__(self, name, proxy, acquisition_proxy):
        self._proxy = proxy
        self._acquisition_proxy = acquisition_proxy
        self._proxy.Start()
        self.name = '%s:RoiCounters' % name
        self._current_config = settings.SimpleSetting(self.name,
                                                      default_value='default')
        settings_name = '%s:%s' % (self.name, self._current_config.get())
        self._save_rois = settings.HashObjSetting(settings_name)
        self._roi_ids = {}
        self._grouped_read_handler = RoiCounterGroupReadHandler(self)

    def set_roi(self,name,roi_values):
        if isinstance(roi_values,Roi):
            roi = roi_values
        elif len(roi_values) == 4:
            roi = Roi(*roi_values)
        else:
            raise TypeError("Lima.RoiCounters: roi accepts roi (class)"
                            " or (x,y,width,height) values")
        roi.name = name
        roi_id = self._proxy.addNames((name,))[0]
        self._proxy.setRois((roi_id,
                             roi.x,roi.y,
                             roi.width,roi.height,))
        self._save_rois[name] = roi
        self._roi_ids[name] = roi_id

    def get_rois(self):
        return self._save_rois.values()

    def get_saved_config_names(self):
        return list(settings.scan(match='%s:*' % self.name))

    @property
    def config_name(self):
        return self._current_config.get()
    @config_name.setter
    def config_name(self,name):
        self._current_config.set(name)
        self._save_rois = settings.HashObjSetting('%s:%s' % (self.name,name))

    def upload_rois(self):
        roi_list = [roi for roi in self.get_rois() if roi.is_valid()]
        roi_id_list = self._proxy.addNames([x.name for x in roi_list])
        rois_values = list()
        for roi_id,roi in zip(roi_id_list,roi_list):
            rois_values.extend((roi_id,
                                roi.x,roi.y,
                                roi.width,roi.height))
            self._roi_ids[roi.name] = roi_id
        self._proxy.setRois(rois_values)

    def __getattr__(self, name):
        if self._save_rois.get(name) is None:
            raise AttributeError('Unknown ROI counter {0:!r}'.format(name))
        return RoiCounter(name, controller=self, 
                          acquisition_controller=self._acquisition_proxy,
                          grouped_read_handler=self._grouped_read_handler)

    def __repr__(self):
        name = self.name.rsplit(':', 1)[-1]
        rois = self.get_rois()
        header = 'Name', 'ROI'
        x = max((len(str(roi.x)) for roi in rois))
        y = max((len(str(roi.y)) for roi in rois))
        w = max((len(str(roi.width)) for roi in rois))
        h = max((len(str(roi.height)) for roi in rois))
        roi_template = '<{{0.x: >{0}}}, {{0.y: >{1}}}> ' \
                       '<{{0.width: >{2}}} x {{0.height: >{3}}}>'.format(x, y, w, h)
        name_len = max(max((len(roi.name) for roi in rois)), len(header[0]))
        roi_len = x + y + w + h + 10 # 10 is surrounding characters (<,>,x and spaces)
        template = '{{0: >{0}}}  {{1: >{1}}}'.format(name_len, roi_len)
        lines = ['ROI Counters: {0} ({1})\n'.format(name, self.config_name),
                 template.format(*header),
                 template.format(name_len*'-', roi_len*'-')]
        lines += [template.format(roi.name, roi_template.format((roi))) for roi in rois]
        return '\n'.join(lines)
