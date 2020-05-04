# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import enum
import gevent
import os
import weakref
import sys
import time
import datetime
import collections
import typing
from functools import wraps
import warnings

from bliss import current_session, is_bliss_shell
from bliss.common.event import connect, disconnect
from bliss.common.cleanup import error_cleanup, axis as cleanup_axis, capture_exceptions
from bliss.common.greenlet_utils import KillMask
from bliss.common.plot import (
    get_flint,
    check_flint,
    CurvePlot,
    ImagePlot,
    ScatterPlot,
    McaPlot,
)
from bliss.common.utils import periodic_exec, deep_update
from bliss.scanning.scan_meta import get_user_scan_meta
from bliss.common.axis import Axis
from bliss.common.utils import Statistics, Null, update_node_info, round
from bliss.controllers.motor import remove_real_dependent_of_calc
from bliss.config.settings import ParametersWardrobe
from bliss.config.settings import pipeline
from bliss.data.node import _get_or_create_node, _create_node, is_zerod
from bliss.data.scan import get_data
from bliss.scanning.chain import (
    AcquisitionSlave,
    AcquisitionMaster,
    StopChain,
    CompletedCtrlParamsDict,
)
from bliss.scanning.writer.null import Writer as NullWriter
from bliss.scanning import scan_math
from bliss.scanning.scan_saving import ScanSaving
from bliss.common.logtools import lprint_disable
from louie import saferef
from bliss.common.plot import get_plot
from bliss import __version__ as publisher_version

# Globals
current_module = sys.modules[__name__]

# STORE THE CALLBACK FUNCTIONS THAT ARE CALLED DURING A SCAN ON THE EVENTS SCAN_NEW, SCAN_DATA, SCAN_END
# THIS FUNCTIONS ARE EXPECTED TO PRINT INFO ABOUT THE SCAN AT THE CONSOLE LEVEL (see bliss/shell/cli/repl => ScanPrinter )
# USERS CAN OVERRIDE THE DEFAULT TO SPECIFY ITS OWN SCAN INFO DISPLAY
# BY DEFAULT THE CALLBACKS ARE SET TO NULL() TO AVOID UNNECESSARY PRINTS OUTSIDE A SHELL CONTEXT
_SCAN_WATCH_CALLBACKS = {"new": Null(), "data": Null(), "end": Null()}


def set_scan_watch_callbacks(scan_new=None, scan_data=None, scan_end=None):
    if scan_new is None:
        r_scan_new = Null()
    elif not callable(scan_new):
        raise TypeError(f"{scan_new} is not callable")
    else:
        r_scan_new = saferef.safe_ref(scan_new)

    if scan_data is None:
        r_scan_data = Null()
    elif not callable(scan_data):
        raise TypeError(f"{scan_data} is not callable")
    else:
        r_scan_data = saferef.safe_ref(scan_data)

    if scan_end is None:
        r_scan_end = Null()
    elif not callable(scan_end):
        raise TypeError(f"{scan_end} is not callable")
    else:
        r_scan_end = saferef.safe_ref(scan_end)

    _SCAN_WATCH_CALLBACKS.update(
        {"new": r_scan_new, "data": r_scan_data, "end": r_scan_end}
    )


class DataWatchCallback:
    def on_state(self, state):
        """Ask if callback **on_scan_data** will be called during
        **PREPARING** and **STOPPING** state. The return of this
        method will activate/deactivate the calling of the callback
        **on_scan_data** during this stage. By default
        **on_scan_data** will be only called when new data are
        emitted.

        state -- either ScanState.PREPARING or ScanState.STOPPING.

        i.e: return state == ScanState.PREPARING will inform that
        **on_scan_data** will be called during **PREPARING** scan
        state.

        """
        return False

    def on_scan_new(self, scan, scan_info):
        """
        This callback is called when the scan is about to starts
        
        scan -- is the scan object
        scan_info -- is the dict of information about this scan
        """
        pass

    def on_scan_data(self, data_events, nodes, scan_info):
        """
        This callback is called when new data is emitted.

        data_events --  a dict with Acq(Device/Master) as key and a set of signal as values
        nodes -- a dict with Acq(Device/Master) as key and the associated data node as value
        scan_info -- dictionnary which contains the current scan state
        """
        raise NotImplementedError

    def on_scan_end(self, scan_info):
        """
        Called at the end of the scan.
        """
        pass


class StepScanDataWatch(DataWatchCallback):
    """
    This class is an helper to follow data generation by a step scan like:
    an acquisition chain with motor(s) as the top-master.
    This produce event compatible with the ScanListener class (bliss.shell)
    """

    def __init__(self):
        self._last_point_display = 0
        self._channel_name_2_channel = dict()
        self._init_done = False

    def on_scan_new(self, scan, scan_info):

        cb = _SCAN_WATCH_CALLBACKS["new"]()
        if cb is not None:
            cb(scan, scan_info)

    def on_scan_data(self, data_events, nodes, scan_info):

        cb = _SCAN_WATCH_CALLBACKS["data"]()
        if cb is None:
            return

        if not self._init_done:
            for acq_device_or_channel, data_node in nodes.items():
                if is_zerod(data_node):
                    channel = data_node
                    self._channel_name_2_channel[channel.fullname] = channel
            self._init_done = True

        min_nb_points = None
        for channels_name, channel in self._channel_name_2_channel.items():
            nb_points = len(channel)
            if min_nb_points is None:
                min_nb_points = nb_points
            elif min_nb_points > nb_points:
                min_nb_points = nb_points

        if min_nb_points is None or self._last_point_display >= min_nb_points:
            return

        for point_nb in range(self._last_point_display, min_nb_points):
            values = {
                ch_name: ch.get(point_nb)
                for ch_name, ch in iter(self._channel_name_2_channel.items())
            }

            cb(scan_info, values)

        self._last_point_display = min_nb_points

    def on_scan_end(self, scan_info):

        cb = _SCAN_WATCH_CALLBACKS["end"]()
        if cb is not None:
            cb(scan_info)


