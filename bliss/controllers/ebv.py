
import numpy
import gevent
import gevent.lock

from bliss.controllers.wago.wago import ModulesConfig, WagoController, get_wago_comm
from bliss.config.channels import Channel
from bliss.common.counter import SamplingCounter
from bliss.controllers.counter import SamplingCounterController, counter_namespace
from bliss.common import event
from bliss import global_map
from bliss.common.logtools import log_critical

from bliss.controllers.lima.lima_base import Lima
from bliss.common.utils import autocomplete_property
from bliss.common.tango import DeviceProxy
from bliss.scanning.acquisition.counter import SamplingCounterAcquisitionSlave

from bliss.flint.client.live_plots import LiveImagePlot

"""
# EBV mockup

- controller: EBV
  plugin: bliss
  name: bv1
  class: EBV
  wago_controller: $ebv_wago_simulator
  single_model: False
  has_foil: False
  channel: 0
  counter_name: ebv_diode
  camera_tango_url: id00/limaccds/simulator2


- name: ebv_wago_simulator
  plugin: bliss
  module: wago.wago
  class: WagoMockup
  modbustcp:
      url: localhost
  ignore_missing: True
  mapping:
      - type: 750-436
        logical_names: status,status,status,status
      - type: 750-530
        logical_names: screen,screen,led,led,gain,gain,gain,gain
      - type: 750-530
        logical_names: _,_,_,_,_,_,_,_
      - type: 750-479
        logical_names: current


- name: mybpm
  plugin: bliss
  module: ebv
  class: BpmController
  camera_tango_url: idxx/limaccds/camname
"""


def build_wago_mapping(single_model=False, channel=0, has_foil=False):
    STATUS_MODULE = [
        "750-436,status,status,status,status",
        "750-436,_,_,_,_,status,status,status,status",
    ]
    SINGLE_CONTROL_MODULE = "750-530,screen,screen,led,led,gain,gain,gain,gain"
    CONTROL_MODULE = [
        "750-530,screen,screen,led,led,gain,gain,gain,gain\n" "750-530,_,_,_,_,_,_,_,_",
        "750-530,_,_,_,_,_,_,_,_\n" "750-530,screen,screen,led,led,gain,gain,gain,gain",
    ]
    CURRENT_MODULE = ["750-479,current", "750-479,_,current"]
    FOIL_STATUS_MODULE = [
        "750-436,foil_status,foil_status",
        "750-436,_,_,foil_status,foil_status",
    ]
    FOIL_CONTROL_MODULE = ["750-504,foil_cmd", "750-504,_,foil_cmd"]

    modules = list()
    if single_model is True:
        modules.append(STATUS_MODULE[0])
        modules.append(SINGLE_CONTROL_MODULE)
        modules.append(CURRENT_MODULE[0])
    else:
        modules.append(STATUS_MODULE[channel])
        if has_foil:
            modules.append(FOIL_STATUS_MODULE[channel])
        modules.append(CONTROL_MODULE[channel])
        if has_foil:
            modules.append(FOIL_CONTROL_MODULE[channel])
        modules.append(CURRENT_MODULE[channel])
    mapstr = "\n".join(modules)
    return ModulesConfig(mapstr, ignore_missing=True)


# --------------- DIODE COUNTER ---------------------------
class EBVDiodeRange:
    def __init__(self, wago_value, str_value, float_value):
        self.wago_value = wago_value
        self.name = str_value
        self.value = float_value


class EBVCounterController(SamplingCounterController):
    def __init__(self, ebv_device, diode_name, register_counters=False):
        super().__init__(ebv_device.name, register_counters=register_counters)
        self._ebv_device = ebv_device
        self._diode_name = diode_name

    def read(self, counter):
        if counter.name == self._diode_name:
            return self._ebv_device.current


# --------------- BPM COUNTERS ---------------------------
class BpmCounter(SamplingCounter):
    """EBV BPM sampling counter."""

    def __init__(self, name, value_index, controller, unit=None, mode="MEAN"):
        super().__init__(name, controller, unit=unit, mode=mode)
        self.__value_index = value_index

    @property
    def value_index(self):
        return self.__value_index


class BpmAcqSlave(SamplingCounterAcquisitionSlave):
    def prepare_device(self):

        self.device._prepare_cam_proxy()

        self._orig_expo = None
        # check expo <= count_time
        expo = self.device._acq_expo
        if expo > self.count_time:
            # self._orig_expo = expo
            # self.device.exposure = self.count_time
            msg = (
                f"\nWarning: {self.device._cam_tango_url}: exposure_time > count_time! "
            )
            # msg += f"Exposure_time set to {self.count_time} (for this scan only)\n"
            print(msg)

    def start_device(self):
        pass

    def stop_device(self):
        if self._orig_expo is not None:
            self.device.exposure = self._orig_expo


