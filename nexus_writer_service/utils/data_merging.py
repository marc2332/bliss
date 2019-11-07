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

import numpy
import itertools
import logging


logger = logging.getLogger(__name__)


def createSlice(start, end, stride):
    """
    :param int start: start index
    :param int end: end index
    :param stride:
    :returns slice or int: integer when stride is zero
    """
    if stride:
        end += stride
        if stride < 0 and end < 0:
            end = None
        return slice(start, end, stride)
    else:
        return start


def intListToSliceIndexing(coord, slicetwo=False, allow_negative_stride=False):
    """
    Convert lists of integers to slices and/or integers

    :param tuple(array(int)) coord:
    :yields tuple(slice or int): same length as `coord`
    """
    coord = numpy.asarray(coord)
    ndim, ncoord = coord.shape
    # print('\n')
    # print(numpy.concatenate([coord, numpy.arange(ncoord)[None,:]], axis=0))

    # Determine slices
    strides = numpy.diff(coord, axis=1)
    # print(numpy.concatenate([numpy.zeros((ndim,1),dtype=int), strides], axis=1))
    diff = numpy.diff(strides, axis=1)
    newslices = numpy.any(diff, axis=0)
    if not allow_negative_stride:
        negative_strides = numpy.any(strides < 0, axis=0)
        newslices |= negative_strides[1:]

    def getstrides(start):
        try:
            return strides[:, start]
        except IndexError:
            return numpy.ones_like(coord[:, start])

    # Create a slice from start and stop index
    def makeslice(start, end):
        _start = coord[:, start]
        _end = coord[:, end]
        _strides = getstrides(start)
        if not allow_negative_stride:
            if (_strides < 0).any():
                lst = [
                    list(range(start, end + stride, stride)) if stride else [start]
                    for start, end, stride in zip(_start, _end, _strides)
                ]
                n = max(map(len, lst))
                lst = [e * n if len(e) == 1 else e for e in lst]
                for idx in zip(*lst):
                    yield tuple(idx)
                return
        yield tuple(createSlice(*args) for args in zip(_start, _end, _strides))

    def split2(start, end):
        if slicetwo:
            return False
        if start + 1 == end:
            if allow_negative_stride:
                return True
            else:
                return (getstrides(start) < 0).any()
        else:
            return False

    # Yield the slices
    start = 0
    skip = False
    for end, newslice in enumerate(newslices, 1):
        if skip:
            skip = False
        elif newslice:
            if start + 1 == end and not slicetwo:
                yield tuple(coord[:, start])
                start = end
            else:
                for idx in makeslice(start, end):
                    yield idx
                start = end + 1
                skip = True

    # Yield the last slice
    end = ncoord - 1
    if start == end:
        yield tuple(coord[:, start])
    elif start + 1 == end and not slicetwo:
        a = tuple(coord[:, start])
        b = tuple(coord[:, end])
        yield a
        if a != b:
            yield b
    else:
        for idx in makeslice(start, end):
            yield idx


def intListToSliceIndexing2(coordrange, coord):
    """
    Convert lists of integers to slices and/or integers

    :param array(int) coordrange: a range with step one
    :param tuple(array(int)) coord:
    :yields tuple, tuple:
    """
    start = 0
    for idx in intListToSliceIndexing(coord, slicetwo=True):
        for s in idx:
            if isinstance(s, slice):
                stop = start + (s.stop - s.start) // s.step
                idxflat = slice(coordrange[start], coordrange[stop - 1] + 1, 1)
                start = stop
                break
        else:
            idxflat = coordrange[start]
            start += 1
        yield (idxflat,), idx


def _mergedShape(shapes, axis=0, newaxis=True):
    """
    Shape after merging

    :param list(tuple) shapes:
    :param int axis: merge along this axis
    :param bool newaxis: merge axis is new or existing
    :returns tuple or None:
    """
    if not shapes:
        return None
    shape = list(shapes[0])
    if newaxis:
        if axis < 0:
            axis += len(shape) + 1
        shape.insert(axis, len(shapes))
    else:
        shape[axis] = 0
        for s in shapes:
            shape[axis] += s[axis]
    return tuple(shape)


