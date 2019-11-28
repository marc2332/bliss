# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import numpy
from nexus_writer_service.utils import scan_utils
from nexus_writer_service.io import nexus
from nexus_writer_service.scan_writers.writer_base import (
    default_saveoptions as base_options
)
from nexus_writer_service.scan_writers.writer_config import (
    default_saveoptions as config_options
)
import nxw_test_config
import nxw_test_utils


def assert_scan_data(scan, writer_stdout=None, **kwargs):
    """
    :param bliss.scanning.scan.Scan scan:
    :param io.BufferedIOBase writer_stdout:
    """
    # scan_utils.open_data(scan, subscan=subscan, config=config, block=True)
    try:
        validate_scan_data(scan, **kwargs)
    except Exception:
        if writer_stdout is not None:
            nxw_test_utils.print_output(writer_stdout)
        raise


def validate_scan_data(
    scan,
    subscan=1,
    masters=None,
    scan_shape=None,
    config=True,
    withpolicy=True,
    alt=False,
):
    """
    :param bliss.scanning.scan.Scan scan:
    :param int subscan:
    :param tuple masters: fast axis first by default 'timer' when 1D scan or None otherwise
    :param tuple scan_shape: fast axis first 0D scan by default
    :param bool config: configurable writer
    :param bool withpolicy: data policy
    :param bool alt: alternative writer options
    """
    # Parse arguments
    if config:
        save_options = config_options
    else:
        save_options = base_options
    if alt:
        save_options = {k: not v for k, v in save_options.items()}
    if scan_shape is None:
        scan_shape = tuple()
    if masters is None:
        if not scan_shape:
            masters = tuple()
        elif len(scan_shape) == 1:
            if save_options["multivalue_positioners"]:
                masters = ("timer",)
            else:
                masters = ("elapsed_time",)
    assert len(scan_shape) == len(masters)
    if withpolicy:
        det_technique = nxw_test_config.technique["withpolicy"]
    else:
        det_technique = nxw_test_config.technique["withoutpolicy"]
    if config:
        scan_technique = scan.scan_info["nxwriter"]["technique"]["name"]
    else:
        scan_technique = det_technique
    # Validate NXentry links
    validate_master_links(scan, config=config)
    # Validate NXentry content
    uri = scan_utils.scan_uri(scan, subscan=subscan, config=config)
    with nexus.uriContext(uri) as nxentry:
        validate_nxentry(
            nxentry, config=config, withpolicy=withpolicy, technique=scan_technique
        )
        validate_measurement(
            nxentry["measurement"],
            scan_shape=scan_shape,
            config=config,
            masters=masters,
            technique=det_technique,
            save_options=save_options,
        )
        validate_instrument(
            nxentry["instrument"],
            scan_shape=scan_shape,
            config=config,
            masters=masters,
            withpolicy=withpolicy,
            technique=det_technique,
            save_options=save_options,
        )
        plots = expected_plots(scan_technique, config=config, withpolicy=withpolicy)
        for (detector_ndim, ptype), names in plots.items():
            for name in names:
                validate_nxdata(
                    nxentry[name],
                    detector_ndim,
                    ptype,
                    scan_shape=scan_shape,
                    masters=masters,
                    save_options=save_options,
                )


def validate_master_links(scan, subscan=1, config=True):
    """
    Check whether all files contain the scan entry.

    :param bliss.scanning.scan.Scan scan:
    :param bool config: configurable writer
    """
    uri = scan_utils.scan_uri(scan, subscan=subscan, config=config)
    uri = nexus.normUri(uri)
    for filename in scan_utils.scan_filenames(scan, config=config):
        with nexus.nxRoot(filename) as nxroot:
            for key in nxroot:
                if uri == nexus.normUri(nexus.getUri(nxroot[key])):
                    break
            else:
                assert False, uri


def validate_nxentry(nxentry, config=True, withpolicy=True, technique=None):
    """
    :param h5py.Group nxentry:
    :param bool config: configurable writer
    :param bool withpolicy: data policy
    :param str technique:
    """
    assert nxentry.parent.attrs["NX_class"] == "NXroot"
    assert nxentry.attrs["NX_class"] == "NXentry"
    expected = {"instrument", "measurement", "title", "start_time", "end_time"}
    plots = expected_plots(technique, config=config, withpolicy=withpolicy)
    _expected = set()
    for names in plots.values():
        _expected |= names
    if _expected:
        _expected |= {"plotselect"}
    expected |= _expected
    expected |= expected_applications(technique, config=config, withpolicy=withpolicy)
    assert_set_equal(set(nxentry.keys()), expected)


