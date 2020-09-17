# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import gevent
import logging
from bliss.common import scans
from nexus_writer_service.subscribers.base_subscriber import BaseSubscriber
from nexus_writer_service.utils import process_utils
from nexus_writer_service import logger

logger.setLevel(logging.INFO)


class CountNodesSubscriber(BaseSubscriber):
    """Redis node subscriber which counts NEW_NODE events
    """

    def __init__(self, *args, **kwargs):
        self._progress = 0
        self.delay = 0
        super().__init__(*args, **kwargs)

    def _event_loop_initialize(self, **kwargs):
        self._progress = 0
        super()._event_loop_initialize(**kwargs)

    def _event_new_node(self, node):
        super()._event_new_node(node)
        self._progress += 1
        gevent.sleep(self.delay)

    @property
    def progress(self):
        return self._progress


def wait_finished(subscriber, successfull=True):
    with gevent.Timeout(3):
        while subscriber.active:
            gevent.sleep(0.1)
    if successfull:
        assert subscriber.state == subscriber.STATES.OFF
    else:
        assert subscriber.state == subscriber.STATES.FAULT
    subscriber.join(timeout=3)
    assert not subscriber.active
    assert not subscriber.alive


def test_base_subscriber(session):
    # Define scan
    env_dict = session.env_dict
    db_root = ":".join(name for name, _ in session.scan_saving.get()["db_path_items"])
    detectors = [env_dict["diode"], env_dict["thermo_sample"]]
    # subscan, elapsed_time, epoch, controller, diode, controller, thermo_sample
    nnodes = 7
    scan = scans.loopscan(10, .1, *detectors, save=False, run=False)

    # Instantiate subscriber to scan node
    db_name = db_root + ":_{:0d}_{}".format(1, scan.name)
    subscriber = CountNodesSubscriber(db_name, node_type="scan")

    # Listen during scan
    msg = "Listen during scan"
    subscriber.logger.info(f"\n\n{msg}\n")
    subscriber.start(wait=True, timeout=3)
    scan.run()
    wait_finished(subscriber, successfull=True)
    assert subscriber.progress == nnodes, msg
    resources = process_utils.ResourceMonitor()
    resources.start()

    # Listen after scan
    msg = "Listen after scan"
    subscriber.logger.info(f"\n\n{msg}\n")
    subscriber.start(wait=True, timeout=3)
    wait_finished(subscriber, successfull=True)
    assert subscriber.progress == nnodes, msg
    resources.check_leaks(msg=msg)

    # Give us the chance to stop/kill while processing events
    subscriber.delay = 0.2

    # Stop
    for i, successfull in enumerate([True, False, False, True]):
        msg = f"stop {i}"
        subscriber.logger.info(f"\n\n{msg}\n")
        subscriber.start(wait=True, timeout=3)
        subscriber.stop(successfull=successfull)
        wait_finished(subscriber, successfull=successfull)
        resources.check_leaks(msg=msg)

    # Kill
    msg = "kill"
    subscriber.logger.info(f"\n\n{msg}\n")
    subscriber.start(wait=True, timeout=3)
    subscriber.kill()
    wait_finished(subscriber, successfull=False)
    resources.check_leaks(msg=msg)
