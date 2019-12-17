#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
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
import time
import logging

from ptpython.repl import PythonRepl
import ptpython.layout

## imports needed to have control over _excecute of ptpython
import six
from ptpython.repl import _lex_python_result
from prompt_toolkit.formatted_text.utils import fragment_list_width
from prompt_toolkit.formatted_text import merge_formatted_text, FormattedText
from prompt_toolkit.formatted_text import PygmentsTokens
from prompt_toolkit.shortcuts import print_formatted_text

###

from prompt_toolkit.keys import Keys
from prompt_toolkit.utils import is_windows
from prompt_toolkit.eventloop.defaults import set_event_loop
from prompt_toolkit.eventloop import future

from prompt_toolkit.filters import has_focus
from prompt_toolkit.enums import DEFAULT_BUFFER
from prompt_toolkit.eventloop.defaults import run_in_executor

from bliss.shell.cli import style as repl_style
from bliss.shell import initialize
from bliss.data.display import ScanPrinter, ScanEventHandler
from .prompt import BlissPrompt
from .typing_helper import TypingHelper

from bliss.shell.standard import info
from bliss.shell.cli.ptpython_statusbar_patch import NEWstatus_bar, TMUXstatus_bar

logger = logging.getLogger(__name__)

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

if sys.platform in ["win32", "cygwin"]:
    import win32api


# =================== ERROR REPORTING ============================
class ErrorReport:
    """ 
    Manage the behavior of the error reporting in the shell.
    
    - ErrorReport.expert_mode = False (default) => prints a user friendly error message without traceback
    - ErrorReport.expert_mode = True            => prints the full error message with traceback
    
    - ErrorReport.last_error stores the last error traceback

    """

    def __init__(self):

        self._expert_mode = False
        self._last_error = ""

    @property
    def last_error(self):
        print(self._last_error)

    @property
    def expert_mode(self):
        return self._expert_mode

    @expert_mode.setter
    def expert_mode(self, enable):
        self._expert_mode = bool(enable)


def install_excepthook():
    """Patch the system exception hook,
    and the print exception for gevent greenlet
    """
    ERROR_REPORT = ErrorReport()

    logger = logging.getLogger("exceptions")

    def repl_excepthook(exc_type, exc_value, tb):
        err_file = sys.stderr

        # Store latest traceback (as a string to avoid memory leaks)
        ERROR_REPORT._last_error = "".join(
            traceback.format_exception(exc_type, exc_value, tb)
        )
        logger.error("", exc_info=True)

        # Adapt the error message depending on the ERROR_REPORT expert_mode
        if not ERROR_REPORT._expert_mode:
            print(
                f"!!! === {exc_type.__name__}: {exc_value} === !!! ( for more details type cmd 'last_error' )",
                file=err_file,
            )
        else:
            traceback.print_exception(exc_type, exc_value, tb, file=err_file)

    def print_exception(self, context, exc_type, exc_value, tb):
        repl_excepthook(exc_type, exc_value, tb)

    sys.excepthook = repl_excepthook
    gevent.hub.Hub.print_exception = print_exception
    return ERROR_REPORT


# Patch eventloop of prompt_toolkit to be synchronous
# don't patch the event loop on windows
def _set_pt_event_loop():
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


_set_pt_event_loop()


if sys.platform in ["win32", "cygwin"]:

    import win32api

    class Terminal:
        def __getattr__(self, prop):
            if prop.startswith("__"):
                raise AttributeError(prop)
            return ""


else:

    from blessings import Terminal


__all__ = ("BlissRepl", "embed", "cli", "configure_repl")  # , "configure")

#############
# patch ptpython signaturetoolbar
import bliss.shell.cli.ptpython_signature_patch

# add autocomplete_property to jedi's ALLOWED_DESCRIPTOR_ACCESS
from bliss.common.utils import autocomplete_property
from jedi.evaluate.compiled import access

access.ALLOWED_DESCRIPTOR_ACCESS += (autocomplete_property,)
#############


