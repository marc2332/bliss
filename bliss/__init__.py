SETUP_FILE = None
SYNOPTIC_FILE = None


def set_synoptic_file(synoptic_html_file):
    global SYNOPTIC_FILE
    SYNOPTIC_FILE = synoptic_html_file


def set_setup_file(setup_file):
    global SETUP_FILE
    SETUP_FILE = setup_file


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
