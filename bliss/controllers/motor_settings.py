
from bliss.common import event
from gevent import _threading

SETTINGS_WRITER_THREAD = None
SETTINGS_WRITER_QUEUE = _threading.Queue()


def write_settings():
    while True:
        axis, setting_name, value = SETTINGS_WRITER_QUEUE.get()
        event.send(
            axis, "write_setting", axis.config, setting_name, value, True)


class ControllerAxisSettings:

    def __init__(self):
        self.setting_names = ["velocity", "position", "state", "offset"]
        self.convert_funcs = {
            "velocity": float,
            "position": float,
            "state": str,
            "offset": float}
        self.axis_settings_dict = dict()

        global SETTINGS_WRITER_THREAD
        if SETTINGS_WRITER_THREAD is None:
            SETTINGS_WRITER_THREAD = _threading.start_new_thread(
                write_settings, ())

    def add(self, setting_name, convert_func=str):
        self.setting_names.append(setting_name)
        self.convert_funcs[setting_name] = convert_func

    def load_from_config(self, axis):
        for setting_name in self.setting_names:
            if setting_name in ("state", "position"):
                continue
            try:
                setting_value = axis.config.config_dict[
                    "settings"].get(
                    setting_name)
            except KeyError:
                # no settings in config.
                return
            if setting_value is None:
                continue
            self._set_setting(axis, setting_name, setting_value["value"])

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