class BpmController(SamplingCounterController):
    def __init__(self, name, config, register_counters=True):

        super().__init__(name, register_counters=register_counters)

        self._config = config
        self._cam_tango_url = config["camera_tango_url"]
        self._cam_proxy = self._get_proxy()
        self._bpm_proxy = self._get_proxy(Lima._BPM)

        self._acq_mode = 0
        self._acq_expo = None
        self._is_live = False

        self._BPP2DTYPE = {
            "Bpp8": "uint8",
            "Bpp8S": "int8",
            "Bpp10": "uint16",
            "Bpp10S": "int16",
            "Bpp12": "uint16",
            "Bpp12S": "int16",
            "Bpp14": "uint16",
            "Bpp14S": "int16",
            "Bpp16": "uint16",
            "Bpp16S": "int16",
            "Bpp32": "uint32",
            "Bpp32S": "int32",
            "Bpp32F": "float32",
        }

        self.create_counter(BpmCounter, "acq_time", 0, unit="s", mode="SINGLE")
        self.create_counter(BpmCounter, "intensity", 1, mode="MEAN")
        self.create_counter(BpmCounter, "x", 2, unit="px", mode="MEAN")
        self.create_counter(BpmCounter, "y", 3, unit="px", mode="MEAN")
        self.create_counter(BpmCounter, "fwhm_x", 4, unit="px", mode="MEAN")
        self.create_counter(BpmCounter, "fwhm_y", 5, unit="px", mode="MEAN")
        # self.create_counter(BpmCounter, "frameno", 6, unit="", mode='SINGLE')

        self._get_img_data_info()
        self._plot = LiveImagePlot(self._snap_and_get_image)

    def __info__(self):

        info_str = f"Bpm [{self._cam_tango_url}] \n\n"

        info_str += f"    exposure : {self.exposure} s\n"
        info_str += f"    size     : {self.size}\n"
        info_str += f"    binning  : {self.bin}\n"
        info_str += f"    roi      : {self.roi}\n"
        info_str += f"    flip     : {self.flip}\n"
        info_str += f"    rotation : {self.rotation}\n"
        info_str += f"\n"

        return info_str

    def _get_proxy(self, type_name="LimaCCDs"):
        if type_name == "LimaCCDs":
            device_name = self._cam_tango_url
        else:
            main_proxy = self._cam_proxy
            device_name = main_proxy.command_inout(
                "getPluginDeviceNameFromType", type_name.lower()
            )
            if not device_name:
                raise RuntimeError(
                    "%s: '%s` proxy cannot be found" % (self.name, type_name)
                )
            if not device_name.startswith("//"):
                # build 'fully qualified domain' name
                # '.get_fqdn()' doesn't work
                db_host = main_proxy.get_db_host()
                db_port = main_proxy.get_db_port()
                device_name = "//%s:%s/%s" % (db_host, db_port, device_name)

        device_proxy = DeviceProxy(device_name)
        device_proxy.set_timeout_millis(1000 * 3)

        return device_proxy

    def _prepare_cam_proxy(self):

        self._plot.stop()

        # set required params
        self._cam_proxy.video_live = False
        self._cam_proxy.stopAcq()  # abortAcq()
        self._cam_proxy.acq_mode = "SINGLE"
        self._cam_proxy.acq_trigger_mode = "INTERNAL_TRIGGER"
        self._cam_proxy.acq_nb_frames = 1
        self._acq_expo = self._cam_proxy.acq_expo_time
        self._get_img_data_info()

    def _get_img_data_info(self):
        self._bpp = str(self._cam_proxy.image_type)
        self._sizes = self._cam_proxy.image_sizes
        self._shape = int(self._sizes[3]), int(self._sizes[2])
        self._depth = int(self._sizes[1])
        self._sign = int(self._sizes[0])
        self._dtype = self._BPP2DTYPE[self._bpp]
        self._dlen = self._shape[0] * self._shape[1] * self._depth

    def _get_image(self):
        data_type, data = self._cam_proxy.last_image
        if data_type == "DATA_ARRAY":
            return numpy.frombuffer(data[-self._dlen :], dtype=self._dtype).reshape(
                self._shape
            )
        else:
            raise TypeError(f"cannot handle data-type {data_type}")

    def _snap_and_get_image(self):
        if self._acq_mode == 0:
            self._cam_proxy.prepareAcq()
            self._cam_proxy.startAcq()

            gevent.sleep(self._acq_expo)

            with gevent.Timeout(2.0):
                while self._cam_proxy.last_image_ready == -1:
                    gevent.sleep(0.001)

            return self._get_image()

    def _snap_and_get_results(self):
        if self._acq_mode == 0:
            self._bpm_proxy.Start()
            self._cam_proxy.prepareAcq()
            self._cam_proxy.startAcq()

            gevent.sleep(self._acq_expo)

            with gevent.Timeout(2.0):
                data = []
                while len(data) == 0:
                    data = self._bpm_proxy.GetResults(0)
                    gevent.sleep(0.001)

            self._cam_proxy.stopAcq()
            # self._bpm_proxy.Stop() # temporary fix, see issue 1707

            return data

    def raw_read(self, prepare=True):

        if prepare:
            self._prepare_cam_proxy()

        return self.read_all(*self.counters)

    def read_all(self, *counters):
        # BPM data are : timestamp, intensity, center_x, center_y, fwhm_x, fwhm_y, frameno
        expected_result_size = 7
        all_result = self._snap_and_get_results()
        if len(all_result) != expected_result_size:
            log_critical(self, "One and only one value is expected per counter")

        indexes = [cnt.value_index for cnt in counters]
        result = list(all_result[indexes])
        return result

    def get_acquisition_object(self, acq_params, ctrl_params, parent_acq_params):
        return BpmAcqSlave(self, ctrl_params=ctrl_params, **acq_params)

    def start_live(self):
        self._prepare_cam_proxy()
        self._plot.start()

    def stop_live(self):
        self._plot.stop()

    def snap(self):
        self._prepare_cam_proxy()
        self._plot.plot(self._snap_and_get_image())

    @property
    def plot(self):
        return self._plot

    @property
    def exposure(self):
        self._acq_expo = self._cam_proxy.acq_expo_time
        return self._acq_expo

    @exposure.setter
    def exposure(self, expo):
        self._cam_proxy.acq_expo_time = expo
        self._acq_expo = expo

    @property
    def size(self):
        self._get_img_data_info()
        return [self._shape[1], self._shape[0]]

    @property
    def roi(self):
        return list(self._cam_proxy.image_roi)

    @roi.setter
    def roi(self, roi):
        self._cam_proxy.image_roi = roi

    @property
    def flip(self):
        return list(self._cam_proxy.image_flip)

    @flip.setter
    def flip(self, flip):
        self._cam_proxy.image_flip = flip

    @property
    def bin(self):
        return list(self._cam_proxy.image_bin)

    @bin.setter
    def bin(self, bin):
        self._cam_proxy.image_bin = bin

    @property
    def rotation(self):
        return self._cam_proxy.image_rotation

    @rotation.setter
    def rotation(self, rotation):
        self._cam_proxy.image_rotation = rotation

    # @property
    # def acq_time(self):
    #     return self._counters["acq_time"]


