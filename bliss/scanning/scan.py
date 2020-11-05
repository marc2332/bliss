# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import enum
import gevent
import gevent.lock
import os
import weakref
import sys
import time
import datetime
import collections
import warnings
from typing import Callable, Any
import typeguard
import logging
import numpy

from bliss.common.types import _countable
from bliss import current_session, is_bliss_shell
from bliss.common.event import connect, disconnect
from bliss.common.cleanup import error_cleanup, axis as cleanup_axis, capture_exceptions
from bliss.common.greenlet_utils import KillMask
from bliss.common.plot import get_flint
from bliss.common.utils import periodic_exec, deep_update
from bliss.scanning.scan_meta import get_user_scan_meta
from bliss.common.motor_group import is_motor_group
from bliss.common.utils import Null, update_node_info, round
from bliss.common.profiling import SimpleTimeStatistics
from bliss.common.profiling import simple_time_profile as time_profile
from bliss.controllers.motor import Controller
from bliss.config.settings_cache import CacheConnection
from bliss.data.node import _get_or_create_node, _create_node
from bliss.data.scan import get_data
from bliss.scanning.chain import AcquisitionSlave, AcquisitionMaster, StopChain
from bliss.scanning.writer.null import Writer as NullWriter
from bliss.scanning import scan_math
from bliss.common.logtools import disable_user_output
from louie import saferef
from bliss.common.plot import get_plot
from bliss import __version__ as publisher_version


logger = logging.getLogger("bliss.scans")


# STORE THE CALLBACK FUNCTIONS THAT ARE CALLED DURING A SCAN ON THE EVENTS SCAN_NEW, SCAN_DATA, SCAN_END
# THIS FUNCTIONS ARE EXPECTED TO PRINT INFO ABOUT THE SCAN AT THE CONSOLE LEVEL (see bliss/shell/cli/repl => ScanPrinter )
# USERS CAN OVERRIDE THE DEFAULT TO SPECIFY ITS OWN SCAN INFO DISPLAY
# BY DEFAULT THE CALLBACKS ARE SET TO NULL() TO AVOID UNNECESSARY PRINTS OUTSIDE A SHELL CONTEXT
_SCAN_WATCH_CALLBACKS = {"new": Null(), "data": Null(), "end": Null()}


class ScanAbort(BaseException):
    pass


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


def is_zerod(node):
    return node.type == "channel" and len(node.shape) == 0


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

            ## Replace the channel name by the controller name if not unique
            # if names_count[chan_name] == 1:
            #     # unique short name
            #     display_names[fullname] = chan_name
            # else:
            #     if names_count[controller_chan_name] == 1:
            #         display_names[fullname] = controller_chan_name
            #     else:
            #         display_names[fullname] = fullname

            display_names[fullname] = chan_name

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


