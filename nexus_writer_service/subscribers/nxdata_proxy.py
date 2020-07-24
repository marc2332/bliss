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

import logging
from collections import namedtuple
import numpy
from ..io import nexus
from .dataset_proxy import shape_to_size, split_shape
from ..utils.logging_utils import CustomLogger


logger = logging.getLogger(__name__)


NXsignal = namedtuple("NXsignal", ["name", "value", "attrs"])
NXaxis = namedtuple("NXaxis", ["name", "value", "attrs"])
NXplotID = namedtuple("NXplotID", ["name", "scan_shape", "detector_shape"])


class NXplot:
    def __init__(self, nxplotid, suffix=None):
        """
        :param NXplotID nxplotid:
        :param str suffix: optional suffix which is added to the NXdata
                           name in case of NXdata splitting
        """
        if suffix:
            self.suffix = "_" + suffix
        else:
            self.suffix = ""
        self._signals = []
        self._axes = []
        self.nxplotid = nxplotid

    def add_signal(self, signal):
        """
        :param signal NXsignal:
        """
        self._signals.append(signal)

    @property
    def sortkey(self):
        """
        :returns list(str):
        """
        return sorted([s.name for s in self._signals])

    def add_axes(self, positioners, saveorder):
        """
        :param list(DatasetProxy) positioners:
        :param SaveOrder saveorder:
        """
        scan_shape = self.nxplotid.scan_shape
        detector_shape = self.nxplotid.detector_shape
        scan_ndim = len(scan_shape)
        detector_ndim = len(detector_shape)
        ndim = scan_ndim + detector_ndim
        if scan_ndim:
            # Scan axes dict
            axes = {}
            for dproxy in positioners:
                with dproxy.open(dproxy) as dset:
                    if dset is None:
                        continue
                    axes[dproxy.master_index] = NXaxis(dproxy.linkname, dset, None)

            # TODO: Scatter plot of non-scalar detector
            #       does not have a visualization so no
            #       axes for now
            flattened = scan_ndim != len(axes)
            if flattened and detector_ndim:
                self._axes = []
                return

            # Sort axes
            #   grid plot: fast axis last
            #   scatter plot: fast axis first
            if saveorder.order == "C" and not flattened:
                # Fast axis last
                keys = reversed(sorted(axes))
            else:
                # Fast axis first
                keys = sorted(axes)

            # Dataset creation arguments
            lst = []
            for i, key in enumerate(keys):
                name, value, attrs = axes[key]
                if scan_ndim > 1:  # Grid plot (e.g. image)
                    # Axis values: shape of scan
                    value = value[()]
                    if value.ndim == 1:
                        value = value.reshape(scan_shape)
                    avgdims = tuple(j for j in range(value.ndim) if i != j)
                    # Average along all but axis dimension
                    value = value.mean(avgdims)
                    # Make linear
                    x = numpy.arange(value.size)
                    mask = numpy.isfinite(value)
                    try:
                        m, b = numpy.polyfit(x[mask], value[mask], 1)
                    except Exception:
                        value = numpy.linspace(
                            numpy.nanmin(value), numpy.nanmax(value), value.size
                        )
                    else:
                        value = m * x + b
                else:  # Scatter plot (coordinates and value)
                    if value.ndim > 1:
                        value = {"data": nexus.getUri(value), "shape": scan_shape}
                lst.append(NXaxis(name, value, attrs))
            axes = lst
        else:
            axes = []

        # Add axes for the data dimensions (which are always at the end)
        if ndim - len(axes) == detector_ndim:
            axes += [
                NXaxis("datadim{}".format(i), numpy.arange(detector_shape[i]), None)
                for i in range(detector_ndim)
            ]
        self._axes = axes

    def save(self, nxentry, plotname):
        """
        Create on NXdata with signals and axes.

        :param h5py.Group nxentry:
        :param str plotname:
        :returns h5py.Group:
        """
        h5group = nexus.nxData(nxentry, plotname)
        nexus.nxDataAddSignals(h5group, self._signals)
        if self._axes:
            nexus.nxDataAddAxes(h5group, self._axes)
        return h5group


