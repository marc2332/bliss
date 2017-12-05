# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import sys
from types import ModuleType
import functools

from bliss import setup_globals
from bliss.config import static
from bliss.config.conductor.client import get_config_file, get_python_modules, get_file

DEFAULT_SESSION = None


def get_default():
    return DEFAULT_SESSION


_importer_path = set()


class _StringImporter(object):
    BASE_MODULE_NAME_SPACE = 'bliss.setup'
    SUB_NAME_SPACE = 'scripts'

    def __init__(self, path, session_name):
        self._modules = dict()
        global_module_name_space = '%s.%s' % (self.BASE_MODULE_NAME_SPACE,
                                              self.SUB_NAME_SPACE)
        session_module_name_space = '%s.%s' % (self.BASE_MODULE_NAME_SPACE,
                                               session_name)
        for module_name, file_path in get_python_modules(path):
            for mod_namespace in (global_module_name_space, session_module_name_space):
                self._modules['%s.%s' %
                              (mod_namespace, module_name)] = file_path
        if self._modules:
            self._modules[self.BASE_MODULE_NAME_SPACE] = None
            self._modules['%s.%s' %
                          (self.BASE_MODULE_NAME_SPACE, self.SUB_NAME_SPACE)] = None
            self._modules['%s.%s' %
                          (self.BASE_MODULE_NAME_SPACE, session_name)] = None

    def find_module(self, fullname, path):
        if fullname in self._modules:
            return self
        return None

    def load_module(self, fullname):
        if not fullname in self._modules.keys():
            raise ImportError(fullname)

        file_name = self._modules.get(fullname)
        if file_name:
            data_file = get_config_file(file_name)
        else:
            file_name = '%s (__init__ memory)' % fullname
            data_file = ''         # empty __init__.py

        new_module = sys.modules.get(fullname,
                                     ModuleType(fullname))
        new_module.__loader__ = self
        module_filename = 'beacon://%s' % file_name
        new_module.__file__ = module_filename
        if file_name.find('__init__') > -1:
            new_module.__path__ = []
            new_module.__package__ = fullname
        else:
            new_module.__package__ = fullname.rpartition('.')[0]
        sys.modules.setdefault(fullname, new_module)
        c_code = compile(data_file, module_filename, 'exec')
        exec(c_code, new_module.__dict__)
        return new_module


def load_script(env_dict, script_module_name):
    module_name = '%s.%s.%s' % (_StringImporter.BASE_MODULE_NAME_SPACE,
                                _StringImporter.SUB_NAME_SPACE,
                                script_module_name)

    if module_name in sys.modules:
        reload_module = True
    else:
        reload_module = False
    try:
        script_module = __import__(module_name, env_dict, {}, ['*'])
    except Exception:
        sys.excepthook(*sys.exc_info())
    else:
        if reload_module:
            reload(script_module)
        for k, v in script_module.__dict__.iteritems():
            if k.startswith('_'):
                continue
            env_dict[k] = v


