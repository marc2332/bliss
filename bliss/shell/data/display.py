# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Listen the scan data and display in a selected ptpython buffer console """

import time
from tqdm import tqdm
import datetime
import numpy
import shutil
import typing
import gevent
import numbers

from bliss.data import scan as scan_mdl
from bliss.common.utils import nonblocking_print
from bliss.common.event import dispatcher
from bliss.common.logtools import user_print
from bliss.scanning.scan import set_scan_watch_callbacks
from bliss.scanning.scan_display import ScanDisplay
from bliss import global_map, is_bliss_shell
from bliss.shell.formatters.table import IncrementalTable


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


def is_scan_supported(scan_info):
    """Returns true if the scan is supported"""
    if len(scan_info["acquisition_chain"].keys()) != 1:
        return False

    # Skip scans without a type or without a number of points
    scan_type = scan_info.get("type")
    npoints = scan_info.get("npoints")
    if None in [scan_type, npoints]:
        return False

    return True


class ChannelMetadata(typing.NamedTuple):
    """Store metadata about a channel"""

    display_name: str
    unit: typing.Optional[str]


class ScanRenderer:
    """Reach information from scan_info and provide an helper to display
    top down data table view."""

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

    def __init__(self, scan_info):
        self._displayable_channel_names = None
        self._master_channel_names = []
        self._sorted_channel_names = []
        self._channels_meta = {}
        self._other_channels = None
        self._scan_info = scan_info
        self._tab = None
        self._nb_data_rows = 0
        self._channels_number = None
        self._collect_channels_info(scan_info)
        self._row_data = []

    @property
    def nb_data_rows(self) -> int:
        """Returns rows already received"""
        return self._nb_data_rows

    @property
    def scan_type(self) -> str:
        """Returns the kind of the scan"""
        return self._scan_type

    @property
    def sorted_channel_names(self):
        """List of channel names displayed in columns"""
        return self._sorted_channel_names

    @property
    def displayable_channel_names(self):
        """Channel names from this scans which displayable.

        For example images and MCAs are not displayable.
        """
        return self._displayable_channel_names

    @property
    def master_scalar_channel_names(self):
        """Channel names from this scans which are both masters and scalars.
        """
        return self._master_channel_names

    def _collect_channels_info(self, scan_info):
        """Collect information from scan_info

        Only the first top master is reached. Others are ignored.
        """
        # only the first top master is used
        _top_master, channels = next(iter(scan_info["acquisition_chain"].items()))

        self._scan_type = scan_info.get("type")

        # get the total number of channels
        self._channels_number = len(channels["master"]["scalars"]) + len(
            channels["scalars"]
        )

        # get master scalar channels (remove epoch)
        master_scalar_channels = [
            cname for cname in channels["master"]["scalars"] if cname != "timer:epoch"
        ]

        # get scalar channels (remove epoch)
        counter_scalar_channels = [
            cname for cname in channels["scalars"] if cname != "timer:epoch"
        ]

        # get all channels fullname, display names and units
        channel_names = master_scalar_channels + counter_scalar_channels

        channels_meta = {}
        for channel_name, meta in scan_info["channels"].items():
            display_name = meta.get("display_name")
            if display_name is None:
                display_name = channel_name.split(":")[-1]
            unit = meta.get("unit")
            metadata = ChannelMetadata(display_name, unit)
            channels_meta[channel_name] = metadata
        self._channels_meta = channels_meta

        # get none scalar channels (spectra and images)
        self._other_channels = (
            channels["master"]["spectra"] + channels["master"]["images"]
        )
        self._other_channels += channels["spectra"] + channels["images"]

        displayable_channels = list(set(channel_names))

        sorted_channel_names = []
        # First the timer channel if any
        timer_cname = "timer:elapsed_time"
        if timer_cname in channel_names:
            sorted_channel_names.append(timer_cname)
        # Then masters
        for cname in master_scalar_channels:
            if cname not in sorted_channel_names:
                sorted_channel_names.append(cname)
        # Finally the other scalars channels
        for cname in counter_scalar_channels:
            if cname not in sorted_channel_names:
                sorted_channel_names.append(cname)

        #  Store the channels contained in the scan_info
        self._master_channel_names = master_scalar_channels
        self._displayable_channel_names = displayable_channels
        self._sorted_channel_names = sorted_channel_names

    def set_displayed_channels(self, channel_names):
        """Set the list of column names to display.

        The input argument is filtered.
        """
        # Check if the content or the order have changed
        if self._sorted_channel_names != channel_names:
            # Filter it with available channels
            requested_channels = [
                r for r in channel_names if r in self._displayable_channel_names
            ]
            if self._sorted_channel_names != requested_channels:
                self._sorted_channel_names = requested_channels

    def print_table_header(self):
        """Print the header of the data table.
        """
        if self._scan_type != "ct":
            col_max_width = 40
            labels = self._build_columns_labels()
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

    def _build_columns_labels(self):
        # Build the columns labels (multi-line with counter and controller names)
        channel_labels = []
        counter_labels = []
        controller_labels = []

        for cname in self._sorted_channel_names:
            channel_meta = self._channels_meta[cname]

            # build the channel label
            if cname == "timer:elapsed_time":
                disp_name = "dt"
            else:
                disp_name = channel_meta.display_name

            # check if the unit must be added to channel label
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

        controller_labels.insert(0, "")
        counter_labels.insert(0, "")  # 'index'
        channel_labels.insert(0, "#")

        return [controller_labels, channel_labels]  # counter_labels useless in table

    def print_scan_header(self):
        """Print the header of a new scan"""
        header = self._build_scan_header()
        print(header)

    def _build_scan_header(self):
        """Build the header to be displayed
        """
        # A message about not shown channels
        not_shown_counters_str = ""
        if self._other_channels:
            not_shown_counters_str = ", ".join(self._other_channels)

        master_names = ", ".join(self._master_channel_names)

        header = self.HEADER.format(
            not_shown_counters_str=not_shown_counters_str,
            master_names=master_names,
            **self._scan_info,
        )

        if self._scan_type != "ct":
            header += self._build_extra_scan_header()

        return header

    def _build_extra_scan_header(self):
        not_selected = [
            c
            for c in self._displayable_channel_names
            if c not in self._sorted_channel_names
        ]
        if len(not_selected) == 0:
            return self.EXTRA_HEADER_2

        not_selected = [f"'\033[91m{c}\033[0m'" for c in not_selected]
        not_selected = ", ".join(not_selected)
        return self.EXTRA_HEADER.format(not_selected=not_selected)

    def append_data(self, data):
        """Append data before printing"""
        if not set(data.keys()).issuperset(self._sorted_channel_names):
            return

        self._row_data.append(data)
        self._nb_data_rows += 1

    def print_data_rows(self):
        """Print and flush the available data rows"""
        if len(self._row_data) == 0:
            # Nothing new
            return
        rows = self._row_data
        self._row_data = []

        lines = []
        for i, r in enumerate(rows):
            index = self._nb_data_rows + i - len(rows)
            lines.append(self._build_data_row(index, r))
        block = "\n".join(lines)
        print(block)

    def print_data_ct(self, scan_info):
        # ct is actually a timescan(npoints=1).
        data = self._row_data[-1]
        values = [data[cname] for cname in self._sorted_channel_names]
        norm_values = numpy.array(values) / self._scan_info["count_time"]
        block = self._build_ct_output(values, norm_values)
        print(block)

    def _build_data_row(self, index, data):
        """ data is a dict, one scalar per channel (last point) """
        values = [data[cname] for cname in self._sorted_channel_names]
        values.insert(0, index)
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
        for i, cname in enumerate(self._sorted_channel_names):
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

    def print_scan_end(self, scan_info):
        """Print the end of the scan.

        Argument:
            scan_info: The final state of the `scan_info`
        """
        end = datetime.datetime.fromtimestamp(time.time())
        start = datetime.datetime.fromtimestamp(scan_info["start_timestamp"])
        dt = end - start
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


