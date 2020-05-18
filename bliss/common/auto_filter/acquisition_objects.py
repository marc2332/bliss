# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
import weakref
import gevent
import numpy

from bliss.scanning.acquisition.motor import (
    LinearStepTriggerMaster as _LinearStepTriggerMaster
)
from bliss.scanning import chain
from bliss.scanning.acquisition import lima
from bliss.scanning.channel import AcquisitionChannel
from bliss.common import event


class LinearStepTriggerMaster(_LinearStepTriggerMaster):
    def __init__(self, *args, **keys):
        super().__init__(*args, **keys)
        self._valid_point = None
        self._event = gevent.event.Event()

    def __iter__(self):
        position_iter = zip(*self._motor_pos)
        positions = next(position_iter)
        while True:
            self.next_mv_cmd_arg = []
            for axis, position in zip(self._axes, positions):
                self.next_mv_cmd_arg += [axis, position]
            self.reset_point_valid()
            yield self
            if self.is_point_valid():
                try:
                    positions = next(position_iter)
                except StopIteration:
                    self.stop_all_slaves()
                    break

    def trigger(self):
        self.trigger_slaves()
        self.wait_slaves()

    def validate_point(self, point_nb, valid):
        self._valid_point = valid
        self._event.set()
        if valid:
            positions = [axis.position for axis in self._axes + self._monitor_axes]
            self.channels.update_from_iterable(positions)

    def reset_point_valid(self):
        self._valid_point = None
        self._event.clear()

    def is_point_valid(self):
        while self._valid_point is None:
            self._event.wait()
        return self._valid_point


class _Base:
    def __init__(self, auto_filter):
        self._name_2_channel = weakref.WeakValueDictionary()
        self._name_2_corr_chan = weakref.WeakValueDictionary()
        # copy all channel from the slave.
        for channel in self.device.channels:
            new_channel, _, _ = chain.duplicate_channel(channel)
            self._name_2_channel[new_channel.name] = new_channel
            event.connect(channel, "new_data", self.new_data_received)
            self.channels.append(new_channel)

            # create a corrected channel if given by the AutoFilter instance
            # use same dtype, shape and unit
            if new_channel.name in auto_filter.counters_for_correction:
                corr_chan = AcquisitionChannel(
                    f"{new_channel.name}{auto_filter.corr_suffix}",
                    channel.dtype,
                    channel.shape,
                    channel.unit,
                )
                self.channels.append(corr_chan)
                self._name_2_corr_chan[new_channel.name] = corr_chan

        self.__pending_data = dict()
        self.__last_point_rx = dict()
        self.__valid_point = dict()
        self._auto_filter = auto_filter

    def prepare(self):
        return self.device.prepare()

    def start(self):
        return self.device.start()

    def stop(self):
        try:
            return self.device.stop()
        finally:
            for chan in self.device.channels:
                event.disconnect(chan, "new_data", self.new_data_received)

    def trigger(self):
        return self.device.trigger()

    def reading(self):
        return self.device.reading()

    def trigger_ready(self):
        return self.device.trigger_ready()

    def wait_ready(self):
        return self.device.wait_ready()

    def fill_meta_at_scan_init(self, scan_meta):
        return self.device.fill_meta_at_scan_init(scan_meta)

    def fill_meta_at_scan_end(self, scan_meta):
        return self.device.fill_meta_at_scan_end(scan_meta)

    def new_data_received(self, event_dict=None, signal=None, sender=None):
        channel_data = event_dict.get("data")
        if channel_data is None:
            return

        channel = sender
        channel_name = channel.name
        last_point_rx = self.__last_point_rx.setdefault(channel_name, 0)
        valid = self.__valid_point.get(last_point_rx)
        # three cases
        # valid = False -> not valid
        # valid = True -> is valid
        # valid == None -> not yet validated
        if valid is None:
            previous_data = self.__pending_data.get(channel_name)
            if previous_data is None:
                self.__pending_data[channel_name] = channel_data
            else:
                self.__pending_data[channel_name] = numpy.append(
                    previous_data, channel_data
                )
        else:  # valid is True or False
            if valid:
                my_channel = self._name_2_channel[channel_name]
                my_channel.emit(channel_data)

                corr_chan = self._name_2_corr_chan.get(channel_name)
                if corr_chan is not None:
                    corrected_data = self._auto_filter.corr_func(
                        last_point_rx, channel_name, channel_data
                    )
                    corr_chan.emit(corrected_data)

        self.__last_point_rx[channel_name] = last_point_rx + len(channel_data)

    def validate_point(self, point_nb, valid_flag):
        # for now we just do simple thing we remove all the
        # pending... to check if it too simple.  Doesn't take into
        # account data block receiving...
        self.__valid_point[point_nb] = valid_flag
        if not valid_flag:
            # clean pending_data
            self.__pending_data = dict()
        else:
            pending_data = self.__pending_data
            self.__pending_data = dict()
            for channel_name, data in pending_data.items():
                channel = self._name_2_channel[channel_name]
                channel.emit(data)

                corr_chan = self._name_2_corr_chan.get(channel_name)
                if corr_chan is not None:
                    corrected_data = self._auto_filter.corr_func(
                        point_nb, channel_name, data
                    )
                    corr_chan.emit(corrected_data)


