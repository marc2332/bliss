# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import re
import numpy
from silx.io import dictdump
from nexus_writer_service.utils import scan_utils
from nexus_writer_service.io import nexus
from nexus_writer_service.subscribers.scan_writer_base import (
    default_saveoptions as base_options
)
from nexus_writer_service.subscribers.scan_writer_config import (
    default_saveoptions as config_options
)
from . import nxw_test_config


def assert_scan_data(scan, **kwargs):
    """
    :param bliss.scanning.scan.Scan scan:
    :param kwargs: see `validate_scan_data`
    """
    # scan_utils.open_data(scan, subscan=subscan, block=True)
    validate_scan_data(scan, **kwargs)


def assert_scangroup_data(sequence, **kwargs):
    """
    :param bliss.scanning.group.Sequence sequence:
    :param kwargs: see `validate_scangroup_data`
    """
    # scan_utils.open_data(sequence.scan, subscan=subscan, block=True)
    validate_scangroup_data(sequence, **kwargs)


def validate_scan_data(
    scan,
    subscan=1,
    positioners=None,
    detectors=None,
    notes=None,
    master_name="timer",
    scan_shape=tuple(),
    config=True,
    policy=True,
    alt=False,
    softtimer="master",
    save_images=True,
    **kw,
):
    """
    :param bliss.scanning.scan.Scan scan:
    :param int subscan:
    :param list(list(str)) positioners: fast axis first
    :param list(str) detectors: expected detectors (derived from technique when missing)
    :param list(str) notes:
    :param str master_name: chain master name
    :param tuple scan_shape: fast axis first 0D scan by default
    :param bool config: configurable writer
    :param bool policy: data policy
    :param bool alt: alternative writer options
    :param str softtimer: "detector", "master" or neither
    :param bool save_images: save lima images
    """
    # Parse arguments
    save_options = get_save_options(config=config, alt=alt)
    variable_length = not all(scan_shape)
    if not positioners:
        positioners = []
    if policy:
        det_technique = nxw_test_config.technique["withpolicy"]
    else:
        det_technique = nxw_test_config.technique["withoutpolicy"]
    if detectors is not None:
        det_technique = "none"
    if config:
        scan_technique = scan.scan_info["nexuswriter"]["technique"]["name"]
    else:
        scan_technique = det_technique
    # Validate NXentry links
    validate_master_links(scan, config=config)
    # Validate NXentry content
    uri = scan_utils.scan_uri(scan, subscan=subscan)
    with nexus.uriContext(uri) as nxentry:
        validate_nxentry(
            nxentry,
            config=config,
            policy=policy,
            technique=scan_technique,
            detectors=detectors,
            notes=notes,
            variable_length=variable_length,
            master_name=master_name,
            softtimer=softtimer,
            save_images=save_images,
        )
        validate_measurement(
            nxentry["measurement"],
            scan_shape=scan_shape,
            config=config,
            positioners=positioners,
            technique=det_technique,
            save_options=save_options,
            detectors=detectors,
            master_name=master_name,
            softtimer=softtimer,
            save_images=save_images,
        )
        validate_instrument(
            nxentry["instrument"],
            scan_shape=scan_shape,
            config=config,
            positioners=positioners,
            policy=policy,
            technique=det_technique,
            save_options=save_options,
            detectors=detectors,
            master_name=master_name,
            softtimer=softtimer,
            save_images=save_images,
        )
        if not variable_length:
            validate_plots(
                nxentry,
                config=config,
                policy=policy,
                technique=scan_technique,
                detectors=detectors,
                scan_shape=scan_shape,
                positioners=positioners,
                master_name=master_name,
                softtimer=softtimer,
                save_options=save_options,
                save_images=save_images,
            )
        validate_applications(
            nxentry,
            technique=scan_technique,
            config=config,
            policy=policy,
            save_options=save_options,
            detectors=detectors,
        )
        validate_notes(nxentry, notes)


def assert_scan_nxdata(
    scan,
    plots,
    subscan=1,
    positioners=None,
    master_name="timer",
    scan_shape=tuple(),
    config=True,
    alt=False,
    save_images=True,
    **kw,
):
    """
    :param bliss.scanning.scan.Scan scan:
    :param dict plots:
    :param int subscan:
    :param list(list(str)) positioners: fast axis first
    :param str master_name: chain master name
    :param tuple scan_shape: fast axis first 0D scan by default
    :param bool config: configurable writer
    :param bool alt: alternative writer options
    :param bool save_images: save lima images
    """
    save_options = get_save_options(config=config, alt=alt)
    if not positioners:
        positioners = []
    uri = scan_utils.scan_uri(scan, subscan=subscan)
    with nexus.uriContext(uri) as nxentry:
        for name, info in plots.items():
            validate_nxdata(
                nxentry[name],
                info["ndim"],
                info["type"],
                info["signals"],
                scan_shape=scan_shape,
                positioners=positioners,
                master_name=master_name,
                save_options=save_options,
            )


