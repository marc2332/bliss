# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import numpy
import itertools
from nexus_writer_service.utils import data_merging
from nexus_writer_service.utils.array_order import Order
from nxw_test_math import asproduct


def test_data_merging_general():
    shape = 3, 7
    dtype = float
    data = numpy.arange(numpy.product(shape), dtype=dtype)
    data = data.reshape(shape)
    axis = 0, 1, -1
    newaxis = True, False
    reshape = False, True
    order = Order("C"), Order("F")
    advanced = False, True

    options = itertools.product(axis, newaxis, reshape, order, advanced)
    for axis, newaxis, reshape, order, advanced in options:
        kwargs = {
            "axis": axis,
            "newaxis": newaxis,
            "order": order,
            "allow_advanced_indexing": advanced,
        }
        sources = [data] * 3
        shapes = [shape] * 3
        if not newaxis:
            extrashape = list(shape)
            extrashape[axis] *= 2
            extrashape = tuple(extrashape)
            extradata = numpy.arange(numpy.product(extrashape), dtype=dtype)
            extradata = extradata.reshape(extrashape)
            sources.append(extradata)
            shapes.append(extrashape)
        if newaxis:
            edata = numpy.stack(sources, axis=axis)
        else:
            edata = numpy.concatenate(sources, axis=axis)
        if reshape:
            dshape = edata.shape
            it = asproduct(numpy.product(dshape), 3, includeone=False)
            nshape = next(it)
            while nshape == dshape:
                nshape = next(it)
            edata = order.reshape(edata, nshape)
        else:
            nshape = None
        mshape, fillgen = data_merging.mergeGenerator(
            sources, shapes, shape=nshape, **kwargs
        )
        mdata = numpy.empty(shape=mshape, dtype=dtype)
        for ndarray, idx_generator in fillgen():
            for idxin, idxout in idx_generator():
                for idx in idxin, idxout:
                    isadvanced = any(isinstance(x, numpy.ndarray) for x in idx)
                    assert isadvanced == (advanced and reshape)
                mdata[idxout] = ndarray[idxin]
        numpy.testing.assert_array_equal(edata, mdata)


def test_data_merging_single():
    order = Order("C"), Order("F")
    advanced = False, True
    options = itertools.product(order, advanced)
    dshape = 13, 14
    scanshape1 = 6, 2, 3
    scanshape2 = (numpy.product(scanshape1, dtype=int),)
    for order, advanced in options:
        if order.order == "C":
            shape1 = scanshape1 + dshape
            shape2 = scanshape2 + dshape
        else:
            shape1 = dshape + scanshape1
            shape2 = dshape + scanshape2
        n = numpy.product(shape1, dtype=int)
        data = numpy.arange(n, dtype=float).reshape(shape1)
        assert_single(data, shape2, order, advanced)
        data = numpy.arange(n, dtype=float).reshape(shape2)
        assert_single(data, shape1, order, advanced)


def assert_single(data, shape, order, advanced):
    edata = order.reshape(data, shape)
    mshape, fillgen = data_merging.mergeGenerator(
        [data],
        [data.shape],
        shape=shape,
        newaxis=False,
        order=order,
        allow_advanced_indexing=advanced,
    )
    assert shape == mshape
    mdata = numpy.empty(shape=mshape, dtype=data.dtype)
    for ndarray, idx_generator in fillgen():
        for idxin, idxout in idx_generator():
            mdata[idxout] = ndarray[idxin]
    numpy.testing.assert_array_equal(edata, mdata)


def test_data_merging_list_to_slice():
    idx = (numpy.array([4, 0, 1, 2, 3, 4, 0]), numpy.array([2, 3, 3, 3, 3, 3, 4]))
    assert_intlist_to_slice(idx)
    idx = (numpy.array([2, 1, 0, 1, 2, 3, 4, 0]), numpy.array([2, 2, 2, 3, 3, 3, 3, 4]))
    assert_intlist_to_slice(idx)
    idx = (
        numpy.array([0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 6, 4, 2, 2, 2]),
        numpy.array([0, 1, 2, 3, 0, 1, 2, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3]),
        numpy.array([0, 1, 0, 1, 0, 1, 2, 3, 4, 5, 6, 7, 1, 2, 3, 9, 8]),
    )
    assert_intlist_to_slice(idx)
    idx = (numpy.array([0]), numpy.array([0]), numpy.array([0]))
    assert_intlist_to_slice(idx)
    idx = (numpy.array([0, 0]), numpy.array([0, 2]), numpy.array([0, 4]))
    assert_intlist_to_slice(idx)
    idx = (numpy.array([0, 0, 1]), numpy.array([0, 2, 2]), numpy.array([0, 4, 4]))
    assert_intlist_to_slice(idx)
    idx = (numpy.array([1, 0, 0]), numpy.array([2, 0, 2]), numpy.array([4, 0, 4]))
    assert_intlist_to_slice(idx)
    combinations = []
    comb = [10], [20], [30]
    combinations.append(numpy.array(comb))
    comb = [1], [2], [3]
    combinations.append(numpy.array(comb))
    comb = [0] * 8, list(range(8)), list(range(1, 9))
    combinations.append(numpy.array(comb))
    comb = list(range(4)) + list(range(4)), [0] * 8, list(range(3)) + list(range(5))
    combinations.append(numpy.array(comb))
    for comb in itertools.permutations(combinations):
        idx = numpy.concatenate(comb, axis=1)
        assert_intlist_to_slice(idx)


def assert_intlist_to_slice(idx):
    for slicetwo in True, False:
        for allow_negative_stride in True, False:
            idx = numpy.asarray(idx)
            x = numpy.arange(idx.max() + 1)
            y = []
            for idx2 in data_merging.intListToSliceIndexing(
                idx, slicetwo=slicetwo, allow_negative_stride=allow_negative_stride
            ):
                if not allow_negative_stride:
                    assert all(
                        idx3.step > 0 for idx3 in idx2 if isinstance(idx3, slice)
                    )
                lst = [numpy.array(x[idx3]) for idx3 in idx2]
                n = max(arr.size for arr in lst)
                lst = [arr if arr.ndim else arr.repeat(n) for arr in lst]
                y.append(numpy.array(lst))
            idx2 = numpy.concatenate(y, axis=1)
            numpy.testing.assert_array_equal(idx, idx2)