def validate_measurement(
    measurement,
    scan_shape=None,
    masters=None,
    config=True,
    technique=None,
    save_options=None,
):
    """
    :param h5py.Group nxentry:
    :param tuple scan_shape: fast axis first
    :param tuple masters: fast axis first
    :param bool config: configurable writer
    :param str technique:
    :param dict save_options:
    """
    assert measurement.attrs["NX_class"] == "NXcollection"
    # Detectors
    datasets = expected_channels(config=config, technique=technique)
    # Positioners
    if masters:
        datasets[0] |= set(masters)
    else:
        if save_options["multivalue_positioners"]:
            datasets[0] |= {"timer"}
        else:
            datasets[0] |= {"elapsed_time"}
    if save_options["multivalue_positioners"]:
        datasets[0] |= {"pos_timer", "pos_timer_epoch"}
    else:
        datasets[0] |= {"pos_elapsed_time", "pos_epoch"}
    # Check all datasets present
    expected = set()
    for names in datasets.values():
        expected |= names
    assert_set_equal(set(measurement.keys()), expected)
    # Validate data
    variable_length = not all(scan_shape)
    if scan_shape:
        if save_options["flat"]:
            scan_shape = (numpy.product(scan_shape, dtype=int),)
        else:
            # C-order: fast axis last
            scan_shape = scan_shape[::-1]
    else:
        scan_shape = tuple()
    for ndim, names in datasets.items():
        for name in names:
            dset = measurement[name]
            dshape = dset.shape
            eshape = scan_shape + (0,) * ndim
            eshape = tuple(s if s else ds for s, ds in zip(eshape, dshape))
            assert dshape == eshape, name
            scan_shape = eshape[: len(scan_shape)]
            assert_dataset(dset, ndim, save_options, variable_length=variable_length)


def validate_instrument(
    instrument,
    scan_shape=None,
    config=True,
    masters=None,
    withpolicy=True,
    technique=None,
    save_options=None,
):
    """
    :param h5py.Group nxentry:
    :param tuple scan_shape: fast axis first
    :param bool config: configurable writer
    :param tuple masters:
    :param bool withpolicy: data policy
    :param str technique:
    :param dict save_options:
    """
    # Positioner groups
    expected_posg = {"positioners", "positioners_start", "positioners_dial_start"}
    if config:
        expected_posg |= {"positioners_end", "positioners_dial_end"}
    # Detectors
    expected_dets = expected_detectors(config=config, technique=technique)
    # Positioners
    expected_pos = set(masters)
    if save_options["multivalue_positioners"]:
        expected_pos |= {"timer"}
    else:
        expected_pos |= {"elapsed_time", "epoch"}
    # Check all subgroups present
    if config:
        expected = {"title"}
    else:
        expected = set()
    expected |= expected_posg
    expected |= expected_dets
    expected |= expected_pos
    assert_set_equal(set(instrument.keys()), expected)
    # Validate content of positioner NXcollections
    for name in expected_posg:
        assert instrument[name].attrs["NX_class"] == "NXcollection", name
        expected = {"robx", "roby", "robz"}
        if name == "positioners":
            expected |= expected_pos
            if save_options["multivalue_positioners"]:
                expected |= {"timer_epoch"}
        assert_set_equal(set(instrument[name].keys()), expected)
    # Validate content of NXpositioner groups
    for name in expected_pos:
        assert instrument[name].attrs["NX_class"] == "NXpositioner", name
        if save_options["multivalue_positioners"] and name == "timer":
            expected = {"value", "epoch"}
        else:
            expected = {"value"}
        assert_set_equal(set(instrument[name].keys()), expected, msg=name)
    # Validate content of NXdetector groups
    variable_length = not all(scan_shape)
    for name in expected_dets:
        assert instrument[name].attrs["NX_class"] == "NXdetector", name
        expected = expected_detector_content(name, config=config)
        assert_set_equal(set(instrument[name].keys()), expected, msg=name)
        if "lima_simulator" in name:
            if not config and not name.endswith("image"):
                continue
            assert_dataset(instrument[name]["data"], 2, save_options, variable_length)


