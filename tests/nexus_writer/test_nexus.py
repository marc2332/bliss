# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import os
import numpy
from contextlib import contextmanager
import h5py.h5t
from nexus_writer_service.io import nexus


@contextmanager
def nxroot(path, name):
    filename = os.path.join(str(path), name + ".h5")
    with nexus.nxRoot(filename, mode="a") as f:
        yield f


def test_nexus_root(scan_tmpdir):
    with nxroot(scan_tmpdir, "test_nexus_root") as h5group:
        validateNxRoot(h5group)


def test_nexus_entry(scan_tmpdir):
    with nxroot(scan_tmpdir, "test_nexus_entry") as h5group:
        entry = nexus.nxEntry(h5group, "entry0001")
        nexus.updated(entry, final=True)
        with pytest.raises(RuntimeError):
            nexus.nxEntry(entry, "entry0002")
        validateNxEntry(entry)


def test_nexus_process(scan_tmpdir):
    with nxroot(scan_tmpdir, "test_nexus_process") as h5group:
        entry = nexus.nxEntry(h5group, "entry0001")
        configdict = {"a": 1, "b": 2}
        for i, type in enumerate(["json", "ini", None]):
            process = nexus.nxProcess(
                entry, "process{:04d}".format(i), configdict=configdict, type=type
            )
            with pytest.raises(RuntimeError):
                nexus.nxProcess(h5group, "process0002", configdict=configdict)
            validateNxProcess(process)


def test_nexus_data(scan_tmpdir):
    with nxroot(scan_tmpdir, "test_nexus_data") as h5group:
        entry = nexus.nxEntry(h5group, "entry0001")
        process = nexus.nxProcess(entry, "process0001")
        data = nexus.nxData(process["results"], "data")
        s = (4, 3, 2)
        datadict = {
            "Fe K": numpy.arange(numpy.product(s), dtype=float).reshape(s),
            "Ca K": numpy.arange(numpy.product(s)).reshape(s) + 1,
            "S K": numpy.zeros(s),
        }
        axes = [
            ("y", numpy.arange(s[0]), {"units": "um"}),
            ("x", numpy.arange(s[1]), {}),
            ("z", {"shape": (s[2],), "dtype": int}, None),
        ]
        signals = [
            ("Fe K", datadict["Fe K"], {"interpretation": "image"}),
            ("Ca K", {"data": datadict["Ca K"]}, {}),
            ("S K", {"shape": s, "dtype": int}, None),
        ]
        nexus.nxDataAddAxes(data, axes)
        nexus.nxDataAddSignals(data, signals)

        validateNxData(data, axes, signals)
        signals = nexus.nxDataGetSignals(data)
        assert signals == ["Fe K", "Ca K", "S K"]

        nexus.markDefault(data["Ca K"])
        default = data.file[nexus.getDefault(data.file, signal=False)]
        default = nexus.dereferenceUri(nexus.getUri(default))
        assert default == nexus.getUri(data)
        default = data.file[nexus.getDefault(data.file, signal=True)]
        default = nexus.dereferenceUri(nexus.getUri(default))
        assert default == nexus.getUri(data["Ca K"])

        data = entry[nexus.DEFAULT_PLOT_NAME]
        signals = nexus.nxDataGetSignals(data)
        assert signals == ["Ca K", "Fe K", "S K"]
        assert data["y"].attrs["units"] == "um"
        assert data["Fe K"].attrs["interpretation"] == "image"
        for name in signals:
            assert data[name].shape == s
        for n, name in zip(s, list(next(iter(zip(*axes))))):
            assert data[name].shape == (n,)

        # Test dataset concatenation
        def vdatanamegen():
            c = 0
            while True:
                yield "vdata{}".format(c)
                c += 1

        vdataname = vdatanamegen()
        for virtual in False, True:
            value = {
                "axis": 0,
                "newaxis": True,
                "virtual": virtual,
                "data": [nexus.getUri(data[name]) for name in datadict],
            }
            vdata = nexus.nxCreateDataSet(process, next(vdataname), value, None)
            for i, name in enumerate(datadict):
                numpy.testing.assert_array_equal(datadict[name], vdata[i])
            value["axis"] = 1
            vdata1 = nexus.nxCreateDataSet(process, next(vdataname), value, None)
            for i, name in enumerate(datadict):
                numpy.testing.assert_array_equal(datadict[name], vdata1[:, i])
            value["axis"] = 0
            value["newaxis"] = False
            vdata = nexus.nxCreateDataSet(process, next(vdataname), value, None)
            for i, name in enumerate(datadict):
                numpy.testing.assert_array_equal(
                    datadict[name], vdata[i * s[0] : (i + 1) * s[0]]
                )
            value["axis"] = 1
            vdata = nexus.nxCreateDataSet(process, next(vdataname), value, None)
            for i, name in enumerate(datadict):
                numpy.testing.assert_array_equal(
                    datadict[name], vdata[:, i * s[1] : (i + 1) * s[1]]
                )
            value["data"].append(nexus.getUri(data["y"]))
            with pytest.raises(RuntimeError):
                nexus.nxCreateDataSet(process, next(vdataname), value, None)