def mergeShapeGenerator(sources, shapes, mshape, axis=0, newaxis=True):
    """
    Merge I/O index generator.

    :param list(any) sources:
    :param list(tuple) shapes: of sources
    :param tuple mshape: merged shape
    :param int axis: merge along this axis
    :param bool newaxis: merge axis is new or existing
    :returns generator: index generator
    """
    logger.debug(
        "{} --{}--> {}".format(shapes, "stack" if newaxis else "concat", mshape)
    )
    if len(sources) == 1:

        def fill_generator():
            def index_generator():
                yield tuple(), tuple()

            yield sources[0], index_generator

    else:

        def fill_generator():
            idx = [slice(None)] * len(mshape)
            n = 0
            for i, (source, shapei) in enumerate(zip(sources, shapes)):
                if newaxis:
                    idx[axis] = i
                else:
                    idx[axis] = slice(n, n + shapei[axis])
                    n += shapei[axis]

                def index_generator():
                    yield tuple(), tuple(idx)

                yield source, index_generator

    return fill_generator


def _countCommonFastAxes(shapein, shapeout, newshapeout, order=None):
    """
    Full index along common fast axes.

    :param tuple shapein: slice of `shapeout`
    :param tuple shapeout:
    :param tuple newshapeout: reshape `shapeout`
    :param str or None order:
    :returns tuple(int):
    """
    # Fast axis first
    if order != "F":
        shapein = shapein[::-1]
        shapeout = shapeout[::-1]
        newshapeout = newshapeout[::-1]

    shapein = numpy.array(shapein)
    arrin = numpy.cumprod(shapein)[:-1]
    shapeout = numpy.array(shapeout)
    arrout = numpy.cumprod(shapeout)[:-1]
    newshapeout = numpy.array(newshapeout)
    arroutnew = numpy.cumprod(newshapeout)[:-1]
    n = min([arrin.size, arrout.size, arroutnew.size])
    if not n:
        return 0, 0, 0
    b = numpy.where(
        (arrin[:n] == arroutnew[:n])
        & (arrin[:n] == arrout[:n])
        & (arrout[:n] == arroutnew[:n])
    )[0]
    if not b.size:
        return 0, 0, 0

    # Number of fast axis to skip
    m = arrin[b[-1]]
    nin = numpy.where(arrin == m)[0][-1] + 1
    nout = numpy.where(arrout == m)[0][-1] + 1
    noutnew = numpy.where(arroutnew == m)[0][-1] + 1
    return nin, nout, noutnew


def _getCoordinates(
    shape, ran, nskipfast, newshape, newnskipfast, nsources=1, order=None
):
    """
    Coordinates of all elements in `newshape` except the ones on
    the skipped fast axes.

    :param tuple shape: 
    :param list(list) ran: same length as `shape`
    :param int nskipfast: number of fast axes in `shape` to skip
    :param tuple newshape: reshaped `shape`
    :param int nsources:
    :param str or None order:
    :returns tuple(list): same length as `newshape`
    """
    # C: fast axis last
    # F: fast axis first
    # itertools.product: fast axis is last
    if nskipfast:
        if order == "F":
            ran = ran[nskipfast:]
            shape = shape[nskipfast:]
        else:
            ran = ran[:-nskipfast]
            shape = shape[:-nskipfast]
    if newnskipfast:
        if order == "F":
            newshape = newshape[newnskipfast:]
        else:
            newshape = newshape[:-newnskipfast]
    if nsources > 1:
        if order == "F":
            idx = tuple(zip(*itertools.product(*ran[::-1])))[::-1]
        else:
            idx = tuple(zip(*itertools.product(*ran)))
        flatidx = numpy.ravel_multi_index(idx, shape, order=order)
    else:
        flatidx = numpy.arange(numpy.product(shape))
    return numpy.unravel_index(flatidx, newshape, order=order)


