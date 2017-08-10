# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Usage: bliss [--log-level=<log_level>] [(-s | --session)] <name>...
       bliss [--show-sessions]
       bliss
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


def main():
    try:
        # Parse arguments, use file docstring as a parameter definition
        arguments = docopt.docopt(__doc__)
        session_names = arguments['<name>']
    except docopt.DocoptExit as e:
        print e.message
    else:
        log_level = getattr(logging, arguments['--log-level'].upper())
        fmt = '%(levelname)s %(asctime)-15s %(name)s: %(message)s'
        logging.basicConfig(level=log_level, format=fmt)

        if arguments['--show-sessions']:
            config = static.get_config()
            print 'Session name(s):'
            for name in config.names_list:
                c = config.get_config(name)
                if c.get('class') != 'Session': continue
                if c.get_inherited('plugin') != 'session': continue
                print ' '*4,name
            exit(0)

        embed(session_names=session_names)
        

if __name__ == '__main__':
    main()