def test_nexus_StringAttribute(scan_tmpdir):
    check_string_types(scan_tmpdir, attribute=True, raiseExtended=True)


def test_nexus_StringDataset(scan_tmpdir):
    check_string_types(scan_tmpdir, attribute=False, raiseExtended=True)


def test_nexus_ExtStringAttribute(scan_tmpdir):
    check_string_types(scan_tmpdir, attribute=True, raiseExtended=False)


def test_nexus_ExtStringDataset(scan_tmpdir):
    check_string_types(scan_tmpdir, attribute=False, raiseExtended=False)


def test_nexus_uri(scan_tmpdir):
    path = str(scan_tmpdir)

    uri = "test1.h5::/a::/b"
    a, b = nexus.splitUri(uri)
    assert a == "test1.h5"
    assert b == "/a::/b"

    uri = nexus.normUri("./test1.h5::/a/../b")
    assert uri == "test1.h5::/b"

    uri = "test1.h5::/a/b"
    uriref = "test1.h5::/a"
    a, b = nexus.relUri(uri, uriref)
    assert a == "."
    assert b == "b"

    uri = os.path.join(path, "test1.h5::/a/b")
    uriref = os.path.join(path, "test1.h5::/a")
    a, b = nexus.relUri(uri, uriref)
    assert a == "."
    assert b == "b"

    uri = "test1.h5::/a/b"
    uriref = "test2.h5::/a"
    a, b = nexus.relUri(uri, uriref)
    assert a == "test1.h5"
    assert b == "/a/b"

    uri = os.path.join(path, "test1.h5::/a/b")
    uriref = os.path.join(path, "test2.h5::/a")
    a, b = nexus.relUri(uri, uriref)
    assert a == "./test1.h5"
    assert b == "/a/b"

    uri = os.path.join(path, "..", "test1.h5::/a/b")
    uriref = os.path.join(path, "test2.h5::/a")
    a, b = nexus.relUri(uri, uriref)
    assert a == "../test1.h5"
    assert b == "/a/b"


