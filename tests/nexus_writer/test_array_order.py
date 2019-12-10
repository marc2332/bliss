# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import numpy
import random
import itertools
from nexus_writer_service.utils import array_order
from nxw_test_math import asproduct


def test_order_ravel():
    for shape, order, caxes in parameter_generator():
        _test_order_ravel(shape, order, caxes)


def test_order_swap():
    for shape, order, caxes in parameter_generator():
        _test_order_swap(shape, order, caxes)


def test_order_reshape():
    for shape, order, caxes in parameter_generator():
        _test_order_reshape(shape, order, caxes)


def parameter_generator():
    for ndim in [1, 2, 3, 4]:
        for order in ["C", "F"]:
            for ncaxis in range(ndim):
                shape = tuple(random.sample(range(1, 10), ndim))
                yield shape, order, "all"
                for caxes in itertools.permutations(range(ndim), ncaxis):
                    shape = tuple(random.sample(range(1, 10), ndim))
                    yield shape, order, caxes


def _test_order_ravel(shape, order, caxes):
    err_msg = "order:{}, shape:{}, caxes:{}".format(order, shape, caxes)
    ind = list(range(numpy.prod(shape)))

    # Test some internals
    o = array_order.Order(order)
    mind1 = o.unravel(ind, shape)
    mind2 = o._unravel(ind, shape)
    numpy.testing.assert_array_equal(mind1, mind2, err_msg=err_msg)
    ind1 = o.ravel(mind1, shape)
    ind2 = o._ravel(mind2, shape)
    numpy.testing.assert_array_equal(ind, ind1, err_msg=err_msg)
    numpy.testing.assert_array_equal(ind, ind2, err_msg=err_msg)

    # Test unravel
    o = array_order.Order(order, caxes=caxes)
    midx = o.unravel(ind, shape)
    mind2 = _mindex(shape, order, caxes)
    numpy.testing.assert_array_equal(midx, mind2, err_msg=err_msg)

    # Test ravel
    ind2 = o.ravel(midx, shape)
    numpy.testing.assert_array_equal(ind2, ind, err_msg=err_msg)


def _test_order_swap(shape, order1, caxes1):
    err_msg = "order:{}, shape:{}, caxes:{}".format(order1, shape, caxes1)
    if order1 == "C":
        order2 = "F"
    else:
        order2 = "C"
    if caxes1 == "all":
        caxes2 = None
    else:
        caxes2 = tuple(i for i in range(len(shape)) if i not in caxes1)

    o1 = array_order.Order(order1, caxes=caxes1)
    o2 = array_order.Order(order2, caxes=caxes2)

    ind = list(range(numpy.prod(shape)))
    random.shuffle(ind)
    for a, b in [(o1, o2), (o2, o1)]:
        mind1 = a.unravel(ind, shape)
        mind2 = a.swap_mindex(mind1, shape, b)
        mind3 = b.unravel(ind, shape)
        numpy.testing.assert_array_equal(mind2, mind3, err_msg=err_msg)

    mind = mind1
    for a, b in [(o1, o2), (o2, o1)]:
        ind1 = a.ravel(mind, shape)
        ind2 = a.swap_index(ind1, shape, b)
        ind3 = b.ravel(mind, shape)
        numpy.testing.assert_array_equal(ind2, ind3, err_msg=err_msg)


def _test_order_reshape(shape, order, caxes):
    err_msg = "order:{}, shape:{}, caxes:{}".format(order, shape, caxes)

    o = array_order.Order(order, caxes=caxes)
    arr1 = numpy.zeros(shape)
    gen = _mindex_generator(shape, order, caxes)
    for v, idx in enumerate(gen):
        arr1[idx] = v

    # Flatten
    arr2 = numpy.arange(arr1.size)
    arr3 = o.flatten(arr1)
    numpy.testing.assert_array_equal(arr2, arr3, err_msg=err_msg)

    # Reshape
    shapes = list(asproduct(arr1.size, 2))
    if len(shapes) > 10:
        shapes = random.sample(shapes, 10)
    for newshape in shapes:
        err_msg2 = "{}, newshape: {}".format(err_msg, newshape)
        arr2 = numpy.zeros(newshape)
        gen = _mindex_generator(newshape, order, caxes)
        for v, idx in enumerate(gen):
            arr2[idx] = v
        arr3 = o.reshape(arr1, newshape)
        numpy.testing.assert_array_equal(arr2, arr3, err_msg=err_msg2)


def _mindex(shape, order, caxes):
    """Multi index in fill order (flatten gives range(0, size))
    """
    gen = _mindex_generator(shape, order, caxes)
    return tuple(zip(*(idx for idx in gen)))


def _mindex_generator(shape, order, caxes):
    """Generate multi index in fill order (flatten gives range(0, size))
    """
    if caxes:
        if caxes == "all":
            caxes = tuple(range(len(shape)))
        if order == "F":
            maxdim = len(shape) - 1
            flipstate = {maxdim - dim: False for dim in caxes}
        else:
            flipstate = {dim: False for dim in caxes}
    else:
        flipstate = {}
    if order == "F":
        gen = _ndindex_generator(shape[::-1], 0, flipstate)
        for idx in gen:
            yield idx[::-1]
    else:
        gen = _ndindex_generator(shape, 0, flipstate)
        for idx in gen:
            yield idx


def _ndindex_generator(shape, dim, flipstate):
    """Generate multi index of shape[dim:] in C-order
    """
    if dim == len(shape) - 1:
        for i in _range(shape, dim, flipstate):
            yield (i,)
    else:
        for i in _range(shape, dim, flipstate):
            for idx in _ndindex_generator(shape, dim + 1, flipstate):
                yield (i,) + idx


def _range(shape, dim, flipstate):
    n = shape[dim]
    flip = flipstate.get(dim, None)
    if flip is not None:
        flipstate[dim] = not flip
    if flip:
        return range(n - 1, -1, -1)
    else:
        return range(n)
