# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Listen the scan data and display in a selected ptpython buffer console """

import sys
import time
import datetime
import numpy
import shutil
import signal
import atexit
import contextlib
import gevent

from bliss.data.scan import watch_session_scans
from bliss.common.utils import nonblocking_print
from bliss.common.axis import Axis
from bliss.common.event import dispatcher
from bliss.common.logtools import lprint
from bliss.common import user_status_info
from bliss.scanning.scan import set_scan_watch_callbacks
from bliss.scanning.scan_display import ScanDisplay
from bliss import global_map
from bliss.scanning.chain import ChainPreset, ChainIterationPreset


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


class FormatedTab:
    class _Cell:
        def __init__(
            self,
            value,
            dtype="g",
            align="^",
            width=12,
            flag="#",
            ellipse="..",
            fpreci="",
        ):

            self.value = value
            self.params = {
                "dtype": dtype,
                "align": align,
                "width": width,
                "flag": flag,  # '' or '#'
                "ellipse": ellipse,
                "fpreci": fpreci,  # '' or '.3' for example
            }

        def __str__(self):

            if isinstance(self.value, (int, float)):
                txt = f"{self.value:{self.params['flag']}{self.params['fpreci']}{self.dtype}}"
            else:
                txt = self._lim(str(self.value))

            return f"{txt:{self.params['align']}{self.width}}"

        def _lim(self, txt):
            if len(txt) > self.width:
                lng = self.width - len(self.params["ellipse"])
                txt = f"{self.params['ellipse']}{txt[-lng:]}"
            return txt

        @property
        def width(self):
            return self.params["width"]

        @width.setter
        def width(self, value):
            self.params["width"] = value

        @property
        def dtype(self):
            return self.params["dtype"]

        @property
        def vsize(self):
            """return the length of the value as a string"""
            if isinstance(self.value, str):
                return len(self.value)
            elif isinstance(self.value, (int, float)):
                return len(f"{self.value:{self.dtype}}")
            else:
                return len(str(self.value))

        def set_params(self, params):
            for k, v in params.items():
                if k in self.params.keys():
                    self.params[k] = v

    def __init__(
        self,
        header_lines,
        minwidth=1,
        maxwidth=50,
        col_sep=" ",
        dtype="g",
        align="^",
        flag="#",
        ellipse="..",
        fpreci="",
        lmargin="",
    ):

        """ helper class to manage tables of data with header lines and formated columns

            - header_lines (2D list): list of lines, each line is a list of words (labels).
               All lines must have the same number of words. 
            - minwidth: the minimum width for columns
            - maxwidth: the maximum width for columns
            - col_sep: the column separator character
            - dtype: format for numerical values (f, g, e)
            - align: alignment style [ center = '^', left = '<', right = '>' ]
            - flag: [ default form = '', alternate form = '#'] 
            - ellipse: characters to use for truncated labels
            - fpreci: precision for floating point numbers (eg: '.3' for 3 digits precision)
            - lmargin: left margin of the entire table

        """

        if not isinstance(header_lines, (list, tuple)):
            raise ValueError("header_lines must be a 2D list")

        dim = None
        for line in header_lines:

            if not isinstance(line, (list, tuple)):
                raise ValueError("header_lines must be a 2D list")

            if dim is None:
                dim = len(line)
            elif len(line) != dim:
                raise ValueError("header_lines: all lists must have the same size")

        if align not in ["^", "<", ">"]:
            raise ValueError("align must be in ['^', '<', '>'] ")

        self.col_sep = col_sep
        self.minwidth = minwidth
        self.maxwidth = max(maxwidth, self.minwidth)

        self.default_params = {
            "dtype": dtype,
            "align": align,
            "width": minwidth,
            "flag": flag,  # '' or '#'
            "ellipse": ellipse,
            "fpreci": fpreci,  # '' or '.3' for example
        }

        self.lmargin = lmargin
        self.col_num = 0
        self._cells = []  # [raw][col]

        for values in header_lines:
            self.add_line(values)

        self.resize()

    @property
    def full_width(self):
        if self._cells:
            full_width = sum([c.width for c in self._cells[0]])
            full_width += len(self.col_sep) * (self.col_num - 1)
            return full_width

    def get_line(self, index):
        return self._cells[index]

    def get_column(self, index):
        return list(zip(*self._cells))[index]

    def get_col_params(self, index):
        """get current column width, based on the cells of the last line"""

        if self._cells:
            return self._cells[-1][index].params
        else:
            return self.default_params

    def set_column_params(self, index, params):
        for cell in self.get_column(index):
            cell.set_params(params)

    def add_line(self, values, line_index=None):
        dim = len(values)
        if self._cells:
            if dim != self.col_num:
                raise ValueError(
                    f"cannot add a line with a different number of columns: {dim} != {self.col_num}"
                )
        else:
            self.col_num = dim

        line = [self._Cell(v, **self.get_col_params(i)) for i, v in enumerate(values)]

        if line_index is None:
            self._cells.append(line)
        else:
            self._cells.insert(line_index, line)

        return self.lmargin + self.col_sep.join([str(cell) for cell in line])

    def add_separator(self, sep="", line_index=None):
        if self._cells:
            self.add_line([sep * c.width for c in self._cells[0]], line_index)

    def resize(self, minwidth=None, maxwidth=None):
        if minwidth:
            self.minwidth = minwidth
        if maxwidth:
            self.maxwidth = max(maxwidth, self.minwidth)

        for col in zip(*self._cells):
            self._find_best_width(col)

    def _find_best_width(self, col_cells):

        _maxwidth = max([c.vsize for c in col_cells])
        _maxwidth = max(_maxwidth, self.minwidth)

        if self.maxwidth:
            _maxwidth = min(_maxwidth, self.maxwidth)

        for c in col_cells:
            c.width = _maxwidth

    def __str__(self):
        lines = [
            self.lmargin + self.col_sep.join([str(cell) for cell in line_cells])
            for line_cells in self._cells
        ]
        return "\n".join(lines)


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
        + "                 (use \033[90mplotselect\033[0m to custom this list)\n"
    )

    EXTRA_HEADER_2 = (
        "                 (use \033[90mplotselect\033[0m to filter this list)\n"
    )

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
        self.display_names = None
        self.channel_units = None
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
                #                        'scalars_units': {'axis:roby': None}, 
                #                        'spectra': [], 
                #                        'images': [], 
                #                        'display_names': {'axis:roby': 'roby'}
                #                       }, 

                #             'scalars': ['timer:elapsed_time', 
                #                         'timer:epoch', 
                #                         'lima_simulator2:bpm:x', 
                #                         'simulation_diode_sampling_controller:diode'],
                #  
                #             'scalars_units': {'timer:elapsed_time': 's', 
                #                               'timer:epoch': 's', 
                #                               'lima_simulator2:bpm:x': 'px', 
                #                               'simulation_diode_sampling_controller:diode': None}, 
                #             'spectra': [], 
                #             'images': [], 
                #             'display_names': {'timer:elapsed_time': 'elapsed_time', 
                #                               'timer:epoch': 'epoch', 
                #                               'lima_simulator2:bpm:x': 'x', 
                #                               'simulation_diode_sampling_controller:diode': 'diode'}}
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
        self.display_names = channels["master"]["display_names"]
        self.display_names.update(channels["display_names"])
        self.channel_units = channels["master"]["scalars_units"]
        self.channel_units.update(channels["scalars_units"])

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
                self._possible_motors.append(self.display_names[cname])

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

            # build the channel label
            if cname == "timer:elapsed_time":
                disp_name = "dt"
            else:
                disp_name = self.display_names[cname]

            # check if the unit must be added to channel label
            if channel_with_unit:
                unit = self.channel_units[cname]
                if unit:
                    disp_name += f"[{unit}]"

            channel_labels.append(disp_name)

            # try to get controller and counter names
            try:
                ctrl, cnt = cname.split(":")[0:2]
                if cnt == self.display_names[cname]:
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
        if scan_info.get("type") != "ct":

            col_max_width = 40
            labels = self.build_columns_labels()
            self._tab = FormatedTab(
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
        else:
            self._tab = ""

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

        return header

    def build_extra_header(self):
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
        if scan_info.get("type") != "ct":
            header += self.build_extra_header()
        print(header)

    def print_data_header(self, scan_info, first=False):
        """Print the header of the data table.

        The first one skip the EXTRA_HEADER, cause it is already part of the
        scan header.
        """
        if not first:
            header = "\n" + self.build_extra_header()
        else:
            header = ""

        self.build_header(scan_info)
        tab = str(self._tab)
        print(header + tab)

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

    def _build_ct_output(self, values, norm_values):

        info_dict = {}
        width = 20
        for i, cname in enumerate(self.sorted_channel_names):

            # display name
            if cname == "timer:elapsed_time":
                # disp_name = "dt"
                continue
            else:
                disp_name = self.display_names[cname]

            # unit
            unit = self.channel_units[cname]
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
                v = f"{v:#g}"
                nv = f"{nv:#g}"
                lines.append(f"  {dname:>{width}}  =  {v:12} ({nv:^12}/s)    {ctrl}")

            # separate data blocks per controller
            # lines.append('')

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

        return True

    def on_scan_new(self, scan_info):

        if self.is_new_scan_valid(scan_info):

            self.scan_is_running = True
            self.scan_name = scan_info.get("node_name")
            self.scan_steps_index = 0
            self._warning_messages = []

            self.collect_channels_info(scan_info)
            self.print_scan_header(scan_info)

    def on_scan_data(self, scan_info, data):
        raise NotImplementedError

    def on_scan_end(self, scan_info):
        if self.is_end_scan_valid(scan_info):
            end = datetime.datetime.fromtimestamp(time.time())
            start = datetime.datetime.fromtimestamp(scan_info["start_timestamp"])
            dt = end - start

            self.scan_is_running = False

            for msg in self._warning_messages:
                print(msg)

            print(f"\n   Took {dt}[s] \n")


class ScanPrinter(_ScanPrinterBase):
    """compose scan output"""

    HEADER = ""

    def __init__(self):

        super().__init__()

        self.real_motors = None
        set_scan_watch_callbacks(self.on_scan_new, self.on_scan_data, self.on_scan_end)

    def print_scan_info(self, scan, scan_info):
        """Print date + scan __repr__ at the beginning of the scan output"""
        lprint(f"   {scan_info['start_time_str']}: {scan}")

    def find_and_connect_real_motors(self):
        self.real_motors = []
        for disp_name in self._possible_motors:
            # we can suppose channel_fullname to be a motor name
            motor = _find_obj(disp_name)
            if isinstance(motor, Axis):
                self.real_motors.append(motor)
                if self.term.is_a_tty:
                    dispatcher.connect(
                        self._on_motor_position_changed, signal="position", sender=motor
                    )

    def disconnect_real_motors(self):
        for motor in self.real_motors:
            dispatcher.disconnect(
                self._on_motor_position_changed, signal="position", sender=motor
            )

    def on_scan_new(self, scan, scan_info):
        self.term = Terminal(scan_info.get("stream"))
        self.print_scan_info(scan, scan_info)
        super().on_scan_new(scan_info)
        self.find_and_connect_real_motors()

    def on_scan_data(self, scan_info, data):

        if self.is_new_data_valid(scan_info, data):
            line = self.build_data_output(scan_info, data)

            if self.term.is_a_tty and scan_info.get("type") == "ct":
                monitor = scan_info.get("output_mode", "tail") == "monitor"
                print("\r" + line, end=monitor and "\r" or "\n")
            else:
                print(line)

            self.scan_steps_index += 1

    def on_scan_end(self, scan_info):
        super().on_scan_end(scan_info)
        self.disconnect_real_motors

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
        if requested_channels == []:
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
        super(ScanDataListener, self).collect_channels_info(scan_info)
        # Update the displayed channels before printing the scan header
        self.update_displayed_channels_from_user_request()

    def on_scan_new_child(self, scan_info, data_channel):
        pass

    def on_scan_new(self, scan_info):
        if not self.scan_is_running:
            self.update_header = True
            self.first_header = True
            self.scan_info = scan_info
        super(ScanDataListener, self).on_scan_new(scan_info)

    def on_scan_data(self, data_dim, master_name, channel_info):
        if data_dim != "0d":
            return False

        scan_info = channel_info["scan_info"]
        data = channel_info["data"]

        if self.is_new_data_valid(scan_info, data):
            with nonblocking_print():
                if scan_info.get("type") != "ct":
                    updated = self.update_displayed_channels_from_user_request()
                    self.update_header = self.update_header or updated
                else:
                    self.update_header = False

                # Skip if partial data
                for cname in self.sorted_channel_names:
                    if len(data[cname]) <= self.scan_steps_index:
                        return False

                if self.update_header:
                    self.update_header = False
                    # The table header have to be updated
                    # It is always the case the very first time
                    self.print_data_header(scan_info, first=self.first_header)
                    self.first_header = False

                # Check if we receive more than one scan points (i.e. lines) per 'scan_data' event
                bsize = min([len(data[cname]) for cname in data])

                for i in range(bsize - self.scan_steps_index):
                    # convert data in order to keep only the concerned line (one scalar per channel).
                    ndata = {
                        cname: data[cname][self.scan_steps_index] for cname in data
                    }
                    line = self.build_data_output(scan_info, ndata)
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
        print(line)

        # Start the watch, winter is coming...
        watch_session_scans(
            self.session_name,
            self.on_scan_new,
            self.on_scan_new_child,
            self.on_scan_data,
            self.on_scan_end,
        )


@contextlib.contextmanager
def _local_pb(scan, repl, task):
    # Shitty cyclic import
    # we have to purge this :-(
    from bliss.shell.cli import progressbar

    def stop():
        task.kill()

    repl.register_application_stopper(stop)
    try:
        real_motors = list()
        messages_dict = dict()

        def set_scan_status(*messages):
            messages_dict["status"] = ",".join(messages)
            on_motor_position_changed(None)  # refresh progressbar label

        def on_motor_position_changed(position, signal=None, sender=None):
            labels = []
            for motor in real_motors:
                position = "{0:.03f}".format(motor.position)
                unit = motor.config.get("unit", default=None)
                if unit:
                    position += "[{0}]".format(unit)
                labels.append("{0}: {1}".format(motor.name, position))
            message_status = messages_dict.get("status")
            if message_status:
                labels.append(message_status)
            pb.bar.label = ", ".join(labels)
            pb.invalidate()

        scan_info = scan.scan_info
        master, channels = next(iter(scan_info["acquisition_chain"].items()))
        for channel_fullname in channels["master"]["scalars"]:
            channel_short_name = channels["master"]["display_names"][channel_fullname]
            motor = _find_obj(channel_short_name)
            if isinstance(motor, Axis):
                real_motors.append(motor)
                dispatcher.connect(
                    on_motor_position_changed, signal="position", sender=motor
                )
        if scan.scan_info.get("type") == "ct":

            class my_pb(progressbar.ProgressBar):
                def __call__(self, queue, **keys):
                    npoints = int(scan.scan_info.get("count_time", 1) // .1) or None
                    keys["total"] = npoints
                    self._ct_tick_task = None
                    if npoints:

                        def tick():
                            for i in range(npoints):
                                queue.put("-")
                                gevent.sleep(.1)

                        self._ct_tick_task = gevent.spawn(tick)
                    return super().__call__(queue, **keys)

                def __exit__(self, *args, **kwargs):
                    if self._ct_tick_task is not None:
                        self._ct_tick_task.kill()
                    super().__exit__(*args, **kwargs)

            with my_pb() as pb:
                yield pb
        else:
            with user_status_info.callback() as cbk:
                cbk(set_scan_status)
                with progressbar.ProgressBar() as pb:
                    yield pb

    except KeyboardInterrupt:
        repl.stop_current_task(block=False, exception=KeyboardInterrupt)

    finally:
        repl.unregister_application_stopper(stop)
        for motor in real_motors:
            dispatcher.disconnect(
                on_motor_position_changed, signal="position", sender=motor
            )


class ScanPrinterWithProgressBar(ScanPrinter):
    def __init__(self, repl):
        """ Alternate ScanPrinter to be used in parallel of a ScanDataListener.
            Prints in the user shell a progress bar during the scan execution.
            Prints data output of 'ct' scans only.
        """

        super().__init__()

        self.repl = repl
        self.progress_task = None
        self._on_scan_data_values = None

    def on_scan_new(self, scan, scan_info):

        # allow prints for 'ct' scans only
        scan_type = scan_info.get("type")
        if scan_type == "ct":
            super().on_scan_new(scan, scan_info)

        # prepare progress bar for all type of scans
        if self.progress_task:
            self.progress_task.kill()

        self._on_scan_data_values = None

        # display progressbar only in repl greenlet
        if self.repl.current_task != gevent.getcurrent():
            return

        started_event = gevent.event.Event()
        self.progress_task = gevent.spawn(self._progress_bar, scan, started_event)
        with gevent.Timeout(1.):
            started_event.wait()

    def on_scan_data(self, scan_info, values):
        self._on_scan_data_values = scan_info, values

    def on_scan_end(self, scan_info):
        # allow prints for 'ct' scans only
        scan_type = scan_info.get("type")
        if scan_type == "ct":
            super().on_scan_end(scan_info)

    def _progress_bar(self, scan, started_event):

        try:
            npoints = scan.scan_info["npoints"]
        except KeyError:
            started_event.set()
            return  # nothing to do
        queue = gevent.queue.Queue()
        task = self.progress_task

        class Preset(ChainPreset):
            class Iter(ChainIterationPreset):
                def stop(self):
                    queue.put("+")

            def get_iterator(self, chain):
                while True:
                    yield Preset.Iter()

            def stop(self, chain):
                queue.put(StopIteration)
                task.join()

        preset = Preset()
        scan.acq_chain.add_preset(preset)
        started_event.set()
        try:
            with _local_pb(scan, self.repl, task) as pb:
                it = pb(queue, remove_when_done=True, total=npoints or None)
                pb.bar = it
                for i in it:
                    pass
        finally:
            if self._on_scan_data_values:
                scan_info, values = self._on_scan_data_values
                scan_type = scan_info.get("type")
                if scan_type == "ct":
                    line = self.build_data_output(scan_info, values)
                    print(line)