class WatchdogCallback:
    """
    This class is a watchdog for scan class.  It's role is to follow
    if detectors involved in the scan have the right behavior. If not
    the callback may raise an exception.
    All exception will bubble-up except StopIteration which will just stop
    the scan.
    """

    def __init__(self, watchdog_timeout=1.0):
        """
        watchdog_timeout -- is the maximum calling frequency of **on_timeout**
        method.
        """
        self.__watchdog_timeout = watchdog_timeout

    @property
    def timeout(self):
        return self.__watchdog_timeout

    def on_timeout(self):
        """
        This method is called when **watchdog_timeout** elapsed it means
        that no data event is received for the time specified by
        **watchdog_timeout**
        """
        pass

    def on_scan_new(self, scan, scan_info):
        """
        Called when scan is starting
        """
        pass

    def on_scan_data(self, data_events, nodes, scan_info):
        """
        Called when new data are emitted by the scan.  This method should
        raise en exception to stop the scan.  All exception will
        bubble-up exception the **StopIteration**.  This one will just
        stop the scan.
        """
        pass

    def on_scan_end(self, scan_info):
        """
        Called at the end of the scan
        """
        pass


class _WatchDogTask(gevent.Greenlet):
    def __init__(self, scan, callback):
        super().__init__()
        self._scan = weakref.proxy(scan, self.stop)
        self._events = gevent.queue.Queue()
        self._data_events = dict()
        self._callback = callback
        self.__watchdog_timer = None
        self._lock = gevent.lock.Semaphore()
        self._lock_watchdog_reset = gevent.lock.Semaphore()

    def trigger_data_event(self, sender, signal):
        self._reset_watchdog()
        event_set = self._data_events.setdefault(sender, set())
        event_set.add(signal)
        if not len(self._events):
            self._events.put("Data Event")

    def on_scan_new(self, scan, scan_info):
        self._callback.on_scan_new(scan, scan_info)
        self._reset_watchdog()

    def on_scan_end(self, scan_info):
        self.stop()
        self._callback.on_scan_end(scan_info)

    def stop(self):
        self.clear_queue()
        self._events.put(StopIteration)

    def kill(self):
        super().kill()
        if self.__watchdog_timer is not None:
            self.__watchdog_timer.kill()

    def clear_queue(self):
        while True:
            try:
                self._events.get_nowait()
            except gevent.queue.Empty:
                break

    def _run(self):
        try:
            for ev in self._events:
                if isinstance(ev, BaseException):
                    raise ev
                try:
                    if self._data_events:
                        data_event = self._data_events
                        self._data_events = dict()
                        # disable the watchdog before calling the callback
                        if self.__watchdog_timer is not None:
                            self.__watchdog_timer.kill()
                        with KillMask():
                            with self._lock:
                                self._callback.on_scan_data(
                                    data_event, self._scan.nodes, self._scan.scan_info
                                )
                        # reset watchdog if it wasn't restarted in between
                        if not self.__watchdog_timer:
                            self._reset_watchdog()

                except StopIteration:
                    break
        finally:
            if self.__watchdog_timer is not None:
                self.__watchdog_timer.kill()

    def _reset_watchdog(self):
        with self._lock_watchdog_reset:
            if self.__watchdog_timer:
                self.__watchdog_timer.kill()

            if self.ready():
                return

            def loop(timeout):
                while True:
                    gevent.sleep(timeout)
                    try:
                        with KillMask():
                            with self._lock:
                                self._callback.on_timeout()
                    except StopIteration:
                        self.stop()
                        break
                    except BaseException as e:
                        self.clear_queue()
                        self._events.put(e)
                        break

            self.__watchdog_timer = gevent.spawn(loop, self._callback.timeout)


class ScanDisplay(ParametersWardrobe):
    SLOTS = []

    def __init__(self, session_name=None):
        """
        This class represents the display parameters for scans for a session.
        """
        if session_name is None:
            session_name = current_session.name

        super().__init__(
            "%s:scan_display_params" % session_name,
            default_values={
                "auto": False,
                "motor_position": True,
                "_extra_args": [],
                "_next_scan_metadata": None,
            },
            property_attributes=("session", "extra_args", "flint_output_enabled"),
            not_removable=("auto", "motor_position"),
        )

        self.add("_session_name", session_name)

    def __dir__(self):
        keys = super().__dir__()
        return keys

    def __repr__(self):
        return super().__repr__()

    @property
    def session(self):
        """ This give the name of the current session or default if no current session is defined """
        return self._session_name

    @property
    def extra_args(self):
        """Returns the list of extra arguments which will be provided to flint
        at it's next creation"""
        return self._extra_args

    @extra_args.setter
    def extra_args(self, extra_args):
        """Set the list of extra arguments to provide to flint at it's
        creation"""
        # FIXME: It could warn to restart flint in case it is already loaded
        if not isinstance(extra_args, (list, tuple)):
            raise TypeError(
                "SCAN_DISPLAY.extra_args expects a list or a tuple of strings"
            )

        # Do not load it while it is not needed
        from argparse import ArgumentParser
        from bliss.flint import config

        # Parse and check flint command line arguments
        parser = ArgumentParser(prog="Flint")
        config.configure_parser_arguments(parser)
        try:
            parser.parse_args(extra_args)
        except SystemExit:
            # Avoid to exit while parsing the arguments
            pass

        self._extra_args = list(extra_args)

    @property
    def flint_output_enabled(self):
        """
        Returns true if the output (strout/stderr) is displayed using the
        logging system.

        This is an helper to display the `disabled` state of the logger
        `flint.output`.
        """
        from bliss.common import plot

        logger = plot.FLINT_OUTPUT_LOGGER
        return not logger.disabled

    @flint_output_enabled.setter
    def flint_output_enabled(self, enabled):
        """
        Enable or disable the display of flint output ((strout/stderr) )
        using the logging system.

        This is an helper to set the `disabled` state of the logger
        `flint.output`.
        """
        from bliss.common import plot

        logger = plot.FLINT_OUTPUT_LOGGER
        logger.disabled = not enabled

    def init_next_scan_meta(self, display: typing.List[str] = None):
        """Register extra information for the next scan."""
        info = self._next_scan_metadata
        if info is None:
            info = {}
        if display is not None:
            info["displayed_channels"] = display
        self._next_scan_metadata = info

    def get_next_scan_channels(self) -> typing.List[str]:
        if self._next_scan_metadata is None:
            return []
        return self._next_scan_metadata["displayed_channels"]

    def pop_scan_meta(self) -> typing.Optional[typing.Dict]:
        """Pop the extra information to feed the scan with."""
        info = self._next_scan_metadata
        self._next_scan_metadata = None
        return info


