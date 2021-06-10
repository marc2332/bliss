# -*- coding: utf-8 -*-
#
# This file is part of the nexus writer service of the BLISS project.
#
# Code is maintained by the ESRF Data Analysis Unit.
#
# Original author: Wout de Nolf
#
# Copyright (c) 2015-2020 ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import re
import numpy
import logging
from gevent.time import time
from gevent import sleep
from collections import OrderedDict
from fabio.edfimage import EdfImage
from silx.io import dictdump
from .base_proxy import BaseProxy
from ..io import nexus
from ..io import h5_external
from ..io.io_utils import mkdir
from ..utils.array_order import Order


logger = logging.getLogger(__name__)


def normalize_nexus_name(name):
    # TODO: could cause unique names to become non-unique ...
    return re.sub("[^a-zA-Z0-9_]+", "_", name)


def format_bytes(size):
    # 2**10 = 1024
    power = 2 ** 10
    n = 0
    power_labels = {0: "B", 1: "KB", 2: "MB", 3: "GB", 4: "TB"}
    while size > power:
        size /= power
        n += 1
    return "{:.01f}{}".format(size, power_labels[n])


def shape_to_size(shape):
    return numpy.product(shape, dtype=int)


def split_shape(shape, detector_ndim):
    scan_ndim = len(shape) - detector_ndim
    scan_shape = shape[:scan_ndim]
    detector_shape = shape[scan_ndim:]
    return scan_shape, detector_shape


