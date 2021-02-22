# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Bliss REPL (Read Eval Print Loop)"""

import builtins
import os
import sys
import signal
import weakref
import warnings
import functools
import traceback
import gevent
import logging
import platform
from gevent import socket

import __future__
from collections import deque, defaultdict
from datetime import datetime

from ptpython.repl import PythonRepl
import ptpython.layout

# imports needed to have control over _execute of ptpython
from ptpython.repl import _lex_python_result
from prompt_toolkit.formatted_text.utils import fragment_list_width
from prompt_toolkit.formatted_text import merge_formatted_text, FormattedText
from prompt_toolkit.formatted_text import PygmentsTokens
from prompt_toolkit.shortcuts import print_formatted_text
from prompt_toolkit.keys import Keys
from prompt_toolkit.utils import is_windows
from prompt_toolkit.eventloop.defaults import set_event_loop
from prompt_toolkit.eventloop import future
from prompt_toolkit.filters import has_focus
from prompt_toolkit.enums import DEFAULT_BUFFER

from bliss.shell.data.display import ScanPrinter, ScanPrinterWithProgressBar
from bliss.shell.cli import style as repl_style
from bliss.shell.cli.prompt import BlissPrompt
from bliss.shell.cli.typing_helper import TypingHelper
from bliss.shell.cli.ptpython_statusbar_patch import NEWstatus_bar, TMUXstatus_bar

from bliss.common.utils import ShellStr
from bliss.common import constants
from bliss import release, current_session
from bliss.config import static
from bliss.shell.standard import info
from bliss.common.logtools import userlogger, elogbook
from bliss.shell.cli.protected_dict import ProtectedDict
from bliss.shell import standard
from redis.exceptions import ConnectionError

from bliss.common import session as session_mdl
from bliss.common.session import DefaultSession
from bliss.config.conductor.client import get_default_connection
from bliss.shell.bliss_banners import print_rainbow_banner


logger = logging.getLogger(__name__)

if sys.platform in ["win32", "cygwin"]:
    import win32api

    class Terminal:
        def __getattr__(self, prop):
            if prop.startswith("__"):
                raise AttributeError(prop)
            return ""


else:
    from blessings import Terminal


session_mdl.set_current_session = functools.partial(
    session_mdl.set_current_session, force=False
)


# =================== ERROR REPORTING ============================


class LastError:
    def __init__(self):
        self.errors = deque()

    def __getitem__(self, index):
        try:
            return ShellStr(self.errors[index])
        except IndexError:
            return ShellStr(
                f"No exception with index {index} found, size is {len(self.errors)}"
            )

    def __repr__(self):
        try:
            return ShellStr(self.errors[-1])
        except IndexError:
            return "Not yet exceptions in this session"

    def append(self, item):
        self.errors.append(item)
        while len(self.errors) > 100:
            self.errors.popleft()


class ErrorReport:
    """
    Manage the behavior of the error reporting in the shell.

    - ErrorReport.expert_mode = False (default) => prints a user friendly error message without traceback
    - ErrorReport.expert_mode = True            => prints the full error message with traceback

    - ErrorReport.last_error stores the last error traceback

    """

    _orig_sys_excepthook = sys.excepthook
    _orig_gevent_print_exception = gevent.hub.Hub.print_exception

    def __init__(self):
        self._expert_mode = False
        self._last_error = LastError()

    @property
    def last_error(self):
        return self._last_error

    @property
    def expert_mode(self):
        return self._expert_mode

    @expert_mode.setter
    def expert_mode(self, enable):
        self._expert_mode = bool(enable)


class CaptureOutput:
    SIZE = 20
    MAX_PARAGRAPH_SIZE = 1000
    patched = False

    _data = defaultdict(list)
    history_num = 1

    def to_str(self, index: int) -> str:
        return "".join(self._data[index])[:-1]

    def append(self, args, kwargs):
        if len(self._data) > self.MAX_PARAGRAPH_SIZE:
            return

        args = (str(arg) for arg in args)
        sep = kwargs.pop("sep", " ")
        end = kwargs.pop("end", "\n")

        stringed = sep.join(args) + end

        self._data[self.history_num].append(stringed)

    def __len__(self):
        return len(self._data)

    def end_of_paragraph(self, num):
        type(self).history_num = num
        self._data[self.history_num] = []
        try:
            del self._data[self.history_num - self.SIZE]
        except KeyError:
            pass

    def __getitem__(self, index):
        """
        Use [-1] to get the last element stdout
        or [n] coresponding to shell output line number
        """
        if index < 0:
            index = self.history_num + index
        if index not in self._data:
            raise IndexError
        return self.to_str(index)

    def patch_print(self):
        def memorize_arguments(func):
            @functools.wraps(func)
            def wrapped(*args, **kwargs):
                self.append(args, dict(kwargs))
                return func(*args, **kwargs)

            return wrapped

        if not self.patched:
            builtins.print = memorize_arguments(builtins.print)
            type(self).patched = True


