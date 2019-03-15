# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Shell (:term:`CLI` and Web based)"""

import os
import sys
import time
import logging
import datetime
import platform
import functools

import numpy
import operator


if sys.platform not in ["win32", "cygwin"]:
    from blessings import Terminal
else:

    class Terminal:
        def __getattr__(self, prop):
            if prop.startswith("__"):
                raise AttributeError(prop)
            return ""


from bliss import release
from bliss import setup_globals
from bliss.config import static
from bliss.scanning import scan
from bliss.common.axis import Axis
from bliss.common.event import dispatcher
from bliss.common.session import DefaultSession
from bliss.config.conductor.client import get_default_connection
from bliss.shell.bliss_banners import print_rainbow_banner
from bliss.common.utils import counter_dict


_log = logging.getLogger("bliss.shell")


def initialize(session_name=None):
    # Initialize user namespace with bliss.common.standard
    from bliss.common import standard

    user_ns = {name: getattr(standard, name) for name in standard.__all__}

    # Add config to the user namespace
    config = static.get_config()
    user_ns["config"] = config
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
        _conda_env = (
            "(in {t.blue}%s{t.normal} Conda environment)".format(t=t)
            % os.environ["CONDA_DEFAULT_ENV"]
        )
    except KeyError:
        _conda_env = ""

    print_rainbow_banner()
    print("")
    print(
        "Welcome to BLISS %s running on {t.blue}%s{t.normal} %s".format(t=t)
        % (_version, _hostname, _conda_env)
    )
    print("Copyright (c) ESRF, 2015-2018")
    print("-")
    print(
        "Connected to Beacon server on {t.blue}%s{t.normal} (port %s)".format(t=t)
        % (_host, _port)
    )

    """ Setup(s) """
    if session_name is None:
        session = DefaultSession()
    else:
        session = config.get(session_name)
        print("%s: Executing setup..." % session.name)

    try:
        session.setup(env_dict=user_ns, verbose=True)
    except Exception:
        error_flag = True
        sys.excepthook(*sys.exc_info())

    if error_flag:
        print("Warning: error(s) happened during setup, setup may not be complete.")
    else:
        print("Done.")
        print("")

    return user_ns, session


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
                **scan_info
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


# class ScanListener(ScanPrinter):
#    """ listen to scan events and compose output """
#    def __init__(self):
#        ScanPrinter.__init__(self)
#
#        dispatcher.connect(self.__on_scan_new, "scan_new", scan)
#        dispatcher.connect(self.__on_scan_data, "scan_data", scan)
#        dispatcher.connect(self.__on_scan_end, "scan_end", scan)
