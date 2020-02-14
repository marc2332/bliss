import os
import sys

from types import SimpleNamespace

from bliss import current_session
from bliss.config.settings import SimpleSetting

__all__ = [
    "user_script_homedir",
    "user_script_run",
    "user_script_list",
    "user_script_load",
]

USER_SCRIPT_HOME = None


def _create_user_script_home():
    global USER_SCRIPT_HOME
    USER_SCRIPT_HOME = SimpleSetting("%s:script_home" % current_session.name)


def _get_user_script_home():
    global USER_SCRIPT_HOME
    if USER_SCRIPT_HOME is None:
        _create_user_script_home()
    return USER_SCRIPT_HOME.get()


def _set_user_script_home(dir):
    global USER_SCRIPT_HOME
    if USER_SCRIPT_HOME is None:
        _create_user_script_home()
    USER_SCRIPT_HOME.set(dir)


def _clear_user_script_home():
    global USER_SCRIPT_HOME
    if USER_SCRIPT_HOME is None:
        _create_user_script_home()
    USER_SCRIPT_HOME.clear()


def user_script_homedir(new_dir=None, clear=False):
    """Set or get local user script home directory"""
    if clear:
        _clear_user_script_home()
    elif new_dir is not None:
        if not os.path.isabs(new_dir):
            raise RuntimeError(f"Directory path must be absolute [{new_dir}]")
        if not os.path.isdir(new_dir):
            raise RuntimeError(f"Invalid directory [{new_dir}]")
        _set_user_script_home(new_dir)
    else:
        return _get_user_script_home()


def user_script_list():
    """List python scripts from home directory"""
    rootdir = _get_user_script_home()
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


def user_script_load(scriptname=None, export_global=False):
    return _user_script_exec(
        scriptname, return_namespace=True, export_global=export_global
    )


def user_script_run(scriptname=None):
    _user_script_exec(scriptname, return_namespace=False)


def _user_script_exec(scriptname, return_namespace=False, export_global=False):
    if not scriptname:
        user_script_list()
        return

    if os.path.isabs(scriptname):
        filepath = scriptname
    else:
        if not _get_user_script_home():
            print(
                "First, you need to set a directory with `user_script_homedir(path_to_dir)`"
            )
            raise RuntimeError("User scripts home directory not configured")

        homedir = os.path.abspath(_get_user_script_home())
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

    if return_namespace is True:
        print(f"Loading [{filepath}]...")
    else:
        print(f"Running [{filepath}]...")

    globals_dict = current_session.env_dict.copy()

    try:
        exec(script, globals_dict)
    except Exception:
        sys.excepthook(*sys.exc_info())

    if export_global is True:
        for k in globals_dict.keys():
            if k.startswith("_"):
                continue
            current_session.env_dict[k] = globals_dict[k]

    elif return_namespace is True:
        env_dict = dict()
        for k in globals_dict.keys():
            if k.startswith("_"):
                continue
            env_dict[k] = globals_dict[k]
        return SimpleNamespace(**env_dict)

    else:
        return None
