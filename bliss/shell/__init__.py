import os
import yaml
import sys

SHELL_CONFIG_FILE = None
SYNOPTIC = dict()
SETUP = dict()

def set_shell_config_file(cfg_file):
    global SHELL_CONFIG_FILE
    if not os.path.isfile(cfg_file):
        raise RuntimeError("Config file '%s` does not exist." % cfg_file)
    SHELL_CONFIG_FILE = cfg_file


def set_synoptic_file(session_id, synoptic_svg_file, synoptic_elements):
    global SYNOPTIC
    s = SYNOPTIC.setdefault(session_id, dict())
    s["file"] = os.path.abspath(os.path.expanduser(synoptic_svg_file))
    s["elements"] = synoptic_elements


def set_setup_file(session_id, setup_file, config_objects_names):
    global SETUP
    if isinstance(config_objects_names, str):
        config_objects_names = config_objects_names.split()
    SETUP[session_id] = dict(file=os.path.abspath(os.path.expanduser(setup_file)), config_objects=config_objects_names)

def read_config(config_file=SHELL_CONFIG_FILE):
    if not config_file:
        return
    with file(config_file, "r") as f:
        cfg = yaml.load(f.read())

        for session_id in cfg.iterkeys():
            setup_file = cfg[session_id]["setup-file"]
            if not os.path.isabs(setup_file):
                setup_file = os.path.join(os.path.dirname(os.path.abspath(config_file)), setup_file)
            set_setup_file(session_id, setup_file, cfg[session_id].get("config_objects"))
            try:
                synoptic_file = cfg[session_id]["synoptic"]["svg-file"]
            except KeyError:
                sys.excepthook(*sys.exc_info())
            else:
                if not os.path.isabs(synoptic_file):
                    synoptic_file = os.path.join(os.path.dirname(os.path.abspath(config_file)), synoptic_file)
                set_synoptic_file(session_id, synoptic_file, cfg[session_id]["synoptic"]["elements"])
    return SETUP, SYNOPTIC