class _Slave(_Base, chain.AcquisitionSlave):
    def __init__(self, auto_filter, slave, npoints=1):
        chain.AcquisitionSlave.__init__(
            self,
            slave,
            name=slave.name,
            npoints=npoints,
            trigger_type=slave.trigger_type,
            prepare_once=slave.prepare_once,
            start_once=slave.start_once,
        )
        _Base.__init__(self, auto_filter)


class _SlaveIter(_Slave):
    def __iter__(self):
        for i in self.device:
            yield self


class _Master(_Base, chain.AcquisitionMaster):
    def __init__(self, auto_filter, master, npoints=1):
        chain.AcquisitionMaster.__init__(
            self,
            master,
            name=master.name,
            npoints=npoints,
            trigger_type=master.trigger_type,
            prepare_once=master.prepare_once,
            start_once=master.start_once,
        )
        _Base.__init__(self, auto_filter)
        # hack slaves of master
        # replace buy our slaves
        master._AcquisitionMaster__slaves = self.slaves

    @property
    def parent(self):
        return chain.AcquisitionMaster.parent.fget(self)

    @parent.setter
    def parent(self, new_parent):
        chain.AcquisitionMaster.parent.fset(self, new_parent)
        # give to the embeded AcqMaster the same parent
        # to avoid to trig on start (i.e:Timer)
        self.device.parent = new_parent


class _MasterIter(_Master):
    def __iter__(self):
        for i in self.device:
            yield self


class _Lima(_MasterIter):
    pass


_MASTERS = weakref.WeakKeyDictionary()


def get_new_master(auto_filter, master, npoints):
    new_master = _MASTERS.get(master)
    if new_master is None:
        new_master = _get_new_master(auto_filter, master, npoints)
        _MASTERS[master] = new_master
    return new_master


def _get_new_master(auto_filter, master, npoints):
    try:
        iter(master)
    except TypeError:
        return _Master(auto_filter, master, npoints=npoints)
    else:
        # check if it Lima
        if isinstance(master, lima.LimaAcquisitionMaster):
            return _Lima(auto_filter, master, npoints=npoints)
        else:
            return _MasterIter(auto_filter, master, npoints=npoints)


def get_new_slave(auto_filter, slave, npoints):
    if isinstance(slave, chain.AcquisitionMaster):
        return get_new_master(auto_filter, slave, npoints)
    try:
        iter(slave)
    except TypeError:  # not iterable
        return _Slave(auto_filter, slave, npoints=npoints)
    else:  # can be iterable
        return _SlaveIter(auto_filter, slave, npoints=npoints)