def test_nexus_links(scan_tmpdir):
    def namegen():
        i = 1
        while True:
            yield "link" + str(i)
            i += 1

    linkname = namegen()
    with nxroot(scan_tmpdir, os.path.join("a", "b", "test1")) as f1:
        f1.create_group("a/b/c")
        g = f1["/a/b"]
        _same_target(g, g)
        # internal link up
        name = next(linkname)
        nexus.createLink(g, name, f1["a"])
        _same_target(f1["a"], g[name])
        link = g.get(name, getlink=True)
        assert link.path == "/a"
        assert isinstance(link, h5py.SoftLink)
        # internal link same level
        name = next(linkname)
        nexus.createLink(g, name, f1["a/b"])
        _same_target(f1["a/b"], g[name])
        link = g.get(name, getlink=True)
        assert link.path == "."
        assert isinstance(link, h5py.SoftLink)
        # internal link down
        name = next(linkname)
        nexus.createLink(g, name, f1["a/b/c"])
        _same_target(f1["a/b/c"], g[name])
        link = g.get(name, getlink=True)
        assert link.path == "c"
        assert isinstance(link, h5py.SoftLink)
        # external link down
        with nxroot(scan_tmpdir, os.path.join("a", "test2")) as f2:
            name = next(linkname)
            nexus.createLink(f2, name, f1["a"])
            link = f2.get(name, getlink=True)
            _same_target(f1["a"], f2[name])
            assert link.path == "/a"
            assert link.filename == "b/test1.h5"
            assert isinstance(link, h5py.ExternalLink)
        # internal link same level
        with nxroot(scan_tmpdir, os.path.join("a", "b", "test2")) as f2:
            name = next(linkname)
            nexus.createLink(f2, name, f1["a"])
            link = f2.get(name, getlink=True)
            # _same_target(f1["a"], f2[name])
            assert link.path == "/a"
            assert link.filename == "./test1.h5"
            assert isinstance(link, h5py.ExternalLink)
        # external link up
        with nxroot(scan_tmpdir, os.path.join("a", "b", "c", "test2")) as f2:
            name = next(linkname)
            nexus.createLink(f2, name, f1["a"])
            _same_target(f1["a"], f2[name])
            link = f2.get(name, getlink=True)
            assert link.path, "/a"
            assert link.filename == "../test1.h5"
            assert isinstance(link, h5py.ExternalLink)


def _same_target(node1, node2):
    target1 = nexus.dereferenceUri(nexus.getUri(node1))
    target2 = nexus.dereferenceUri(nexus.getUri(node2))
    assert nexus.normUri(target1) == nexus.normUri(target2)


