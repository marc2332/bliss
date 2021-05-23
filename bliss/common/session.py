# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import sys
import typing
import warnings
import collections
import functools
import inspect
import contextlib
import shutil
from treelib import Tree
from types import ModuleType
from weakref import WeakKeyDictionary
from tabulate import tabulate

from bliss import setup_globals, global_map, is_bliss_shell
from bliss.config import static
from bliss.config.settings import SimpleSetting
from bliss.config.channels import EventChannel
from bliss.config.conductor.client import get_text_file, get_python_modules, get_file
from bliss.common.proxy import Proxy
from bliss.common.logtools import log_warning
from bliss.common.utils import UserNamespace
from bliss.common import constants
from bliss.scanning import scan_saving
from bliss.scanning import scan_display


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


def chunk_list(lst, n):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


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

    .. code-block::

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
        self.__user_script_homedir = SimpleSetting("%s:user_script_homedir" % self.name)
        self._script_source_cache = WeakKeyDictionary()
        self.__data_policy_events = EventChannel(f"{self.name}:esrf_data_policy")
        self.scan_saving = None
        self.scan_display = None
        self.is_loading_config = False

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

        # convert windows-style path to linux-style
        if self.__scripts_module_path:
            self.__scripts_module_path = self._scripts_module_path.replace("\\", "/")

        try:
            self.__synoptic_file = config_tree.get("synoptic").get("svg-file")
        except AttributeError:
            self.__synoptic_file = None

        self.__config_objects_names = config_tree.get("config-objects")
        self.__exclude_objects_names = config_tree.get("exclude-objects", list())
        self.__children_tree = None
        self.__include_sessions = config_tree.get("include-sessions")
        self.__config_aliases = config_tree.get("aliases", [])
        self.__icat_mapping = None
        self.__icat_mapping_config = config_tree.get("icat-mapping")
        self.__default_user_script_homedir = config_tree.get("default-userscript-dir")
        if self.__default_user_script_homedir and not self._get_user_script_home():
            self._set_user_script_home(self.__default_user_script_homedir)
        self.__scan_saving_config = config_tree.get(
            "scan_saving", self.config.root.get("scan_saving", {})
        )

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
    @contextlib.contextmanager
    def temporary_config(self):
        """
        Create a context to export temporary some devices.
        """
        # store current config status
        cfg = static.get_config()
        name2instancekey = set(cfg._name2instance.keys())
        name2cache = cfg._name2cache.copy()

        # reload is not permited in temporary config
        previous_reload = cfg.reload

        def reload(*args):
            raise RuntimeError("Not permitted under tempaorary config context")

        cfg.reload = reload

        try:
            yield self.config
        finally:
            # rollback config
            cfg.reload = previous_reload
            diff_keys = set(cfg._name2instance.keys()) - name2instancekey
            for key in diff_keys:
                cfg._name2instance.pop(key)
                self.__env_dict.pop(key, None)
            cfg_name2cache_key = set(cfg._name2cache)
            prev_name2cache_key = set(name2cache)
            added_keys = cfg_name2cache_key - prev_name2cache_key
            removed_key = prev_name2cache_key - cfg_name2cache_key
            # remove added cache
            for key in added_keys:
                cfg._name2cache.pop(key)
            # re-insert removed cache
            for key in removed_key:
                cfg._name2cache[key] = name2cache[key]

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
    def icat_mapping(self):
        if self.__icat_mapping is not None:
            return self.__icat_mapping
        if self.__icat_mapping_config:
            self.__icat_mapping = self.config.get(self.__icat_mapping_config)
            return self.__icat_mapping

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
            cfg = alias_cfg.clone()
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

    def _emit_event(self, event, **kwargs):
        if event in scan_saving.ESRFDataPolicyEvent:
            self.__data_policy_events.post(dict(event_type=event, value=kwargs))
        else:
            raise NotImplementedError

    def _set_scan_saving(self, cls=None):
        """Defines the data policy, which includes the electronic logbook
        """
        scan_saving.set_scan_saving_class(cls)
        self.scan_saving = scan_saving.ScanSaving(self.name)
        if is_bliss_shell():
            self.env_dict["SCAN_SAVING"] = self.scan_saving

    @property
    def _config_scan_saving_class(self):
        scan_saving_class_name = self.__scan_saving_config.get("class")
        try:
            return getattr(scan_saving, scan_saving_class_name)
        except (AttributeError, TypeError):
            return None

    def _set_scan_display(self):
        self.scan_display = scan_display.ScanDisplay(self.name)
        if is_bliss_shell():
            self.env_dict["SCAN_DISPLAY"] = self.scan_display

    def enable_esrf_data_policy(self):
        self._set_scan_saving(cls=scan_saving.ESRFScanSaving)
        self._emit_event(
            scan_saving.ESRFDataPolicyEvent.Enable,
            data_path=self.scan_saving.get_path(),
        )

    def disable_esrf_data_policy(self):
        self._set_scan_saving()
        self._emit_event(
            scan_saving.ESRFDataPolicyEvent.Disable,
            data_path=self.scan_saving.get_path(),
        )

    def _cache_script_source(self, obj):
        """ Store source code of obj in cache for prdef """
        try:
            self._script_source_cache[obj] = inspect.getsourcelines(obj)
        except Exception:
            pass

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
                globals_dict["__file__"] = filename
                try:
                    exec(c_code, globals_dict)
                except Exception:
                    sys.excepthook(*sys.exc_info())

                for k in globals_dict.keys():
                    if k.startswith("_"):
                        continue
                    self.env_dict[k] = globals_dict[k]
                    self._cache_script_source(globals_dict[k])
            finally:
                sys.meta_path.remove(importer)
        else:
            raise RuntimeError(f"{session.name} session has no script module path")

    def _get_user_script_home(self):
        return self.__user_script_homedir.get()

    def _set_user_script_home(self, dir):
        self.__user_script_homedir.set(dir)

    def _reset_user_script_home(self):
        if self.__default_user_script_homedir:
            self.__user_script_homedir.set(self.__default_user_script_homedir)
        else:
            self.__user_script_homedir.clear()

    def user_script_homedir(self, new_dir=None, reset=False):
        """
        Set or get local user script home directory

        Args:
            None -> returns current user script home directory
            new_dir (optional) -> set user script home directory to new_dir
            reset (optional) -> reset previously set user script home directory
        """
        if reset:
            self._reset_user_script_home()
        elif new_dir is not None:
            if not os.path.isabs(new_dir):
                raise RuntimeError(f"Directory path must be absolute [{new_dir}]")
            if not os.path.isdir(new_dir):
                raise RuntimeError(f"Invalid directory [{new_dir}]")
            self._set_user_script_home(new_dir)
        else:
            return self._get_user_script_home()

    def user_script_list(self):
        """List python scripts from user script home directory"""
        rootdir = self._get_user_script_home()
        if not rootdir:
            print(
                "First, you need to set a directory with `user_script_homedir(path_to_dir)`"
            )
            raise RuntimeError("User scripts home directory not configured")
        if not os.path.isdir(rootdir):
            raise RuntimeError(f"Invalid directory [{rootdir}]")

        print(f"List of python scripts in [{rootdir}]:")
        for (dirpath, dirnames, filenames) in os.walk(rootdir):
            dirname = dirpath.replace(rootdir, "")
            dirname = dirname.lstrip(os.path.sep)
            for filename in filenames:
                _, ext = os.path.splitext(filename)
                if ext != ".py":
                    continue
                print(f" - {os.path.join(dirname, filename)}")

    def user_script_load(self, scriptname=None, export_global="user"):
        """
        load a script and export all public (= not starting with _)
        objects and functions to current environment or to a namespace.
        (exceptions are printed but not thrown, execution is stopped)

        Args:
            scriptname: the python file to load (script path can be absolute relative to script_homedir)
        Optional args:
            export_global="user" (default): export objects to "user" namespace in session env dict (eg. user.myfunc())
            export_global=False: return a namespace
            export_global=True: export objects to session env dict
        """
        return self._user_script_exec(
            scriptname, load=True, export_global=export_global
        )

    def user_script_run(self, scriptname=None):
        """
        Execute a script without exporting objects or functions to current environment.
        (exceptions are printed but not thrown, execution is stopped)

        Args:
            scriptname: the python file to run (script path can be absolute or relative to script_homedir)
        """
        self._user_script_exec(scriptname, load=False)

    def _user_script_exec(self, scriptname, load=False, export_global=False):
        if not scriptname:
            self.user_script_list()
            return

        if os.path.isabs(scriptname):
            filepath = scriptname
        else:
            if not self._get_user_script_home():
                print(
                    "First, you need to set a directory with `user_script_homedir(path_to_dir)`"
                )
                raise RuntimeError("User scripts home directory not configured")

            homedir = os.path.abspath(self._get_user_script_home())
            filepath = os.path.join(homedir, scriptname)

        _, ext = os.path.splitext(scriptname)
        if not ext:
            filepath += ".py"
        if not os.path.isfile(filepath):
            raise RuntimeError(f"Cannot find [{filepath}] !")
        try:
            script = open(filepath).read()
        except Exception:
            raise RuntimeError(f"Failed to read [{filepath}] !")

        if load is True:
            print(f"Loading [{filepath}]")
        else:
            print(f"Running [{filepath}]")

        globals_dict = self.env_dict.copy()
        globals_dict["__file__"] = filepath

        c_code = compile(script, filepath, "exec")
        try:
            exec(c_code, globals_dict)
        except Exception:
            sys.excepthook(*sys.exc_info())

        def safe_save_to_env_dict(env_dict, key, value):
            """ Print warning if env_dict[key] already exists """
            if key in env_dict and value is not env_dict[key]:
                print(f"Replaced [{key}] in session env")
            env_dict[key] = value

        # case #1: run file
        if not load:
            return

        # case #2: export to global env dict
        if export_global is True:
            for k in globals_dict.keys():
                if k.startswith("_"):
                    continue
                safe_save_to_env_dict(self.env_dict, k, globals_dict[k])
                self._cache_script_source(globals_dict[k])

        else:
            env_dict = dict()
            for k in c_code.co_names:
                if k.startswith("_"):
                    continue
                if k not in globals_dict:
                    continue
                env_dict[k] = globals_dict[k]
            ns = UserNamespace(env_dict)

            for obj in env_dict.values():
                self._cache_script_source(obj)

            if isinstance(export_global, str):
                if (
                    getattr(self.env_dict.get(export_global), "__module__", None)
                    == "bliss.common.utils.namespace"
                ):
                    # case #3: export and merge to existing namespace in env dict
                    d = self.env_dict[export_global]._asdict()
                    d.update(env_dict)
                    self.env_dict[export_global] = UserNamespace(d)
                    print(f"Merged [{export_global}] namespace in session.")
                else:
                    # case #4: export to given (non existing) namespace in env dict
                    safe_save_to_env_dict(self.env_dict, export_global, ns)
                    print(f"Exported [{export_global}] namespace in session.")

            else:
                # case #5: export_global is False, return the namespace
                return ns

    def _do_setup(self, env_dict: typing.Union[dict, None], verbose: bool) -> bool:
        """
        Load configuration, and execute the setup script

        env_dict: globals dictionary (or None to use current session env. dict)
        verbose: boolean flag passed to `load_config`

        Return: True if setup went without error, False otherwise
        """
        ret = True
        set_current_session(self, force=True)

        # Session environment
        if env_dict is None:
            env_dict = get_current_session().env_dict
        self.__env_dict = env_dict

        # Data policy needs to be defined before instantiating the
        # session objects
        self._set_scan_saving(cls=self._config_scan_saving_class)

        # Instantiate the session objects
        try:
            CURRENT_SESSION.is_loading_config = True
            self._load_config(verbose)
        except Exception:
            ret = False
            sys.excepthook(*sys.exc_info())
        finally:
            CURRENT_SESSION.is_loading_config = False
            env_dict["config"] = self.config

        self._register_session_importers(self)

        self._set_scan_display()

        self._additional_env_variables(env_dict)

        for child_session in self._child_session_iter():
            self._register_session_importers(child_session)
            child_session_ret = child_session._setup(env_dict, nested=True)
            ret = ret and child_session_ret

        setup_ret = self._setup(env_dict)
        ret = ret and setup_ret

        return ret

    def setup(
        self,
        env_dict: typing.Optional[dict] = None,
        verbose: typing.Optional[bool] = False,
    ) -> bool:
        """Call _do_setup, but catch exception to display error message via except hook

        In case of SystemExit: the exception is propagated.

        Return: True if setup went without error, False otherwise
        """
        try:
            ret = self._do_setup(env_dict, verbose)
        except SystemExit:
            raise
        except BaseException:
            sys.excepthook(*sys.exc_info())
            return False
        return ret

    @staticmethod
    def _register_session_importers(session):
        """Allows remote scripts to be registered and executed locally
        """
        if session.__scripts_module_path and session.name not in _SESSION_IMPORTERS:
            sys.meta_path.append(
                _StringImporter(session.__scripts_module_path, session.name)
            )
            _SESSION_IMPORTERS.add(session.name)

    def _additional_env_variables(self, env_dict):
        """Add additional variables to the session environment
        """
        from bliss.common.measurementgroup import ACTIVE_MG

        env_dict["ALIASES"] = global_map.aliases
        env_dict["ACTIVE_MG"] = ACTIVE_MG
        if "load_script" not in env_dict:
            env_dict["load_script"] = self.load_script
        if "user_script_homedir" not in env_dict:
            env_dict["user_script_homedir"] = self.user_script_homedir
        if "user_script_list" not in env_dict:
            env_dict["user_script_list"] = self.user_script_list
        if "user_script_load" not in env_dict:
            env_dict["user_script_load"] = self.user_script_load
        if "user_script_run" not in env_dict:
            env_dict["user_script_run"] = self.user_script_run

    def _setup(self, env_dict, nested=False):
        """
        Load an execute setup file.

        Called by _do_setup() which is called by setup().
        Must return True in case of success.
        """
        if self.setup_file is None:
            return True

        print("%s: Executing setup file..." % self.name)

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

            try:
                code = compile(setup_file.read(), self.setup_file, "exec")
                exec(code, env_dict)
            except Exception:
                sys.excepthook(*sys.exc_info())
                return False

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
        warning_item_list = list()
        success_item_list = list()
        error_item_list = list()
        error_count = 0
        item_count = 0

        for item_name in self.object_names:
            item_count += 1

            # Skip initialization of existing objects.
            if hasattr(setup_globals, item_name):
                self.env_dict[item_name] = getattr(setup_globals, item_name)
                continue

            print(f"Initializing: {item_name}                  ", end="", flush=True)

            try:
                self.config.get(item_name)
            except Exception:
                if verbose:
                    print("\r", end="", flush=True)  # return to begining of line.
                    print(" " * 80, flush=True)
                    print(
                        f"Initialization of {item_name} \033[91mFAILED\033[0m ",
                        flush=True,
                    )

                    print(f"[{error_count}] ", end="", flush=True)
                    sys.excepthook(*sys.exc_info())
                    error_count += 1
                    error_item_list.append(item_name)

            else:
                print("\r", end="", flush=True)  # return to begining of line.
                if verbose:
                    item_node = self.config.get_config(item_name)
                    if item_node.plugin is None:
                        warning_item_list.append(item_name)
                    else:
                        success_item_list.append(item_name)

        # Clear the line.
        print(" " * 80, flush=True)

        # Maximal length of objects names (min 5).
        display_width = shutil.get_terminal_size().columns
        if len(self.object_names) == 0:
            max_length = 5
            print("There are no objects declared in the session's config file.")
        else:
            max_length = max([len(x) for x in self.object_names])
        # Number of items displayable on one line.
        item_number = int(display_width / max_length) + 1

        # SUCCESS
        success_count = len(success_item_list)
        if success_count > 0:
            success_item_list.sort(key=str.casefold)
            print(
                f"OK: {len(success_item_list)}/{item_count}"
                f" object{'s' if success_count > 1 else ''} successfully initialized.",
                flush=True,
            )
            print(
                tabulate(chunk_list(success_item_list, item_number), tablefmt="plain")
            )
            print("")

        # WARNING
        warning_count = len(warning_item_list)
        if warning_count > 0:
            warning_item_list.sort(key=str.casefold)
            print(
                f"WARNING: {len(warning_item_list)} object{'s' if warning_count > 1 else ''}"
                f" initialized with **default** plugin:"
            )
            print(
                tabulate(chunk_list(warning_item_list, item_number), tablefmt="plain")
            )
            print("")

        # ERROR
        if error_count > 0:
            error_item_list.sort(key=str.casefold)
            print(
                f"ERROR: {error_count} object{'s' if error_count > 1 else ''} failed to intialize:"
            )
            print(tabulate(chunk_list(error_item_list, item_number), tablefmt="plain"))
            print("")

            if error_count == 1:
                print("To learn about failure, type: 'last_error'")
            else:
                print(
                    f"To learn about failures, type: 'last_error[X]' for X in [0..{error_count-1}]"
                )
            print("")

        # Make aliases.
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
    """Session without config, setup scripts and data policy
    """

    def __init__(self):
        Session.__init__(self, constants.DEFAULT_SESSION_NAME, {"config-objects": []})

    def _set_scan_saving(self, cls=None):
        if cls is not None:
            log_warning(self, "No data policy allowed in this session.")
        super()._set_scan_saving(None)

    def enable_esrf_data_policy(self):
        pass

    def disable_esrf_data_policy(self):
        pass

    def _load_config(self, verbose=True):
        pass

    def resetup(self, verbose=False):
        pass
