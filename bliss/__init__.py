import os
import sys
from bliss.common.scans import *
from bliss.common.task_utils import task, cleanup, error_cleanup
from bliss import setup_globals
try:
    from bliss.config import static
except ImportError:
    sys.excepthook(*sys.exc_info())

def setup(setup_file=None, env_dict=None, verbose=True):
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

            if verbose:
                print "Reading setup file '%s`" % setup_file_path

            setattr(setup_globals, "SETUP_FILE", setup_file_path)

            if env_dict is None:
                # does Python run in interactive mode?
                import __main__ as main
                if not hasattr(main, '__file__'):
                    # interactive interpreter 
                    env_dict = main.__dict__
                else:
                    env_dict = globals()

            _load_config(env_dict,verbose) 

            try:
                execfile(setup_file_path, env_dict) #setup_globals.__dict__) 
            finally:
                for obj_name, obj in env_dict.iteritems():
                    setattr(setup_globals, obj_name, obj) 

            if verbose:
                print "Done."
            return True
    raise RuntimeError("No setup file.")

def _load_config(env_dict, verbose=True):
    try:
        cfg = static.get_config()
    except:
        sys.excepthook(*sys.exc_info())
        return        

    cfg.reload()
 
    for item_name in cfg.names_list:
        if verbose:
            print "Initializing '%s`" % item_name
        try:
            o = cfg.get(item_name)
        except:
            sys.excepthook(*sys.exc_info())
        else:
            env_dict[item_name] = o
            setattr(setup_globals, item_name, o)
            del o

def load_script(script_module_name, path=None):
    if path is None:
        setup_file_path = setup_globals.SETUP_FILE
        path = os.path.join(os.path.dirname(setup_file_path), "scripts")

    if not os.path.isdir(path):
        raise RuntimeError("Scripts directory '%s` does not exist." % path)
    if not path in sys.path:
        sys.path.insert(0, path)

    try:
        script_module = __import__(script_module_name, globals(), {}, [])
    except Exception:
        sys.excepthook(*sys.exc_info())
    else:
        for k, v in script_module.__dict__.iteritems():
            script_module.__builtins__[k] = v

