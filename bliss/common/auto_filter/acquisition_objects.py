# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
import weakref
import gevent
import numpy

from bliss.scanning.acquisition.motor import (
    VariableStepTriggerMaster as _VariableStepTriggerMaster
)
from bliss.scanning import chain
from bliss.scanning.acquisition import lima
from bliss.scanning.channel import AcquisitionChannel
from bliss.common import event


class VariableStepTriggerMaster(_VariableStepTriggerMaster):
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
                    # To be remove sleep to publish last point
                    gevent.sleep(1)
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
        self.__received_event = gevent.event.Event()
        self._auto_filter = auto_filter

    def prepare(self):
        return self.device.prepare()

    def start(self):
        return self.device.start()

    def stop(self):
        try:
            with gevent.Timeout(1.):
                while not self._all_point_rx():
                    self.__received_event.clear()
                    self.__received_event.wait()
        except gevent.Timeout:
            pass
        # print(f"stop {self.device}")
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

    def get_acquisition_metadata(self, *args, **kw):
        return self.device.get_acquisition_metadata(*args, **kw)

    def _all_point_rx(self):
        """
        Check that all point are received
        """
        current_point = self._auto_filter.current_point
        if not self.__last_point_rx:
            return True

        min_last_point = min(self.__last_point_rx.values())
        return min_last_point == current_point + 1 and not self.__pending_data

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
                if isinstance(previous_data, dict):  # Lima
                    self.__pending_data[channel_name] = channel_data
                else:
                    self.__pending_data[channel_name] = numpy.append(
                        previous_data, channel_data
                    )
        else:  # valid is True or False
            if valid:
                my_channel = self._name_2_channel[channel_name]
                # print(f"emit {channel_name} {self._auto_filter.current_point}")
                my_channel.emit(channel_data)

                corr_chan = self._name_2_corr_chan.get(channel_name)
                if corr_chan is not None:
                    corrected_data = self._auto_filter.corr_func(
                        last_point_rx, channel_name, channel_data
                    )
                    corr_chan.emit(corrected_data)

        if isinstance(channel_data, dict):  # Lima
            self.__last_point_rx[channel_name] = last_point_rx + 1
        else:
            self.__last_point_rx[channel_name] = last_point_rx + len(channel_data)
        self.__received_event.set()

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
                # print(f"emit {channel_name} {self._auto_filter.current_point}")
                channel.emit(data)

                corr_chan = self._name_2_corr_chan.get(channel_name)
                if corr_chan is not None:
                    corrected_data = self._auto_filter.corr_func(
                        point_nb, channel_name, data
                    )
                    corr_chan.emit(corrected_data)
            self.__received_event.set()


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
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.save_flag = False
        # hook emit of image channel
        if self.channels:
            channel = self.channels[0]
            channel_emit = channel.emit
            # Final number of scan points.
            self.nb_points_to_receive = self.npoints
            self.emit_event = gevent.event.Event()
            self._last_image_saved = -1

            def emit(data):
                if not data.get("in_prepare", False):
                    if self.save_flag:
                        # ask lima to save the current image
                        img_ready = data["last_image_ready"]
                        self.device.device.proxy.writeImage(img_ready)
                        self._last_image_saved += 1
                    data["last_image_saved"] = self._last_image_saved

                    self.nb_points_to_receive -= 1
                    self.emit_event.set()

                return channel_emit(data)

            channel.emit = emit

    def set_image_saving(self, directory, prefix, force_no_saving=False):
        self.device.set_image_saving(directory, prefix, force_no_saving)
        # force Manual saving
        self.device.acq_params["saving_mode"] = "MANUAL"
        self.save_flag = True if directory else False

    def new_data_received(self, event_dict=None, signal=None, sender=None):
        data = event_dict["data"]
        if data.get("in_prepare", False):
            # Need to fill channel description
            channel = self.channels[0]
            channel.description.update(
                {"acq_trigger_mode": self.device.acq_params["acq_trigger_mode"]}
            )
            if self.save_flag:
                channel.description.update(self.device._get_saving_description())
            channel.emit(data)
        else:
            super().new_data_received(event_dict, signal, sender)

    def stop(self):
        # wait last frame to be save + emit
        if self.channels and self.nb_points_to_receive:
            self.emit_event.clear()
            self.emit_event.wait(timeout=1.)

        self.device.stop()


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
    except (TypeError, NotImplementedError):
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
    except (TypeError, NotImplementedError):  # not iterable
        return _Slave(auto_filter, slave, npoints=npoints)
    else:  # can be iterable
        return _SlaveIter(auto_filter, slave, npoints=npoints)
