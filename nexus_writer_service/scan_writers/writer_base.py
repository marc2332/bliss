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

"""
Basic Nexus writer listening to Redis events of a scan
"""

import gevent
import os
import numpy
import traceback
import logging
import datetime
from contextlib import contextmanager
from collections import defaultdict
from . import devices
from . import dataset_proxy
from ..io import nexus
from ..utils import scan_utils
from ..utils import logging_utils
from ..utils import profiling


logger = logging.getLogger(__name__)


default_saveoptions = {
    "flat": True,
    "multivalue_positioners": False,
    "allow_external_nonhdf5": False,  # not recommends due to absolute path links!!!
    "allow_external_hdf5": True,
    "profile": False,
}


cli_saveoptions = {
    "keepshape": (
        {"action": "store_false", "help": "Keep shape of multi-dimensional grid scans"},
        "flat",
    ),
    "multivalue_positioners": (
        {"action": "store_true", "help": "Allow positioners with multiple values"},
        "multivalue_positioners",
    ),
    "enable_external_nonhdf5": (
        {"action": "store_true", "help": "Enable external non-hdf5 files (like edf)"},
        "allow_external_nonhdf5",
    ),
    "disable_external_hdf5": (
        {
            "action": "store_false",
            "help": "Disable external hdf5 files (virtual datasets)",
        },
        "allow_external_hdf5",
    ),
    "enable_profiling": (
        {"action": "store_true", "help": "Enable code profiling"},
        "profile",
    ),
}


