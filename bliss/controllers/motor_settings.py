from bliss.common import event


class AxisSettings:

    def __init__(self):
        self.setting_names = ["velocity", "position", "state"]
        self.convert_funcs = {
            "velocity": float,
            "position": float,
            "state": str}
        self.axis_settings_dict = dict()
        self.axis_settings_class = None
        #self.state_updated_callback = None

    def add(self, setting_name, convert_func):
        self.setting_names.append(setting_name)
        self.convert_funcs[setting_name] = convert_func

    def set(self, axis, setting_name, value):
        settings = self.axis_settings_dict.setdefault(
            axis,
            dict(zip(self.setting_names, (None,) * len(self.setting_names))))
        convert_func = self.convert_funcs.get(setting_name, str)
        settings[setting_name] = convert_func(value)
        event.send(axis, setting_name, settings[setting_name])

    def get(self, axis, setting_name):
        return self.axis_settings_dict[axis][setting_name]