class ScanHooks:
    """Abstract class with the expected signature to retrieve BLISS scans
    internal hooks.

    This do not use Redis.

    .. code-block::

        from bliss.scanning.scan import set_scan_watch_callbacks
        set_scan_watch_callbacks(self.on_scan_new, self.on_scan_data, self.on_scan_end)

    FIXME: It would be better to provide it from the scan class.
    """

    def on_scan_new(self, scan, scan_info):
        """Called by BLISS callback on new scan start"""
        pass

    def on_scan_data(self, scan_info, data):
        """Called by BLISS callback on a new scan data"""
        pass

    def on_scan_end(self, scan_info):
        """Called by BLISS callback on scan ending"""
        pass


class ScanPrinter(ScanHooks, ScanMotorListener):
    """compose scan output"""

    def __init__(self):
        super().__init__()

        self._labels = []
        self.scan_renderer = None
        self._print_table = True

    @property
    def labels(self):
        return self._labels

    def print_scan_info(self, scan, scan_info):
        """Print date + scan __repr__ at the beginning of the scan output"""
        user_print(f"   {scan_info['start_time_str']}: {scan}")

    def on_scan_new(self, scan, scan_info):
        self.print_scan_info(scan, scan_info)
        self.scan_renderer = ScanRenderer(scan_info)
        if self._print_table:
            self.scan_renderer.print_table_header()
        self.connect_real_motors(scan)

    def on_scan_data(self, scan_info, data):
        self.scan_renderer.append_data(data)
        if self._print_table:
            if self.scan_renderer.scan_type != "ct":
                self.scan_renderer.print_data_rows()

    def on_scan_end(self, scan_info):
        self.disconnect_real_motors()
        if self.scan_renderer.scan_type == "ct":
            self.scan_renderer.print_data_ct(scan_info)
        self.scan_renderer.print_scan_end(scan_info)

    def _on_motor_position_changed(self, position, signal=None, sender=None):
        self._labels.clear()
        for motor in self.real_motors:
            pos = "{0:.03f}".format(motor.position if sender is not motor else position)
            unit = motor.config.get("unit", default=None)
            if unit:
                pos += "[{0}]".format(unit)
            self._labels.append("{0}: {1}".format(motor.name, pos))

        ERASE_CURRENT_LINE = "\33[2K"
        print(f"{ERASE_CURRENT_LINE}\r{', '.join(self._labels)}", end="\r")