def validate_nxdata(
    nxdata, detector_ndim, ptype, scan_shape=None, masters=None, save_options=None
):
    """
    :param h5py.Group nxdata:
    :param int detector_ndim:
    :param str ptype:
    :param tuple scan_shape: fast axis first
    :param tuple masters: fast axis first
    :param dict save_options:
    """
    assert nxdata.attrs["NX_class"] == "NXdata", nxdata.name
    signals = nexus.nxDataGetSignals(nxdata)
    if ptype == "flat" and scan_shape:
        escan_shape = (numpy.product(scan_shape, dtype=int),)
    else:
        escan_shape = scan_shape
    if ptype == "grid":
        # C-order: fast axis last
        escan_shape = escan_shape[::-1]
        masters = masters[::-1]
    # Validate signal shape and interpretation
    # TODO: check expected signals
    scan_ndim = len(scan_shape)
    variable_length = not all(scan_shape)
    for name in signals:
        dset = nxdata[name]
        dscan_shape = dset.shape
        if dset.ndim and detector_ndim:
            dscan_shape = dscan_shape[: dset.ndim - detector_ndim]
        escan_shape = tuple(
            es if es else ds for es, ds in zip(escan_shape, dscan_shape)
        )
        assert dscan_shape == escan_shape, dset.name
        expected = nexus.nxDatasetInterpretation(scan_ndim, detector_ndim, dset.ndim)
        assert dset.attrs.get("interpretation", None) == expected, dset.name
        assert_dataset(
            dset, detector_ndim, save_options, variable_length=variable_length
        )
    # Validate axes
    if detector_ndim:
        if len(scan_shape) > 1 and ptype == "flat":
            # Scatter plot of non-scalar detector
            masters = tuple()
        else:
            masters += tuple("datadim{}".format(i) for i in range(detector_ndim))
    axes = tuple(nxdata.attrs.get("axes", tuple()))
    assert axes == masters, (axes, masters, scan_shape, ptype, nxdata.name)


def expected_plots(technique, config=True, withpolicy=True):
    """
    All expected plots for this technique (see nexus_definitions.yml)

    :param str technique:
    :param bool config: configurable writer
    :param bool withpolicy: data policy
    :returns dict: grouped by detector dimension and flat/grid
    """
    groups = dict()
    for n in range(3):
        for s in "grid", "flat":
            groups[(n, s)] = set()
    if config:
        if technique != "none":
            groups[(0, "flat")] |= {"all_counters"}
            groups[(0, "grid")] |= {"all_counters_grid"}
        if "xrf" in technique:
            groups[(0, "flat")] |= {"xrf_counters"}
            groups[(0, "grid")] |= {"xrf_counters_grid"}
        if "xas" in technique:
            groups[(0, "flat")] |= {"xas_counters"}
            groups[(0, "grid")] |= {"xas_counters_grid"}
        if "xrf" in technique or "xas" in technique:
            groups[(1, "flat")] |= {
                "all_spectra_samplingcounter",
                "all_spectra_mca",
                "xrf_spectra",
            }
            groups[(1, "grid")] |= {
                "all_spectra_grid_samplingcounter",
                "all_spectra_grid_mca",
                "xrf_spectra_grid",
            }
        elif technique != "none":
            groups[(1, "flat")] |= {"all_spectra"}
            groups[(1, "grid")] |= {"all_spectra_grid"}
        if "xrd" in technique:
            groups[(2, "flat")] |= {"all_images", "xrd_patterns"}
            groups[(2, "grid")] |= {"all_images_grid", "xrd_patterns_grid"}
    else:
        groups[(0, "flat")] |= {"plot0D"}
        if "xrf" in technique or "xas" in technique:
            groups[(1, "flat")] |= {"plot1D_unknown1D1", "plot1D_unknown1D2"}
        else:
            groups[(1, "flat")] |= {"plot1D_unknown1D"}
        if "xrd" in technique:
            groups[(2, "flat")] |= {"plot2D"}
    return groups


def expected_applications(technique, config=True, withpolicy=True):
    """
    All expected application definitions for this technique (see nexus_definitions.yml)

    :param str technique:
    :param bool config: configurable writer
    :param bool withpolicy: data policy
    :returns set:
    """
    apps = set()
    if config:
        if "xrf" in technique or "xas" in technique:
            apps |= {"xrf"}
    return apps


