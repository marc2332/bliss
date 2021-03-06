# -*- coding: utf-8 -*-
#
# This file is part of the nexus writer service of the BLISS project.
#
# Code is maintained by the ESRF Data Analysis Unit.
#
# Original author: Wout de Nolf
#
# Copyright (c) 2015-2020 ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Basic Redis node subscriber
"""

import gevent
import datetime
import enum
import logging
import traceback
from gevent.time import time
from contextlib import contextmanager
from bliss.data.node import datanode_factory
from bliss.config.streaming import DataStreamReaderStopHandler
from ..utils.logging_utils import CustomLogger
from ..utils.async_utils import greenlet_ident, kill_on_exit
from ..utils import profiling


logger = logging.getLogger(__name__)


class PeriodicTask(object):
    def __init__(self, task, period=0):
        self.reset()
        self._period = period
        self._task = task

    def reset(self):
        self._tm0 = time()

    def execute(self):
        tm = time()
        if (tm - self._tm0) > self._period:
            self._task()
            self._tm0 = tm


def get_node(node_type, db_name):
    """
    Get DataNode instance even if the Redis node does not exist yet
    """
    return datanode_factory(
        db_name, node_type=node_type, state="exists", on_not_state="instantiate"
    )


class BaseSubscriber:
    """
    Listen to events of a particular Redis node

    All resources (Redis nodes) are assigned to an internal greenlet
    instance as BLISS cleans up resources when the greenlet is destroyed.
    """

    @enum.unique
    class STATES(enum.IntEnum):
        """
        * INIT: initializing (not listening to events yet)
        * ON: listening to events
        * OFF: not listening to events and resources released
        * FAULT: not listening to events due to exception
        """

        INIT = enum.auto()
        ON = enum.auto()
        FAULT = enum.auto()
        OFF = enum.auto()

    ALLOWED_STATE_TRANSITIONS = {
        STATES.INIT: [STATES.INIT, STATES.ON, STATES.OFF, STATES.FAULT],
        STATES.ON: [STATES.OFF, STATES.FAULT],
        STATES.OFF: [STATES.OFF, STATES.FAULT],
        STATES.FAULT: [],
    }

    @enum.unique
    class PROFILE_PARAMETERS(enum.IntEnum):
        OFF = enum.auto()
        CPU30 = enum.auto()
        CPU50 = enum.auto()
        CPU100 = enum.auto()
        WALL30 = enum.auto()
        WALL50 = enum.auto()
        WALL100 = enum.auto()
        MEM30 = enum.auto()
        MEM50 = enum.auto()
        MEM100 = enum.auto()

    _profile_arguments = {
        PROFILE_PARAMETERS.OFF: {},
        PROFILE_PARAMETERS.CPU30: {
            "memory": False,
            "time": True,
            "clock": "cpu",
            "timelimit": 30,
        },
        PROFILE_PARAMETERS.CPU50: {
            "memory": False,
            "time": True,
            "clock": "cpu",
            "timelimit": 50,
        },
        PROFILE_PARAMETERS.CPU100: {
            "memory": False,
            "time": True,
            "clock": "cpu",
            "timelimit": 100,
        },
        PROFILE_PARAMETERS.WALL30: {
            "memory": False,
            "time": True,
            "clock": "wall",
            "timelimit": 30,
        },
        PROFILE_PARAMETERS.WALL50: {
            "memory": False,
            "time": True,
            "clock": "wall",
            "timelimit": 50,
        },
        PROFILE_PARAMETERS.WALL100: {
            "memory": False,
            "time": True,
            "clock": "wall",
            "timelimit": 100,
        },
        PROFILE_PARAMETERS.MEM30: {"memory": True, "time": False, "memlimit": 30},
        PROFILE_PARAMETERS.MEM50: {"memory": True, "time": False, "memlimit": 50},
        PROFILE_PARAMETERS.MEM100: {"memory": True, "time": False, "memlimit": 100},
    }

    def __init__(
        self, db_name, node_type=None, parentlogger=None, resource_profiling=None
    ):
        """
        :param str db_name:
        :param str node_type:
        :param parentlogger:
        :param PROFILE_PARAMETERS resource_profiling:
        """
        self.state = self.STATES.INIT
        self.state_reason = "instantiation"
        self.init_time = datetime.datetime.now()
        self.start_time = None
        self.end_time = None
        self.db_name = db_name
        self.node_type = node_type
        if parentlogger is None:
            parentlogger = logger
        self.logger = CustomLogger(parentlogger, self)
        self.resource_profiling = resource_profiling

        self._greenlet = None
        self._started_event = gevent.event.Event()
        self._stopped_event = gevent.event.Event()
        self._stopped_event.set()
        self._log_task_period = 5
        self._exception_is_fatal = False
        self._info_cache = {}

    def __repr__(self):
        return self.db_name

    def __str__(self):
        return "{}-{} ({})".format(self.name, greenlet_ident(), self.state.name)

    @property
    def name(self):
        return self.db_name.split(":")[-1]

    def _set_state(self, state, reason, force=False):
        if force or state in self.ALLOWED_STATE_TRANSITIONS[self.state]:
            self.state = state
            reason = self.state_reason = str(reason)
            if state == self.STATES.FAULT:
                self.logger.error(reason)
            else:
                self.logger.info(reason)

    def start(self, wait=False, timeout=None):
        """
        Start listening to Redis events in a separate greenlet
        """
        # Check whether we need a (re)start
        if self.active:
            return
        self._started_event.clear()
        self._set_state(self.STATES.INIT, "Starting greenlet", force=True)
        self._greenlet = gevent.spawn(self._greenlet_main)
        if wait:
            with gevent.Timeout(timeout):
                self._started_event.wait()

    def stop(self, successfull=False, kill=False, wait=False, timeout=1):
        """
        Stop listening to Redis events

        :param bool successfull:
        :param bool kill: kill the listening greenlet rather than gracefully stopping it
        :param bool wait: wait for the listening greenlet to exit
        :param num timeout: on wait
        """
        if not self.alive:
            return
        if kill:
            self._set_state(self.STATES.FAULT, "Kill subscriber")
        elif successfull:
            self.log_progress("Send STOP event")
        else:
            self._set_state(self.STATES.FAULT, "Send STOP event (mark as FAULT)")
        if self._greenlet is not None:
            if kill:
                self._greenlet.kill()
            else:
                if self._stop_handler is None:
                    self.logger.warning("Cannot send STOP event (no stop handler)")
                else:
                    self._stop_handler.stop()
            if wait:
                self.join(timeout=timeout)

    def kill(self, **kw):
        self.stop(kill=True, **kw)

    def join(self, **kw):
        try:
            self._greenlet.join(**kw)
        except AttributeError:
            pass

    @property
    def duration(self):
        """Time between start and end of writing
        """
        t0 = self.start_time
        t1 = self.end_time
        if t0 is None:
            t0 = self.init_time
        if t1 is None:
            t1 = datetime.datetime.now()
        if t1 < t0:
            return t0 - t0
        else:
            return t1 - t0

    @property
    def sort_key(self):
        if self.start_time is None:
            return self.init_time
        else:
            return self.start_time

    def done(self, seconds=0):
        """
        Listener greenlet has finished for x seconds

        :param num seconds:
        :returns bool:
        """
        if self.active:
            return False
        if self.end_time is None:
            return False
        timediff = datetime.datetime.now() - self.end_time
        return timediff >= datetime.timedelta(seconds=seconds)

    @property
    def active(self):
        """Greenlet is running and listening
        """
        return (
            self.alive
            and self._started_event.is_set()
            and not self._stopped_event.is_set()
        )

    @property
    def alive(self):
        """Greenlet is running
        """
        return bool(self._greenlet)

    def wait_started(self, **kw):
        """Wait until the subscriber started listening to Redis.
        It may have already stopped.
        """
        self._started_event.wait(**kw)

    def wait_stopped(self, **kw):
        """Wait until the subscriber stopped listening to Redis.
        It may not have started.
        """
        self._stopped_event.wait(**kw)

    @property
    def _greenlet_id(self):
        if self._greenlet is None:
            return None
        else:
            return greenlet_ident(self._greenlet)

    @property
    def _local_greenlet(self):
        return self._greenlet_id == greenlet_ident()

    @property
    def node(self):
        if self._local_greenlet:
            try:
                return self._greenlet._node
            except AttributeError:
                node = self._greenlet._node = get_node(self.node_type, self.db_name)
                return node
        else:
            return get_node(self.node_type, self.db_name)

    @property
    def _nodes(self):
        if self._greenlet is None:
            return []
        else:
            try:
                return self._greenlet._node_children
            except AttributeError:
                lst = self._greenlet._node_children = []
                return lst

    @property
    def _periodic_tasks(self):
        if self._greenlet is None:
            return []
        else:
            try:
                return self._greenlet._periodic_tasks
            except AttributeError:
                lst = self._greenlet._periodic_tasks = []
                return lst

    def _greenlet_main(self):
        """
        Greenlet main function
        """
        with kill_on_exit():
            try:
                self.__greenlet_main()
            finally:
                self._greenlet = None
        self.logger.info("Greenlet exits")

    def _create_stop_handler(self):
        """
        Handler needed to stop the listener greenlet gracefully
        """
        if self._greenlet is not None:
            self._greenlet._stop_handler = DataStreamReaderStopHandler()

    @property
    def _stop_handler(self):
        return getattr(self._greenlet, "_stop_handler", None)

    @contextmanager
    def _cleanup_action(self, action):
        """
        Log exceptions during cleanup by do not reraise
        """
        try:
            yield
        except BaseException as e:
            # No need to reraise or set the listener state to FAULT
            self.logger.error(
                "Exception while {}:\n{}".format(action, traceback.format_exc())
            )

    def __greenlet_main(self):
        """
        Greenlet main function without the resource (de)allocation
        """
        try:
            kw = self._get_profile_arguments()
            if kw:
                with profiling.profile(**kw):
                    self._listen_event_loop()
            else:
                self._listen_event_loop()
        except gevent.GreenletExit:
            self._set_state(self.STATES.FAULT, "GreenletExit")
            self.logger.warning("Stop listening to Redis events (greenlet killed)")
            raise
        except KeyboardInterrupt:
            self._set_state(self.STATES.FAULT, "KeyboardInterrupt")
            self.logger.warning("Stop listening to Redis events (KeyboardInterrupt)")
            raise
        except BaseException as e:
            self._set_state(self.STATES.FAULT, e)
            self.logger.error(
                "Stop listening to Redis events due to exception:\n{}".format(
                    traceback.format_exc()
                )
            )
            raise
        finally:
            self.end_time = datetime.datetime.now()
            self._set_state(self.STATES.OFF, "Finished succesfully")

    @property
    def resource_profiling(self):
        return self._resource_profiling

    @resource_profiling.setter
    def resource_profiling(self, value):
        if value is None:
            value = self.PROFILE_PARAMETERS.OFF
        self._resource_profiling = value

    def _get_profile_arguments(self):
        """
        :returns dict or None:
        """
        kwargs = self._profile_arguments.get(self.resource_profiling, None)
        if kwargs:
            kwargs.update(
                {
                    "sortby": "tottime",
                    "color": False,
                    "filename": True,
                    "units": "MB",
                    "logger": logger,
                }
            )
        return kwargs

    def _listen_event_loop(self, **kwargs):
        """
        Listen to Redis events
        """
        try:
            self._event_loop_initialize(**kwargs)
            self._stopped_event.clear()
            for event_type, node, event_data in self._walk_events(
                stop_handler=self._stop_handler, started_event=self._started_event
            ):
                if event_type == event_type.END_SCAN:
                    if self.node.type in ["scan", "scan_group"]:
                        self.log_progress("Received END_SCAN event")
                        break
                else:
                    try:
                        self._exception_is_fatal = False
                        self._process_event(event_type, node, event_data)
                    except gevent.GreenletExit:
                        self._set_state(self.STATES.FAULT, "GreenletExit")
                        raise
                    except KeyboardInterrupt:
                        self._set_state(self.STATES.FAULT, "KeyboardInterrupt")
                        raise
                    except BaseException as e:
                        self._set_state(self.STATES.FAULT, e)
                        self.logger.warning(
                            "Processing {} event caused an exception:\n{}".format(
                                repr(event_type.name), traceback.format_exc()
                            )
                        )
                        if self._exception_is_fatal:
                            raise
                    self._event_loop_tasks()
        finally:
            try:
                self._stopped_event.set()
                self._event_loop_finalize(**kwargs)
            except BaseException as e:
                self._set_state(self.STATES.FAULT, e)
                self.logger.error(
                    "Not properly finalized due to exception:\n{}".format(
                        traceback.format_exc()
                    )
                )

    def _walk_events(self, **kwargs):
        yield from self.node.walk_events(**kwargs)

    def _process_event(self, event_type, node, event_data):
        """
        Process event belonging to this node
        """
        if event_type == event_type.NEW_NODE:
            self._event_new_node(node)
        else:
            event_info = event_type.name, node.type, node.name, node.fullname
            self.logger.debug("Untreated event: {}".format(event_info))

    def _event_new_node(self, node):
        """
        Creation of a new Redis node
        """
        self.logger.info("New node {} (type: {})".format(repr(node.db_name), node.type))
        self._nodes.append(node)

    def log_progress(self, msg=None):
        progress = self.progress_string
        duration = self.duration
        if msg:
            self.logger.info("{} ({} {})".format(msg, progress, duration))
        else:
            self.logger.info(" {} {}".format(progress, duration))

    @property
    def progress_string(self):
        return "{} nodes".format(self.progress)

    @property
    def progress(self):
        return len(self._nodes)

    def _event_loop_initialize(self, **kwargs):
        """
        Executed at the start of the event loop
        """
        self.start_time = datetime.datetime.now()
        self.end_time = None
        self._create_stop_handler()
        self._register_event_loop_tasks(**kwargs)
        self._set_state(self.STATES.ON, "Start listening to Redis events")

    def _event_loop_finalize(self, **kwargs):
        """
        Executed at the end of the event loop
        """
        self.logger.info("Stop listening to Redis events")

    def _register_event_loop_tasks(self, **kwargs):
        """
        Tasks to be run periodically after succesfully processing a Redis event
        """
        self._periodic_tasks.append(
            PeriodicTask(self.log_progress, self._log_task_period)
        )

    def _event_loop_tasks(self):
        """
        Execute tasks after succesfully processing a Redis event
        """
        for task in self._periodic_tasks:
            task.execute()

    @property
    def info(self):
        """
        Get the node's info dictionary
        """
        return self.node.info.get_all()

    def get_info(self, key, default=None, cache=False):
        """
        Get from the node's info dictionary

        :param str key:
        :param default: never cached
        :param bool cache: cache this value when retrieved
        """
        if cache:
            try:
                return self._info_cache[key]
            except KeyError:
                pass
            try:
                result = self._info_cache[key] = self.node.info[key]
            except KeyError:
                result = default
        else:
            result = self.node.info.get(key, default)
        return result
