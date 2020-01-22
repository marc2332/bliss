# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import re
import numpy
from nexus_writer_service.utils import scan_utils
from nexus_writer_service.io import nexus
from nexus_writer_service.subscribers.scan_writer_base import (
    default_saveoptions as base_options
)
from nexus_writer_service.subscribers.scan_writer_config import (
    default_saveoptions as config_options
)
import nxw_test_config
import nxw_test_utils


def assert_scan_data(scan, **kwargs):
    """
    :param bliss.scanning.scan.Scan scan:
    :param kwargs: see `validate_scan_data`
    """
    # scan_utils.open_data(scan, subscan=subscan, config=config, block=True)
    validate_scan_data(scan, **kwargs)


def assert_scangroup_data(sequence, **kwargs):
    """
    :param bliss.scanning.group.Sequence sequence:
    :param kwargs: see `validate_scangroup_data`
    """
    # scan_utils.open_data(sequence.scan, subscan=subscan, config=config, block=True)
    validate_scangroup_data(sequence, **kwargs)


def validate_scan_data(
    scan,
    subscan=1,
    masters=None,
    detectors=None,
    master_name="timer",
    scan_shape=None,
    config=True,
    withpolicy=True,
    alt=False,
):
    """
    :param bliss.scanning.scan.Scan scan:
    :param int subscan:
    :param tuple masters: fast axis first by default `master_name` when 1D scan
                          or None otherwise
    :param list(str) detectors: expected detectors (derived from technique when missing)
    :param str master_name: chain master name
    :param tuple scan_shape: fast axis first 0D scan by default
    :param bool config: configurable writer
    :param bool withpolicy: data policy
    :param bool alt: alternative writer options
    """
    # Parse arguments
    if config:
        save_options = config_options()
    else:
        save_options = base_options()
    if alt:
        save_options = {k: not v for k, v in save_options.items()}
    if scan_shape is None:
        scan_shape = tuple()
    variable_length = not all(scan_shape)
    if masters is None:
        if not scan_shape:
            masters = tuple()
        elif len(scan_shape) == 1:
            if save_options["multivalue_positioners"]:
                masters = (master_name,)
            else:
                masters = ("elapsed_time",)
    assert len(scan_shape) == len(masters)
    if withpolicy:
        det_technique = nxw_test_config.technique["withpolicy"]
    else:
        det_technique = nxw_test_config.technique["withoutpolicy"]
    if detectors is not None:
        det_technique = "none"
    if detectors:
        for name, alias in zip(["diode2", "diode9"], ["diode2alias", "diode9alias"]):
            if config:
                detectors = [alias if d == name else d for d in detectors]
            else:
                detectors = [name if d == alias else d for d in detectors]
    if config:
        scan_technique = scan.scan_info["nexuswriter"]["technique"]["name"]
    else:
        scan_technique = det_technique
    # Validate NXentry links
    validate_master_links(scan, config=config)
    # Validate NXentry content
    uri = scan_utils.scan_uri(scan, subscan=subscan, config=config)
    with nexus.uriContext(uri) as nxentry:
        validate_nxentry(
            nxentry,
            config=config,
            withpolicy=withpolicy,
            technique=scan_technique,
            detectors=detectors,
            variable_length=variable_length,
        )
        validate_measurement(
            nxentry["measurement"],
            scan_shape=scan_shape,
            config=config,
            masters=masters,
            technique=det_technique,
            save_options=save_options,
            detectors=detectors,
            master_name=master_name,
        )
        validate_instrument(
            nxentry["instrument"],
            scan_shape=scan_shape,
            config=config,
            masters=masters,
            withpolicy=withpolicy,
            technique=det_technique,
            save_options=save_options,
            detectors=detectors,
            master_name=master_name,
        )
        if not variable_length:
            validate_plots(
                nxentry,
                config=config,
                withpolicy=withpolicy,
                technique=scan_technique,
                detectors=detectors,
                scan_shape=scan_shape,
                masters=masters,
                save_options=save_options,
            )
        validate_applications(
            nxentry,
            technique=scan_technique,
            config=config,
            withpolicy=withpolicy,
            save_options=save_options,
            detectors=detectors,
        )


