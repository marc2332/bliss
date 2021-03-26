# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Listen the scan data and display in a selected ptpython buffer console """

import sys
import time
from tqdm import tqdm
import datetime
import numpy
import shutil
import signal
import atexit
import typing
import gevent
import numbers

from bliss.data import scan as scan_mdl
from bliss.common.utils import nonblocking_print
from bliss.common.event import dispatcher
from bliss.common.logtools import user_print
from bliss.scanning.scan import set_scan_watch_callbacks, ScanState
from bliss.scanning.scan_display import ScanDisplay
from bliss import global_map, is_bliss_shell
from bliss.shell.formatters.table import IncrementalTable


if sys.platform not in ["win32", "cygwin"]:
    import termios
    from blessings import Terminal
else:

    class Terminal:
        def __getattr__(self, prop):
            if prop.startswith("__"):
                raise AttributeError(prop)
            return ""


def catch_sigint(*args):
    pass


def get_decorated_line(msg, width=None, deco="=", head="\n", tail="\n", rdeco=None):
    if not width:
        width = shutil.get_terminal_size().columns

    ldeco = deco
    if rdeco is None:
        rdeco = deco

    diff = width - len(msg)
    if diff > 1:
        ldeco = ldeco * (diff // 2)
        rdeco = rdeco * (diff - diff // 2)

    return "".join([head, ldeco, msg, rdeco, tail])


def _find_obj(name: str):
    """Return the object (Axis or Counter) corresponding to the given name
    """
    for axis in global_map.get_axes_iter():
        if axis.name == name:
            return axis
    for cnt in global_map.get_counters_iter():
        if cnt.name == name:
            return cnt


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
    except Exception:
        return


class ChannelMetadata(typing.NamedTuple):
    """Store metadata about a channel"""

    display_name: str
    unit: typing.Optional[str]


class _ScanPrinterBase:
    HEADER = (
        "\033[92m** Scan {scan_nb}: {title} **\033[0m\n\n"
        + "   date      : {start_time_str}\n"
        + "   file      : {filename}\n"
        + "   user      : {user_name}\n"
        + "   session   : {session_name}\n"
        + "   masters   : [ {master_names} ]\n"
        + "   skipped   : [ {not_shown_counters_str} ]\n"
    )

    EXTRA_HEADER = (
        "   unselected: [ {not_selected} ]\n"
        + "                 (use plotselect to customize this list)\n"
    )

    EXTRA_HEADER_2 = "                 (use plotselect to filter this list)\n"

    DEFAULT_WIDTH = 12

    COL_SEP = "|"
    RAW_SEP = "-"
    NO_NAME = "-"

    def __init__(self):

        self.scan_name = None
        self.scan_is_running = False

        self.channels_number = None
        self.displayable_channel_names = None
        self.master_channel_names = []
        self.sorted_channel_names = []
        self._channels_meta = {}
        self.other_channels = None
        self._possible_motors = None

        self.scan_steps_index = 0
        self._warning_messages = None

    def collect_channels_info(self, scan_info):

        """ 
                #------------- scan_info example -------------------------------------------------------

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

                # acquisition_chain = scan_info.get('acquisition_chain')  
                # ex: {'axis':
                #       { 
                #         'master' : {'scalars': ['axis:roby'], 'spectra': [], 'images': [] }, 
                #         'scalars': ['timer:elapsed_time', 'diode:diode'], 
                #         'spectra': [], 
                #         'images' : [] 
                #       }
                #     }
        """

        """
                # master, channels = next(iter(scan_info["acquisition_chain"].items()))
                # master = axis
                # channels = {'master': {'scalars': ['axis:roby'], 
                #                        'spectra': [], 
                #                        'images': [], 
                #                       }, 
                #             'scalars': ['timer:elapsed_time', 
                #                         'timer:epoch', 
                #                         'lima_simulator2:bpm:x', 
                #                         'simulation_diode_sampling_controller:diode'],
                #             'spectra': [], 
                #             'images': [], 
        """

        # ONLY MANAGE THE FIRST ACQUISITION BRANCH (multi-top-masters scan are ignored)
        top_master, channels = next(iter(scan_info["acquisition_chain"].items()))

        # get the total number of channels
        self.channels_number = len(channels["master"]["scalars"]) + len(
            channels["scalars"]
        )

        # get master scalar channels (remove epoch)
        master_scalar_channels = [
            cname for cname in channels["master"]["scalars"] if cname != "timer:epoch"
        ]

        # get scalar channels (remove epoch)
        scalar_channels = [
            cname for cname in channels["scalars"] if cname != "timer:epoch"
        ]

        # get all channels fullname, display names and units
        channel_names = master_scalar_channels + scalar_channels

        channels_meta = {}
        for channel_name, meta in scan_info["channels"].items():
            display_name = meta.get("display_name")
            if display_name is None:
                display_name = channel_name.split(":")[-1]
            unit = meta.get("unit")
            metadata = ChannelMetadata(display_name, unit)
            channels_meta[channel_name] = metadata
        self._channels_meta = channels_meta

        master_channel_names = master_scalar_channels.copy()

        # get none scalar channels (spectra and images)
        self.other_channels = (
            channels["master"]["spectra"] + channels["master"]["images"]
        )
        self.other_channels += channels["spectra"] + channels["images"]

        displayable_channels = []
        # First the timer channel if any
        timer_cname = "timer:elapsed_time"
        if timer_cname in channel_names:
            displayable_channels.append(timer_cname)

        # Then the masters scalars channels
        self._possible_motors = []
        for cname in master_scalar_channels:
            if cname != timer_cname:
                displayable_channels.append(cname)
                channel_meta = self._channels_meta[cname]
                self._possible_motors.append(channel_meta.display_name)

        # Finally the other scalars channels
        for cname in scalar_channels:
            if cname != timer_cname:
                displayable_channels.append(cname)

        #  Store the channels contained in the scan_info
        self.master_channel_names = master_channel_names
        self.displayable_channel_names = displayable_channels
        self.sorted_channel_names = displayable_channels.copy()

    def build_columns_labels(self, channel_with_unit=True, with_index=True):
        # Build the columns labels (multi-line with counter and controller names)
        channel_labels = []
        counter_labels = []
        controller_labels = []

        for cname in self.sorted_channel_names:
            channel_meta = self._channels_meta[cname]

            # build the channel label
            if cname == "timer:elapsed_time":
                disp_name = "dt"
            else:
                disp_name = channel_meta.display_name

            # check if the unit must be added to channel label
            if channel_with_unit:
                unit = channel_meta.unit
                if unit:
                    disp_name += f"[{unit}]"

            channel_labels.append(disp_name)

            # try to get controller and counter names
            try:
                ctrl, cnt = cname.split(":")[0:2]
                if cnt == channel_meta.display_name:
                    cnt = self.NO_NAME
                counter_labels.append(cnt)
                controller_labels.append(ctrl)
            except Exception:
                counter_labels.append("")
                controller_labels.append("")

        if with_index:
            controller_labels.insert(0, "")
            counter_labels.insert(0, "")  # 'index'
            channel_labels.insert(0, "#")

        return [controller_labels, channel_labels]  # counter_labels useless in table

    def build_header(self, scan_info):
        """Build the header to be displayed
        """
        # A message about not shown channels
        not_shown_counters_str = ""
        if self.other_channels:
            not_shown_counters_str = ", ".join(self.other_channels)

        master_names = ", ".join(self.master_channel_names)

        header = self.HEADER.format(
            not_shown_counters_str=not_shown_counters_str,
            master_names=master_names,
            **scan_info,
        )

        if scan_info.get("type") != "ct":
            header += self._build_extra_header()

        return header

    def _build_extra_header(self):
        not_selected = [
            c
            for c in self.displayable_channel_names
            if c not in self.sorted_channel_names
        ]
        if len(not_selected) == 0:
            return self.EXTRA_HEADER_2

        not_selected = [f"'\033[91m{c}\033[0m'" for c in not_selected]
        not_selected = ", ".join(not_selected)
        return self.EXTRA_HEADER.format(not_selected=not_selected)

    def print_scan_header(self, scan_info):
        """Print the header of a new scan"""
        header = self.build_header(scan_info)
        print(header)

    def print_data_header(self, scan_info):  # , first=False):
        """Print the header of the data table.
        """
        if scan_info.get("type") != "ct":
            col_max_width = 40
            labels = self.build_columns_labels()
            self._tab = IncrementalTable(
                labels,
                minwidth=self.DEFAULT_WIDTH,
                maxwidth=col_max_width,
                col_sep=self.COL_SEP,
                lmargin="   ",
            )

            self._tab.set_column_params(0, {"flag": ""})

            # auto adjust columns widths in order to fit the screen
            screen_width = int(shutil.get_terminal_size().columns)
            while (self._tab.full_width + len(self._tab.lmargin) + 1) > screen_width:
                col_max_width -= 1
                self._tab.resize(maxwidth=col_max_width)
                if col_max_width <= self.DEFAULT_WIDTH:
                    break

            self._tab.add_separator(self.RAW_SEP)
            print(str(self._tab))
        else:
            self._tab = ""

    def build_data_output(self, scan_info, data):
        """ data is a dict, one scalar per channel (last point) """

        # Get data for the current scan step
        values = [data[cname] for cname in self.sorted_channel_names]

        # Format output line
        if scan_info.get("type") == "ct":
            # ct is actually a timescan(npoints=1).
            norm_values = numpy.array(values) / scan_info["count_time"]
            return self._build_ct_output(values, norm_values)
        else:
            values.insert(0, self.scan_steps_index)
            line = self._tab.add_line(values)
            return line

    def _format_number(self, value, length_before, length_after) -> str:
        """Format a number in order to center the dot.

        Arguments:
            length_before: Expected size before (the content is padded
                           right if small)
            length_after: Expected size after (the content is padded left
                          if smaller)
        Returns:
            A string with always a size of (length_before + length_after + 1)
        """
        if isinstance(value, numbers.Integral):
            v = str(value)
        else:
            v = f"{value:#g}"
        prefix_size = len(v.split(".")[0])
        suffix_size = len(v) - prefix_size - 1
        if length_before > prefix_size:
            prefix = " " * (length_before - prefix_size)
        else:
            prefix = ""
        if length_after > suffix_size:
            suffix = " " * (length_after - suffix_size)
        else:
            suffix = ""
        return f"{prefix}{v}{suffix}"

    def _build_ct_output(self, values, norm_values):

        info_dict = {}
        width = 20
        for i, cname in enumerate(self.sorted_channel_names):
            channel_meta = self._channels_meta[cname]

            # display name
            if cname == "timer:elapsed_time":
                # disp_name = "dt"
                continue
            else:
                disp_name = channel_meta.display_name

            # unit
            unit = channel_meta.unit
            if unit:
                disp_name += f"[{unit}]"

            nw = len(disp_name)
            if nw > width:
                width = nw

            # sort by controller name
            ctrl, _ = cname.split(":")[0:2]
            if info_dict.get(ctrl):
                info_dict[ctrl].append([disp_name, values[i], norm_values[i]])
            else:
                info_dict[ctrl] = [[disp_name, values[i], norm_values[i]]]

        width = min(50, width)

        lines = []
        for ctrl, values in info_dict.items():
            for dname, v, nv in values:
                v = self._format_number(v, 8, 9)
                nv = self._format_number(nv, 8, 11)
                lines.append(f"  {dname:>{width}}  = {v} ({nv} /s)  {ctrl}")

        return "\n".join(lines)

    def is_new_scan_valid(self, scan_info):

        # Skip multi-top-masters scans
        if len(scan_info["acquisition_chain"].keys()) != 1:
            return False

        # Skip scans without a type or without a number of points
        scan_type = scan_info.get("type")
        npoints = scan_info.get("npoints")
        if None in [scan_type, npoints]:
            return False

        # Skip secondary scans and warn user
        if self.scan_is_running:
            self._warning_messages.append(
                f"\nWarning: a new scan '{scan_info.get('node_name')}' has been started while scan '{self.scan_name}' is running.\nNew scan outputs will be ignored."
            )
            return False

        return True

    def is_new_data_valid(self, scan_info, data):
        # Skip other scan
        if scan_info.get("node_name") != self.scan_name:
            return False

        # Skip if missing channels
        if len(data) != self.channels_number:
            return False

        return True

    def is_end_scan_valid(self, scan_info):
        # Skip other scan
        if scan_info.get("node_name") != self.scan_name:
            return False
        if scan_info["state"] not in (ScanState.STOPPING, ScanState.DONE):
            # why is there STOPPING here?
            return False
        return True

    def on_scan_new(self, scan_info):
        if self.is_new_scan_valid(scan_info):
            self.scan_is_running = True
            self.scan_name = scan_info.get("node_name")
            self.scan_steps_index = 0
            self._warning_messages = []

            self.collect_channels_info(scan_info)
            self.print_scan_header(scan_info)
            self.print_data_header(scan_info)

    def on_scan_data(self, scan_info, data):
        raise NotImplementedError

    def on_scan_end(self, scan_info):
        if self.is_end_scan_valid(scan_info):
            self.scan_is_running = False
            end = datetime.datetime.fromtimestamp(time.time())
            start = datetime.datetime.fromtimestamp(scan_info["start_timestamp"])
            dt = end - start

            for msg in self._warning_messages:
                print(msg)

            print(f"\n   Took {dt}[s] \n")


class ScanMotorListener:
    def __init__(self):
        self.real_motors = []

    def connect_real_motors(self, scan):
        self.real_motors = scan._get_data_axes()

        for motor in self.real_motors:
            dispatcher.connect(
                self._on_motor_position_changed, signal="position", sender=motor
            )

    def _on_motor_position_changed(self, position, signal=None, sender=None):
        raise NotImplementedError

    def disconnect_real_motors(self):
        for motor in self.real_motors:
            dispatcher.connect(
                self._on_motor_position_changed, signal="position", sender=motor
            )


class ScanPrinter(_ScanPrinterBase, ScanMotorListener):
    """compose scan output"""

    HEADER = ""

    def __init__(self):
        super().__init__()

        self._labels = []
        self._ct_data = None

        set_scan_watch_callbacks(self.on_scan_new, self.on_scan_data, self.on_scan_end)

    @property
    def labels(self):
        return self._labels

    def print_scan_info(self, scan, scan_info):
        """Print date + scan __repr__ at the beginning of the scan output"""
        user_print(f"   {scan_info['start_time_str']}: {scan}")

    def print_scan_line(self, *args, **kwargs):
        """Forward the call to 'print', but allow subclasses to modify behaviour"""
        # raw print is used because the scan happens in 'disable_user_output' context
        print(*args, **kwargs)

    def on_scan_new(self, scan, scan_info):
        self.print_scan_info(scan, scan_info)
        super().on_scan_new(scan_info)
        self.connect_real_motors(scan)

    def on_scan_data(self, scan_info, data):
        if self.is_new_data_valid(scan_info, data):
            if scan_info.get("type") == "ct":
                self._ct_data = data
            else:
                line = self.build_data_output(scan_info, data)
                if line:
                    self.print_scan_line(line)

            self.scan_steps_index += 1

    def on_scan_end(self, scan_info):
        self.disconnect_real_motors()
        if scan_info.get("type") == "ct":
            if self.is_end_scan_valid(scan_info):
                line = self.build_data_output(scan_info, self._ct_data)
                self.print_scan_line(line)
        super().on_scan_end(scan_info)

    def _on_motor_position_changed(self, position, signal=None, sender=None):
        self._labels.clear()
        for motor in self.real_motors:
            pos = "{0:.03f}".format(motor.position if sender is not motor else position)
            unit = motor.config.get("unit", default=None)
            if unit:
                pos += "[{0}]".format(unit)
            self._labels.append("{0}: {1}".format(motor.name, pos))

        # \33[2K means: erase current line
        self.print_scan_line(f"\33[2K\r{', '.join(self._labels)}", end="\r")


class CtProgressBar(tqdm):
    def __init__(self, count_time):
        self.__progress_greenlet = None

        total = int(count_time / 0.1) or None

        super().__init__(total=total, leave=False)

    def _progress_task(self):
        for i in range(self.total):  # _progress_bar.total):
            gevent.sleep(0.1)
            self.update()  # self._progress_bar.update()

    def update(self):
        # this is called from data update,
        # but there is only 1 data event for 'ct',
        # so it is not useful to show progress
        # (this is why we have greenlet for updating here)
        if self.__progress_greenlet is None:
            self.__progress_greenlet = gevent.spawn(self._progress_task)
        return super().update()

    def close(self):
        if self.__progress_greenlet:
            self.__progress_greenlet.kill()
        return super().close()


class ScanPrinterWithProgressBar(ScanPrinter):
    def __init__(self):
        """ Alternate ScanPrinter to be used in parallel of a ScanDataListener.
            Prints in the user shell a progress bar during the scan execution.
            Prints data output of 'ct' scans only.
        """
        super().__init__()

        self.progress_bar = None

        self._print_scan = True
        """FIXME: This have to be managed per scans"""

    def print_scan_header(self, scan_info):
        if scan_info.get("type") == "ct":
            return super().print_scan_header(scan_info)

    def print_data_header(self, scan_info):  # , first=False):
        if scan_info.get("type") == "ct":
            return super().print_data_header(scan_info)

    def build_data_output(self, scan_info, data):
        if scan_info.get("type") == "ct":
            return super().build_data_output(scan_info, data)
        return None

    def _on_motor_position_changed(self, position, signal=None, sender=None):
        super()._on_motor_position_changed(position, signal, sender)
        self.progress_bar.set_description(", ".join(self.labels))
        self.progress_bar.refresh()

    def _is_scan_must_be_printed(self):
        """Only print scans if it is executed as forground in BLISS shell"""
        # display progress bar only in BLISS repl
        if not is_bliss_shell():
            return False
        # If it was not started in the background
        current = gevent.getcurrent()
        if current.parent is not None:
            return False

        return True

    def on_scan_new(self, scan, scan_info):
        self._print_scan = self._is_scan_must_be_printed()
        if not self._print_scan:
            return
        super().on_scan_new(scan, scan_info)
        scan_type = scan_info.get("type")
        if scan_type == "ct":
            self.progress_bar = CtProgressBar(scan_info["count_time"])
            self.progress_bar.update()  # put in place the progress task
        else:
            self.progress_bar = tqdm(total=scan_info["npoints"], leave=False)

    def on_scan_data(self, scan_info, data):
        if not self._print_scan:
            return
        old_step = self.scan_steps_index
        super().on_scan_data(scan_info, data)
        if self.progress_bar is not None:
            if self.scan_steps_index > old_step:
                # only update if there is a new scan line
                if not scan_info["npoints"]:
                    self.progress_bar.total = self.scan_steps_index * 2
                    self.progress_bar.refresh()
                self.progress_bar.update()

    def on_scan_end(self, scan_info):
        if not self._print_scan:
            return
        if self.progress_bar is not None:
            self.progress_bar.close()
        super().on_scan_end(scan_info)
        self.progress_bar = None


class ScanDataListener(_ScanPrinterBase):
    def __init__(self, session_name):
        super().__init__()

        self.session_name = session_name
        self.scan_display = None
        self.scan_info = None
        self.update_header = False

    def update_displayed_channels_from_user_request(self) -> bool:
        """If enabled, check ScanDisplay content and compare it to the
        current displayed channel selection.

        If there is a mismatch, update the selection and redisplay the
        table header.

        Returns:
            True if the channel selection was changed.
        """
        if self.scan_display is None:
            self.scan_display = ScanDisplay(self.session_name)

        requested_channels = []
        if self.scan_display.scan_display_filter_enabled:
            # Use master channel plus user request
            requested_channels = self.scan_display.displayed_channels.copy()
            for m in self.master_channel_names:
                if m in requested_channels:
                    requested_channels.remove(m)
            # Always use the masters
            requested_channels = self.master_channel_names + requested_channels
        if not requested_channels:
            requested_channels = self.displayable_channel_names.copy()

        # Check if the content or the order have changed
        if self.sorted_channel_names != requested_channels:
            # Filter it with available channels
            requested_channels = [
                r for r in requested_channels if r in self.displayable_channel_names
            ]
            if self.sorted_channel_names != requested_channels:
                self.sorted_channel_names = requested_channels
                return True
        return False

    def collect_channels_info(self, scan_info):
        super().collect_channels_info(scan_info)
        # Update the displayed channels before printing the scan header
        self.update_displayed_channels_from_user_request()

    def on_scan_new_child(self, scan_info, data_channel):
        pass

    def on_scan_new(self, scan_info):
        self.scan_info = scan_info
        super().on_scan_new(scan_info)

    def on_scan_data(self, data_dim, master_name, channel_info):
        if data_dim != "0d":
            return False

        scan_info = channel_info["scan_info"]
        data = channel_info["data"]

        if self.is_new_data_valid(scan_info, data):
            with nonblocking_print():
                # Skip if partial data
                for cname in self.sorted_channel_names:
                    if len(data[cname]) <= self.scan_steps_index:
                        return False

                # Check if we receive more than one scan points (i.e. lines) per 'scan_data' event
                bsize = min(len(data[cname]) for cname in data)

                for i in range(bsize - self.scan_steps_index):
                    # convert data in order to keep only the concerned line (one scalar per channel).
                    ndata = {
                        cname: data[cname][self.scan_steps_index] for cname in data
                    }
                    line = self.build_data_output(scan_info, ndata)
                    if line:
                        print(line)
                    self.scan_steps_index += 1

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

        msg = f" Watching scans from Bliss session: '{self.session_name}' "
        line = get_decorated_line(msg, deco=">", rdeco="<", head="\n", tail="\n")

        observer = scan_mdl.DefaultScansObserver()
        observer.scan_new_callback = self.on_scan_new
        observer.scan_new_child_callback = self.on_scan_new_child
        observer.scan_data_callback = self.on_scan_data
        observer.scan_end_callback = self.on_scan_end

        watcher = scan_mdl.ScansWatcher(self.session_name)
        watcher.set_observer(observer)
        watcher.set_exclude_existing_scans(True)

        def print_ready():
            watcher.wait_ready()
            print(line)

        g = gevent.spawn(print_ready)

        try:
            watcher.run()
        finally:
            g.kill()