def test_nexus_reshape_datasets(scan_tmpdir):
    shape = 12, 5
    vshape = 3, 4, 5
    order = "C"

    def flatten(arr):
        return arr.flatten(order=order)

    kwargs = {
        "axis": 0,
        "virtual": True,
        "newaxis": False,
        "shape": vshape,
        "order": order,
        "fillvalue": 0,
    }
    fdatamem = numpy.arange(numpy.product(shape))
    datamem = fdatamem.reshape(shape, order=order)
    filenames = (
        os.path.join("basedir1", "test1"),
        os.path.join("basedir1", "test2"),
        os.path.join("basedir1", "subdir", "test3"),
    )
    with nxroot(scan_tmpdir, filenames[0]) as root1:
        with nxroot(scan_tmpdir, filenames[1]) as root2:
            with nxroot(scan_tmpdir, filenames[2]) as root3:
                for root in root1, root2, root3:
                    g = root.create_group("a")
                    g.create_group("b")
                    g["data"] = datamem
                    # Internal links
                    kwargs["data"] = [nexus.getUri(root["/a/data"])]
                    dset = nexus.nxCreateDataSet(root, "vdata", kwargs, None)
                    numpy.testing.assert_array_equal(
                        fdatamem, flatten(dset[()]), err_msg=nexus.getUri(dset)
                    )
                    dset = nexus.nxCreateDataSet(root["/a"], "vdata", kwargs, None)
                    numpy.testing.assert_array_equal(
                        fdatamem, flatten(dset[()]), err_msg=nexus.getUri(dset)
                    )
                    dset = nexus.nxCreateDataSet(root["/a/b"], "vdata", kwargs, None)
                    numpy.testing.assert_array_equal(
                        fdatamem, flatten(dset[()]), err_msg=nexus.getUri(dset)
                    )
                # root1 -> root2, root3
                kwargs["data"] = [nexus.getUri(root1["/a/data"])]
                for root in root2, root3:
                    dset = nexus.nxCreateDataSet(root, "vdatae", kwargs, None)
                    numpy.testing.assert_array_equal(
                        fdatamem, flatten(dset[()]), err_msg=nexus.getUri(dset)
                    )
                    dset = nexus.nxCreateDataSet(root["/a"], "vdatae", kwargs, None)
                    numpy.testing.assert_array_equal(
                        fdatamem, flatten(dset[()]), err_msg=nexus.getUri(dset)
                    )
                    dset = nexus.nxCreateDataSet(root["/a/b"], "vdatae", kwargs, None)
                    numpy.testing.assert_array_equal(
                        fdatamem, flatten(dset[()]), err_msg=nexus.getUri(dset)
                    )
                # root2 -> root1
                kwargs["data"] = [nexus.getUri(root2["/a/data"])]
                dset = nexus.nxCreateDataSet(root1, "vdatae", kwargs, None)
                numpy.testing.assert_array_equal(
                    fdatamem, flatten(dset[()]), err_msg=nexus.getUri(dset)
                )
                dset = nexus.nxCreateDataSet(root1["/a"], "vdatae", kwargs, None)
                numpy.testing.assert_array_equal(
                    fdatamem, flatten(dset[()]), err_msg=nexus.getUri(dset)
                )
                dset = nexus.nxCreateDataSet(root1["/a/b"], "vdatae", kwargs, None)
                numpy.testing.assert_array_equal(
                    fdatamem, flatten(dset[()]), err_msg=nexus.getUri(dset)
                )

    paths = ("/vdata", "/vdatae", "/a/vdata", "/a/vdatae", "/a/b/vdata", "/a/b/vdatae")
    for filename in filenames:
        with nxroot(scan_tmpdir, filename) as root:
            data = root["/a/data"]
            assert shape == data.shape
            numpy.testing.assert_array_equal(fdatamem, flatten(data[()]))
            for path in paths:
                vdata = root[path]
                assert vshape == vdata.shape
                numpy.testing.assert_array_equal(
                    fdatamem, flatten(vdata[()]), err_msg=nexus.getUri(vdata)
                )

    dirname = str(scan_tmpdir)
    os.rename(os.path.join(dirname, "basedir1"), os.path.join(dirname, "basedir2"))
    os.rename(
        os.path.join(dirname, "basedir2", "test2.h5"),
        os.path.join(dirname, "basedir2", "test2_.h5"),
    )
    os.rename(
        os.path.join(dirname, "basedir2", "subdir", "test3.h5"),
        os.path.join(dirname, "basedir2", "subdir", "test3_.h5"),
    )
    filenames = (
        os.path.join("basedir2", "test1"),
        os.path.join("basedir2", "test2_"),
        os.path.join("basedir2", "subdir", "test3_"),
    )
    lostlinks = [
        ("/vdatae", "/a/vdatae", "/a/b/vdatae"),
        tuple(),
        ("/vdatae", "/a/vdatae", "/a/b/vdatae"),
    ]
    for filename, lost in zip(filenames, lostlinks):
        with nxroot(scan_tmpdir, filename) as root:
            data = root["/a/data"]
            assert shape == data.shape
            numpy.testing.assert_array_equal(fdatamem, flatten(data[()]))
            for path in paths:
                vdata = root[path]
                assert vshape == vdata.shape
                isequal = (fdatamem == flatten(vdata[()])).all()
                if path in lost:
                    assert not isequal, nexus.getUri(vdata)
                else:
                    assert isequal, nexus.getUri(vdata)


def validateNxRoot(h5group):
    attrs = [
        "NX_class",
        "creator",
        "HDF5_Version",
        "file_name",
        "file_time",
        "file_update_time",
        "h5py_version",
    ]
    assert set(h5group.attrs.keys()) == set(attrs)
    assert h5group.attrs["NX_class"] == "NXroot"
    assert h5group.name == "/"


def validateNxEntry(h5group):
    attrs = ["NX_class"]
    assert set(h5group.attrs.keys()) == set(attrs)
    files = ["start_time", "end_time"]
    assert set(h5group.keys()) == set(files)
    assert h5group.attrs["NX_class"] == "NXentry"
    assert h5group.parent.name == "/"