def guess_chunk(scan_shape, detector_shape):
    """Simplified form of h5py._hl.filters.guess_chunk"""
    if detector_shape:
        return tuple(1 for _ in scan_shape) + tuple(
            min(n, max(n // 4, 256)) if n else 256 for n in detector_shape
        )
    else:
        return tuple(min(n, 256) if n else 256 for n in scan_shape)


class FileSizeMonitor:
    def __init__(self, filename="", timeout=10):
        self.filename = filename
        self.timeout = timeout

    def is_growing(self):
        filesize = os.path.getsize(self.filename)
        if filesize == self.filesize:
            if (time() - self.t0) > self.timeout:
                return False
        else:
            self.reset(filesize)
        return True

    def reset(self, filesize=0):
        self.filesize = filesize
        self.t0 = time()

    @property
    def filename(self):
        return self._filename

    @filename.setter
    def filename(self, value):
        self._filename = value
        self.reset()


class DatasetProxy(BaseProxy):
    """
    Wraps HDF5 dataset creating and growth.
    """

    def __init__(
        self,
        filename=None,
        parent=None,
        filecontext=None,
        device=None,
        scan_shape=None,
        scan_save_shape=None,
        detector_shape=None,
        external_images_per_file=None,
        external_uri_from_file=False,
        dtype=None,
        saveorder=None,
        publishorder=None,
        parentlogger=None,
    ):
        """
        :param str filename: HDF5 file name
        :param str filecontext: HDF5 open context manager
        :param str parent: path in the HDF5 file (must already exist)
        :param dict device: defined in module `scan_writers.devices`
        :param tuple scan_shape: zeros indicate variable length
        :param tuple scan_save_shape: zeros indicate variable length
        :param tuple detector_shape: does not contain zeros to
                                     indicate variable length
        :param int external_images_per_file: number of images per file for external datasets
        :param bool external_uri_from_file: get the URI's from file instead of trusting the provided URI's
        :param dtype dtype:
        :param Order saveorder: order in which the scan shape is filled
        :param Order publishorder: order in which the scan shape is published
        :param parentlogger:
        """
        if parentlogger is None:
            parentlogger = logger
        super().__init__(
            filename=filename,
            parent=parent,
            filecontext=filecontext,
            parentlogger=parentlogger,
        )

        # Expected data shape, dtype and order
        if sum(n == 0 for n in scan_shape) > 1:
            raise ValueError("Scan can have only one variable dimension")
        if sum(n == 0 for n in scan_save_shape) > 1:
            raise ValueError("Scan can have only one variable dimension")
        self._scan_shape = scan_shape
        self._scan_save_shape = scan_save_shape
        self._detector_shape = detector_shape
        self._dtype = dtype
        if not isinstance(saveorder, Order):
            saveorder = Order(saveorder)
        self._saveorder = saveorder
        if not isinstance(publishorder, Order):
            publishorder = Order(publishorder)
        self._publishorder = publishorder

        # Derived from expected data shape, dtype and order
        self._itemsize = numpy.asarray(1, dtype=dtype).itemsize

        corder_shape = scan_save_shape + detector_shape
        if corder_shape:
            chunk_shape = guess_chunk(scan_save_shape, detector_shape)
            self._npoints_h5chunk = shape_to_size(chunk_shape[: self.scan_ndim])
            if not self.csaveorder:
                chunk_shape = (
                    chunk_shape[self.scan_ndim :] + chunk_shape[: self.scan_ndim]
                )
            self._chunk_shape = chunk_shape
        else:
            # Scalar dataset (ndim=0)
            self._chunk_shape = None
            self._npoints_h5chunk = 1
        self._npoints_h5chunk = self._npoints_h5chunk
        self._save_interal_time = None
        self._save_interal_dtmax = 3

        # Check whether we need compression or not
        compression = None
        if self._chunk_shape:
            # Only use compression when chunking
            if detector_shape:
                compression = "gzip"
            else:
                n = shape_to_size(scan_save_shape)
                if n > 256 or not n:
                    compression = "gzip"
        self._compression = compression

        # Currently arrive data shape (but not necessarily saved already)
        self.current_scan_save_shape = scan_save_shape
        self.current_detector_shape = detector_shape

        # Device parameters
        self._device = device

        # Internal/external data buffers
        self._internal_buffer = []  # Buffer data saved as an HDF5 dataset
        self._external_raw = []  # URI's for supported external binary data
        self._external_raw_formats = ["edf"]
        self._external_names = []  # URI's for unsupported external binary data
        self._external_datasets = []  # URI's for virtual datasets

        # External data settings
        self._external_images_per_file = external_images_per_file
        self._external_uri_from_file = external_uri_from_file

    @property
    def scan_shape(self):
        """Expected scan shape (when run to completion). Zero indicates
        a variable dimension.
        """
        return self._scan_shape

    @property
    def scan_save_shape(self):
        """Expected scan shape (when run to completion) as saved. Zero
        indicates a variable dimension.
        """
        return self._scan_save_shape

    @property
    def detector_shape(self):
        """Expected detector shape. Does not contain zeros to indicate
        variable dimensions.
        """
        return self._detector_shape

    @property
    def dtype(self):
        """Data dtype
        """
        return self._dtype

    @property
    def saveorder(self):
        """Order to fill `scan_save_shape` with data
        """
        return self._saveorder

    @property
    def publishorder(self):
        """Order in which data from `scan_shape` arrives
        """
        return self._publishorder

    @property
    def device(self):
        """Device parameters
        """
        return self._device

    @property
    def external_images_per_file(self):
        """Number of images per file for external datasets (VDS)
        """
        return self._external_images_per_file

    @property
    def external_uri_from_file(self):
        """Get the URI's from file instead of trusting the provided URI's
        """
        return self._external_uri_from_file

    def __repr__(self):
        return "{}: shape = {}, dtype={}".format(
            repr(self.path), self.shape, self.dtype_name
        )

    @property
    def dtype_name(self):
        try:
            return self.dtype.__name__
        except AttributeError:
            return str(self.dtype)

    @property
    def name(self):
        return normalize_nexus_name(self.device["data_name"])

    @property
    def linkname(self):
        if self._external_names:
            # This dataset is a list of URI's saved as an array of strings
            return None
        else:
            return normalize_nexus_name(self.device["unique_name"])

    @property
    def device_type(self):
        return self.device["device_type"]

    @property
    def data_type(self):
        return self.device["data_type"]

    @property
    def master_index(self):
        return self.device["master_index"]

    @property
    def scan_ndim(self):
        """Expected scan dimensions
        """
        return len(self.scan_shape)

    @property
    def detector_ndim(self):
        """Expected detector dimensions
        """
        return len(self.detector_shape)

    @property
    def scan_save_ndim(self):
        return len(self.scan_save_shape)

    @property
    def csaveorder(self):
        return self.saveorder.corder

    @property
    def cpublishorder(self):
        return self.publishorder.corder

    @property
    def shape(self):
        """Expected data shape. Zero indicates a variable length.
        """
        if self.csaveorder:
            return self.scan_save_shape + self.detector_shape
        else:
            return self.detector_shape + self.scan_save_shape

    @property
    def ndim(self):
        return len(self.shape)

    @property
    def current_shape(self):
        """Current data shape. Zero indicates a variable length.
        """
        if self.csaveorder:
            return self.current_scan_save_shape + self.current_detector_shape
        else:
            return self.current_detector_shape + self.current_scan_save_shape

    @property
    def grid_shape(self):
        """Like `current_shape` but with the original scan shape
        """
        if self.variable_scan_shape and self.scan_ndim == 1:
            scan_shape = self.current_scan_save_shape
        else:
            scan_shape = self.scan_shape
        if self.csaveorder:
            return scan_shape + self.current_detector_shape
        else:
            return self.current_detector_shape + scan_shape

    @property
    def flat_shape(self):
        """Like `current_shape` but flatten the scan dimensions
        """
        if self.scan_ndim:
            size = shape_to_size(self.current_scan_save_shape)
            if self.csaveorder:
                return (size,) + self.current_detector_shape
            else:
                return self.current_detector_shape + (size,)
        else:
            return self.current_detector_shape

    @property
    def reshaped(self):
        """
        Shape of scan equal to saved shape of scan?
        """
        return self.scan_shape != self.scan_save_shape

    @property
    def npoints_expected(self):
        # TODO: A fixed length scan can have channels with
        #       more than the expected points.
        return 0
        # return shape_to_size(self.scan_shape)

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
    def current_detector_size(self):
        """Number of elements currently in the detector dimensions
        """
        return shape_to_size(self.current_detector_shape)

    @property
    def current_scan_size(self):
        """Number of elements currently in the shape dimensions
        """
        return self.npoints

    @property
    def current_size(self):
        """Number of elements currently in the dataset
        """
        return self.current_scan_size * self.current_detector_size

    @property
    def itemsize(self):
        """dtype size in bytes
        """
        return self._itemsize

    @property
    def current_bytes(self):
        return self.current_size * self.itemsize

    @property
    def maxshape(self):
        # All dimensions are variable:
        # - Currently detector_shape does not contain
        #   zeros to indicate variable length so assume
        #   any dimension can have a variable length.
        # - Detector may publish more points than
        #   expected.
        return (None,) * self.ndim

    def add_external(self, newdata, file_format=None):
        """Add data as external references.

        :param list((str, int)) newdata: uri and index within the uri
        :param str file_format: if not specified, uris will be saved as strings
        """
        if self.is_internal:
            msg = f"{self} already has internal data"
            raise RuntimeError(msg)
        if file_format == "hdf5":
            if self._external_raw or self._external_names:
                msg = f"{self} cannot mix HDF5 with other formats"
                raise RuntimeError(msg)
            self._external_datasets += newdata
            self.npoints = len(self._external_datasets)
        elif file_format in self._external_raw_formats:
            if self._external_datasets or self._external_names:
                msg = f"{self} cannot mix {repr(file_format)} with other formats"
                raise RuntimeError(msg)
            self._external_raw += newdata
            self.npoints = len(self._external_raw)
        else:
            if self._external_datasets or self._external_raw:
                msg = f"{self} cannot mix file formats"
                raise RuntimeError(msg)
            self._external_names += newdata
            self.npoints = len(self._external_names)

    def add(self, newdata):
        """Add data to dataset (copy)

        :param h5py.Dataset dset: shape = scan_shape + detector_shape
        :param sequence newdata: shape = (nnew, ) + detector_shape
        """
        if self.is_external:
            msg = f"{self} already has external data"
            raise RuntimeError(msg)
        super().add(newdata)

    add_internal = add

    def _insert_data(self, dset, newdata):
        """Add data to the internal buffer

        :param h5py.Dataset dset:
        :param sequence newdata: shape = (npoints, ) + detector_shape
        :returns int: number of added points
        """
        nnew = len(newdata)
        points_buffer = self._internal_buffer
        nalready_buffered = len(points_buffer)
        points_buffer.extend(newdata)
        nbuffered = nalready_buffered + nnew
        nalready_saved = self.npoints - nalready_buffered
        if self._save_interal_time is None:
            self._save_interal_time = time()

        # Save points aligned with the HDF5 chunks
        nchunk = self._npoints_h5chunk - (nalready_saved % self._npoints_h5chunk)
        nsave = (nbuffered // nchunk) * nchunk
        # Save non-aligned when the data arrives too slow.
        if not nsave:
            if (time() - self._save_interal_time) > self._save_interal_dtmax:
                nsave = nbuffered
        if nsave:
            newdata = self._merge_ragged_sequence(points_buffer[:nsave])
            self._internal_buffer = points_buffer[nsave:]
            info = self._insert_data_info(
                dset.shape, nalready_saved, nsave, newdata[0].shape
            )
            self.current_scan_save_shape = info["new_scanshape"]
            self.current_detector_shape = info["new_detshape"]
            self._save_internal_data(dset, newdata, info)
            self._save_interal_time = time()
        return nnew

    def _merge_ragged_sequence(self, sequence):
        # Return the sequence when not ragged
        if self.detector_ndim != 1:
            return sequence
        shape0 = sequence[0].shape
        if all(e.shape == shape0 for e in sequence):
            return sequence

        # Regular nD array
        nmax = max(e.shape[0] if e.ndim else 1 for e in sequence)
        shape = (len(sequence), nmax)
        arr = numpy.full(shape, self.fillvalue, dtype=self.dtype)
        for src, dest in zip(sequence, arr):
            dest[: len(src)] = src
        return arr

    def flush(self):
        """Flush any buffered data
        """
        # Flush external data (VDS or raw external datasets)
        super().flush()

        # Flush internal data
        if self.is_external or not self._internal_buffer:
            return
        self._npoints_h5chunk = 1
        self.add_internal([])

    def _insert_data_info(self, old_shape, nold_points, nnew_points, newdata_detshape):
        """Add data to the internal buffer

        :param tuple old_shape:
        :param int nnew_points:
        :param tuple newdata_detshape:
        :param sequence newdata: shape = (npoints, ) + detector_shape
        :returns dict:
        """
        scan_ndim = self.scan_save_ndim
        det_ndim = self.detector_ndim
        csaveorder = self.csaveorder

        if csaveorder:
            scan_slice = slice(None, scan_ndim)
            det_slice = slice(scan_ndim, None)
        else:
            det_slice = slice(None, det_ndim)
            scan_slice = slice(det_ndim, None)

        old_scanshape = old_shape[scan_slice]
        old_detshape = old_shape[det_slice]
        icurrent = nold_points
        inext = icurrent + nnew_points
        new_detshape = tuple(max(a, b) for a, b in zip(old_detshape, newdata_detshape))

        if scan_ndim == 0:
            save_coord = None
            if inext == 1:
                new_scanshape = tuple()
            else:
                new_scanshape = (inext,)
        elif scan_ndim == 1:
            save_coord = None
            new_scanshape = (max(old_shape[0], inext),)
        else:
            save_coord, new_scanshape = self._save_shape_mindex(
                icurrent, inext, old_scanshape
            )

        if csaveorder:
            new_shape = new_scanshape + new_detshape
        else:
            new_shape = new_detshape + new_scanshape

        info = {
            "old_shape": old_shape,
            "old_scanshape": old_scanshape,
            "old_detshape": old_detshape,
            "new_shape": new_shape,
            "new_scanshape": new_scanshape,
            "new_detshape": new_detshape,
            "newdata_detshape": newdata_detshape,
            "scan_ndim": scan_ndim,
            "det_ndim": det_ndim,
            "scan_slice": scan_slice,
            "det_slice": det_slice,
            "csaveorder": csaveorder,
            "icurrent": icurrent,
            "inext": inext,
            "nnew_points": nnew_points,
            "save_coord": save_coord,
        }
        return info

    def _save_shape_mindex(self, start, stop, shape):
        """Coordinates in shape (which may need to be expended along the
        slow dimension) that correspond to flat indices `range(start, stop)`.

        :param int start:
        :param int stop:
        :param tuple shape: shape to be filled (with self.saveorder)
        :returns iterable, shape: coordinates and (expanded) shape
        """
        indices = list(range(start, stop))
        while True:
            try:
                save_coord = self.saveorder.unravel(indices, shape)
                break
            except ValueError:
                # Increase the variable dimension or
                # the slow dimension if fixed-length scan
                shape = list(shape)
                try:
                    vdim = shape.index(0)
                except ValueError:
                    if self.csaveorder:
                        vdim = 0
                    else:
                        vdim = -1
                shape[vdim] += 1
                shape = tuple(shape)
        return save_coord, shape

    def _save_internal_data(self, dset, newdata, info):
        """Add data to the HDF5 dataset

        :param h5py.Dataset dset:
        :param sequence newdata:
        :returns int: number of added points
        """
        # Extend HDF5 dataset
        if info["old_shape"] != info["new_shape"]:
            dset.resize(info["new_shape"])

        # Insert new data in HDF5 dataset
        if info["scan_ndim"] == 0:
            dset[()] = newdata
        else:
            if info["csaveorder"]:
                idx = [None] * info["scan_ndim"] + [
                    slice(0, n) for n in info["newdata_detshape"]
                ]
            else:
                idx = [slice(0, n) for n in info["newdata_detshape"]] + [None] * info[
                    "scan_ndim"
                ]
            if info["scan_ndim"] == 1:
                newdata = numpy.asarray(newdata)
                # all at once
                if info["csaveorder"]:
                    idx[0] = slice(info["icurrent"], info["inext"])
                else:
                    idx[-1] = slice(info["icurrent"], info["inext"])
                    axes = list(range(1, newdata.ndim)) + [0]
                    newdata = numpy.transpose(newdata, axes)
                try:
                    dset[tuple(idx)] = newdata
                except Exception:
                    self.logger.warning(
                        "\n\n" + str((idx, dset.shape, newdata.shape)) + "\n\n"
                    )
                    raise
            else:
                # point per point (could be done better)
                scan_slice = info["scan_slice"]
                for coordi, newdatai in zip(zip(*info["save_coord"]), newdata):
                    idx[scan_slice] = coordi
                    dset[tuple(idx)] = newdatai

    @property
    def current_scan_save_shape(self):
        """This refers to the currently know scan shape, not the current
        shape in terms of arrived data.
        """
        if self.scan_save_ndim == 1:
            return (self.npoints,)
        else:
            return self._current_scan_save_shape

    @current_scan_save_shape.setter
    def current_scan_save_shape(self, value):
        self._current_scan_save_shape = value

    @property
    def compression(self):
        return self._compression

    @property
    def chunks(self):
        # Remark: chunking is required for resizable datasets and/or compression
        return self._chunk_shape

    @property
    def fillvalue(self):
        """Value reader gets for uninitialized elements
        """
        if self.dtype in (str, bytes):
            return ""
        fillvalue = numpy.nan
        try:
            numpy.array(fillvalue, dtype=self.dtype)
        except ValueError:
            fillvalue = 0
        return fillvalue

    @property
    def external_source_args(self):
        nframes = self.external_images_per_file
        if nframes is None:
            # self.logger.warning("Number of frames per external file is not specified")
            return {}
        else:
            shape = (nframes,) + self.detector_shape
            return {"shape": shape, "dtype": self.dtype}

    @property
    def _dset_value(self):
        value = {"fillvalue": self.fillvalue, "dtype": self.dtype}
        if self._external_datasets:
            files, nuris, fill_generator = self._external_dataset_uris()
            if not nuris:
                self.logger.warning("No data to create a virtual dataset")
                return None
            value["data"] = files
            value["order"] = self.saveorder
            value["fill_generator"] = fill_generator
            value["virtual_source_args"] = self.external_source_args
            value["axis"] = 0
            value["newaxis"] = True
            value["maxshape"] = self.maxshape
            if nexus.HASVIRTUAL:
                value["shape"] = self.current_shape
                self.logger.info(
                    f"merge {nuris} URIs from {len(files)} files as a virtual dataset"
                )
            else:
                value["compression"] = self.compression
                value["chunks"] = self.chunks
                self.logger.info(
                    f"merge {nuris} URIs from {len(files)} files as a copy (VDS not supported)"
                )
        elif self._external_raw:
            nuris = self._get_external_raw(value)
            if not nuris:
                self.logger.warning("No data to create an external dataset")
                return None
            # Same number of external files as nframes
            nframes = shape_to_size(self.current_scan_save_shape)
            ext = os.path.splitext(self._external_raw[0][0])[-1]
            filename = self._dummy_filename(ext)
            nskip = h5_external.resize(value, nframes, filename, value["fillvalue"])
            if nskip > 0:
                self.logger.warning(f"Skip {nskip} files")
            elif nskip < 0:
                self.logger.warning(f"Missing {nskip} files")
            # Finalize arguments
            fillorder = self.saveorder
            addorder = Order()
            h5_external.finalize(
                value,
                shape=self.current_scan_save_shape,
                addorder=addorder,
                fillorder=fillorder,
            )
            # REMARK: no chunking or reshaping
            #         links are absolute paths
            value["shape"] = self.current_shape
            value["chunks"] = None
            nuris = len(value.get("external", []))
            self.logger.info("merge {nuris} URIs as an external (non-HDF5) dataset")
        elif self._external_names:
            value = []
            dirname = os.path.dirname(self.filename)
            for filename, ind in self._external_names:
                filename = os.path.relpath(filename, dirname)
                value.append(f"{filename}::{ind}")
            self.logger.info(f"merge {len(value)} URIs as a list of strings")
        else:
            value["shape"] = self.current_shape
            value["chunks"] = self.chunks
            value["maxshape"] = self.maxshape
            value["compression"] = self.compression
            self.logger.debug("create as internal data (copy)")
        return value

    def _external_dataset_uris(self):
        """
        :returns list, num, generator:
        """
        # Assume dataset shapes are (nframes, detdim0, detdim1, ...)
        extorder = Order()
        cextorder = extorder.order
        csaveorder = self.csaveorder

        # Map uri to list of (idxin(int or slice), idxout(tuple(int or slice))) tuples
        uridict = OrderedDict()
        uris = self._get_external_datasets()
        if self.current_scan_save_shape:
            coordout = range(len(uris))
            coordout = self.saveorder.unravel(coordout, self.current_scan_save_shape)

            collapse_slice = self.csaveorder

            for (uri, idxin), idxout in zip(uris, zip(*coordout)):
                if uri in uridict:
                    if collapse_slice:
                        self._vdsidx_append(uridict[uri], idxin, idxout)
                    else:
                        uridict[uri].append((idxin, idxout))
                else:
                    uridict[uri] = [(idxin, idxout)]
        else:
            uri, idxin = uris[0]
            uridict[uri] = [(idxin, tuple())]

        # Generates uri's with associated in/out index generator
        def fill_generator():
            for uri, lst in uridict.items():

                def index_generator():
                    for idxin, idxout in lst:
                        idxin = self._add_detidx(idxin, cextorder)
                        idxout = self._add_detidx(idxout, csaveorder)
                        yield idxin, idxout

                yield uri, index_generator

        files = list(uridict.keys())
        nuris = sum(len(v) for v in uridict.values())
        return files, nuris, fill_generator

    @classmethod
    def _vdsidx_append(cls, lst, idxin, idxout):
        """Append VDS input/output index or modify the last one

        :param list(2-tuple) lst:
        :param int idxin:
        :param tuple(int) idxout:
        """
        idxin_prev, idxout_prev = lst[-1]

        # Input index follows the previous one?
        inext = cls._vdsidx_slice_next(idxin_prev, idxin)
        if not inext:
            lst.append((idxin, idxout))
            return

        # Output index follows the previous one
        onext = [
            cls._vdsidx_slice_next(ilast, i) for ilast, i in zip(idxout_prev, idxout)
        ]
        if sum(onext) != 1:
            lst.append((idxin, idxout))
            return
        iout = onext.index(True)

        # Output index the same except for the one that incremented
        eout = [ilast == i for ilast, i in zip(idxout_prev, idxout)]
        eout.pop(iout)
        if not all(eout):
            lst.append((idxin, idxout))
            return

        # Extent output index slice
        idxout_prev = idxout_prev[iout]
        end = idxout[iout]
        if isinstance(idxout_prev, slice):
            start = idxout_prev.start
            step = idxout_prev.step
        else:
            start = idxout_prev
            step = end - start
        idxout = list(idxout)
        idxout[iout] = slice(start, end + step, step)
        idxout = tuple(idxout)

        # Extent input index slice
        if isinstance(idxin_prev, slice):
            a = idxin_prev.start
            b = idxin
            s = idxin_prev.step
        else:
            a = idxin_prev
            b = idxin
            s = b - a
        b += s
        idxin = slice(a, b, s)

        # Replace previous index with extended slices
        lst[-1] = (idxin, idxout)

    @staticmethod
    def _vdsidx_slice_next(idx_prev, idx):
        """Index follows the previous index
        """
        step = 1
        if isinstance(idx_prev, slice):
            if idx_prev.step is not None:
                step = idx_prev.step
            idx_prev = next(reversed(range(idx_prev.start, idx_prev.stop, step)))
        # Negative steps not supported by h5py VDS
        return idx_prev + step == idx

    def _add_detidx(self, idx, corder):
        """Add detector dimensions to index
        """
        if not isinstance(idx, tuple):
            idx = (idx,)
        if self.detector_ndim:
            if corder:
                return idx + (Ellipsis,)
            else:
                return (Ellipsis,) + idx
        else:
            return idx

    def _get_external_datasets(self):
        if not self.external_uri_from_file:
            return self._external_datasets
        self.logger.info("Retrieving HDF5 URI's ...")
        uris = list(zip(*self._external_datasets))[0]
        filenames = set(nexus.splitUri(uri)[0] for uri in uris)
        uridict = {}
        mon = FileSizeMonitor()
        for filename in sorted(filenames):
            mon.filename = filename
            while True:
                try:
                    uri = nexus.getDefaultUri(filename, enable_file_locking=True)
                except (RuntimeError, OSError):
                    if not mon.is_growing():
                        raise
                else:
                    if uri:
                        self.logger.debug(f"Got URI from file {filename}")
                        uridict[filename] = uri
                        break
                    else:
                        if not mon.is_growing():
                            raise RuntimeError(f"Cannot get URI from file {filename}")
                sleep(0.1)
        return [
            (uridict[nexus.splitUri(uri)[0]], i) for uri, i in self._external_datasets
        ]

    def _get_external_raw(self, createkwargs):
        self.logger.info("Retrieving external URI's ...")
        mon = FileSizeMonitor()
        for filename, i in self._external_raw:
            mon.filename = filename
            while True:
                try:
                    h5_external.add_arguments(
                        [(filename, i)], createkwargs=createkwargs
                    )
                except OSError:
                    if not mon.is_growing():
                        raise
                else:
                    break
                sleep(0.1)
        return len(createkwargs.get("external", []))

    @property
    def is_external(self):
        """"External" means a virtual dataset or a raw external dataset,
        for example links to EDF files.
        """
        return bool(
            self._external_datasets or self._external_raw or self._external_names
        )

    @property
    def is_internal(self):
        """"Internal" mean a normal HDF5 dataset
        """
        return self.exists and not self.is_external

    @property
    def interpretation(self):
        return nexus.nxDatasetInterpretation(
            self.scan_ndim, self.detector_ndim, self.ndim
        )

    @property
    def _dset_attrs(self):
        """HDF5 dataset attributes
        """
        attrs = self.device.get("data_info", {})
        interpretation = self.interpretation
        if interpretation:
            attrs["interpretation"] = interpretation
        attrs = {k: v for k, v in attrs.items() if v is not None}
        return attrs

    def _create(self, nxroot):
        """Create the dataset
        """
        parent = nxroot[self.parent]
        value = self._dset_value
        if value:
            attrs = self._dset_attrs
            nexus.nxCreateDataSet(parent, self.name, value, attrs)
            self._exists = True

    def _create_parent(self, nxroot):
        raise RuntimeError("Parent must exist already")

    @property
    def _progress_log_string(self):
        return f" ({format_bytes(self.current_bytes)})"

    def reshape(self, scan_save_shape, detector_shape=None):
        """Reshape dataset (must exist when internal, should not exist when external)

        :param tuple or None scan_save_shape:
        :param tuple or None detector_shape:
        """
        if scan_save_shape is None:
            scan_save_shape = self.current_scan_save_shape
        elif len(scan_save_shape) != self.scan_save_ndim:
            raise ValueError("Number of scan dimensions should not change")
        if detector_shape is None:
            detector_shape = self.current_detector_shape
        elif len(detector_shape) != self.detector_ndim:
            raise ValueError("Number of detector dimensions should not change")
        if self.is_external:
            reshaped = self._reshape_external(scan_save_shape, detector_shape)
        else:
            reshaped = self._reshape_internal(scan_save_shape, detector_shape)
        if reshaped:
            self.current_scan_save_shape = scan_save_shape
            self.current_detector_shape = detector_shape
            self.npoints = shape_to_size(scan_save_shape)

    def _reshape_internal(self, scan_save_shape, detector_shape):
        """Reshape HDF5 dataset if it exists

        :param tuple or None scan_save_shape:
        :param tuple or None detector_shape:
        :return bool:
        """
        with self.open(create=False) as dset:
            if dset is None:
                self.logger.warning("Cannot reshape internal dataset before creation")
                return False
            shape = dset.shape
            if self.csaveorder:
                new_shape = scan_save_shape + detector_shape
            else:
                new_shape = detector_shape + scan_save_shape
            if dset.shape != new_shape:
                self.logger.info(f"reshape from {shape} to {new_shape}")
                try:
                    dset.resize(new_shape)
                except TypeError as e:
                    self.logger.warning(f"Cannot be reshaped because '{e}'")
                else:
                    return True
        return False

    def _reshape_external(self, scan_save_shape, detector_shape):
        """Reshape HDF5 dataset if it exists

        :param tuple or None scan_save_shape:
        :param tuple or None detector_shape:
        :return bool:
        """
        if self.exists:
            self.logger.warning("Cannot reshape external dataset after creation")
            return False
        npoints = shape_to_size(scan_save_shape)
        if self._external_datasets:
            lst = self._external_datasets
        elif self._external_names:
            lst = self._external_names
        else:
            lst = self._external_raw
        nlst = len(lst)
        if npoints != nlst:
            if npoints < nlst:
                nremove = nlst - npoints
                self.logger.info(f"remove {nremove} points")
                lst = lst[:npoints]
            else:
                nadd = npoints - nlst
                self.logger.info(f"add {nadd} dummy points")
                lst += self._dummy_uris(nadd)
            if self._external_datasets:
                self._external_datasets = lst
            elif self._external_names:
                self._external_names = lst
            else:
                self._external_raw = lst
            return True
        return False

    def _dummy_uris(self, npoints):
        """URIs of dummy data (create when missing).

        :returns lst(str, int): uri, index
        """
        hdf5 = bool(self._external_datasets)
        if hdf5:
            ext = ".h5"
        else:
            ext = ".edf"
        filename = self._dummy_filename(ext)
        if not os.path.isfile(filename):
            mkdir(os.path.dirname(filename))
            fillvalue = self.fillvalue
            dtype = self.dtype
            if hdf5:
                shape = (1,) + self.current_detector_shape
                with nexus.File(filename, mode="w") as f:
                    dset = f.create_dataset(
                        "data", shape=shape, dtype=dtype, fillvalue=fillvalue
                    )
                    nexus.markDefault(dset)
            else:
                shape = self.current_detector_shape
                if not shape:
                    shape = 1, 1
                elif len(shape) == 1:
                    shape = 1, shape[0]
                data = numpy.full(shape, fillvalue, dtype=dtype)
                edf = EdfImage(data=data, header=None)
                edf.write(filename)
        return [(filename, 0) for _ in range(npoints)]

    def _dummy_filename(self, ext):
        """
        :param str ext: .edf, .h5, ...
        :returns str:
        """
        dirname = os.path.dirname(self.filename)
        name = "_".join(map(str, self.current_detector_shape)) + "_" + self.dtype_name
        return os.path.join(dirname, "dummy", "dummy_" + name + ext)

    def add_metadata(self, treedict, parent=False, create=False, **kwargs):
        """Add datasets/attributes (typically used for metadata)

        :param dict treedict:
        :param bool parent:
        :param bool create: create destination when it does not exist
        :param kwargs: see `dicttonx`
        """
        if parent:
            ctx = self.open_parent
        else:
            ctx = self.open
        with ctx(create=create) as destination:
            if destination is None:
                self.logger.error("Cannot add metadata before creation")
            else:
                dictdump.dicttonx(treedict, destination, **kwargs)
