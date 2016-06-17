# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

'''Shell (:term:`CLI` and Web based)'''

import os
import yaml
import sys
import logging
import functools

from bliss import setup_globals
from bliss.common.axis import Axis

try:
    from bliss.config import static
except ImportError:
    sys.excepthook(*sys.exc_info())

try:
    from tabulate import tabulate
except ImportError:
    pass

_log = logging.getLogger('bliss.shell')

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
    SETUP['session_name'] = session_id


def read_config(config_file=None):
    if config_file is None:
        config_file = SHELL_CONFIG_FILE
    if not config_file:
        return
    with file(config_file, "r") as f:
        cfg = yaml.load(f.read())
        default_session = None

        for session_id in cfg.iterkeys():
            if default_session is None:
                default_session = str(session_id)

            setup_file = cfg[session_id]["setup-file"]
            if not os.path.isabs(setup_file):
                setup_file = os.path.join(os.path.dirname(os.path.abspath(config_file)), setup_file)

            set_setup_file(str(session_id), setup_file, cfg[session_id].get("config_objects"))

            try:
                synoptic_file = cfg[session_id]["synoptic"]["svg-file"]
            except KeyError:
                _log.warning('Unable to find synoptic file')
                _log.debug('Details:', exc_info=1)
            else:
                if not os.path.isabs(synoptic_file):
                    synoptic_file = os.path.join(os.path.dirname(os.path.abspath(config_file)), synoptic_file)
                set_synoptic_file(str(session_id), synoptic_file, cfg[session_id]["synoptic"]["elements"])

    return SETUP, SYNOPTIC, default_session


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


def initialize(config_file=None, session_name=None):
    user_ns = { "config": static.get_config() }
    if config_file:
        set_shell_config_file(config_file)

        SETUP, SYNOPTIC, default_session = read_config()
        session_id = session_name or default_session

        setup_file = SETUP.get(session_id, {}).get("file")
        config_objects_names = SETUP.get(session_id, {}).get("config_objects")

        resetup = functools.partial(setup, env_dict=user_ns,
                                    config_objects_names_list=config_objects_names)
        user_ns.update({"resetup": resetup, "SETUP_FILE": setup_file})

        resetup()
        return user_ns, session_id, (SETUP, SYNOPTIC)
    else:
        return user_ns,None,(None,None)