def validateNxProcess(h5group):
    attrs = ["NX_class"]
    assert set(h5group.attrs.keys()) == set(attrs)
    files = ["program", "version", "configuration", "date", "results"]
    assert set(h5group.keys()) == set(files)
    assert h5group.attrs["NX_class"] == "NXprocess"
    assert h5group.parent.attrs["NX_class"] == "NXentry"
    validateNxNote(h5group["configuration"])
    validateNxCollection(h5group["results"])


def validateNxNote(h5group):
    attrs = ["NX_class"]
    assert set(h5group.attrs.keys()) == set(attrs)
    files = ["date", "data", "type"]
    assert set(h5group.keys()) == set(files)
    assert h5group.attrs["NX_class"] == "NXnote"


def validateNxCollection(h5group):
    attrs = ["NX_class"]
    assert set(h5group.attrs.keys()) == set(attrs)
    assert h5group.attrs["NX_class"] == "NXcollection"


def validateNxData(h5group, axes, signals):
    attrs = ["NX_class", "axes", "signal", "auxiliary_signals"]
    assert set(h5group.attrs.keys()) == set(attrs)
    files = list(next(iter(zip(*axes)))) + list(next(iter(zip(*signals))))
    assert set(h5group.keys()) == set(files)
    assert h5group.attrs["NX_class"] == "NXdata"


def check_string_types(scan_tmpdir, attribute=True, raiseExtended=True):
    # Test following string literals
    sAsciiBytes = b"abc"
    sAsciiUnicode = u"abc"
    sLatinBytes = b"\xe423"
    sLatinUnicode = u"\xe423"  # not used
    sUTF8Unicode = u"\u0101bc"
    sUTF8Bytes = b"\xc4\x81bc"
    sUTF8AsciiUnicode = u"abc"
    sUTF8AsciiBytes = b"abc"
    # Expected conversion after HDF5 write/read
    strmap = {}
    strmap["ascii(scalar)"] = sAsciiBytes, sAsciiUnicode
    strmap["ext(scalar)"] = sLatinBytes, sLatinBytes
    strmap["unicode(scalar)"] = sUTF8Unicode, sUTF8Unicode
    strmap["unicode2(scalar)"] = sUTF8AsciiUnicode, sUTF8AsciiUnicode
    strmap["ascii(list)"] = [sAsciiBytes, sAsciiBytes], [sAsciiUnicode, sAsciiUnicode]
    strmap["ext(list)"] = [sLatinBytes, sLatinBytes], [sLatinBytes, sLatinBytes]
    strmap["unicode(list)"] = [sUTF8Unicode, sUTF8Unicode], [sUTF8Unicode, sUTF8Unicode]
    strmap["unicode2(list)"] = (
        [sUTF8AsciiUnicode, sUTF8AsciiUnicode],
        [sUTF8AsciiUnicode, sUTF8AsciiUnicode],
    )
    strmap["mixed(list)"] = (
        [sUTF8Unicode, sUTF8AsciiUnicode, sAsciiBytes, sLatinBytes],
        [sUTF8Bytes, sUTF8AsciiBytes, sAsciiBytes, sLatinBytes],
    )
    strmap["ascii(0d-array)"] = numpy.array(sAsciiBytes), sAsciiUnicode
    strmap["ext(0d-array)"] = numpy.array(sLatinBytes), sLatinBytes
    strmap["unicode(0d-array)"] = numpy.array(sUTF8Unicode), sUTF8Unicode
    strmap["unicode2(0d-array)"] = numpy.array(sUTF8AsciiUnicode), sUTF8AsciiUnicode
    strmap["ascii(1d-array)"] = (
        numpy.array([sAsciiBytes, sAsciiBytes]),
        [sAsciiUnicode, sAsciiUnicode],
    )
    strmap["ext(1d-array)"] = (
        numpy.array([sLatinBytes, sLatinBytes]),
        [sLatinBytes, sLatinBytes],
    )
    strmap["unicode(1d-array)"] = (
        numpy.array([sUTF8Unicode, sUTF8Unicode]),
        [sUTF8Unicode, sUTF8Unicode],
    )
    strmap["unicode2(1d-array)"] = (
        numpy.array([sUTF8AsciiUnicode, sUTF8AsciiUnicode]),
        [sUTF8AsciiUnicode, sUTF8AsciiUnicode],
    )
    strmap["mixed(1d-array)"] = (
        numpy.array([sUTF8Unicode, sUTF8AsciiUnicode, sAsciiBytes]),
        [sUTF8Unicode, sUTF8AsciiUnicode, sAsciiUnicode],
    )
    strmap["mixed2(1d-array)"] = (
        numpy.array([sUTF8AsciiUnicode, sAsciiBytes]),
        [sUTF8AsciiUnicode, sAsciiUnicode],
    )

    with nxroot(scan_tmpdir, "test_nexus_String{:d}".format(attribute)) as h5group:
        h5group = h5group.create_group("test")
        if attribute:
            out = h5group.attrs
        else:
            out = h5group
        for name, (value, expectedValue) in strmap.items():
            decodingError = "ext" in name or name == "mixed(list)"
            if raiseExtended and decodingError:
                with pytest.raises(UnicodeDecodeError):
                    ovalue = nexus.asNxChar(value, raiseExtended=raiseExtended)
                continue
            else:
                ovalue = nexus.asNxChar(value, raiseExtended=raiseExtended)
            # Write/read
            out[name] = ovalue
            if attribute:
                value = out[name]
            else:
                value = out[name][()]
            # Expected type and value?
            if "list" in name or "1d-array" in name:
                assert isinstance(value, numpy.ndarray)
                value = value.tolist()
                assert list(map(type, value)) == list(map(type, expectedValue)), name
                firstValue = value[0]
            else:
                firstValue = value
            msg = "{} {} instead of {}".format(name, type(value), type(expectedValue))
            assert type(value) == type(expectedValue), msg
            assert value == expectedValue, msg
            # Expected character set?
            if not attribute:
                charSet = out[name].id.get_type().get_cset()
                if isinstance(firstValue, bytes):
                    # This is the tricky part, CSET_ASCII is supposed to be
                    # only 0-127 while we actually allow 0-255
                    expectedCharSet = h5py.h5t.CSET_ASCII
                else:
                    expectedCharSet = h5py.h5t.CSET_UTF8
                msg = "{} type {} instead of {}".format(name, charSet, expectedCharSet)
                assert charSet == expectedCharSet, msg


