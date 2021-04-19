# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Bliss REPL (Read Eval Print Loop)"""
import asyncio
import queue
import threading
import contextlib
import os
import sys
import types
import socket
import warnings
import functools
import traceback
import gevent
import logging
import platform

from collections import deque
from datetime import datetime

from ptpython.repl import PythonRepl

from prompt_toolkit.patch_stdout import patch_stdout as patch_stdout_context
import ptpython.layout
from prompt_toolkit.output import DummyOutput

# imports needed to have control over _execute of ptpython
from prompt_toolkit.keys import Keys
from prompt_toolkit.utils import is_windows
from prompt_toolkit.filters import has_focus
from prompt_toolkit.enums import DEFAULT_BUFFER

from bliss.shell.data.display import ScanPrinter, ScanPrinterWithProgressBar
from bliss.shell.cli.prompt import BlissPrompt
from bliss.shell.cli.typing_helper import TypingHelper
from bliss.shell.cli.ptpython_statusbar_patch import NEWstatus_bar, TMUXstatus_bar

from bliss import set_bliss_shell_mode
from bliss.common.utils import ShellStr, Singleton
from bliss.common import constants
from bliss import release, current_session
from bliss.config import static
from bliss.shell.standard import info
from bliss.common.logtools import userlogger, elogbook
from bliss.shell.cli.protected_dict import ProtectedDict
from bliss.shell import standard

from bliss.common import session as session_mdl
from bliss.common.session import DefaultSession
from bliss.config.conductor.client import get_default_connection
from bliss.shell.bliss_banners import print_rainbow_banner

logger = logging.getLogger(__name__)

if is_windows():
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
            return "None"

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


def install_excepthook():
    """Patch the system exception hook,
    and the print exception for gevent greenlet
    """
    ERROR_REPORT = ErrorReport()

    exc_logger = logging.getLogger("exceptions")

    def repl_excepthook(exc_type, exc_value, tb, _with_elogbook=True):
        if exc_value is None:
            # filter exceptions from aiogevent(?) with no traceback, no value
            return
        err_file = sys.stderr

        # Store latest traceback (as a string to avoid memory leaks)
        # next lines are inspired from "_handle_exception()" (ptpython/repl.py)
        # skip bottom calls from ptpython
        tblist = list(traceback.extract_tb(tb))
        to_remove = 0
        for line_nr, tb_tuple in enumerate(tblist):
            if tb_tuple.filename == "<stdin>":
                to_remove = line_nr
        for i in range(to_remove):
            tb = tb.tb_next

        exc_text = "".join(traceback.format_exception(exc_type, exc_value, tb))
        ERROR_REPORT._last_error.append(
            datetime.now().strftime("%d/%m/%Y %H:%M:%S ") + exc_text
        )

        exc_logger.error(exc_text)

        # Adapt the error message depending on the ERROR_REPORT expert_mode
        if ERROR_REPORT._expert_mode:
            print(ERROR_REPORT._last_error, file=err_file)
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
        if gevent.getcurrent() is self:
            # repl_excepthook tries to yield to the gevent loop
            gevent.spawn(repl_excepthook, exc_type, exc_value, tb)
        else:
            repl_excepthook(exc_type, exc_value, tb)

    sys.excepthook = repl_excepthook
    gevent.hub.Hub.print_exception = types.MethodType(print_exception, gevent.get_hub())
    return ERROR_REPORT


def reset_excepthook():
    sys.excepthook = ErrorReport._orig_sys_excepthook
    gevent.hub.Hub.print_exception = ErrorReport._orig_gevent_print_exception


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


class Info:
    def __init__(self, obj_with_info):
        self.info_repr = info(obj_with_info)

    def __repr__(self):
        return self.info_repr


class WrappedStdout:
    def __init__(self, ptpython_output, current_output):
        self._ptpython_output = ptpython_output
        self._current_output = current_output
        self._orig_stdout = sys.stdout

    # context manager
    def __enter__(self, *args, **kwargs):
        self._orig_stdout = sys.stdout
        sys.stdout = self
        return self

    def __exit__(self, *args, **kwargs):
        self._ptpython_output._output.append("".join(self._current_output))
        self._current_output.clear()
        sys.stdout = self._orig_stdout

    # delegated members
    @property
    def encoding(self):
        return self._orig_stdout.encoding

    @property
    def errors(self):
        return self._orig_stdout.errors

    def fileno(self) -> int:
        # This is important for code that expects sys.stdout.fileno() to work.
        return self._orig_stdout.fileno()

    def isatty(self) -> bool:
        return self._orig_stdout.isatty()

    def flush(self):
        self._orig_stdout.flush()

    # extended members
    def write(self, data):
        # wait for stdout to be ready to receive output
        if True:  # if gevent.select.select([],[self.fileno()], []):
            self._current_output.append(data)
            self._orig_stdout.write(data)


