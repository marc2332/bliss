
from bliss.config import settings

from bliss.common.scans import ct
from bliss.controllers.counter import CalcCounterController
from bliss.common.counter import IntegratingCounter
from bliss.scanning.acquisition.calc import CalcCounterAcquisitionSlave


class BackgroundCalcCounterController(CalcCounterController):
    def __init__(self, name, config):

        self.background_object = config.get("open_close", None)

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
                name = o_cnt.name
                self._integration_time_index[self.tags[name]] = 0
        return CalcCounterAcquisitionSlave(
            self, acq_devices, acq_params, ctrl_params=ctrl_params
        )

    def get_default_chain_parameters(self, scan_params, acq_params):
        int_time = scan_params.get("count_time", None)
        if int_time is not None:
            self._integration_time = int_time
            for o_cnt in self._output_counters:
                name = o_cnt.name
                self._integration_time_index[self.tags[name]] = 0
        return acq_params

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
                # Close beam
                background_object_state = self.background_object.state
                self.background_object.close()

                # take background
                if self.background_object.state == "CLOSED":
                    self.take_background_data(time)
                    if background_object_state == "OPEN":
                        self.background_object.open()
                else:
                    print(
                        "Close functions did not succeed, Backgrounds have not been changed !!!"
                    )

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