def validate_scangroup_data(sequence, config=True, **kwargs):
    """
    :param bliss.scanning.scan.Scan sequence:
    :param bool config: configurable writer
    """
    # Validate NXentry links
    validate_master_links(sequence.scan, config=config)
    # Validate scan links (currently disabled)
    # validate_scangroup_links(sequence, config=config)
    # Validate NXentry content
    uri = scan_utils.scan_uri(sequence.scan, config=config)
    with nexus.uriContext(uri) as nxentry:
        # TODO: validate scan group NXentry (custom channels)
        pass


def validate_master_links(scan, subscan=1, config=True):
    """
    Check whether all files contain the scan entry.

    :param bliss.scanning.scan.Scan scan:
    :param bool config: configurable writer
    """
    uri = scan_utils.scan_uri(scan, subscan=subscan, config=config)
    uri = nexus.normUri(uri)
    for filename in scan_utils.scan_filenames(scan, config=config):
        with nexus.File(filename) as nxroot:
            for key in nxroot:
                if uri == nexus.normUri(nexus.getUri(nxroot[key])):
                    break
            else:
                assert False, uri


def validate_scangroup_links(sequence, config=True):
    """
    :param bliss.scanning.scan.Scan sequence:
    :param bool config: configurable writer
    """
    expected = []
    for scan in sequence._scans:
        expected += scan_utils.scan_uris(scan, config=config)
    uri = scan_utils.scan_uri(sequence.scan, config=config)
    actual = []
    with nexus.uriContext(uri) as nxentry:
        root = nxentry["dependencies"]
        for k in root:
            actual.append(nexus.normUri(nexus.dereference(root[k])))
    assert_set_equal(set(actual), set(expected))


def validate_nxentry(
    nxentry,
    config=True,
    withpolicy=True,
    technique=None,
    detectors=None,
    variable_length=None,
):
    """
    :param h5py.Group nxentry:
    :param bool config: configurable writer
    :param bool withpolicy: data policy
    :param str technique:
    :param list(str) detectors:
    :param bool variable_length: e.g. timescan
    """
    assert nxentry.parent.attrs["NX_class"] == "NXroot"
    assert nxentry.attrs["NX_class"] == "NXentry"
    actual = set(nxentry.keys())
    expected = {"instrument", "measurement", "title", "start_time", "end_time"}
    if variable_length:
        for name in list(actual):
            if nxentry[name].attrs.get("NX_class") == "NXdata":
                actual.remove(name)
    else:
        plots = expected_plots(
            technique, config=config, withpolicy=withpolicy, detectors=detectors
        )
        for name, info in plots.items():
            if info["signals"]:
                expected |= {name, "plotselect"}
    expected |= expected_applications(technique, config=config, withpolicy=withpolicy)
    assert_set_equal(actual, expected)


def validate_measurement(
    measurement,
    scan_shape=None,
    masters=None,
    config=True,
    technique=None,
    save_options=None,
    detectors=None,
    master_name=None,
):
    """
    :param h5py.Group nxentry:
    :param tuple scan_shape: fast axis first
    :param tuple masters: fast axis first
    :param bool config: configurable writer
    :param str technique:
    :param dict save_options:
    :param list(str) detectors:
    :param str master_name:
    """
    assert measurement.attrs["NX_class"] == "NXcollection"
    # Detectors
    datasets = expected_channels(
        config=config, technique=technique, detectors=detectors
    )
    # Positioners
    if masters:
        datasets[0] |= set(masters)
    else:
        if save_options["multivalue_positioners"]:
            datasets[0] |= {master_name}
        else:
            datasets[0] |= {"elapsed_time"}
    if save_options["multivalue_positioners"]:
        datasets[0] |= {
            "pos_{}".format(master_name),
            "pos_{}_epoch".format(master_name),
        }
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
            if not variable_length:
                # TODO: timescans will have variable length data channels
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
    detectors=None,
    master_name=None,
):
    """
    :param h5py.Group nxentry:
    :param tuple scan_shape: fast axis first
    :param bool config: configurable writer
    :param tuple masters:
    :param bool withpolicy: data policy
    :param str technique:
    :param dict save_options:
    :param list(str) detectors:
    :param str master_name:
    """
    # Positioner groups
    expected_posg = {
        "positioners",
        "positioners_start",
        "positioners_dial_start",
        "positioners_end",
        "positioners_dial_end",
    }
    # Detectors
    expected_dets = expected_detectors(
        config=config, technique=technique, detectors=detectors
    )
    # Positioners
    expected_pos = set(masters)
    if save_options["multivalue_positioners"]:
        expected_pos |= {master_name}
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
                expected |= {"{}_epoch".format(master_name)}
        assert_set_equal(set(instrument[name].keys()), expected)
    # Validate content of NXpositioner groups
    for name in expected_pos:
        assert instrument[name].attrs["NX_class"] == "NXpositioner", name
        if save_options["multivalue_positioners"] and name == master_name:
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
        if config:
            islima_image = name in ["lima_simulator", "lima_simulator2"]
        else:
            islima_image = name in ["lima_simulator_image", "lima_simulator2_image"]
        if islima_image:
            assert_dataset(instrument[name]["data"], 2, save_options, variable_length)