class CtPrinterWithProgressBar(ScanPrinter):
    """Dedicated ScanPrinter for ct scan.

    Displays a progress bar according to the count time.
    """

    def __init__(self):
        super().__init__()
        self.__progress_bar = None
        self.__progress_greenlet = None
        self._print_table = False

    def _progress_task(self):
        prev = self.__start
        now = time.time()
        while now < self.__end:
            gevent.sleep(0.2)
            now = time.time()
            increment = now - prev
            prev = now
            self.__progress_bar.update(increment)

    def on_scan_new(self, scan, scan_info):
        super(CtPrinterWithProgressBar, self).on_scan_new(scan, scan_info)
        count_time = scan_info["count_time"]
        self.__progress_bar = tqdm(total=count_time, unit_scale=True, leave=False)
        self.__start = time.time()
        self.__end = self.__start + count_time
        self.__progress_bar.update(0.0)
        if self.__progress_greenlet is None:
            self.__progress_greenlet = gevent.spawn(self._progress_task)

    def on_scan_end(self, scan_info):
        if self.__progress_greenlet:
            self.__progress_greenlet.kill()
            self.__progress_greenlet = None
        self.__progress_bar.close()
        self.__progress_bar = None
        super().on_scan_end(scan_info)


class ScanPrinterWithProgressBar(ScanPrinter):
    """Dedicated ScanPrinter for any scan.

    Displays a progress bar according to the received data.
    """

    def __init__(self):
        super().__init__()
        self.progress_bar = None
        self._print_table = False

    def _on_motor_position_changed(self, position, signal=None, sender=None):
        super()._on_motor_position_changed(position, signal, sender)
        self.progress_bar.set_description(", ".join(self.labels))
        self.progress_bar.refresh()

    def on_scan_new(self, scan, scan_info):
        super().on_scan_new(scan, scan_info)
        total = scan_info["npoints"]
        self.progress_bar = tqdm(total=total, leave=False)

    def on_scan_data(self, scan_info, data):
        nb_rows = self.scan_renderer.nb_data_rows
        super().on_scan_data(scan_info, data)
        steps = self.scan_renderer.nb_data_rows - nb_rows
        if steps > 0:
            # only update if there is a new scan line
            self.progress_bar.update(steps)

    def on_scan_end(self, scan_info):
        if self.progress_bar is not None:
            self.progress_bar.close()
        super().on_scan_end(scan_info)
        self.progress_bar = None


