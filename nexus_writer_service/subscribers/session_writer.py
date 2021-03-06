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
Nexus writer listening to Redis events of a session
"""

import gevent
import enum
import traceback
from collections import OrderedDict
from ..utils import async_utils
from ..utils import logging_utils
from ..utils import process_utils
from . import scan_writer_base
from . import scan_writer_config
from . import base_subscriber


logger = logging_utils.getLogger(__name__, __file__)


cli_saveoptions = {
    "noconfig": {
        "dest": "configurable",
        "action": "store_false",
        "help": "Do not use extra writer information from Redis",
    }
}


def all_cli_saveoptions(configurable=True):
    if configurable:
        ret = dict(scan_writer_config.cli_saveoptions)
    else:
        ret = dict(scan_writer_base.cli_saveoptions)
    ret.update(cli_saveoptions)
    return ret


def default_saveoptions(configurable=False):
    if configurable:
        ret = scan_writer_config.default_saveoptions()
    else:
        ret = scan_writer_base.default_saveoptions()
    ret["configurable"] = configurable
    return ret


class NexusSessionWriter(base_subscriber.BaseSubscriber):
    """
    Listen to session scan events and spawn a writer for each new scan.
    """

    @enum.unique
    class STATES(enum.IntEnum):
        """Writer states:
        * INIT: initializing (not accepting scans yet)
        * ON: accepting scans (without scan writers)
        * RUNNING: accepting scans (with scan writers)
        * OFF: not accepting scans
        * FAULT: not accepting scans due to exception
        """

        INIT = enum.auto()
        ON = enum.auto()
        RUNNING = enum.auto()
        FAULT = enum.auto()
        OFF = enum.auto()

    ALLOWED_STATE_TRANSITIONS = {
        STATES.INIT: [STATES.INIT, STATES.ON, STATES.RUNNING, STATES.OFF, STATES.FAULT],
        STATES.ON: [STATES.RUNNING, STATES.OFF, STATES.FAULT],
        STATES.RUNNING: [STATES.ON, STATES.OFF, STATES.FAULT],
        STATES.OFF: [STATES.OFF, STATES.FAULT],
        STATES.FAULT: [],
    }

    def __init__(
        self,
        db_name,
        configurable=True,
        purge_delay=300,
        parentlogger=None,
        resource_profiling=None,
        **saveoptions,
    ):
        """
        :param str db_name:
        :param bool configurable: generic or configurable writer
        :param int purge_delay: purge finished scans after x seconds
        :param Logger parentlogger:
        :param PROFILE_PARAMETERS resource_profiling:
        :param **saveoptions:
        """
        self.configurable = configurable
        self.writers = {}
        self.writer_saveoptions = saveoptions
        self.purge_delay = purge_delay
        self.minimal_purge_delay = 5
        self._log_task_period = 5
        self._fds = {}
        if parentlogger is None:
            parentlogger = logger
        super().__init__(
            db_name, resource_profiling=resource_profiling, parentlogger=parentlogger
        )

    def update_saveoptions(self, **kwargs):
        if "configurable" in kwargs:
            self.configurable = kwargs.pop("configurable")
        self.writer_saveoptions.update(kwargs)

    @property
    def saveoptions(self):
        d = dict(self.writer_saveoptions)
        d["configurable"] = self.configurable
        return d

    @property
    def resource_profiling(self):
        return self.writer_saveoptions["resource_profiling"]

    @resource_profiling.setter
    def resource_profiling(self, value):
        if value is None:
            value = self.PROFILE_PARAMETERS.OFF
        self.writer_saveoptions["resource_profiling"] = value

    @property
    def _scan_writer_class(self):
        if self.configurable:
            return scan_writer_config.NexusScanWriterConfigurable
        else:
            return scan_writer_base.NexusScanWriterBase

    @property
    def progress_string(self):
        n = len(self.writers)
        nactive = sum(w.active for w in list(self.writers.values()))
        return "{} scan writers ({} active)".format(n, nactive)

    @property
    def progress(self):
        return len(self.writers)

    @property
    def purge_delay(self):
        return max(self.minimal_purge_delay, self._purge_delay)

    @purge_delay.setter
    def purge_delay(self, value):
        self._purge_delay = value

    def start(self, **kwargs):
        if self.state in [self.STATES.ON, self.STATES.RUNNING]:
            return
        super().start(**kwargs)
        async_utils.log_gevent()
        # async_utils.start_heartbeat(self.logger)

    def stop(self, **kwargs):
        if self.state == self.STATES.RUNNING:
            raise RuntimeError("Cannot stop session writer when scans are running")
        super().stop(**kwargs)

    def _walk_events(self, **kwargs):
        scan_types = "scan_group", "scan"
        kwargs["include_filter"] = scan_types
        kwargs["exclude_children"] = scan_types
        yield from self.node.walk_on_new_events(**kwargs)

    def _event_loop_initialize(self, **kwargs):
        """
        Executed at the start of the event loop
        """
        super()._event_loop_initialize(**kwargs)
        self.logger.info(
            "Session writer started with options {}".format(self.saveoptions)
        )
        self._fds = {}

    def _event_loop_finalize(self, **kwargs):
        """
        Executed at the end of the event loop
        """
        try:
            self.stop_scan_writers(kill=False)
        except BaseException as e:
            self._set_state(self.STATES.FAULT, e)
            self.logger.error(
                "Exception while stopping scan writers:\n{}".format(
                    traceback.format_exc()
                )
            )
        finally:
            super()._event_loop_finalize(**kwargs)

    def _register_event_loop_tasks(self, nxroot=None, **kwargs):
        """
        Tasks to be run periodically after succesfully processing a Redis event
        """
        super()._register_event_loop_tasks(**kwargs)
        self._periodic_tasks.append(
            base_subscriber.PeriodicTask(self.purge_scan_writers, 0)
        )

    def _process_event(self, event_type, node, event_data):
        """
        Process event belonging to this session
        """
        if not self._fds:
            self._fds = process_utils.file_descriptors()
        if event_type == event_type.NEW_NODE:
            self._event_new_node(node)
        else:
            event_info = event_type.name, node.type, node.name, node.fullname
            self.logger.debug("Untreated event: {}".format(event_info))

    def _event_new_node(self, node):
        """
        Creation of a new Redis node
        """
        name = repr(node.name)
        if node.type == "scan":
            self.logger.debug("Start writer for scan " + name)
            self._event_start_scan(node)
        elif node.type == "scan_group":
            self.logger.debug("Start writer for group scan " + name)
            self._event_start_scan(node)
        else:
            self.logger.debug(
                "new {} node event on {} not treated".format(repr(node.type), name)
            )

    def _event_start_scan(self, node):
        """
        Create and spawn a scan writer greenlet
        """
        writer = self._scan_writer_class(
            node.db_name,
            node_type=node.node_type,
            parentlogger=self.logger,
            **self.writer_saveoptions,
        )
        writer.start()
        self.writers[node.name] = writer

    def purge_scan_writers(self, delay=True):
        """
        Remove finished writers
        """
        if delay:
            delay = self.purge_delay
        else:
            delay = self.minimal_purge_delay
        for name, writer in list(self.writers.items()):
            if writer.done(delay):
                self.logger.info("Purge scan writer " + str(writer))
                self.writers.pop(name, None)

    def stop_scan_writers(self, kill=False):
        """
        Kill scan writers
        """
        if kill:
            action = "kill"
        else:
            action = "stop"
        if self.writers:
            greenlets = []
            lst = []
            writers = list(self.writers.values())
            for writer in writers:
                if writer.active:
                    greenlets.append(writer._greenlet)
                    lst.append(writer)
                    if kill:
                        writer.kill()
                    else:
                        writer.stop()
            if greenlets:
                lst = list(map(str, lst))
                self.logger.info(action + " scan writers {} ...".format(lst))
            else:
                self.logger.info("No scan writers to " + action)
            gevent.joinall(greenlets)
            self.writers = {}
            self.log_progress()
        else:
            self.logger.info("No scan writers to " + action)

    def log_progress(self, msg=None):
        n = len(self.writers)
        nactive = sum(w.active for w in list(self.writers.values()))
        if msg:
            msg = "{} ({} scan writers, {} active)".format(msg, n, nactive)
        else:
            msg = "{} scan writers ({} active)".format(n, nactive)
        self.logger.info(msg)
        if self.resource_profiling != self.PROFILE_PARAMETERS.OFF:
            self.log_resources()

    def _get_profile_arguments(self):
        """
        :returns dict or None:
        """
        # No time or CPU profiling for the session
        return None

    @property
    def resources(self):
        nfds = len(process_utils.file_descriptors())
        nsockets = len(process_utils.sockets())
        ngreenlets = len(process_utils.greenlets())
        nthreads = len(process_utils.threads())
        mb = int(process_utils.memory() / 1024 ** 2)
        return f"{nthreads} threads, {ngreenlets} greenlets, {nsockets} sockets, {nfds} fds, {mb}MB MEM"

    def log_resources(self):
        self.logger.info(self.resources)

    @property
    def state(self):
        if self._state == self.STATES.ON:
            if any(writer.alive for writer in list(self.writers.values())):
                return self.STATES.RUNNING
        return self._state

    @state.setter
    def state(self, value):
        self._state = value

    def scan_names(self):
        """
        :returns list(str):
        """
        return list(
            name
            for name, writer in sorted(
                list(self.writers.items()), key=lambda item: item[1].sort_key
            )
        )

    def scan_exists(self, name):
        """
        :param str name: scan name
        :returns bool:
        """
        return name in self.writers

    def stop_scan_writer(self, name=None, kill=False):
        if name is None:
            self.stop_scan_writers(kill=kill)
        else:
            writer = self.writers.get(name, None)
            if writer is None:
                raise ValueError("No writer for scan {} exists".format(repr(name)))
            if kill:
                writer.kill()
            else:
                writer.stop()
            self.log_progress()

    def _scan_properties(self, getter, name=None):
        """
        :param str name: scan name (all scans by default)
        :returns dict: keys are the scan names (ordered by scan number)
        """
        ret = OrderedDict()
        if name:
            writer = self.writers.get(name, None)
            if writer is None:
                raise ValueError(f"No writer for scan {repr(name)} exists")
            ret[name] = getter(writer)
        else:
            for name, writer in sorted(
                list(self.writers.items()), key=lambda item: item[1].sort_key
            ):
                ret[name] = getter(writer)
        return ret

    def scan_state(self, name=None):
        """
        :param str name: scan name (all scans by default)
        :returns dict: str->ScanWriterState
        """
        return self._scan_properties(self._scan_state_getter, name=name)

    @staticmethod
    def _scan_state_getter(writer):
        return writer.state

    def scan_state_info(self, name=None):
        """
        :param str name: scan name (all scans by default)
        :returns dict: str->(ScanWriterState, str)
        """
        return self._scan_properties(self._scan_state_info_getter, name=name)

    @staticmethod
    def _scan_state_info_getter(writer):
        return writer.state, writer.state_reason

    def scan_uri(self, name=None):
        """
        :param str name: scan name (all scans by default)
        :returns dict: str->list(str)
        """
        return self._scan_properties(self._scan_uri_getter, name=name)

    @staticmethod
    def _scan_uri_getter(writer):
        return writer.uris

    def scan_start(self, name=None):
        """
        :param str name: scan name (all scans by default)
        :returns dict: str->DateTime
        """
        return self._scan_properties(self._scan_start_getter, name=name)

    @staticmethod
    def _scan_start_getter(writer):
        return writer.start_time

    def scan_end(self, name=None):
        """
        :param str name: scan name (all scans by default)
        :returns dict: str->DateTime
        """
        return self._scan_properties(self._scan_end_getter, name=name)

    @staticmethod
    def _scan_end_getter(writer):
        return writer.end_time

    def scan_duration(self, name=None):
        """
        :param str name: scan name (all scans by default)
        :returns dict: str->TimeDelta
        """
        return self._scan_properties(self._scan_duration_getter, name=name)

    @staticmethod
    def _scan_duration_getter(writer):
        return writer.duration

    def scan_progress(self, name=None):
        """
        :param str name: scan name (all scans by default)
        :returns dict: scanname->dict(subscanname->str)
        """
        return self._scan_properties(self._scan_progress_getter, name=name)

    @staticmethod
    def _scan_progress_getter(writer):
        return writer.subscan_progress

    def scan_progress_info(self, name=None):
        """
        :param str name: scan name (all scans by default)
        :returns dict: scanname->dict(subscanname->str)
        """
        return self._scan_properties(self._scan_progress_info_getter, name=name)

    @staticmethod
    def _scan_progress_info_getter(writer):
        return writer.subscan_progress_info

    def scan_event_buffers(self, name=None):
        """
        :param str name: scan name (all scans by default)
        :returns dict: scanname->dict(subscanname->int)
        """
        return self._scan_properties(self._scan_event_buffers_getter, name=name)

    @staticmethod
    def _scan_event_buffers_getter(writer):
        return writer.buffer_size

    def scan_has_write_permissions(self, name):
        """
        :param str name: scan name
        :returns bool:
        """
        writer = self.writers.get(name, None)
        if writer is None:
            raise ValueError(f"No writer for scan {repr(name)} exists")
        else:
            return writer.has_write_permissions

    def scan_has_required_disk_space(self, name):
        """
        :param str name: scan name
        :returns bool:
        """
        writer = self.writers.get(name, None)
        if writer is None:
            raise ValueError(f"No writer for scan {repr(name)} exists")
        else:
            return writer.has_required_disk_space


def start_session_writer(session_name, **saveoptions):
    """
    This starts the main session writer in a Greenlet.

    :param str session_name: does not need to exist yet
    :param **saveoptions: see `session_writer`
    :returns Greenlet:
    """
    # Monitoring h5py
    # from .patching import monkey
    # monkey.patch("h5py")
    processlogger = saveoptions.get("parentlogger", None)
    if processlogger is None:
        logid = "Session writer " + repr(session_name)
        processlogger = logging_utils.CustomLogger(logger, logid)
    writer = NexusSessionWriter(session_name, **saveoptions)
    writer.start()
    processlogger.info("greenlet started")
    return writer


def main():
    """
    Parse CLI arguments, start a session writer and block.
    """
    # Define CLI
    import argparse

    parser = argparse.ArgumentParser(
        description="Start a Bliss session writer as a process"
    )
    parser.add_argument("session_name", type=str, help="Session name")
    _cli_saveoptions = all_cli_saveoptions()
    for attr, okwargs in _cli_saveoptions.items():
        parser.add_argument("--" + attr, **okwargs)
    logging_utils.add_cli_args(parser)

    # Parse CLI arguments
    args, unknown = parser.parse_known_args()
    kwargs = {}
    _cli_saveoptions = all_cli_saveoptions(configurable=args.configurable)
    for attr, okwargs in _cli_saveoptions.items():
        option = okwargs["dest"]
        try:
            kwargs[option] = getattr(args, option)
        except AttributeError:
            continue

    # Launch the session writer
    logid = "Session writer " + repr(args.session_name)
    processlogger = logging_utils.CustomLogger(logger, logid)
    processlogger.info("process started")
    writer = start_session_writer(args.session_name, **kwargs)
    writer.join()
    processlogger.info("process exits")


if __name__ == "__main__":
    main()
