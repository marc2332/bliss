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
import time
import datetime
import numpy
import operator


from ptpython.repl import PythonRepl
from prompt_toolkit.keys import Keys

from bliss.shell.cli import style as repl_style

# from prompt_toolkit.history import History
from prompt_toolkit.utils import is_windows
from prompt_toolkit.eventloop.defaults import set_event_loop
from prompt_toolkit.eventloop import future


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


ERROR_REPORT = ErrorReport()

# patch the system exception hook
def repl_excepthook(exc_type, exc_value, tb):

    err_file = sys.stderr

    # Store latest traceback (as a string to avoid memory leaks)
    ERROR_REPORT._last_error = "".join(
        traceback.format_exception(exc_type, exc_value, tb)
    )

    # Adapt the error message depending on the ERROR_REPORT expert_mode
    if not ERROR_REPORT._expert_mode:
        print(
            f"!!! === {exc_type.__name__}: {exc_value} === !!! ( for more details type cmd 'last_error' )",
            file=err_file,
        )
    else:
        traceback.print_exception(exc_type, exc_value, tb, file=err_file)


sys.excepthook = repl_excepthook


# patch the print_exception for gevent greenlet
def print_exception(self, context, exc_type, exc_value, tb):
    repl_excepthook(exc_type, exc_value, tb)


gevent.hub.Hub.print_exception = print_exception


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

from bliss import setup_globals
from bliss.shell import initialize
from bliss.config import static
from bliss.common.utils import counter_dict
from bliss.common.axis import Axis
from bliss.common.event import dispatcher
from bliss.scanning.scan import set_scan_watch_callbacks

if sys.platform in ["win32", "cygwin"]:
    import win32api


if sys.platform not in ["win32", "cygwin"]:
    from blessings import Terminal
else:

    class Terminal:
        def __getattr__(self, prop):
            if prop.startswith("__"):
                raise AttributeError(prop)
            return ""


__all__ = ("BlissRepl", "embed", "cli", "configure_repl")  # , "configure")

REPL = None

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
        self.bliss_prompt = BlissPrompt(self)
        self.all_prompt_styles["bliss"] = self.bliss_prompt
        self.prompt_style = "bliss"
        self.show_signature = True
        self.ui_styles["bliss_ui"] = repl_style.bliss_ui_style
        self.use_ui_colorscheme("bliss_ui")
        self.code_styles["bliss_code"] = repl_style.bliss_code_style
        self.use_code_colorscheme("bliss_code")

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


def _find_obj(name):
    return operator.attrgetter(name)(setup_globals)


def _find_unit(obj):
    try:
        if isinstance(obj, str):
            # in the form obj.x.y
            obj = _find_obj(obj)
        if hasattr(obj, "unit"):
            return obj.unit
        if hasattr(obj, "config"):
            return obj.config.get("unit")
        if hasattr(obj, "controller"):
            return _find_unit(obj.controller)
    except:
        return


