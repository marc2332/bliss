# -*- coding: utf-8 -*-
#
# This file is part of the nexus writer service of the BLISS project.
#
# Code is maintained by the ESRF Data Analysis Unit.
#
# Original author: Wout de Nolf
#
# Copyright (c) 2015-2019 ESRF
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


def scansortkey(scan_name):
    return int(scan_name.split("_")[0])


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
        resource_profiling=False,
        **saveoptions,
    ):
        """
        :param str db_name:
        :param bool configurable: generic or configurable writer
        :param int purge_delay: purge finished scans after x seconds
        :param Logger parentlogger:
        :param saveoptions:
        """
        if parentlogger is None:
            parentlogger = logger
        super().__init__(
            db_name, resource_profiling=resource_profiling, parentlogger=parentlogger
        )
        self._log_task_period = 5
        self.saveoptions = saveoptions
        if configurable:
            self._scan_writer_class = scan_writer_config.NexusScanWriterConfigurable
        else:
            self._scan_writer_class = scan_writer_base.NexusScanWriterBase
        self.writers = {}
        self.minimal_purge_delay = 5
        self.purge_delay = purge_delay
        self._fds = {}

    @property
    def progress_string(self):
        n = len(self.writers)
        nactivate = sum(w.active for w in self.writers.values())
        return "{} scan writers ({} activate)".format(n, nactivate)

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
        g = self._greenlet
        super().start(**kwargs)
        if g != self._greenlet:
            async_utils.kill_on_exit(self._greenlet)

    def stop(self, **kwargs):
        if self.state == self.STATES.RUNNING:
            raise RuntimeError("Cannot stop session writer when scans are running")
        super().stop(**kwargs)

    def _walk_events(self):
        yield from self._node_iterator.walk_on_new_events(filter=["scan_group", "scan"])

    def _event_loop_initialize(self, **kwargs):
        """
        Executed at the start of the event loop
        """
        super()._event_loop_initialize(**kwargs)
        self.logger.info("Writer started with options {}".format(self.saveoptions))
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

    def _process_event(self, event_type, node):
        """
        Process event belonging to this session
        """
        if not self._fds:
            self._fds = process_utils.file_descriptors()
        if event_type.name == "NEW_NODE":
            self._event_new_node(node)
        elif event_type.name == "END_SCAN":
            self._event_end_scan(node)
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
            resource_profiling=self.resource_profiling,
            **self.saveoptions,
        )
        writer.start()
        self.writers[node.name] = writer

    def _event_end_scan(self, node):
        """
        Send an END_SCAN event to the scan writer
        """
        self.logger.info("END_SCAN event received for scan {}".format(repr(node.name)))
        writer = self.writers.get(node.name, None)
        if writer:
            writer.stop(successfull=True)

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
            writers = list(self.writers.values())
            for writer in writers:
                if writer.active:
                    greenlets.append(writer._greenlet)
                    if kill:
                        writer.kill()
                    else:
                        writer.stop()
            if greenlets:
                lst = list(map(str, greenlets))
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
        nactivate = sum(w.active for w in self.writers.values())
        msg = "{} scan writers ({} activate)".format(n, nactivate)
        self.logger.info(msg)
        if self.resource_profiling:
            self.log_resources()

    def log_resources(self):
        fds = process_utils.log_fd_diff(
            self.logger.info, self._fds, prefix="{} fds since start"
        )
        nfds = len(fds)
        ngreenlets = len(process_utils.greenlets())
        nthreads = len(process_utils.threads())
        mb = int(process_utils.memory() / 1024 ** 2)
        self.logger.info(
            "{} threads, {} greenlets, {} fds, {}MB MEM".format(
                nthreads, ngreenlets, nfds, mb
            )
        )

    @property
    def state(self):
        if self._state == self.STATES.ON:
            if any(writer.active for writer in self.writers.values()):
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
                self.writers.items(), key=lambda item: item[1].scan_number
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
                raise ValueError("No writer for scan {} exists".format(repr(name)))
            ret[name] = getter(writer)
        else:
            for name, writer in sorted(
                self.writers.items(), key=lambda item: item[1].scan_number
            ):
                ret[name] = getter(writer)
        return ret

    def scan_state(self, name=None):
        """
        :param str name: scan name (all scans by default)
        :returns dict: str->ScanWriterState
        """

        def getter(writer):
            return writer.state

        return self._scan_properties(getter, name=name)

    def scan_state_info(self, name=None):
        """
        :param str name: scan name (all scans by default)
        :returns dict: str->(ScanWriterState, str)
        """

        def getter(writer):
            return writer.state, writer.state_reason

        return self._scan_properties(getter, name=name)

    def scan_uri(self, name=None):
        """
        :param str name: scan name (all scans by default)
        :returns dict: str->list(str)
        """

        def getter(writer):
            return writer.uris

        return self._scan_properties(getter, name=name)

    def scan_start(self, name=None):
        """
        :param str name: scan name (all scans by default)
        :returns dict: str->DateTime
        """

        def getter(writer):
            return writer.starttime

        return self._scan_properties(getter, name=name)

    def scan_end(self, name=None):
        """
        :param str name: scan name (all scans by default)
        :returns dict: str->DateTime
        """

        def getter(writer):
            return writer.endtime

        return self._scan_properties(getter, name=name)

    def scan_duration(self, name=None):
        """
        :param str name: scan name (all scans by default)
        :returns dict: str->TimeDelta
        """

        def getter(writer):
            return writer.duration

        return self._scan_properties(getter, name=name)

    def scan_progress(self, name=None):
        """
        :param str name: scan name (all scans by default)
        :returns dict: str->(ScanWriterState, str)
        """

        def getter(writer):
            return writer.progress

        return self._scan_properties(getter, name=name)

    def scan_progress_string(self, name=None):
        """
        :param str name: scan name (all scans by default)
        :returns dict: str->str
        """

        def getter(writer):
            return writer.progress_string

        return self._scan_properties(getter, name=name)

    def scan_info_string(self, name=None):
        """
        :param str name: scan name (all scans by default)
        :returns dict: str->str
        """

        def getter(writer):
            return writer.info_string

        return self._scan_properties(getter, name=name)

    def scan_has_write_permissions(self, name):
        """
        :param str name: scan name
        :returns bool:
        """
        writer = self.writers.get(name, None)
        if writer is None:
            raise RuntimeError("Scan {} does not exist".format(repr(name)))
        else:
            return writer.has_write_permissions


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
    async_utils.log_gevent()
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