class _ScanIterationsRunner:
    """Helper class to execute iterations of a scan
    
    Uses a generator to execute the different steps, as it receives tasks via 'send'
    """

    def __init__(
        self,
        data_watch_event,
        data_watch_call_on_prepare=False,
        data_watch_call_on_stop=False,
    ):
        self.data_watch_event = data_watch_event
        self.data_watch_call_on_prepare = data_watch_call_on_prepare
        self.data_watch_call_on_stop = data_watch_call_on_stop
        self.runner = self._run()  # make generator
        next(self.runner)  # "prime" runner: go to first yield

    def _gwait(self, greenlets, masked_kill_nb=0):
        """Wait until given greenlets are all done

        In case of error, greenlets are all killed and exception is raised
        
        If a kill happens (GreenletExit or KeyboardInterrupt exception)
        while waiting for greenlets, wait is retried - 'masked_kill_nb'
        allow to specify a number of 'kills' to mask to really kill only
        if it insists.
        """
        try:
            gevent.joinall(greenlets, raise_error=True)
        except (gevent.GreenletExit, KeyboardInterrupt):
            # in case of kill: give a chance to finish the task,
            # but if it insists => let it kill
            if masked_kill_nb > 0:
                with KillMask(masked_kill_nb=masked_kill_nb):
                    gevent.joinall(greenlets)
            raise
        finally:
            if any(
                greenlets
            ):  # only kill if some greenlets are still running, as killall takes time
                gevent.killall(greenlets)

    def _run_next(self, scan, next_iter):
        next_iter.start()
        for i in next_iter:
            i.prepare(scan, scan.scan_info)
            i.start()

    def send(self, arg):
        """Delegate 'arg' to generator"""
        try:
            return self.runner.send(arg)
        except StopIteration:
            pass

    def _run(self):
        """Generator that runs a scan: from applying parameters to acq. objects then preparing and up to stopping

        Goes through the different steps by receiving tasks from the caller Scan object
        """
        apply_parameters_tasks = yield

        # apply parameters in parallel on all iterators
        self._gwait(apply_parameters_tasks)

        # execute prepare tasks in parallel
        prepare_tasks = yield
        with periodic_exec(
            0.1 if self.data_watch_call_on_prepare else 0, self.data_watch_event.set
        ):
            self._gwait(prepare_tasks)

        # scan tasks
        scan, chain_iterators, watchdog_task = yield
        tasks = {gevent.spawn(self._run_next, scan, i): i for i in chain_iterators}
        if watchdog_task is not None:
            # put watchdog task in list, but there is no corresponding iterator
            tasks[watchdog_task] = None

        with capture_exceptions(raise_index=0) as capture:
            with capture():
                try:
                    # gevent.iwait iteratively yield objects as they are ready
                    with gevent.iwait(tasks) as task_iter:
                        # loop over ready tasks until all are consumed, or an
                        # exception is raised
                        for t in task_iter:
                            t.get()  # get the task result ; this may raise an exception

                            if t is watchdog_task:
                                # watchdog task ended: stop the scan
                                raise StopChain
                            elif tasks[t].top_master.terminator:
                                # a task with a terminator top master has finished:
                                # scan has to end
                                raise StopChain
                except StopChain:
                    # stop scan:
                    # kill all tasks, but do not raise an exception
                    gevent.killall(tasks, exception=StopChain)
                except (gevent.GreenletExit, KeyboardInterrupt):
                    # scan gets killed:
                    # kill all tasks, re-raise exception
                    gevent.killall(tasks, exception=gevent.GreenletExit)
                    raise
                except BaseException:
                    # an error occured: kill all tasks, re-raise exception
                    gevent.killall(tasks, exception=StopChain)
                    raise

            stop_tasks = yield
            with capture():
                with periodic_exec(
                    0.1 if self.data_watch_call_on_stop else 0,
                    self.data_watch_event.set,
                ):
                    self._gwait(stop_tasks, masked_kill_nb=1)


