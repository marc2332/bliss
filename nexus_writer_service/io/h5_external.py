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


def swap_flattening_order(lst, shape, order):
    """
    Swap order of flattened list

    :param list lst: flattened shape
    :param tuple shape: original shape of `lst`
    :param str order: flattening order of `lst`
    :returns list:
    """
    if len(shape) <= 1:
        return lst
    if order == "C":
        ofrom, oto = "C", "F"
    elif order == "F":
        ofrom, oto = "F", "C"
    else:
        raise ValueError("Order must be 'C' or 'F'")
    idx = numpy.arange(len(lst))
    idx = idx.reshape(shape, order=oto)
    idx = idx.flatten(order=ofrom)
    return [lst[i] for i in idx]


def add_edf_arguments(filenames, createkwargs=None):
    """
    Arguments for `h5py.create_dataset` to link to EDF data frames.

    :param list(str or tuple) filenames: file names (str) and optionally image indices (tuple)
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
            indices = None
        if ".edf." in os.path.basename(filename):
            raise RuntimeError(
                "{}: external datasets with compression not supported".format(
                    repr(filename)
                )
            )
        if indices:
            img = fabio.open(filename)
            # EdfImage.getframe returns an EdfImage, not a EdfFrame

            def getframe(img):
                return img._frames[img.currentframe]

            it = (getframe(img.getframe(i)) for i in indices)
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
            mkdir(filename)
            EdfImage(data=numpy.full(fillvalue, frame_shape)).write(filename)
        else:
            raise RuntimeError(
                "Dummy file with extension {} not supported".format(repr(ext))
            )
        createkwargs["external"] += [filename] * (enframes - nframes)
    return nframes - enframes


def finalize(createkwargs, order="C", shape=None):
    """
    Finalize external dataset arguments: define shape

    :param dict createkwargs:
    :param tuple shape: scan shape (default: (nframes,))
    :param str order: fill order of shape
    :raises RuntimeError: scan shape does not match number of frames
    """
    nframes = len(createkwargs["external"])
    frame_shape = createkwargs.pop("frame_shape", None)
    if not frame_shape:
        raise RuntimeError("The shape of one external frame must be provided")
    if shape:
        createkwargs["shape"] = shape + frame_shape
        if order == "F":
            external = swap_flattening_order(createkwargs["external"], shape, "C")
            createkwargs["external"] = external
    else:
        createkwargs["shape"] = (nframes,) + frame_shape


def add_arguments(file_format, filenames, shape=None, createkwargs=None):
    """
    Arguments for `h5py.create_dataset` to link to data frames.
    The resulting shape will be `shape + frame_shape`

    :param str file_format:
    :param list(str or tuple) filenames: file names (str) and optionally image indices (tuple)
    :param dict: result of previous call to append to

    :param order(str): refers to the scan dimensions, not the image dimensions
    :returns dict:
    """
    if file_format == "edf":
        return add_edf_arguments(filenames, createkwargs=createkwargs)
    else:
        raise ValueError("Unknown external data format " + repr(file_format))