def validate_plots(
    nxentry,
    config=True,
    withpolicy=True,
    technique=None,
    detectors=None,
    scan_shape=None,
    masters=None,
    save_options=None,
):
    """
    :param h5py.Group nxentry:
    :param bool config: configurable writer
    :param bool withpolicy: data policy
    :param str technique:
    :param list(str) detectors:
    :param tuple scan_shape: fast axis first
    :param tuple masters: fast axis first
    :param dict save_options:
    """
    plots = expected_plots(
        technique, config=config, withpolicy=withpolicy, detectors=detectors
    )
    for name, info in plots.items():
        if info["signals"]:
            validate_nxdata(
                nxentry[name],
                info["ndim"],
                info["type"],
                info["signals"],
                scan_shape=scan_shape,
                masters=masters,
                save_options=save_options,
            )
        else:
            assert name not in nxentry, name


def validate_applications(
    nxentry,
    technique=None,
    config=True,
    withpolicy=True,
    save_options=None,
    detectors=None,
):
    """
    All application definitions for this technique (see nexus_definitions.yml)

    :param h5py.Group nxentry:
    :param str technique:
    :param bool config: configurable writer
    :param bool withpolicy: data policy
    :param dict save_options:
    :param list detectors:
    """
    names = expected_applications(technique, config=config, withpolicy=withpolicy)
    for name in names:
        nxsubentry = nxentry[name]
        if name == "xrf":
            validate_appxrf(nxsubentry, save_options=save_options, detectors=detectors)


def validate_appxrf(nxsubentry, save_options=None, detectors=None):
    """
    XRF application defintion (see nexus_definitions.yml)

    :param h5py.Group nxsubentry:
    :param dict save_options:
    :param list detectors:
    """
    # Application definition complete?
    expected = {"definition", "end_time", "start_time"}
    if detectors:
        if "diode2" in detectors or "diode2alias" in detectors:
            expected.add("i0")
        if "diode3" in detectors:
            expected.add("it")
        mcas = []
        if "simu1" in detectors:
            mcas.append(0)
        if "simu2" in detectors:
            mcas.append(1)
    else:
        expected |= {"i0", "it"}
        mcas = [0, 1]
    if save_options["stack_mcas"]:
        expected |= {"mca", "elapsed_time", "live_time"}
    else:
        for i in mcas:
            expected |= {
                "mca{:02d}".format(i),
                "elapsed_time_mca{:02d}".format(i),
                "live_time_mca{:02d}".format(i),
            }
    assert_set_equal(set(nxsubentry.keys()), expected, msg=nxsubentry.name)

    # Validate content
    definition = nxsubentry["definition"][()]
    assert definition == "APPxrf"
    if save_options["stack_mcas"] and len(mcas) > 1:
        dset = nxsubentry["mca"]
        assert dset.shape[0] == len(mcas), dset.name
        assert dset.is_virtual, dset.name


