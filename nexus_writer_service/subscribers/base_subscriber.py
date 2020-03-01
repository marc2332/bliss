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

import os
import gevent
import datetime
import enum
import logging
import traceback
from gevent.time import time
from contextlib import contextmanager
from bliss.data.node import get_node as _get_node
from bliss.data.node import _get_node_object
from bliss.config.streaming import StreamStopReadingHandler
from ..utils.logging_utils import CustomLogger
from ..io import io_utils
from ..utils.async_utils import greenlet_ident
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
    Get DataNode instance event if the Redis node does not exist yet
    """
    node = _get_node(db_name)
    if node is None:
        node = _get_node_object(node_type, db_name, None, None)
    return node


class BaseSubscriber(object):
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
        * OFF: not listening to events
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

    def __init__(
        self, db_name, node_type=None, parentlogger=None, resource_profiling=False
    ):
        """
        :param str db_name:
        :param str node_type:
        :param parentlogger:
        :param bool resource_profiling:
        """
        self.state = self.STATES.INIT
        self.state_reason = "instantiation"
        self.starttime = datetime.datetime.now()
        self.endtime = None
        self.db_name = db_name
        self.node_type = node_type
        if parentlogger is None:
            parentlogger = logger
        self.logger = CustomLogger(parentlogger, self)
        self.resource_profiling = resource_profiling

        self._greenlet = None
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

    def start(self):
        """
        Start listening to Redis events in a separate greenlet
        """
        if not self.active:
            self._set_state(self.STATES.INIT, "Starting greenlet", force=True)
            self._greenlet = gevent.spawn(self._greenlet_main)

    def stop(self, successfull=False, kill=False, wait=False, timeout=1):
        """
        Stop listening to Redis events

        :param bool successfull:
        :param bool kill: kill the listening greenlet rather than gracefully stopping it
        :param bool wait: wait for the listening greenlet to exit
        :param num timeout: on wait
        """
        if not self.active:
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
        tm = self.endtime
        if tm is None:
            tm = datetime.datetime.now()
        return tm - self.starttime

    def done(self, seconds=0):
        """
        Listener greenlet has finished for x seconds

        :param num seconds:
        :returns bool:
        """
        if self.active:
            return False
        if self.endtime is None:
            return False
        timediff = datetime.datetime.now() - self.endtime
        return timediff >= datetime.timedelta(seconds=seconds)

    @property
    def active(self):
        """
        Listener greenlet is running
        """
        return bool(self._greenlet)

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
    def _node_iterator(self):
        if self._local_greenlet:
            try:
                return self._greenlet._iterator
            except AttributeError:
                it = self._greenlet._iterator = self.node.iterator
                return it
        else:
            return None

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
            self._greenlet._stop_handler = StreamStopReadingHandler()

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
            if self.resource_profiling:
                dumpname = os.path.join(
                    io_utils.temproot(), "pyprof_pid{}.cprof".format(os.getpid())
                )
                with profiling.profile(
                    logger=self.logger,
                    timelimit=100,
                    memlimit=30,
                    sortby=["cumtime", "tottime"],
                    color=False,
                    filename=dumpname,
                    units="MB",
                ):
                    self._listen_event_loop()
            else:
                self._listen_event_loop()
        except gevent.GreenletExit:
            self._set_state(self.STATES.FAULT, "GreenletExit")
            self.logger.warning("Stop listening to Redis events (greenlet killed)")
        except KeyboardInterrupt:
            self._set_state(self.STATES.FAULT, "KeyboardInterrupt")
            self.logger.warning("Stop listening to Redis events (KeyboardInterrupt)")
        except BaseException as e:
            self._set_state(self.STATES.FAULT, e)
            self.logger.error(
                "Stop listening due to exception:\n{}".format(traceback.format_exc())
            )
        finally:
            self._set_state(self.STATES.OFF, "Finished succesfully")
            if self.endtime is None:
                self.endtime = datetime.datetime.now()

    def _listen_event_loop(self, **kwargs):
        """
        Listen to Redis events
        """
        try:
            self._event_loop_initialize(**kwargs)
            for event_type, node, event_data in self._walk_events(
                stream_stop_reading_handler=self._stop_handler
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
                self._event_loop_finalize(**kwargs)
            except BaseException as e:
                self._set_state(self.STATES.FAULT, e)
                self.logger.error(
                    "Not properly finalized due to exception:\n{}".format(
                        traceback.format_exc()
                    )
                )

    def _walk_events(self, **kwargs):
        yield from self._node_iterator.walk_events(**kwargs)

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
        self.starttime = datetime.datetime.now()
        self.endtime = None
        self._create_stop_handler()
        self._register_event_loop_tasks(**kwargs)
        self._set_state(self.STATES.ON, "Start listening to Redis events")

    def _event_loop_finalize(self, **kwargs):
        """
        Executed at the end of the event loop
        """
        self.endtime = datetime.datetime.now()
        self._set_state(self.STATES.OFF, "Stop listening to Redis events")

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
