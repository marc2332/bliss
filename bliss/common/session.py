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
from treelib import Tree

from bliss import setup_globals
from bliss.config import static
from bliss.common.utils import closable
from bliss.config.conductor.client import get_text_file, get_python_modules, get_file

CURRENT_SESSION = None


def get_current():
    """
    return the current session object
    """
    return CURRENT_SESSION


_SESSION_IMPORTERS = set()


class _StringImporter(object):
    BASE_MODULE_NAMESPACE = "bliss.session"

    def __init__(self, path, session_name, in_load_script=False):
        self._modules = dict()
        session_module_namespace = "%s.%s" % (self.BASE_MODULE_NAMESPACE, session_name)
        for module_name, file_path in get_python_modules(path):
            self._modules["%s.%s" % (session_module_namespace, module_name)] = file_path
            if in_load_script:
                self._modules[module_name] = file_path
        if self._modules:
            self._modules[self.BASE_MODULE_NAMESPACE] = None
            self._modules["%s.%s" % (self.BASE_MODULE_NAMESPACE, session_name)] = None

    def find_module(self, fullname, path):
        if fullname in self._modules:
            return self
        return None

    def load_module(self, fullname):
        if not fullname in self._modules.keys():
            raise ImportError(fullname)

        filename = self._modules.get(fullname)
        if filename:
            s_code = get_text_file(filename)
        else:
            filename = "%s (__init__ memory)" % fullname
            s_code = ""  # empty __init__.py

        new_module = sys.modules.get(fullname, ModuleType(fullname))
        new_module.__loader__ = self
        module_filename = "beacon://%s" % filename
        new_module.__file__ = module_filename
        new_module.__name__ = fullname
        if filename.find("__init__") > -1:
            new_module.__path__ = []
            new_module.__package__ = fullname
        else:
            new_module.__package__ = fullname.rpartition(".")[0]
        sys.modules.setdefault(fullname, new_module)
        c_code = compile(s_code, module_filename, "exec")
        exec(c_code, new_module.__dict__)
        return new_module

    def get_source(self, fullname):
        if not fullname in self._modules.keys():
            raise ImportError(fullname)

        filename = self._modules.get(fullname)
        return get_text_file(filename) if filename else ""


def load_script(env_dict, script_module_name, session=None):
    """
    load a script name script_module_name and export all public
    (not starting with _) object and function in env_dict.
    just print exception but not throwing it.

    Args:
    	env_dict (python dictionnary) where object will be exported
    	script_module_name the python file you want to load
    	session from which session name you want to load your script,
        default (None) is the current.
    """
    if session is None:
        session = get_current()
    elif isinstance(session, str):
        session = static.get_config().get(session)

    if session._scripts_module_path:
        importer = _StringImporter(
            session._scripts_module_path, session.name, in_load_script=True
        )
        try:
            sys.meta_path.insert(0, importer)

            module_name = "%s.%s.%s" % (
                _StringImporter.BASE_MODULE_NAMESPACE,
                session.name,
                os.path.splitext(script_module_name)[0],
            )
            filename = importer._modules.get(module_name)
            if not filename:
                raise RuntimeError("Cannot find module %s" % module_name)

            s_code = get_text_file(filename)
            c_code = compile(s_code, filename, "exec")

            globals_dict = env_dict.copy()
            try:
                exec(c_code, globals_dict)
            except Exception:
                sys.excepthook(*sys.exc_info())
        finally:
            sys.meta_path.remove(importer)

    for k in globals_dict.keys():
        if k.startswith("_"):
            continue
        env_dict[k] = globals_dict[k]