class BlissRepl(PythonRepl):
    def __init__(self, *args, **kwargs):
        prompt_label = kwargs.pop("prompt_label", "BLISS")
        title = kwargs.pop("title", None)
        session = kwargs.pop("session")

        # bliss_bar = status_bar(self)
        # toolbars = list(kwargs.pop("extra_toolbars", ()))
        # kwargs["_extra_toolbars"] = [bliss_bar] + toolbars

        # Catch and remove additional kwargs
        self.session_name = kwargs.pop("session_name", "default")
        self.use_tmux = kwargs.pop("use_tmux", False)

        # patch ptpython statusbar
        if self.use_tmux and sys.platform not in ["win32", "cygwin"]:
            ptpython.layout.status_bar = TMUXstatus_bar
        else:
            ptpython.layout.status_bar = NEWstatus_bar

        super(BlissRepl, self).__init__(*args, **kwargs)

        self.current_task = None
        if title:
            self.terminal_title = title

        # self.show_bliss_bar = True
        # self.bliss_bar = bliss_bar
        # self.bliss_bar_format = "normal"
        self.bliss_prompt_label = prompt_label
        self.bliss_session = session
        self.bliss_prompt = BlissPrompt(self)
        self.all_prompt_styles["bliss"] = self.bliss_prompt
        self.prompt_style = "bliss"
        self.show_signature = True
        self.ui_styles["bliss_ui"] = repl_style.bliss_ui_style
        self.use_ui_colorscheme("bliss_ui")

        # Records bliss color style and make it active in bliss shell.
        self.code_styles["bliss_code"] = repl_style.bliss_code_style
        self.use_code_colorscheme("bliss_code")

        # PTPYTHON SHELL PREFERENCES
        self.enable_history_search = True
        self.show_status_bar = True
        self.confirm_exit = True
        self.enable_mouse_support = False

        self.typing_helper = TypingHelper(self)

        self._application_stopper_callback = weakref.WeakSet()

    def _another_execute(self, line):
        """
        Evaluate the line and print the result.
        """
        output = self.app.output

        def compile_with_flags(code, mode):
            " Compile code with the right compiler flags. "
            return compile(
                code,
                "<stdin>",
                mode,
                flags=self.get_compiler_flags(),
                dont_inherit=True,
            )

        if line.lstrip().startswith("\x1a"):
            # When the input starts with Ctrl-Z, quit the REPL.
            self.app.exit()

        elif line.lstrip().startswith("!"):
            # Run as shell command
            os.system(line[1:])
        else:
            # Try eval first
            try:
                code = compile_with_flags(line, "eval")
                result = eval(code, self.get_globals(), self.get_locals())

                locals = self.get_locals()
                locals["_"] = locals["_%i" % self.current_statement_index] = result

                if result is not None:
                    out_prompt = self.get_output_prompt()

                    result_str = f"{info(result)}\n"  ## patched here!!

                    # Align every line to the first one.
                    line_sep = "\n" + " " * fragment_list_width(out_prompt)
                    result_str = line_sep.join(result_str.splitlines()) + "\n"

                    # Write output tokens.
                    if self.enable_syntax_highlighting:
                        formatted_output = merge_formatted_text(
                            [
                                out_prompt,
                                PygmentsTokens(list(_lex_python_result(result_str))),
                            ]
                        )
                    else:
                        formatted_output = FormattedText(
                            out_prompt + [("", result_str)]
                        )

                    print_formatted_text(
                        formatted_output,
                        style=self._current_style,
                        style_transformation=self.style_transformation,
                        include_default_pygments_style=False,
                    )

            # If not a valid `eval` expression, run using `exec` instead.
            except SyntaxError:
                code = compile_with_flags(line, "exec")
                six.exec_(code, self.get_globals(), self.get_locals())

            output.flush()

    def _execute_task(self, *args, **kwargs):
        try:
            # return super(BlissRepl, self)._execute(*args, **kwargs)
            return self._another_execute(*args, **kwargs)
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
                raise return_value[1].with_traceback(return_value[2]) from None
        except gevent.Timeout:
            self._handle_exception(*args)
        except KeyboardInterrupt:
            self.current_task.kill(KeyboardInterrupt)
            print("\n")
            raise
        finally:
            if args[0]:
                self.bliss_prompt.python_input.current_statement_index += 1
            self.current_task = None

    def stop_current_task(self, block=True, exception=gevent.GreenletExit):
        current_task = self.current_task
        if current_task is not None:
            current_task.kill(block=block, exception=exception)

    def register_application_stopper(self, func):
        """
        As ptpython only allow one Application at at time,
        callback registered will be called in case the shell re-enter in 
        the main loop. This should never happens except when something
        really go wrong.
        This is just a fallback to keep the repl loop running.
        """
        self._application_stopper_callback.add(func)

    def unregister_application_stopper(self, func):
        try:
            self._application_stopper_callback.remove(func)
        except KeyError:
            pass


