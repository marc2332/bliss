# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os


def find_existing(path):
    """Returns `path` or one of its parent directories.

    :param str path:
    :returns str or None:
    """
    path = os.path.normpath(path)
    while not os.path.exists(path):
        previous = path
        path = os.path.dirname(path)
        if path == previous:
            break
    if not os.path.exists(path):
        return
    return path


def has_required_disk_space(path, required_disk_space):
    """
    :param str path: may not exist yet
    :param num required_disk_space: is MB
    :returns bool: also returns `True` when no path was found
    """
    if required_disk_space <= 0:
        return True
    path = find_existing(path)
    if not path:
        return True
    statvfs = os.statvfs(path)
    free_space = statvfs.f_frsize * statvfs.f_bavail / 1024 ** 2
    return free_space >= required_disk_space


def has_write_permissions(path):
    """
    :param str path: may not exist yet
    :returns bool:
    """
    if os.path.exists(path):
        return os.access(path, os.W_OK)
    else:
        # Check whether we can create the path
        path = os.path.dirname(os.path.normpath(path))
        path = find_existing(path)
        if path and os.path.isdir(path):
            return os.access(path, os.W_OK)
        else:
            return False