def _get_channels_dict(acq_object, channels_dict):
    scalars = channels_dict.setdefault("scalars", [])
    scalars_units = channels_dict.setdefault("scalars_units", {})
    spectra = channels_dict.setdefault("spectra", [])
    images = channels_dict.setdefault("images", [])
    display_names = channels_dict.setdefault("display_names", {})

    for acq_chan in acq_object.channels:
        fullname = acq_chan.fullname
        if fullname in display_names:
            continue
        try:
            _, controller_chan_name, chan_name = fullname.split(":")
        except ValueError:
            controller_chan_name, _, chan_name = fullname.rpartition(":")
        display_names[fullname] = (
            controller_chan_name,
            acq_chan.short_name,
        )  # use .name to get alias, if any
        scalars_units[fullname] = acq_chan.unit
        shape = acq_chan.shape
        if len(shape) == 0 and fullname not in scalars:
            scalars.append(fullname)
        elif len(shape) == 1 and fullname not in spectra:
            spectra.append(fullname)
        elif len(shape) == 2 and fullname not in images:
            images.append(fullname)

    return channels_dict


def _get_masters_and_channels(acq_chain):
    # go through acq chain, group acq channels by master and data shape
    tree = acq_chain._tree

    chain_dict = {}
    display_names_list = []
    for path in tree.paths_to_leaves():
        master = None
        # path[0] is root
        for acq_object in path[1:]:
            # it is mandatory to find an acq. master first
            if isinstance(acq_object, AcquisitionMaster):
                if master is None or acq_object.parent is None:
                    master = acq_object.name
                    channels = chain_dict.setdefault(master, {"master": {}})
                    _get_channels_dict(acq_object, channels["master"])
                    display_names_list.append(channels["master"]["display_names"])
                    continue
            _get_channels_dict(acq_object, channels)
            display_names_list.append(channels["display_names"])

    # find channel display labels
    names_count = collections.Counter()
    # eliminate duplicated display_names dict in list
    display_names_list = [
        d
        for i, d in enumerate(display_names_list)
        if d not in display_names_list[i + 1 :]
    ]
    for display_names in display_names_list:
        for controller_chan_name, chan_name in display_names.values():
            if controller_chan_name == chan_name:
                # weird case, but it can happen
                names_count.update([chan_name])
            else:
                names_count.update([controller_chan_name, chan_name])
    for display_names in display_names_list:
        for fullname, (controller_chan_name, chan_name) in display_names.items():
            if names_count[chan_name] == 1:
                # unique short name
                display_names[fullname] = chan_name
            else:
                if names_count[controller_chan_name] == 1:
                    display_names[fullname] = controller_chan_name
                else:
                    display_names[fullname] = fullname

    return chain_dict


class ScanPreset:
    def __init__(self):
        self.__acq_chain = None

    @property
    def acq_chain(self):
        return self.__acq_chain

    def _prepare(self, scan):
        """
        Called on the preparation phase of a scan.
        """
        self.__acq_chain = scan.acq_chain
        self.__new_channel_data = {}
        self.__new_data_callback = None
        return self.prepare(scan)

    def prepare(self, scan):
        """
        Called on the preparation phase of a scan.
        To be overwritten in user scan presets
        """
        pass

    def start(self, scan):
        """
        Called on the starting phase of a scan.
        """
        pass

    def _stop(self, scan):
        if self.__new_channel_data:
            for data_chan in self.__new_channel_data.keys():
                disconnect(data_chan, "new_data", self.__new_channel_data_cb)
        self.__new_data_callback = None
        self.__new_channel_data = {}
        return self.stop(scan)

    def stop(self, scan):
        """
        Called at the end of a scan.
        """
        pass

    def __new_channel_data_cb(self, event_dict, sender=None):
        data = event_dict.get("data")
        if data is None:
            return
        counter = self.__new_channel_data[sender]
        return self.__new_data_callback(counter, sender.fullname, data)

    def connect_data_channels(self, counters_list, callback):
        nodes = self.acq_chain.get_node_from_devices(*counters_list)
        for i, node in enumerate(nodes):
            try:
                channels = node.channels
            except AttributeError:
                continue
            else:
                self.__new_data_callback = callback
                cnt = counters_list[i]
                for data_chan in channels:
                    self.__new_channel_data[data_chan] = cnt
                    connect(data_chan, "new_data", self.__new_channel_data_cb)