def get_save_options(config=True, alt=False):
    """
    :param bool config: configurable writer
    :param bool alt: alternative writer options
    """
    if config:
        save_options = config_options()
    else:
        save_options = base_options()
    if alt:
        save_options = {k: not v for k, v in save_options.items()}
    # Forced in confdtest.py::writer_options
    save_options["copy_non_external"] = True
    save_options["allow_external_hdf5"] = True
    return save_options


def validate_scangroup_data(sequence, config=True, **kwargs):
    """
    :param bliss.scanning.scan.Scan sequence:
    :param bool config: configurable writer
    """
    # Validate NXentry links
    validate_master_links(sequence.scan, config=config)
    # Validate scan links (currently disabled)
    # validate_scangroup_links(sequence)
    # Validate NXentry content
    uri = scan_utils.scan_uri(sequence.scan)
    with nexus.uriContext(uri) as nxentry:
        # TODO: validate scan group NXentry (custom channels)
        pass


def validate_master_links(scan, subscan=1, config=True):
    """
    Check whether all files contain the scan entry.

    :param bliss.scanning.scan.Scan scan:
    :param bool config: configurable writer
    """
    uri = scan_utils.scan_uri(scan, subscan=subscan)
    uri = nexus.normUri(uri)
    if config:
        for filename in scan_utils.scan_filenames(scan, config=config).values():
            with nexus.File(filename) as nxroot:
                for key in nxroot:
                    if uri == nexus.normUri(nexus.getUri(nxroot[key])):
                        break
                else:
                    assert False, uri
    else:
        for filename in scan_utils.scan_master_filenames(scan, config=True).values():
            assert not os.path.exists(filename), filename


def validate_scangroup_links(sequence):
    """
    :param bliss.scanning.scan.Scan sequence:
    """
    expected = []
    for scan in sequence._scans:
        expected += scan_utils.scan_uris(scan)
    uri = scan_utils.scan_uri(sequence.scan)
    actual = []
    with nexus.uriContext(uri) as nxentry:
        root = nxentry["dependencies"]
        for k in root:
            actual.append(nexus.normUri(nexus.dereference(root, k)))
    assert_set_equal(set(actual), set(expected))


def validate_nxentry(
    nxentry,
    config=True,
    policy=True,
    technique=None,
    detectors=None,
    notes=None,
    variable_length=None,
    master_name=None,
    softtimer=None,
    save_images=True,
):
    """
    :param h5py.Group nxentry:
    :param bool config: configurable writer
    :param bool policy: data policy
    :param str technique:
    :param list(str) detectors:
    :param bool notes:
    :param bool variable_length: e.g. timescan
    :param str master_name:
    :param str softtimer:
    :param bool save_images:
    """
    assert nxentry.parent.attrs["NX_class"] == "NXroot"
    assert nxentry.attrs["NX_class"] == "NXentry"
    actual = set(nxentry.keys())
    expected = {"instrument", "measurement", "title", "start_time", "end_time"}
    if variable_length:
        # Multiple plots based on
        for name in list(actual):
            if nxentry[name].attrs.get("NX_class") == "NXdata":
                actual.remove(name)
    else:
        plots = expected_plots(
            technique,
            config=config,
            policy=policy,
            detectors=detectors,
            master_name=master_name,
            softtimer=softtimer,
            save_images=save_images,
        )
        for name, info in plots.items():
            if info["signals"]:
                expected |= {name, "plotselect"}
    expected |= expected_applications(technique, config=config, policy=policy)
    if notes:
        expected.add("notes")
    if policy:
        expected.add("sample")
    assert_set_equal(actual, expected)


def validate_measurement(
    measurement,
    scan_shape=None,
    positioners=None,
    config=True,
    technique=None,
    save_options=None,
    detectors=None,
    master_name=None,
    softtimer=None,
    save_images=True,
):
    """
    :param h5py.Group nxentry:
    :param tuple scan_shape: fast axis first
    :param list(list(str)) positioners: fast axis first
    :param bool config: configurable writer
    :param str technique:
    :param dict save_options:
    :param list(str) detectors:
    :param str master_name:
    :param str softtimer:
    :param bool save_images:
    """
    assert measurement.attrs == {"NX_class": "NXcollection"}
    # Detectors
    datasets = expected_channels(
        config=config,
        technique=technique,
        detectors=detectors,
        master_name=master_name,
        softtimer=softtimer,
        positioners=positioners,
        save_images=save_images,
    )
    # Positioners
    pos_instrument, pos_meas, pos_pgroup = expected_positioners(
        master_name=master_name, positioners=positioners, save_options=save_options
    )
    datasets[0] |= set(pos_meas)
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
        if not save_images and ndim == 2:
            continue
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
            assert_attributes(dset.name.split("/")[-1], dset, config=config)


