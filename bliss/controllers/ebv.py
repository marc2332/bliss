import gevent
import gevent.lock

from bliss.controllers.wago.wago import ModulesConfig, WagoController, get_wago_comm
from bliss.config.channels import Channel
from bliss.common.counter import SamplingCounter
from bliss.controllers.counter import SamplingCounterController
from bliss.common.utils import add_property
from bliss.common import event
from bliss import global_map


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


class EBVDiodeRange:
    def __init__(self, wago_value, str_value, float_value):
        self.wago_value = wago_value
        self.name = str_value
        self.value = float_value


class EBVCounterController(SamplingCounterController):
    def __init__(self, ebv_device, diode_name):
        super().__init__(ebv_device.name)
        self._ebv_device = ebv_device
        self._diode_name = diode_name

    def read(self, counter):
        if counter.name == self._diode_name:
            return self._ebv_device.current


class EBVCounter(SamplingCounter):
    def __call__(self, *args, **kwargs):
        return self


class EBV:
    _PULSE_INDEX = {"led_on": 0, "led_off": 1, "screen_in": 1, "screen_out": 0}
    _DIODE_RANGES = [
        EBVDiodeRange([True, False, True, False], "1mA", 1),
        EBVDiodeRange([False, False, True, False], "100uA", 1E1),
        EBVDiodeRange([True, True, False, False], "10uA", 1E2),
        EBVDiodeRange([False, True, False, False], "1uA", 1E3),
        EBVDiodeRange([True, False, False, False], "100nA", 1E4),
        EBVDiodeRange([False, False, False, False], "10nA", 1E5),
    ]

    def __init__(self, name, config_node):
        self.name = name
        # --- config parsing
        self._single_model = config_node.get("single_model", False)
        self._channel = config_node.get("channel", 0)
        self._has_foil = config_node.get("has_foil", False)
        self._cnt_name = config_node.get("counter_name", "diode")

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
        mapping = build_wago_mapping(self._single_model, self._channel, self._has_foil)
        comm = get_wago_comm(config_node)
        self._wago = WagoController(comm, mapping)

        self.initialize()

        # --- counter interface
        self._counter_controller = EBVCounterController(self, self._cnt_name)
        self._diode_counter = EBVCounter(
            self._cnt_name, self._counter_controller, unit="mA"
        )

        global_map.register(
            self,
            parents_list=["ebv"],
            children_list=[self._wago],
            tag=f"EBV({self.name})",
        )

    def initialize(self):
        self._wago.connect()
        self.__update()

    @property
    def diode(self):
        return self._diode_counter

    def counters(self):
        return self._counter_controller.counters

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

    def __update(self):
        self.__update_state()
        self.__update_foil_state()
        self.__update_diode_range()

    def __update_state(self):
        with self.__comm_lock:
            status = self._wago.get("status")
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
                status = self._wago.get("foil_status")
            if status[0] and not status[1]:
                self._foil_status.value = "IN"
            elif not status[0] and status[1]:
                self._foil_status.value = "OUT"
            else:
                self._foil_status.value = "UNKNOWN"

    def __update_diode_range(self):
        with self.__comm_lock:
            gain_value = self._wago.get("gain")
        for gain in self._DIODE_RANGES:
            if gain_value == gain.wago_value:
                self._diode_range.value = gain.name
                break

    def __pulse_command(self, name, value):
        index = self._PULSE_INDEX[value]
        with self.__comm_lock:
            set_value = [0, 0]
            self._wago.set(name, set_value)
            gevent.sleep(0.01)
            set_value[index] = 1
            self._wago.set(name, set_value)
            set_value[index] = 0
            gevent.sleep(0.01)
            self._wago.set(name, set_value)

    def __info__(self):
        self.__update()
        info_str = f"EBV [{self.name}] (wago: {self._wago.client.host})\n"
        try:
            info_str += f"    screen : {self._screen_status.value}\n"
            info_str += f"    led    : {self._led_status.value}\n"
            info_str += f"    foil   : {self._foil_status.value}\n"
            info_str += f"    diode range   : {self._diode_range.value}\n"
            info_str += f"    diode current : {self.current:.6g} mA\n"
        except:
            info_str += "!!! Failed to read EBV status !!!"
        return info_str

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
                    self._wago.set("gain", gain.wago_value)
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
        except:
            raise ValueError(f"Invalid diode gain [{value}]")
        set_gain = None
        all_gain = list(self._DIODE_RANGES)
        all_gain.reverse()
        for gain in all_gain:
            if gain.value >= askval:
                set_gain = gain
        if set_gain is not None:
            with self.__comm_lock:
                self._wago.set("gain", set_gain.wago_value)
            self.__update_diode_range()
        else:
            raise ValueError(f"Cannot adjust gain for [{value}]")

    @property
    def raw_current(self):
        with self.__comm_lock:
            value = self._wago.get("current")
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
            self._wago.set("foil_cmd", flag)
        self.__update_foil_state()