def install_excepthook():
    """Patch the system exception hook,
    and the print exception for gevent greenlet
    """
    ERROR_REPORT = ErrorReport()

    logger = logging.getLogger("exceptions")

    from bliss import current_session

    def repl_excepthook(exc_type, exc_value, tb, _with_elogbook=True):
        err_file = sys.stderr

        # Store latest traceback (as a string to avoid memory leaks)
        ERROR_REPORT._last_error.append(
            datetime.now().strftime("%d/%m/%Y %H:%M:%S ")
            + "".join(traceback.format_exception(exc_type, exc_value, tb))
        )

        logger.error("", exc_info=True)

        # Adapt the error message depending on the ERROR_REPORT expert_mode
        if ERROR_REPORT._expert_mode:
            traceback.print_exception(exc_type, exc_value, tb, file=err_file)
        elif current_session:
            if current_session.is_loading_config:
                print(f"{exc_type.__name__}: {exc_value}", file=err_file)
            else:
                print(
                    f"!!! === {exc_type.__name__}: {exc_value} === !!! ( for more details type cmd 'last_error' )",
                    file=err_file,
                )

        if _with_elogbook:
            try:
                elogbook.error(f"{exc_type.__name__}: {exc_value}")
            except Exception:
                repl_excepthook(*sys.exc_info(), _with_elogbook=False)

    def print_exception(self, context, exc_type, exc_value, tb):
        if gevent.getcurrent() == gevent.get_hub():
            # repl_excepthook tries to yield to the gevent loop
            gevent.spawn(repl_excepthook, exc_type, exc_value, tb)
        else:
            repl_excepthook(exc_type, exc_value, tb)

    sys.excepthook = repl_excepthook
    gevent.hub.Hub.print_exception = print_exception
    return ERROR_REPORT


def reset_excepthook():
    sys.excepthook = ErrorReport._orig_sys_excepthook
    gevent.hub.Hub.print_exception = ErrorReport._orig_gevent_print_exception


# Patch eventloop of prompt_toolkit to be synchronous
# don't patch the event loop on windows
def _set_pt_event_loop():
    if not is_windows():
        import fcntl
        from prompt_toolkit.eventloop.posix import PosixEventLoop
        from prompt_toolkit.eventloop.select import PollSelector

        class _PosixLoop(PosixEventLoop):
            EVENT_LOOP_DAEMON_GREENLETS = weakref.WeakSet()

            def __init__(self, *kwargs):
                super().__init__(selector=PollSelector)
                # ensure that write schedule pipe is non blocking
                fcntl.fcntl(self._schedule_pipe[1], fcntl.F_SETFL, os.O_NONBLOCK)

            def run_in_executor(self, callback, _daemon=False):
                t = gevent.spawn(callback)
                if _daemon:
                    _PosixLoop.EVENT_LOOP_DAEMON_GREENLETS.add(t)

                class F(future.Future):
                    def result(self):
                        if not t.ready():
                            raise future.InvalidStateError
                        return t.get()

                    def add_done_callback(self, callback):
                        t.link(callback)

                    def set_exception(self, exception):
                        t.kill(exception)

                    def exception(self):
                        return t.exception

                    def done(self):
                        return t.ready()

                return F()

            def close(self):
                super().close()
                gevent.killall(_PosixLoop.EVENT_LOOP_DAEMON_GREENLETS)

        set_event_loop(_PosixLoop())


__all__ = ("BlissRepl", "embed", "cli", "configure_repl")

#############
# patch ptpython signaturetoolbar
import bliss.shell.cli.ptpython_signature_patch

# patch ptpython completer
import bliss.shell.cli.ptpython_completer_patch

# add autocomplete_property to jedi's ALLOWED_DESCRIPTOR_ACCESS
from bliss.common.utils import autocomplete_property
import jedi

jedi.Interpreter._allow_descriptor_getattr_default = False
jedi.inference.compiled.access.ALLOWED_DESCRIPTOR_ACCESS += (autocomplete_property,)
#############


