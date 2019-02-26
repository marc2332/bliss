#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Bliss REPL (Read Eval Print Loop)"""

import os
import sys
import signal
import weakref
import warnings
import functools
import traceback
import gevent

from ptpython.repl import PythonRepl
from prompt_toolkit.keys import Keys
from prompt_toolkit.history import History

from .prompt import BlissPrompt
from .typing_helper import TypingHelper

from bliss.shell import initialize, ScanListener


__all__ = ("BlissRepl", "embed", "cli", "configure_repl")  # , "configure")

REPL = None


class BlissRepl(PythonRepl):
    def __init__(self, *args, **kwargs):
        prompt_label = kwargs.pop("prompt_label", "BLISS")
        title = kwargs.pop("title", None)
        scan_listener = kwargs.pop("scan_listener")
        session = kwargs.pop("session")
        # bliss_bar = status_bar(self)
        # toolbars = list(kwargs.pop("extra_toolbars", ()))
        # kwargs["_extra_toolbars"] = [bliss_bar] + toolbars
        super(BlissRepl, self).__init__(*args, **kwargs)

        self.current_task = None
        if title:
            self.terminal_title = title
        self.show_status_bar = False
        # self.show_bliss_bar = True
        # self.bliss_bar = bliss_bar
        # self.bliss_bar_format = "normal"
        self.bliss_prompt_label = prompt_label
        self.bliss_session = session
        self.bliss_scan_listener = scan_listener
        self.all_prompt_styles["bliss"] = BlissPrompt(self)
        self.prompt_style = "bliss"
        self.show_signature = True
        # self.install_ui_colorscheme("bliss", bliss_ui_style)
        # self.use_ui_colorscheme("bliss")

        self.typing_helper = TypingHelper(self)

    def _execute_task(self, *args, **kwargs):
        try:
            return super(BlissRepl, self)._execute(*args, **kwargs)
        except:
            return sys.exc_info()

    def _execute(self, *args, **kwargs):
        self.current_task = gevent.spawn(self._execute_task, *args, **kwargs)
        try:
            return_value = self.current_task.get()
            if (
                isinstance(return_value, tuple)
                and len(return_value) >= 3
                and isinstance(return_value[1], (BaseException, Exception))
            ):
                raise return_value[1].with_traceback(return_value[2])
        except gevent.Timeout:
            self._handle_exception(*args)
        finally:
            self.current_task = None

    def stop_current_task(self, block=True, exception=gevent.GreenletExit):
        current_task = self.current_task
        if current_task is not None:
            current_task.kill(block=block, exception=exception)


CONFIGS = weakref.WeakValueDictionary()


def configure_repl(repl):
    @repl.add_key_binding(Keys.ControlC)
    def _(event):
        repl.stop_current_task()

    # intended to be used for testing as ctrl+t can be send via stdin.write(bytes.fromhex("14"))
    # @repl.add_key_binding(Keys.ControlT)
    # def _(event):
    #    sys.stderr.write("<<BLISS REPL TEST>>")
    #    text = repl.default_buffer.text
    #    sys.stderr.write("<<BUFFER TEST>>")
    #    sys.stderr.write(text)
    #    sys.stderr.write("<<BUFFER TEST>>")
    #    sys.stderr.write("<<HISTORY>>")
    #    sys.stderr.write(repl.default_buffer.history._loaded_strings[-1])
    #    sys.stderr.write("<<HISTORY>>")
    #    sys.stderr.write("<<BLISS REPL TEST>>")