def validate_instrument(
    instrument,
    scan_shape=None,
    config=True,
    positioners=None,
    policy=True,
    technique=None,
    save_options=None,
    detectors=None,
    master_name=None,
    softtimer=None,
    save_images=True,
):
    """
    :param h5py.Group instrument:
    :param tuple scan_shape: fast axis first
    :param bool config: configurable writer
    :param list(list(str)) positioners:
    :param bool policy: data policy
    :param str technique:
    :param dict save_options:
    :param list(str) detectors:
    :param str master_name:
    :param str softtimer:
    :param bool save_images:
    """
    assert instrument.attrs == {"NX_class": "NXinstrument"}
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
        config=config,
        technique=technique,
        detectors=detectors,
        master_name=master_name,
        softtimer=softtimer,
        positioners=positioners,
    )

    # Positioners
    pos_instrument, _, pos_positioners = expected_positioners(
        master_name=master_name, positioners=positioners, save_options=save_options
    )

    # Check all subgroups present
    if config:
        expected = {"title"}
    else:
        expected = set()
    expected |= expected_posg
    expected |= expected_dets
    expected |= set(pos_instrument.keys())
    expected |= {
        "att1",
        "beamstop",
        "primary_slit",
        "machine",
        "transfocator_simulator",
    }
    assert_set_equal(set(instrument.keys()), expected)

    if config:
        assert instrument["title"][()] == "esrf-id00a"

    # Validate content of positioner NXcollections
    for name in expected_posg:
        assert instrument[name].attrs["NX_class"] == "NXcollection", name
        expected = {
            "robx",
            "roby",
            "robz",
            "bsy",
            "bsz",
            "att1z",
            "s1b",
            "s1d",
            "s1f",
            "s1hg",
            "s1ho",
            "s1u",
            "s1vg",
            "s1vo",
        }
        if name == "positioners":
            expected |= set(pos_positioners)
        assert_set_equal(set(instrument[name].keys()), expected)

    # Validate content of NXpositioner groups
    for name, content in pos_instrument.items():
        assert instrument[name].attrs["NX_class"] == "NXpositioner", name
        assert_set_equal(set(instrument[name].keys()), set(content), msg=name)

    # Validate content of NXdetector groups
    variable_length = not all(scan_shape)
    for name in expected_dets:
        assert instrument[name].attrs["NX_class"] == "NXdetector", name
        expected = expected_detector_content(
            name, config=config, save_images=save_images
        )
        assert_set_equal(set(instrument[name].keys()), expected, msg=name)
        if config:
            islima_image = name in ["lima_simulator", "lima_simulator2"]
        else:
            islima_image = name in ["lima_simulator_image", "lima_simulator2_image"]
        if islima_image and save_images:
            assert_dataset(
                instrument[name]["data"],
                2,
                save_options,
                variable_length=variable_length,
            )

    # Validate content of other groups
    content = dictdump.nxtodict(instrument["beamstop"], asarray=False)
    assert content == {"@NX_class": "NXbeam_stop", "status": "in"}

    content = dictdump.nxtodict(instrument["att1"], asarray=False)
    assert content == {"@NX_class": "NXattenuator", "status": "in", "type": "Al"}

    content = dictdump.nxtodict(instrument["primary_slit"], asarray=False)
    assert content == {
        "@NX_class": "NXslit",
        "horizontal_gap": 0.0,
        "horizontal_offset": 0.0,
        "vertical_gap": 0.0,
        "vertical_offset": 0.0,
    }

    content = dictdump.nxtodict(instrument["transfocator_simulator"], asarray=False)
    assert content["@NX_class"] == "NXcollection"
    # The value of the L and P datasets is `True`, `False` or `None`.
    # A dataset value of `??one` which is skipped by dicttonx;
    maxkeys = {"@NX_class", "L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8", "P0", "P9"}
    assert not (set(content.keys()) - maxkeys)

    content = dictdump.nxtodict(instrument["machine"], asarray=False)
    expected = {
        "@NX_class": "NXsource",
        "automatic_mode": content["automatic_mode"],
        "current": content["current"],
        "current@units": "mA",
        "filling_mode": "7/8 multibunch",
        "front_end": "",
        "message": "You are in Simulated Machine",
        "mode": content["mode"],
        "name": "ESRF",
        "refill_countdown": content["refill_countdown"],
        "refill_countdown@units": "s",
        "type": "Synchrotron",
    }

    for k in expected:
        assert content[k] == expected[k], (k, content[k], expected[k])