class ScanDisplayDispatcher(ScanHooks):
    """Listen scans from the BLISS session and dispatch them to dedicated scan
    displayer"""

    def __init__(self):
        set_scan_watch_callbacks(self.on_scan_new, self.on_scan_data, self.on_scan_end)
        self._scan_displayer = None
        """Current scan displayer"""

        self._scan_id = None
        """Current scan id"""

        self._use_progress_bar = False
        """If True try to use a scan display using a progress bar"""

    def set_use_progress_bar(self, use_progress_bar):
        """When set the next displayed scan will use or not the progress bar"""
        self._use_progress_bar = use_progress_bar

    def _create_scan_displayer(self, scan, scan_info):
        """Create a scan displayer for a specific scan"""

        if not is_scan_supported(scan_info):
            return None

        # Display the scan only on the main BlissRepl
        if not is_bliss_shell():
            return None

        # Scans started from the background are ignored
        current = gevent.getcurrent()
        if current.parent is not None:
            return None

        if self._use_progress_bar:
            scan_type = scan_info.get("type")
            if scan_type == "ct":
                return CtPrinterWithProgressBar()
            else:
                return ScanPrinterWithProgressBar()
        else:
            return ScanPrinter()

    def on_scan_new(self, scan, scan_info):
        """Called by BLISS callback on new scan start"""
        if self._scan_displayer is None:
            self._scan_displayer = self._create_scan_displayer(scan, scan_info)
            if self._scan_displayer is not None:
                self._scan_id = scan_info["node_name"]
                self._scan_displayer.on_scan_new(scan, scan_info)

    def on_scan_data(self, scan_info, data):
        """Called by BLISS callback on a new scan data"""
        scan_id = scan_info["node_name"]
        if self._scan_id == scan_id:
            if self._scan_displayer is not None:
                self._scan_displayer.on_scan_data(scan_info, data)

    def on_scan_end(self, scan_info):
        """Called by BLISS callback on scan ending"""
        scan_id = scan_info["node_name"]
        if self._scan_id == scan_id:
            try:
                if self._scan_displayer is not None:
                    self._scan_displayer.on_scan_end(scan_info)
            finally:
                self._scan_displayer = None
                self._scan_id = None


class ScanDataRowStream:
    """Hold the data received from Redis to follow the last available row.

    When the row is read the data is released.
    """

    def __init__(self):
        self._data_per_channels = {}
        self._nb_per_channels = {}
        self._nb_full_rows = 0
        self._current = -1

    def register(self, name: str):
        self._data_per_channels[name] = []
        self._nb_per_channels[name] = 0

    def is_registered(self, name: str) -> bool:
        return name in self._data_per_channels

    def add_channel_data(self, name: str, index: int, data_bunch: numpy.ndarray):
        row = self._data_per_channels.setdefault(name, [])
        row.append([index, data_bunch])
        self._nb_per_channels[name] = index + len(data_bunch)

    def _pop_channel_value(self, name: str, index: int):
        row = self._data_per_channels[name]
        data_index, data_bunch = row[0]
        while not (index < data_index + len(data_bunch)):
            row.pop(0)
            data_index, data_bunch = row[0]
        return data_bunch[index - data_index]

    def next_rows(self) -> typing.Iterator[typing.Dict[str, float]]:
        """Returns a dict containing the next value of each channels.

        Else returns None
        """
        self._nb_full_rows = min(self._nb_per_channels.values())
        if self._nb_full_rows == 0:
            return
        for i in range(self._current + 1, self._nb_full_rows):
            data = {
                k: self._pop_channel_value(k, i) for k in self._data_per_channels.keys()
            }
            yield data
        self._current = self._nb_full_rows - 1