def cli(
    locals=None,
    session_name=None,
    vi_mode=False,
    startup_paths=None,
    eventloop=None,
    refresh_interval=1.0,
):
    """
    Create a command line interface without running it::

        from bliss.shell.cli.repl import cli
        from signal import SIGINT, SIGTERM

        cmd_line_iface = cli(locals=locals())
        cmd_line_iface.run()

    Args:
        session_name : session to initialize (default: None)
        vi_mode (bool): Use Vi instead of Emacs key bindings.
        eventloop: use a specific eventloop (default: PosixGeventLoop)
        refresh_interval (float): cli refresh interval (seconds)
                                  (default: 0.25s). Use 0 or None to
                                  deactivate refresh.
    """
    user_ns, session = initialize(session_name)

    locals = locals or user_ns

    def get_globals():
        return user_ns  # , REPL=repl)

    def get_locals():  # -*- coding: utf-8 -*-

        return locals

    if session_name:
        session_id = session_name
        session_title = "Bliss shell ({0})".format(session_name)
        history_filename = ".%s_%s_history" % (
            os.path.basename(sys.argv[0]),
            session_id,
        )
        prompt_label = session_name.upper()
    else:
        session_id = "default"
        session_title = "Bliss shell"
        history_filename = ".%s_history" % os.path.basename(sys.argv[0])
        prompt_label = "BLISS"

    history_filename = os.path.join(os.environ["HOME"], history_filename)

    scan_listener = ScanListener()

    # Create REPL.
    repl = BlissRepl(
        get_globals,
        get_locals,
        session=session,
        scan_listener=scan_listener,
        vi_mode=vi_mode,
        prompt_label=prompt_label,
        title=session_title,
        history_filename=history_filename,
        startup_paths=startup_paths,
    )

    global REPL
    REPL = repl

    # Run registered configurations
    for idx in sorted(CONFIGS):
        try:
            CONFIGS[idx](repl)
        except:
            sys.excepthook(*sys.exc_info())

    configure_repl(repl)

    return repl


def embed(*args, **kwargs):
    """
    Call this to embed bliss shell at the current point in your program::

        from bliss.shell.cli.repl import cli
        from signal import SIGINT, SIGTERM

        embed(locals=locals())

    Args:
        session_name : session to initialize (default: None)
        vi_mode (bool): Use Vi instead of Emacs key bindings.
        eventloop: use a specific eventloop (default: PosixGeventLoop)
        refresh_interval (float): cli refresh interval (seconds)
                                  (default: 0.25s). Use 0 or None to
                                  deactivate refresh.
        stop_signals (bool): if True (default), registers SIGINT and SIGTERM
                             signals to stop the current task
    """
    stop_signals = kwargs.pop("stop_signals", True)

    # Hide the warnings from the users
    warnings.filterwarnings("ignore")
    try:
        cmd_line_i = cli(*args, **kwargs)

        if stop_signals:

            def stop_current_task(signum, frame, exception=gevent.GreenletExit):
                cmd_line_i.stop_current_task(block=False, exception=exception)

            stop_with_keyboard_interrupt = functools.partial(
                stop_current_task, exception=KeyboardInterrupt
            )

            r, w = os.pipe()

            def stop_current_task_and_exit(signum, frame):
                stop_current_task(signum, frame)
                os.close(w)

            signal.signal(signal.SIGINT, stop_with_keyboard_interrupt)
            signal.signal(signal.SIGTERM, stop_current_task_and_exit)

            def watch_pipe(r):
                gevent.select.select([r], [], [])
                exit()

            gevent.spawn(watch_pipe, r)

        while True:
            try:
                inp = cmd_line_i.app.run()
                cmd_line_i._execute(inp)

            except KeyboardInterrupt:
                # ctrl c
                pass
            except EOFError:
                # ctrl d
                break
            except (SystemExit):
                # kill and exit()
                print("")
                break
            except BaseException as e:
                # all unexpected Errors and exceptions ... should be logged

                # this could be the output in a less scary way for non python users
                # related to isssu 402
                # for x in traceback.format_exception_only(type(e), e): print(x)

                # a bit more verbose output should/could be activated/deactivated
                traceback.print_exception(type(e), e, e.__traceback__)
                pass

    finally:
        warnings.filterwarnings("default")


if __name__ == "__main__":
    embed()
