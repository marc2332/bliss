# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import sys
import warnings
import collections
import functools
from treelib import Tree
from bliss.common.logtools import log_warning

from bliss import setup_globals, global_map
from types import ModuleType
from bliss.config import static
from bliss.config.conductor.client import get_text_file, get_python_modules, get_file
from bliss.common.proxy import Proxy
from bliss import is_bliss_shell
from bliss.scanning import scan_saving


_SESSION_IMPORTERS = set()
CURRENT_SESSION = None


def set_current_session(session, force=True):
    if force:
        global CURRENT_SESSION
        CURRENT_SESSION = session
    else:
        raise RuntimeError("It is not allowed to set another current session.")


def get_current_session():
    return CURRENT_SESSION


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
        if fullname not in self._modules.keys():
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
        if fullname not in self._modules.keys():
            raise ImportError(fullname)

        filename = self._modules.get(fullname)
        return get_text_file(filename) if filename else ""


class ConfigProxy(Proxy):
    def __init__(self, target, env_dict):
        object.__setattr__(self, "_ConfigProxy__env_dict", env_dict)
        super().__init__(target, init_once=True)

    def get(self, name):
        """This is the same as the canonical static config.get,
        except that it adds the object to the corresponding session env dict"""
        obj = self.__wrapped__.get(name)
        self.__env_dict[name] = obj
        return obj


