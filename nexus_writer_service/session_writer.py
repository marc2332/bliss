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
import os
import errno
import logging
from bliss.data.node import get_session_node
from .utils import async_utils
from .utils import logging_utils
from .scan_writers import writer_base
from .scan_writers import writer_config


logger = logging.getLogger(__name__)


cli_saveoptions = {
    "noconfig": (
        {
            "action": "store_true",
            "help": "Do not use extra writer information from Redis",
        },
        "noconfig",
    )
}


def all_cli_saveoptions(noconfig=False):
    if noconfig:
        ret = dict(writer_base.cli_saveoptions)
    else:
        ret = dict(writer_config.cli_saveoptions)
    ret.update(cli_saveoptions)
    return ret


def default_saveoptions(noconfig=False):
    if noconfig:
        return writer_base.default_saveoptions
    else:
        return writer_config.default_saveoptions


def close_pipe(file_descriptor):
    try:
        os.close(file_descriptor)
    except OSError as e:
        if e.errno == errno.EBADF:
            pass
        else:
            raise e


def session_writer(session_name, noconfig=False, **saveoptions):
    """
    Listen to session scan events and spawn a writer for each new scan.

    :param str session_name:
    :param str noconfig: generic or configurable writer
    :param **saveoptions:
    """
    if noconfig:
        writerclass = writer_base.NexusScanWriterBase
    else:
        writerclass = writer_config.NexusScanWriterConfigurable
    session_node = get_session_node(session_name)  # bliss.data.node.DataNode
    writers = {}
    default = None, None, None
    locks = async_utils.SharedLockPool()
    sessionlogger = logging_utils.CustomLogger(logger, "Session " + repr(session_name))
    try:
        sessionlogger.info("Start listening to scans ...")
        for event_type, node in session_node.iterator.walk_on_new_events(filter="scan"):
            if event_type.name == "NEW_NODE":
                sessionlogger.info("NEW_NODE received for scan {}".format(node.name))
                # Scan starts: launch separate writer thread
                fd_read, fd_write = os.pipe()
                writer = writerclass(
                    node, locks, fd_read, parentlogger=sessionlogger, **saveoptions
                )
                writer.start()
                writers[node.db_name] = writer, fd_read, fd_write
            elif event_type.name == "END_SCAN":
                # Scan ends: trigger EXTERNAL_EVENT on scan node
                writer, fd_read, fd_write = writers.get(node.db_name, default)
                if fd_write is not None:
                    sessionlogger.info(
                        "END_SCAN received for scan {}".format(node.name)
                    )
                    os.write(fd_write, b"END_SCAN received")
                # Purge dead writers
                for node_db_name in list(writers.keys()):
                    writer, fd_read, fd_write = writers.get(node_db_name, default)
                    if writer is not None:
                        if not writer:
                            writers.pop(node_db_name, None)
                            close_pipe(fd_write)
                            close_pipe(fd_read)
                # Show the active writers
                if writers:
                    sessionlogger.info(
                        "Running writers: {}".format(
                            [repr(writer) for writer, _, _ in writers.values()]
                        )
                    )
    except gevent.GreenletExit:
        sessionlogger.info("Stop listening to scans ...")
        if writers:
            greenlets = []
            pipes = []
            for writer, fd_read, fd_write in writers.values():
                pipes.append(fd_read)
                pipes.append(fd_write)
                if writer:
                    writer.kill()
                    greenlets.append(writer)
            if greenlets:
                sessionlogger.info("Stop writers {} ...".format(greenlets))
            else:
                sessionlogger.info("No running writers to kill.")
            gevent.joinall(greenlets)
            for file_descriptor in pipes:
                close_pipe(file_descriptor)
        else:
            sessionlogger.info("No running writers to kill.")
    sessionlogger.info("Listener exits.")


def start_session_writer(session_name, **saveoptions):
    """
    This starts the main session writer in a Greenlet.

    :param str session_name: does not need to exist yet
    :param **saveoptions: see `session_writer`
    :returns Greenlet:
    """
    greenlet = gevent.spawn(session_writer, session_name, **saveoptions)
    async_utils.kill_on_exit(greenlet)
    return greenlet


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
    for attr, (okwargs, option) in _cli_saveoptions.items():
        parser.add_argument("--" + attr, **okwargs)
    # Parse CLI arguments
    args, unknown = parser.parse_known_args()
    kwargs = {}
    _cli_saveoptions = all_cli_saveoptions(noconfig=args.noconfig)
    for attr, (_, option) in _cli_saveoptions.items():
        try:
            kwargs[option] = getattr(args, attr)
        except AttributeError:
            continue
    # Launch the session writer
    logid = "Session " + repr(args.session_name)
    sessionlogger = logging_utils.CustomLogger(logger, logid)
    greenlet = start_session_writer(args.session_name, **kwargs)
    greenlet.join()
    sessionlogger.info("Nexus writer exits")


if __name__ == "__main__":
    main()
