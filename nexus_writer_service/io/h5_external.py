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
Utilities for raw external data wrapping in HDF5
"""

import os
import numpy
import fabio
from fabio.edfimage import EdfImage
from .io_utils import mkdir
from ..utils.array_order import Order


def add_edf_arguments(filenames, createkwargs=None):
    """
    Arguments for `h5py.create_dataset` to link to EDF data frames.

    :param list(str or tuple) filenames: file names (str) and optionally
                                         image indices (tuple)
    :param dict: result of previous call to append to
    :returns dict:
    :raises RuntimeError: not supported by external datasets
    """
    if not isinstance(createkwargs, dict):
        createkwargs = {}
    stack = isinstance(filenames, list)
    if stack:
        if not filenames:
            return createkwargs
    else:
        filenames = [filenames]
    shape0 = createkwargs.get("frame_shape", tuple())
    for filename in filenames:
        if isinstance(filename, (tuple, list)):
            filename, indices = filename
            if not isinstance(indices, (tuple, list)):
                indices = [indices]
        else:
            indices = []
        if ".edf." in os.path.basename(filename):
            raise RuntimeError(
                "{}: external datasets with compression not supported".format(
                    repr(filename)
                )
            )
        if indices:
            img = fabio.open(filename)
            it = (img._frames[i] for i in indices)
        else:
            it = EdfImage.lazy_iterator(filename)

        for frame in it:
            if frame.swap_needed():
                raise RuntimeError(
                    "{} (frame {}): external datasets do not support byte-swap".format(
                        repr(filename), frame.iFrame
                    )
                )
            compressioni = frame._data_compression
            if compressioni:
                compressioni = compressioni.lower()
            if compressioni == "none":
                compressioni = None
            if compressioni is not None:
                raise RuntimeError(
                    "{} (frame {}): external datasets with compression not supported".format(
                        repr(filename), frame.iFrame
                    )
                )
            shapei = frame.shape
            if len(shapei) == 1:
                # TODO: bug in fabio?
                shapei = 1, shapei[0]
            dtypei = frame.dtype
            start = frame.start
            size = frame.size  # TODO: need compressed size
            external = filename, start, size

            def assertEqual(key, value, evalue):
                if value != evalue:
                    raise RuntimeError(
                        "{} (frame {}): {} = {} instead of {}".format(
                            repr(filename), frame.iFrame, repr(key), value, evalue
                        )
                    )

            if shape0:
                assertEqual("shape", shapei, shape0)
            else:
                createkwargs["frame_shape"] = shape0 = shapei
            if "dtype" in createkwargs:
                assertEqual("dtype", dtypei, createkwargs["dtype"])
            else:
                createkwargs["dtype"] = dtypei
            if "compression" in createkwargs:
                assertEqual("compression", compressioni, createkwargs["compression"])
            else:
                createkwargs["compression"] = compressioni
            if "external" in createkwargs:
                createkwargs["external"].append(external)
            else:
                createkwargs["external"] = [external]
    return createkwargs


def resize(createkwargs, enframes, filename, fillvalue):
    """
    Add/remove external files (before finalization).

    :param dict createkwargs:
    :param enframes shape: number of frames
    :param str filename: in case not enough external files
    :param num fillvalue: in case not enough external files
    :returns int: number of frames skipped
    """
    frame_shape = createkwargs.get("frame_shape", None)
    if not frame_shape:
        raise RuntimeError("The shape of one external frame must be provided")
    nframes = len(createkwargs["external"])
    if nframes > enframes:
        createkwargs["external"] = createkwargs["external"][:enframes]
    elif nframes < enframes:
        if nframes:
            ext = os.path.splitext(createkwargs["external"][0])[-1]
        else:
            ext = ".edf"
        if os.path.splitext(filename)[-1] != ext:
            filename += ext
        if ext == ".edf":
            mkdir(os.path.dirname(filename))
            if not frame_shape:
                frame_shape = 1, 1
            elif len(frame_shape) == 1:
                frame_shape = 1, frame_shape[0]
            EdfImage(data=numpy.full(fillvalue, frame_shape)).write(filename)
        else:
            raise RuntimeError(
                "Dummy file with extension {} not supported".format(repr(ext))
            )
        createkwargs["external"] += [filename] * (enframes - nframes)
    return nframes - enframes


def finalize(createkwargs, addorder=None, fillorder=None, shape=None):
    """
    Finalize external dataset arguments: define shape

    :param dict createkwargs:
    :param tuple shape: scan shape (default: (nframes,))
    :param Order addorder: add order to external
    :param Order fillorder: fill order of shape
    :raises RuntimeError: scan shape does not match number of frames
    """
    nframes = len(createkwargs["external"])
    frame_shape = createkwargs.pop("frame_shape", None)
    if not frame_shape:
        raise RuntimeError("The shape of one external frame must be provided")
    if shape:
        createkwargs["shape"] = shape + frame_shape
        if not isinstance(addorder, Order):
            addorder = Order(addorder)
        if not isinstance(fillorder, Order):
            fillorder = Order(fillorder)
        if fillorder.forder:
            raise ValueError("External HDF5 datasets are always saved in C-order")
        createkwargs["external"] = addorder.swap_list(
            createkwargs["external"], shape, fillorder
        )
    else:
        createkwargs["shape"] = (nframes,) + frame_shape


def add_arguments(filenames, createkwargs=None):
    """
    Arguments for `h5py.create_dataset` to link to data frames.
    The resulting shape will be `shape + frame_shape`

    :param list(str or tuple) filenames: file names (str) and optionally image indices (tuple)
    :param dict createkwargs: result of previous call to append to
    :returns dict:
    """
    if not filenames:
        return
    first = filenames[0]
    if isinstance(first, (tuple, list)):
        first = first[0]
    file_format = os.path.splitext(first)[-1].lower()
    if file_format == ".edf":
        return add_edf_arguments(filenames, createkwargs=createkwargs)
    else:
        raise ValueError("Unknown external data format " + repr(file_format))
