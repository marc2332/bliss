# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016-2018 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Usage: bliss [-l | --log-level=<log_level>] [-s <name> | --session=<name>]
       bliss [-v | --version]
       bliss [-c <name> | --create=<name>]
       bliss [-d <name> | --delete=<name>]
       bliss [-h | --help]
       bliss --show-sessions
       bliss --show-sessions-only

Options:
    -l, --log-level=<log_level>   Log level [default: WARN] (CRITICAL ERROR INFO DEBUG NOTSET)
    -s, --session=<session_name>  Start with the specified session
    -v, --version                 Show version and exit
    -c, --create=<session_name>   Create a new session with the given name
    -d, --delete=<session_name>   Delete the given session
    -h, --help                    Show help screen and exit
    --show-sessions               Display available sessions and tree of sub-sessions
    --show-sessions-only          Display available sessions names only
"""

import os
import sys
import logging
from docopt import docopt, DocoptExit
from jinja2 import Template

from bliss import release
from bliss.config import static

from .repl import embed

__all__ = ('main',)


def get_sessions_list():
    """Return a list of available sessions found in config"""
    all_sessions = list()
    config = static.get_config()
    for name in config.names_list:
        c = config.get_config(name)
        if c.get('class') != 'Session':
            continue
        if c.get_inherited('plugin') != 'session':
            continue
        all_sessions.append(name)

    return all_sessions


def print_sessions_list(slist):
    for session in slist:
        print session


def print_sessions_and_trees(slist):
    print "Available BLISS sessions are:"
    config = static.get_config()
    for name in slist:
        session = config.get(name)
        session.sessions_tree.show()


def delete_session(session_name):
    print("removing '%s' session" % session_name)

    dirname = "%s/local/beamline_configuration/sessions" % os.environ['HOME']
    xxx_setup_py_name = "%s/%s_setup.py" % (dirname, session_name)
    xxx_yml_name = "%s/%s.yml" % (dirname, session_name)
    xxx_py_name = "%s/scripts/%s.py" % (dirname, session_name)

    print("Are you sure you want to delete: ")
    print("rm %s" % xxx_setup_py_name)
    print("rm %s" % xxx_yml_name)
    print("rm %s" % xxx_py_name)
    print("")
    print("hummm, do it manualy for now...")

    # os.remove(xxx_setup_py_name)
    # os.remove(xxx_yml_name)
    # os.remove(xxx_py_name)


def create_session(session_name):
    print("creating '%s' session" % session_name)

    # Test, and create if needed, directories:
    # ~/local/beamline_configuration/sessions/scripts/
    # ~/local/beamline_configuration/<beamline_name>/motors/
#    or
    # ~/local/beamline_configuration/<computer_name>/motors/

    dirname = "%s/local/beamline_configuration/sessions" % os.environ['HOME']
    if not os.path.isdir("%s/%s" % (dirname, "scripts")):
        print("creating : %s/%s" % (dirname, "scripts"))
        os.makedirs("%s/%s" % (dirname, "scripts"))

    # # # # files to create in ~/local/beamline_configuration/sessions/:

    # <session_name>_setup.py
    xxx_setup_py_name = "%s/%s_setup.py" % (dirname, session_name)
    xxx_setup_py_template = Template("""
from bliss import setup_globals


print(\"\")
print(\"Welcome to your new '{{ name }}' BLISS session !! \")
print(\"\")
print(\"You can now customize your '{{ name }}' session by changing these files:\")
print(\"   * {{ dir }}/{{ name }}_setup.py \")
print(\"   * {{ dir }}/{{ name }}.yml \")
print(\"   * {{ dir }}/scripts/{{ name }}.py \")
print(\"\")
""")
    # print xxx_setup_py_template.render(name=session_name)
    print "Creating:", xxx_setup_py_name
    with open(xxx_setup_py_name, mode='a+') as f:
        f.write(xxx_setup_py_template.render(name=session_name, dir=dirname))

    # <session_name>.yml
    xxx_yml_name = "%s/%s.yml" % (dirname, session_name)
    xxx_yml_template = Template("""
- class: Session
  name: {{ name }}
  setup-file: ./{{ name }}_setup.py
""")
    # print xxx_yml_template.render(name=session_name)
    print "Creating:", xxx_yml_name
    with open(xxx_yml_name, mode='a+') as f:
        f.write(xxx_yml_template.render(name=session_name))

    # scripts/<session_name>.py
    xxx_py_name = "%s/scripts/%s.py" % (dirname, session_name)
    xxx_py_template = Template("""
from bliss.shell.cli import configure
from bliss.shell.cli.layout import AxisStatus, LabelWidget, DynamicWidget
from bliss.shell.cli.esrf import Attribute, FEStatus, IDStatus, BEAMLINE

import time

def what_time_is_it():
    return time.ctime()

@configure
def config(repl):
    repl.bliss_bar.items.append(LabelWidget(\"BL=ID245c\"))
    repl.bliss_bar.items.append(AxisStatus('simot1'))
    repl.bliss_bar.items.append(DynamicWidget(what_time_is_it))
""")
    beamline_name = "ID00"
    # print xxx_py_template.render(bl_name=beamline_name)
    print "Creating:", xxx_py_name
    with open(xxx_py_name, mode='a+') as f:
        f.write(xxx_py_template.render(name=session_name))


def main():
    # Parse arguments wit docopt : it uses this file (main.py) docstring
    # to define parameters to handle.
    sessions_list = get_sessions_list()

    try:
        arguments = docopt(__doc__)
    except DocoptExit:
        print "Available sessions:"
        print_sessions_list(sessions_list)
        arguments = docopt(__doc__)

    # log level
    log_level = getattr(logging, arguments['--log-level'][0].upper())
    fmt = '%(levelname)s %(asctime)-15s %(name)s: %(message)s'
    logging.basicConfig(level=log_level, format=fmt)

    # Print version
    if arguments['--version']:
        print ("BLISS version %s" % release.short_version)
        sys.exit()

    # Display session names and trees
    if arguments['--show-sessions']:
        print_sessions_and_trees(sessions_list)
        exit(0)

    # Display session names only
    if arguments['--show-sessions-only']:
        print_sessions_list(sessions_list)
        exit(0)

    # Create session
    if arguments['--create']:
        session_name = arguments['--create']
        if session_name in sessions_list:
            print ("Session '%s' cannot be created: it already exists." % session_name)
            exit(0)
        else:
            create_session(session_name)
            # exit ( or launch new session ? )
            exit(0)

    # Delete session
    if arguments['--delete']:
        session_name = arguments['--delete']
        if session_name in sessions_list:
            delete_session(session_name)
            exit(0)
        else:
            print ("Session '%s' cannot be deleted: it seems it does not exist." % session_name)
            exit(0)

    # Start a specific session
    if arguments['--session']:
        session_name = arguments['--session']
        if session_name not in sessions_list:
            print("'%s' does not seem to be a valid session, exiting." % session_name)
            print_sessions_list(sessions_list)
            exit(0)
    else:
        session_name = None

    # If session_name is None, an empty session is started.
    embed(session_name=session_name)

if __name__ == '__main__':
    main()
