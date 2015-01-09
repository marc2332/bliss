
from bliss.common import event
from gevent import _threading
import gevent.queue
import gevent.event
import gevent
import atexit

SETTINGS_WRITER_THREAD = None
SETTINGS_WRITER_QUEUE = None 
SETTINGS_WRITER_WATCHER = None 


def wait_settings_writing():
    if SETTINGS_WRITER_QUEUE:
        SETTINGS_WRITER_QUEUE.put((None, None, None))
        SETTINGS_WRITER_WATCHER.wait()


def write_settings():
    global SETTINGS_WRITER_WATCHER
    SETTINGS_WRITER_WATCHER.clear()
    try:
        while True:
            axis, setting_name, value = SETTINGS_WRITER_QUEUE.get()
            if axis is None:
                break
            event.send(
                axis, "write_setting", axis.config, setting_name, value, True)
    finally:
        SETTINGS_WRITER_WATCHER.set()


class ControllerAxisSettings:

    def __init__(self):
        self.setting_names = ["velocity", "position", "dial_position", "state", "offset", "acceleration", "low_limit", "high_limit"]
        self.convert_funcs = {
            "velocity": float,
            "position": float,
            "dial_position": float,
            "state": str,
            "offset": float,
            "low_limit": float,
            "high_limit": float,
            "acceleration": float }
        self.axis_settings_dict = dict()

        from bliss.config import motors as config
        global SETTINGS_WRITER_THREAD
        global SETTINGS_WRITER_QUEUE
        global SETTINGS_WRITER_WATCHER
        if SETTINGS_WRITER_THREAD is None:
            if config.BACKEND == 'xml': 
                SETTINGS_WRITER_QUEUE = _threading.Queue()
                SETTINGS_WRITER_WATCHER = _threading.Event()
                SETTINGS_WRITER_WATCHER.set()
                atexit.register(wait_settings_writing)
                if SETTINGS_WRITER_THREAD is None:
                   SETTINGS_WRITER_THREAD = _threading.start_new_thread(
                        write_settings, ())
            else:
                SETTINGS_WRITER_QUEUE = gevent.queue.Queue()
                SETTINGS_WRITER_WATCHER = gevent.event.Event()
                SETTINGS_WRITER_WATCHER.set()
                if SETTINGS_WRITER_THREAD is None:
                    SETTINGS_WRITER_THREAD = gevent.spawn(write_settings)

    def add(self, setting_name, convert_func=str):
        self.setting_names.append(setting_name)
        self.convert_funcs[setting_name] = convert_func

    def load_from_config(self, axis):
        from bliss.config import motors as config
        for setting_name in self.setting_names:
            if setting_name in ("state", "position"):
                continue
            try:
                setting_value = config.get_axis_setting(axis, setting_name)
            except RuntimeError:
                # no settings in config.
                return
            if setting_value is None:
                continue
            self._set_setting(axis, setting_name, setting_value)

    def _settings(self, axis):
        return self.axis_settings_dict.setdefault(
            axis,
            dict(zip(self.setting_names, (None,) * len(self.setting_names))))

    def _set_setting(self, axis, setting_name, value):
        settings = self._settings(axis)
        convert_func = self.convert_funcs.get(setting_name, str)
        setting_value = convert_func(value)
        settings[setting_name] = setting_value
        return setting_value

    def set(self, axis, setting_name, value, write=True):
        old_value = self.get(axis, setting_name)
        if value == old_value:
            return

        setting_value = self._set_setting(axis, setting_name, value)

        if write:
            SETTINGS_WRITER_QUEUE.put((axis, setting_name, setting_value))

        event.send(axis, setting_name, setting_value)

    def get(self, axis, setting_name):
        settings = self._settings(axis)
        return settings.get(setting_name)


class AxisSettings:

    def __init__(self, axis):
        self.__axis = axis

    def set(self, setting_name, value, write=True):
        return self.__axis.controller.axis_settings.set(
            self.__axis, setting_name, value, write)

    def get(self, setting_name):
        return self.__axis.controller.axis_settings.get(
            self.__axis, setting_name)

    def load_from_config(self):
        return self.__axis.controller.axis_settings.load_from_config(
            self.__axis)
