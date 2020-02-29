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
import re
import numpy
import logging
from gevent.time import time
from gevent import sleep
from collections import OrderedDict
from contextlib import contextmanager
from fabio.edfimage import EdfImage
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
        :param str parent: path in the HDF5 file
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

        # Shape and order
        if sum(n == 0 for n in scan_shape) > 1:
            raise ValueError("Scan can have only one variable dimension")
        if sum(n == 0 for n in scan_save_shape) > 1:
            raise ValueError("Scan can have only one variable dimension")
        self.scan_shape = scan_shape
        self.scan_save_shape = scan_save_shape
        self.current_scan_save_shape = scan_save_shape
        self.detector_shape = detector_shape
        self.current_detector_shape = detector_shape
        self.dtype = dtype
        self.external_images_per_file = external_images_per_file
        self.external_uri_from_file = external_uri_from_file
        if not isinstance(saveorder, Order):
            saveorder = Order(saveorder)
        self.saveorder = saveorder
        if not isinstance(publishorder, Order):
            publishorder = Order(publishorder)
        self.publishorder = publishorder

        # Device parameters
        self.device = device

        # Internals
        self._external_raw = []
        self._external_datasets = []
        self._external_names = []
        self._external_raw_formats = ["edf"]

    def __repr__(self):
        return "{}: shape = {}, dtype={}".format(
            repr(self.path), self.shape, self.dtype.__name__
        )

    @property
    def name(self):
        return normalize_nexus_name(self.device["data_name"])

    @property
    def linkname(self):
        if self._external_names:
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
        return len(self.scan_shape)

    @property
    def detector_ndim(self):
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
        if self.csaveorder:
            return self.scan_save_shape + self.detector_shape
        else:
            return self.detector_shape + self.scan_save_shape

    @property
    def current_shape(self):
        if self.csaveorder:
            return self.current_scan_save_shape + self.current_detector_shape
        else:
            return self.current_detector_shape + self.current_scan_save_shape

    @property
    def grid_shape(self):
        """
        Like `current_shape` but with the original scan shape
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
        """
        Like `current_shape` but flatten the scan dimensions
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
    def ndim(self):
        return len(self.shape)

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
    def current_bytes(self):
        return (
            self.npoints
            * shape_to_size(self.current_detector_shape)
            * numpy.asarray(1, dtype=self.dtype).itemsize
        )

    @property
    def maxshape(self):
        # TODO: currently detector_shape does not contain
        #       zeros to indicate variable length so assume
        #       any dimension can have a variable length
        return (None,) * self.ndim
        if all(self.shape):
            return None
        else:
            return tuple(n if n else None for n in self.shape)

    def add_external(self, newdata, file_format=None):
        """
        Add data as external references.

        :param list((str, int)) newdata: uri and index within the uri
        :param str file_format: if not specified, uris will be saved as strings
        """
        if self.is_internal:
            msg = "{} already has internal data".format(self)
            raise RuntimeError(msg)
        if file_format == "hdf5":
            if self._external_raw or self._external_names:
                msg = "{} cannot mix HDF5 with other formats".format(self)
                raise RuntimeError(msg)
            self._external_datasets += newdata
            self.npoints = len(self._external_datasets)
        elif file_format in self._external_raw_formats:
            if self._external_datasets or self._external_names:
                msg = "{} cannot mix {} with other formats".format(
                    self, file_format.upper()
                )
                raise RuntimeError(msg)
            self._external_raw += newdata
            self.npoints = len(self._external_raw)
        else:
            if self._external_datasets or self._external_raw:
                msg = "{} cannot mix file formats".format(self)
                raise RuntimeError(msg)
            self._external_names += newdata
            self.npoints = len(self._external_names)

    def add(self, newdata):
        """
        Add data to dataset (copy)

        :param h5py.Dataset dset: shape = scan_shape + detector_shape
        :param array-like newdata: shape = (nnew, ) + detector_shape
        """
        if self.is_external:
            msg = "{} already has external data".format(self)
            raise RuntimeError(msg)
        super().add(newdata)

    add_internal = add

    def _insert_data(self, dset, newdata):
        """
        Insert new data in dataset

        :param h5py.Dataset dset:
        :param array-like newdata: shape = (npoints, ) + detector_shape
        :returns int: number of added points
        """
        scanndim = self.scan_save_ndim
        detndim = self.detector_ndim
        corder = self.csaveorder
        if corder:
            scanidx = slice(None, scanndim)
            detidx = slice(scanndim, None)
        else:
            detidx = slice(None, detndim)
            scanidx = slice(detndim, None)

        shape = dset.shape
        scanshape = shape[scanidx]
        detshape = shape[detidx]
        nnew = newdata.shape[0]
        icurrent = self.npoints
        inext = icurrent + nnew
        newdetshape = tuple(max(a, b) for a, b in zip(detshape, newdata.shape[1:]))

        if scanndim == 0:
            if inext == 1:
                newscanshape = tuple()
            else:
                newscanshape = (inext,)
        elif scanndim == 1:
            newscanshape = (max(shape[0], inext),)
        else:
            savecoord, newscanshape = self._save_shape_mindex(
                icurrent, inext, scanshape
            )
        if corder:
            newshape = newscanshape + newdetshape
        else:
            newshape = newdetshape + newscanshape
        self.current_scan_save_shape = newscanshape
        self.current_detector_shape = newdetshape

        # Extend dataset
        if shape != newshape:
            try:
                dset.resize(newshape)
            except (ValueError, TypeError):
                msg = "{} cannot be resized from {} to {}: {} points are not saved".format(
                    repr(dset.name), shape, newshape, nnew
                )
                self.logger.error(msg)
                return 0

        # Insert new data
        if scanndim == 0:
            dset[()] = newdata
        else:
            if corder:
                idx = [None] * scanndim + [slice(0, n) for n in newdata.shape[1:]]
            else:
                idx = [slice(0, n) for n in newdata.shape[1:]] + [None] * scanndim
            if scanndim == 1:
                # all at once
                if corder:
                    idx[0] = slice(icurrent, inext)
                else:
                    idx[-1] = slice(icurrent, inext)
                    axes = list(range(1, newdata.ndim)) + [0]
                    newdata = numpy.transpose(newdata, axes)
                dset[tuple(idx)] = newdata
            else:
                # point per point
                for coordi, newdatai in zip(zip(*savecoord), newdata):
                    idx[scanidx] = coordi
                    dset[tuple(idx)] = newdatai
        return nnew

    def _save_shape_mindex(self, icurrent, inext, scanshape):
        publishidx = list(range(icurrent, inext))
        while True:
            try:
                savecoord = self.saveorder.unravel(publishidx, scanshape)
            except ValueError:
                # Increase the variable dimension or
                # the slow dimension if fixed-length scan
                scanshape = list(scanshape)
                try:
                    vdim = scanshape.index(0)
                except ValueError:
                    if self.csaveorder:
                        vdim = 0
                    else:
                        vdim = -1
                scanshape[vdim] += 1
                scanshape = tuple(scanshape)
            else:
                break
        return savecoord, scanshape

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
                compression = "gzip"
            else:
                compression = None
        else:
            # variable length
            compression = "gzip"
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
        if self.dtype in (str, bytes):
            return ""
        fillvalue = numpy.nan
        try:
            numpy.array(fillvalue, self.dtype)
        except ValueError:
            fillvalue = 0
        return fillvalue

    @property
    def external_source_args(self):
        nframes = self.external_images_per_file
        if nframes is None:
            self.logger.warning("Number of frames per external file is not specified")
            return {}
        else:
            shape = (nframes,) + self.detector_shape
            return {"shape": shape, "dtype": self.dtype}

    @property
    def _dset_value(self):
        value = {"fillvalue": self.fillvalue, "dtype": self.dtype}
        if self._external_datasets:
            files, nuris, fill_generator = self._external_dataset_uris()
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
                    "merge {} URIs from {} files as a virtual dataset".format(
                        nuris, len(files)
                    )
                )
            else:
                value["compression"] = self.compression
                value["chunks"] = self.chunks
                self.logger.info(
                    "merge {} URIs from {} files as a copy (VDS not supported)".format(
                        nuris, len(files)
                    )
                )
        elif self._external_raw:
            self._get_external_raw(value)
            # Same number of external files as nframes
            nframes = shape_to_size(self.current_scan_save_shape)
            ext = os.path.splitext(self._external_raw[0][0])[-1]
            filename = self._dummy_filename(ext)
            nskip = h5_external.resize(value, nframes, filename, value["fillvalue"])
            if nskip > 0:
                self.logger.warning("Skip {} files".format(nskip))
            elif nskip < 0:
                self.logger.warning("Missing {} files".format(nskip))
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
            self.logger.info(
                "merge {} URIs as an external (non-HDF5) dataset".format(nuris)
            )
        elif self._external_names:
            value = []
            dirname = os.path.dirname(self.filename)
            for filename, ind in self._external_names:
                filename = os.path.relpath(filename, dirname)
                value.append("{}::{}".format(filename, ind))
            self.logger.info("merge {} URIs as a list of strings".format(len(value)))
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

        # Map uri to list of (idxin(int), idxout(tuple)) tuples
        uridict = OrderedDict()
        uris = self._get_external_datasets()
        if self.current_scan_save_shape:
            coordout = range(len(uris))
            coordout = self.saveorder.unravel(coordout, self.current_scan_save_shape)

            for (uri, idxin), idxout in zip(uris, zip(*coordout)):
                item = idxin, idxout
                if uri in uridict:
                    uridict[uri].append(item)
                else:
                    uridict[uri] = [item]
        else:
            uri, idxin = uris[0]
            item = idxin, tuple()
            uridict[uri] = [item]

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

    def _add_detidx(self, tpl, corder):
        if not isinstance(tpl, tuple):
            tpl = (tpl,)
        if self.detector_ndim:
            if corder:
                return tpl + (Ellipsis,)
            else:
                return (Ellipsis,) + tpl
        else:
            return tpl

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
                        self.logger.debug("Got URI from file {}".format(filename))
                        uridict[filename] = uri
                        break
                    else:
                        if not mon.is_growing():
                            raise RuntimeError(
                                "Cannot get URI from file {}".format(filename)
                            )
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

    @property
    def is_external(self):
        """
        "External" means a virtual dataset or a raw external dataset (for example links to EDF files)
        """
        return bool(
            self._external_datasets or self._external_raw or self._external_names
        )

    @property
    def is_internal(self):
        """
        "Internal" mean a normal HDF5 dataset
        """
        return self.exists and not self.is_external

    @property
    def interpretation(self):
        return nexus.nxDatasetInterpretation(
            self.scan_ndim, self.detector_ndim, self.ndim
        )

    @property
    def _dset_attrs(self):
        """
        HDF5 dataset attributes
        """
        attrs = self.device.get("data_info", {})
        interpretation = self.interpretation
        if interpretation:
            attrs["interpretation"] = interpretation
        attrs = {k: v for k, v in attrs.items() if v is not None}
        return attrs

    def _create(self, nxroot):
        """
        Create the dataset
        """
        parent = nxroot[self.parent]
        nexus.nxCreateDataSet(parent, self.name, self._dset_value, self._dset_attrs)

    @property
    def _progress_log_string(self):
        return " ({})".format(format_bytes(self.current_bytes))

    def reshape(self, scan_save_shape, detector_shape=None):
        """
        Reshape dataset (must exist when internal, should not exist when external)

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
        """
        Reshape HDF5 dataset if it exists

        :param tuple or None scan_save_shape:
        :param tuple or None detector_shape:
        :return bool:
        """
        with self.open(ensure_existance=True) as dset:
            if dset is None:
                self.logger.warning("Cannot reshape internal dataset before creation")
                return False
            shape = dset.shape
            if self.csaveorder:
                newshape = scan_save_shape + detector_shape
            else:
                newshape = detector_shape + scan_save_shape
            if dset.shape != newshape:
                self.logger.info("reshape from {} to {}".format(shape, newshape))
                try:
                    dset.resize(newshape)
                except TypeError as e:
                    self.logger.warning("Cannot be reshaped because '{}'".format(e))
                else:
                    return True
        return False

    def _reshape_external(self, scan_save_shape, detector_shape):
        """
        Reshape HDF5 dataset if it exists

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
                self.logger.info("remove {} points".format(nremove))
                lst = lst[:npoints]
            else:
                nadd = npoints - nlst
                self.logger.info("add {} dummy points".format(nadd))
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
        """
        URIs of dummy data (create when missing).

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
        name = (
            "_".join(map(str, self.current_detector_shape)) + "_" + self.dtype.__name__
        )
        return os.path.join(dirname, "dummy", "dummy_" + name + ext)

    def add_metadata(self, treedict, parent=False, **kwargs):
        """
        Add datasets/attributes (typically used for metadata)

        :param dict treedict:
        :param bool parent:
        :param kwargs: see `dicttonx`
        """
        with self.open(ensure_existance=True) as destination:
            if parent:
                destination = destination.parent
            nexus.dicttonx(treedict, destination, **kwargs)