def test_nexus_exists(scan_tmpdir):
    with nxroot(scan_tmpdir, "test_nexus_entry") as root:
        uri = nexus.getUri(root)
        assert nexus.exists(uri)

        parent = root
        uri = nexus.hdf5_join(nexus.getUri(parent), "entry")
        assert not nexus.exists(uri)
        entry = nexus.nxEntry(parent, "entry")
        assert nexus.exists(uri)
        with pytest.raises(nexus.NexusInstanceExists):
            nexus.nxEntry(parent, "entry", raise_on_exists=True)

        parent = entry
        uri = nexus.hdf5_join(nexus.getUri(parent), "collection")
        assert not nexus.exists(uri)
        collection = nexus.nxCollection(parent, "collection")
        assert nexus.exists(uri)
        with pytest.raises(nexus.NexusInstanceExists):
            nexus.nxCollection(parent, "collection", raise_on_exists=True)
        # with pytest.raises(RuntimeError):
        nexus.nxCollection(root, "collection")

        parent = entry
        uri = nexus.hdf5_join(nexus.getUri(parent), "process")
        assert not nexus.exists(uri)
        process = nexus.nxProcess(parent, "process")
        assert nexus.exists(uri)
        with pytest.raises(nexus.NexusInstanceExists):
            nexus.nxProcess(parent, "process", raise_on_exists=True)

        parent = entry
        uri = nexus.hdf5_join(nexus.getUri(parent), "subentry")
        assert not nexus.exists(uri)
        subentry = nexus.nxSubEntry(parent, "subentry")
        assert nexus.exists(uri)
        with pytest.raises(nexus.NexusInstanceExists):
            nexus.nxSubEntry(parent, "subentry", raise_on_exists=True)

        parent = entry
        uri = nexus.hdf5_join(nexus.getUri(parent), "plot")
        assert not nexus.exists(uri)
        data = nexus.nxData(parent, "plot")
        assert nexus.exists(uri)
        with pytest.raises(nexus.NexusInstanceExists):
            nexus.nxData(parent, "plot", raise_on_exists=True)

        parent = entry
        uri = nexus.hdf5_join(nexus.getUri(parent), "instrument")
        assert not nexus.exists(uri)
        instrument = nexus.nxInstrument(parent, "instrument")
        assert nexus.exists(uri)
        with pytest.raises(nexus.NexusInstanceExists):
            nexus.nxInstrument(parent, "instrument", raise_on_exists=True)

        parent = instrument
        uri = nexus.hdf5_join(nexus.getUri(parent), "detector")
        assert not nexus.exists(uri)
        detector = nexus.nxDetector(parent, "detector")
        assert nexus.exists(uri)
        with pytest.raises(nexus.NexusInstanceExists):
            nexus.nxDetector(parent, "detector", raise_on_exists=True)

        parent = instrument
        uri = nexus.hdf5_join(nexus.getUri(parent), "positioner")
        assert not nexus.exists(uri)
        positioner = nexus.nxPositioner(parent, "positioner")
        assert nexus.exists(uri)
        with pytest.raises(nexus.NexusInstanceExists):
            nexus.nxPositioner(parent, "positioner", raise_on_exists=True)


