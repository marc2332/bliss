# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import gc
import gevent
from bliss.common import scans
from nexus_writer_service.subscribers.base_subscriber import BaseSubscriber
from nexus_writer_service.utils import process_utils

import logging
from nexus_writer_service import logger

logger.setLevel(logging.INFO)


class CountNodesSubscriber(BaseSubscriber):
    def __init__(self, *args, **kwargs):
        self._progress = 0
        super().__init__(*args, **kwargs)

    def _event_loop_initialize(self):
        self._progress = 0
        super()._event_loop_initialize()

    def _event_new_node(self, node):
        super()._event_new_node(node)
        self._progress += 1

    @property
    def progress(self):
        return self._progress


def _start(subscriber):
    with gevent.Timeout(3):
        subscriber.start()
        while subscriber.state != subscriber.STATES.ON:
            gevent.sleep(0.1)


def _wait_finished(subscriber, successfull=True):
    if successfull:
        state = subscriber.STATES.OFF
    else:
        state = subscriber.STATES.FAULT
    with gevent.Timeout(3):
        while subscriber.state != state:
            gevent.sleep(0.1)
        while subscriber.active:
            gevent.sleep(0.1)


def test_base_subscriber(session):
    env_dict = session.env_dict
    db_root = ":".join(name for name, _ in session.scan_saving.get()["db_path_items"])
    detectors = [env_dict["diode"], env_dict["diode3"], env_dict["diode4"]]
    # scan, subscan, elapsed_time, epoch, controller, diode, diode3, diode4
    nnodes = 5 + len(detectors)

    scan = scans.loopscan(10, .1, *detectors, save=False, run=False)
    db_name = db_root + ":{:0d}_{}".format(1, scan.name)
    subscriber = CountNodesSubscriber(db_name, node_type="scan")

    # Listen
    msg = "iteration 0"
    _start(subscriber)
    scan.run()
    del scan
    subscriber.stop(successfull=True)
    _wait_finished(subscriber, successfull=True)
    # TODO: why do we have more NEW_NODE events?
    nnodes = 4 + 2 * len(detectors)
    assert subscriber.progress == nnodes, msg

    # Resources
    while gc.collect():
        pass
    glts = process_utils.greenlets()
    fds = process_utils.file_descriptors()

    # TODO: why do we have more NEW_NODE events?
    nnodes = 4 + len(detectors) * (len(detectors) + 1)
    for i, successfull in enumerate([True, False, False, False]):
        msg = f"iteration {i}"
        _start(subscriber)
        subscriber.stop(successfull=successfull)
        _wait_finished(subscriber, successfull=successfull)
        assert subscriber.progress == nnodes, msg
        while gc.collect():
            pass
        new_glts = process_utils.greenlets()
        assert glts == new_glts, msg
        process_utils.raise_fd_diff(fds, prefix=msg)
