import yaml
from .conductor.client import Client

def load_cfg(filename):
    cfg_string = Client.get_config_file(filename)
    return yaml.load(cfg_string)

def load_cfg_fromstring(cfg_string):
   return yaml.load(cfg_string)