class Scan:
    SCAN_NUMBER_LOCK = gevent.lock.Semaphore()

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
        self._cache_cnx = None
        self._shadow_scan_number = not save
        self._add_to_scans_queue = not (name == "ct" and self._shadow_scan_number)

        # Double buffer pipeline for streams store
        self._stream_pipeline_lock = gevent.lock.Semaphore()
        self._stream_pipeline_task = None
        self._current_pipeline_stream = None

        self.__nodes = dict()
        self._devices = []

        self._data_watch_task = None
        self._data_watch_callback = data_watch_callback
        self._data_watch_callback_event = gevent.event.Event()
        self._data_watch_callback_done = gevent.event.Event()
        self._data_events = dict()
        self.set_watchdog_callback(watchdog_callback)

        self.__state = ScanState.IDLE
        self.__state_change = gevent.event.Event()
        self._preset_list = list()
        self.__node = None
        self.__comments = list()  # user comments

        # Scan initialization:
        self._init_acq_chain(chain)
        self._init_scan_saving(scan_saving)
        self._init_scan_display()
        self._init_scan_info(scan_info=scan_info, save=save)
        self._init_writer(save=save, save_images=save_images)
        self._init_flint()

    def _init_scan_saving(self, scan_saving):
        with time_profile(self._stats_dict, "scan.init.saving", logger=logger):
            if scan_saving is None:
                scan_saving = current_session.scan_saving
            self.__scan_saving = scan_saving.clone()

    def _init_scan_display(self):
        with time_profile(self._stats_dict, "scan.init.display", logger=logger):
            self.__scan_display = current_session.scan_display.clone()

    def _init_acq_chain(self, chain):
        """Initialize acquisition chain"""
        chain.reset_stats()
        self._acq_chain = chain
        with time_profile(self._stats_dict, "scan.init.chain", logger=logger):
            self._check_acq_chan_unique_name()

    def _check_acq_chan_unique_name(self):
        """Make channel names unique in the scope of the scan"""
        names = []
        for node in self._acq_chain._tree.is_branch(self._acq_chain._tree.root):
            self._uniquify_chan_name(node, names)

    def _uniquify_chan_name(self, node, names):
        """Change the node's channel names in case of collision"""
        if node.channels:
            for c in node.channels:
                if c.name in names:
                    if self._acq_chain._tree.get_node(node).bpointer:
                        new_name = (
                            self._acq_chain._tree.get_node(node).bpointer.name
                            + ":"
                            + c.name
                        )
                    else:
                        new_name = c.name
                    if new_name in names:
                        new_name = str(id(c)) + ":" + c.name
                    c._AcquisitionChannel__name = new_name
                names.append(c.name)

        for node in self._acq_chain._tree.is_branch(node):
            self._uniquify_chan_name(node, names)

    def _init_scan_info(self, scan_info=None, save=True):
        """Initialize `scan_info`"""
        with time_profile(self._stats_dict, "scan.init.scan_info", logger=logger):
            self._scan_info = dict(scan_info) if scan_info is not None else dict()
            scan_saving = self.__scan_saving
            self._scan_info.setdefault("title", self.__name)
            self._scan_info["session_name"] = scan_saving.session
            self._scan_info["user_name"] = scan_saving.user_name
            self._scan_info["shadow_scan_number"] = self._shadow_scan_number
            self._scan_info["save"] = save
            self._scan_info["data_writer"] = scan_saving.writer
            self._scan_info["data_policy"] = scan_saving.data_policy
            self._scan_info["publisher"] = "Bliss"
            self._scan_info["publisher_version"] = publisher_version
            self._scan_info["acquisition_chain"] = _get_masters_and_channels(
                self._acq_chain
            )

    def _init_writer(self, save=True, save_images=None):
        """Initialize the data writer if needed"""
        with time_profile(self._stats_dict, "scan.init.writer", logger=logger):
            scan_config = self.__scan_saving.get()
            if save:
                self.__writer = scan_config["writer"]
            else:
                self.__writer = NullWriter(
                    scan_config["root_path"],
                    scan_config["images_path"],
                    os.path.basename(scan_config["data_path"]),
                )
            self.__writer._save_images = save if save_images is None else save_images

    def _init_flint(self):
        """Initialize flint if needed"""
        with time_profile(self._stats_dict, "scan.init.flint", logger=logger):
            if is_bliss_shell():
                if self.__scan_display.auto:
                    if self.is_flint_recommended():
                        get_flint(mandatory=False)

    def is_flint_recommended(self):
        """Return true if flint is recommended for this scan"""
        scan_info = self._scan_info
        kind = scan_info.get("type", None)

        # If there is explicit plots, Flint is helpful
        plots = scan_info.get("plots", [])
        if len(plots) >= 1:
            return True

        # For ct, Flint is only recommended if there is MCAs or images
        if kind == "ct":
            chain = scan_info["acquisition_chain"]
            ndim_data = []
            for _top_master, chain in scan_info["acquisition_chain"].items():
                ndim_data.extend(chain.get("images", []))
                ndim_data.extend(chain.get("spectra", []))
                ndim_data.extend(chain.get("master", {}).get("images", []))
                ndim_data.extend(chain.get("master", {}).get("spectra", []))
            return len(ndim_data) > 0

        return True

    def _create_data_node(self, node_name):
        """Create the data node in Redis
        
        Important: has to be a method, since it can be overwritten in Scan subclasses (like Sequence)
        """
        self.__node = _create_node(
            node_name,
            "scan",
            parent=self.root_node,
            info=self._scan_info,
            connection=self._cache_cnx,
        )
        self._cache_cnx.add_prefetch(self.__node)

    def _prepare_node(self):
        if self.__node is None:
            self.root_node = self.__scan_saving.get_parent_node()
            self._cache_cnx = CacheConnection(self.root_node.db_connection)

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
            if self._shadow_scan_number:
                node_name = "_" + node_name
            self._create_data_node(node_name)
            self._current_pipeline_stream = self.root_node.db_connection.pipeline()
            self._pending_watch_callback = weakref.WeakKeyDictionary()

    def _end_node(self):
        self._current_pipeline_stream = None

        with capture_exceptions(raise_index=0) as capture:
            _exception, _, _ = sys.exc_info()

            with capture():
                # Store end event before setting the ttl
                self.node.end(exception=_exception)
            with capture():
                self.set_ttl()

            self._scan_info["end_time"] = self.node.info["end_time"]
            self._scan_info["end_time_str"] = self.node.info["end_time_str"]
            self._scan_info["end_timestamp"] = self.node.info["end_timestamp"]

    def __repr__(self):
        number = self.__scan_number
        if self._shadow_scan_number:
            number = ""
            path = "'not saved'"
        else:
            number = f"number={self.__scan_number}, "
            path = self.writer.filename

        return f"Scan({number}name={self.name}, path={path})"

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
        return SimpleTimeStatistics(self._stats_dict)

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

    def _get_data_axes(self):
        """
        Return all axes objects in this scan
        """
        master_axes = []
        for node in self.acq_chain.nodes_list:
            if not isinstance(node, AcquisitionMaster):
                continue
            if isinstance(node.device, Controller):
                master_axes.append(node.device)
            if is_motor_group(node.device):
                master_axes.extend(node.device.axes.values())

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
        return scan_math.cen(*self._get_x_y_data(counter, axis))[1]

    def peak(self, counter, axis=None, return_axes=False):
        return self._multimotors(self._peak, counter, axis, return_axes=return_axes)

    def _peak(self, counter, axis):
        return scan_math.peak(*self._get_x_y_data(counter, axis))

    def com(self, counter, axis=None, return_axes=False):
        return self._multimotors(self._com, counter, axis, return_axes=return_axes)

    def _com(self, counter, axis):
        return scan_math.com(*self._get_x_y_data(counter, axis))

    def cen(self, counter, axis=None, return_axes=False):
        return self._multimotors(self._cen, counter, axis, return_axes=return_axes)

    @typeguard.typechecked
    def find_position(
        self,
        func: Callable[[Any, Any], float],
        counter: _countable,
        axis=None,
        return_axes=False,
    ):
        """evaluate user supplied scan math function"""

        def _find_custom(counter, axis):
            return func(*self._get_x_y_data(counter, axis))

        return self._multimotors(_find_custom, counter, axis, return_axes=return_axes)

    def _cen(self, counter, axis):
        return scan_math.cen(*self._get_x_y_data(counter, axis))[0]

    def _multimotors(self, func, counter, axis=None, return_axes=False):
        motors = self._get_data_axes()
        axes_names = [axis.name for axis in motors]
        res = collections.UserDict()

        def info():
            """TODO: could be a nice table at one point"""
            s = "{"
            for key, value in res.items():
                if len(s) != 1:
                    s += ", "
                s += f"{key.name}: {round(value,precision=key.tolerance)}"
            s += "}"
            return s

        res.__info__ = info

        if axis is not None:
            if isinstance(axis, str):
                assert axis in axes_names or axis in ["elapsed_time", "epoch"]
            else:
                assert axis.name in axes_names
            res[axis] = func(counter, axis=axis)
        elif len(axes_names) == 1 and axes_names[0] in ["elapsed_time", "epoch"]:
            res = {axis: func(counter, axis=axes_names[0])}
        else:
            # allow "timer axis" for timescan
            if self.scan_info.get("type") in ["loopscan", "timescan"]:
                motors = ["elapsed_time"]
            if len(motors) < 1:
                raise RuntimeError("No axis found in this scan.")
            for mot in motors:
                res[mot] = func(counter, axis=mot)

        if not return_axes and len(res) == 1:
            return next(iter(res.values()))
        else:
            return res

    def _goto_multimotors(self, goto):
        bad_pos = [(mot, pos) for mot, pos in goto.items() if not numpy.isfinite(pos)]
        if len(bad_pos) > 0:
            motors = ", ".join([mot.name for mot, pos in goto.items()])
            pos = [pos for mot, pos in goto.items()]
            pos = ", ".join(
                [(f"{p}" if numpy.isfinite(p) else f"{p} (bad)") for p in pos]
            )
            raise RuntimeError(f"Motor(s) move aborted. Request: {motors} -> {pos}")
        for key in goto.keys():
            if key in ["elapsed_time", "epoch"]:
                RuntimeError("Cannot move. Time travel forbidden.")
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

    @typeguard.typechecked
    def goto_custom(
        self,
        func: Callable[[Any, Any], float],
        counter: _countable,
        axis=None,
        return_axes=False,
    ):
        """goto for custom user supplied scan math function"""
        return self._goto_multimotors(
            self.find_position(func, counter, axis, return_axes=True)
        )

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
        with time_profile(self._stats_dict, "scan.events.channel", logger=logger):
            with KillMask():
                with self._stream_pipeline_lock:
                    self.nodes[sender].store(
                        event_dict, cnx=self._current_pipeline_stream
                    )
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
        db_names = set()
        nodes = list(self.nodes.values())
        for node in nodes:
            db_names |= set(node.get_db_names())
        db_names |= set(self.node.get_db_names())
        self.node.apply_ttl(db_names)
        for node in nodes:
            node.ttl_is_set()
        self.node.ttl_is_set()

    def _device_event(self, event_dict=None, signal=None, sender=None):
        with time_profile(self._stats_dict, "scan.events.device", logger=logger):
            if signal == "end":
                task = self._swap_pipeline()
                if task is not None:
                    task.join()
                self.__trigger_data_watch_callback(signal, sender, sync=True)

    def _prepare_channels(self, channels, parent_node):
        for channel in channels:
            chan_name = channel.short_name
            channel_node = _get_or_create_node(
                chan_name,
                channel.data_node_type,
                parent_node,
                shape=channel.shape,
                dtype=channel.dtype,
                unit=channel.unit,
                fullname=channel.fullname,
                connection=self._cache_cnx,
            )
            channel.data_node = channel_node
            connect(channel, "new_data", self._channel_event)
            self._cache_cnx.add_prefetch(channel_node)
            self.nodes[channel] = channel_node

    def prepare(self, scan_info, devices_tree):
        with time_profile(self._stats_dict, "scan.prepare.devices", logger=logger):
            self._prepare_devices(devices_tree)
        with time_profile(self._stats_dict, "scan.prepare.writer", logger=logger):
            self.writer.prepare(self)

    def _prepare_devices(self, devices_tree):
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
                data_container_node = _create_node(
                    dev.name, parent=parent_node, connection=self._cache_cnx
                )
                self._cache_cnx.add_prefetch(data_container_node)
                self.nodes[dev] = data_container_node
                self._prepare_channels(dev.channels, data_container_node)

                for signal in ("start", "end"):
                    connect(dev, signal, self._device_event)

    def _update_scan_info_with_user_scan_meta(self):
        with time_profile(
            self._stats_dict, "scan.prepare.user_scan_meta", logger=logger
        ):
            with KillMask(masked_kill_nb=1):
                deep_update(self._scan_info, self.user_scan_meta.to_dict(self))
            self._scan_info["scan_meta_categories"] = self.user_scan_meta.cat_list()

    def _prepare_scan_meta(self):
        self._scan_info["filename"] = self.writer.filename
        # User metadata
        self.user_scan_meta = get_user_scan_meta().copy()
        self._update_scan_info_with_user_scan_meta()

        # Plot metadata
        display_extra = {}
        displayed_channels = self.__scan_display.displayed_channels
        if displayed_channels is not None:
            # Contextual display request
            display_extra["plotselect"] = displayed_channels
        displayed_channels = self.__scan_display._pop_next_scan_displayed_channels()
        if displayed_channels is not None:
            # Structural display request specified for this scan
            display_extra["displayed_channels"] = displayed_channels
        if len(display_extra) > 0:
            self._scan_info["_display_extra"] = display_extra

    def disconnect_all(self):
        for dev in self._devices:
            if isinstance(dev, (AcquisitionSlave, AcquisitionMaster)):
                for channel in dev.channels:
                    disconnect(channel, "new_data", self._channel_event)
                for signal in ("start", "end"):
                    disconnect(dev, signal, self._device_event)
        self._devices = []

    def _set_state(self, state):
        """Set the scan state
        """
        if self.__state < state:
            self.__state = state
            self.node.info["state"] = state
            self._scan_info["state"] = state
            self.__state_change.set()

    def _fill_meta(self, method_name):
        """Fill metadata from devices using specified method

        Method name can be either 'fill_meta_as_scan_start' or 'fill_meta_at_scan_end'
        """
        with time_profile(self._stats_dict, "scan.fill_metadata", logger=logger):
            for dev in self.acq_chain.nodes_list:
                node = self.nodes.get(dev)
                if node is None:
                    # prepare has not finished ?
                    continue
                with KillMask(masked_kill_nb=1):
                    meth = getattr(dev, method_name)
                    tmp = meth(self.user_scan_meta)
                if tmp:
                    update_node_info(node, tmp)

    def run(self):
        """Run the scan

        A scan can only be executed once.
        """
        if self.state != ScanState.IDLE:
            raise RuntimeError(
                "Scan state is not idle. Scan objects can only be used once."
            )

        # check if watch callback has to be called in "prepare" and "stop" phases
        data_watch_call_on_prepare = data_watch_call_on_stop = False
        if self._data_watch_callback is not None:
            if hasattr(self._data_watch_callback, "on_state"):
                data_watch_call_on_prepare = self._data_watch_callback.on_state(
                    ScanState.PREPARING
                )
                data_watch_call_on_stop = self._data_watch_callback.on_state(
                    ScanState.STOPPING
                )

        # initialize the iterations runner helper object
        iterations_runner = _ScanIterationsRunner(
            self._data_watch_callback_event,
            data_watch_call_on_prepare,
            data_watch_call_on_stop,
        )

        with capture_exceptions(raise_index=0) as capture:
            with time_profile(self._stats_dict, "scan.prepare.node", logger=logger):
                # check that icat metadata has been colleted for the dataset
                self.__scan_saving.on_scan_run(not self._shadow_scan_number)
                self._prepare_node()  # create scan node in redis

            # start data watch task, if needed
            if self._data_watch_callback is not None:
                with time_profile(
                    self._stats_dict, "scan.run.start_data_watcher", logger=logger
                ):
                    with capture():
                        self._data_watch_callback.on_scan_new(self, self.scan_info)
                    if capture.failed:
                        # if the data watch callback for "new" scan failed,
                        # better to not continue: let's put the final state
                        # and end the scan node
                        self._end_node()
                        self._set_state(ScanState.KILLED)
                        # disable connection caching
                        self._cache_cnx.disable_caching()
                        return
                    self._data_watch_running = False
                    self._data_watch_task = gevent.spawn(
                        Scan._data_watch,
                        weakref.proxy(
                            self, lambda _: self._data_watch_callback_event.set()
                        ),
                        self._data_watch_callback_event,
                        self._data_watch_callback_done,
                    )

            killed = killed_by_user = False

            with capture():
                # start the watchdog task, if any
                if self._watchdog_task is not None:
                    with time_profile(
                        self._stats_dict, "scan.run.start_watchdog", logger=logger
                    ):
                        self._watchdog_task.start()
                        self._watchdog_task.on_scan_new(self, self.scan_info)

                # get scan iterators
                # be careful: this has to be done after "scan_new" callback,
                # since it is possible to add presets in the callback...
                scan_chain_iterators = [next(i) for i in self.acq_chain.get_iter_list()]

                # execute scan iterations
                # NB: "user_print" messages won't be displayed to stdout, this avoids
                # output like "moving from X to Y" on motors for example. In principle
                # there should be no output to stdout from the scan itself
                with disable_user_output():
                    try:
                        # prepare acquisition objects (via AcquisitionChainIter)
                        iterations_runner.send(
                            [
                                gevent.spawn(i.apply_parameters)
                                for i in scan_chain_iterators
                            ]
                        )

                        # prepare scan
                        self._set_state(ScanState.PREPARING)

                        self._execute_preset("_prepare")

                        self.prepare(self.scan_info, self.acq_chain._tree)

                        iterations_runner.send(
                            [
                                gevent.spawn(i.prepare, self, self.scan_info)
                                for i in scan_chain_iterators
                            ]
                        )

                        # starting the scan
                        self._set_state(ScanState.STARTING)

                        self._fill_meta("fill_meta_at_scan_start")

                        self._execute_preset("start")

                        # this execute iterations
                        iterations_runner.send(
                            (self, scan_chain_iterators, self._watchdog_task)
                        )

                        # scan stop
                        self._set_state(ScanState.STOPPING)

                        iterations_runner.send(
                            [
                                gevent.spawn(i.stop)
                                for i in scan_chain_iterators
                                if i is not None
                            ]
                        )
                    except KeyboardInterrupt:
                        killed = killed_by_user = True
                        raise ScanAbort
                    except BaseException:
                        killed = True
                        raise

            with capture():
                # check if there is any master or device that would like
                # to provide meta data at the end of the scan.
                self._fill_meta("fill_meta_at_scan_end")

            with capture():
                self._update_scan_info_with_user_scan_meta()

                with KillMask(masked_kill_nb=1):
                    # update scan_info in redis
                    self.node._info.update(self.scan_info)

            # wait the end of publishing
            # (should be already finished)
            with capture():
                stream_task = self._swap_pipeline()
                if stream_task is not None:
                    stream_task.get()

            # Disconnect events
            self.disconnect_all()

            # counterpart of "_create_node"
            with capture():
                self._end_node()

            with capture():
                # Close nodes
                for node in self.nodes.values():
                    try:
                        node.close()
                    except AttributeError:
                        pass

            # kill watchdog task, if any
            with capture():
                if self._watchdog_task is not None:
                    self._watchdog_task.kill()
                    self._watchdog_task.on_scan_end(self.scan_info)

            # execute "stop" preset
            with capture():
                try:
                    self._execute_preset("_stop")
                except BaseException as e:
                    killed = True
                    if e == KeyboardInterrupt:
                        killed_by_user = True
                        raise ScanAbort
                    raise e

            # put final state
            with capture():
                if not killed:
                    self._set_state(ScanState.DONE)
                elif killed_by_user:
                    self._set_state(ScanState.USER_ABORTED)
                else:
                    self._set_state(ScanState.KILLED)

            if self._data_watch_task is not None:
                # call "scan end" data watch callback
                with capture():
                    self._data_watch_callback.on_scan_end(self.scan_info)

                with capture():
                    # ensure data watch task is stopped
                    if self._data_watch_task.ready():
                        if not self._data_watch_task.successful():
                            self._data_watch_task.get()
                    else:
                        self._data_watch_task.kill()

            # Add scan to the globals
            if self._add_to_scans_queue:
                current_session.scans.append(self)

            if self.writer:
                # write scan_info to file
                with time_profile(
                    self._stats_dict, "scan.finalize_writer", logger=logger
                ):
                    with capture():
                        self.writer.finalize_scan_entry(self)
                    with capture():
                        self.writer.close()

            # disable connection caching
            self._cache_cnx.disable_caching()

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
                try:
                    scan.scan_info["state"] = scan.state
                    scan._data_watch_callback.on_scan_data(
                        data_events, scan.nodes, scan.scan_info
                    )
                finally:
                    scan._data_watch_running = False
            except ReferenceError:
                break
            else:
                event_done.set()

    def get_data(self, key=None):
        """Return a dictionary of { channel_name: numpy array }.

        It is a 1D array corresponding to the scan points.
        Each point is a named structure corresponding to the counter names.
        """
        if key:
            return get_data(self)[key]
        else:
            return get_data(self)

    def _next_scan_number(self):
        LAST_SCAN_NUMBER = "last_scan_number"
        if self._shadow_scan_number:
            LAST_SCAN_NUMBER = "last_shadow_scan_number"
        filename = self.writer.filename
        # last scan number is stored in the parent of the scan
        parent_node = self.__scan_saving.get_parent_node()
        cnx = parent_node.connection
        with self.SCAN_NUMBER_LOCK:
            last_scan_number = cnx.hget(parent_node.db_name, LAST_SCAN_NUMBER)
            if (
                not self._shadow_scan_number
                and last_scan_number is None
                and "{scan_number}" not in filename
            ):
                # next scan number from the file (1 when not existing)
                next_scan_number = self.writer.last_scan_number + 1
                cnx.hsetnx(parent_node.db_name, LAST_SCAN_NUMBER, next_scan_number)
            else:
                # next scan number from Redis
                next_scan_number = cnx.hincrby(parent_node.db_name, LAST_SCAN_NUMBER, 1)
            return next_scan_number

    def _execute_preset(self, method_name):
        with time_profile(
            self._stats_dict, "scan.preset." + method_name, logger=logger
        ):
            preset_tasks = [
                gevent.spawn(getattr(preset, method_name), self)
                for preset in self._preset_list
            ]
            try:
                gevent.joinall(preset_tasks, raise_error=True)
            except BaseException:
                gevent.killall(preset_tasks)
                raise

    @property
    def _stats_dict(self):
        return self._acq_chain._stats_dict