def expected_detectors(config=True, technique=None):
    """
    Expected detectors

    :param bool config: configurable writer
    :param str technique:
    :returns set:
    """
    if config:
        # Data channels are grouped per detector
        expected = {
            "diode3",
            "diode4",
            "diode5",
            "diode6",
            "diode7",
            "diode8",
            "sim_ct_gauss",
            "sim_ct_gauss_noise",
            "thermo_sample",
        }
        if config:
            expected |= {"diode2alias", "diode9alias"}
        else:
            expected |= {"diode2", "diode9"}
        if "xrf" in technique or "xas" in technique:
            expected |= {
                "simu1_det0",
                "simu1_det1",
                "simu1_det2",
                "simu1_det3",
                "simu1_sum",
                "simu2_det0",
                "simu2_det1",
                "simu2_det2",
                "simu2_det3",
                "simu2_sum",
            }
        if "xrd" in technique:
            expected |= {"lima_simulator", "lima_simulator2"}
    else:
        # Each data channel is a detector
        expected = set()
        channels = expected_channels(config=config, technique=technique)
        for names in channels.values():
            expected |= names
    return expected


def expected_detector_content(name, config=True):
    """
    :param bool config: configurable writer
    :returns set:
    """
    if config:
        if name.startswith("diode"):
            datasets = {"data", "mode", "type"}
            if name.startswith("diode9"):
                datasets |= {"samples"}
            elif name == "diode7":
                datasets |= {"N", "max", "min", "p2v", "std", "var"}
        elif name == "thermo_sample":
            datasets = {"data", "mode", "type"}
        elif name.startswith("simu"):
            datasets = {"type", "description", "roi1", "roi2", "roi3"}
            if "sum" not in name:
                datasets |= {
                    "data",
                    "dead_time",
                    "elapsed_time",
                    "input_counts",
                    "input_rate",
                    "live_time",
                    "output_counts",
                    "output_rate",
                }
        elif name.startswith("lima"):
            datasets = {
                "roi1_avg",
                "roi1_max",
                "roi1_min",
                "roi1_std",
                "roi1_sum",
                "roi2_avg",
                "roi2_max",
                "roi2_min",
                "roi2_std",
                "roi2_sum",
                "roi3_avg",
                "roi3_max",
                "roi3_min",
                "roi3_std",
                "roi3_sum",
                "roi4_avg",
                "roi4_max",
                "roi4_min",
                "roi4_std",
                "roi4_sum",
                "type",
                "data",
            }
        else:
            datasets = {"data"}
    else:
        datasets = {"data"}
    return datasets