class Session:
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
        self.__env_dict = {}
        self.__scripts_module_path = None
        self.__setup_file = None
        self.__synoptic_file = None
        self.__config_objects_names = []
        self.__exclude_objects_names = []
        self.__children_tree = None
        self.__include_sessions = []
        self.__map = None
        self.__log = None
        self.__scans = collections.deque(maxlen=20)

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
        self.__children_tree = None
        self.__include_sessions = config_tree.get("include-sessions")
        self.__config_aliases = config_tree.get("aliases", [])

    @property
    def name(self):
        return self.__name

    @property
    def scans(self):
        return self.__scans

    @property
    def config(self):
        return ConfigProxy(static.get_config, self.env_dict)

    @property
    def setup_file(self):
        return self.__setup_file

    @property
    def synoptic_file(self):
        return self.__synoptic_file

    @property
    def _scripts_module_path(self):
        return self.__scripts_module_path

    def _child_session_iter(self):
        sessions_tree = self.sessions_tree
        for child_session in reversed(
            list(sessions_tree.expand_tree(mode=Tree.WIDTH))[1:]
        ):
            yield child_session

    def _aliases_info(self, cache={"aliases": {}, "config_id": None}):
        aliases = cache["aliases"]
        config_id = id(self.__config_aliases)
        if cache["config_id"] != config_id:
            aliases.clear()
            cache["config_id"] = config_id
        if aliases:
            return aliases

        for child_session in self._child_session_iter():
            aliases.update(child_session._aliases_info())

        for alias_cfg in self.__config_aliases:
            cfg = alias_cfg.deep_copy()
            aliases[cfg.pop("original_name")] = cfg

        return aliases

    @property
    def object_names(self, cache={"objects_names": [], "config_id": None}):
        objects_names = cache["objects_names"]
        config_id = id(self.__config_objects_names)
        if cache["config_id"] != config_id:
            objects_names.clear()
            cache["config_id"] = config_id
        if objects_names:
            return objects_names

        names_list = list()
        for child_session in self._child_session_iter():
            names_list.extend(child_session.object_names)

        session_config = self.config.get_config(self.name)

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
                    log_warning(
                        self,
                        f"In {session_config.filename} of session '{self.name}':"
                        + f" object '{name}' does not exist. Ignoring it.",
                    )
                    names_list.remove(name)
                else:
                    class_name = object_config.get("class", "")
                    if class_name.lower() == "session":
                        warnings.warn(
                            f"Session {self.name} 'config-objects' list contains session "
                            + f"{name}, ignoring (hint: add session in 'include-sessions' list)",
                            RuntimeWarning,
                        )
                        names_list.remove(name)

        for name in self.__exclude_objects_names:
            try:
                names_list.remove(name)
            except (ValueError, AttributeError):
                pass
        seen = set()
        objects_names.clear()
        objects_names.extend(x for x in names_list if not (x in seen or seen.add(x)))
        return objects_names

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

    def _set_scan_saving_class(self, scan_saving_class):
        scan_saving.set_scan_saving_class(scan_saving_class)

        self.scan_saving = scan_saving.ScanSaving(self.name)
        if is_bliss_shell():
            self.env_dict["SCAN_SAVING"] = self.scan_saving

    def enable_esrf_data_policy(self):
        self._set_scan_saving_class(scan_saving.ESRFScanSaving)

    def disable_esrf_data_policy(self):
        self._set_scan_saving_class(None)

    def load_script(self, script_module_name, session=None):
        """
        load a script name script_module_name and export all public
        (not starting with _) object and function in env_dict.
        just print exception but not throwing it.

        Args:
            script_module_name the python file you want to load
            session (optional) the session from which to load the script
        """
        if session is None:
            session = self
        elif isinstance(session, str):
            session = self.config.get(session)

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

                globals_dict = self.env_dict.copy()
                try:
                    exec(c_code, globals_dict)
                except Exception:
                    sys.excepthook(*sys.exc_info())

                for k in globals_dict.keys():
                    if k.startswith("_"):
                        continue
                    self.env_dict[k] = globals_dict[k]
            finally:
                sys.meta_path.remove(importer)

    def setup(self, env_dict=None, verbose=False):
        if get_current_session() is None:
            set_current_session(self, force=True)
        if env_dict is None:
            # use existing env dict
            env_dict = get_current_session().env_dict
        self.__env_dict = env_dict

        try:
            self._load_config(verbose)
        except Exception:
            sys.excepthook(*sys.exc_info())

        if self.__scripts_module_path and self.name not in _SESSION_IMPORTERS:
            sys.meta_path.append(_StringImporter(self.__scripts_module_path, self.name))
            _SESSION_IMPORTERS.add(self.name)

        env_dict["config"] = self.config

        if "load_script" not in env_dict:
            env_dict["load_script"] = self.load_script

        scan_saving_config = self.config.root.get("scan_saving", {})
        scan_saving_class_name = scan_saving_config.get("class")
        if scan_saving_class_name is not None:
            scan_saving_class = getattr(scan_saving, scan_saving_class_name)
        else:
            scan_saving_class = None
        self._set_scan_saving_class(scan_saving_class)

        env_dict["ALIASES"] = global_map.aliases

        from bliss.common.measurementgroup import ACTIVE_MG

        env_dict["ACTIVE_MG"] = ACTIVE_MG

        for child_session in self._child_session_iter():
            if child_session.name not in _SESSION_IMPORTERS:
                sys.meta_path.append(
                    _StringImporter(
                        child_session._scripts_module_path, child_session.name
                    )
                )
                _SESSION_IMPORTERS.add(child_session.name)

            child_session._setup(env_dict, nested=True)

        self._setup(env_dict)

    def _setup(self, env_dict, nested=False):
        if self.setup_file is None:
            return

        with get_file(
            {"setup_file": self.setup_file}, "setup_file", text=True
        ) as setup_file:

            if nested:
                # in case of nested sessions, execute load_script from the child session
                env_dict["load_script"] = functools.partial(
                    env_dict["load_script"], session=self.name
                )
            else:
                env_dict["load_script"] = self.load_script

            code = compile(setup_file.read(), self.setup_file, "exec")
            exec(code, env_dict)

            for obj_name, obj in env_dict.items():
                setattr(setup_globals, obj_name, obj)

            return True

    def close(self):
        setup_globals.__dict__.clear()
        for obj_name, obj in self.env_dict.items():
            if obj is self or obj is self.config:
                continue
            try:
                obj.__close__()
            except Exception:
                pass
        self.env_dict.clear()
        global CURRENT_SESSION
        CURRENT_SESSION = None

    def _load_config(self, verbose=True):
        for item_name in self.object_names:
            if hasattr(setup_globals, item_name):
                self.env_dict[item_name] = getattr(setup_globals, item_name)
                continue

            try:
                self.config.get(item_name)
            except Exception:
                if verbose:
                    print(f"FAILED to initialize '{item_name}'")
                sys.excepthook(*sys.exc_info())
            else:
                if verbose:
                    item_node = self.config.get_config(item_name)
                    if item_node.plugin is None:
                        print(f"Initialized '{item_name}' with **default** plugin")
                    else:
                        print(f"Initialized '{item_name}'")

        for item_name, alias_cfg in self._aliases_info().items():
            alias_name = alias_cfg["alias_name"]
            try:
                global_map.aliases.add(alias_name, item_name, verbose=verbose)
            except Exception:
                sys.excepthook(*sys.exc_info())
        try:
            self.config.get(self.name)
        except Exception:
            sys.excepthook(*sys.exc_info())

        setup_globals.__dict__.update(self.env_dict)

    def resetup(self, verbose=False):
        self.close()

        self.config.reload()

        self.init(self.config.get_config(self.name))

        self.setup(self.env_dict, verbose)


class DefaultSession(Session):
    def __init__(self):
        Session.__init__(self, "__DEFAULT__", {"config-objects": []})

    def _load_config(self, verbose=True):
        return

    def resetup(self, verbose=False):
        return