class ScanPrinter:
    """compose scan output"""

    HEADER = (
        "Total {npoints} points{estimation_str}\n"
        + "{not_shown_counters_str}\n"
        + "Scan {scan_nb} {start_time_str} {filename} "
        + "{session_name} user = {user_name}\n"
        + "{title}\n\n"
        + "{column_header}"
    )

    DEFAULT_WIDTH = 12

    def __init__(self):
        self.real_motors = []

    def _on_scan_new(self, scan_info):

        scan_type = scan_info.get("type")
        if scan_type is None:
            return
        config = static.get_config()
        scan_info = dict(scan_info)
        self.term = Terminal(scan_info.get("stream"))
        nb_points = scan_info.get("npoints")
        if nb_points is None:
            return

        self.col_labels = ["#"]
        self.real_motors = []
        self.counter_names = []
        self._point_nb = 0
        motor_labels = []
        counter_labels = []

        master, channels = next(iter(scan_info["acquisition_chain"].items()))

        for channel_name in channels["master"]["scalars"]:
            channel_short_name = channel_name.split(":")[-1]
            # name is in the form 'acq_master:channel_name'  <---not necessarily true anymore (e.g. roi counter have . in name / respective channel has additional : in name)
            if channel_short_name == "elapsed_time":
                # timescan
                self.col_labels.insert(1, "dt[s]")
            else:
                # we can suppose channel_name to be a motor name
                try:
                    motor = _find_obj(channel_short_name)
                except Exception:
                    continue
                else:
                    if isinstance(motor, Axis):
                        self.real_motors.append(motor)
                        if self.term.is_a_tty:
                            dispatcher.connect(
                                self._on_motor_position_changed,
                                signal="position",
                                sender=motor,
                            )
                        unit = motor.config.get("unit", default=None)
                        motor_label = motor.name
                        if unit:
                            motor_label += "[{0}]".format(unit)
                        motor_labels.append(motor_label)

        self.cntlist = [
            x.name for x in counter_dict().values()
        ]  # get all available counter names
        self.cnt_chanlist = [
            x.replace(".", ":") for x in self.cntlist
        ]  # channel names can not contain "." so we have to take care of that
        self.cntdict = dict(zip(self.cnt_chanlist, self.cntlist))

        for channel_name in channels["scalars"]:
            if channel_name.split(":")[-1] == "elapsed_time":
                self.col_labels.insert(1, "dt[s]")
                continue
            else:
                potential_cnt_channels = [
                    channel_name.split(":", i)[-1]
                    for i in range(channel_name.count(":") + 1)
                ]
                potential_cnt_channel_name = [
                    e for e in potential_cnt_channels if e in self.cntlist
                ]
                if len(potential_cnt_channel_name) > 0:
                    self.counter_names.append(potential_cnt_channel_name[0])
                    unit = _find_unit(self.cntdict[potential_cnt_channel_name[0]])
                    if unit:
                        counter_name += "[{0}]".format(unit)
                    counter_labels.append(self.cntdict[potential_cnt_channel_name[0]])

        self.col_labels.extend(sorted(motor_labels))
        self.col_labels.extend(sorted(counter_labels))

        other_channels = [
            channel_name.split(":")[-1]
            for channel_name in channels["spectra"] + channels["images"]
        ]
        if other_channels:
            not_shown_counters_str = "Activated counters not shown: %s\n" % ", ".join(
                other_channels
            )
        else:
            not_shown_counters_str = ""

        if scan_type == "ct":
            header = not_shown_counters_str
        else:
            estimation = scan_info.get("estimation")
            if estimation:
                total = datetime.timedelta(seconds=estimation["total_time"])
                motion = datetime.timedelta(seconds=estimation["total_motion_time"])
                count = datetime.timedelta(seconds=estimation["total_count_time"])
                estimation_str = ", {0} (motion: {1}, count: {2})".format(
                    total, motion, count
                )
            else:
                estimation_str = ""

            col_lens = [max(len(x), self.DEFAULT_WIDTH) for x in self.col_labels]
            h_templ = ["{{0:>{width}}}".format(width=col_len) for col_len in col_lens]
            header = "  ".join(
                [templ.format(label) for templ, label in zip(h_templ, self.col_labels)]
            )
            header = self.HEADER.format(
                column_header=header,
                estimation_str=estimation_str,
                not_shown_counters_str=not_shown_counters_str,
                **scan_info,
            )
            self.col_templ = [
                "{{0: >{width}g}}".format(width=col_len) for col_len in col_lens
            ]
        print(header)

    def _on_scan_data(self, scan_info, values):
        scan_type = scan_info.get("type")
        if scan_type is None:
            return

        master, channels = next(iter(scan_info["acquisition_chain"].items()))

        elapsed_time_col = []
        if "elapsed_time" in values:
            elapsed_time_col.append(values.pop("elapsed_time"))

        motor_labels = sorted(m.name for m in self.real_motors)
        motor_values = [values[motor_name] for motor_name in motor_labels]
        counter_values = [
            values[counter_name] for counter_name in sorted(self.counter_names)
        ]

        values = elapsed_time_col + motor_values + counter_values
        if scan_type == "ct":
            # ct is actually a timescan(npoints=1).
            norm_values = numpy.array(values) / scan_info["count_time"]
            col_len = max(map(len, self.col_labels)) + 2
            template = "{{label:>{0}}} = {{value: >12}} ({{norm: 12}}/s)".format(
                col_len
            )
            lines = "\n".join(
                [
                    template.format(label=label, value=v, norm=nv)
                    for label, v, nv in zip(self.col_labels[1:], values, norm_values)
                ]
            )
            end_time_str = datetime.datetime.now().strftime("%a %b %d %H:%M:%S %Y")
            msg = "{0}\n\n{1}".format(end_time_str, lines)
            print(msg)
        else:
            values.insert(0, self._point_nb)
            self._point_nb += 1
            line = "  ".join(
                [self.col_templ[i].format(v) for i, v in enumerate(values)]
            )
            if self.term.is_a_tty:
                monitor = scan_info.get("output_mode", "tail") == "monitor"
                print("\r" + line, end=monitor and "\r" or "\n")
            else:
                print(line)

    def _on_scan_end(self, scan_info):
        scan_type = scan_info.get("type")
        if scan_type is None or scan_type == "ct":
            return

        for motor in self.real_motors:
            dispatcher.disconnect(
                self._on_motor_position_changed, signal="position", sender=motor
            )

        end = datetime.datetime.fromtimestamp(time.time())
        start = datetime.datetime.fromtimestamp(scan_info["start_timestamp"])
        dt = end - start
        if scan_info.get("output_mode", "tail") == "monitor" and self.term.is_a_tty:
            print()
        msg = "\nTook {0}".format(dt)
        if "estimation" in scan_info:
            time_estimation = scan_info["estimation"]["total_time"]
            msg += " (estimation was for {0})".format(
                datetime.timedelta(seconds=time_estimation)
            )
        print(msg)

    def _on_motor_position_changed(self, position, signal=None, sender=None):
        labels = []
        for motor in self.real_motors:
            position = "{0:.03f}".format(motor.position)
            unit = motor.config.get("unit", default=None)
            if unit:
                position += "[{0}]".format(unit)
            labels.append("{0}: {1}".format(motor.name, position))

        print("\33[2K", end="")
        print(*labels, sep=", ", end="\r")


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


def old_history_cmd():
    print("Please press F3-key to view history!")


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

    # ADD 2 GLOBALS TO HANDLE THE LAST ERROR AND THE ERROR REPORT MODE (IN SHELL ENV ONLY)
    user_ns["ERROR_REPORT"] = ERROR_REPORT
    user_ns["last_error"] = lambda: ERROR_REPORT.last_error

    user_ns["history"] = old_history_cmd

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

    # Create REPL.
    repl = BlissRepl(
        get_globals=get_globals,
        session=session,
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

        # set print methods for the scans
        scan_printer = ScanPrinter()
        set_scan_watch_callbacks(
            scan_printer._on_scan_new,
            scan_printer._on_scan_data,
            scan_printer._on_scan_end,
        )

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
                print("\rKeyboard Interrupt\n")
                # ctrl c
                # pass
            except EOFError:
                # ctrl d
                break
            except (SystemExit):
                # kill and exit()
                print("")
                break
            except BaseException:
                sys.excepthook(*sys.exc_info())

    finally:
        warnings.filterwarnings("default")


if __name__ == "__main__":
    embed()