class NexusScanWriterBase(gevent.Greenlet):
    """
    Listens to events of a particular scan and
    writes the result in Nexus format.
    No configuration needed.
    """

    def __init__(self, scan_node, locks, wakeup_fd, parentlogger=None, **saveoptions):
        """
        The locks are only used to protect nxroot creation/updating.
        This is not needed for the nxentry because only one writer
        will create/update it.

        :param bliss.data.scan.Scan scan_node:
        :param geventsync.SharedLockPool locks:
        :param parentlogger:
        :param int wakeup_fd: receiving data from this file descriptor
                              means the scan has ended
        :param saveoptions:
        """
        super(NexusScanWriterBase, self).__init__()
        self.starttime = datetime.datetime.now()
        self.scan_node = scan_node
        self.wakeup_fd = wakeup_fd
        if parentlogger is None:
            parentlogger = logger
        self.logger = logging_utils.CustomLogger(
            parentlogger, "DataNode " + repr(scan_node.name)
        )
        # Save options
        for option, default in default_saveoptions.items():
            saveoptions[option] = saveoptions.get(option, default)
        saveoptions["short_names"] = True
        saveoptions["expand_variable_length"] = True
        self.saveoptions = saveoptions
        # Scan shape is filled as in 'C' (first axis last) or 'F' order (fast axis first)
        # Saving is always done in 'C'
        self._order = defaultdict(lambda: "C")
        # Cache
        self._data_nodes = []  # list(bliss.data.node.DataNode)
        self._datasets = {}  # subscan:dict(bliss.data.node.DataNode.fullname:DatasetProxy)
        self._nxroot = {}  # cache for recursive calling
        self._nxentry = None  # cache for recursive calling
        self._nxroot_locks = locks
        self._devices = {}  # subscan:dict(fullname:dict)
        self._subscanmap = {}  # subscan:dbname
        self._redis_cache = {}

    def __str__(self):
        parts = self.scan_node.db_name.split(":")
        return ":".join([parts[0], parts[-1]])
        # return self.scan_node.name

    def __repr__(self):
        return "NexusScanWriter({})".format(str(self))

    @property
    def scan_info(self):
        """
        Get the scan's info dictionary
        """
        return self.scan_node.info.get_all()

    def scan_info_get(self, key, default=None):
        """
        Get from the scan's info dictionary
        """
        return self.scan_node.info.get(key, default=default)

    def subscan_info_get(self, subscan, key, default=None):
        """
        Get from the subscan's info dictionary
        Try scan's info dictionary when key is missing

        :param str subscan:
        """
        for node in self.scan_node.children():
            if node.name == subscan:
                try:
                    return node.info[key]
                except KeyError:
                    return self.scan_info_get(key, default)
        return self.scan_info_get(key, default)

    @property
    def save(self):
        """
        Saving intended for this scan?
        """
        return self.scan_info_get("save", False)

    @property
    def filename(self):
        """
        HDF5 file name for data
        """
        return self._filename()

    def _filename(self, level=0):
        """
        HDF5 file name for data and masters
        """
        try:
            filename = self.filenames[level]
            if not os.path.dirname(filename):
                self.logger.warning(
                    "Saving {} in current working directory {}".format(
                        repr(filename), repr(os.getcwd())
                    )
                )
        except IndexError:
            filename = ""
        return filename

    @property
    def filenames(self):
        """
        :returns list: a list of filenames, the first for the dataset
                       and the others for the masters
        """
        if self.save:
            return scan_utils.scan_filenames(self.scan_node, config=False)
        else:
            return []

    @property
    def instrument_info(self):
        """
        Instrument information publish by the Bliss core library
        """
        return self.scan_info_get("instrument", default={})

    @property
    def config_devices(self):
        return {}

    @property
    def devices(self):
        """
        Maps subscan name to a dictionary of devices,
        which maps fullname to device info.
        """
        if not self._devices:
            self._devices = devices.device_info(
                self.config_devices,
                self.scan_info,
                short_names=self.saveoptions["short_names"],
                multivalue_positioners=self.saveoptions["multivalue_positioners"],
            )
        return self._devices

    @property
    def subscans(self):
        """
        Subscan names for which there are devices defined.
        """
        return list(sorted(self.devices.keys()))

    def subscan(self, node):
        """
        Get the subscan name to which this node belongs

        :param bliss.data.node.DataNode node:
        :returns str:
        """
        if len(self._subscanmap) == 1:
            subscan = next(iter(self._subscanmap.keys()))
        else:
            fullname = node.fullname
            matches = [
                subscan
                for subscan, prefix in self._subscanmap.items()
                if node.db_name.startswith(prefix)
            ]
            if len(matches) != 1:
                self.logger.warning("Could not identify subscan of " + repr(fullname))
                return ""
            subscan = matches[0]
        if subscan not in self.devices:
            self.logger.warning("No devices defined for subscan " + repr(subscan))
            return ""
        return subscan

    def device(self, subscan, node):
        """
        Get device information of the node belonging to the subscan

        :param str subscan:
        :param bliss.data.node.DataNode node:
        :returns dict:
        """
        fullname = node.fullname
        subdevices = self.devices[subscan]
        device = subdevices.get(fullname, None)
        if device is None:
            device = devices.update_device(subdevices, fullname)
        if not device["device_type"]:
            device["device_type"] = self._device_type(node)
        return device.copy()

    def _device_type(self, node):
        """
        Get device type from data node

        :param bliss.data.node.DataNode node:
        :returns str:
        """
        return "unknown{}D".format(len(node.shape))

    @contextmanager
    def nxroot(self, level=0):
        """
        Yields the NXroot instance (h5py.File) or None
        when information is missing
        """
        nxroot = self._nxroot.get(level, None)
        if nxroot is None:
            filename = self._filename(level=level)
            if filename:
                # REMARK: External readers could have opened
                # the file with `enable_file_locking=True` and
                # `swmr=False`.
                with nexus.nxRoot(
                    filename,
                    mode="a",
                    enable_file_locking=False,
                    swmr=False,
                    creationlocks=self._nxroot_locks,
                ) as nxroot:
                    try:
                        self._nxroot[level] = nxroot
                        yield nxroot
                    finally:
                        self._nxroot[level] = None
            else:
                self._h5missing("filenames")
                self._nxroot[level] = None
                yield None
        else:
            yield nxroot

    @contextmanager
    def nxentry(self, subscan):
        """
        :param str subscan:

        Yields the NXentry instance (h5py.Group) or None
        when information is missing
        """
        with self.nxroot() as nxroot:
            if nxroot is None:
                yield None
                return
            if self._nxentry is None:
                name = self._nxentry_name(subscan)
                if not name:
                    yield None
                    return
                # Create NXentry instance when missing
                nxentry = nxroot.get(name, None)
                if nxentry is None:
                    kwargs = self._nxentry_create_args()
                    if not kwargs:
                        yield None
                        return
                    nxentry = nexus.nxEntry(nxroot, name, **kwargs)
                try:
                    self._nxentry = nxentry
                    yield nxentry
                finally:
                    self._nxentry = None
            else:
                yield self._nxentry

    def _nxentry_name(self, subscan):
        """
        :param str subscan:
        :returns str:
        """
        try:
            subscan = self.subscans.index(subscan)
        except ValueError:
            self._h5missing("subscan " + repr(subscan))
            return None
        try:
            name = scan_utils.scan_name(self.scan_node, subscan + 1)
        except AttributeError as e:
            self._h5missing(str(e))
            return None
        return name

    def _nxentry_create_args(self):
        """
        Arguments for nxEntry creation

        :returns dict:
        """
        start_timestamp = self.scan_info_get("start_timestamp")
        if not start_timestamp:
            self._h5missing("start_timestamp")
            return None
        title = self.scan_info_get("title")
        if not title:
            self._h5missing("title")
            return None
        start_time = datetime.datetime.fromtimestamp(start_timestamp)
        datasets = {"title": title}
        kwargs = {"start_time": start_time, "datasets": datasets}
        return kwargs

    @contextmanager
    def nxmeasurement(self, subscan):
        """
        Yields the generic NXdata instance (h5py.Group) or None
        when NXentry is missing
        """
        with self.nxentry(subscan) as nxentry:
            if nxentry is None:
                yield None
            else:
                yield nexus.nxCollection(nxentry, "measurement")

    def _h5missing(self, variable):
        """
        :param str variable:
        """
        self.logger.debug(
            "HDF5 group not created yet ({} missing)".format(repr(variable))
        )

    def _create_measurement_group(self, subscan):
        """
        Fill measurement group with links to NXdetector

        :param str subscan:
        """
        with self.nxmeasurement(subscan) as measurement:
            if measurement is None:
                return
            self.logger.info("Create 'measurement' group")
            path = measurement.name
            motors = self.instrument_info.get("positioners", {})
            for dproxy in self.datasets(subscan).values():
                if dproxy.type == "positioner":
                    linknames = []
                    # Positioners should always be there under
                    # a different name when not in positioners
                    # snapshot
                    if dproxy.linkname not in motors:
                        linknames.append("pos_" + dproxy.linkname)
                    # Principle positioners which are masters should
                    # be there under their normal name
                    if dproxy.master_index >= 0 and dproxy.data_type == "principal":
                        linknames.append(dproxy.linkname)
                else:
                    # Only the principle value of this detector
                    # if dproxy.data_type != 'principal':
                    #    continue
                    linknames = [dproxy.linkname]
                with dproxy.open() as dset:
                    if dset is None:
                        continue
                    if dset.parent.name == path:
                        continue
                    for linkname in linknames:
                        nexus.nxCreateDataSet(measurement, linkname, dset, None)

    @property
    def plots(self):
        """
        NXdata signals
        """
        return {"plot{}D".format(ndim): {"ndim": ndim} for ndim in self.detector_ndims}

    @property
    def plotselect(self):
        """
        Default NXdata group
        """
        return "plot0D"

    def _create_plots(self, subscan):
        """
        Create default plot in Nexus structure

        :param str subscan:
        """
        with self.nxentry(subscan) as nxentry:
            if nxentry is None:
                return
            plotselect = self.plotselect
            firstplot = None
            plotselected = False
            plots = self.plots
            self.logger.info("Create plots: {}".format(list(plots.keys())))
            for plotname, plotparams in plots.items():
                if plotname in nxentry:
                    self.logger.warning(
                        "Cannot create plot {} (name already exists)".format(
                            repr(plotname)
                        )
                    )
                    continue
                signaldict = self._select_plot_signals(subscan, plotname, **plotparams)
                if signaldict:
                    # Make sure plot name is unique
                    fmt = "{}"
                    plotnames = set(
                        fmt.format(name) for name, _, _ in signaldict.keys()
                    )
                    if len(plotnames) != len(signaldict):
                        fmt = "{}_{}"
                        plotnames = set(
                            fmt.format(name, devicetype)
                            for (name, _, _), (
                                devicetype,
                                signals,
                            ) in signaldict.items()
                        )
                        if len(plotnames) != len(signaldict):
                            fmt = "{}_{}{}"
                    # Create axes belonging to the signals and save plots
                    for (
                        i,
                        ((name, scan_shape, detector_shape), (devicetype, signals)),
                    ) in enumerate(sorted(signaldict.items()), 1):
                        plotname = fmt.format(name, devicetype, i)
                        axes = self._select_plot_axes(
                            subscan, scan_shape, detector_shape
                        )
                        plot = self._create_plot(nxentry, plotname, signals, axes)
                        if plotname == plotselect:
                            plotselected = True
                            nexus.markDefault(plot)
                        if firstplot is None:
                            firstplot = plot
                        self.logger.info("Plot " + repr(plotname) + " created")
            if not plotselected:
                with self._nxroot_locks.acquire(self.filename):
                    if firstplot is not None:
                        nexus.markDefault(plot)
                    else:
                        nexus.markDefault(nxentry)

    def _select_plot_signals(self, subscan, plotname, ndim=-1, grid=False):
        """
        Select plot signals based on detector dimensions.

        :param str subscan:
        :param str plotname:
        :param int ndim: detector dimensions
        :param bool grid: preserve scan shape
        :returns dict: (str, tuple): (str, [(name, value, attrs)])
        """
        signaldict = {}
        if ndim >= 0:
            for fullname, dproxy in self.detector_iter(subscan):
                if dproxy.detector_ndim == ndim:
                    self._add_signal(plotname, grid, dproxy, signaldict)
        return signaldict

    def _add_signal(self, plotname, grid, dproxy, signaldict):
        """
        Add dataset to NXdata signal dictionary

        :param str plotname:
        :param bool grid:
        :param DatasetProxy dproxy:
        :param dict signaldict:
        """
        with dproxy.open() as dset:
            if dset is None:
                return
            # Determine signal shape
            if dproxy.flattened == grid:
                if not nexus.HASVIRTUAL:
                    dproxy.logger.error(
                        "Cannot reshape {} for plot {} due to missing VDS support".format(
                            repr(plotname)
                        )
                    )
                    return
                if grid:
                    shape = dproxy.grid_shape
                else:
                    shape = dproxy.flat_shape
                npoints = dataset_proxy.shape_to_size(dset.shape)
                enpoints = dataset_proxy.shape_to_size(shape)
                if npoints != enpoints:
                    dproxy.logger.error(
                        "Cannot reshape {} to {} for plot {}".format(
                            dset.shape, shape, repr(plotname)
                        )
                    )
                    return
            else:
                shape = dset.shape
            # Arguments for dataset creation
            attrs = {}
            scan_shape, detector_shape = dataset_proxy.split_shape(
                shape, dproxy.detector_ndim
            )
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
            # Add arguments to signaldict
            signal = (dproxy.linkname, value, attrs)
            key = plotname, scan_shape, detector_shape
            if key not in signaldict:
                signaldict[key] = dproxy.type, []
            lst = signaldict[key][1]
            lst.append(signal)

    def _create_plot(self, nxentry, plotname, signals, axes):
        """
        Create on NXdata with signals and axes.

        :param h5py.Group nxentry:
        :param str plotname:
        :param list signals:
        :param list axes:
        :returns h5py.Group:
        """
        h5group = nexus.nxData(nxentry, plotname)
        nexus.nxDataAddSignals(h5group, signals)
        if axes:
            nexus.nxDataAddAxes(h5group, axes)
        return h5group

    def _select_plot_axes(self, subscan, scan_shape, detector_shape):
        """
        :param str subscan:
        :param str scan_shape: signal scan shape
        :param str scan_shape: signal detector shape
        :returns list(3-tuple): name, value, attrs
        """
        scan_ndim = len(scan_shape)
        detector_ndim = len(detector_shape)
        ndim = scan_ndim + detector_ndim
        if scan_ndim:
            # Scan axes dict
            axes = {}
            for fullname, dproxy in self.positioner_iter(
                subscan, onlyprincipals=True, onlymasters=True
            ):
                with dproxy.open(dproxy) as dset:
                    if dset is None:
                        continue
                    axes[dproxy.master_index] = dproxy.linkname, dset, None

            # TODO: Scatter plot of non-scalar detector
            #       does not have a visualization
            flattened = scan_ndim != len(axes)
            if flattened and detector_ndim:
                return []

            # Sort axes
            #   grid plot: fast axis last
            #   scatter plot: fast axis first
            order = self.order(scan_ndim)
            if order == "C" and not flattened:
                # Fast axis last
                keys = reversed(sorted(axes))
            else:
                # Fast axis first
                keys = sorted(axes)

            # Dataset creation arguments
            lst = []
            for i, key in enumerate(keys):
                name, value, attrs = axes[key]
                if scan_ndim > 1:  # Grid plot
                    # Axis values: shape of scan
                    value = value[()]
                    if value.ndim == 1:
                        value = value.reshape(scan_shape)
                    avgdims = tuple(j for j in range(value.ndim) if i != j)
                    # Average along all but axis dimension
                    value = value.mean(avgdims)
                else:  # Scatter plot
                    if value.ndim > 1:
                        value = {"data": nexus.getUri(value), "shape": scan_shape}
                lst.append((name, value, attrs))
            axes = lst
        else:
            axes = []

        # Add axes for the data dimensions (which are always at the end)
        if ndim - len(axes) == detector_ndim:
            axes += [
                ("datadim{}".format(i), numpy.arange(detector_shape[i]), None)
                for i in range(detector_ndim)
            ]
        return axes

    def _mark_done(self, subscan):
        """
        The NXentry is completed

        :param str subscan:
        """
        with self.nxentry(subscan) as nxentry:
            if nxentry is not None:
                with self._nxroot_locks.acquire(nxentry.file.filename):
                    nexus.updated(nxentry, final=True, parents=True)
                self.logger.info("Scan marked as DONE in HDF5")

    @property
    def instrument_name(self):
        return ""

    @contextmanager
    def nxinstrument(self, subscan):
        """
        Yields the NXinstrument instance (h5py.Group) or None
        when NXentry is missing

        :param str subscan:
        """
        with self.nxentry(subscan) as nxentry:
            if nxentry is None:
                yield None
            else:
                datasets = {}
                title = self.instrument_name
                if title:
                    datasets["title"] = title
                yield nexus.nxInstrument(nxentry, "instrument", datasets=datasets)

    @contextmanager
    def nxdetector(self, subscan, name, **kwargs):
        """
        Yields the NXinstrument instance (h5py.Group) or None
        when NXentry is missing

        :param str subscan:
        """
        with self.nxinstrument(subscan) as nxinstrument:
            if nxinstrument is None:
                yield None
            else:
                yield nexus.nxDetector(nxinstrument, name, **kwargs)

    @contextmanager
    def nxpositioner(self, subscan, name, **kwargs):
        """
        Yields the NXinstrument instance (h5py.Group) or None
        when NXentry is missing

        :param str subscan:
        """
        with self.nxinstrument(subscan) as nxinstrument:
            if nxinstrument is None:
                yield None
            else:
                yield nexus.nxPositioner(nxinstrument, name, **kwargs)

    @contextmanager
    def nxpositioners(self, subscan, suffix=""):
        """
        Yields the generic positioners instance (h5py.Group) or None
        when NXentry is missing

        :param str subscan:
        """
        with self.nxinstrument(subscan) as nxinstrument:
            if nxinstrument is None:
                yield None
            else:
                yield nexus.nxCollection(nxinstrument, "positioners" + suffix)

    def _run(self):
        """
        Greenlet main function
        """
        try:
            if self.saveoptions["profile"]:
                with profiling.profile(
                    logger=self.logger,
                    timelimit=50,
                    memlimit=10,
                    sortby="cumtime",
                    units="MB",
                ):
                    self._listen_scan_events()
            else:
                self._listen_scan_events()
        except Exception:
            self.logger.error(
                "Stop writer due to exception:\n{}".format(traceback.format_exc())
            )

    def _listen_scan_events(self):
        """
        Listening to scan events
        """
        try:
            if self.save:
                self.logger.info(
                    "Start writing to {} with options {}".format(
                        repr(self.filename), self.saveoptions
                    )
                )
                iterator = self.scan_node.iterator
                iterator.wakeup_fd = self.wakeup_fd
                # walk_events: all events, also the ones that have already passed
                for event_type, node in iterator.walk_events():
                    try:
                        if event_type.name == "EXTERNAL_EVENT":
                            self.logger.info("Scan is finished, stop processing events")
                            break
                        else:
                            self._process_event(event_type, node)
                    except gevent.GreenletExit:
                        raise
                    except Exception:
                        self.logger.warning(
                            "Process {} event caused an exception:\n{}".format(
                                repr(event_type.name), traceback.format_exc()
                            )
                        )
            else:
                self.logger.info("No saving requested")
        except gevent.GreenletExit:
            self.logger.info("Writer stop requested")
        finally:
            if self.save:
                nbytes = 0
                try:
                    nbytes = self._finalize()
                except Exception:
                    self.logger.error(
                        "Not properly finalized due to exception:\n{}".format(
                            traceback.format_exc()
                        )
                    )
                finally:
                    dtime = datetime.datetime.now() - self.starttime
                    self.logger.info(
                        "Finished writing to {} ({} in {})".format(
                            repr(self.filename),
                            dataset_proxy.format_bytes(nbytes),
                            dtime,
                        )
                    )
            self.logger.info("Writer exits")

    def _finalize(self):
        """
        Finish writing

        :returns int: total number of bytes (data-only)
        """
        self.logger.info("Finalize writing to {}".format(repr(self.filename)))
        nbytes = 0
        try:
            self.logger.info("Fetch last data")
            for node in self._data_nodes:
                self._fetch_data(node, last=True)

            self.logger.info("Ensure all dataset have the same number of points")
            for subscan in self.subscans:
                self._ensure_same_length(subscan)

            self.logger.info("Create external datasets if any")
            for node in self._data_nodes:
                dproxy = self._ensure_dataset_existance(node)
                if dproxy is not None:
                    nbytes += dproxy.current_bytes

            for subscan in self.subscans:
                self._finalize_extra(subscan)
                self._mark_done(subscan)
        finally:
            self._nxroot_locks.pop(self.filename)
        return nbytes

    def _finalize_extra(self, subscan):
        """
        All raw data and metadata has been saved.
        Save additional information.

        :param str subscan:
        """
        self._save_positioners(subscan)
        self._create_measurement_group(subscan)
        self._create_plots(subscan)

    @property
    def current_bytes(self):
        """
        Total bytes (data-only) of all subscans
        """
        nbytes = 0
        for subscan in self.subscans:
            for dproxy in self.datasets(subscan).values():
                if dproxy is not None:
                    nbytes += dproxy.current_bytes
        return nbytes

    @property
    def detector_ndims(self):
        """
        All detector dimensions
        """
        ret = set()
        for subscan in self.subscans:
            for dproxy in self.datasets(subscan).values():
                if dproxy is not None:
                    ret.add(dproxy.detector_ndim)
        return ret

    def _process_event(self, event_type, node):
        """
        Process event belonging to this scan
        """
        if event_type.name == "NEW_NODE":
            self._event_new_node(node)
        elif event_type.name == "NEW_DATA_IN_CHANNEL":
            self._event_new_data(node)
        else:
            event_info = event_type.name, node.type, node.name, node.fullname
            self.logger.debug("Untreated event: {}".format(event_info))

    def _event_new_node(self, node):
        """
        Creation of a new Redis node
        """
        name = repr(node.name)
        if node.type == "scan":
            self.logger.debug("Start scan " + name)
            self._event_start_scan(node)
        elif node.type == "channel":
            self.logger.debug("New channel " + name)
            self._event_new_datanode(node)
        elif node.type == "lima":
            self.logger.debug("New Lima " + name)
            self._event_new_datanode(node)
        elif node.parent.type == "scan":
            self.logger.debug("New subscan " + name)
            self._event_new_subscan(node)
        else:
            self.logger.debug(
                "new {} node event on {} not treated".format(
                    repr(node.type), repr(name)
                )
            )

    def _event_new_subscan(self, node):
        """
        :param node bliss.data.node.DataNodeContainer:
        """
        subscan = node.name
        self.logger.debug("Start sub scan " + subscan)
        if subscan not in self._subscanmap:
            self._subscanmap[subscan] = node.db_name
        self._save_positioners(subscan)

    def _event_new_data(self, node):
        """
        Creation of a new data node
        """
        # New data in an existing Redis node
        name = repr(node.fullname)
        if node.type == "channel":
            self._fetch_data(node)
        elif node.type == "lima":
            self._fetch_data(node)
        else:
            self.logger.warning(
                "New {} data for {} not treated".format(repr(node.type), name)
            )

    def _event_start_scan(self, scan):
        """
        Scan has started

        :param bliss.data.scan.Scan scan:
        """
        self.logger.debug("title = " + self.scan_info_get("title", ""))

    def _event_new_datanode(self, node):
        """
        New data node is created

        :param bliss.data.node.DataNode node:
        """
        self._data_nodes.append(node)
        subscan = self.subscan(node)
        if subscan:
            self._create_dataset_proxy(subscan, node)

    def _create_dataset_proxy(self, subscan, node):
        """
        Initialize HDF5 dataset creation for a data node.

        :param str subscan:
        :param bliss.data.node.DataNode node:
        """
        # Already initialized?
        datasets = self.datasets(subscan)
        if node.fullname in datasets:
            return
        # Detector data type known?
        if not node.dtype:
            # Detector data dtype not known at this point
            return
        # Detector data shape known?
        detector_shape = node.shape
        if not all(detector_shape):
            # Detector data shape not known at this point
            # TODO: this is why 0 cannot indicate variable length
            return

        # Create parent: NXdetector, NXpositioner or measurement
        device = self.device(subscan, node)
        parentname = dataset_proxy.normalize_nexus_name(device["device_name"])
        if device["device_type"] == "positioner":
            # Add as separate positioner group
            parentcontext = self.nxpositioner
            parentcontextargs = subscan, parentname
        elif device["device_name"]:
            # Add as separate detector group
            parentcontext = self.nxdetector
            parentcontextargs = subscan, parentname
        else:
            # Add to generic 'measurement' group
            parentcontext = self.nxmeasurement
            parentcontextargs = (subscan,)
        with parentcontext(*parentcontextargs) as parent:
            if parent is None:
                return
            # Save info associated to the device (not the specific dataset)
            for dset_name, value in device["device_info"].items():
                if dset_name in parent:
                    nexus.updateDataset(parent, dset_name, value)
                else:
                    nexus.nxCreateDataSet(parent, dset_name, value, None)
            parent = parent.name

        # Everything is ready to create the dataset
        scan_shape = self.scan_shape(subscan)
        scan_save_shape = self.scan_save_shape(subscan)
        order = self.order(len(scan_shape))
        dproxy = dataset_proxy.DatasetProxy(
            parent=parent,
            device=device,
            scan_shape=scan_shape,
            scan_save_shape=scan_save_shape,
            detector_shape=detector_shape,
            dtype=node.dtype,
            order=order,
            parentlogger=self.logger,
            filename=self.filename,
            filecontext=self.nxroot,
        )
        datasets[node.fullname] = dproxy
        self.logger.info("New data " + str(dproxy))

    def scan_size(self, subscan):
        """
        Number of points in the subscan (0 means variable-length)

        :param str subscan:
        :returns int:
        """
        # TODO: currently subscans always give 0 (npoints is not published in Redis)
        cache = self._redis_cache.get("scan_size", {})
        npoints = cache.get(subscan, None)
        if npoints is None:
            npoints = cache[subscan] = self.subscan_info_get(
                subscan, "npoints", default=0
            )
            self._redis_cache["scan_size"] = cache
        return npoints

    def scan_ndim(self, subscan):
        """
        Number of dimensions of the subscan

        :param str subscan:
        :returns int:
        """
        # TODO: currently subscans always give 1 (data_dim is not published in Redis)
        if self.scan_size(subscan) == 1:
            default = 0  # scalar
        else:
            default = 1  # vector
        return self.subscan_info_get(subscan, "data_dim", default)

    def scan_shape(self, subscan):
        """
        Shape of the subscan

        :param str subscan:
        :returns tuple:
        """
        ndim = self.scan_ndim(subscan)
        if ndim == 0:
            return tuple()
        elif ndim == 1:
            return (self.scan_size(subscan),)
        else:
            # Fast axis first
            s = [
                self.subscan_info_get(subscan, "npoints{}".format(i))
                for i in range(1, ndim + 1)
            ]
            if self.order(ndim) == "C":
                # Fast axis last
                s = s[::-1]
            return tuple(s)

    def order(self, ndim):
        """
        Data is published as a flat list in the order of
        nested scan loops (fast, slow1, slow2, ...).
        We need the order in which the final shape is filled.
        """
        return self._order[ndim]

    def scan_save_shape(self, subscan):
        """
        Potentially flattened `scan_shape`

        :param str subscan:
        :returns tuple:
        """
        if self.saveoptions["flat"]:
            if self.scan_ndim(subscan) == 0:
                return tuple()
            else:
                return (self.scan_size(subscan),)
        else:
            return self.scan_shape(subscan)

    def scan_save_ndim(self, subscan):
        """
        Potentially flattened scan_ndim

        :param str subscan:
        :returns int:
        """
        return len(self.scan_save_shape(subscan))

    def _fetch_data(self, node, last=False):
        """
        Get new data (if any) from a data node and create/insert/link in HDF5.

        :param bliss.data.node.DataNode node:
        :param bool last: this will be the last fetch
        """
        # Get/initialize dataset proxy
        dproxy = self._dataset_proxy(node)
        if dproxy is None:
            return

        # Copy/link new data
        if node.type == "channel":
            # newdata = copied from Redis
            newdata = self._fetch_new_redis_data(dproxy, node)
            if newdata.shape[0]:
                dproxy.add_internal(newdata)
        else:
            try:
                if dproxy.is_internal:
                    raise RuntimeError("already has some copied data")
                else:
                    # newdata = references to external files (no copy)
                    newdata, file_format = self._fetch_new_references(dproxy, node)
            except RuntimeError as e:
                if dproxy.is_external:
                    dproxy.logger.debug(
                        "data is not copied because we already have external data references"
                    )
                else:
                    dproxy.logger.debug(
                        "data is copied instead of linked because {}".format(
                            repr(str(e))
                        )
                    )
                    # newdata = copied from external files
                    newdata = self._fetch_new_external_data(dproxy, node)
                    if newdata.shape[0]:
                        dproxy.add_internal(newdata)
            else:
                if newdata and file_format:
                    dproxy.add_external(newdata, file_format)

        # Log progress of this DataNode
        subscan = self.subscan(node)
        npoints_expected = self.scan_size(subscan)
        dproxy.log_progress(npoints_expected, last=last)

    def _ensure_dataset_existance(self, node):
        """
        Make sure the dataset associated with this node is created (if not already done).

        :param bliss.data.node.DataNode node:
        :param bool last: this will be the last fetch
        :returns DatasetProxy or None:
        """
        dproxy = self._dataset_proxy(node)
        if dproxy is None:
            msg = "{} dataset not initialized".format(repr(node.fullname))
            self.logger.warning(msg)
        else:
            dproxy.ensure_existance()
        return dproxy

    def _dataset_proxy(self, node):
        """
        Get dataset proxy associated with node (initialize when needed).

        :param bliss.data.node.DataNode node:
        :returns DatasetProxy or None:
        """
        # Initialize HDF5 dataset handle when not already done
        dproxy = None
        subscan = self.subscan(node)
        if subscan:
            self._create_dataset_proxy(subscan, node)
            datasets = self.datasets(subscan)
            dproxy = datasets.get(node.fullname, None)
        return dproxy

    def _ensure_same_length(self, subscan):
        """
        Ensure the all datasets of a subscan have the same number of points.

        :param str subscan:
        """
        expand = self.saveoptions["expand_variable_length"]
        scanshape = self.scan_save_shape(subscan)
        scanndim = len(scanshape)
        scanshapes = []
        for dproxy in self.datasets(subscan).values():
            scanshapes.append(dproxy.current_scan_save_shape)
        if expand:
            scanshape = tuple(max(lst) if any(lst) else 1 for lst in zip(*scanshapes))
        else:
            scanshape = tuple(
                min(i for i in lst if i) if any(lst) else 1 for lst in zip(*scanshapes)
            )
        for dproxy in self.datasets(subscan).values():
            dproxy.reshape(scanshape, None)

    def _fetch_new_redis_data(self, dproxy, node):
        """
        Get a copy of the new data provided by a 'channel' data node.

        :param DatasetProxy dproxy:
        :param bliss.data.channel.ChannelDataNode node:
        :returns numpy.ndarray:
        """
        icurrent = dproxy.npoints
        # list(num or numpy.ndarray)
        # return numpy.array(node.get(icurrent, -1))
        return node.get_as_array(icurrent, -1)

    def _fetch_new_references(self, dproxy, node):
        """
        Get references to the new data provided by the node.

        :param DatasetProxy dproxy:
        :param bliss.data.node.DataNode node:
        :returns lst, str: references, file_format
        :raises RuntimeError:
        """
        icurrent = dproxy.npoints
        # e.g node: bliss.data.lima.LimaImageChannelDataNode
        #     dataview: bliss.data.lima.LimaImageChannelDataNode.LimaDataView
        dataview = node.get(icurrent, -1)
        uris = []
        file_format0 = None
        imgidx = list(range(dataview.from_index, dataview.last_index))
        if not imgidx:
            return uris, file_format0
        try:
            files = dataview._get_filenames(node.info, *imgidx)
        except Exception as e:
            dproxy.logger.debug(e)
            return uris, file_format0
        for uri, suburi, index, file_format in files:
            # Validate format
            if file_format:
                file_format = file_format.lower()
                if file_format in ("edf", "edfgz", "edfconcat"):
                    file_format = "edf"
            self._validate_external_format(dproxy, file_format)
            if file_format0:
                if file_format != file_format0:
                    raise RuntimeError(
                        "Cannot handle mixed file formats (got {} instead of {})".format(
                            file_format, file_format0
                        )
                    )
            else:
                file_format0 = file_format
            # Full uri
            if suburi:
                if file_format == "hdf5":
                    uri = self._hdf5_full_uri(uri, suburi)
                else:
                    raise RuntimeError(
                        "Sub-uri of format {} not supported".format(repr(file_format))
                    )
                if not uri:
                    continue
            else:
                if file_format == "hdf5":
                    continue
            # All is ok: append uri
            uris.append((uri, index))
        return uris, file_format0

    def _fetch_new_external_data(self, dproxy, node):
        """
        Get a copy of the new data provided by a data node that publishes references.

        :param DatasetProxy dproxy:
        :param bliss.data.node.DataNode node:
        :returns numpy.ndarray:
        """
        icurrent = dproxy.npoints
        # e.g node: bliss.data.lima.LimaImageChannelDataNode
        #     dataview: bliss.data.lima.LimaImageChannelDataNode.LimaDataView
        dataview = node.get(icurrent, -1)
        lst = []
        try:
            for data in dataview:
                lst.append(data)
        except Exception as e:
            # Data is not ready (yet): RuntimeError, ValueError, ...
            dproxy.logger.debug("Data is not ready (yet): {}".format(e))
        return numpy.array(lst)

    def _hdf5_full_uri(self, uri, suburi):
        """
        Make sure the uri exists.

        :param str uri:
        :param str suburi:
        :returns str:
        """
        try:
            fulluri = uri + "::" + suburi
            with nexus.uriContext(fulluri, mode="r") as dset:
                return fulluri
        except Exception as e:
            logger.debug("HDF5 '{}::{}' error ({})".format(uri, suburi, e))
        return ""

    def _validate_external_format(self, dproxy, file_format):
        """
        Make sure this file format can be or is allowed to be
        used in datasets with external data.

        :param DatasetProxy dproxy:
        :param str file_format:
        :raises RuntimeError:
        """
        if file_format not in ("edf", "hdf5"):
            raise RuntimeError("Unknown file format {}".format(repr(file_format)))
        if file_format == "hdf5":
            if not self.saveoptions["allow_external_hdf5"]:
                raise RuntimeError("External HDF5 disabled by writer")
            elif not nexus.HASVIRTUAL:
                # We could let this pass but then the copying will
                # be done at the end instead of during the scan
                raise RuntimeError("External HDF5 not used due to missing VDS support")
        else:
            if not self.saveoptions["allow_external_nonhdf5"]:
                raise RuntimeError(
                    "External {} disabled by writer".format(repr(file_format))
                )

    def datasets(self, subscan):
        """
        :param str subscan:
        """
        self._datasets[subscan] = ret = self._datasets.get(subscan, {})
        return ret

    def datasetproxy(self, subscan, fullname):
        """
        :param str subscan:
        :param str fullname:
        :returns DatasetProxy:
        """
        return self.datasets(subscan)[fullname]

    def positioner_iter(self, subscan, onlyprincipals=True, onlymasters=True):
        """
        Yields all positioner dataset handles

        :param str subscan:
        :param bool onlyprincipals: only the principal value of each positioner
        :param bool onlymasters: only positioners that are master in the acquisition chain
        :returns str, DatasetProxy: fullname and dataset handles
        """
        for fullname, dproxy in self.datasets(subscan).items():
            if dproxy.type == "positioner":
                if onlyprincipals and dproxy.data_type != "principal":
                    continue
                if onlymasters and dproxy.master_index < 0:
                    continue
                yield fullname, dproxy

    def detector_iter(self, subscan):
        """
        Yields all dataset handle except for positioners

        :param str subscan:
        :returns str, DatasetProxy: fullname and dataset handle
        """
        for fullname, dproxy in self.datasets(subscan).items():
            if dproxy.type != "positioner":
                yield fullname, dproxy

    @property
    def positioners_start(self):
        positioners = self.instrument_info.get("positioners", {})
        units = self.instrument_info.get("positioners_units", {})
        return positioners, units

    @property
    def positioners_dial_start(self):
        positioners = self.instrument_info.get("positioners_dial", {})
        units = self.instrument_info.get("positioners_units", {})
        return positioners, units

    @property
    def positioners_end(self):
        return {}, {}

    @property
    def positioners_dial_end(self):
        return {}, {}

    def _save_positioners(self, subscan):
        """
        Save fixed snapshots of motor positions.

        :param str subscan:
        """
        # Positions at the beginning of the scan
        positioners, units = self.positioners_start
        self._save_positioners_snapshot(
            subscan, positioners, units, "_start", overwrite=False
        )
        self._save_positioners_snapshot(
            subscan, positioners, units, "", overwrite=False
        )
        positioners, units = self.positioners_dial_start
        self._save_positioners_snapshot(
            subscan, positioners, units, "_dial_start", overwrite=False
        )

        # Positions at the end of the scan
        positioners, units = self.positioners_end
        self._save_positioners_snapshot(
            subscan, positioners, units, "_end", overwrite=True
        )
        positioners, units = self.positioners_dial_end
        self._save_positioners_snapshot(
            subscan, positioners, units, "_dial_end", overwrite=True
        )

        # Links to NXpositioners (moving during the scan)
        for fullname, dproxy in self.positioner_iter(
            subscan, onlyprincipals=False, onlymasters=False
        ):
            with self.nxpositioners(subscan) as parent:
                if parent is None:
                    return
                with dproxy.open() as dset:
                    if dset is None:
                        continue
                    linkname = dproxy.linkname
                    if linkname in parent:
                        del parent[linkname]
                    nexus.nxCreateDataSet(parent, linkname, dset, None)

    def _save_positioners_snapshot(
        self, subscan, positions, units, suffix, overwrite=False
    ):
        """
        Save fixed snapshot of motor positions.

        :param dict positions: name:position
        :param dict units: name:unit
        :param str suffix: output suffix
        :param bool overwrite: goes for values and attributes
        """
        if not positions:
            return
        with self.nxpositioners(subscan, suffix=suffix) as nxpositioners:
            if nxpositioners is None:
                return
            self.logger.info(
                "Save motor positions snapshot " + repr(nexus.h5Name(nxpositioners))
            )
            for mot, pos in positions.items():
                unit = units.get(mot, None)
                exists = mot in nxpositioners
                if exists:
                    dset = nxpositioners[mot]
                    if overwrite:
                        dset[()] = pos
                    if unit and ("units" not in dset.attrs or overwrite):
                        dset.attrs["units"] = unit
                else:
                    if unit:
                        attrs = {"units": unit}
                    else:
                        attrs = {}
                    nexus.nxCreateDataSet(nxpositioners, mot, pos, attrs)