def test_nexus_dicttonx_dataset(scan_tmpdir):
    with nxroot(scan_tmpdir, "test_nexus_dicttonx_dataset") as group:
        dsetorg = dset = nexus._dicttonx_create_dataset(
            group, "dataset", [1, 2, 3], overwrite=False, update=False
        )
        nexus._dicttonx_create_attr(dset, "attr", "a", update=False)
        assert dset[()].tolist() == [1, 2, 3]
        assert dset.attrs["attr"] == "a"
        assert dset.id == dsetorg.id
        # Preserve values and attributes
        dset = nexus._dicttonx_create_dataset(
            group, "dataset", [4, 5, 6], overwrite=False, update=False
        )
        nexus._dicttonx_create_attr(dset, "attr", "b", update=False)
        assert dset[()].tolist() == [1, 2, 3]
        assert dset.attrs["attr"] == "a"
        assert dset.id == dsetorg.id
        # Preserve values but not attributes
        dset = nexus._dicttonx_create_dataset(
            group, "dataset", [4, 5, 6], overwrite=False, update=False
        )
        nexus._dicttonx_create_attr(dset, "attr", "b", update=True)
        assert dset[()].tolist() == [1, 2, 3]
        assert dset.attrs["attr"] == "b"
        assert dset.id == dsetorg.id
        # Preserve attributes but not values
        dset = nexus._dicttonx_create_dataset(
            group, "dataset", [4, 5, 7], overwrite=False, update=True
        )
        assert dset[()].tolist() == [4, 5, 7]
        assert dset.attrs["attr"] == "b"
        assert dset.id == dsetorg.id
        # Preserve attributes but not values
        dset = nexus._dicttonx_create_dataset(
            group, "dataset", [7, 8], overwrite=False, update=True
        )
        assert dset[()].tolist() == [7, 8]
        assert dset.attrs["attr"] == "b"
        assert dset.id != dsetorg.id
        # Do not preserve values nor attributes
        dsetorg = dset
        dset = nexus._dicttonx_create_dataset(
            group, "dataset", [9, 10], overwrite=True, update=False
        )
        assert dset[()].tolist() == [9, 10]
        assert "attr" not in dset.attrs
        assert dset.id == dsetorg.id
        dset.attrs["attr"] = "b"
        # Do not preserve values nor attributes
        dset = nexus._dicttonx_create_dataset(
            group, "dataset", [12, 13, 14], overwrite=True, update=False
        )
        assert dset[()].tolist() == [12, 13, 14]
        assert "attr" not in dset.attrs
        assert dset.id != dsetorg.id


