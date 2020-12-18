# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
"""
Provides plot helper class to deal with flint proxy.
"""
import contextlib
from bliss.flint import config as flint_config
from bliss.config.conductor.client import get_default_connection
from bliss import current_session


@contextlib.contextmanager
def draw_manager(plot):
    """Context manager to inhibit the repaint of a plot during the
    context."""
    try:
        # disable the silx auto_replot to avoid refreshing the GUI for each curve plot (when calling plot.select_data(...) )
        plot.submit("setAutoReplot", False)
        yield
    except AssertionError:
        # ignore eventual AssertionError raised by the rpc com
        pass
    finally:
        # re-enable the silx auto_replot
        plot.submit("setAutoReplot", True)


def clean_up_user_data():
    """Helper to clean up the data stored in Redis and used by Flint.

    Flint should be able to deal with durty data, but in case of stronger
    problem this could help a lot (for example if the layout is really broken).

    As result all the saved user preferences will be lost.
    """
    session_name = current_session.name
    beacon = get_default_connection()
    redis = beacon.get_redis_proxy()

    # get existing keys, if any

    # Old keys from BLISS <= 1.6dev
    key = flint_config.get_workspace_key(session_name)
    pattern = f"{key}*"
    for key in redis.scan_iter(pattern):
        key = key.decode()
        redis.delete(key)

    key = flint_config.get_workspace_key(None)
    pattern = f"{key}*"
    for key in redis.scan_iter(pattern):
        key = key.decode()
        redis.delete(key)
