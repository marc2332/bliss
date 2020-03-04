# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""

Usage: bliss [-l | --log-level=<log_level>] [-s <name> | --session=<name>] [--no-tmux] [--debug]
       bliss [-v | --version]
       bliss [-c <name> | --create=<name>]
       bliss [-D <name> | --delete=<name>]
       bliss [-h | --help]
       bliss [-S | --show-sessions]
       bliss --show-sessions-only

Options:
    -l, --log-level=<log_level>   Log level [default: WARN] (CRITICAL ERROR INFO DEBUG NOTSET)
    -s, --session=<session_name>  Start with the specified session
    -v, --version                 Show version and exit
    -c, --create=<session_name>   Create a new session with the given name
    -D, --delete=<session_name>   Delete the given session
    -h, --help                    Show help screen and exit
    --no-tmux                     Deactivate Tmux usage
    --debug                       Allow debugging with full exceptions and keeping tmux alive after Bliss shell exits
    -S, --show-sessions           Display available sessions and tree of sub-sessions
    --show-sessions-only          Display available sessions names only
"""

import warnings

warnings.filterwarnings("ignore", module="jinja2")

import os
import sys
import subprocess
from docopt import docopt, DocoptExit
import logging

from bliss import release
from bliss.config import get_sessions_list
from bliss.config import static
from bliss.config.static import Node
from bliss.config.conductor import client
from bliss import logging_startup
from bliss import current_session, global_map

from .repl import embed
from . import session_files_templates as sft

__all__ = ("main",)


def yes_or_no(question):
    answer = input(question + " (yes/no) ").lower().strip()
    print("")
    while not (answer in {"yes", "y"} or answer in {"no", "n"}):
        print("Input yes or no")
        answer = input(question + " (yes/no) ").lower().strip()
        print("")

    return answer[0] == "y"


def print_sessions_list(slist):
    for session in slist:
        print(session)


def print_sessions_and_trees(slist):
    print("Available BLISS sessions are:")
    config = static.get_config()
    for name in slist:
        session = config.get(name)
        session.sessions_tree.show()


def delete_session(session_name):
    print(("Removing '%s' session." % session_name))

    if session_name in get_sessions_list():
        config = static.get_config()

        # Gets config of the session by its name.
        session_config = config.get_config(session_name)

        # Gets the name of the setup file (found in YML file).
        setup_file_name = session_config.get("setup-file")

        # Gets name of the YML file.
        session_file = session_config.filename

        if setup_file_name is not None:
            # Gets the full path.
            if setup_file_name.startswith("."):  # relative path
                base_path = os.path.dirname(session_file)
                setup_file_name = os.path.normpath(
                    os.path.join(base_path, setup_file_name)
                )
                script_file_name = "scripts/%s.py" % session_name
                script_file_name = os.path.normpath(
                    os.path.join(base_path, script_file_name)
                )

            # Removes <session_name>_setup.py file.
            print(("removing .../%s" % setup_file_name))
            client.remove_config_file(setup_file_name)

        # Removes YML file.
        print(("removing .../%s" % session_file))
        client.remove_config_file(session_file)

        # Removes script file.
        print(("removing .../%s" % script_file_name))
        client.remove_config_file(script_file_name)


def create_session(session_name):
    """
    Creation of skeleton files for a new session:
       sessions/<session_name>.yml
       sessions/<session_name>_setup.py
       sessions/scripts/<session_name>.py

    This method is valid even if config directory is located on
    a remote computer.
    """
    print(("Creating '%s' BLISS session" % session_name))

    # <session_name>.yml: config file created as a config Node.
    file_name = "sessions/%s.yml" % session_name
    new_session_node = Node(filename=file_name)
    print(("Creating %s" % file_name))
    new_session_node.update(
        {
            "class": "Session",
            "name": session_name,
            "setup-file": "./%s_setup.py" % session_name,
            "config-objects": [],
        }
    )
    new_session_node.save()

    config = static.get_config()
    config.set_config_db_file("sessions/__init__.yml", "plugin: session\n")
    # <session_name>_setup.py: setup file of the session.
    skeleton = sft.xxx_setup_py_template.render(name=session_name)
    file_name = "sessions/%s_setup.py" % session_name
    print(("Creating %s" % file_name))
    config.set_config_db_file(file_name, skeleton)

    # scripts/<session_name>.py: additional python script file.
    skeleton = sft.xxx_py_template.render(name=session_name)
    file_name = "sessions/scripts/%s.py" % session_name
    print(("Creating %s" % file_name))
    config.set_config_db_file(file_name, skeleton)


def main():
    # Parse arguments wit docopt : it uses this file (main.py) docstring
    # to define parameters to handle.
    try:
        arguments = docopt(__doc__)
    except DocoptExit:
        print("")
        print("Available BLISS sessions:")
        print("-------------------------")
        print_sessions_list(get_sessions_list())
        print("")
        arguments = docopt(__doc__)

    # disable those ugly loggers from jedi
    logging.getLogger("parso.python.diff").disabled = True
    logging.getLogger("parso.cache").disabled = True
    # initialize logging
    log_level = getattr(logging, arguments["--log-level"][0].upper())
    logging_startup(log_level)

    # Print version
    if arguments["--version"]:
        print(("BLISS version %s" % release.short_version))
        sys.exit()

    # Display session names and trees
    if arguments["--show-sessions"]:
        print_sessions_and_trees(get_sessions_list())
        exit(0)

    # Display session names only
    if arguments["--show-sessions-only"]:
        print_sessions_list(get_sessions_list())
        exit(0)

    # Create session
    if arguments["--create"]:
        session_name = arguments["--create"]
        if session_name in get_sessions_list():
            print(("Session '%s' cannot be created: it already exists." % session_name))
            exit(0)
        elif session_name[0].isdigit():
            print(f"Invalid session name ({session_name}). Must start with [a-zA-Z_]")
            exit(0)
        else:
            create_session(session_name)
            # exit ( or launch new session ? )
            exit(0)

    # Delete session
    if arguments["--delete"]:
        session_name = arguments["--delete"]
        if session_name in get_sessions_list():
            if yes_or_no("Do you want to delete '%s' session?" % session_name):
                delete_session(session_name)
            exit(0)
        else:
            print(
                (
                    "Session '%s' cannot be deleted: it seems it does not exist."
                    % session_name
                )
            )
            exit(0)

    # Start a specific session
    if arguments["--session"]:
        session_name = arguments["--session"]
        if session_name not in get_sessions_list():
            print(("'%s' does not seem to be a valid session, exiting." % session_name))
            print_sessions_list(get_sessions_list())
            exit(0)
    else:
        session_name = None

    if arguments["--no-tmux"] or sys.platform in ["win32", "cygwin"]:
        # If session_name is None, an empty session is started.
        embed(session_name=session_name)
        current_session.close()
        global_map.clear()

    else:

        if session_name is None:
            session = (
                f"__DEFAULT__"  # {os.getpid()}
            )  # see __DEFAULT__ in bliss.shell.cli.repl => def cli()
        else:
            session = session_name

        from bliss import config

        config_path = os.path.join(os.path.dirname(config.__file__), "tmux.conf")

        win1 = "bliss"
        win2 = "scan"

        uid = os.geteuid()

        # not sure if we should use the user id instead => os.getuid()
        # euid (effective user id) can be different from uid.
        # The difference between the regular UID and the Effective UID is that
        # only the EUID is checked when you do something that requires special access
        #  (such as reading or writing a file, or making certain system calls).
        # The UID indicates the actual user who is performing the action,
        # but it is (usually) not considered when examining permissions.
        # In normal programs they will be the same.
        # Some programs change their EUID to add or subtract from the actions they are allowed to take.
        # A smaller number also change their UID, to effectively "become" another user.

        tsock = f"/tmp/bliss_tmux_{uid}.sock"

        ans = subprocess.run(
            ["tmux", "-S", tsock, "has-session", "-t", "=%s" % session],
            capture_output=True,
            text=True,
        )
        # print("stdout = ",ans.stdout,", stderr = ", ans.stderr,", returncode = ", ans.returncode)

        if ans.returncode == 0:
            print(f"Tmux session {session} already exist, joining session...")
        else:
            print(f"Starting new tmux session {session}...")
            ans = subprocess.run(["tmux", "-S", tsock, "start-server"])

            if arguments["--debug"]:
                ans = subprocess.run(
                    [
                        "tmux",
                        "-S",
                        tsock,
                        "-f",
                        config_path,
                        "new-session",
                        "-d",
                        "-s",
                        session,
                        "-n",
                        win1,
                    ]
                )

                sub_cmd = f"{sys.executable} -m bliss.shell.cli.start_bliss_repl {session} {arguments['--log-level'][0]} 1"
                ans = subprocess.run(
                    ["tmux", "-S", tsock, "send-keys", "-t", win1, sub_cmd, "Enter"]
                )

                ans = subprocess.run(
                    ["tmux", "-S", tsock, "new-window", "-d", "-n", win2]
                )

                sub_cmd = f"{sys.executable} -m bliss.data.start_listener {session}"
                ans = subprocess.run(
                    ["tmux", "-S", tsock, "send-keys", "-t", win2, sub_cmd, "Enter"]
                )

            else:
                ans = subprocess.run(
                    [
                        "tmux",
                        "-S",
                        tsock,
                        "-f",
                        config_path,
                        "new-session",
                        "-d",
                        "-s",
                        session,
                        "-n",
                        win1,
                        sys.executable,
                        "-m",
                        "bliss.shell.cli.start_bliss_repl",
                        session,
                        arguments["--log-level"][0],
                    ]
                )

                ans = subprocess.run(
                    [
                        "tmux",
                        "-S",
                        tsock,
                        "new-window",
                        "-d",
                        "-n",
                        win2,
                        sys.executable,
                        "-m",
                        "bliss.data.start_listener",
                        session,
                    ]
                )

        ans = subprocess.run(
            [
                "tmux",
                "-S",
                tsock,
                "set-hook",
                "-t",
                session,
                "pane-exited",
                "kill-session -t %s" % session,
            ]
        )
        ans = subprocess.run(["tmux", "-S", tsock, "attach-session", "-t", session])


if __name__ == "__main__":

    main()
