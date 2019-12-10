# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import numpy
import random
import itertools
from fabio.edfimage import EdfImage
from nxw_test_math import asproduct
from nexus_writer_service.subscribers.dataset_proxy import DatasetProxy
from nexus_writer_service.io import nexus
from nexus_writer_service.utils.array_order import Order


def test_dataset_proxy(tmpdir):
    mainfile = os.path.join(str(tmpdir), "main.h5")
    with nexus.nxRoot(mainfile, mode="w") as nxroot:
        nexus.nxEntry(nxroot, "entry0000")

    dsetname_generator = name_generator("dataset{:04d}")

    scan_shapes = tuple(), (0,), (8,), (4, 8), (2, 4, 6)
    detector_shapes = tuple(), (3,), (3, 5)
    scan_save_ndims = 0, 1, 2
    saveorders = (
        Order(order="C"),
        Order(order="F"),
        Order(order="C", caxes="all"),
        Order(order="F", caxes="all"),
    )
    publishorders = tuple(saveorders)
    nextras = (0, -2, 2)
    datatypes = (None, "edf", "hdf5")

    options = [
        scan_shapes,
        detector_shapes,
        saveorders,
        publishorders,
        nextras,
        scan_save_ndims,
        datatypes,
    ]
    for params in itertools.product(*options):
        scan_shape, detector_shape, saveorder, publishorder, nextra, scan_save_ndim, datatype = (
            params
        )
        if datatype == "edf" and saveorder.forder:
            continue
        # Number of points published: npoints + nextra
        if not detector_shape and datatype:
            continue
        if not scan_shape:
            if nextra > 0:
                continue
            elif nextra < 0:
                nextra = -1
        # Scan part of the saved dataset shape
        npoints = numpy.prod(scan_shape, dtype=int)
        if npoints:
            # Fixed length scan
            lst = list(asproduct(npoints, scan_save_ndim, includeone=False))
            if not lst:
                continue
            escan_save_shape = scan_save_shape = random.choice(lst)
        else:
            # Variable length scan
            scan_save_shape = scan_shape
            escan_save_shape = tuple(n if n else i for i, n in enumerate(scan_shape, 4))
            npoints = numpy.prod(escan_save_shape, dtype=int)
        # Expected shape after publish + reshape
        edetector_shape = detector_shape
        if saveorder.corder:
            escan_shape = escan_save_shape + edetector_shape
        else:
            escan_shape = edetector_shape + escan_save_shape

        err_msg = str(
            {
                "scan_shape": scan_shape,
                "scan_save_shape": scan_save_shape,
                "detector_shape": detector_shape,
                "saveorder": str(saveorder),
                "publishorder": str(publishorder),
                "nextra": nextra,
                "npoints": npoints,
            }
        )

        name = next(dsetname_generator)
        dproxy = DatasetProxy(
            filename=mainfile,
            parent="/entry0000",
            device={"data_name": name, "data_info": {"units": "s"}},
            scan_shape=scan_shape,
            scan_save_shape=scan_save_shape,
            detector_shape=detector_shape,
            dtype=float,
            saveorder=saveorder,
            publishorder=publishorder,
        )

        # Add data
        if datatype == "hdf5":
            data_generator = hdf5_data_generator(tmpdir, "file", detector_shape)
        elif datatype == "edf":
            data_generator = edf_data_generator(tmpdir, "file", detector_shape)
        else:
            data_generator = mem_data_generator(detector_shape)
        add_data(dproxy, data_generator, npoints + nextra)

        # Make sure it exists with the expected shape
        dproxy.reshape(escan_save_shape)
        dproxy.ensure_existance()
        assert dproxy.current_scan_save_shape == escan_save_shape, err_msg
        assert dproxy.current_shape == escan_shape, err_msg
        assert dproxy.current_detector_shape == edetector_shape, err_msg
        _validate_data(dproxy, npoints, nextra, escan_save_shape, err_msg)


def _validate_data(dproxy, npoints, nextra, escan_save_shape, err_msg):
    if dproxy.csaveorder:
        detector_save_axes = tuple(
            range(dproxy.scan_save_ndim, dproxy.scan_save_ndim + dproxy.detector_ndim)
        )
    else:
        detector_save_axes = tuple(range(dproxy.detector_ndim))

    with dproxy.open() as dset:
        data = dset[()].max(axis=detector_save_axes)
        expected = numpy.arange(1, npoints + 1, dtype=dproxy.dtype)
        if nextra < 0:
            expected[nextra:] = dproxy.fillvalue
        if escan_save_shape:
            expected = dproxy.saveorder.reshape(expected, escan_save_shape)
        numpy.testing.assert_array_equal(data, expected, err_msg=err_msg)