def validate_plots(
    nxentry,
    config=True,
    policy=True,
    technique=None,
    detectors=None,
    scan_shape=None,
    positioners=None,
    master_name=None,
    softtimer=None,
    save_options=None,
    save_images=True,
):
    """
    :param h5py.Group nxentry:
    :param bool config: configurable writer
    :param bool policy: data policy
    :param str technique:
    :param list(str) detectors:
    :param tuple scan_shape: fast axis first
    :param list(list(str)) positioners: fast axis first
    :param str master_name:
    :param str softtimer:
    :param dict save_options:
    :param bool save_images:
    """
    plots = expected_plots(
        technique,
        config=config,
        policy=policy,
        detectors=detectors,
        master_name=master_name,
        softtimer=softtimer,
        positioners=positioners,
        save_images=save_images,
    )
    for name, info in plots.items():
        if info["signals"]:
            validate_nxdata(
                nxentry[name],
                info["ndim"],
                info["type"],
                info["signals"],
                scan_shape=scan_shape,
                positioners=positioners,
                master_name=master_name,
                save_options=save_options,
            )
        else:
            assert name not in nxentry, name


def validate_applications(
    nxentry, technique=None, config=True, policy=True, save_options=None, detectors=None
):
    """
    All application definitions for this technique (see nexus_definitions.yml)

    :param h5py.Group nxentry:
    :param str technique:
    :param bool config: configurable writer
    :param bool policy: data policy
    :param dict save_options:
    :param list detectors:
    """
    names = expected_applications(technique, config=config, policy=policy)
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
        if mcas:
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
    positioners=None,
    master_name="timer",
    save_options=None,
):
    """
    :param h5py.Group nxdata:
    :param int detector_ndim:
    :param str ptype:
    :param list expected_signals:
    :param tuple scan_shape: fast axis first
    :param list(list(str)) positioners: fast axis first
    :param str master_name:
    :param dict save_options:
    """
    assert nxdata.attrs["NX_class"] == "NXdata", nxdata.name
    signals = nexus.nxDataGetSignals(nxdata)
    assert_set_equal(set(signals), set(expected_signals), msg=nxdata.name)
    if ptype == "flat" and scan_shape:
        escan_shape = (numpy.product(scan_shape, dtype=int),)
    else:
        escan_shape = scan_shape
    axes = []
    for lst in positioners:
        if len(lst) > 1 and save_options["multivalue_positioners"]:
            lst = [master_name]
        axes.append(lst)
    if ptype == "grid":
        # C-order: fast axis last
        escan_shape = escan_shape[::-1]
        axes = axes[::-1]
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
    if not scan_shape:
        axes = []
    if detector_ndim:
        if len(scan_shape) > 1 and ptype == "flat":
            # Scatter plot of non-scalar detector
            axes = []
        else:
            axes += [["datadim{}".format(i)] for i in range(detector_ndim)]
    axes = [lst[0] if lst else None for lst in axes]
    if None in axes:
        axes = []
    nxdata_axes = list(nxdata.attrs.get("axes", []))
    assert nxdata_axes == axes, (nxdata_axes, axes, scan_shape, ptype, nxdata.name)


def validate_notes(nxentry, notes):
    """
    :param h5py.Group nxentry:
    :param list(str) notes:
    """
    if not notes:
        assert "notes" not in nxentry, nxentry.name
        return
    group = nxentry["notes"]
    assert group.attrs["NX_class"] == "NXcollection", group.name
    for i, data in enumerate(notes, 1):
        subgroup = group["note_{:02d}".format(i)]
        assert subgroup.attrs["NX_class"] == "NXnote", subgroup.name
        assert set(subgroup.keys()) == {"date", "type", "data"}
        assert subgroup["data"][()] == data
        assert subgroup["type"][()] == "text/plain"


