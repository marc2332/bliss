# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
import numpy
import gevent
from gevent import event
from bliss.common.utils import grouped
from ..chain import AcquisitionDevice, AcquisitionChannel


class PIAcquisitionDevice(AcquisitionDevice):
    """
    Helper to read **Physik Instrumente** controller data recorder.
    """

    def __init__(self, pi_controller, npoints, count_time, trigger_source=None, **keys):
        """
        Args:
           pi_controller the pi motor controller
           i.e: px.controller if px is a motor
           count_time the sampling time of the data recorder for one point
           trigger_source if None will use the **trigger_type** to define it.
        """
        AcquisitionDevice.__init__(
            self, pi_controller, pi_controller.name, npoints=npoints, **keys
        )
        self.__motor_data_type = list()
        self.__external_input = 0
        self.__count_time = count_time
        self.__stopped = False
        self.__started = False
        self.__event = event.Event()
        self._nb_acq_points = 0
        self.__previous_data_len = None
        self.__triger_source = trigger_source

    @property
    def count_time(self):
        return self.__count_time

    @property
    def external_input(self):
        """
        Could define external trigger input.
        default 0 mean all
        """
        return self.__external_input

    @external_input.setter
    def external_input(self, value):
        self.__external_input = value

    def set_counters(self, *counters_params):
        """
        Configuration of the counters you want to record in the data recorder

        Args:
          counters_params should be a list of (counter_name, pi_motor, recorder_type...)
          i.e: set_counters('px', px, px.CURRENT_POSITION_OF_AXIS,
                            'py', py, py.CURRENT_POSITION_OF_AXIS)
        """
        nb_counters = len(counters_params) // 3
        if nb_counters * 3 != len(counters_params):
            raise RuntimeError(
                "Arguments must be grouped by 3 "
                "(counter_name,motor,recorder_type...)"
            )
        if (self.npoints * nb_counters) > self.device.get_data_max_len():
            raise RuntimeError(
                "The total number points ({0}) is more "
                "than the controller can handle ({1})".format(
                    self.npoints * nb_counters, self.device.get_data_max_len()
                )
            )
        self.channels[:] = [AcquisitionChannel(self, "timestamp", numpy.double, ())]
        self.__motor_data_type = list()
        for counter_name, motor, recorder_type in grouped(counters_params, 3):
            self.channels.append(
                AcquisitionChannel(self, counter_name, numpy.double, ())
            )
            self.__motor_data_type.extend((motor, recorder_type))

    def prepare(self):
        if not self.__motor_data_type:
            raise RuntimeError("Nothing to prepare, didn't call set_counters")

        self.device.set_recorder_data_type(*self.__motor_data_type)

    def start(self):
        self.__started = False
        self.__stopped = False
        self._nb_acq_points = 0
        if self.trigger_type == AcquisitionDevice.SOFTWARE:
            return
        self.trigger()

    def trigger(self):
        if self.__triger_source is not None:
            trigger_source = self.__triger_source
            data_len = self.device.get_data_len()
        elif self.trigger_type == AcquisitionDevice.SOFTWARE:
            trigger_source = self.device.IMMEDIATELY
            data_len = None
        else:
            trigger_source = self.device.EXTERNAL
            data_len = self.device.get_data_len()

        self.__previous_data_len = data_len if data_len > 0 else None
        self.device.start_recording(
            trigger_source, value=self.external_input, recorder_rate=self.count_time
        )
        self.__started = True
        self.__event.set()

    def stop(self):
        self.__stopped = True
        self.__event.set()

    def reading(self):
        while not self.__started and not self.__stopped:
            self.__event.wait()
            self.__event.clear()
        if self.__stopped:
            return

        # Wait data trigger
        if self.__previous_data_len is not None:
            while not self.__stopped:
                data_len = self.device.get_data_len()
                # received the trigger so start reading
                if data_len < self.__previous_data_len:
                    break
                gevent.sleep(0)

        while self._nb_acq_points < self.npoints and not self.__stopped:
            data = self.device.get_data(
                self._nb_acq_points, npoints=self.npoints - self._nb_acq_points
            )
            if data is not None:
                for channel, data_name in zip(self.channels, data.dtype.names):
                    channel.emit(data[data_name])
                self._nb_acq_points += len(data)
                gevent.idle()
            else:
                gevent.sleep(self.count_time / 2.0)
