# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Usage: bliss [--log-level=<log_level>] [(-s | --session)] <name>
       bliss [--show-sessions]
       bliss [--log-level=<log_level>]
       bliss (-h | --help)
Options:
    --log-level=<log_level>       Log level [default: WARN].
    --show-sessions               Display available sessions.
    -s, --session                 Starts with some session(s).
    -h, --help                    Show this screen.
"""

import logging

import docopt

from bliss.config import static

from .repl import embed

__all__ = ('main',)

def get_sessions_list():
    all_sessions = list()
    config = static.get_config()
    for name in config.names_list:
        c = config.get_config(name)
        if c.get('class') != 'Session': continue
        if c.get_inherited('plugin') != 'session': continue
        all_sessions.append(name)
    return all_sessions

def main():
    try:
        # Parse arguments, use file docstring as a parameter definition
        arguments = docopt.docopt(__doc__)
        session_name = arguments['<name>']
    except docopt.DocoptExit as e:
        print e.message
    else:
        log_level = getattr(logging, arguments['--log-level'].upper())
        fmt = '%(levelname)s %(asctime)-15s %(name)s: %(message)s'
        logging.basicConfig(level=log_level, format=fmt)
       
        if session_name is not None: 
            sessions_list = get_sessions_list()

            if arguments['--show-sessions']:
                print 'Session name(s):'
                config = static.get_config()
                for name in sessions_list:
                    session = config.get(name)
                    session.sessions_tree.show()
                exit(0)
            else:
                if session_name not in sessions_list:
                    print "'%s` does not seem to be a valid session, exiting." % session_name
                    exit(0)
        embed(session_name=session_name)
        

if __name__ == '__main__':
    main()