def expected_plots(
    technique,
    config=True,
    policy=True,
    detectors=None,
    master_name=None,
    softtimer=None,
    positioners=None,
    save_images=True,
):
    """
    All expected plots for this technique (see nexus_definitions.yml)

    :param str technique:
    :param bool config: configurable writer
    :param bool policy: data policy
    :param list(str) detectors:
    :param str master_name:
    :param str softtimer:
    :param list(list(str)) positioners:
    :param bool save_images:
    :returns dict: grouped by detector dimension and flat/grid
    """
    plots = dict()
    channels = expected_channels(
        config=config,
        technique=technique,
        detectors=detectors,
        master_name=master_name,
        softtimer=softtimer,
        positioners=positioners,
        save_images=save_images,
    )

    def ismca1d(name):
        return ("simu" in name or "spectrum" in name) and "lima" not in name

    def islima1d_roi(name):
        return "roi4" in name

    def islima1d_collection(name):
        return "roi_collection" in name

    lima_1d_roi_signals = {name for name in channels[1] if islima1d_roi(name)}
    lima_1d_collection_signals = {
        name for name in channels[1] if islima1d_collection(name)
    }
    mca_1d_signals = {name for name in channels[1] if ismca1d(name)}
    other_1d_signals = (
        set(channels[1])
        - mca_1d_signals
        - lima_1d_roi_signals
        - lima_1d_collection_signals
    )
    n_1d_types = (
        bool(mca_1d_signals)
        + bool(other_1d_signals)
        + bool(lima_1d_roi_signals)
        + bool(lima_1d_collection_signals)
    )
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
            if n_1d_types == 1:
                signals = {f"simu{i}_det{j}" for i in range(1, 3) for j in range(4)}
                signals |= {"diode9alias_samples"}
                signals |= {"lima_simulator2_roi4", "lima_simulator_roi4"}
                signals |= {
                    "lima_simulator2_roi_collection",
                    "lima_simulator_roi_collection",
                }
                signals &= channels[1]
                plots["all_spectra"] = {"ndim": 1, "type": "flat", "signals": signals}
                plots["all_spectra_grid"] = {
                    "ndim": 1,
                    "type": "grid",
                    "signals": signals,
                }
            else:
                plotctr = 1
                lst = [
                    other_1d_signals,
                    lima_1d_roi_signals,
                    lima_1d_collection_signals,
                    mca_1d_signals,
                ]
                for signals in sorted(lst, key=lambda x: sorted(x)):
                    if not signals:
                        continue
                    if signals == other_1d_signals:
                        affix = "_samplingcounter"
                    elif signals == lima_1d_roi_signals:
                        affix = "_lima"
                    elif signals == lima_1d_collection_signals:
                        affix = "_lima"
                    elif signals == mca_1d_signals:
                        affix = "_mca"
                    else:
                        affix = None
                    affix += str(plotctr)
                    plots["all_spectra" + affix] = {
                        "ndim": 1,
                        "type": "flat",
                        "signals": signals,
                    }
                    plots["all_spectra_grid" + affix] = {
                        "ndim": 1,
                        "type": "grid",
                        "signals": signals,
                    }
                    plotctr += 1

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
                "simu1_det0_fractional_dead_time",
                "simu2_det1_fractional_dead_time",
            }
            signals &= channels[0]
            plots["xrf_counters"] = {"ndim": 0, "type": "flat", "signals": signals}
            plots["xrf_counters_grid"] = {"ndim": 0, "type": "grid", "signals": signals}
        if "xas" in technique:
            signals = {
                "diode4",
                "diode5",
                "simu1_det0_fractional_dead_time",
                "simu2_det1_fractional_dead_time",
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
        if n_1d_types == 1:
            plots["plot1D"] = {"ndim": 1, "type": "flat", "signals": channels[1]}
        else:
            plotctr = 1
            lst = [
                other_1d_signals,
                lima_1d_roi_signals,
                lima_1d_collection_signals,
                mca_1d_signals,
            ]
            for signals in sorted(lst, key=lambda x: sorted(x)):
                if not signals:
                    continue
                plots["plot1D_unknown1D" + str(plotctr)] = {
                    "ndim": 1,
                    "type": "flat",
                    "signals": signals,
                }
                plotctr += 1
        # All 2D detectors
        plots["plot2D"] = {"ndim": 2, "type": "flat", "signals": channels[2]}
    return plots


def expected_applications(technique, config=True, policy=True):
    """
    All expected application definitions for this technique (see nexus_definitions.yml)

    :param str technique:
    :param bool config: configurable writer
    :param bool policy: data policy
    :returns set:
    """
    apps = set()
    if config:
        if "xrf" in technique or "xas" in technique:
            apps |= {"xrf"}
    return apps


def expected_positioners(
    master_name=None, positioners=None, softtimer=None, save_options=None
):
    """
    Expected positioners

    :param str master_name:
    :param list(list(str)) positioners:
    :param str softtimer:
    :param dict save_options:
    :returns dict, set, set: content, measurement, positioners
    """
    content = {}  # groups under NXinstrument
    measurement = set()  # links under measurement
    pgroup = set()  # links under instrument/positioners
    for axes in positioners:
        if len(axes) > 1:
            if save_options["multivalue_positioners"]:
                content[master_name] = ["value"] + axes[1:]
                measurement.add(master_name)
                pgroup.add(master_name)
                pgroup |= {master_name + "_" + axis for axis in axes[1:]}
                measurement |= {master_name + "_" + axis for axis in axes[1:]}
            else:
                for axis in axes:
                    content[axis] = ["value"]
                measurement |= set(axes)
                pgroup |= set(axes)
        elif axes:
            content[axes[0]] = ["value"]
            measurement.add(axes[0])
            pgroup.add(axes[0])
    if softtimer == "master":
        if save_options["multivalue_positioners"]:
            content[master_name] = ["value", "epoch"]
            measurement |= {master_name, master_name + "_epoch"}
            pgroup |= {master_name, master_name + "_epoch"}
        else:
            content["elapsed_time"] = ["value"]
            content["epoch"] = ["value"]
            measurement |= {"elapsed_time", "epoch"}
            pgroup |= {"elapsed_time", "epoch"}
    return content, measurement, pgroup


def expected_detectors(
    config=True,
    technique=None,
    detectors=None,
    master_name=None,
    softtimer=None,
    positioners=None,
):
    """
    Expected detectors

    :param bool config: configurable writer
    :param str technique:
    :param list(str) detectors:
    :param str master_name:
    :param str softtimer:
    :param list(list(str)) positioners:
    :returns set:
    """
    if config:
        # Data channels are grouped per detector
        expected = {
            "diode2alias",
            "diode3",
            "diode4",
            "diode5",
            "diode6",
            "diode7",
            "diode8",
            "diode9alias",
            "sim_ct_gauss",
            "sim_ct_gauss_noise",
            "sim_ct_linear",
            "thermo_sample",
        }
        if "xrf" in technique or "xas" in technique or detectors:
            names = {"simu1", "simu2"}
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
            for name in names:
                expected |= {
                    name,
                    name + "_roi1",
                    name + "_roi2",
                    name + "_roi3",
                    name + "_roi4",
                    name + "_bpm",
                    name + "_roi_collection",
                }
        expected = detectors_filter(expected, detectors)
        if softtimer == "detector":
            expected |= {"elapsed_time", "epoch"}
        if positioners and any("robx" in axes for axes in positioners):
            expected.add("robxenc")
        if detectors and "machinfo.counters.current" in detectors:
            expected.add("current")
    else:
        # Each data channel is a detector
        expected = set()
        channels = expected_channels(
            config=config,
            technique=technique,
            detectors=detectors,
            master_name=master_name,
            softtimer=softtimer,
            positioners=positioners,
        )
        for names in channels.values():
            expected |= names
    return expected


def detectors_filter(expected, detectors, removeprefix=False):
    """
    :param sequence expected:
    :param list(str) detectors:
    :returns set:
    """
    if not detectors:
        return expected
    result = []
    for pattern in detector_pattern(detectors):
        result += [d for d in expected if re.match(pattern, d)]
    if removeprefix:
        result = remove_controller_prefix(
            result,
            ["^lima_simulator_", "^lima_simulator2_"],
            ["lima_simulator", "lima_simulator2"],
            [
                "{}_roi_counters_",
                "{}_roi_profiles_",
                "{}_roi_collection_",
                "{}_bpm_",
                "{}_",
            ],
        )
        result = remove_controller_prefix(
            result, ["^simu1_", "^simu2_"], ["simu1", "simu2"], ["{}_"]
        )
    return set(result)


def remove_controller_prefix(names, patterns, connames, replacefmts):
    """
    :param list(str) names:
    :param list(str) patterns:
    :param list(str) connames:
    :returns list(str):
    """
    connames = [
        conname
        for conname, pattern in zip(connames, patterns)
        if any(re.match(pattern, name) for name in names)
    ]
    if len(connames) == 1:
        for fmt in replacefmts:
            s = fmt.format(connames[0])
            names = [name.replace(s, "") for name in names]
    return names


def detector_pattern(detectors):
    patterns = {
        "diode7": "^diode7.*$",
        "diode9": "^diode9.*$",
        "diode9alias": "^diode9alias.*$",
        "lima_simulator": "^lima_simulator([^2].*|)$",
        "lima_simulator2": "^lima_simulator2.*$",
        "simu1": "^simu1.*$",
        "simu2": "^simu2.*$",
    }
    return [
        d
        if d.startswith("^") and d.startswith("$")
        else patterns.get(d, "^{}$".format(d))
        for d in detectors
    ]


def expected_detector_content(name, config=True, save_images=True):
    """
    :param bool config: configurable writer
    :param bool save_images:
    :returns set:
    """
    if config:
        if name.startswith("diode"):
            datasets = {"data", "mode", "type"}
            if name.startswith("diode9"):
                datasets |= {"samples"}
            elif name == "diode7":
                datasets |= {"N", "max", "min", "p2v", "std", "var"}
        elif name in ("thermo_sample", "robxenc", "current"):
            datasets = {"data", "mode", "type"}
        elif name.startswith("simu"):
            datasets = {"type", "roi1", "roi2", "roi3"}
            if "sum" not in name:
                datasets |= {
                    "data",
                    "fractional_dead_time",
                    "elapsed_time",
                    "trigger_live_time",
                    "triggers",
                    "trigger_count_rate",
                    "live_time",
                    "events",
                    "event_count_rate",
                }
        elif name.startswith("lima"):
            if "roi" in name:
                if "roi4" in name or "collection" in name:
                    datasets = {"data", "type", "selection"}
                else:
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
                if save_images:
                    datasets = {"type", "data", "acq_parameters", "ctrl_parameters"}
                else:
                    datasets = {"type", "acq_parameters", "ctrl_parameters"}
        elif name.startswith("simu1_") or name.startswith("simu2_"):
            datasets = {"data", "type"}
        else:
            datasets = {"data"}
    else:
        if name.startswith("lima"):
            if "roi_counter" in name:
                datasets = {"data", "roi1", "roi2", "roi3"}
            elif "roi_profile" in name:
                datasets = {"data", "roi4"}
            elif "roi_collection" in name:
                datasets = {"data", "roi_collection_counter"}
            elif "bpm" in name:
                datasets = {"data"}
            else:
                if save_images:
                    datasets = {"data", "acq_parameters", "ctrl_parameters", "type"}
                else:
                    datasets = {"acq_parameters", "ctrl_parameters", "type"}
        elif name == "image":
            if save_images:
                datasets = {"data", "acq_parameters", "ctrl_parameters", "type"}
            else:
                datasets = {"acq_parameters", "ctrl_parameters", "type"}
        elif re.match("roi[1-3]_(sum|avg|std|min|max)", name):
            datasets = {"data", "roi1", "roi2", "roi3"}
        elif name == "roi4":
            datasets = {"data", "roi4"}
        elif name == "roi_collection_counter":
            datasets = {"data", "roi_collection_counter"}
        elif re.match("roi[1-3]", name):
            # Lima
            datasets = {"data", "type"}
        elif name.startswith("simu1_") or name.startswith("simu2_"):
            # MCAs
            datasets = {"data", "type"}
        elif (
            name.endswith("_det0")
            or name.endswith("_det1")
            or name.endswith("_det2")
            or name.endswith("_det3")
        ):
            # MCAs
            datasets = {"data", "type"}
        else:
            datasets = {"data"}
    return datasets


def expected_channels(
    config=True,
    technique=None,
    detectors=None,
    master_name=None,
    softtimer=None,
    positioners=None,
    save_images=True,
):
    """
    Expected channels grouped per dimension

    :param bool config: configurable writer
    :param str technique:
    :param list(str) detectors:
    :param str master_name:
    :param str softtimer:
    :param list(list(str)) positioners:
    :param bool save_images:
    :returns dict: key are the unique names (used in plots and measurement)
    """
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
        "sim_ct_linear",
        "thermo_sample",
    }
    names |= {"diode2alias", "diode9alias"}
    datasets[0] |= names
    # Statistics diodes
    names = {"diode7"}
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
    names = {"diode9alias"}
    for name in names:
        datasets[1] |= {name + "_samples"}
    # MCA's with ROI's
    if "xrf" in technique or "xas" in technique or detectors:
        names = {"simu1", "simu2"}
        if config:
            for conname in names:
                for detname in ["det0", "det1", "det2", "det3"]:
                    detname = conname + "_" + detname
                    datasets[1] |= {detname}
                    datasets[0] |= {
                        detname + "_trigger_live_time",
                        detname + "_triggers",
                        detname + "_trigger_count_rate",
                        detname + "_live_time",
                        detname + "_events",
                        detname + "_event_count_rate",
                        detname + "_fractional_dead_time",
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
                    prefix = conname + "_"
                    datasets[1] |= {prefix + "spectrum_" + detname}
                    datasets[0] |= {
                        prefix + "trigger_livetime_" + detname,
                        prefix + "triggers_" + detname,
                        prefix + "icr_" + detname,
                        prefix + "energy_livetime_" + detname,
                        prefix + "events_" + detname,
                        prefix + "ocr_" + detname,
                        prefix + "deadtime_" + detname,
                        prefix + "realtime_" + detname,
                        prefix + "roi1_" + detname,
                        prefix + "roi2_" + detname,
                        prefix + "roi3_" + detname,
                    }
                datasets[0] |= {prefix + "roi1", prefix + "roi2", prefix + "roi3"}
    # Lima's with ROI's and BPM
    if "xrd" in technique or detectors:
        names = {"lima_simulator", "lima_simulator2"}
        if config:
            for conname in names:
                if save_images:
                    datasets[2] |= {conname}
                datasets[1] |= {conname + "_roi4", conname + "_roi_collection"}
                datasets[0] |= {
                    conname + "_roi1",
                    conname + "_roi1_min",
                    conname + "_roi1_max",
                    conname + "_roi1_avg",
                    conname + "_roi1_std",
                    conname + "_roi2",
                    conname + "_roi2_min",
                    conname + "_roi2_max",
                    conname + "_roi2_avg",
                    conname + "_roi2_std",
                    conname + "_roi3",
                    conname + "_roi3_min",
                    conname + "_roi3_max",
                    conname + "_roi3_avg",
                    conname + "_roi3_std",
                    conname + "_bpm_x",
                    conname + "_bpm_y",
                    conname + "_bpm_fwhm_x",
                    conname + "_bpm_fwhm_y",
                    conname + "_bpm_intensity",
                    conname + "_bpm_acq_time",
                }
        else:
            for conname in names:
                prefix = conname + "_"
                prefix_roi = conname + "_roi_counters_"
                prefix_roi_profile = conname + "_roi_profiles_"
                prefix_bpm = conname + "_bpm_"
                prefix_roi_collection = conname + "_roi_collection_"
                if save_images:
                    datasets[2] |= {prefix + "image"}
                datasets[1] |= {
                    prefix_roi_profile + "roi4",
                    prefix_roi_collection + "roi_collection_counter",
                }
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
                    prefix_bpm + "x",
                    prefix_bpm + "y",
                    prefix_bpm + "fwhm_x",
                    prefix_bpm + "fwhm_y",
                    prefix_bpm + "intensity",
                    prefix_bpm + "acq_time",
                }
    for k in datasets:
        datasets[k] = detectors_filter(datasets[k], detectors, removeprefix=not config)
    if softtimer == "detector":
        datasets[0] |= {"elapsed_time", "epoch"}
    if positioners and any("robx" in axes for axes in positioners):
        datasets[0].add("robxenc")
    if detectors and "machinfo.counters.current" in detectors:
        datasets[0].add("current")
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

    if "lima_simulator" in dset.name and detector_ndim == 2:
        assert_lima_image_data(dset, save_options, variable_length=variable_length)
    elif "sim_ct_linear" in dset.name:
        assert_linear_dataset(dset, detector_ndim)
    else:
        assert_random_dataset(dset, detector_ndim)


