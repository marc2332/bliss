import os
import sys
import yaml

SETUP_FILE = dict()
SYNOPTIC = dict()


def set_synoptic_file(session_id, synoptic_svg_file, synoptic_elements):
    global SYNOPTIC
    s = SYNOPTIC.setdefault(session_id, dict())
    s["file"] = os.path.abspath(os.path.expanduser(synoptic_svg_file))
    s["elements"] = synoptic_elements


def set_setup_file(session_id, setup_file):
    global SETUP_FILE
    SETUP_FILE[session_id] = setup_file


def read_config(config_file):
    with file(config_file, "r") as f:
        cfg = yaml.load(f.read())

        for session_id in cfg.iterkeys():
            set_setup_file(session_id, os.path.join(os.path.dirname(config_file), cfg[session_id]["setup-file"]))
            set_synoptic_file(session_id, os.path.join(os.path.dirname(config_file), cfg[session_id]["synoptic"]["svg-file"]), cfg[session_id]["synoptic"]["elements"])


def setup(setup_file=None, env_dict=None):
    if env_dict: 
        setup_file = env_dict.get("SETUP_FILE") if setup_file is None else setup_file
    if setup_file is not None:
        if env_dict is not None:
            env_dict["SETUP_FILE"] = setup_file
        setup_file_path = os.path.abspath(os.path.expanduser(setup_file))
        if os.path.isfile(setup_file_path):
            setup_file_dir = os.path.dirname(setup_file_path)
            if not setup_file_dir in sys.path:
                sys.path.insert(0, setup_file_dir)
        execfile(setup_file_path, env_dict or globals())
