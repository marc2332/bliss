from __future__ import division

from gevent import monkey
monkey.patch_all(thread=False)

from bliss.controllers.motor import Controller, CalcController
from bliss.common.task_utils import *
from bliss.config.motors import load_cfg, load_cfg_fromstring, get_axis, get_encoder
from bliss.controllers.motor_group import Group
from bliss.common.scans import *
from bliss.common.task_utils import task, cleanup, error_cleanup
from bliss import setup_globals
from bliss.common.continuous_scan import Scan
from bliss.common.continuous_scan import AcquisitionChain
from bliss.common.continuous_scan import AcquisitionDevice
from bliss.common.continuous_scan import AcquisitionMaster
try:
    from bliss.config import static
except ImportError:
    sys.excepthook(*sys.exc_info())
import functools
import os
import sys

def setup(setup_file=None, env_dict=None, config_objects_names_list=None, verbose=True):
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

            _load_config(env_dict, config_objects_names_list, verbose) 

            env_dict['load_script']=functools.partial(_load_script, env_dict)

            try:
                execfile(setup_file_path, env_dict) 
            finally:
                for obj_name, obj in env_dict.iteritems():
                    setattr(setup_globals, obj_name, obj) 

            if verbose:
                print "Done."
            return True
    raise RuntimeError("No setup file.")

def _load_config(env_dict, names_list=None, verbose=True):
    try:
        cfg = static.get_config()
    except:
        sys.excepthook(*sys.exc_info())
        return        

    cfg.reload()
 
    if names_list is None:
        names_list = cfg.names_list
    for item_name in names_list:
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

def _load_script(env_dict, script_module_name, path=None):
    if path is None:
        setup_file_path = setup_globals.SETUP_FILE
        path = os.path.join(os.path.dirname(setup_file_path), "scripts")

    if not os.path.isdir(path):
        raise RuntimeError("Scripts directory '%s` does not exist." % path)
    if not path in sys.path:
        sys.path.insert(0, path)

    if script_module_name in sys.modules:
        reload_module = True
    else:
        reload_module = False
    try:
        script_module = __import__(script_module_name, globals(), {}, [])
    except Exception:
        sys.excepthook(*sys.exc_info())
    else:
        if reload_module:
            reload(script_module)
        for k, v in script_module.__dict__.iteritems():
            env_dict[k] = v