def validate_nxdata(
    nxdata,
    detector_ndim,
    ptype,
    expected_signals,
    scan_shape=None,
    masters=None,
    save_options=None,
):
    """
    :param h5py.Group nxdata:
    :param int detector_ndim:
    :param str ptype:
    :param list expected_signals:
    :param tuple scan_shape: fast axis first
    :param tuple masters: fast axis first
    :param dict save_options:
    """
    assert nxdata.attrs["NX_class"] == "NXdata", nxdata.name
    signals = nexus.nxDataGetSignals(nxdata)
    assert_set_equal(set(signals), set(expected_signals), msg=nxdata.name)
    if ptype == "flat" and scan_shape:
        escan_shape = (numpy.product(scan_shape, dtype=int),)
    else:
        escan_shape = scan_shape
    if ptype == "grid":
        # C-order: fast axis last
        escan_shape = escan_shape[::-1]
        masters = masters[::-1]
    # Validate signal shape and interpretation
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


def expected_plots(technique, config=True, withpolicy=True, detectors=None):
    """
    All expected plots for this technique (see nexus_definitions.yml)

    :param str technique:
    :param bool config: configurable writer
    :param bool withpolicy: data policy
    :param list(str) detectors:
    :returns dict: grouped by detector dimension and flat/grid
    """
    plots = dict()
    channels = expected_channels(
        config=config, technique=technique, detectors=detectors
    )

    def ismca(name):
        return "simu" in name or "spectrum" in name

    mca_signals = [name for name in channels[1] if ismca(name)]
    non_mca_signals = [name for name in channels[1] if not ismca(name)]
    single1Dtype = bool(mca_signals) ^ bool(non_mca_signals)
    if config:
        if technique != "none":
            # All 0D detectors
            plots["all_counters"] = {"ndim": 0, "type": "flat", "signals": channels[0]}
            plots["all_counters_grid"] = {
                "ndim": 0,
                "type": "grid",
                "signals": channels[0],
            }
            # All 1D detectors
            if single1Dtype:
                signals = {f"simu{i}_det{j}" for i in range(1, 3) for j in range(4)}
                signals |= {"diode9alias_samples"}
                signals &= channels[1]
                plots["all_spectra"] = {"ndim": 1, "type": "flat", "signals": signals}
                plots["all_spectra_grid"] = {
                    "ndim": 1,
                    "type": "grid",
                    "signals": signals,
                }
            else:
                signals = {"diode9alias_samples"}
                signals &= channels[1]
                plots["all_spectra_samplingcounter"] = {
                    "ndim": 1,
                    "type": "flat",
                    "signals": signals,
                }
                plots["all_spectra_grid_samplingcounter"] = {
                    "ndim": 1,
                    "type": "grid",
                    "signals": signals,
                }
                signals = {f"simu{i}_det{j}" for i in range(1, 3) for j in range(4)}
                signals &= channels[1]
                plots["all_spectra_mca"] = {
                    "ndim": 1,
                    "type": "flat",
                    "signals": signals,
                }
                plots["all_spectra_grid_mca"] = {
                    "ndim": 1,
                    "type": "grid",
                    "signals": signals,
                }
            # All 2D detectors
            plots["all_images"] = {"ndim": 2, "type": "flat", "signals": channels[2]}
            plots["all_images_grid"] = {
                "ndim": 2,
                "type": "grid",
                "signals": channels[2],
            }
        # Plots with specific signals (see nexus_definitions.yml)
        if "xrf" in technique:
            signals = {
                "diode2alias",
                "diode3",
                "simu1_det0_dead_time",
                "simu2_det1_dead_time",
            }
            signals &= channels[0]
            plots["xrf_counters"] = {"ndim": 0, "type": "flat", "signals": signals}
            plots["xrf_counters_grid"] = {"ndim": 0, "type": "grid", "signals": signals}
        if "xas" in technique:
            signals = {
                "diode4",
                "diode5",
                "simu1_det0_dead_time",
                "simu2_det1_dead_time",
            }
            signals &= channels[1]
            plots["xas_counters"] = {"ndim": 0, "type": "flat", "signals": signals}
            plots["xas_counters_grid"] = {"ndim": 0, "type": "grid", "signals": signals}
        if "xrf" in technique or "xas" in technique:
            signals = {"simu1_det0", "simu2_det1"}
            signals &= channels[1]
            plots["xrf_spectra"] = {"ndim": 1, "type": "flat", "signals": signals}
            plots["xrf_spectra_grid"] = {"ndim": 1, "type": "grid", "signals": signals}
        if "xrd" in technique:
            signals = {"lima_simulator"}
            signals &= channels[2]
            plots["xrd_patterns"] = {"ndim": 2, "type": "flat", "signals": signals}
            plots["xrd_patterns_grid"] = {"ndim": 2, "type": "grid", "signals": signals}
    else:
        # All 0D detectors
        plots["plot0D"] = {"ndim": 0, "type": "flat", "signals": channels[0]}
        # All 1D detectors
        if single1Dtype:
            plots["plot1D"] = {"ndim": 1, "type": "flat", "signals": channels[1]}
        else:
            plots["plot1D_unknown1D1"] = {
                "ndim": 1,
                "type": "flat",
                "signals": non_mca_signals,
            }
            plots["plot1D_unknown1D2"] = {
                "ndim": 1,
                "type": "flat",
                "signals": mca_signals,
            }
        # All 2D detectors
        plots["plot2D"] = {"ndim": 2, "type": "flat", "signals": channels[2]}
    return plots


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


