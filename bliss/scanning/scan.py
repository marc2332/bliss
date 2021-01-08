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
from bliss.common.axis import Axis
from bliss.common.motor_group import is_motor_group
from bliss.common.hook import group_hooks, execute_pre_scan_hooks
from bliss.common.event import connect, disconnect
from bliss.common.cleanup import error_cleanup, axis as cleanup_axis, capture_exceptions
from bliss.common.greenlet_utils import KillMask
from bliss.common.plot import get_flint
from bliss.common.utils import periodic_exec, deep_update
from bliss.scanning.scan_meta import get_user_scan_meta, META_TIMING
from bliss.common.motor_group import is_motor_group
from bliss.common.utils import Null, update_node_info, round
from bliss.common.profiling import SimpleTimeStatistics
from bliss.common.profiling import simple_time_profile as time_profile
from bliss.controllers.motor import Controller, get_real_axes
from bliss.config.conductor.client import get_redis_proxy
from bliss.data.node import create_node
from bliss.data.nodes import channel as channelnode
from bliss.data.node import DataNodeAsyncHelper
from bliss.data.scan import get_data
from bliss.scanning.chain import AcquisitionSlave, AcquisitionMaster, StopChain
from bliss.scanning.writer.null import Writer as NullWriter
from bliss.scanning import scan_math
from bliss.common.logtools import disable_user_output
from louie import saferef
from bliss.common.plot import get_plot
from bliss import __version__ as publisher_version
from bliss.common import logtools
from bliss.scanning.scan_info import ScanInfo


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

        :param ScanState state: either ScanState.PREPARING or ScanState.STOPPING.

        i.e: return state == ScanState.PREPARING will inform that
        **on_scan_data** will be called during **PREPARING** scan
        state.

        """
        return False

    def on_scan_new(self, scan, scan_info):
        """This callback is called when the scan is about to starts
        
        :param Scan scan: is the scan object
        :param dict scan_info: is the dict of information about this scan
        """
        pass

    def on_scan_data(self, data_events, nodes, scan_info):
        """This callback is called when new data is emitted.

        :param dict data_events: a dict with Acq(Device/Master) as key and a set of signal as values
        :param dict nodes: a dict with Acq(Device/Master) as key and the associated data node as value
        :param dict scan_info: dictionary which contains the current scan state
        """
        raise NotImplementedError

    def on_scan_end(self, scan_info):
        """Called at the end of the scan.
        
        :param dict scan_info: dictionary which contains the current scan state
        """
        pass


def is_zerod(node):
    return node.type == "channel" and len(node.shape) == 0


class StepScanDataWatch(DataWatchCallback):
    """Follow 0D data generation for a step scan. Data is buffered and
    yielded to the callback point-per-point (i.e. channels are synchronized).
    """

    def __init__(self):
        self._buffers = dict()
        self._missing = set()

    def _init_buffers(self, nodes):
        """
        :param dict nodes:
        """
        if self._buffers or not nodes:
            return
        for name, node in nodes.items():
            if node.type != "channel" or node.shape:
                continue  # Does not generate 0D data
            info = {"node": node, "queue": collections.deque(), "from_index": 0}
            self._buffers[node.fullname] = info

    def on_scan_new(self, scan, scan_info):
        cb = _SCAN_WATCH_CALLBACKS["new"]()
        if cb is not None:
            cb(scan, scan_info)

    def _get_info(self, channel):
        """
        :param AcquisitionChannel or AcquisitionObject channel:
        :return None or dict:
        """
        try:
            fullname = channel.fullname
        except AttributeError:
            return None  # AcquisitionObject
        return self._buffers.get(fullname, None)

    def _fetch_data(self, data_events):
        """
        :param dict data_events:
        """
        for channel in data_events:
            info = self._get_info(channel)
            if info is None:
                continue
            node = info["node"]
            try:
                data = node.get(info["from_index"], -1)
            except Exception as e:
                # Most likely the data has already disappeared from Redis.
                # Only show this message once per channel.
                name = channel.name
                if name not in self._missing:
                    self._missing.add(name)
                    logtools.log_warning(
                        self, f"data watcher failed for '{name}' ({e})"
                    )
                data = numpy.nan
            data = numpy.atleast_1d(data)
            if data.size:
                info["queue"].extend(data)
                info["from_index"] += data.size

    def _pop_data(self):
        """
        :yields dict: fullname:num
        """
        npop = min(len(info["queue"]) for info in self._buffers.values())
        for _ in range(npop):
            yield {
                fullname: info["queue"].popleft()
                for fullname, info in self._buffers.items()
            }

    def on_scan_data(self, data_events, nodes, scan_info):
        cb = _SCAN_WATCH_CALLBACKS["data"]()
        if cb is None:
            return
        self._init_buffers(nodes)
        self._fetch_data(data_events)
        for pointdatadict in self._pop_data():
            cb(scan_info, pointdatadict)

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
    _NODE_TYPE = "scan"
    SCAN_NUMBER_LOCK = gevent.lock.Semaphore()

    # When enabled, only the scan/channel node's info and struct are
    # cached, not the channel data.
    _REDIS_CACHING = True

    _USE_PIPELINE_MGR = True

    def __init__(
        self,
        chain,
        name="scan",
        scan_info=None,
        save=True,
        save_images=None,
        scan_saving=None,
        data_watch_callback=None,
        watchdog_callback=None,
    ):
        """
        Scan class to publish data and trigger the writer if any.

        Arguments:
            chain: Acquisition chain you want to use for this scan.
            name: Scan name, if None set default name *scan*
            scan_info: Scan parameters if some, as a dict (or as ScanInfo
                       object)
            save: True if this scan have to be saved
            save_images: None means follows "save"
            scan_saving: Object describing how to save the scan, if any
            data_watch_callback: a callback inherited from `DataWatchCallback`
        """
        self.__name = name
        self.__scan_number = None
        self._scan_info = ScanInfo()

        self.root_node = None
        self._scan_connection = None
        self._shadow_scan_number = not save
        self._add_to_scans_queue = not (name == "ct" and self._shadow_scan_number)

        # Double buffer pipeline for streams store
        if self._USE_PIPELINE_MGR:
            self._rotating_pipeline_mgr = None
        else:
            self._stream_pipeline_lock = gevent.lock.Semaphore()
            self._stream_pipeline_task = None
            self._current_pipeline_stream = None

        self.__nodes = dict()
        self._devices = []
        self._axes_in_scan = []  # for pre_scan, post_scan in axes hooks

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
            if scan_info is not None:
                self._scan_info.update(scan_info)
            scan_saving = self.__scan_saving
            self._scan_info.setdefault("title", self.__name)
            self._scan_info["session_name"] = scan_saving.session
            self._scan_info["user_name"] = scan_saving.user_name
            self._scan_info["data_writer"] = scan_saving.writer
            self._scan_info["data_policy"] = scan_saving.data_policy
            self._scan_info["shadow_scan_number"] = self._shadow_scan_number
            self._scan_info["save"] = save
            self._scan_info["publisher"] = "Bliss"
            self._scan_info["publisher_version"] = publisher_version
            self._scan_info.set_acquisition_chain_info(self._acq_chain)

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
        """
        self.__node = create_node(
            node_name,
            node_type=self._NODE_TYPE,
            parent=self.root_node,
            info=self._scan_info,
            connection=self._scan_connection,
        )
        if self._REDIS_CACHING:
            self.__node.add_prefetch()

    @property
    def root_connection(self):
        """Redis connection of the root node (parent of the scan).

        :returns RedisDbProxy:
        """
        return self.root_node.db_connection

    @property
    def scan_connection(self):
        """Redis connection of the scan node and its children.

        :returns RedisDbProxy or CachingRedisDbProxy:
        """
        return self._scan_connection

    def _disable_caching(self):
        """After this, the `scan_connection` behaves like a normal
        RedisDbProxy without caching
        """
        if self._REDIS_CACHING and self.scan_connection is not None:
            self.scan_connection.disable_caching()

    def _prepare_node(self):
        if self.__node is not None:
            return
        # The root nodes will not have caching
        self.root_node = self.__scan_saving.get_parent_node()
        # The scan node and its children will have caching
        if self._REDIS_CACHING:
            self._scan_connection = get_redis_proxy(db=1, caching=True, shared=False)
        else:
            self._scan_connection = self.root_connection

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

        if self._USE_PIPELINE_MGR:
            # Channel data will be emitted and the associated `trigger_data_watch_callback`
            # calls executed, when one of the following things happens:
            #  - 1 stream has buffered a number of events equal to `max_stream_events`
            #  - the total buffered data has reached `max_bytes` bytes
            #  - the time from the first buffered event reached `max_time`
            #  - `flush` is called on the proxy rotation manager

            max_time = 0.2  # We don't want to keep Redis subscribers waiting too long
            if channelnode.CHANNEL_MAX_LEN:
                max_stream_events = min(channelnode.CHANNEL_MAX_LEN // 10, 50)
            else:
                max_stream_events = 50
            max_bytes = None  # No maximum

            self._rotating_pipeline_mgr = self.root_connection.rotating_pipeline(
                max_bytes=max_bytes,
                max_stream_events=max_stream_events,
                max_time=max_time,
            )
        else:
            self._current_pipeline_stream = self.root_connection.pipeline()
            self._pending_watch_callback = weakref.WeakKeyDictionary()

    def _end_node(self):
        if self._USE_PIPELINE_MGR:
            self._rotating_pipeline_mgr = None
        else:
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

    def _get_data_axes(self, include_calc_reals=False):
        """
        Return all axes objects in this scan
        """
        master_axes = []
        for node in self.acq_chain.nodes_list:
            if not isinstance(node, AcquisitionMaster):
                continue
            if isinstance(node.device, Controller):
                if include_calc_reals:
                    master_axes += get_real_axes(node.device)
                else:
                    master_axes.append(node.device)
            if is_motor_group(node.device):
                if include_calc_reals:
                    master_axes += get_real_axes(*node.device.axes.values())
                else:
                    master_axes += node.device.axes.values()

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

    def __trigger_watchers_data_event(self, signal, sender, sync=False):
        # Only used when self._USE_PIPELINE_MGR=False
        self.__trigger_data_watch_callback(signal, sender, sync=sync)
        self.__trigger_watchdog_data_event(signal, sender)

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

    def __trigger_watchdog_data_event(self, signal, sender):
        if self._watchdog_task is not None:
            self._watchdog_task.trigger_data_event(sender, signal)

    def _channel_event(self, event_dict, signal=None, sender=None):
        with time_profile(self._stats_dict, "scan.events.channel", logger=logger):
            if self._USE_PIPELINE_MGR:
                with KillMask():
                    with self._rotating_pipeline_mgr.async_proxy() as async_proxy:
                        self.nodes[sender].store(event_dict, cnx=async_proxy)
                        async_proxy.add_execute_callback(
                            self.__trigger_data_watch_callback, signal, sender
                        )
                        self.__trigger_watchdog_data_event(signal, sender)
            else:
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
                new_pipeline = self.root_connection.pipeline()
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
                    self.__trigger_watchers_data_event,
                )

                self._stream_pipeline_task = task
                self._current_pipeline_stream = self.root_connection.pipeline()
            return self._stream_pipeline_task

    def set_ttl(self):
        with time_profile(self._stats_dict, "scan.finalize.set_ttl", logger=logger):
            # node.get_db_names takes the most time
            db_names = set()
            nodes = list(self.nodes.values())
            for node in nodes:
                db_names |= set(node.get_db_names(include_parents=False))
            db_names |= set(self.node.get_db_names())
            self.node.apply_ttl(db_names)
            for node in nodes:
                node.detach_ttl_setter()
            self.node.detach_ttl_setter()

    def _device_event(self, event_dict=None, signal=None, sender=None):
        with time_profile(self._stats_dict, "scan.events.device", logger=logger):
            if signal == "end":
                if self._USE_PIPELINE_MGR:
                    self._rotating_pipeline_mgr.flush(raise_error=False)
                    self.__trigger_data_watch_callback(signal, sender, sync=True)
                    self.__trigger_watchdog_data_event(signal, sender)
                else:
                    task = self._swap_pipeline()
                    if task is not None:
                        task.join()
                    self.__trigger_watchers_data_event(signal, sender, sync=True)

    def prepare(self, scan_info, devices_tree):
        with time_profile(self._stats_dict, "scan.prepare.devices", logger=logger):
            self._prepare_devices(devices_tree)
        with time_profile(self._stats_dict, "scan.prepare.writer", logger=logger):
            self.writer.prepare(self)

        with time_profile(self._stats_dict, "scan.prepare.motion_hooks", logger=logger):
            self._axes_in_scan = self._get_data_axes(include_calc_reals=True)
            with execute_pre_scan_hooks(self._axes_in_scan):
                pass

    def _prepare_devices(self, devices_tree):
        nodes = dict()
        # DEPTH expand without the root node
        devices = list(devices_tree.expand_tree())[1:]

        # Create channel nodes and their parents in Redis
        addparentinfo = dict()  # {level:(parents, children)}
        asynchelper = DataNodeAsyncHelper(self.scan_connection)

        with asynchelper:
            # All this will be executed in one pipeline:
            for dev in devices:
                if not isinstance(dev, (AcquisitionSlave, AcquisitionMaster)):
                    continue

                # Create the parent node for the channel nodes
                dev_node = devices_tree.get_node(dev)
                level = devices_tree.depth(dev_node)
                if level == 1:
                    # Top level node has the scan node as parent
                    parent = self.node
                else:
                    parent = nodes[dev_node.bpointer]
                channel_parent = create_node(
                    dev.name,  # appended to parent.db_name
                    parent=parent,
                    add_to_parent=False,  # post-pone because order matters
                    connection=asynchelper.async_proxy,
                )
                asynchelper.replace_connection(channel_parent)
                nodes[dev] = channel_parent

                parents, children = addparentinfo.setdefault(level, (list(), list()))
                parents.append((parent, channel_parent))

                # Create the channel nodes
                for channel in dev.channels:
                    channel_node = create_node(
                        channel.short_name,  # appended to channel_parent.db_name
                        node_type=channel.data_node_type,
                        parent=channel_parent,
                        add_to_parent=False,  # post-pone because order matters
                        shape=channel.shape,
                        dtype=channel.dtype,
                        unit=channel.unit,
                        fullname=channel.fullname,  # node.fullname
                        channel_name=channel.fullname,  # node.name
                        connection=asynchelper.async_proxy,
                    )
                    asynchelper.replace_connection(channel_node)
                    channel.data_node = channel_node
                    nodes[channel] = channel_node
                    children.append((channel_parent, channel_node))

        if self._REDIS_CACHING:
            for node in nodes.values():
                node.add_prefetch()

        # Add the children to their parents in Redis (NEW_NODE events)
        for level, addlists in sorted(addparentinfo.items(), key=lambda item: item[0]):
            for addlist in addlists:
                with asynchelper:
                    # All this will be executed in one pipeline:
                    for parent, child in addlist:
                        asynchelper.replace_connection(parent, child)
                        parent.add_children(child)

        # Connect device and channel events
        self.__nodes = nodes
        self._devices = devices
        for dev, node in list(nodes.items()):
            if dev in devices:
                connect(dev, "start", self._device_event)
                connect(dev, "end", self._device_event)
            else:
                connect(dev, "new_data", self._channel_event)

    def _update_scan_info_with_user_scan_meta(self, meta_timing):
        # be aware: this is patched in ct!
        with time_profile(
            self._stats_dict, "scan.prepare.user_scan_meta", logger=logger
        ):
            with KillMask(masked_kill_nb=1):
                deep_update(
                    self._scan_info,
                    self.user_scan_meta.to_dict(self, timing=meta_timing),
                )
            self._scan_info["scan_meta_categories"] = self.user_scan_meta.cat_list()

    def _prepare_scan_meta(self):
        self._scan_info["filename"] = self.writer.filename
        # User metadata
        self.user_scan_meta = get_user_scan_meta().copy()
        self._update_scan_info_with_user_scan_meta(META_TIMING.START)

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
                        with time_profile(
                            self._stats_dict, "scan.finalize.node", logger=logger
                        ):
                            self._end_node()

                        self._set_state(ScanState.KILLED)

                        with time_profile(
                            self._stats_dict, "scan.finalize.caching", logger=logger
                        ):
                            self._disable_caching()
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
                self._update_scan_info_with_user_scan_meta(META_TIMING.END)

                with KillMask(masked_kill_nb=1):
                    # update scan_info in redis
                    self.node._info.update(self.scan_info)

            # wait the end of publishing
            # (should be already finished)
            with capture():
                if self._USE_PIPELINE_MGR:
                    self._rotating_pipeline_mgr.flush(raise_error=True)
                else:
                    stream_task = self._swap_pipeline()
                    if stream_task is not None:
                        stream_task.get()

            # Disconnect events
            self.disconnect_all()

            with time_profile(self._stats_dict, "scan.finalize.node", logger=logger):
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

            # execute post scan hooks
            hooks = group_hooks(self._axes_in_scan)
            for hook in reversed(list(hooks)):
                with capture():
                    hook.post_scan(self._axes_in_scan[:])

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
                    self._stats_dict, "scan.finalize.writer", logger=logger
                ):
                    with capture():
                        self.writer.finalize_scan_entry(self)
                    with capture():
                        self.writer.close()

            # disable connection caching
            with time_profile(self._stats_dict, "scan.finalize.caching", logger=logger):
                self._disable_caching()

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