def test_nexus_dicttonx_group(scan_tmpdir):
    with nxroot(scan_tmpdir, "test_nexus_dicttonx_group") as root:
        grouporg = group = nexus._dicttonx_create_group(root, "group", overwrite=False)
        group["dataset"] = [1, 2, 3]
        nexus._dicttonx_create_attr(group, "attr", "a")
        assert group.attrs["attr"] == "a"
        assert list(group.keys()) == ["dataset"]
        assert group.id == grouporg.id
        # Preserve datasets and attributes
        group = nexus._dicttonx_create_group(root, "group", overwrite=False)
        assert group.attrs["attr"] == "a"
        assert list(group.keys()) == ["dataset"]
        assert group.id == grouporg.id
        # Do not preserve datasets and attributes
        group = nexus._dicttonx_create_group(root, "group", overwrite=True)
        assert "attr" not in group.attrs
        assert list(group.keys()) == []
        assert group.id == grouporg.id


def test_nexus_dictdump(scan_tmpdir):
    with nxroot(scan_tmpdir, "test_nexus_dictdump") as root:
        group = root.create_group("group")
        treedict1 = {
            "group1": {"a": 1, "b": 2},
            "group2": {
                "@NX_class": "NXentry",
                "@attr1": "attr1",
                "@attr2": "attr2",
                "c": 3,
                "d": 4,
                "dataset4": {"@data": 8, "@units": "keV"},
            },
            "group3": {"subgroup": {"e": 9, "f": 10}},
            "dataset1": 5,
            "dataset2": {"@data": 6},
            "dataset3": {"@data": 7, "@units": "mm"},
        }
        treedict2 = {
            "@NX_class": "NXcollection",
            "group1": {"@NX_class": "NXcollection", "a": 1, "b": 2},
            "group2": {
                "@NX_class": "NXentry",
                "@attr1": "attr1",
                "@attr2": "attr2",
                "c": 3,
                "d": 4,
                "dataset4": {"@data": 8, "@units": "keV"},
            },
            "group3": {
                "@NX_class": "NXcollection",
                "subgroup": {"@NX_class": "NXcollection", "e": 9, "f": 10},
            },
            "dataset1": 5,
            "dataset2": 6,
            "dataset3": {"@data": 7, "@units": "mm"},
        }
        nexus.dicttonx(treedict1, group, overwrite=False, update=False)
        treedict3 = nexus.nxtodict(group)
        assert treedict2 == treedict3
        # Add non-existing attributes/datasets/groups
        treedict1["group1"].pop("a")
        treedict1["group2"].pop("@attr1")
        treedict1["group2"]["@attr2"] = "attr3"
        treedict1["group2"]["@type"] = "test"
        treedict1["group2"]["dataset4"] = {"@data": 9}
        treedict1["group3"] = {}
        treedict2["group2"]["@type"] = "test"
        nexus.dicttonx(treedict1, group, overwrite=False, update=False)
        treedict3 = nexus.nxtodict(group)
        assert treedict2 == treedict3
        # Add update existing attributes and datasets
        treedict2["group2"]["@attr2"] = "attr3"
        treedict2["group2"]["dataset4"]["@data"] = 9
        nexus.dicttonx(treedict1, group, overwrite=False, update=True)
        treedict3 = nexus.nxtodict(group)
        assert treedict2 == treedict3
        # Overwrite existing groups/datasets (existing datasets/attributes will be removed)
        treedict2["group1"].pop("a")
        treedict2["group2"].pop("@attr1")
        treedict2["group2"]["dataset4"] = 9
        treedict2["group3"] = {"@NX_class": "NXcollection"}
        nexus.dicttonx(treedict1, group, overwrite=True, update=False)
        treedict3 = nexus.nxtodict(group)
        assert treedict2 == treedict3
