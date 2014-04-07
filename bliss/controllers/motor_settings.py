
from bliss.common import event

class ControllerAxisSettings:

    def __init__(self):
        self.setting_names = ["velocity", "position", "state"]
        self.convert_funcs = {
            "velocity": float,
            "position": float,
            "state": str}
        self.axis_settings_dict = dict()

    def add(self, setting_name, convert_func=str):
        self.setting_names.append(setting_name)
        self.convert_funcs[setting_name] = convert_func

    def set(self, axis, setting_name, value, write=False):
        settings = self.axis_settings_dict.setdefault(
            axis,
            dict(zip(self.setting_names, (None,) * len(self.setting_names))))
        convert_func = self.convert_funcs.get(setting_name, str)
        settings[setting_name] = convert_func(value)

        if write:
            event.send(axis, "write_setting", axis, setting_name, settings[setting_name])

        event.send(axis, setting_name, settings[setting_name])

    def get(self, axis, setting_name):
        return self.axis_settings_dict[axis][setting_name]


class AxisSettings:
    
    def __init__(self, axis):
        self.__axis = axis

    def set(self, setting_name, value):
        return self.__axis.controller.axis_settings.set(self.__axis, setting_name, value)

    def get(self, setting_name):
        return self.__axis.controller.axis_settings.get(self.__axis, setting_name) 
