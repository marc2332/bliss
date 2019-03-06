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

warnings.filterwarnings("ignore", module="jinja2")

from ptpython.repl import PythonRepl
from prompt_toolkit.keys import Keys
from prompt_toolkit.history import History
from prompt_toolkit.utils import is_windows
from prompt_toolkit.eventloop.defaults import set_event_loop
from prompt_toolkit.eventloop import future

from bliss import setup_globals


class ErrorReport:
    """ 
    Manage the behavior of the error reporting in the shell.
    
    - ErrorReport.expert_mode = False (default) => prints a user friendly error message without traceback
    - ErrorReport.expert_mode = True            => prints the full error message with traceback
    
    - ErrorReport.last_error stores the last error traceback

    """

    def __init__(self):

        self._expert_mode = False
        self._last_error = "No error"

    @property
    def last_error(self):
        print(self._last_error)

    @property
    def expert_mode(self):
        return self._expert_mode

    @expert_mode.setter
    def expert_mode(self, enable):
        self._expert_mode = bool(enable)


setup_globals.ERROR_REPORT = ErrorReport()

# don't patch the event loop on windows
if not is_windows():
    from prompt_toolkit.eventloop.posix import PosixEventLoop

    class _PosixLoop(PosixEventLoop):
        def run_in_executor(self, callback, _daemon=False):
            t = gevent.spawn(callback)

            class F(future.Future):
                def result(self):
                    if not t.ready():
                        raise future.InvalidStateError
                    return t.get()

                def add_done_callback(self, callback):
                    t.link(callback)

                def exception(self):
                    return t.exception

                def done(self):
                    return t.ready()

            return F()

    set_event_loop(_PosixLoop())

from .prompt import BlissPrompt
from .typing_helper import TypingHelper

from bliss.shell import initialize, ScanListener

if sys.platform in ["win32", "cygwin"]:
    import win32api


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
        self.bliss_prompt = BlissPrompt(self)
        self.all_prompt_styles["bliss"] = self.bliss_prompt
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
            if args[0]:
                self.bliss_prompt.python_input.current_statement_index += 1
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

    import __main__

    __main__.__dict__.update(user_ns)

    def get_globals():
        return __main__.__dict__

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

    if sys.platform in ["win32", "cygwin"]:
        history_filename = os.path.join(os.environ["USERPROFILE"], history_filename)
    else:
        history_filename = os.path.join(os.environ["HOME"], history_filename)

    scan_listener = ScanListener()

    # Create REPL.
    repl = BlissRepl(
        get_globals=get_globals,
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
                gevent.os.tp_read(r, 1)
                exit()

            gevent.spawn(watch_pipe, r)

            # ============ handle CTRL-C under windows  ============
            # ONLY FOR Win7 (COULD BE IGNORED ON Win10 WHERE CTRL-C PRODUCES A SIGINT)
            if sys.platform in ["win32", "cygwin"]:

                def CTRL_C_handler(a, b=None):
                    cmd_line_i.stop_current_task(
                        block=False, exception=KeyboardInterrupt
                    )

                # ===== Install CTRL_C handler ======================
                win32api.SetConsoleCtrlHandler(CTRL_C_handler, True)

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

                # Store latest traceback (as a string to avoid memory leaks)
                setup_globals.ERROR_REPORT._last_error = str(traceback.format_exc())

                # Adapt the error message depending on the ERROR_REPORT expert_mode
                if not setup_globals.ERROR_REPORT._expert_mode:
                    err_txt = "Error occurs in command: '%s' => '%s' " % (inp, e)

                    print(
                        "!!! === %s === !!! ( for more details type cmd 'last_error' )"
                        % err_txt
                    )
                    print("\n")
                else:
                    traceback.print_exception(type(e), e, e.__traceback__)
                    print("\n")
                pass

    finally:
        warnings.filterwarnings("default")


if __name__ == "__main__":
    embed()