def expected_detectors(config=True, technique=None, detectors=None):
    """
    Expected detectors

    :param bool config: configurable writer
    :param str technique:
    :param list(str) detectors:
    :returns set:
    """
    if detectors:
        detectors = set(detectors)
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
        if detectors:
            expected &= detectors
        if "xrf" in technique or "xas" in technique or detectors:
            names = {"simu1", "simu2"}
            if detectors:
                names &= detectors
            for name in names:
                expected |= {
                    name + "_det0",
                    name + "_det1",
                    name + "_det2",
                    name + "_det3",
                    name + "_sum",
                }
        if "xrd" in technique or detectors:
            names = {"lima_simulator", "lima_simulator2"}
            if detectors:
                names &= detectors
            for name in names:
                expected |= {
                    name,
                    name + "_roi1",
                    name + "_roi2",
                    name + "_roi3",
                    name + "_roi4",
                    name + "_bpm",
                }
    else:
        # Each data channel is a detector
        expected = set()
        channels = expected_channels(
            config=config, technique=technique, detectors=detectors
        )
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
            datasets = {"type", "roi1", "roi2", "roi3"}
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
            if "roi" in name:
                datasets = {"data", "type", "avg", "min", "max", "std", "selection"}
            elif "bpm" in name:
                datasets = {
                    "type",
                    "x",
                    "y",
                    "fwhm_x",
                    "fwhm_y",
                    "intensity",
                    "acq_time",
                }
            else:
                datasets = {"type", "data", "acq_parameters", "ctrl_parameters"}
        else:
            datasets = {"data"}
    else:
        if name.startswith("lima"):
            if "roi" in name:
                datasets = {"data", "roi1", "roi2", "roi3", "roi4"}
            elif "bpm" in name:
                datasets = {"data"}
            else:
                datasets = {"data", "acq_parameters", "ctrl_parameters"}
        elif name == "image":
            datasets = {"data", "acq_parameters", "ctrl_parameters"}
        elif re.match("roi[0-9]_(sum|avg|std|min|max)", name):
            datasets = {"data", "roi1", "roi2", "roi3", "roi4"}
        else:
            datasets = {"data"}
    return datasets