def assert_lima_image_data(dset, save_options, variable_length=False):
    """Checks whether the image maxima are linear and check external links
    """
    # Check external data (VDS or raw external)
    isexternal = isvirtual = False
    if dset.parent.attrs.get("NX_class", "") == "NXdetector":
        # This is the external dataset itself, not a softlink in
        # measurement or NXdata
        if "lima_simulator2" in dset.name:
            isexternal = bool(dset.external)
            if save_options["allow_external_nonhdf5"]:
                assert isexternal, dset.name
            else:
                assert not isexternal, dset.name
        else:
            try:
                isvirtual = dset.is_virtual
            except RuntimeError:
                isvirtual = False
            if save_options["allow_external_hdf5"]:
                assert isvirtual, dset.name
            else:
                assert not isvirtual, dset.name

    # Check image maxima: 100, 200, ...
    data = dset[()].max(axis=(-2, -1)).flatten(order="C")
    npoints = data.size
    if variable_length:
        npoints -= 1
        if npoints:
            data = data[:-1]
    if npoints:
        edata = numpy.arange(1, npoints + 1) * 100
        numpy.testing.assert_array_equal(data, edata, err_msg=dset.name)

    # Check that we don't have one virtual source per image
    if isvirtual:
        sources = dset.virtual_sources()
        assert len(sources) < npoints or npoints <= 1


