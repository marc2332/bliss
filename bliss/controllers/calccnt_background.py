# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.config import settings

from bliss.common.scans import ct
from bliss.common.cleanup import cleanup
from bliss.controllers.counter import CalcCounterController
from bliss.common.counter import IntegratingCounter
from bliss.scanning.acquisition.calc import CalcCounterAcquisitionSlave
from bliss.common.logtools import user_print


class BackgroundCalcCounterController(CalcCounterController):
    def __init__(self, name, config):

        self.background_object = config.get("open_close", None)

        self.background_object_initial_state = "UNKNOWN"

        CalcCounterController.__init__(self, name, config)

        self._integration_time = None
        self._integration_time_index = {}

        background_setting_name = f"background_{self.name}"
        background_setting_default = {}
        for cnt in self.inputs:
            tag = self.tags[cnt.name]
            background_setting_default[tag] = 0.0
        self.background_setting = settings.HashSetting(
            background_setting_name, default_values=background_setting_default
        )

    def __info__(self):
        mystr = ""
        for cnt in self.outputs:
            tag = self.tags[cnt.name]
            background = self.background_setting[tag]
            mystr += f"{cnt.name} - {background}\n"
        bck_time = self.background_setting["background_time"]
        mystr += f"\nBackground Integration Time: {bck_time} [s]\n"

        return mystr

    def get_acquisition_object(
        self, acq_params, ctrl_params, parent_acq_params, acq_devices
    ):
        int_time = acq_params.get("count_time", None)
        if int_time is not None:
            self._integration_time = int_time
            for o_cnt in self._output_counters:
                self._integration_time_index[self.tags[o_cnt.name]] = 0
        return CalcCounterAcquisitionSlave(
            self, acq_devices, acq_params, ctrl_params=ctrl_params
        )

    def get_default_chain_parameters(self, scan_params, acq_params):
        int_time = scan_params.get("count_time", None)
        if int_time is not None:
            self._integration_time = int_time
            for o_cnt in self._output_counters:
                self._integration_time_index[self.tags[o_cnt.name]] = 0

        return super().get_default_chain_parameters(scan_params, acq_params)

    def get_input_counter_from_tag(self, tag):
        for cnt in self.inputs:
            if self.tags[cnt.name] == tag:
                return cnt

        return None

    def take_background(self, time=1.0, set_value=None):
        if set_value is not None:
            for cnt in self.inputs:
                tag = self.tags[cnt.name]
                self.background_setting[tag] = set_value
                self.background_setting["background_time"] = time
        else:
            if self.background_object is None:
                self.take_background_data(time)
            else:
                # Store initial state.
                self.background_object_initial_state = self.background_object.state

                # Close beam.
                self.background_object.close()

                # Take background.
                if self.background_object.state == "CLOSED":
                    with cleanup(self._close):
                        self.take_background_data(time)
                else:
                    user_print(
                        "Close functions did not succeed, Backgrounds have not been changed !!!"
                    )

    def _close(self):
        """ Re-open if initial state was OPEN"""
        if self.background_object_initial_state == "OPEN":
            self.background_object.open()

    def take_background_data(self, time):
        scan_ct = ct(time, self.inputs, run=False)
        scan_ct._data_watch_callback = None
        scan_ct.run()
        data_background = scan_ct.get_data()
        for cnt in self.inputs:
            tag = self.tags[cnt.name]
            background = data_background[cnt.name][0]
            self.background_setting[tag] = data_background[cnt.name][0]
            self.background_setting["background_time"] = time
            user_print(f"{cnt.name} - {background}")

    def calc_function(self, input_dict):
        value = {}
        for tag in input_dict.keys():
            cnt = self.get_input_counter_from_tag(tag)
            background = self.background_setting[tag]
            if isinstance(cnt, IntegratingCounter):
                background /= self.background_setting["background_time"]
                if isinstance(self._integration_time, list):
                    background *= self._integration_time[
                        self._integration_time_index[tag]
                    ]
                    self._integration_time_index[tag] = (
                        self._integration_time_index[tag] + 1
                    )
                else:
                    background *= self._integration_time

            value[tag] = input_dict[tag] - background

        return value