def expected_channels(config=True, technique=None, detectors=None):
    """
    Expected channels grouped per dimension

    :param bool config: configurable writer
    :param str technique:
    :param list(str) detectors:
    :returns dict: key are the unique names (used in plots and measurement)
    """
    if detectors:
        detectors = set(detectors)
    datasets = {0: set(), 1: set(), 2: set()}
    # Normal diodes
    names = {
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
        names |= {"diode2alias", "diode9alias"}
    else:
        names |= {"diode2", "diode9"}
    if detectors:
        names &= detectors
    datasets[0] |= names
    # Statistics diodes
    names = {"diode7"}
    if detectors:
        names &= detectors
    for name in names:
        datasets[0] |= {
            name + "_N",
            name + "_min",
            name + "_max",
            name + "_p2v",
            name + "_std",
            name + "_var",
        }
    # Statistics diodes
    if config:
        names = {"diode9alias"}
    else:
        names = {"diode9"}
    if detectors:
        names &= detectors
    for name in names:
        datasets[1] |= {name + "_samples"}
    # MCA's with ROI's
    if "xrf" in technique or "xas" in technique or detectors:
        names = {"simu1", "simu2"}
        if detectors:
            names &= detectors
        if config:
            for conname in names:
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
            for conname in names:
                for detname in ["det0", "det1", "det2", "det3"]:
                    if len(names) > 1:
                        prefix = conname + "_"
                    else:
                        prefix = ""
                    datasets[1] |= {prefix + "spectrum_" + detname}
                    datasets[0] |= {
                        prefix + "triggers_" + detname,
                        prefix + "icr_" + detname,
                        prefix + "events_" + detname,
                        prefix + "ocr_" + detname,
                        prefix + "deadtime_" + detname,
                        prefix + "livetime_" + detname,
                        prefix + "realtime_" + detname,
                        prefix + "roi1_" + detname,
                        prefix + "roi2_" + detname,
                        prefix + "roi3_" + detname,
                    }
                datasets[0] |= {prefix + "roi1", prefix + "roi2", prefix + "roi3"}
    # Lima's with ROI's and BPM
    if "xrd" in technique or detectors:
        names = {"lima_simulator", "lima_simulator2"}
        if detectors:
            names &= detectors
        if config:
            for conname in names:
                datasets[2] |= {conname}
                datasets[0] |= {
                    conname + "_roi1_min",
                    conname + "_roi1_max",
                    conname + "_roi1",
                    conname + "_roi1_avg",
                    conname + "_roi1_std",
                    conname + "_roi2_min",
                    conname + "_roi2_max",
                    conname + "_roi2",
                    conname + "_roi2_avg",
                    conname + "_roi2_std",
                    conname + "_roi3_min",
                    conname + "_roi3_max",
                    conname + "_roi3",
                    conname + "_roi3_avg",
                    conname + "_roi3_std",
                    conname + "_roi4_min",
                    conname + "_roi4_max",
                    conname + "_roi4",
                    conname + "_roi4_avg",
                    conname + "_roi4_std",
                    conname + "_bpm_x",
                    conname + "_bpm_y",
                    conname + "_bpm_fwhm_x",
                    conname + "_bpm_fwhm_y",
                    conname + "_bpm_intensity",
                    conname + "_bpm_acq_time",
                }
        else:
            for conname in names:
                if len(names) > 1:
                    prefix = conname + "_"
                    prefix_roi = conname + "_roi_counters_"
                    prefix_bpm = conname + "_bpm_"
                else:
                    prefix = ""
                    prefix_roi = ""
                    prefix_bpm = ""
                datasets[2] |= {prefix + "image"}
                datasets[0] |= {
                    prefix_roi + "roi1_min",
                    prefix_roi + "roi1_max",
                    prefix_roi + "roi1_sum",
                    prefix_roi + "roi1_avg",
                    prefix_roi + "roi1_std",
                    prefix_roi + "roi2_min",
                    prefix_roi + "roi2_max",
                    prefix_roi + "roi2_sum",
                    prefix_roi + "roi2_avg",
                    prefix_roi + "roi2_std",
                    prefix_roi + "roi3_min",
                    prefix_roi + "roi3_max",
                    prefix_roi + "roi3_sum",
                    prefix_roi + "roi3_avg",
                    prefix_roi + "roi3_std",
                    prefix_roi + "roi4_min",
                    prefix_roi + "roi4_max",
                    prefix_roi + "roi4_sum",
                    prefix_roi + "roi4_avg",
                    prefix_roi + "roi4_std",
                    prefix_bpm + "x",
                    prefix_bpm + "y",
                    prefix_bpm + "fwhm_x",
                    prefix_bpm + "fwhm_y",
                    prefix_bpm + "intensity",
                    prefix_bpm + "acq_time",
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
                    isexternal = dset.is_virtual
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


def validate_detector_data_npoints(scan, subscan=1, npoints=None):
    """
    :param bliss.scanning.scan.Scan scan:
    :param int subscan:
    :param int npoints:
    """
    uri = scan_utils.scan_uri(scan, subscan=subscan, config=True)
    with nexus.uriContext(uri) as nxentry:
        instrument = nxentry["instrument"]
        for name in instrument:
            detector = instrument[name]
            if nexus.isNxClass(detector, "NXdetector"):
                dset = instrument[detector]["data"]
                assert dset.shape[0] == npoints, dset.name
