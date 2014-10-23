# -*- coding: utf-8 -*-
"""
gevent's inputhook support function

Code is very similar to the same kind of hook for Qt4...
(see file included in IPython)

Author: Matias Guijarro
"""
import sys
import gevent
from gevent import select
from IPython.core.interactiveshell import InteractiveShell
from IPython.lib.inputhook import InputHookManager, allow_CTRL_C

def create_inputhook_gevent(mgr):
    """Create an input hook for running the gevent event loop.

    Parameters
    ----------
    mgr : an InputHookManager

    Returns
    -------
    An inputhook
    """

    # Re-use previously created inputhook if any
    ip = InteractiveShell.instance()
    if hasattr(ip, '_inputhook_gevent'):
        return ip._inputhook_gevent

    got_kbdint = [False]

    def inputhook_gevent():
        """PyOS_InputHook python hook for Gevent.
        """
        allow_CTRL_C()

        try:
            select.select([sys.stdin], [], [])
        except:
            from traceback import print_exc
            print_exc()
        return 0

    def preprompthook_gevent(ishell):
        if got_kbdint[0]:
            mgr.set_inputhook(inputhook_gevent)
        got_kbdint[0] = False

    ip._inputhook_gevent = inputhook_gevent
    ip.set_hook('pre_prompt_hook', preprompthook_gevent)

    return inputhook_gevent


def enable_gevent():
    mgr = InputHookManager()
    mgr.set_inputhook(create_inputhook_gevent(mgr))