class BlissRepl(PythonRepl):
    def __init__(self, *args, **kwargs):
        _set_pt_event_loop()

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

        super().__init__(*args, **kwargs)

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

        self.captured_output = CaptureOutput()
        self.captured_output.patch_print()

        if self.use_tmux:
            self.exit_message = (
                "Do you really want to close session? (CTRL-B D to detach)"
            )

        self.typing_helper = TypingHelper(self)

        self._application_stopper_callback = weakref.WeakSet()

    def get_compiler_flags(self):
        """
        Give the current compiler flags by looking for _Feature instances
        in the globals. Pached here to avoid `Unhandled exception in event loop` e.g. on quit.
        """
        flags = 0

        for value in self.get_globals().values():
            try:
                if isinstance(value, __future__._Feature):
                    f = value.compiler_flag
                    flags |= f
            except:
                pass

        return flags

    def _execute_line(self, line):
        """
        Evaluate the line and print the result.
        """
        if line.lstrip().startswith("\x1a"):
            # When the input starts with Ctrl-Z, quit the REPL.
            self.app.exit()
        elif line.lstrip().startswith("!"):
            # Run as shell command
            os.system(line[1:])
        else:
            # First try `eval` and then `exec`
            try:
                self._eval_line(line)
                return
            except SyntaxError:
                pass  # SyntaxError should not be in exception chain
            self._exec_line(line)

    def _eval_line(self, line):
        """Try executing line with `eval`
        """
        code = self._compile_with_flags(line, "eval")
        result = eval(code, self.get_globals(), self.get_locals())

        locals = self.get_locals()
        locals["_"] = locals["_%i" % self.current_statement_index] = result

        if result is None:
            return

        out_prompt = self.get_output_prompt()

        result_str = f"{info(result)}\n"  # patched here!!

        # Align every line to the first one.
        line_sep = "\n" + " " * fragment_list_width(out_prompt)
        result_str = line_sep.join(result_str.splitlines()) + "\n"

        # Write output tokens.
        if self.enable_syntax_highlighting:
            formatted_output = merge_formatted_text(
                [out_prompt, PygmentsTokens(list(_lex_python_result(result_str)))]
            )
        else:
            formatted_output = FormattedText(out_prompt + [("", result_str)])

        self.captured_output.append((result_str,), {})

        print_formatted_text(
            formatted_output,
            style=self._current_style,
            style_transformation=self.style_transformation,
            include_default_pygments_style=False,
        )

        self.app.output.flush()

    def _exec_line(self, line):
        """Try executing line with `exec`
        """
        code = self._compile_with_flags(line, "exec")
        exec(code, self.get_globals(), self.get_locals())
        self.app.output.flush()

    def _compile_with_flags(self, code, mode):
        """Compile code with the right compiler flags.
        """
        return compile(
            code, "<stdin>", mode, flags=self.get_compiler_flags(), dont_inherit=True
        )

    def _execute_task(self, *args, **kwargs):
        try:
            self._execute_line(*args, **kwargs)
        except BaseException as e:
            return e

    def _execute(self, *args, **kwargs):
        self.current_task = gevent.spawn(self._execute_task, *args, **kwargs)
        try:
            exception = self.current_task.get()
            if exception is not None:
                raise exception  # .with_traceback(exception.__traceback__)
        except gevent.Timeout:
            self._handle_exception(*args)
        except ConnectionError as e:
            raise ConnectionError(
                "Connection to Beacon server lost. "
                + "This is a serious problem! "
                + "Please quit the bliss session and try to restart it. ("
                + str(e)
                + ")"
            )
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