def assert_linear_dataset(dset, detector_ndim):
    """Check whether data is linear in the scan dimension
    """
    if dset.ndim == detector_ndim:
        return
    detaxis = tuple(range(-detector_ndim, 0))
    data = dset[()].max(axis=detaxis).flatten(order="C")
    data = numpy.diff(data)
    numpy.testing.assert_allclose(data, data[0], err_msg=dset.name)


def assert_random_dataset(dset, detector_ndim):
    """Checks whether we have at least one valid value along the
    detector dimensions
    """
    try:
        numpy.array(numpy.nan, dset.dtype)
    except ValueError:
        return  # TODO: figure out how to mark missing data
        invalid = dset[()] == 0
    else:
        invalid = numpy.isnan(dset[()])
    detaxis = tuple(range(-detector_ndim, 0))
    invalid = invalid.min(axis=detaxis)
    assert not invalid.all() or invalid.size == 1, dset.name


def assert_attributes(unique_name, dset, config=True):
    """
    Check whether dataset contains the expected attributes

    :param str unique_name:
    :param h5py.Dataset dset:
    """
    if unique_name in ["elapsed_time", "epoch"]:
        assert dset.attrs.get("units") == "s", unique_name
    elif "bpm_fwhm_y" in unique_name:
        assert dset.attrs.get("units") == "px", unique_name
    elif "thermo" in unique_name:
        assert dset.attrs.get("units") == "deg", unique_name
    if not config:
        return
    if "live_time" in unique_name:
        assert dset.attrs.get("units") == "s", unique_name
    elif "icr" in unique_name:
        assert dset.attrs.get("units") == "hertz", unique_name


def validate_detector_data_npoints(scan, subscan=1, npoints=None):
    """
    :param bliss.scanning.scan.Scan scan:
    :param int subscan:
    :param int npoints:
    """
    uri = scan_utils.scan_uri(scan, subscan=subscan)
    with nexus.uriContext(uri) as nxentry:
        instrument = nxentry["instrument"]
        for name in instrument:
            detector = instrument[name]
            if nexus.isNxClass(detector, "NXdetector"):
                dset = instrument[detector]["data"]
                assert dset.shape[0] == npoints, dset.name
