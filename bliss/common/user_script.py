import os
import sys

from bliss import current_session
from bliss.config.settings import SimpleSetting

USER_SCRIPT_HOME = SimpleSetting(
    "%s:script_home" % current_session.name,
    # default_value="%s/bliss_scripts" % os.getenv("HOME"),
)

__all__ = [
    "user_script_homedir",
    "user_script_run",
    "user_script_load",
    "user_script_list",
]


def user_script_homedir(new_dir=None):
    """Set or get local user script home directory"""
    if new_dir is not None:
        if not os.path.isabs(new_dir):
            raise RuntimeError(f"Directory path must be absolute [{new_dir}]")
        if not os.path.isdir(new_dir):
            raise RuntimeError(f"Invalid directory [{new_dir}]")
        USER_SCRIPT_HOME.set(new_dir)
    else:
        return USER_SCRIPT_HOME.get()


def user_script_list():
    """List python scripts from home directory"""
    rootdir = USER_SCRIPT_HOME.get()
    if not rootdir:
        print(
            "First, you need to set a directory with `user_script_homedir(path_to_dir)`"
        )
        raise RuntimeError("User scripts home directory not configured")

    print(f"List of python scripts in [{rootdir}]:")
    for (dirpath, dirnames, filenames) in os.walk(rootdir):
        dirname = dirpath.replace(rootdir, "")
        dirname = dirname.lstrip(os.path.sep)
        for filename in filenames:
            _, ext = os.path.splitext(filename)
            if ext != ".py":
                continue
            print(f" - {os.path.join(dirname, filename)}")


def user_script_load(scriptname=None, namespace=None):
    _user_script_exec(scriptname, export=True, namespace=namespace)


def user_script_run(scriptname=None, namespace=None):
    _user_script_exec(scriptname, export=False, namespace=namespace)


def _user_script_exec(scriptname, export=False, namespace=None):
    if not scriptname:
        user_script_list()
        return
    if os.path.isabs(scriptname):
        filepath = scriptname
    else:
        if not USER_SCRIPT_HOME.get():
            print(
                "First, you need to set a directory with `user_script_homedir(path_to_dir)`"
            )
            raise RuntimeError("User scripts home directory not configured")

        homedir = os.path.abspath(USER_SCRIPT_HOME.get())
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

    if export is True:
        print(f"Loading [{filepath}]...")
    else:
        print(f"Running [{filepath}]...")

    if namespace is None:
        namespace = current_session.env_dict

    globals_dict = namespace.copy()

    try:
        exec(script, globals_dict)
    except Exception:
        sys.excepthook(*sys.exc_info())

    if export is True:
        for k in globals_dict.keys():
            if k.startswith("_"):
                continue
            namespace[k] = globals_dict[k]
