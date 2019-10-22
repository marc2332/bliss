import gevent
import gevent.lock

from bliss.controllers.wago.wago import (\
    ModulesConfig, 
    WagoController,
    get_wago_comm,
)
from bliss.config.channels import Channel
from bliss.common import event
from bliss import global_map

def build_wago_mapping(single_model=False, channel=0, has_foil=False):
    STATUS_MODULE = [
        "750-436,status,status,status,status",
        "750-436,_,_,_,_,status,status,status,status",
    ]
    SINGLE_CONTROL_MODULE = "750-530,screen,screen,led,led,gain,gain,gain,gain"
    CONTROL_MODULE = [
        "750-530,screen,screen,led,led,gain,gain,gain,gain\n"
        "750-530,_,_,_,_,_,_,_,_",
        "750-530,_,_,_,_,_,_,_,_\n"
        "750-530,screen,screen,led,led,gain,gain,gain,gain"
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

class EBV:
    PULSE_INDEX = {
       "led_on": 0,
       "led_off": 1,
       "screen_in": 1,
       "screen_out": 0
    }

    def __init__(self, name, config_node):
        self.name = name
        self._single_model = config_node.get("single_model", False)
        self._channel = config_node.get("channel", 0)
        self._has_foil = config_node.get("has_foil", False)

        self._led_status = Channel(
            f"{name}:led_status",
            default_value="UNKNOWN",
            callback=self.__led_status_changed
        )
        self._screen_status = Channel(
            f"{name}:screen_status",
            default_value="UNKNOWN",
            callback=self.__screen_status_changed
        )
        self._diode_range = Channel(
            f"{name}:diode_range",
            callback=self.__diode_range_changed
        )
        self._foil_status = Channel(
            f"{name}:foil_status",
            default_value="UNKNOWN",
            callback=self.__foil_status_changed
        )

        self.__comm_lock = gevent.lock.RLock()
        mapping = build_wago_mapping(self._single_model, self._channel, self._has_foil)
        comm = get_wago_comm(config_node)
        self.controller = WagoController(comm, mapping)

        self.initialize()

        global_map.register(
            self,
            parents_list=["ebv"],
            children_list=[self.controller],
            tag=f"EBV({self.name})",
        )

    def initialize(self):
        self.controller.connect()
        self.__update()

    def __led_status_changed(self, state):
        event.send(self, "led_status", state)

    def __screen_status_changed(self, state):
        event.send(self, "screen_status", state)

    def __diode_range_changed(self, value):
        event.send(self, "diode_range", value)

    def __foil_status_changed(self, state):
        event.send(self, "foil_status", state)

    def __update(self):
        self.__update_state()
        self.__update_foil_state()

    def __update_state(self):
        with self.__comm_lock:
            status = self.controller.get("status")
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
                status = self.controller.get("foil_status")
            if status[0] and not status[1]:
                self._foil_status.value = "IN"
            elif not status[0] and status[1]:
                self._foil_status.value = "OUT"
            else:
                self._foil_status.value = "UNKNOWN"
       
    def __pulse_command(self, name, value): 
        index = self.PULSE_INDEX[value]
        with self.__comm_lock:
            set_value = [0, 0]
            self.controller.set(name, set_value)
            gevent.sleep(0.01)
            set_value[index] = 1
            self.controller.set(name, set_value)
            set_value[index] = 0
            gevent.sleep(0.01)
            self.controller.set(name, set_value)
        
    def __info__(self):
        self.__update()
        #info = f"Wago controller : {self.controller.client.host}\n"
        info = f"EBV Status:\n"
        info += f"    screen : {self._screen_status.value}\n"
        info += f"    led    : {self._led_status.value}\n"
        info += f"    foil   : {self._foil_status.value}\n"
        return info

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

    def led_on(self):
        self.__pulse_command("led", "led_on")
        
    def led_off(self):
        self.__pulse_command("led", "led_off")

    def screen_in(self):
        self.__pulse_command("screen", "screen_in")
  
    def screen_out(self):
        self.__pulse_command("screen", "screen_out")

    def foil_in(self):
        if not self._has_foil:
           raise RuntimeError(f"No foil on EBV [{self.name}]")
        with self.__comm_lock:
           self.controller.set("foil_cmd", True)

    def foil_out(self):
        if not self._has_foil:
           raise RuntimeError(f"No foil on EBV [{self.name}]")
        with self.__comm_lock:
           self.controller.set("foil_cmd", False)