# in the next class, inheritance from DummyOutput is just needed
# to make ptpython happy (as there are some asserts checking instance type)
class PromptToolkitOutputWrapper(DummyOutput):
    SIZE = 20

    def __init__(self, output):
        self.__wrapped_output = output
        self._current_output = []
        self._output = deque(maxlen=20)

    def __getattr__(self, attr):
        if attr.startswith("__"):
            raise AttributeError(attr)
        return getattr(self.__wrapped_output, attr)

    @property
    def capture_stdout(self):
        return WrappedStdout(self, self._current_output)

    def __getitem__(self, item_no):
        if item_no >= 0:
            # item_no starts at 1 to match "Out" number in ptpython
            item_no -= 1
        # if item_no is specified negative => no decrement of number of course
        return self._output[item_no]

    def write(self, data):
        self._current_output.append(data)
        self.__wrapped_output.write(data)

    def fileno(self):
        return self.__wrapped_output.fileno()


class BlissRepl(PythonRepl, metaclass=Singleton):
    def __init__(self, *args, **kwargs):
        self._show_result_aw = gevent.get_hub().loop.async_()
        self._show_result_aw.start(self._on_result)
        self._result_q = queue.Queue()

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
        if self.use_tmux and not is_windows():
            ptpython.layout.status_bar = TMUXstatus_bar
        else:
            ptpython.layout.status_bar = NEWstatus_bar

        super().__init__(*args, **kwargs)

        self.app.output = PromptToolkitOutputWrapper(self.app.output)

        if title:
            self.terminal_title = title

        # self.show_bliss_bar = True
        # self.bliss_bar = bliss_bar
        # self.bliss_bar_format = "normal"
        self.bliss_session = session
        self.bliss_prompt = BlissPrompt(self, prompt_label)
        self.all_prompt_styles["bliss"] = self.bliss_prompt
        self.prompt_style = "bliss"

        self.show_signature = True
        # self.ui_styles["bliss_ui"] = repl_style.bliss_ui_style
        # self.use_ui_colorscheme("bliss_ui")

        # Monochrome mode
        self.color_depth = "DEPTH_1_BIT"

        # Records bliss color style and make it active in bliss shell.
        # self.code_styles["bliss_code"] = repl_style.bliss_code_style
        # self.use_code_colorscheme("bliss_code")

        # PTPYTHON SHELL PREFERENCES
        self.enable_history_search = True
        self.show_status_bar = True
        self.confirm_exit = True
        self.enable_mouse_support = False

        if self.use_tmux:
            self.exit_message = (
                "Do you really want to close session? (CTRL-B D to detach)"
            )

        self.typing_helper = TypingHelper(self)

    def _on_result(self):
        # spawn, because we cannot block in async watcher callback
        gevent.spawn(self._do_handle_result, self._last_result)

    def _do_handle_result(self, result):
        if hasattr(result, "__info__"):
            result = Info(result)
        logging.getLogger("user_input").info(result)
        elogbook.command(result)
        self._result_q.put(result)

    ##
    # NB: next methods are overloaded
    ##
    def show_result(self, result):
        # warning: this may be called from a different thread each time
        # (when "run_async" is used)
        if threading.current_thread() is threading.main_thread():
            self._do_handle_result(result)
        else:
            self._last_result = result
            self._show_result_aw.send()
        return super().show_result(self._result_q.get())

    def _handle_keyboard_interrupt(self, e: KeyboardInterrupt) -> None:
        sys.excepthook(*sys.exc_info())

    def _handle_exception(self, e):
        sys.excepthook(*sys.exc_info())


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

    if session.setup(session_env, verbose=True):
        print("Done.")
    else:
        print("Warning: error(s) happened during setup, setup may not be complete.")
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
    use_tmux=False,
    expert_error_report=False,
    **kwargs,
):
    """
    Create a command line interface
    
    Args:
        session_name : session to initialize (default: None)
        vi_mode (bool): Use Vi instead of Emacs key bindings.
    """
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
    if is_windows():
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

    # Custom keybindings
    configure_repl(repl)

    return repl


@contextlib.contextmanager
def filter_warnings():
    # Hide the warnings from the users
    warnings.filterwarnings("ignore")
    yield
    warnings.filterwarnings("default")


def embed(*args, **kwargs):
    """
    Call this to embed bliss shell at the current point in your program::

        from bliss.shell.cli.repl import cli
        from signal import SIGINT, SIGTERM

        embed(locals=locals())

    Args:
        session_name : session to initialize (default: None)
        vi_mode (bool): Use Vi instead of Emacs key bindings.
    """
    use_tmux = kwargs.get("use_tmux", False)

    if not is_windows() and use_tmux:
        # Catch scans events to show the progress bar
        scan_printer = ScanPrinterWithProgressBar()
    else:
        # set old style print methods for the scans
        scan_printer = ScanPrinter()

    with filter_warnings():
        cmd_line_i = cli(*args, **kwargs)

        with patch_stdout_context(raw=True):
            asyncio.run(cmd_line_i.run_async())
