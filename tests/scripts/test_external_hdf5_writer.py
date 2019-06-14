# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import gevent
import pprint
import collections.abc
import numpy

from scripts.produce_hdf5.produce_hdf5 import listen_to_session_wait_for_scans
from bliss.common import scans
from silx.io.dictdump import h5todict


def h5_scan_name(scan_info):
    return str(scan_info["scan_nb"]) + "_" + scan_info["type"]


def deep_compare(d, u):
    """using logic of deep update used here to compare two dicts 
    """
    stack = [(d, u)]
    while stack:
        d, u = stack.pop(0)
        assert len(d) == len(u)
        for k, v in u.items():
            assert k in d
            if not isinstance(v, collections.abc.Mapping):
                if isinstance(v, numpy.ndarray) and v.size > 1:
                    assert all(d[k].flatten() == v.flatten())
                else:
                    assert d[k] == v
            else:
                stack.append((d[k], v))


def test_external_hdf5_writer(alias_session, scan_tmpdir):

    env_dict, session = alias_session

    # put scan file in a tmp directory
    env_dict["SCAN_SAVING"].base_path = str(scan_tmpdir)

    # this scan is only to set up the file path in pytest
    s = scans.ascan(env_dict["robyy"], 0, 1, 3, .1, env_dict["lima_simulator"])

    event = gevent.event.Event()
    g = gevent.spawn(listen_to_session_wait_for_scans, "test_alias", event=event)

    s = scans.ascan(env_dict["robyy"], 0, 1, 3, .1, env_dict["lima_simulator"])

    gevent.sleep(.5)
    g.kill()

    external_writer = h5todict(s.scan_info["filename"].replace(".", "_external."))[
        h5_scan_name(s.scan_info)
    ]
    bliss_writer = h5todict(s.scan_info["filename"])[h5_scan_name(s.scan_info)]
    deep_compare(external_writer, bliss_writer)