def mergeReshapeGenerator(
    sources,
    shapes,
    shapeout,
    newshapeout,
    order=None,
    axis=0,
    newaxis=True,
    allow_advanced_indexing=True,
):
    """
    Reshaped merge I/O index generator.

    :param list(any) sources:
    :param list(tuple) shapes: of sources
    :param tuple shapeout: merged `shapes`
    :param tuple newshapeout: reshaping shapeout
    :param str order: for reshaping ('C': fast axis last, 'F': fast axis first)
    :param int axis: merge along this axis
    :param bool newaxis: merge axis is new or existing
    :param bool allow_advanced_indexing:
    :returns generator: index generator
    """
    logger.debug(
        "{} --{}--> {} --{}--> {}".format(
            shapes, "stack" if newaxis else "concat", shapeout, order, newshapeout
        )
    )
    nsources = len(sources)

    def fill_generator():
        noutconcat = 0
        for i, (source, shapein) in enumerate(zip(sources, shapes)):
            # Indices per dimension
            ranin = [list(range(s)) for s in shapein]
            ranout = [list(range(s)) for s in shapeout]
            if newaxis:
                ranout[axis] = [i]
            else:
                n = noutconcat + shapein[axis]
                ranout[axis] = list(range(noutconcat, n))
                noutconcat = n

            # Indices for full dimensions
            if newaxis and nsources in shapein:
                nskipin, nskipout, nskipoutnew = 0, 0, 0
            else:
                nskipin, nskipout, nskipoutnew = _countCommonFastAxes(
                    shapein, shapeout, newshapeout, order=order
                )
            fastidxin = (slice(None),) * nskipin
            fastidxoutnew = (slice(None),) * nskipoutnew

            # Indices for other dimensions
            coordin = _getCoordinates(
                shapein, ranin, nskipin, shapein, nskipin, nsources=1, order=order
            )
            coordout = _getCoordinates(
                shapeout,
                ranout,
                nskipout,
                newshapeout,
                nskipoutnew,
                nsources=nsources,
                order=order,
            )
            flatin = len(coordin) == 1
            flatout = len(coordout) == 1

            # Add full indices
            if order == "F":

                def fout(tpl):
                    return fastidxoutnew + tpl

                def fin(tpl):
                    return fastidxin + tpl

            else:

                def fout(tpl):
                    return tpl + fastidxoutnew

                def fin(tpl):
                    return tpl + fastidxin

            # Create index generator
            noreduction = False
            if allow_advanced_indexing:
                # Index type: list of integers
                def index_generator():
                    yield fin(coordin), fout(coordout)

            elif noreduction:
                # Index type: integers
                def index_generator():
                    for idxin, idxout in zip(zip(*coordin), zip(*coordout)):
                        yield fin(idxin), fout(idxout)

            elif flatin:

                def index_generator():
                    for idxin, idxout in intListToSliceIndexing2(coordin[0], coordout):
                        yield fin(idxin), fout(idxout)

            elif flatout:

                def index_generator():
                    for idxout, idxin in intListToSliceIndexing2(coordout[0], coordin):
                        yield fin(idxin), fout(idxout)

            else:
                # Index type: integers and slices
                n = len(coordin)
                coord = coordin + coordout

                def index_generator():
                    for idx in intListToSliceIndexing(coord):
                        yield fin(idx[:n]), fout(idx[n:])

            yield source, index_generator

    return fill_generator


def mergeGenerator(
    sources,
    shapes,
    axis=0,
    newaxis=True,
    shape=None,
    order=None,
    allow_advanced_indexing=True,
):
    """
    Equivalent to `numpy.stack` or `numpy.concatenate` combined
    with `numpy.reshape`. Return I/O index generator for merging.

    :param list(any) sources:
    :param list(tuple) shapes: of sources
    :param int axis: merge along this axis
    :param bool newaxis: merge axis is new or existing
    :param tuple shape: for reshaping
    :param str order: for reshaping
    :param bool allow_advanced_indexing:
    :returns tuple, generator: merged shape and index generator
    """
    mshape = _mergedShape(shapes, axis=axis, newaxis=newaxis)
    if not mshape:

        def fill_generator():
            return
            yield None

    elif shape is None or shape == mshape:
        fill_generator = mergeShapeGenerator(
            sources, shapes, mshape, axis=axis, newaxis=newaxis
        )
        shape = mshape
    else:
        fill_generator = mergeReshapeGenerator(
            sources,
            shapes,
            mshape,
            shape,
            order=order,
            axis=axis,
            newaxis=newaxis,
            allow_advanced_indexing=allow_advanced_indexing,
        )
    return shape, fill_generator