class ScanPrinterFromRedis(scan_mdl.ScansObserver):
    def __init__(self, scan_display):
        super(ScanPrinterFromRedis, self).__init__()
        self.scan_display = scan_display
        self.update_header = False
        self.scan_renderer = None
        self._rows = ScanDataRowStream()

    def update_displayed_channels_from_user_request(self) -> bool:
        """If enabled, check ScanDisplay content and compare it to the
        current displayed channel selection.

        If there is a mismatch, update the selection and redisplay the
        table header.

        Returns:
            True if the channel selection was changed.
        """
        requested_channels = []
        scan_renderer = self.scan_renderer
        if self.scan_display.scan_display_filter_enabled:
            # Use master channel plus user request
            requested_channels = self.scan_display.displayed_channels.copy()
            if len(requested_channels) == 0:
                return
            for m in scan_renderer.master_scalar_channel_names:
                if m in requested_channels:
                    requested_channels.remove(m)
            # Always use the masters
            requested_channels = (
                scan_renderer.master_scalar_channel_names + requested_channels
            )
            if not requested_channels:
                requested_channels = scan_renderer.displayable_channel_names.copy()
            scan_renderer.set_displayed_channels(requested_channels)

    def on_scan_started(self, scan_db_name: str, scan_info: typing.Dict):
        self.scan_renderer = ScanRenderer(scan_info)
        # Update the displayed channels before printing the scan header
        if self.scan_renderer.scan_type != "ct":
            self.update_displayed_channels_from_user_request()
        for n in self.scan_renderer.sorted_channel_names:
            self._rows.register(n)
        self.scan_renderer.print_scan_header()
        self.scan_renderer.print_table_header()

    def on_scan_finished(self, scan_db_name: str, scan_info: typing.Dict):
        if self.scan_renderer.scan_type == "ct":
            self.scan_renderer.print_data_ct(scan_info)
        self.scan_renderer.print_scan_end(scan_info)

    def on_scalar_data_received(
        self,
        scan_db_name: str,
        channel_name: str,
        index: int,
        data_bunch: typing.Union[list, numpy.ndarray],
    ):
        if not self._rows.is_registered(channel_name):
            return

        self._rows.add_channel_data(channel_name, index, data_bunch)
        for row in self._rows.next_rows():
            self.scan_renderer.append_data(row)

        if self.scan_renderer.scan_type != "ct":
            with nonblocking_print():
                self.scan_renderer.print_data_rows()


class ScanDataListener(scan_mdl.ScansObserver):
    """Listen all the scans of a session from Redis and dispatch them to a
    dedicated printer"""

    def __init__(self, session_name):
        super().__init__()
        self.session_name = session_name
        self.scan_display = ScanDisplay(self.session_name)

        self._scan_displayer = None
        """Current scan displayer"""

        self._scan_id = None
        """Current scan id"""

        self._warning_messages = []

    def _create_scan_displayer(self, scan_info):
        """Create a scan displayer for a specific scan"""
        if not is_scan_supported(scan_info):
            return None
        return ScanPrinterFromRedis(self.scan_display)

    def on_scan_started(self, scan_db_name: str, scan_info: typing.Dict):
        """Called from Redis callback on scan started"""
        if self._scan_displayer is None:
            self._scan_displayer = self._create_scan_displayer(scan_info)
            if self._scan_displayer is not None:
                self._scan_id = scan_db_name
                self._scan_displayer.on_scan_started(scan_db_name, scan_info)
        else:
            self._warning_messages.append(
                f"\nWarning: a new scan '{scan_db_name}' has been started while scan '{self._scan_id}' is running.\nNew scan outputs will be ignored."
            )

    def on_scan_finished(self, scan_db_name: str, scan_info: typing.Dict):
        """Called from Redis callback on scan ending"""
        scan_id = scan_info["node_name"]
        if self._scan_id == scan_id:
            try:
                if self._scan_displayer is not None:
                    self._scan_displayer.on_scan_finished(scan_db_name, scan_info)
            finally:
                self._scan_displayer = None
                self._scan_id = None

        messages = self._warning_messages
        self._warning_messages.clear()
        for msg in messages:
            print(msg)

    def on_scalar_data_received(
        self,
        scan_db_name: str,
        channel_name: str,
        index: int,
        data_bunch: typing.Union[list, numpy.ndarray],
    ):
        """Called from Redis callback on a scalar data received"""
        if self._scan_id == scan_db_name:
            if self._scan_displayer is not None:
                self._scan_displayer.on_scalar_data_received(
                    scan_db_name, channel_name, index, data_bunch
                )

    def start(self):

        msg = f" Watching scans from Bliss session: '{self.session_name}' "
        line = get_decorated_line(msg, deco=">", rdeco="<", head="\n", tail="\n")

        watcher = scan_mdl.ScansWatcher(self.session_name)
        watcher.set_observer(self)
        watcher.set_exclude_existing_scans(True)

        def print_ready():
            watcher.wait_ready()
            print(line)

        g = gevent.spawn(print_ready)

        try:
            watcher.run()
        finally:
            g.kill()