def initialize(session_name=None, session_env=None) -> session_mdl.Session:
    """
    Initialize a session.

    Create a session from its name, and update a provided env dictionary.

    Arguments:
        session_name: Name of the session to load
        session_env: Dictionary containing an initial env to feed. If not defined
                     an empty dict is used
    """
    if session_env is None:
        session_env = {}

    # Add config to the user namespace
    config = static.get_config()
    error_flag = False

    """ BLISS CLI welcome messages """

    t = Terminal()

    # Version
    _version = "version %s" % release.short_version

    # Hostname
    _hostname = platform.node()

    # Beacon host/port
    try:
        _host = get_default_connection()._host
        _port = str(get_default_connection()._port)
    except:
        _host = "UNKNOWN"
        _port = "UNKNOWN"

    # Conda environment
    try:
        _conda_env = "(in %s Conda environment)" % os.environ["CONDA_DEFAULT_ENV"]
    except KeyError:
        _conda_env = ""

    print_rainbow_banner()
    print("")
    print(
        "Welcome to BLISS %s running on {t.blue}%s{t.normal} %s".format(t=t)
        % (_version, _hostname, _conda_env)
    )
    print("Copyright (c) 2015-2020 Beamline Control Unit, ESRF")
    print("-")
    print(
        "Connected to Beacon server on {t.blue}%s{t.normal} (port %s)".format(t=t)
        % (_host, _port)
    )

    """ Setup(s) """
    if session_name is None:
        session = DefaultSession()
    else:
        # we will lock the session name
        # this will prevent to start serveral bliss shell
        # with the same session name
        # lock will only be released at the end of process
        default_cnx = get_default_connection()
        try:
            default_cnx.lock(session_name, timeout=1.)
        except RuntimeError:
            try:
                lock_dict = default_cnx.who_locked(session_name)
            except RuntimeError:  # Beacon is to old to answer
                raise RuntimeError(f"{session_name} is already started")
            else:
                raise RuntimeError(
                    f"{session_name} is already running on %s"
                    % lock_dict.get(session_name)
                )
        # set the client name to somethings useful
        try:
            default_cnx.set_client_name(
                f"host:{socket.gethostname()},pid:{os.getpid()} cmd: **bliss -s {session_name}**"
            )
        except RuntimeError:  # Beacon is too old
            pass
        session = config.get(session_name)
        print("%s: Loading config..." % session.name)

    from bliss.shell import standard

    cmds = {k: standard.__dict__[k] for k in standard.__all__}
    session_env.update(cmds)

    session_env["history"] = lambda: print("Please press F3-key to view history!")

    try:
        session.setup(session_env, verbose=True)
    except Exception:
        error_flag = True
        sys.excepthook(*sys.exc_info())

    if error_flag:
        print("Warning: error(s) happened during setup, setup may not be complete.")
    else:
        print("Done.")
        print("")

    session_env["SCANS"] = current_session.scans

    log = logging.getLogger("startup")
    log.info(
        f"Started BLISS version "
        f"{_version} running on "
        f"{_hostname} "
        f"{_conda_env} "
        f"connected to Beacon server {_host}"
    )

    return session


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

    # Enable loggers
    userlogger.enable()  # destination: user
    elogbook.enable()  # destination: electronic logbook

    ERROR_REPORT = install_excepthook()
    ERROR_REPORT.expert_mode = expert_error_report

    # user namespace
    user_ns = {}
    protected_user_ns = ProtectedDict(user_ns)

    # This 2 commands can be used buy user script loaded during
    # the initialization
    user_ns["protect"] = protected_user_ns.protect
    user_ns["unprotect"] = protected_user_ns.unprotect

    if session_name and not session_name.startswith(constants.DEFAULT_SESSION_NAME):
        try:
            session = initialize(session_name, session_env=user_ns)
        except RuntimeError as e:
            if use_tmux:
                print("\n", "*" * 20, "\n", e, "\n", "*" * 20)
                gevent.sleep(10)  # just to let the eyes to see the message ;)
            raise
    else:
        session = initialize(session_name=None, session_env=user_ns)

    if session.name != constants.DEFAULT_SESSION_NAME:
        protected_user_ns.protect(session.object_names)
        # protect Aliases if they exist
        if "ALIASES" in protected_user_ns:
            for alias in protected_user_ns["ALIASES"].names_iter():
                if alias in protected_user_ns:
                    protected_user_ns.protect(alias)

    # Add 2 GLOBALS to handle thelast error and the error report mode
    # (in the shell env only)
    user_ns["ERROR_REPORT"] = ERROR_REPORT
    user_ns["last_error"] = ERROR_REPORT.last_error

    # protect certain imports and Globals
    to_protect = [
        "ERROR_REPORT",
        "last_error",
        "ALIASES",
        "SCAN_DISPLAY",
        "SCAN_SAVING",
        "SCANS",
    ]
    to_protect.extend(standard.__all__)
    protected_user_ns.protect(to_protect)

    def get_globals():
        return protected_user_ns

    if session_name and not session_name.startswith(constants.DEFAULT_SESSION_NAME):
        session_id = session_name
        session_title = "Bliss shell ({0})".format(session_name)
        prompt_label = session_name.upper()
    else:
        session_id = "default"
        session_title = "Bliss shell"
        prompt_label = "BLISS"

    history_filename = ".bliss_%s_history" % (session_id)
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

        if sys.platform not in ["win32", "cygwin"] and cmd_line_i.use_tmux:
            # Catch scan events to show the progress bar
            seh = ScanPrinterWithProgressBar()
        else:
            # set old style print methods for the scans
            scan_printer = ScanPrinter()

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
                gevent.select.select([r], [], [])
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
                if inp:
                    logging.getLogger("user_input").info(inp)
                    elogbook.command(inp)
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
                cmd_line_i.captured_output.end_of_paragraph(
                    cmd_line_i.current_statement_index
                )

    finally:
        warnings.filterwarnings("default")


if __name__ == "__main__":
    embed()
