# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import re
import numpy
from collections import OrderedDict
from contextlib import contextmanager
from . import nexus
from . import hdf5external
from ..utils import logging_utils


def normalize_nexus_name(name):
    # TODO: could cause unique names to become non-unique ...
    return re.sub('[^a-zA-Z0-9_]+', '_', name)


def format_bytes(size):
    # 2**10 = 1024
    power = 2**10
    n = 0
    power_labels = {0: 'B', 1: 'KB', 2: 'MB', 3: 'GB', 4: 'TB'}
    while size > power:
        size /= power
        n += 1
    return '{:.01f}{}'.format(size, power_labels[n])


def shape_to_size(shape):
    return numpy.product(shape, dtype=int)


def split_shape(shape, detector_ndim):
    scan_ndim = len(shape) - detector_ndim
    scan_shape = shape[:scan_ndim]
    detector_shape = shape[scan_ndim:]
    return scan_shape, detector_shape


class DatasetProxy():
    """
    Wraps HDF5 dataset creating and growth.
    """

    def __init__(self, parent=None, device=None,
                 scan_shape=None, scan_save_shape=None,
                 detector_shape=None, dtype=None, order='C',
                 parentlogger=None, filename=None,
                 filecontext=None):
        """
        :param str parent: path in the HDF5 file
        :param dict device: defined in module `..data.devices`
        :param tuple scan_shape: zeros indicate variable length
        :param tuple scan_save_shape: zeros indicate variable length
        :param tuple detector_shape: does not contain zeros to
                                     indicate variable length
        :param dtype dtype:
        :param str order:
        :param parentlogger:
        :param str filename:
        :param str filecontext:
        """
        self.parent = parent
        self.npoints = 0
        self.device = device
        self.scan_shape = scan_shape
        self.scan_save_shape = scan_save_shape
        self.current_scan_save_shape = scan_save_shape
        self.detector_shape = detector_shape
        self.current_detector_shape = detector_shape
        self.dtype = dtype
        self.order = order
        self.filename = filename
        self.filecontext = filecontext
        self._external_raw = {}
        self._external_datasets = []
        if parentlogger is not None:
            logger = parentlogger
        self.logger = logging_utils.CustomLogger(logger, self)

    def __repr__(self):
        return '{}: shape = {}, dtype={}'\
            .format(repr(self.path),
                    self.shape,
                    self.dtype.__name__)

    @property
    def path(self):
        return '/'.join([self.parent, self.name])

    @property
    def uri(self):
        return self.filename + '::' + self.path

    @property
    def name(self):
        return normalize_nexus_name(self.device['data_name'])

    @property
    def linkname(self):
        return normalize_nexus_name(self.device['unique_name'])

    @property
    def type(self):
        return self.device['device_type']

    @property
    def data_type(self):
        return self.device['data_type']

    @property
    def master_index(self):
        return self.device['master_index']

    @property
    def scan_ndim(self):
        return len(self.scan_shape)

    @property
    def detector_ndim(self):
        return len(self.detector_shape)

    @property
    def scan_save_ndim(self):
        return len(self.scan_save_shape)

    @property
    def flattened(self):
        """
        Shape of scan equal to saved shape of scan?
        """
        return self.scan_shape != self.scan_save_shape

    @property
    def shape(self):
        return self.scan_save_shape + self.detector_shape

    @property
    def current_shape(self):
        return self.current_scan_save_shape + self.current_detector_shape

    @property
    def ndim(self):
        return len(self.shape)

    @property
    def grid_shape(self):
        """
        Like `current_shape` but with the original scan shape
        """
        return self.scan_shape + self.current_detector_shape

    @property
    def flat_shape(self):
        """
        Like `current_shape` but flatten the scan dimensions
        """
        if self.scan_ndim:
            size = shape_to_size(self.current_scan_save_shape)
            return (size,) + self.current_detector_shape
        else:
            return self.current_detector_shape

    @property
    def variable_shape(self):
        return not all(self.shape)

    @property
    def variable_scan_shape(self):
        return not all(self.scan_shape)

    @property
    def variable_detector_shape(self):
        # Variable detector shapes are not set to zero in Redis
        # but to 1 so we will have to assume variable
        return True

    @property
    def current_bytes(self):
        return self.npoints * shape_to_size(self.current_detector_shape) * \
            numpy.asarray(1, dtype=self.dtype).itemsize

    @property
    def maxshape(self):
        # TODO: currently detector_shape will not contains
        #       zeros to indicate variable length so assume
        #       any dimension can have a variable length
        return (None,) * self.ndim
        if all(self.shape):
            return None
        else:
            return tuple(n if n else None for n in self.shape)

    def add_external(self, newdata, file_format):
        """
        Add data as external references.

        :param list newdata:
        :param str file_format: 'hdf5' or other
        """
        if file_format == 'hdf5':
            if self._external_raw:
                raise RuntimeError('Cannot merge external hdf5 files with other external files')
            self._external_datasets += newdata
        else:
            if self._external_datasets:
                raise RuntimeError('Cannot merge external hdf5 files with other external files')
            hdf5external.add_arguments(file_format, newdata,
                                       createkwargs=self._external_raw)
        self.npoints += len(newdata)

    def add_internal(self, newdata):
        """
        Add data to dataset (copy)

        :param h5py.Dataset dset: shape = scan_shape + detector_shape
        :param array-like newdata: shape = (nnew, ) + detector_shape
        """
        with self.open(ensure_existance=True) as dset:
            try:
                self.npoints += self._insert_data(dset, newdata)
            except TypeError as e:
                self.logger.error(e)
                raise

    def _insert_data(self, dset, newdata):
        """
        Insert new data in dataset

        :param h5py.Dataset dset:
        :param array-like newdata: shape = (npoints, ) + detector_shape
        :returns int: number of added points
        """
        scanndim = self.scan_save_ndim
        shape = dset.shape
        scanshape = shape[:scanndim]
        detshape = shape[scanndim:]
        nnew = newdata.shape[0]
        icurrent = self.npoints
        inext = icurrent + nnew

        # New dataset shape
        newdetshape = tuple(max(a, b) for a, b in
                            zip(detshape, newdata.shape[1:]))
        if scanndim == 0:
            if inext == 1:
                newscanshape = tuple()
            else:
                newscanshape = inext,
            newshape = newscanshape + newdetshape
        elif scanndim == 1:
            newscanshape = max(shape[0], inext),
            newshape = newscanshape + newdetshape
        else:
            scancoord = numpy.unravel_index(range(icurrent, inext),
                                            scanshape, order=self.order)
            newscanshape = tuple(max(max(lst) + 1, n)
                                 for lst, n in zip(scancoord, scanshape))
            newshape = newscanshape + newdetshape
        self.current_scan_save_shape = newscanshape
        self.current_detector_shape = newdetshape

        # Extend dataset
        if shape != newshape:
            try:
                dset.resize(newshape)
            except (ValueError, TypeError):
                msg = '{} cannot be resized from {} to {}: {} points are not saved'\
                      .format(repr(dset.name), shape, newshape, nnew)
                self.logger.error(msg)
                return 0

        # Insert new data
        if scanndim == 0:
            dset[()] = newdata
        else:
            idx = [None] * scanndim + [slice(0, n) for n in newdata.shape[1:]]
            if scanndim == 1:
                # all at once
                idx[0] = slice(icurrent, inext)
                dset[tuple(idx)] = newdata
            else:
                # point per point
                for coordi, newdatai in zip(zip(*scancoord), newdata):
                    idx[:scanndim] = coordi
                    dset[tuple(idx)] = newdatai
        return nnew

    @property
    def current_scan_save_shape(self):
        if self.scan_save_ndim == 1:
            return (self.npoints,)
        else:
            return self._current_scan_save_shape

    @current_scan_save_shape.setter
    def current_scan_save_shape(self, value):
        self._current_scan_save_shape = value

    @property
    def compression(self):
        shape = self.shape
        maxshape = self.maxshape
        if all(shape):
            # fixed length
            if shape_to_size(shape) > 512 or maxshape:
                compression = 'gzip'
            else:
                compression = None
        else:
            # variable length
            compression = 'gzip'
        return compression

    @property
    def chunks(self):
        # Remark: chunking required if bool(maxshape or compression)
        if self.compression or self.maxshape:
            return True
        else:
            return None

    @property
    def fillvalue(self):
        """
        Value reader gets for uninitialized elements
        """
        fillvalue = numpy.nan
        try:
            numpy.array(fillvalue, self.dtype)
        except ValueError:
            fillvalue = 0
        return fillvalue

    @property
    def _dset_value(self):
        value = {'fillvalue': self.fillvalue,
                 'dtype': self.dtype}
        if self._external_datasets:
            uris, fill_generator = self._external_uris()
            value['data'] = uris
            value['fill_generator'] = fill_generator
            value['axis'] = 0
            value['newaxis'] = True
            value['maxshape'] = self.maxshape
            if nexus.HASVIRTUAL:
                value['shape'] = self.current_shape
                self.logger.debug('merged external HDF5 datasets (link using VDS)')
            else:
                value['compression'] = self.compression
                value['chunks'] = self.chunks
                self.logger.debug('merged external HDF5 datasets (copy because VDS not supported)')
        elif self._external_raw:
            value.update(self._external_raw)
            nframes = shape_to_size(self.current_scan_shape)
            # Same number of external files as nframes
            filename = os.path.join(os.path.dirname(self.filename),
                                    self.linkname)
            nskip = hdf5external.resize(value, nframes, filename,
                                        value['fillvalue'])
            if nskip > 0:
                self.logger.warning('Skip {} files'.format(nskip))
            elif nskip < 0:
                self.logger.warning('Missing {} files (added dummy files)'
                                    .format(nskip))
            # Finalize arguments
            hdf5external.finalize(value,
                                  shape=self.current_scan_save_shape,
                                  order=self.order)
            # REMARK: no chunking or reshaping
            #         compression not tested
            #         links are absolute paths
            value['shape'] = self.current_shape
            value['compression'] = self.compression
            self.logger.debug('merged external non-HDF5 data (link using external dataset)')
        else:
            value['shape'] = self.current_shape
            value['chunks'] = self.chunks
            value['maxshape'] = self.maxshape
            value['compression'] = self.compression
            self.logger.debug('internal data (copy)')
        return value

    def _external_uris(self):
        """
        :returns list, generator:
        """
        if self.detector_ndim:
            detidx = (Ellipsis, )
        else:
            detidx = tuple()
        uridict = OrderedDict()
        if self.current_scan_save_shape:
            coordout = list(range(len(self._external_datasets)))
            coordout = numpy.unravel_index(coordout, self.current_scan_save_shape,
                                           order=self.order)
            for (uri, idxin), idxout in zip(self._external_datasets, zip(*coordout)):
                item = (idxin, )+detidx, idxout+detidx
                if uri in uridict:
                    uridict[uri].append(item)
                else:
                    uridict[uri] = [item]
        else:
            uri, idxin = self._external_datasets[0]
            item = (idxin, )+detidx, tuple()
            uridict[uri] = [item]

        def fill_generator():
            for uri, lst in uridict.items():
                def index_generator():
                    for idxin, idxout in lst:
                        yield idxin, idxout
                yield uri, index_generator
        uris = list(uridict.keys())
        return uris, fill_generator

    @property
    def has_external(self):
        return bool(self._external_datasets or self._external_raw)

    @property
    def has_internal(self):
        return self.exists and not self.has_external

    @property
    def interpretation(self):
        return nexus.nxDatasetInterpretation(self.scan_ndim,
                                             self.detector_ndim,
                                             self.ndim)

    @property
    def _dset_attrs(self):
        """
        HDF5 dataset attributes
        """
        attrs = self.device['data_info']
        interpretation = self.interpretation
        if interpretation:
            attrs['interpretation'] = interpretation
        attrs = {k: v for k, v in attrs.items() if v is not None}
        return attrs

    def ensure_existance(self):
        with self.filecontext() as nxroot:
            if self.exists:
                return
            parent = nxroot[self.parent]
            nexus.nxCreateDataSet(parent, self.name,
                                  self._dset_value,
                                  self._dset_attrs)

    @property
    def exists(self):
        """
        :returns bool:
        """
        with self.filecontext() as nxroot:
            return self.path in nxroot

    @contextmanager
    def open(self, ensure_existance=False):
        """
        :param bool ensure_existance:
        :yields h5py.Dataset or None:
        """
        with self.filecontext() as nxroot:
            if ensure_existance:
                self.ensure_existance()
            if self.path in nxroot:
                yield nxroot[self.path]
            else:
                self.logger.warning(repr(self.uri) + ' does not exist')
                yield None

    def log_progress(self, npoints_expected, last=True):
        """
        :param int npoints_expected:
        :param bool last:
        """
        npoints_current = self.npoints
        datasize = format_bytes(self.current_bytes)
        self.logger.debug('progress {}/{} ({})'
                          .format(npoints_current, npoints_expected, datasize))
        if last and npoints_current < npoints_expected:
            self.logger.warning('Only {}/{} points saved ({})'
                                .format(npoints_current, npoints_expected, datasize))

    def reshape(self, scan_save_shape, detector_shape):
        """
        Reshape HDF5 dataset if it exists

        :param tuple or None scan_save_shape:
        :param tuple or None detector_shape:
        """
        with self.open() as dset:
            if dset is None:
                return
            shape = dset.shape
            if scan_save_shape is None:
                scan_save_shape = self.current_scan_save_shape
            elif len(scan_save_shape) != self.scan_save_ndim:
                raise ValueError('Scan dimensions must not change')
            if detector_shape is None:
                detector_shape = self.current_detector_shape
            elif len(detector_shape) != self.detector_ndim:
                raise ValueError('Detector dimensions must not change')
            newshape = scan_save_shape + detector_shape
            if dset.shape != newshape:
                self.logger.info('reshape from {} to {}'
                                 .format(shape, newshape))
                try:
                    dset.resize(newshape)
                except TypeError as e:
                    self.logger.warning("Cannot be reshaped because '{}'".format(e))
                else:
                    self.current_scan_save_shape = scan_save_shape
                    self.current_detector_shape = detector_shape