# --------- EBV CONTROLLER ----------------------------
class EBV:
    _WAGO_KEYS = [
        "status",
        "screen",
        "led",
        "gain",
        "current",
        "foil_status",
        "foil_cmd",
    ]
    _PULSE_INDEX = {"led_on": 0, "led_off": 1, "screen_in": 1, "screen_out": 0}
    _DIODE_RANGES = [
        EBVDiodeRange([True, False, True, False], "1mA", 1),
        EBVDiodeRange([False, False, True, False], "100uA", 1E1),
        EBVDiodeRange([True, True, False, False], "10uA", 1E2),
        EBVDiodeRange([False, True, False, False], "1uA", 1E3),
        EBVDiodeRange([True, False, False, False], "100nA", 1E4),
        EBVDiodeRange([False, False, False, False], "10nA", 1E5),
    ]

    _MISSING_BPM_MSG = (
        "\n================= No bpm attached ! ========================\n"
    )
    _MISSING_BPM_MSG += (
        "Add the 'camera_tango_url' key in the EBV configuration file \n"
    )
    _MISSING_BPM_MSG += (
        "Example in 'ebv.yml': 'camera_tango_url: id00/limaccds/simulator1' \n"
    )

    def __init__(self, name, config_node):
        self.name = name
        # --- config parsing
        self._single_model = config_node.get("single_model", False)
        self._channel = config_node.get("channel", 0)
        self._has_foil = config_node.get("has_foil", False)
        self._cnt_name = config_node.get("counter_name", "diode")
        self._cam_tango_url = config_node.get("camera_tango_url")

        # --- shared states
        self._led_status = Channel(
            f"{name}:led_status",
            default_value="UNKNOWN",
            callback=self.__led_status_changed,
        )
        self._screen_status = Channel(
            f"{name}:screen_status",
            default_value="UNKNOWN",
            callback=self.__screen_status_changed,
        )
        self._diode_range = Channel(
            f"{name}:diode_range", callback=self.__diode_range_changed
        )
        self._current_gain = self._DIODE_RANGES[0].value
        self._foil_status = Channel(
            f"{name}:foil_status",
            default_value="UNKNOWN",
            callback=self.__foil_status_changed,
        )

        # --- wago interface
        self.__comm_lock = gevent.lock.RLock()
        wctrl = config_node.get("wago_controller", None)
        if wctrl is None:
            mapping = build_wago_mapping(
                self._single_model, self._channel, self._has_foil
            )
            comm = get_wago_comm(config_node)
            self._wago = WagoController(comm, mapping)
            self._wkeys = dict(tuple([(name, name) for name in self._WAGO_KEYS]))
        else:
            self._wago = wctrl.controller
            wprefix = config_node.get("wago_prefix", "")
            self._wkeys = dict(
                tuple([(name, f"{wprefix}{name}") for name in self._WAGO_KEYS])
            )

        # --- diode counter controller
        self._counter_controller = EBVCounterController(
            self, self._cnt_name, register_counters=False
        )
        self._diode_counter = self._counter_controller.create_counter(
            SamplingCounter, self._cnt_name, unit="mA"
        )

        # --- bpm counters controller

        if self._cam_tango_url:
            self._bpm = BpmController(self.name, config_node, register_counters=False)

        self.initialize()

        global_map.register(
            self,
            parents_list=["ebv", "counters"],
            # parents_list=["ebv",],
            children_list=[self._wago],
            tag=f"EBV({self.name})",
        )

    def initialize(self):
        self._wago.connect()
        self.__update()

    def __close__(self):
        self._wago.close()

    def __led_status_changed(self, state):
        event.send(self, "led_status", state)

    def __screen_status_changed(self, state):
        event.send(self, "screen_status", state)

    def __diode_range_changed(self, value):
        for gain in self._DIODE_RANGES:
            if gain.name == value:
                self._current_gain = gain.value
                break
        event.send(self, "diode_range", value)

    def __foil_status_changed(self, state):
        event.send(self, "foil_status", state)

    def wago_get(self, name):
        self.__wago_check_key(name)
        return self.__wago_get(name)

    def __wago_get(self, name):
        return self._wago.get(self._wkeys[name])

    def wago_set(self, name, value):
        self.__wago_check_key(name)
        self.__wago_set(name, value)

    def __wago_set(self, name, value):
        self._wago.set(self._wkeys[name], value)

    def __wago_check_key(self, name):
        if name not in self._WAGO_KEYS:
            raise ValueError(
                "Invalid key name. Should be one of {0}".format(self._WAGO_KEYS)
            )

    def __update(self):
        self.__update_state()
        self.__update_foil_state()
        self.__update_diode_range()

    def __update_state(self):
        with self.__comm_lock:
            status = self.__wago_get("status")
        # --- screen status
        if status[0] and not status[1]:
            screen = "IN"
        elif not status[0] and status[1]:
            screen = "OUT"
        else:
            screen = "UNKNOWN"
        self._screen_status.value = screen
        # --- led status
        if status[2]:
            self._led_status.value = "ON"
        else:
            self._led_status.value = "OFF"

    def __update_foil_state(self):
        if not self._has_foil:
            self._foil_status.value = "NONE"
        else:
            with self.__comm_lock:
                status = self.__wago_get("foil_status")
            if status[0] and not status[1]:
                self._foil_status.value = "IN"
            elif not status[0] and status[1]:
                self._foil_status.value = "OUT"
            else:
                self._foil_status.value = "UNKNOWN"

    def __update_diode_range(self):
        with self.__comm_lock:
            gain_value = self.__wago_get("gain")
        for gain in self._DIODE_RANGES:
            if gain_value == gain.wago_value:
                self._diode_range.value = gain.name
                break

    def __pulse_command(self, name, value):
        index = self._PULSE_INDEX[value]
        with self.__comm_lock:
            set_value = [0, 0]
            self.__wago_set(name, set_value)
            gevent.sleep(0.01)
            set_value[index] = 1
            self.__wago_set(name, set_value)
            set_value[index] = 0
            gevent.sleep(0.01)
            self.__wago_set(name, set_value)

    def __info__(self):
        self.__update()
        try:
            wname = f"Wago({self._wago.client.host})"
        except Exception:
            wname = self._wago.comm
        info_str = f"EBV [{self.name}] {wname}\n"
        try:
            info_str += f"    screen : {self._screen_status.value}\n"
            info_str += f"    led    : {self._led_status.value}\n"
            info_str += f"    foil   : {self._foil_status.value}\n"
            info_str += f"    diode range   : {self._diode_range.value}\n"
            info_str += f"    diode current : {self.current:.6g} mA\n"

        except Exception:
            info_str += "!!! Failed to read EBV status !!!"

        if self._cam_tango_url:
            info_str += "\n"
            info_str += self._bpm.__info__()

        return info_str

    @autocomplete_property
    def counters(self):
        all_counters = list(self._counter_controller.counters)
        if self._cam_tango_url:
            all_counters += list(self._bpm.counters)
        return counter_namespace(all_counters)

    @autocomplete_property
    def bpm(self):
        if not self._cam_tango_url:
            raise AttributeError(self._MISSING_BPM_MSG)
        return self._bpm

    @property
    def show_beam(self):
        if self._cam_tango_url:
            self._bpm.start_live()

    @property
    def wago(self):
        return self._wago

    @property
    def diode(self):
        return self._diode_counter

    @property
    def x(self):
        if not self._cam_tango_url:
            raise AttributeError(self._MISSING_BPM_MSG)
        return self._bpm._counters["x"]

    @property
    def y(self):
        if not self._cam_tango_url:
            raise AttributeError(self._MISSING_BPM_MSG)
        return self._bpm._counters["y"]

    @property
    def intensity(self):
        if not self._cam_tango_url:
            raise AttributeError(self._MISSING_BPM_MSG)
        return self._bpm._counters["intensity"]

    @property
    def fwhm_x(self):
        if not self._cam_tango_url:
            raise AttributeError(self._MISSING_BPM_MSG)
        return self._bpm._counters["fwhm_x"]

    @property
    def fwhm_y(self):
        if not self._cam_tango_url:
            raise AttributeError(self._MISSING_BPM_MSG)
        return self._bpm._counters["fwhm_y"]

    @property
    def screen_status(self):
        self.__update_state()
        return self._screen_status.value

    @property
    def led_status(self):
        self.__update_state()
        return self._led_status.value

    @property
    def foil_status(self):
        self.__update_foil_state()
        return self._foil_status.value

    @property
    def diode_range_available(self):
        return [gain.name for gain in self._DIODE_RANGES]

    @property
    def diode_range(self):
        self.__update_diode_range()
        return self._diode_range.value

    @diode_range.setter
    def diode_range(self, value):
        for gain in self._DIODE_RANGES:
            if gain.name == value:
                with self.__comm_lock:
                    self.__wago_set("gain", gain.wago_value)
                self.__update_diode_range()
                return
        raise ValueError(f"Invalid diode range [{value}]")

    @property
    def diode_gain(self):
        self.__update_diode_range()
        return self._current_gain

    @diode_gain.setter
    def diode_gain(self, value):
        try:
            askval = float(value)
        except Exception:
            raise ValueError(f"Invalid diode gain [{value}]")
        set_gain = None
        all_gain = list(self._DIODE_RANGES)
        all_gain.reverse()
        for gain in all_gain:
            if gain.value >= askval:
                set_gain = gain
        if set_gain is not None:
            with self.__comm_lock:
                self.__wago_set("gain", set_gain.wago_value)
            self.__update_diode_range()
        else:
            raise ValueError(f"Cannot adjust gain for [{value}]")

    @property
    def raw_current(self):
        with self.__comm_lock:
            value = self.__wago_get("current")
        return float(value)

    @property
    def current(self):
        return self.raw_current / (10.0 * self._current_gain)

    def led_on(self):
        self.__pulse_command("led", "led_on")
        self.__update_state()

    def led_off(self):
        self.__pulse_command("led", "led_off")
        self.__update_state()

    def screen_in(self):
        self.__pulse_command("screen", "screen_in")
        self.__update_state()

    def screen_out(self):
        self.__pulse_command("screen", "screen_out")
        self.__update_state()

    def foil_in(self):
        if not self._has_foil:
            raise RuntimeError(f"No foil on EBV [{self.name}]")
        self.__set_foil(True)

    def foil_out(self):
        if not self._has_foil:
            raise RuntimeError(f"No foil on EBV [{self.name}]")
        self.__set_foil(False)

    def __set_foil(self, flag):
        with self.__comm_lock:
            self.__wago_set("foil_cmd", flag)
        self.__update_foil_state()
