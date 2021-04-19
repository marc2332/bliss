# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import sys
import traceback
import time
import gevent
import atexit
import signal

from bliss.shell.data.display import ScanDataListener

if sys.platform not in ["win32", "cygwin"]:
    import termios
else:
    termios = None


def catch_sigint(*args):
    pass


def prevent_user_input():
    """Prevent user input in the terminal, if the feature is available"""
    if termios is None:
        return

    fd = sys.stdin.fileno()
    try:
        new = termios.tcgetattr(fd)
        new[3] &= ~termios.ECHO
        termios.tcsetattr(fd, termios.TCSANOW, new)
    except termios.error:
        pass  # not in terminal (example in tests)
    else:
        # revert 'Prevent user inputs if using a terminal'
        atexit.register(release_user_input)


def release_user_input(self):
    """Release user input, if it was locked with `_prevent_user_input`"""
    fd = sys.stdin.fileno()
    new = termios.tcgetattr(fd)
    new[3] |= termios.ECHO
    termios.tcsetattr(fd, termios.TCSANOW, new)


def main(session_name):
    # Prevent user to close the listener with Ctrl-C
    signal.signal(signal.SIGINT, catch_sigint)

    # Prevent user inputs if using a terminal
    prevent_user_input()

    while True:
        try:
            start_time = time.time()
            sdl = ScanDataListener(session_name)
            sdl.start()
        except Exception:
            exc_type, exc_value, tb = sys.exc_info()
            traceback.print_exception(exc_type, exc_value, tb)
            if (time.time() - start_time) < 5.0:
                gevent.sleep(5)


if __name__ == "__main__":
    main(sys.argv[1])
