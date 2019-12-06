# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Helper to expose an object as a RPC server
"""

import gevent
import contextlib
import tempfile
import logging

from bliss.comm import rpc
from bliss.config.conductor.client import get_redis_connection
from bliss.flint import config


_logger = logging.getLogger(__name__)


@contextlib.contextmanager
def safe_rpc_server(obj):
    with tempfile.NamedTemporaryFile(delete=False) as f:
        url = "ipc://{}".format(f.name)
        server = rpc.Server(obj, stream=True)
        try:
            server.bind(url)
            task = gevent.spawn(server.run)
            yield task, url
            task.kill()
            task.join()
        except Exception:
            _logger.error("Exception while serving %s", url, exc_info=True)
            raise
        finally:
            server.close()


@contextlib.contextmanager
def maintain_value(key, value):
    redis = get_redis_connection()
    redis.lpush(key, value)
    yield
    redis.delete(key)


class FlintServer:
    def __init__(self, flintApi):
        self.stop = gevent.event.AsyncResult()
        self.thread = gevent.spawn(self._task, flintApi, self.stop)

    def _task(self, flint, stop):
        key = config.get_flint_key()
        with safe_rpc_server(flint) as (task, url):
            with maintain_value(key, url):
                gevent.wait([stop, task], count=1)

    def join(self):
        self.stop.set_result(True)
        self.thread.join()
