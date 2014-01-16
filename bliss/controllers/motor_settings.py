import collections

class AxisSettings:
  def __init__(self):
    self.setting_names = ["velocity", "position",  "state"]
    self.convert_funcs = { "velocity": float,
                           "position": float }
    self.axis_settings_dict = dict()
    self.axis_settings_class = None

  def add(self, setting_name, convert_func):
    self.setting_names.append(setting_name)
    self.convert_funcs[setting_name]=convert_func

  def set(self, axis, setting_name, value):
    settings = self.axis_settings_dict.setdefault(axis, dict(zip(self.setting_names, (None,)*len(self.setting_names))))
    convert_func = self.convert_funcs.get(setting_name, str)
    settings[setting_name]=convert_func(value)

    if setting_name == "state":
      if callable(self.state_updated_callback):
        self.state_updated_callback(axis, self.get(axis, "state"))

  def set_from_config(self, axis, axis_config):
    for setting_name in self.setting_names:
      try:
        self.set(axis, setting_name, axis_config[setting_name].get('value'))
      except KeyError:
        continue

  def get(self, axis, setting_name):
    return self.axis_settings_dict[axis][setting_name]

