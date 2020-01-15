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


import os
import errno
import random
import tempfile
import string


def tempname(
    size=6, chars=string.ascii_lowercase + string.digits, prefix="", suffix=""
):
    """
    Random name with prefix and suffix
    """
    # Number of combinations: n^size  (default: 62^6)
    name = "".join(random.choice(chars) for _ in range(size))
    return prefix + name + suffix


def temproot():
    """
    OS tmp directory
    """
    return tempfile.gettempdir()


def tempdir(root=None, **kwargs):
    """
    Random directory in OS tmp directory
    """
    if not root:
        root = temproot()
    return os.path.join(root, tempname(**kwargs))


def mkdir(path):
    """
    Create directory recursively and silent when already existing

    :param str path:
    """
    if path:
        path = os.path.abspath(path)
        os.makedirs(path, exist_ok=True)


def close_files(*fds):
    exceptions = []
    for fd in fds:
        try:
            if fd is None:
                continue
            try:
                os.close(fd)
            except OSError as e:
                if e.errno == errno.EBADF:
                    pass
                else:
                    raise
        except Exception as e:
            exceptions.append(e)
    if exceptions:
        raise Exception(exceptions)