CONFIGS = weakref.WeakValueDictionary()


def configure_repl(repl):

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

    @repl.add_key_binding(
        Keys.ControlSpace, filter=has_focus(DEFAULT_BUFFER), eager=True
    )
    def _(event):
        """
        Initialize autocompletion at cursor.
        If the autocompletion menu is not showing, display it with the
        appropriate completions for the context.
        If the menu is showing, select the next completion.
        """

        b = event.app.current_buffer
        if b.complete_state:
            b.complete_next()
        else:
            b.start_completion(select_first=False)


def cli(
    locals=None,
    session_name=None,
    vi_mode=False,
    startup_paths=None,
    eventloop=None,
    use_tmux=False,
    expert_error_report=False,
    **kwargs,
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
    from bliss import set_bliss_shell_mode

    set_bliss_shell_mode(True)

    # adding stdout print of lprint messages
    from bliss.common.logtools import logbook_printer

    logbook_printer.add_stdout_handler()

    ERROR_REPORT = install_excepthook()
    ERROR_REPORT.expert_mode = expert_error_report

    if session_name and not session_name.startswith("__DEFAULT__"):
        try:
            user_ns, session = initialize(session_name)
        except RuntimeError as e:
            if use_tmux:
                print("\n", "*" * 20, "\n", e, "\n", "*" * 20)
                gevent.sleep(10)  # just to let the eyes to see the message ;)
            raise
    else:
        user_ns, session = initialize(session_name=None)

    # ADD 2 GLOBALS TO HANDLE THE LAST ERROR AND THE ERROR REPORT MODE (IN SHELL ENV ONLY)
    user_ns["ERROR_REPORT"] = ERROR_REPORT
    user_ns["last_error"] = lambda: ERROR_REPORT.last_error

    def get_globals():
        return user_ns

    if session_name and not session_name.startswith("__DEFAULT__"):
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

    # Create REPL.
    repl = BlissRepl(
        get_globals=get_globals,
        session=session,
        vi_mode=vi_mode,
        prompt_label=prompt_label,
        title=session_title,
        history_filename=history_filename,
        startup_paths=startup_paths,
        session_name=session_name,
        use_tmux=use_tmux,
        **kwargs,
    )

    # Run registered configurations
    for idx in sorted(CONFIGS):
        try:
            CONFIGS[idx](repl)
        except:
            sys.excepthook(*sys.exc_info())

    # Custom keybindings
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

        # set old style print methods for the scans
        scan_printer = ScanPrinter()

        if sys.platform not in ["win32", "cygwin"] and cmd_line_i.use_tmux:
            # Catch scan events to show the scan display window
            seh = ScanEventHandler(cmd_line_i)

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

            # traps SIGINT (from ctrl-c or kill -INT)
            signal.signal(signal.SIGINT, stop_with_keyboard_interrupt)

            # traps SIGTERM (ctrl-d or kill)
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
            # stop all Application
            if cmd_line_i._application_stopper_callback:
                # Should never happen but...
                print("Warning some application left running")
                for stop_callback in list(cmd_line_i._application_stopper_callback):
                    stop_callback()

            try:
                inp = cmd_line_i.app.run()
                logging.getLogger("user_input").info(f"{inp}")
                cmd_line_i._execute(inp)
            except KeyboardInterrupt:
                cmd_line_i.default_buffer.reset()
            except EOFError:
                # ctrl d
                break
            except (SystemExit):
                # kill and exit()
                break
            except BaseException:
                sys.excepthook(*sys.exc_info())

    finally:
        warnings.filterwarnings("default")


if __name__ == "__main__":
    embed()
