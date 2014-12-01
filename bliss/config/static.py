import yaml

def load_cfg(filename):
    with open(filename, 'r') as f:
        return yaml.load(f)


def load_cfg_fromstring(cfg_string):
   return yaml.load(cfg_string)
