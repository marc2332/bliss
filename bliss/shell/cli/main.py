# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016-2018 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
 
Usage: bliss [-l | --log-level=<log_level>] [-s <name> | --session=<name>]
       bliss [-c | --create-session=<name>]
       bliss [-v | --version]
       bliss [-h | --help]
       bliss --show-sessions
       bliss --show-sessions-only

Options:
    -l, --log-level=<log_level>   Log level [default: WARN] (CRITICAL ERROR INFO DEBUG NOTSET)
    -s, --session=<session_name>  Start with the specified session
    -v, --version                 Show version and exit
    -h, --help                    Show help screen and exit
    --show-sessions               Display available sessions and tree of sub-sessions
    --show-sessions-only          Display available sessions names only
 
"""
#-c, --create=<session_name>   Create a new session with the given name

import sys
import logging
from docopt import docopt, DocoptExit

from bliss.config import static

from .repl import embed

__all__ = ('main',)

VERSION = 0.07


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
        print ("BLISS version %s" % VERSION)
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
    #if arguments['--create']:
    #    session_name = arguments['--create'][0]
    #    if session_name in sessions_list:
    #        print ("Session '%s' cannot be created: it already exists." % session_name)
    #        exit(0)
    #    else:
    #        print ("Creation of '%s' session : To be implemented :) " % session_name)
    #        # exit or launch new session ?
    #        exit(0)

    # Start a specific session
    if arguments['--session']:
        session_name = arguments['--session']
        if session_name not in sessions_list:
            print "'%s' does not seem to be a valid session, exiting." % session_name
            print_sessions_list(sessions_list)
            exit(0)

    # If session_name is None, an empty session is started.
    embed(session_name=session_name)

if __name__ == '__main__':
    main()