def add_data(dproxy, data_generator, npoints):
    newdata = []
    for i in range(npoints):
        newdata.append(next(data_generator))
        if random.choice([0, 0, 1]):
            if isinstance(newdata[0], tuple):
                file_format = os.path.splitext(newdata[0][0])[-1][1:]
                dproxy.add_external(newdata, file_format=file_format)
            else:
                newdata = numpy.array(newdata)
                dproxy.add_internal(newdata)
            newdata = []
    if newdata:
        if isinstance(newdata[0], tuple):
            file_format = os.path.splitext(newdata[0][0])[-1][1:]
            dproxy.add_external(newdata, file_format=file_format)
        else:
            newdata = numpy.array(newdata)
            dproxy.add_internal(newdata)


def mem_data_generator(detector_shape):
    ndim = len(detector_shape)
    if ndim:
        x = numpy.mgrid[tuple(slice(None, n) for n in detector_shape)]
        n = numpy.prod(detector_shape)
        x = x.reshape((ndim, n))
        mu = numpy.array(detector_shape) // 2
        sigma = numpy.array(detector_shape) / 6
        cov = sigma[:, numpy.newaxis].dot(sigma[numpy.newaxis, :]) / 10
        cov[range(ndim), range(ndim)] *= 10
        data = ndgaussian(x, mu, cov).reshape(detector_shape)
        m = 1
        while True:
            yield m * data
            m += 1
    else:
        m = 1
        while True:
            yield m
            m += 1


def hdf5_data_generator(tmpdir, basename, detector_shape, nframes=3):
    fmt = os.path.join(str(tmpdir), basename + "{:04d}.hdf5")
    filename_generator = name_generator(fmt)
    data_generator = mem_data_generator(detector_shape)
    iframe = nframes
    shape = (nframes,) + detector_shape
    nxroot = None
    try:
        while True:
            data = next(data_generator)
            if iframe == nframes:
                datafile = next(filename_generator)
                if nxroot is not None:
                    nxroot.close()
                nxroot = nexus.nxRoot(datafile, mode="w")
                nxentry = nexus.nxEntry(nxroot, "entry0000")
                nxinstrument = nexus.nxInstrument(nxentry)
                nxdetector = nexus.nxDetector(nxinstrument, "detector")
                dtype = numpy.array(data).dtype
                dset = nxdetector.create_dataset(
                    "data", shape=shape, dtype=dtype, chunks=True, fillvalue=numpy.nan
                )
                nexus.markDefault(dset)
                iframe = 0
            dset[iframe] = data
            nxroot.flush()
            yield datafile, iframe
            iframe += 1
    finally:
        if nxroot is not None:
            nxroot.close()


def edf_data_generator(tmpdir, basename, detector_shape, nframes=3):
    fmt = os.path.join(str(tmpdir), basename + "{:04d}.edf")
    filename_generator = name_generator(fmt)
    if not detector_shape:
        detector_shape = 1, 1
    elif len(detector_shape) == 1:
        detector_shape = 1, detector_shape[0]
    data_generator = mem_data_generator(detector_shape)
    iframe = nframes
    while True:
        data = next(data_generator)
        if iframe == nframes:
            datafile = next(filename_generator)
            edffile = EdfImage(data=data)
            iframe = 0
        else:
            edffile.append_frame(data=data)
        edffile.write(datafile)
        yield datafile, iframe
        iframe += 1


def name_generator(fmt):
    i = 0
    while True:
        yield fmt.format(i)
        i += 1


def ndgaussian(x, mu, cov, normalize=False):
    """
    :param array x: ndim x n
    :param array mu: ndim
    :param array cov: ndim x ndim
    :param bool normalize:
    :returns array: n
    """
    ndim = x.shape[0]
    if ndim != len(mu) or (ndim, ndim) != cov.shape:
        raise ValueError("The dimensions of the input don't match")
    icov = numpy.linalg.inv(cov)
    result = x - mu[:, numpy.newaxis]
    result = result * icov.dot(result)
    result = numpy.exp(-result.sum(axis=0) / 2)
    if normalize:
        result /= (2 * numpy.pi) ** (ndim / 2) * numpy.linalg.det(cov) ** 0.5
    return result
