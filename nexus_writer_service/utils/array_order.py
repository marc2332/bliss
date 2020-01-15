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
Ravel/unravel index
"""

import numpy


class Order:
    def __init__(self, order=None, caxes=None):
        """
        :param str order: "C": fast axis last, "F": fast axis first
        :param tuple or str caxes: No jumps along these dimensions when
                                   looping through the array in order.
                                   Supported strings: ["all"]
        """
        self.order = order
        self.caxes = caxes

    def __eq__(self, other):
        return self.order == other.order and self.caxes == other.caxes

    def __str__(self):
        if self.caxes:
            return "{} ({})".format(self.order, self.caxes)
        else:
            return self.order

    def __copy__(self):
        return self.__class__(self.order, self.caxes)

    def copy(self):
        return self.__copy__()

    @property
    def order(self):
        return self._order

    @order.setter
    def order(self, value):
        if value:
            value = value.upper()
        else:
            value = "C"
        if value not in ["C", "F"]:
            raise ValueError("Order must be C or F")
        self._order = value

    @property
    def corder(self):
        return self.order == "C"

    @property
    def forder(self):
        return self.order == "F"

    @property
    def caxes(self):
        return self.__caxes

    @caxes.setter
    def caxes(self, value):
        if isinstance(value, str):
            if value != "all":
                raise ValueError('caxes should be "all" or a tuple of integers')
            self.__caxes = value
        else:
            if value:
                self.__caxes = set(value)
            else:
                self.__caxes = set()

    def ravel(self, idx, shape):
        """
        :param tuple(array) idx: nD indices (nD x n)
        :param tuple shape:
        :returns ndarray: 1D indices (length n)
        """
        idx = self._mindex_discontinuous(idx, shape)
        return numpy.ravel_multi_index(idx, shape, order=self.order)

    def unravel(self, idx, shape):
        """
        :param array idx: 1D indices (length n)
        :param tuple shape:
        :returns tuple(ndarray): nD indices (nD x n)
        """
        idx = numpy.unravel_index(idx, shape, order=self.order)
        idx = self._mindex_continuous(idx, shape)
        return idx

    def reshape(self, arr, shape):
        """
        :param ndarray arr: nD array
        :param tuple shape: mD
        :returns ndarray: mD array
        """
        if self.caxes:
            ret = numpy.empty_like(arr, shape=shape)
            midx_get = self.unravel(range(arr.size), arr.shape)
            itget = zip(*midx_get)
            midx_set = self.unravel(range(arr.size), shape)
            itset = zip(*midx_set)
            for iget, iset in zip(itget, itset):
                ret[iset] = arr[iget]
            return ret
        else:
            return arr.reshape(shape, order=self.order)

    def flatten(self, arr):
        """
        :param ndarray arr: nD array
        :returns ndarray: 1D array
        """
        if self._caxes(arr.shape):
            midx = self.unravel(range(arr.size), arr.shape)
            return numpy.asarray([arr[idx] for idx in zip(*midx)])
        else:
            return arr.flatten(order=self.order)

    def _ravel(self, idx, shape):
        """
        Same as numpy.ravel_multi_index

        :param tuple(array) idx: nD indices (nD x n)
        :param tuple shape:
        :returns ndarray: 1D indices (length n)
        """
        # TODO: can we merge this with _mindex_discontinuous?
        mshape = self._mshape(shape)
        return sum(x * m for x, m in zip(idx, mshape))

    def _unravel(self, idx, shape):
        """
        Same as numpy.unravel_index

        :param array idx: 1D indices (length n)
        :param tuple shape:
        :returns tuple(ndarray): nD indices (nD x n)
        """
        # TODO: can we merge this with _mindex_continuous?
        mshape = self._mshape(shape)
        idx = numpy.asarray(idx)
        return tuple(idx // m % s for s, m in zip(shape, mshape))

    def _mshape(self, shape):
        if self.order == "C":
            return numpy.cumprod((1,) + shape[: -len(shape) : -1])[::-1]
        else:
            return numpy.cumprod((1,) + shape[:-1])

    def _mindex_continuous(self, idx, shape):
        """
        Convert discontinuous index to continuous

        :param tuple(array) idx: nD indices (nD x n)
        :param tuple shape:
        :param tuple(array): nD indices (nD x n)
        """
        return self._mindex_flip(idx, shape, reverse=False)

    def _mindex_discontinuous(self, idx, shape):
        """
        Convert continuous index to discontinuous

        :param tuple(array) idx: nD indices (nD x n)
        :param tuple shape:
        :param tuple(array): nD indices (nD x n)
        """
        return self._mindex_flip(idx, shape, reverse=True)

    def _mindex_flip(self, idx, shape, reverse=False):
        """
        Convert discontinuous index to continuous

        :param tuple(array) idx: nD indices (nD x n)
        :param tuple shape:
        :param tuple(array): nD indices (nD x n)
        """
        # Do we have continuous axes?
        caxes = self._caxes(shape)
        if not caxes:
            return idx
        ndim = len(shape)
        idx = tuple(idx[i].copy() for i in range(ndim))
        # Flip continuous axes
        if (self.order == "F") ^ reverse:
            it = range(ndim)
        else:
            it = range(ndim - 1, -1, -1)
        for i in it:
            if i not in caxes:
                continue
            # Count iterations based in indices in outer loops
            niteri = self._iter_index(idx, shape, i)
            # Reverse idx[i] when in an odd iteration
            arr = idx[i]
            mask = (niteri % 2) == 1
            arr[mask] = shape[i] - 1 - arr[mask]
        return idx

    def _caxes(self, shape):
        """
        Continuous axes. The last axis is iterated through only
        once so it is irrelavent.

        :param tuple shape:
        :returns tuple:
        """
        if not self.caxes:
            return tuple()
        ndim = len(shape)
        if self.order == "F":
            ilast = ndim - 1
        else:
            ilast = 0
        if self.caxes == "all":
            caxes = range(ndim)
        else:
            caxes = self.caxes
        return tuple(i for i in caxes if i != ilast)

    def _iter_index(self, idx, shape, dim):
        """
        The iteration index of dimension `dim` in which `idx` occurs.

        :param tuple(array) idx: nD indices (nD x n)
        :param tuple shape:
        :param int dim:
        :param array: iteration indices (n)
        """
        ndim = len(shape)
        if self.order == "F":
            diminc = 1
            dimlast = ndim - 1
        else:
            diminc = -1
            dimlast = 0
        # The last dimension is only iterated through
        # once so iteration index is zero
        if dim == dimlast:
            return numpy.zeros_like(idx[0])
        # First outer loop
        niter = idx[dim + diminc].copy()
        m = 1
        # Subsequent outer loops (if any)
        for j in range(dim + 2 * diminc, dimlast + diminc, diminc):
            m *= shape[j - diminc]
            niter += idx[j] * m
        return niter

    def swap_index(self, idx, shape, neworder):
        """
        Convert flat index in self order to neworder

        :param array idx: 1D indices (length n)
        :param tuple shape:
        :param Order neworder:
        :returns array: 1D indices (length n)
        """
        if self == neworder or len(shape) <= 1:
            return idx
        else:
            idx = self.unravel(idx, shape)
            return neworder.ravel(idx, shape)

    def swap_full_index(self, shape, neworder):
        """
        :param tuple shape:
        :param Order neworder:
        :returns array: 1D indices (length n)
        """
        idx = numpy.arange(numpy.prod(shape))
        if self == neworder or len(shape) <= 1:
            return idx
        elif not self._caxes(shape) and not neworder._caxes(shape):
            idx = idx.reshape(shape, order=neworder.order)
            return idx.flatten(order=self.order)
        else:
            idx = self.unravel(idx, shape)
            return neworder.ravel(idx, shape)

    def swap_mindex(self, idx, shape, neworder):
        """
        Convert unravelled index in self order to neworder

        :param tuple(array) idx: nD indices (nD x n)
        :param tuple shape:
        :param Order neworder:
        :returns array: 1D indices (length n)
        """
        if self == neworder or len(shape) <= 1:
            return idx
        else:
            idx = self.ravel(idx, shape)
            return neworder.unravel(idx, shape)

    def swap_list(self, lst, shape, neworder):
        """
        :param list lst: 1D items (length == n)
        :param tuple shape:
        :param Order neworder:
        :returns array: lst in new order
        """
        if self == neworder or len(shape) <= 1:
            return lst
        else:
            idx = neworder.swap_full_index(shape, self)
            return [lst[i] for i in idx]