class NXdataProxy:
    """Adding signals with incompatible shapes will result in multiple NXdata's.
    """

    def __init__(self, plotname, parentlogger=None):
        """
        :param str plotname: NXdata may become "{name}_{suffix}{i}" depending plot splitting
        :param parentlogger:
        """
        self.plotname = plotname
        self._plots = {}  # NXplotID -> NXplot
        if parentlogger is None:
            parentlogger = logger
        self.logger = CustomLogger(parentlogger, f"NXdata({plotname})")

    def __bool__(self):
        return bool(self._plots)

    def iter_plots(self):
        """Yield the NXplot's and their unique names

        :yields (str, NXplot): plot name and plot
        """
        suffixes = [nxplot.suffix for nxplot in self._plots.values()]
        need_suffix = len(suffixes) > 1
        need_index = len(set(suffixes)) != len(suffixes)
        i = 0
        for nxplot in sorted(self._plots.values(), key=lambda nxplot: nxplot.sortkey):
            plotname = nxplot.nxplotid.name
            if need_suffix:
                plotname += nxplot.suffix
                if need_index:
                    i += 1
                    plotname += str(i)
            yield plotname, nxplot

    def save(self, nxentry, default, plotselect):
        """Save all the NXplot's as NXdata groups

        :param h5py.Group nxentry:
        :param h5py.Group default: the default NXdata group
        :param str plotselect:
        :returns h5py.Group: the default NXdata group
        """
        for plotname, nxplot in self.iter_plots():
            plot = nxplot.save(nxentry, plotname)
            if default is None or nxplot.nxplotid.name == plotselect:
                default = plot
            self.logger.info("Saved")
        return default

    def add_axes(self, positioners, saveorder):
        """Add axes to all NXplot's. Call this after all signals
        have been added (adding a singal could add another NXplot).

        :param list(DatasetProxy) positioners:
        :param SaveOrder saveorder:
        """
        for nxplot in self._plots.values():
            nxplot.add_axes(positioners, saveorder)

    def add_signal(self, dproxy, grid):
        """Add a dataset to the appropriate NXplot

        :param DatasetProxy dproxy:
        :param bool grid:
        """
        with dproxy.open() as dset:
            if dset is None:
                return
            linkname = dproxy.linkname
            if not linkname:
                dproxy.logger.warning("cannot be linked too")
                return

            # Determine signal shape
            if dproxy.reshaped == grid:
                if not nexus.HASVIRTUAL:
                    dproxy.logger.error(
                        f"Cannot reshape for plot {repr(self.plotname)} due to missing VDS support"
                    )
                    return
                if grid:
                    shape = dproxy.grid_shape
                else:
                    shape = dproxy.flat_shape
                npoints = shape_to_size(dset.shape)
                enpoints = shape_to_size(shape)
                if npoints != enpoints:
                    dproxy.logger.error(
                        f"Cannot reshape {dset.shape} to {shape} for plot {repr(self.plotname)}"
                    )
                    return
            else:
                shape = dset.shape

            # Arguments for dataset creation
            attrs = {}
            scan_shape, detector_shape = split_shape(shape, dproxy.detector_ndim)
            if shape == dset.shape:
                # Same shape so this will be a link
                value = dset
            else:
                # Different shape so this will be a virtual dataset
                scan_ndim = len(scan_shape)
                detector_ndim = len(detector_shape)
                value = {"data": nexus.getUri(dset), "shape": shape}
                interpretation = nexus.nxDatasetInterpretation(
                    scan_ndim, detector_ndim, scan_ndim
                )
                attrs["interpretation"] = interpretation

        # Add the signal
        signal = NXsignal(name=linkname, value=value, attrs=attrs)
        nxplotid = NXplotID(
            name=self.plotname, scan_shape=scan_shape, detector_shape=detector_shape
        )
        signals = self._plots.get(nxplotid)
        if signals is None:
            signals = self._plots[nxplotid] = NXplot(
                nxplotid, suffix=dproxy.device_type
            )
        signals.add_signal(signal)
