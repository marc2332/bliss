import pytest
import os
import numpy
import h5py
import fabio
import itertools

try:
    import gzip
except ImportError:
    gzip = None
from fabio.edfimage import EdfImage
from nexus_writer_service.io import h5_external
from nexus_writer_service.utils.array_order import Order


def test_h5ext_edf(scan_tmpdir):
    scan_shape = 2, 3
    image_shape = 5, 4
    files = edf_files(scan_tmpdir, scan_shape, image_shape)
    for data, filename, indices, order, compression in files:
        if indices:
            filenames = [(filename, i) for i in indices]
        else:
            filenames = filename
        # Save as HDF5:
        if compression != "NONE":
            with pytest.raises(RuntimeError):
                kwargs = h5_external.add_edf_arguments(filenames)
            continue
        else:
            kwargs = h5_external.add_edf_arguments(filenames)
            h5_external.finalize(kwargs, shape=scan_shape, addorder=order)
        # TODO: external datasets do not support relative paths
        # kwargs['external'] = [(os.path.relpath(tpl[0], str(scan_tmpdir)),) + tpl[1:]
        #                      for tpl in kwargs['external']]
        filename = os.path.join(str(scan_tmpdir), "out.h5")
        with h5py.File(filename, mode="w") as f:
            data2 = f.create_dataset("data", **kwargs)
            # Check HDF5
            numpy.testing.assert_array_equal(data, data2[()])


def test_h5ext_edf_append(scan_tmpdir):
    n = 3
    scan_shape_org = 2, 3
    image_shape = 5, 4
    scan_shape = 2, 3 * n
    enpoints = numpy.product(scan_shape)
    files = edf_files(scan_tmpdir, scan_shape_org, image_shape)
    for data, filename, indices, order, compression in files:
        if indices:
            filenames = [(filename, indices)]
        else:
            filenames = [filename]
        if compression != "NONE":
            continue
        for shape in tuple(), scan_shape:
            kwargs1 = {}
            for i in range(n):
                kwargs1 = h5_external.add_edf_arguments(filenames, createkwargs=kwargs1)
            h5_external.finalize(kwargs1, shape=shape, addorder=order)
            kwargs2 = h5_external.add_edf_arguments(filenames * n)
            h5_external.finalize(kwargs2, shape=shape, addorder=order)
            assert kwargs1 == kwargs2
            npoints = numpy.product(kwargs1["shape"]) // numpy.product(image_shape)
            assert npoints == enpoints


def edf_files(scan_tmpdir, scan_shape, image_shape):
    nimages = numpy.product(scan_shape)
    shape = scan_shape + image_shape
    fshape = (numpy.product(scan_shape),) + image_shape
    fdata = numpy.arange(numpy.product(shape))
    # Data save in C order
    data = fdata.reshape(shape, order="C")
    # Data publication in any order
    order = Order("C"), Order("F"), Order("C", caxes="all"), Order("F", caxes="all")
    compression = "NONE", "GZIP"
    withindices = False, True
    options = itertools.product(order, compression, withindices)
    for i, (order, compression, withindices) in enumerate(options):
        # Save as EDF:
        filename = os.path.join(str(scan_tmpdir), "out{}.edf".format(i))
        data1 = order.reshape(data, fshape)
        edf = None
        for img in data1:
            if compression == "GZIP":
                if gzip is None:
                    continue
            # header = {'COMPRESSION': compression}
            header = None
            if edf is None:
                edf = EdfImage(data=img, header=header)
            else:
                edf.append_frame(data=img, header=header)
        if compression == "GZIP":
            filename += ".gz"
            f = gzip.GzipFile(filename, "wb")
        else:
            f = filename
        edf.write(f)
        # Check EDF:
        edf = fabio.open(filename)
        data2 = numpy.array([frame.data for frame in edf.frames()])
        numpy.testing.assert_array_equal(data1, data2)
        if withindices:
            indices = list(range(nimages))
        else:
            indices = None
        yield data, filename, indices, order, compression