class Session(object):
    def __init__(self, name, config_tree):
        self.__name = name
        self.__config = static.get_config()

        self.init(config_tree)

    def init(self, config_tree):
        try:
            self.__setup_file = os.path.normpath(os.path.join(
                os.path.dirname(config_tree.filename), config_tree.get("setup-file")))
        except TypeError:
            self.__setup_file = None
        try:
            self.__synoptic_file = config_tree.get("synoptic").get("svg-file")
        except AttributeError:
            self.__synoptic_file = None

        config_objects = config_tree.get("config-objects")
        if isinstance(config_objects, (str, unicode)):
            self.__config_objects_names = config_objects.split()
        else:
            self.__config_objects_names = config_objects
        exclude_objects = config_tree.get("exclude-objects") or []
        if isinstance(exclude_objects, (str, unicode)):
            self.__exclude_objects_names = exclude_objects.split()
        else:
            self.__exclude_objects_names = exclude_objects

        self.__objects_names = None

        global DEFAULT_SESSION
        if DEFAULT_SESSION is None or config_tree.get('default', False):
            DEFAULT_SESSION = self

    @property
    def name(self):
        return self.__name

    @property
    def config(self):
        return self.__config

    @property
    def setup_file(self):
        return self.__setup_file

    @property
    def synoptic_file(self):
        return self.__synoptic_file

    @property
    def object_names(self):
        if self.__objects_names is None:
            if self.__config_objects_names is None:
                names_list = [x for x in self.config.names_list
                              if self.config.get_config(x).get('class', '').lower() != 'session']
            else:
                names_list = self.__config_objects_names[:]
                #Check if other session in config-objects
                for name in names_list:
                    object_config = self.config.get_config(name)
                    if object_config is None:
                        raise RuntimeError("Session %s contains object %s which doesn't exist" %
                                           (self.name, name))

                    class_name = object_config.get('class', '')
                    if class_name.lower() == 'session':
                        raise RuntimeError('Session %s contains session %s in config-objects' %
                                           (self.name, name))

            for name in self.__exclude_objects_names:
                try:
                    names_list.remove(name)
                except (ValueError, AttributeError):
                    pass

            self.__objects_names = names_list[:]

        return self.__objects_names

    def setup(self, env_dict=None, verbose=False):
        if env_dict is None:
            env_dict = self._get_global_env_dict()

        self._load_config(env_dict, verbose)

        env_dict['load_script'] = functools.partial(
            load_script, env_dict)

        from bliss.scanning.scan import ScanSaving
        env_dict['SCAN_SAVING'] = ScanSaving()
        from bliss.session.measurementgroup import ACTIVE_MG
        env_dict['ACTIVE_MG'] = ACTIVE_MG

        for obj_name, obj in env_dict.iteritems():
            setattr(setup_globals, obj_name, obj)

        if self.setup_file is None:
            raise RuntimeError("No setup file.")

        try:
            with get_file({"setup_file": self.setup_file}, 'setup_file') as setup_file:
                base_path = os.path.dirname(self.setup_file)
                module_path = os.path.join(base_path, 'scripts')

                if module_path not in _importer_path:
                    sys.meta_path.append(
                        _StringImporter(module_path, self.name))
                    _importer_path.add(module_path)

                code = compile(setup_file.read(), self.setup_file, 'exec')
                exec(code, env_dict)

                for obj_name, obj in env_dict.iteritems():
                    setattr(setup_globals, obj_name, obj)

                return True
        except IOError:
            raise ValueError("Session: setup-file %s can't be found" %
                             self.setup_file)

    def _load_config(self, env_dict, verbose=True):
        for item_name in self.object_names:
            if hasattr(setup_globals, item_name):
                env_dict[item_name] = getattr(setup_globals, item_name)
                continue

            if verbose:
                print "Initializing '%s`" % item_name

            self._add_from_config(item_name, env_dict)

        self._add_from_config(self.name, env_dict)

    def _add_from_config(self, item_name, env_dict):
        try:
            o = self.config.get(item_name)
        except:
            sys.excepthook(*sys.exc_info())
        else:
            env_dict[item_name] = o
            setattr(setup_globals, item_name, o)
            del o

    def _get_global_env_dict(self):
        # does Python run in interactive mode?
        import __main__ as main
        if not hasattr(main, '__file__'):
            # interactive interpreter
            env_dict = main.__dict__
        else:
            env_dict = globals()
        return env_dict

    def resetup(self, env_dict=None, verbose=False):
        if env_dict is None:
            env_dict = self._get_global_env_dict()

        for name in self.object_names:
            delattr(setup_globals, name)
            try:
                del env_dict[name]
            except KeyError:
                pass

        self.config.reload()

        self.init(self.config.get_config(self.name))

        self.setup(env_dict, verbose)
