# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import stat
from contextlib import contextmanager


WRITE_FLAGS = (
    stat.S_IWGRP | stat.S_IWUSR | stat.S_IWOTH | stat.SF_IMMUTABLE | stat.UF_IMMUTABLE
)


def _chmod_disable(path, flags):
    st_mode = os.stat(path).st_mode
    os.chmod(path, st_mode & (~flags))


def _chmod_enable(path, flags):
    st_mode = os.stat(path).st_mode
    os.chmod(path, st_mode | flags)


@contextmanager
def _restore_permissions(path):
    st_mode = os.stat(path).st_mode
    try:
        yield
    finally:
        os.chmod(path, st_mode)


@contextmanager
def disable_write_permissions(path):
    with _restore_permissions(path):
        _chmod_disable(path, WRITE_FLAGS)
        yield not os.access(path, os.W_OK)


@contextmanager
def enable_write_permissions(path):
    with _restore_permissions(path):
        _chmod_enable(path, WRITE_FLAGS)
        yield os.access(path, os.W_OK)