class Session(object):
    """
    Bliss session.

    Sessions group objects with a setup.

    YAML file example:
     - plugin: session          # could be defined in parents
       class: Session
       name: super_mario        # session name

       # 'config-objects' contains
       # object name you want to export
       # either in yaml compact list
       config-objects: [seby,diode2]
       # or standard yaml list
       config-objects:
       - seby
       - diode2
       # if config-objects key doesn't exist,
       # session will export all objects;
       # 'exclude-objects' can be used to exclude objects
       exclude-objects: [seby]

       # you can also include other session
       # with the 'include-sessions'
       include-sessions: [luigi]

       # finally a setup file can be defined to be
       # executed for the session.
       # All objects or functions defined in the
       # setup file will be exported in the environment.
       # The file path is relative to the session yaml file
       # location if it starts with a './'
       # otherwise it is absolute from the root of the
       # beacon file data base.
       setup-file: ./super_mario.py

       # A svg synoptic (Web shell) can be added:
       synoptic:
         svg-file: super_mario.svg
    """

    def __init__(self, name, config_tree):
        self.__name = name
        self.__config = static.get_config()
        self.__env_dict = {}

        self.init(config_tree)

    def init(self, config_tree):
        try:
            self.__scripts_module_path = os.path.normpath(
                os.path.join(os.path.dirname(config_tree.filename), "scripts")
            )
        except AttributeError:
            # config_tree has no .filename
            self.__scripts_module_path = None

        try:
            setup_file_path = config_tree["setup-file"]
        except KeyError:
            self.__setup_file = None
        else:
            try:
                self.__setup_file = os.path.normpath(
                    os.path.join(os.path.dirname(config_tree.filename), setup_file_path)
                )
            except TypeError:
                self.__setup_file = None
            else:
                self.__scripts_module_path = os.path.join(
                    os.path.dirname(self.__setup_file), "scripts"
                )

        try:
            self.__synoptic_file = config_tree.get("synoptic").get("svg-file")
        except AttributeError:
            self.__synoptic_file = None

        self.__config_objects_names = config_tree.get("config-objects")
        self.__exclude_objects_names = config_tree.get("exclude-objects", list())
        self.__objects_names = None
        self.__children_tree = None
        self.__include_sessions = config_tree.get("include-sessions")

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
    def _scripts_module_path(self):
        return self.__scripts_module_path

    @property
    def object_names(self):
        if self.__objects_names is None:
            names_list = list()
            sessions_tree = self.sessions_tree
            for child_session in reversed(
                list(sessions_tree.expand_tree(mode=Tree.WIDTH))[1:]
            ):
                names_list.extend(child_session.object_names)

            if self.__config_objects_names is None:
                names_list = list()
                for name in self.config.names_list:
                    cfg = self.config.get_config(name)
                    if cfg.get("class", "").lower() == "session":
                        continue
                    if cfg.get_inherited("plugin") == "default":
                        continue
                    names_list.append(name)
            else:
                names_list.extend(self.__config_objects_names[:])
                # Check if other session in config-objects
                for name in names_list:
                    object_config = self.config.get_config(name)
                    if object_config is None:
                        raise RuntimeError(
                            "Session %s contains object %s which doesn't exist"
                            % (self.name, name)
                        )

                    class_name = object_config.get("class", "")
                    if class_name.lower() == "session":
                        raise RuntimeError(
                            "Session %s contains session %s in config-objects"
                            % (self.name, name)
                        )

            for name in self.__exclude_objects_names:
                try:
                    names_list.remove(name)
                except (ValueError, AttributeError):
                    pass
            seen = set()
            self.__objects_names = [
                x for x in names_list if not (x in seen or seen.add(x))
            ]

        return self.__objects_names

    @property
    def sessions_tree(self):
        """
        return children session as a tree
        """
        if self.__children_tree is None:
            children = {self.name: (1, list())}
            tree = Tree()
            tree.create_node(tag=self.name, identifier=self)
            tree = self._build_children_tree(tree, self, children)
            multiple_ref_child = [
                (name, parents) for name, (ref, parents) in children.items() if ref > 1
            ]
            if multiple_ref_child:
                msg = "Session %s as cyclic references to sessions:\n" % self.name
                msg += "\n".join(
                    "session %s is referenced in %r" % (session_name, parents)
                    for session_name, parents in multiple_ref_child
                )
                raise RuntimeError(msg)
            self.__children_tree = tree
        return self.__children_tree

    def _build_children_tree(self, tree, parent, children):
        if self.__include_sessions is not None:
            for session_name in self.__include_sessions:
                nb_ref, parents = children.get(session_name, (0, list()))
                nb_ref += 1
                children[session_name] = (nb_ref, parents)
                parents.append(self.name)
                if nb_ref > 1:  # avoid cyclic reference
                    continue

                child = self.config.get(session_name)
                child_node = tree.create_node(
                    tag=session_name, identifier=child, parent=parent
                )
                child._build_children_tree(tree, child, children)
        return tree

    @property
    def env_dict(self):
        return self.__env_dict

    def setup(self, env_dict=None, verbose=False):
        if env_dict is None:
            # does Python run in interactive mode?
            import __main__ as main

            if not hasattr(main, "__file__"):
                # interactive interpreter
                self.__env_dict = main.__dict__
            else:
                self.__env_dict = {}
        else:
            self.__env_dict = env_dict
        env_dict = self.__env_dict

        self._load_config(env_dict, verbose)

        global CURRENT_SESSION
        CURRENT_SESSION = self

        if self.__scripts_module_path and self.name not in _SESSION_IMPORTERS:
            sys.meta_path.append(_StringImporter(self.__scripts_module_path, self.name))
            _SESSION_IMPORTERS.add(self.name)

        if not "load_script" in env_dict:
            env_dict["load_script"] = functools.partial(load_script, env_dict)

            from bliss.scanning.scan import ScanSaving, ScanDisplay, SCANS

            env_dict["SCANS"] = SCANS
            env_dict["SCAN_SAVING"] = ScanSaving(self.name)
            env_dict["SCAN_DISPLAY"] = ScanDisplay()
            from bliss.common.measurementgroup import ACTIVE_MG

            env_dict["ACTIVE_MG"] = ACTIVE_MG

        sessions_tree = self.sessions_tree
        for child_session in reversed(
            list(sessions_tree.expand_tree(mode=Tree.WIDTH))[1:]
        ):
            if child_session.name not in _SESSION_IMPORTERS:
                sys.meta_path.append(
                    _StringImporter(
                        child_session._scripts_module_path, child_session.name
                    )
                )
            _SESSION_IMPORTERS.add(self.name)

            child_session._setup(env_dict)

        for obj_name, obj in env_dict.items():
            setattr(setup_globals, obj_name, obj)

        self._setup(env_dict)

    def _setup(self, env_dict):
        if self.setup_file is None:
            return

        with get_file(
            {"setup_file": self.setup_file}, "setup_file", text=True
        ) as setup_file:
            code = compile(setup_file.read(), self.setup_file, "exec")
            exec(code, env_dict)

            for obj_name, obj in env_dict.items():
                setattr(setup_globals, obj_name, obj)

            return True

    def close(self):
        if get_current() is self:
            global CURRENT_SESSION
            CURRENT_SESSION = None
        for obj_name, obj in self.__env_dict.items():
            if obj is self:
                continue
            if hasattr(setup_globals, obj_name):
                delattr(setup_globals, obj_name)
            if closable(obj):
                obj.close()
        self.__env_dict.clear()

    def _load_config(self, env_dict, verbose=True):
        for item_name in self.object_names:
            if hasattr(setup_globals, item_name):
                env_dict[item_name] = getattr(setup_globals, item_name)
                continue

            if verbose:
                print("Initializing '%s`" % item_name)

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

    def resetup(self, verbose=False):
        env_dict = self.__env_dict

        for name in self.object_names:
            delattr(setup_globals, name)
            try:
                obj = env_dict.pop(name)
            except KeyError:
                pass
            else:
                if closable(obj):
                    obj.close()

        self.config.reload()

        self.init(self.config.get_config(self.name))

        self.setup(env_dict, verbose)


class DefaultSession(Session):
    def __init__(self):
        Session.__init__(
            self, "default", {"exclude-objects": static.get_config().names_list}
        )

    def _load_config(self, env_dict, verbose=True):
        return

    def resetup(self, verbose=False):
        return
