# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Listen the scan data and display in a selected ptpython buffer console """

import sys
import time
import datetime
import numpy
import operator
import termios
import shutil
import signal
import subprocess
import atexit

from bliss.data.scan import watch_session_scans

from bliss import setup_globals
from bliss.config import static
from bliss.common.utils import counter_dict
from bliss.common.axis import Axis
from bliss.common.event import dispatcher
from bliss.config.settings import HashSetting
from bliss.scanning.scan import set_scan_watch_callbacks
from bliss.scanning.scan import ScanDisplay


if sys.platform not in ["win32", "cygwin"]:
    from blessings import Terminal
else:

    class Terminal:
        def __getattr__(self, prop):
            if prop.startswith("__"):
                raise AttributeError(prop)
            return ""


def catch_sigint(*args):
    pass


def print_full_line(msg, deco="=", head="\n", tail="\n"):
    width = shutil.get_terminal_size().columns
    fac = (width - len(msg)) // 2
    deco = deco * fac

    print("".join([head, deco, msg, deco, tail]))


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
        set_scan_watch_callbacks(self.on_scan_new, self.on_scan_data, self.on_scan_end)

    def on_scan_new(self, scan_info):
        scan_type = scan_info.get("type")
        if scan_type is None:
            return
        config = static.get_config()
        scan_info = dict(scan_info)
        self.term = Terminal(scan_info.get("stream"))
        nb_points = scan_info.get("npoints")
        if nb_points is None:
            return

        # print("acquisition_chain",scan_info["acquisition_chain"])

        self.col_labels = ["#"]
        self.real_motors = []
        self.counter_names = []
        self.counter_fullnames = []
        self._point_nb = 0
        motor_labels = []
        self.motor_fullnames = []

        master, channels = next(iter(scan_info["acquisition_chain"].items()))

        for channel_fullname in channels["master"]["scalars"]:
            channel_short_name = channels["master"]["display_names"][channel_fullname]
            channel_unit = channels["master"]["scalars_units"][channel_fullname]

            # name is in the form 'acq_master:channel_name'  <---not necessarily true anymore (e.g. roi counter have . in name / respective channel has additional : in name)
            if channel_short_name == "elapsed_time":
                # timescan
                self.col_labels.insert(1, f"dt[{channel_unit}]")
            else:
                # we can suppose channel_fullname to be a motor name
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
                        motor_label = motor.alias_or_name
                        if unit:
                            motor_label += "[{0}]".format(unit)
                        motor_labels.append(motor_label)
                        self.motor_fullnames.append("axis:" + motor.name)

        for channel_fullname in channels["scalars"]:
            channel_short_name = channels["display_names"][channel_fullname]
            channel_unit = channels["scalars_units"][channel_fullname]

            if channel_short_name == "elapsed_time":
                self.col_labels.insert(1, "dt[s]")
                continue
            self.counter_names.append(
                channel_short_name + (f"[{channel_unit}]" if channel_unit else "")
            )
            self.counter_fullnames.append(channel_fullname)

        self.col_labels.extend(motor_labels)
        self.col_labels.extend(self.counter_names)

        other_channels = [
            channels["display_names"][channel_fullname]
            for channel_fullname in channels["spectra"] + channels["images"]
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

    def on_scan_data(self, scan_info, values):
        scan_type = scan_info.get("type")
        if scan_type is None:
            return

        master, channels = next(iter(scan_info["acquisition_chain"].items()))

        elapsed_time_col = []
        if "timer:elapsed_time" in values:
            elapsed_time_col.append(values.pop("timer:elapsed_time"))

        motor_values = [values[motor_name] for motor_name in self.motor_fullnames]
        counter_values = [
            values[counter_fullname] for counter_fullname in self.counter_fullnames
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

    def on_scan_end(self, scan_info):
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


class ScanDataListener:

    HEADER = (
        "Total {npoints} points{estimation_str}\n"
        + "{not_shown_counters_str}\n"
        + "Scan {scan_nb} {start_time_str} {filename} "
        + "{session_name} user = {user_name}\n"
        + "{title}\n\n"
        + "{column_header}"
    )

    DEFAULT_WIDTH = 12

    def __init__(self, session_name="", exit_read_fd=None):

        self.session_name = session_name
        self.scan_name = None
        self.scan_is_running = None
        self.counter_selection = []
        self.exit_read_fd = exit_read_fd
        self.scan_display = ScanDisplay(self.session_name)

    def update_counter_selection(self):
        self.counter_selection = self.scan_display.counters

    def get_selected_counters(self, counter_names):
        if not self.counter_selection:
            return counter_names

        selection = []
        for cname in counter_names:
            if cname in self.counter_selection or cname == "timer:elapsed_time":
                selection.append(cname)

        return selection

    def on_scan_new(self, scan_info):

        # Skip other session
        if scan_info.get("session_name") != self.session_name:
            # print(f"{scan_info.get('session_name')} != {self.session_name}")
            return

        scan_type = scan_info.get("type")
        npoints = scan_info.get("npoints")

        # Skip bad scans
        if None in [scan_type, npoints]:
            # print("scan_type, npoints = ",scan_type, npoints)
            return

        # Skip secondary scans and warn user
        if self.scan_is_running:
            print(
                f"Warning: a new scan '{scan_info.get('node_name')}' has been started while scan '{self.scan_name}' is running.\nNew scan outputs will be ignored."
            )
            return
        else:
            self.scan_is_running = True
            self.scan_name = scan_info.get("node_name")
            self.update_counter_selection()

            # session_name = scan_info.get('session_name')             # ex: 'test_session'
            # user_name = scan_info.get('user_name')                   # ex: 'pguillou'
            # filename = scan_info.get('filename')                     # ex: '/mnt/c/tmp/test_session/data.h5'
            # node_name = scan_info.get('node_name')                   # ex: 'test_session:mnt:c:tmp:183_ascan'

            # start_time = scan_info.get('start_time')                 # ex: datetime.datetime(2019, 3, 18, 15, 28, 17, 83204)
            # start_time_str = scan_info.get('start_time_str')         # ex: 'Mon Mar 18 15:28:17 2019'
            # start_timestamp = scan_info.get('start_timestamp')       # ex: 1552919297.0832036

            # save = scan_info.get('save')                             # ex: True
            # sleep_time = scan_info.get('sleep_time')                 # ex: None

            # title = scan_info.get('title')                           # ex: 'ascan roby 0 10 10 0.01'
            # scan_type = scan_info.get('type')                        # ex:    ^
            # start = scan_info.get('start')                           # ex:             ^              = [0]
            # stop = scan_info.get('stop')                             # ex:                ^           = [10]
            # npoints = scan_info.get('npoints')                       # ex:                   ^        = 10
            # count_time = scan_info.get('count_time')                 # ex:                       ^    = 0.01

            # total_acq_time = scan_info.get('total_acq_time')         # ex: 0.1  ( = npoints * count_time )
            # scan_nb = scan_info.get('scan_nb')                       # ex: 183

            # positioners_dial = scan_info.get('positioners_dial')     # ex: {'bad': 0.0, 'calc_mot1': 20.0, 'roby': 20.0, ... }
            # positioners = scan_info.get('positioners')               # ex: {'bad': 0.0, 'calc_mot1': 20.0, 'roby': 10.0, ...}

            # estimation = scan_info.get('estimation')                 # ex: {'total_motion_time': 2.298404048112306, 'total_count_time': 0.1, 'total_time': 2.398404048112306}
            # acquisition_chain = scan_info.get('acquisition_chain')   # ex: {'axis': {'master': {'scalars': ['axis:roby'], 'spectra': [], 'images': []}, 'scalars': ['timer:elapsed_time', 'diode:diode'], 'spectra': [], 'images': []}}

            self.scan_steps_index = 1
            self.col_labels = ["#"]
            self._point_nb = 0

            master, channels = next(iter(scan_info["acquisition_chain"].items()))

            selected_counters = self.get_selected_counters(channels["scalars"])

            self.channel_names = channels["master"]["scalars"] + selected_counters

            # get the number of masters and counters unfiltered
            self.channels_number = len(channels["master"]["scalars"]) + len(
                channels["scalars"]
            )

            # BUILD THE LABEL COLUMN
            channel_labels = []
            # GET THE LIST OF MASTER CHANNELS SHORT NAMES
            for channel_name in channels["master"]["scalars"]:
                channel_short_name = channels["master"]["display_names"][channel_name]
                channel_unit = channels["master"]["scalars_units"][channel_name]

                if channel_short_name == "elapsed_time":
                    self.col_labels.insert(1, f"dt[{channel_unit}]")
                else:
                    channel_labels.append(
                        channel_short_name
                        + (f"[{channel_unit}]" if channel_unit else "")
                    )

            # GET THE LIST OF SCALAR CHANNELS SHORT NAMES
            for channel_name in selected_counters:
                channel_short_name = channels["display_names"][channel_name]
                channel_unit = channels["scalars_units"][channel_name]

                if channel_short_name == "elapsed_time":
                    self.col_labels.insert(1, f"dt[{channel_unit}]")
                else:
                    channel_labels.append(
                        channel_short_name
                        + (f"[{channel_unit}]" if channel_unit else "")
                    )

            self.col_labels.extend(channel_labels)

            # GET THE LIST OF OTHER CHANNELS ('spectra' and 'images')
            other_channels = []
            for channel_name in channels["spectra"] + channels["images"]:
                # idx = channel_name.rfind(":") + 1
                # channel_short_name = channel_name[idx:]
                # other_channels.append(channel_short_name)
                other_channels.append(channel_name)

            if other_channels:
                not_shown_counters_str = (
                    "Activated counters not shown: %s\n" % ", ".join(other_channels)
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
                h_templ = [
                    "{{0:>{width}}}".format(width=col_len) for col_len in col_lens
                ]
                header = "  ".join(
                    [
                        templ.format(label)
                        for templ, label in zip(h_templ, self.col_labels)
                    ]
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

    def on_scan_new_child(self, scan_info, data_channel):
        pass

    def on_scan_data(self, data_dim, master_name, channel_info):

        scan_info = channel_info["scan_info"]
        scan_type = scan_info.get("type")

        # Skip other session
        if scan_info.get("session_name") != self.session_name:
            return

        # Skip other scan
        if scan_info.get("node_name") != self.scan_name:
            return

        # Skip if missing channels
        if len(channel_info["data"]) != self.channels_number:
            return

        # Skip if partial data
        for channel_name in channel_info["data"]:
            if len(channel_info["data"][channel_name]) < self.scan_steps_index:
                return

        # Get data for the current scan step
        values_dict = {}
        for channel_name in channel_info["data"]:
            if channel_name in self.channel_names:
                values_dict[channel_name] = channel_info["data"][channel_name][
                    self.scan_steps_index - 1
                ]

        # Extract time data
        elapsed_time_col = []
        if "timer:elapsed_time" in values_dict:
            elapsed_time_col.append(values_dict.pop("timer:elapsed_time"))

        # Build data line
        values = elapsed_time_col + [
            values_dict[channel_name] for channel_name in values_dict
        ]

        # Format output line
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

            print(line)

        self.scan_steps_index += 1

    def on_scan_end(self, scan_info):

        if scan_info.get("session_name") != self.session_name:
            return

        if scan_info.get("node_name") != self.scan_name:
            return

        end = datetime.datetime.fromtimestamp(time.time())
        start = datetime.datetime.fromtimestamp(scan_info["start_timestamp"])
        dt = end - start

        msg = "\nTook {0}".format(dt)
        if "estimation" in scan_info:
            time_estimation = scan_info["estimation"]["total_time"]
            msg += " (estimation was for {0})".format(
                datetime.timedelta(seconds=time_estimation)
            )
        print(msg)

        print_full_line(
            " >>> PRESS F5 TO COME BACK TO THE SHELL PROMPT <<< ",
            deco="=",
            head="\n",
            tail="\n",
        )

        self.scan_is_running = False

    def reset_terminal(self):
        # Prevent user inputs
        fd = sys.stdin.fileno()
        new = termios.tcgetattr(fd)
        new[3] |= termios.ECHO
        termios.tcsetattr(fd, termios.TCSANOW, new)

    def start(self):

        # Prevent user to close the listener with Ctrl-C
        signal.signal(signal.SIGINT, catch_sigint)

        # Prevent user inputs if using a terminal
        fd = sys.stdin.fileno()
        try:
            new = termios.tcgetattr(fd)
            new[3] &= ~termios.ECHO
            termios.tcsetattr(fd, termios.TCSANOW, new)
        except termios.error:
            pass  # not in terminal (example in tests)
        else:
            # revert 'Prevent user inputs if using a terminal'
            atexit.register(self.reset_terminal)

        print_full_line(
            f" Bliss session '{self.session_name}': watching scans ",
            deco="=",
            head="",
            tail="\n",
        )

        # Start the watch, winter is coming...
        watch_session_scans(
            self.session_name,
            self.on_scan_new,
            self.on_scan_new_child,
            self.on_scan_data,
            self.on_scan_end,
            exit_read_fd=self.exit_read_fd,
        )


class ScanEventHandler:
    def __init__(self, repl):

        self.repl = repl

    def on_scan_new(self, scan_info):
        subprocess.run(["tmux", "next-window", "-t", self.repl.session_name])

    def on_scan_data(self, scan_info, values):
        pass

    def on_scan_end(self, scan_info):
        pass
