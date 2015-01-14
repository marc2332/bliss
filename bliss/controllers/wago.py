import wago_client

class wago:
  def __init__(self, name, config_tree):
    self.name = name
    self.wago_ip = config_tree["controller_ip"]
    self.controller = None
    self.mapping = ""
   
    mapping = []
    for module in config_tree["mapping"]:
      module_type = module["type"]
      logical_names = module["logical_names"]
      mapping.append("%s,%s" % (module_type, logical_names))
    self.mapping = "\n".join(mapping)

  def connect(self):
    self.controller = wago_client.connect(self.wago_ip)
    self.controller.set_mapping(self.mapping)

  def set(self, *args, **kwargs):
    if self.controller is None:
      self.connect()
    return self.controller.set(*args, **kwargs)

  def get(self, *args, **kwargs):
    if self.controller is None:
      self.connect()
    return self.controller.get(*args, **kwargs)