def expected_channels(config=True, technique=None):
    """
    Expected channels, grouped per dimension

    :param bool config: configurable writer
    :param str technique:
    :returns dict:
    """
    datasets = {0: set(), 1: set(), 2: set()}
    # 1D counters
    datasets[0] |= {
        "diode3",
        "diode4",
        "diode5",
        "diode6",
        "diode7",
        "diode8",
        "sim_ct_gauss",
        "sim_ct_gauss_noise",
        "thermo_sample",
    }
    if config:
        datasets[0] |= {"diode2alias", "diode9alias"}
    else:
        datasets[0] |= {"diode2", "diode9"}
    for name in ["diode7"]:
        datasets[0] |= {
            name + "_N",
            name + "_min",
            name + "_max",
            name + "_p2v",
            name + "_std",
            name + "_var",
        }
    if config:
        lst = ["diode9alias"]
    else:
        lst = ["diode9"]
    for name in lst:
        datasets[1] |= {name + "_samples"}
    # MCA's with ROI's
    if "xrf" in technique or "xas" in technique:
        if config:
            for conname in ["simu1", "simu2"]:
                for detname in ["det0", "det1", "det2", "det3"]:
                    detname = conname + "_" + detname
                    datasets[1] |= {detname}
                    datasets[0] |= {
                        detname + "_input_counts",
                        detname + "_input_rate",
                        detname + "_output_counts",
                        detname + "_output_rate",
                        detname + "_dead_time",
                        detname + "_live_time",
                        detname + "_elapsed_time",
                        detname + "_roi1",
                        detname + "_roi2",
                        detname + "_roi3",
                    }
                detname = conname + "_sum"
                datasets[0] |= {detname + "_roi1", detname + "_roi2", detname + "_roi3"}
        else:
            for conname in ["simu1", "simu2"]:
                for detname in ["det0", "det1", "det2", "det3"]:
                    datasets[1] |= {conname + "_spectrum_" + detname}
                    datasets[0] |= {
                        conname + "_triggers_" + detname,
                        conname + "_icr_" + detname,
                        conname + "_events_" + detname,
                        conname + "_ocr_" + detname,
                        conname + "_deadtime_" + detname,
                        conname + "_livetime_" + detname,
                        conname + "_realtime_" + detname,
                        conname + "_roi1_" + detname,
                        conname + "_roi2_" + detname,
                        conname + "_roi3_" + detname,
                    }
                datasets[0] |= {conname + "_roi1", conname + "_roi2", conname + "_roi3"}
    # Lima's with ROI's
    if "xrd" in technique:
        if config:
            for conname in ["lima_simulator", "lima_simulator2"]:
                datasets[2] |= {conname}
                datasets[0] |= {
                    conname + "_roi1_min",
                    conname + "_roi1_max",
                    conname + "_roi1_sum",
                    conname + "_roi1_avg",
                    conname + "_roi1_std",
                    conname + "_roi2_min",
                    conname + "_roi2_max",
                    conname + "_roi2_sum",
                    conname + "_roi2_avg",
                    conname + "_roi2_std",
                    conname + "_roi3_min",
                    conname + "_roi3_max",
                    conname + "_roi3_sum",
                    conname + "_roi3_avg",
                    conname + "_roi3_std",
                    conname + "_roi4_min",
                    conname + "_roi4_max",
                    conname + "_roi4_sum",
                    conname + "_roi4_avg",
                    conname + "_roi4_std",
                }
        else:
            for conname in ["lima_simulator", "lima_simulator2"]:
                datasets[2] |= {conname + "_image"}
                datasets[0] |= {
                    conname + "_roi_counters_roi1_min",
                    conname + "_roi_counters_roi1_max",
                    conname + "_roi_counters_roi1_sum",
                    conname + "_roi_counters_roi1_avg",
                    conname + "_roi_counters_roi1_std",
                    conname + "_roi_counters_roi2_min",
                    conname + "_roi_counters_roi2_max",
                    conname + "_roi_counters_roi2_sum",
                    conname + "_roi_counters_roi2_avg",
                    conname + "_roi_counters_roi2_std",
                    conname + "_roi_counters_roi3_min",
                    conname + "_roi_counters_roi3_max",
                    conname + "_roi_counters_roi3_sum",
                    conname + "_roi_counters_roi3_avg",
                    conname + "_roi_counters_roi3_std",
                    conname + "_roi_counters_roi4_min",
                    conname + "_roi_counters_roi4_max",
                    conname + "_roi_counters_roi4_sum",
                    conname + "_roi_counters_roi4_avg",
                    conname + "_roi_counters_roi4_std",
                }
    return datasets


def assert_set_equal(actual, expected, msg=""):
    """
    Assert equal sets with message

    :param set actual:
    :param set expected:
    :param str msg:
    """
    diff = actual.difference(expected)
    if diff:
        msg += "\nnot expected: " + repr(sorted(diff))
    diff = expected.difference(actual)
    if diff:
        msg += "\nnot present: " + repr(sorted(diff))
    assert actual == expected, msg


def assert_dataset(dset, detector_ndim, save_options, variable_length=False):
    """
    Check whether dataset contains the expected data

    :param h5py.Dataset dset:
    :param int detector_ndim:
    :param dict save_options:
    :param bool variable_length:
    """
    detaxis = tuple(range(-detector_ndim, 0))
    if "lima_simulator" in dset.name and detector_ndim == 2:
        # Check external data (VDS or raw external)
        if dset.parent.attrs.get("NX_class", "") == "NXdetector":
            if "lima_simulator2" in dset.name:
                isexternal = bool(dset.external)
                if save_options["allow_external_nonhdf5"]:
                    assert isexternal, dset.name
                else:
                    assert not isexternal, dset.name
            else:
                try:
                    isexternal = bool(dset.virtual_sources())
                except RuntimeError:
                    isexternal = False
                if save_options["allow_external_hdf5"]:
                    assert isexternal, dset.name
                else:
                    assert not isexternal, dset.name
        # Check image maxima: 100, 200, ...
        if variable_length:
            return
        data = dset[()].max(axis=detaxis).flatten(order="C")
        npoints = numpy.product(dset.shape[:-2], dtype=int)
        edata = numpy.arange(1, npoints + 1) * 100
        numpy.testing.assert_array_equal(data, edata, err_msg=dset.name)
    else:
        if variable_length:
            return
        try:
            numpy.array(numpy.nan, dset.dtype)
        except ValueError:
            return  # TODO: figure out how to mark missing data
            invalid = dset[()] == 0
        else:
            invalid = numpy.isnan(dset[()])
        # At least one valid value along the detector dimensions
        invalid = invalid.min(axis=detaxis)
        assert not invalid.all(), dset.name