class ScanState(enum.IntEnum):
    IDLE = 0
    PREPARING = 1
    STARTING = 2
    STOPPING = 3
    DONE = 4
    USER_ABORTED = 5
    KILLED = 6


class Scan:
    def __init__(
        self,
        chain,
        name="scan",
        scan_info=None,
        save=True,
        save_images=None,  # None means follows "save"
        scan_saving=None,
        data_watch_callback=None,
        watchdog_callback=None,
    ):
        """
        This class publish data and trig the writer if any.

        chain -- acquisition chain you want to use for this scan.
        name -- scan name, if None set default name *scan*
        parent -- the parent is the root node of the data tree.
        usually the parent is a Container like to a session,sample,experiment...
        i.e: parent = Container('eh3')
        scan_info -- should be the scan parameters as a dict
        writer -- is the final file writer (hdf5,cvs,spec file...)
        data_watch_callback -- a callback inherited from DataWatchCallback
        """
        self.__name = name
        self.__scan_number = None
        self.root_node = None
        self._scan_info = dict(scan_info) if scan_info is not None else dict()

        if scan_saving is None:
            scan_saving = ScanSaving(current_session.name)
        session_name = scan_saving.session
        user_name = scan_saving.user_name
        self.__scan_saving = scan_saving
        scan_config = scan_saving.get()

        self._scan_info["save"] = save
        self._scan_info["data_writer"] = scan_saving.writer
        self._scan_info["data_policy"] = scan_saving.data_policy
        self._scan_info["publisher"] = "Bliss"
        self._scan_info["publisher_version"] = publisher_version
        if save:
            self.__writer = scan_config["writer"]
        else:
            self.__writer = NullWriter(
                scan_config["root_path"],
                scan_config["images_path"],
                os.path.basename(scan_config["data_path"]),
            )
        self.__writer._save_images = save if save_images is None else save_images
        # Double buffer pipeline for streams store
        self._stream_pipeline_lock = gevent.lock.Semaphore()
        self._stream_pipeline_task = None
        self._current_pipeline_stream = None
        ### make channel names unique in the scope of the scan
        def check_acq_chan_unique_name(acq_chain):
            channels = []

            for n in acq_chain._tree.is_branch(acq_chain._tree.root):
                uniquify_chan_name(acq_chain, n, channels)

        def uniquify_chan_name(acq_chain, node, channels):
            # TODO: check if name or fullname should be used below
            if node.channels:
                for c in node.channels:
                    if c.name in channels:
                        if acq_chain._tree.get_node(node).bpointer:
                            new_name = (
                                acq_chain._tree.get_node(node).bpointer.name
                                + ":"
                                + c.name
                            )
                        else:
                            new_name = c.name
                        if new_name in channels:
                            new_name = str(id(c)) + ":" + c.name
                        c._AcquisitionChannel__name = new_name
                    channels.append(c.name)

            for n in acq_chain._tree.is_branch(node):
                uniquify_chan_name(acq_chain, n, channels)

        check_acq_chan_unique_name(chain)

        self.__nodes = dict()
        self._devices = []

        self._scan_info["session_name"] = session_name
        self._scan_info["user_name"] = user_name
        self._scan_info.setdefault("title", name)

        self._data_watch_task = None
        self._data_watch_callback = data_watch_callback
        self._data_events = dict()
        self.set_watchdog_callback(watchdog_callback)
        self._acq_chain = chain
        self._scan_info["acquisition_chain"] = _get_masters_and_channels(
            self._acq_chain
        )

        if is_bliss_shell():
            scan_display = ScanDisplay()
            if scan_display.auto:
                if self.is_flint_recommended():
                    get_flint()

        self.__state = ScanState.IDLE
        self.__state_change = gevent.event.Event()
        self._preset_list = list()
        self.__node = None
        self.__comments = list()  # user comments
        self._exception = None

    def is_flint_recommended(self):
        """Return true if flint is recommended for this scan"""
        scan_info = self._scan_info
        if scan_info["type"] == "ct":
            chain = scan_info["acquisition_chain"]
            ndim_data = []
            for _top_master, chain in scan_info["acquisition_chain"].items():
                ndim_data.extend(chain.get("images", []))
                ndim_data.extend(chain.get("spectra", []))
                ndim_data.extend(chain.get("master", {}).get("images", []))
                ndim_data.extend(chain.get("master", {}).get("spectra", []))
            # Flint is only recommended if there is MCAs or images
            return len(ndim_data) > 0

        return True

    def _create_data_node(self, node_name):
        self.__node = _create_node(
            node_name, "scan", parent=self.root_node, info=self._scan_info
        )

    def _prepare_node(self):
        if self.__node is None:
            self.root_node = self.__scan_saving.get_parent_node()

            ### order is important in the next lines...
            self.writer.template.update(
                {
                    "scan_name": self.name,
                    "session": self.__scan_saving.session,
                    "scan_number": "{scan_number}",
                }
            )

            self.__scan_number = self._next_scan_number()

            self.writer.template["scan_number"] = self.scan_number
            self._scan_info["scan_nb"] = self.__scan_number

            # this has to be done when the writer is ready
            self._prepare_scan_meta()

            start_timestamp = time.time()
            start_time = datetime.datetime.fromtimestamp(start_timestamp)
            self._scan_info["start_time"] = start_time
            start_time_str = start_time.strftime("%a %b %d %H:%M:%S %Y")
            self._scan_info["start_time_str"] = start_time_str
            self._scan_info["start_timestamp"] = start_timestamp

            node_name = str(self.__scan_number) + "_" + self.name
            self._create_data_node(node_name)
            self._current_pipeline_stream = self.root_node.db_connection.pipeline()
            self._pending_watch_callback = weakref.WeakKeyDictionary()

    def __repr__(self):
        return "Scan(number={}, name={}, path={})".format(
            self.__scan_number, self.name, self.writer.filename
        )

    @property
    def name(self):
        return self.__name

    @property
    def state(self):
        return self.__state

    @property
    def writer(self):
        return self.__writer

    @property
    def node(self):
        return self.__node

    @property
    def nodes(self):
        return self.__nodes

    @property
    def acq_chain(self):
        return self._acq_chain

    @property
    def scan_info(self):
        return self._scan_info

    @property
    def scan_number(self):
        if self.__scan_number:
            return self.__scan_saving.scan_number_format % self.__scan_number
        else:
            return "{scan_number}"

    @property
    def statistics(self):
        return Statistics(self._acq_chain._stats_dict)

    def get_plot(
        self, channel_item, plot_type, as_axes=False, wait=False, silent=False
    ):
        warnings.warn(
            "Scan.get_plot is deprecated, use bliss.common.plot.get_plot instead",
            DeprecationWarning,
        )
        return get_plot(
            channel_item,
            plot_type,
            scan=self,
            as_axes=as_axes,
            wait=wait,
            silent=silent,
        )

    @property
    def get_channels_dict(self):
        """
        returns a dict containing all channels used in this scan 
        identified by their fullname
        """
        flatten = lambda l: [item for sublist in l for item in sublist]

        return {
            c.name: c for c in flatten([n.channels for n in self.acq_chain.nodes_list])
        }

    def add_preset(self, preset):
        """
        Add a preset for this scan
        """
        if not isinstance(preset, ScanPreset):
            raise ValueError("Expected ScanPreset instance")
        self._preset_list.append(preset)

    def set_watchdog_callback(self, callback):
        """
        Set a watchdog callback for this scan
        """
        if callback:
            self._watchdog_task = _WatchDogTask(self, callback)
        else:
            self._watchdog_task = None

    def _get_data_axes_name(self):
        """
        Return all axes in this scan
        """
        acq_chain = self._scan_info["acquisition_chain"]
        master_axes = []
        for top_level_master in acq_chain.keys():
            for scalar_master in acq_chain[top_level_master]["master"]["scalars"]:
                ma = scalar_master.split(":")[-1]
                if ma in self._scan_info["positioners"]["positioners_start"]:
                    master_axes.append(ma)

        if len(master_axes) == 0:
            if self._scan_info.get("type") == "timescan":
                return ["elapsed_time"]
            else:
                raise RuntimeError("No axis detected in scan.")
        return master_axes

    def update_ctrl_params(self, ctrl, new_param_dict):
        if self.state != ScanState.IDLE:
            raise RuntimeError(
                "Scan state is not idle. ctrl_params can only be updated before scan starts running."
            )
        ctrl_acq_dev = None
        for acq_dev in self.acq_chain.nodes_list:
            if ctrl is acq_dev.device:
                ctrl_acq_dev = acq_dev
                break
        if ctrl_acq_dev is None:
            raise RuntimeError(f"Controller {ctrl} not part of this scan!")

        ## for Bliss 2 we have to see how to make acq_params available systematically
        potential_new_ctrl_params = ctrl_acq_dev.ctrl_params.copy()
        potential_new_ctrl_params.update(new_param_dict)

        # invoking the Validator here will only work if we have a
        # copy of initial acq_params in the acq_obj
        # ~ if hasattr(ctrl_acq_dev, "acq_params"):
        # ~ potential_new_ctrl_params = CompletedCtrlParamsDict(
        # ~ potential_new_ctrl_params
        # ~ )
        # ~ ctrl_acq_dev.validate_params(
        # ~ ctrl_acq_dev.acq_params, ctrl_params=potential_new_ctrl_params
        # ~ )

        # at least check that no new keys are added
        if set(potential_new_ctrl_params.keys()) == set(
            ctrl_acq_dev.ctrl_params.keys()
        ):
            ctrl_acq_dev.ctrl_params.update(new_param_dict)
        else:
            raise RuntimeError(f"New keys can not be added to ctrl_params of {ctrl}")

    def _get_x_y_data(self, counter, axis):
        data = self.get_data()
        x_data = data[axis]
        y_data = data[counter]
        return x_data, y_data

    def fwhm(self, counter, axis=None, return_axes=False):
        return self._multimotors(self._fwhm, counter, axis, return_axes=return_axes)

    def _fwhm(self, counter, axis=None):
        return round(
            scan_math.cen(*self._get_x_y_data(counter, axis))[1],
            precision=axis.tolerance,
        )

    def peak(self, counter, axis=None, return_axes=False):
        return self._multimotors(self._peak, counter, axis, return_axes=return_axes)

    def _peak(self, counter, axis):
        return scan_math.peak(*self._get_x_y_data(counter, axis))

    def com(self, counter, axis=None, return_axes=False):
        return self._multimotors(self._com, counter, axis, return_axes=return_axes)

    def _com(self, counter, axis):
        return round(
            scan_math.com(*self._get_x_y_data(counter, axis)), precision=axis.tolerance
        )

    def cen(self, counter, axis=None, return_axes=False):
        return self._multimotors(self._cen, counter, axis, return_axes=return_axes)

    def _cen(self, counter, axis):
        return round(
            scan_math.cen(*self._get_x_y_data(counter, axis))[0],
            precision=axis.tolerance,
        )

    def _multimotors(self, func, counter, axis=None, return_axes=False):
        axes_names = self._get_data_axes_name()
        res = collections.UserDict()

        def info():
            """TODO: could be a nice table at one point"""
            s = "{"
            for key, value in res.items():
                if len(s) != 1:
                    s += ", "
                s += f"{key.name}: {value}"
            s += "}"
            return s

        res.__info__ = info

        if axis is not None:
            if isinstance(axis, str):
                assert axis in axes_names or "epoch" in axis or "elapsed_time" in axis
            else:
                assert axis.name in axes_names
            res[axis] = func(counter, axis=axis)
        elif len(axes_names) == 1 and (
            "elapsed_time" in axes_names or "epoch" in axes_names
        ):
            res = {axis: func(counter, axis=axes_names[0])}
        else:
            ##ToDo: does this work for SoftAxis (not always exported)?
            motors = [current_session.env_dict[axis_name] for axis_name in axes_names]
            if len(motors) < 1:
                raise
            # check if there is some calcaxis with associated real
            motors = remove_real_dependent_of_calc(motors)
            for mot in motors:
                res[mot] = func(counter, axis=mot)

        if not return_axes and len(res) == 1:
            return next(iter(res.values()))
        else:
            return res

    def _goto_multimotors(self, goto):
        for key in goto.keys():
            assert not isinstance(key, str)
        with error_cleanup(
            *goto.keys(), restore_list=(cleanup_axis.POS,), verbose=True
        ):
            tasks = [gevent.spawn(mot.move, pos) for mot, pos in goto.items()]
            try:
                gevent.joinall(tasks, raise_error=True)
            finally:
                gevent.killall(tasks)

    def goto_peak(self, counter, axis=None):
        return self._goto_multimotors(self.peak(counter, axis, return_axes=True))

    def goto_com(self, counter, axis=None, return_axes=False):
        return self._goto_multimotors(self.com(counter, axis, return_axes=True))

    def goto_cen(self, counter, axis=None, return_axes=False):
        return self._goto_multimotors(self.cen(counter, axis, return_axes=True))

    def wait_state(self, state):
        while self.__state < state:
            self.__state_change.clear()
            self.__state_change.wait()

    def __trigger_data_watch_callback(self, signal, sender, sync=False):
        if self._data_watch_callback is not None:
            event_set = self._data_events.setdefault(sender, set())
            event_set.add(signal)
            if sync:
                data_events = self._data_events
                self._data_events = dict()
                while self._data_watch_running and not self._data_watch_task.ready():
                    self._data_watch_callback_done.wait()
                    self._data_watch_callback_done.clear()
                self._scan_info["state"] = self.__state
                self._data_watch_callback.on_scan_data(
                    data_events, self.nodes, self._scan_info
                )
            else:
                self._data_watch_callback_event.set()
        if self._watchdog_task is not None:
            self._watchdog_task.trigger_data_event(sender, signal)

    def _channel_event(self, event_dict, signal=None, sender=None):
        with KillMask():
            with self._stream_pipeline_lock:
                self.nodes[sender].store(event_dict, cnx=self._current_pipeline_stream)
                pending = self._pending_watch_callback.setdefault(
                    self._current_pipeline_stream, list()
                )
                pending.append((signal, sender))
        self._swap_pipeline()

    def _pipeline_execute(self, pipeline, trigger_func):
        while True:
            try:
                pipeline.execute()
                for event in self._pending_watch_callback.get(pipeline, list()):
                    trigger_func(*event)
            except:
                raise
            else:
                if not len(self._current_pipeline_stream):
                    break
                new_pipeline = self.root_node.db_connection.pipeline()
                pipeline = self._current_pipeline_stream
                self._current_pipeline_stream = new_pipeline

    def _swap_pipeline(self):
        with self._stream_pipeline_lock:
            if not self._stream_pipeline_task and len(self._current_pipeline_stream):
                if self._stream_pipeline_task is not None:
                    # raise error in case of problem
                    self._stream_pipeline_task.get()

                task = gevent.spawn(
                    self._pipeline_execute,
                    self._current_pipeline_stream,
                    self.__trigger_data_watch_callback,
                )

                self._stream_pipeline_task = task
                self._current_pipeline_stream = self.root_node.db_connection.pipeline()
            return self._stream_pipeline_task

    def set_ttl(self):
        for node in self.nodes.values():
            node.set_ttl()
        self.node.set_ttl()

    def _device_event(self, event_dict=None, signal=None, sender=None):
        if signal == "end":
            task = self._swap_pipeline()
            if task is not None:
                task.join()
            self.__trigger_data_watch_callback(signal, sender, sync=True)

    def _prepare_channels(self, channels, parent_node):
        for channel in channels:
            chan_name = channel.short_name
            self.nodes[channel] = _get_or_create_node(
                chan_name,
                channel.data_node_type,
                parent_node,
                shape=channel.shape,
                dtype=channel.dtype,
                unit=channel.unit,
                fullname=channel.fullname,
            )
            channel.data_node = self.nodes[channel]
            connect(channel, "new_data", self._channel_event)

    def prepare(self, scan_info, devices_tree):
        self.__nodes = dict()
        self._devices = list(devices_tree.expand_tree())[1:]

        for dev in self._devices:
            dev_node = devices_tree.get_node(dev)
            level = devices_tree.depth(dev_node)
            if level == 1:
                parent_node = self.node
            else:
                parent_node = self.nodes[dev_node.bpointer]
            if isinstance(dev, (AcquisitionSlave, AcquisitionMaster)):
                data_container_node = _create_node(dev.name, parent=parent_node)
                self.nodes[dev] = data_container_node
                self._prepare_channels(dev.channels, data_container_node)

                for signal in ("start", "end"):
                    connect(dev, signal, self._device_event)

        self.writer.prepare(self)

    def _prepare_scan_meta(self):
        self._scan_info["filename"] = self.writer.filename
        self.user_scan_meta = get_user_scan_meta().copy()
        with KillMask(masked_kill_nb=1):
            deep_update(self._scan_info, self.user_scan_meta.to_dict(self))
        self._scan_info["scan_meta_categories"] = self.user_scan_meta.cat_list()

    def disconnect_all(self):
        for dev in self._devices:
            if isinstance(dev, (AcquisitionSlave, AcquisitionMaster)):
                for channel in dev.channels:
                    disconnect(channel, "new_data", self._channel_event)
                for signal in ("start", "end"):
                    disconnect(dev, signal, self._device_event)
        self._devices = []

    def run(self):
        with lprint_disable():
            return self._run()

    def _run(self):
        if self.state != ScanState.IDLE:
            raise RuntimeError(
                "Scan state is not idle. Scan objects can only be used once."
            )
        killed = False
        killed_by_user = False
        call_on_prepare, call_on_stop = False, False
        set_watch_event = None

        ### create scan node in redis
        self._prepare_node()

        if self._data_watch_callback is not None:
            data_watch_callback_event = gevent.event.Event()
            data_watch_callback_done = gevent.event.Event()

            def trig(*args):
                data_watch_callback_event.set()

            self._data_watch_running = False
            self._data_watch_task = gevent.spawn(
                Scan._data_watch,
                weakref.proxy(self, trig),
                data_watch_callback_event,
                data_watch_callback_done,
            )
            self._data_watch_callback_event = data_watch_callback_event
            self._data_watch_callback_done = data_watch_callback_done

            if hasattr(self._data_watch_callback, "on_state"):
                call_on_prepare = self._data_watch_callback.on_state(
                    ScanState.PREPARING
                )
                call_on_stop = self._data_watch_callback.on_state(ScanState.STOPPING)

            set_watch_event = self._data_watch_callback_event.set

        self.acq_chain.reset_stats()

        try:
            if self._data_watch_callback:
                self._data_watch_callback.on_scan_new(self, self.scan_info)
            if self._watchdog_task is not None:
                self._watchdog_task.start()
                self._watchdog_task.on_scan_new(self, self.scan_info)

            current_iters = [next(i) for i in self.acq_chain.get_iter_list()]

            # ---- apply parameters
            apply_parameters_tasks = [
                gevent.spawn(i.apply_parameters) for i in current_iters
            ]
            try:
                gevent.joinall(apply_parameters_tasks, raise_error=True)
            except:
                gevent.killall(apply_parameters_tasks)
                raise
            # -----

            self.__state = ScanState.PREPARING
            self.__state_change.set()
            with periodic_exec(0.1 if call_on_prepare else 0, set_watch_event):
                self._execute_preset("_prepare")
                self.prepare(self.scan_info, self.acq_chain._tree)
                prepare_tasks = [
                    gevent.spawn(i.prepare, self, self.scan_info) for i in current_iters
                ]
                try:
                    gevent.joinall(prepare_tasks, raise_error=True)
                except:
                    gevent.killall(prepare_tasks)
                    raise
            for dev in self.acq_chain.nodes_list:
                with KillMask(masked_kill_nb=1):
                    tmp = dev.fill_meta_at_scan_start(self.user_scan_meta)
                if tmp:
                    update_node_info(self.nodes[dev], tmp)

            self.__state = ScanState.STARTING
            self.__state_change.set()
            self._execute_preset("start")
            run_next_tasks = [
                (gevent.spawn(self._run_next, i), i) for i in current_iters
            ]
            run_scan = True

            with capture_exceptions(raise_index=0) as capture:
                with capture():
                    kill_exception = StopChain
                    try:
                        while run_scan:
                            # The master defined as 'terminator' ends the loop
                            # (by default any top master will stop the loop),
                            # the loop is also stopped in case of exception.
                            wait_tasks = [t for t, _ in run_next_tasks]
                            if self._watchdog_task is not None:
                                wait_tasks += [self._watchdog_task]
                            gevent.joinall(wait_tasks, raise_error=True, count=1)
                            if self._watchdog_task is not None:
                                # stop the scan if watchdog_task end normally
                                # it received a StopIteration
                                run_scan = not self._watchdog_task.ready()

                            if not run_scan:
                                break

                            for task, iterator in run_next_tasks:
                                if task.ready():
                                    if iterator.top_master.terminator:
                                        # scan has to end
                                        run_scan = False
                                        break
                            else:
                                run_next_tasks = [
                                    (t, i) for t, i in run_next_tasks if not t.ready()
                                ]
                                run_scan = bool(run_next_tasks)
                    except BaseException as e:
                        kill_exception = gevent.GreenletExit
                        killed = True
                        killed_by_user = isinstance(e, KeyboardInterrupt)
                        raise
                    finally:
                        gevent.killall(
                            [t for t, _ in run_next_tasks], exception=kill_exception
                        )

                self.__state = ScanState.STOPPING
                self.__state_change.set()

                with periodic_exec(0.1 if call_on_stop else 0, set_watch_event):
                    stop_task = [
                        gevent.spawn(i.stop) for i in current_iters if i is not None
                    ]
                    with capture():
                        try:
                            gevent.joinall(stop_task, raise_error=True)
                        except BaseException as e:
                            with KillMask(masked_kill_nb=1):
                                gevent.joinall(stop_task)
                            gevent.killall(stop_task)
                            killed = True
                            killed_by_user = isinstance(e, KeyboardInterrupt)
                            raise
        except Exception as e:
            self._exception = e
            killed = True
            killed_by_user = isinstance(e, KeyboardInterrupt)
            raise
        finally:
            with capture_exceptions(raise_index=0) as capture:
                with capture():
                    # check if there is any master or device that would like
                    # to provide meta data at the end of the scan
                    for dev in self.acq_chain.nodes_list:
                        node = self.nodes.get(dev)
                        if node is None:
                            # prepare has not finished ?
                            continue
                        with KillMask(masked_kill_nb=1):
                            tmp = dev.fill_meta_at_scan_end(self.user_scan_meta)
                        if tmp:
                            update_node_info(node, tmp)

                    with KillMask(masked_kill_nb=1):
                        deep_update(self._scan_info, self.user_scan_meta.to_dict(self))
                        self._scan_info[
                            "scan_meta_categories"
                        ] = self.user_scan_meta.cat_list()

                        # update scan_info in redis
                        self.node._info.update(self.scan_info)

                # wait the end of publishing
                # (should be already finished)
                stream_task = self._swap_pipeline()
                if stream_task is not None:
                    with capture():
                        stream_task.get()
                self._current_pipeline_stream = None
                # Store end event before setting the ttl
                self.node.end(exception=self._exception)

                self._scan_info["end_time"] = self.node.info["end_time"]
                self._scan_info["end_time_str"] = self.node.info["end_time_str"]
                self._scan_info["end_timestamp"] = self.node.info["end_timestamp"]

                with capture():
                    self.set_ttl()

                # Close nodes
                for node in self.nodes.values():
                    try:
                        node.close()
                    except AttributeError:
                        pass
                # Disconnect events
                self.disconnect_all()

                # put state to KILLED if needed
                if not killed:
                    self.__state = ScanState.DONE
                elif killed_by_user:
                    self.__state = ScanState.USER_ABORTED
                else:
                    self.__state = ScanState.KILLED
                self.__state_change.set()
                self.node.info["state"] = self.__state
                self._scan_info["state"] = self.__state

                # Add scan to the globals
                current_session.scans.append(self)

                if self.writer:
                    # write scan_info to file
                    with capture():
                        self.writer.finalize_scan_entry(self)
                    with capture():
                        self.writer.close()

                with capture():
                    if self._data_watch_callback:
                        self._data_watch_callback.on_scan_end(self.scan_info)
                with capture():
                    if self._watchdog_task is not None:
                        self._watchdog_task.kill()
                        self._watchdog_task.on_scan_end(self.scan_info)
                with capture():
                    # Kill data watch task
                    if self._data_watch_task is not None:
                        if (
                            self._data_watch_task.ready()
                            and not self._data_watch_task.successful()
                        ):
                            self._data_watch_task.get()
                        self._data_watch_task.kill()

                self._execute_preset("_stop")

    def _run_next(self, next_iter):
        next_iter.start()
        for i in next_iter:
            i.prepare(self, self.scan_info)
            i.start()

    def add_comment(self, comment):
        """
        Adds a comment (string + timestamp) to scan_info that will also be 
        saved in the file data file together with the scan 
        """
        assert type(comment) == str

        if self.__state < ScanState.DONE:
            self.__comments.append({"timestamp": time.time(), "message": comment})
            self._scan_info["comments"] = self.__comments
            if self.__state > ScanState.IDLE:
                self.node._info.update({"comments": self.__comments})
        else:
            raise RuntimeError(
                "Comments can only be added to scans that have not terminated!"
            )

    @property
    def comments(self):
        """
        list of comments that have been attacht to this scan by the user
        """
        return self.__comments

    @staticmethod
    def _data_watch(scan, event, event_done):
        while True:
            event.wait()
            event.clear()
            try:
                data_events = scan._data_events
                scan._data_events = dict()
                scan._data_watch_running = True
                scan.scan_info["state"] = scan.state
                scan._data_watch_callback.on_scan_data(
                    data_events, scan.nodes, scan.scan_info
                )
                scan._data_watch_running = False
            except ReferenceError:
                break
            else:
                event_done.set()

    def get_data(self):
        """Return a numpy array with the scan data.

        It is a 1D array corresponding to the scan points.
        Each point is a named structure corresponding to the counter names.
        """
        return get_data(self)

    def _next_scan_number(self):
        LAST_SCAN_NUMBER = "last_scan_number"
        filename = self.writer.filename
        # last scan number is stored in the parent of the scan
        parent_node = self.__scan_saving.get_parent_node()
        last_scan_number = parent_node.connection.hget(
            parent_node.db_name, LAST_SCAN_NUMBER
        )
        if last_scan_number is None and "{scan_number}" not in filename:
            max_scan_number = 0
            for scan_entry in self.writer.get_scan_entries():
                try:
                    # TODO: this has to be removed when internal hdf5 writer
                    # is deprecated
                    max_scan_number = max(
                        int(scan_entry.split("_")[0]), max_scan_number
                    )
                except ValueError:
                    # the following is the good code for the Nexus writer
                    try:
                        max_scan_number = max(
                            int(scan_entry.split(".")[0]), max_scan_number
                        )
                    except Exception:
                        continue
            name = parent_node.db_name
            with pipeline(parent_node._struct) as p:
                p.hsetnx(name, LAST_SCAN_NUMBER, max_scan_number)
                p.hincrby(name, LAST_SCAN_NUMBER, 1)
                _, scan_number = p.execute()
        else:
            cnx = parent_node.connection
            scan_number = cnx.hincrby(parent_node.db_name, LAST_SCAN_NUMBER, 1)
        return scan_number

    def _execute_preset(self, method_name):
        preset_tasks = [
            gevent.spawn(getattr(preset, method_name), self)
            for preset in self._preset_list
        ]
        try:
            gevent.joinall(preset_tasks, raise_error=True)
        except:
            gevent.killall(preset_tasks)
            raise
