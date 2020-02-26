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
import tempfile as _tempfile
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
    return _tempfile.gettempdir()


def tempdir(root=None, **kwargs):
    """
    Random directory in OS tmp directory
    """
    if not root:
        root = temproot()
    return os.path.join(root, tempname(**kwargs))


tempfile = tempdir


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
        except BaseException as e:
            exceptions.append(e)
    if exceptions:
        raise Exception(exceptions)


def rotatefiles(filename, nmax=10):
    """
    Rename or delete existing file.

    :param str filename:
    :param int nmax:
    """
    mkdir(os.path.dirname(filename))
    filenamegen = rotatefiles_gen(filename, nmax)
    _rotatefiles(filename, filenamegen)


def _rotatefiles(filename, filenamegen):
    """
    Rename or delete existing file

    :param str filename:
    :param generator filenamegen:
    """
    if os.path.exists(filename):
        try:
            nextname = next(filenamegen)
        except StopIteration:
            os.remove(filename)
        else:
            _rotatefiles(nextname, filenamegen)
            os.rename(filename, nextname)


def rotatefiles_gen(filename, nmax):
    """
    Generate rotating file names (maximal nmax files)

    :param str filename:
    :param int nmax:
    """
    if nmax > 1:
        base, ext = os.path.splitext(filename)
        fmt = "{}.{{}}{}".format(base, ext)
        for i in range(1, nmax):
            yield fmt.format(i)
