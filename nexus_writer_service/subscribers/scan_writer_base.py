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
from bliss.data.node import get_node
from . import devices
from . import dataset_proxy
from . import reference_proxy
from . import base_subscriber
from ..io import nexus
from ..utils import scan_utils
from ..utils.logging_utils import CustomLogger
from ..utils.array_order import Order
from .nxdata_proxy import NXdataProxy


logger = logging.getLogger(__name__)


cli_saveoptions = {
    "keepshape": {
        "dest": "flat",
        "action": "store_false",
        "help": "Keep shape of multi-dimensional grid scans",
    },
    "multivalue_positioners": {
        "dest": "multivalue_positioners",
        "action": "store_true",
        "help": "Group positioners values",
    },
    "enable_external_nonhdf5": {
        "dest": "allow_external_nonhdf5",
        "action": "store_true",
        "help": "Enable external non-hdf5 files like edf (ABSOLUTE LINK!)",
    },
    "disable_external_hdf5": {
        "dest": "allow_external_hdf5",
        "action": "store_false",
        "help": "Disable external hdf5 files (virtual datasets)",
    },
    "copy_non_external": {
        "dest": "copy_non_external",
        "action": "store_true",
        "help": "Copy data instead of saving the uri when external linking is disabled",
    },
    "resource_profiling": {
        "dest": "resource_profiling",
        "action": "store_true",
        "help": "Enable resource profiling",
    },
}


def default_saveoptions():
    return {
        options["dest"]: options["action"] == "store_false"
        for options in cli_saveoptions.values()
    }


class Subscan(object):
    def __init__(self, subscriber, node, parentlogger=None):
        """
        :param BaseSubscriber subscriber:
        :param DataNode node:
        :param Logger parentlogger:
        """
        self.name = node.name
        self.db_name = node.db_name
        self.fullname = node.fullname
        self.node_type = node.node_type

        self.enabled = True
        self.datasets = {}  # bliss.data.node.DataNode.fullname -> DatasetProxy
        self.references = {}  # bliss.data.node.DataNode.fullname -> ReferenceProxy
        self._info_cache = {}  # cache calls to self.get_info
        if parentlogger is None:
            parentlogger = logger
        self.logger = CustomLogger(parentlogger, self)

        # Associate resources with greenlet
        glt = subscriber._greenlet
        try:
            nodes = glt._subscan_nodes
        except AttributeError:
            nodes = glt._subscan_nodes = {}
        nodes[self.db_name] = node
        self._subscriber = subscriber

    def hasnode(self, node):
        """
        :param DataNode node:
        """
        return node.db_name.startswith(self.db_name)

    def __repr__(self):
        return self.db_name

    def __str__(self):
        return "{} ({})".format(self.name, "ENABLED" if self.enabled else "DISABLED")

    @property
    def node(self):
        if self._subscriber._local_greenlet:
            return self._subscriber._greenlet._subscan_nodes[self.db_name]
        else:
            return get_node(self.node_type, self.db_name)

    def get_info(self, key, default=None, cache=False):
        """
        Get from the node's info dictionary.
        Try subscribers's info dictionary when key is missing.

        :param str key:
        :param default: never cached
        :param bool cache: cache this value when retrieved
        """
        if cache:
            try:
                return self._info_cache[key]
            except KeyError:
                pass
        try:
            result = self.node.info[key]
        except KeyError:
            result = self._subscriber.get_info(key, default=default, cache=cache)
        if cache:
            self._info_cache[key] = result
        return result


class NexusScanWriterBase(base_subscriber.BaseSubscriber):
    """
    Listen to events of a particular scan and write the result in Nexus format.
    No configuration needed.
    """

    def __init__(
        self,
        db_name,
        node_type=None,
        resource_profiling=False,
        parentlogger=None,
        **saveoptions,
    ):
        """
        :param str db_name:
        :param str node_type:
        :param Logger parentlogger:
        :param bool resource_profiling:
        :param saveoptions:
        """
        if parentlogger is None:
            parentlogger = logger
        super().__init__(
            db_name,
            node_type=node_type,
            parentlogger=parentlogger,
            resource_profiling=resource_profiling,
        )

        # Save options
        for option, default in default_saveoptions().items():
            saveoptions[option] = saveoptions.get(option, default)
        saveoptions["short_names"] = True
        saveoptions["expand_variable_length"] = True
        saveoptions["hold_file_open"] = True
        saveoptions["enable_file_locking"] = True
        saveoptions["swmr"] = False
        self.saveoptions = saveoptions
        self.saveorder = Order("C")
        # self.publishorder = Order("C")  # not true for snake scans
        # self.plotorder = Order("C")  # currently the same as saveorder
        self._h5flush_task_period = 0.5  # flushing blocks the gevent loop

        # Cache
        self._filename = None
        self._subscans = set()  # set(Subscan)
        self._devices = {}  # str -> dict(subscan.name:dict)
        self._nxroot = {}  # for recursive calling
        self._nxentry = None  # for recursive calling
        self._first_event = True
        self._nxentry_created = False

    def _listen_event_loop(self, **kwargs):
        """
        Listen to Redis events
        """
        if not self.save:
            self.logger.info("No saving requested")
            return
        if not self.filename:
            raise RuntimeError("No filename specified")
        if self.saveoptions["hold_file_open"]:
            with self.nxroot() as nxroot:
                kwargs["nxroot"] = nxroot
                super()._listen_event_loop(**kwargs)
        else:
            super()._listen_event_loop(**kwargs)

    def _event_loop_initialize(self, **kwargs):
        """
        Executed at the start of the event loop
        """
        self._first_event = True
        super()._event_loop_initialize(**kwargs)
        self.logger.info(
            "Start writing to {} with options ({}) {}".format(
                repr(self.filename), self.__class__.__name__, self.saveoptions
            )
        )

    def _event_loop_finalize(self, **kwargs):
        """
        Executed at the end of the event loop
        """
        with self._capture_finalize_exceptions():
            self._finalize_hdf5()
        self.log_progress("Finished writing to {}".format(repr(self.filename)))
        super()._event_loop_finalize(**kwargs)

    def _register_event_loop_tasks(self, nxroot=None, **kwargs):
        """
        Tasks to be run periodically after succesfully processing a Redis event
        """
        super()._register_event_loop_tasks(**kwargs)
        if nxroot is not None:
            self._periodic_tasks.append(
                base_subscriber.PeriodicTask(nxroot.flush, self._h5flush_task_period)
            )

    def _finalize_hdf5(self):
        """
        Finish writing
        """
        if self._exception_is_fatal:
            self.logger.info("Finalization skipped due fatal errors")
            return
        else:
            self.logger.info("Finalize writing to {}".format(repr(self.filename)))

        self.logger.info("Fetch last data")
        for node in self._nodes:
            with self._capture_finalize_exceptions():
                self._fetch_data(node, last=True)

        # Skip because fix length scans can have variable data points
        # self.logger.info(
        #    "Ensure all dataset have the same number of points"
        # )
        #
        # for subscan in self._enabled_subscans:
        #    with self._capture_finalize_exceptions():
        #        self._ensure_same_length(subscan)

        self.logger.info("Link external data (VDS or raw)")
        for node in self._nodes:
            with self._capture_finalize_exceptions():
                self._ensure_dataset_existance(node)

        self.logger.info("Save detector metadata")
        skip = set()
        for node in self._nodes:
            self._fetch_node_metadata(node, skip)

        for subscan in self._enabled_subscans:
            self._finalize_subscan(subscan)
            self._mark_done(subscan)

    @contextmanager
    def _capture_finalize_exceptions(self):
        try:
            yield
        except BaseException as e:
            self._set_state(self.STATES.FAULT, e)
            self.logger.error(
                "Captured finalization exception:\n{}".format(traceback.format_exc())
            )

    def get_subscan_info(self, subscan, key, default=None, cache=False):
        """
        Get from the subscan's info dictionary.
        Try scan's info dictionary when key is missing.

        :param Subscan subscan:
        :param str key: subscan node's info key
        :param default:
        :param bool cache:
        """
        if subscan is None:
            return self.get_info(key, default=default, cache=cache)
        else:
            return subscan.get_info(key, default=default, cache=cache)

    @property
    def save(self):
        """
        Saving intended for this scan?
        """
        return (
            self.get_info("save", False)
            and self.get_info("data_writer", "null") == "nexus"
        )

    @property
    def filename(self):
        """
        HDF5 file name for data
        """
        if not self._filename:
            self._filename = scan_utils.scan_filename(self.node)
        return self._filename

    @property
    def uris(self):
        filename = self.filename
        ret = {}
        for subscan in self._subscans:
            name = self._nxentry_name(subscan)
            ret[name.split(".")[-1]] = filename + "::/" + name
        return [v for _, v in sorted(ret.items())]

    def subscan_uri(self, subscan):
        return self.filename + "::/" + self._nxentry_name(subscan)

    @property
    def config_devices(self):
        return {}

    @property
    def devices(self):
        """
        Maps subscan name to a dictionary of devices,
        which maps fullname to device info. Ordered
        according to position in acquisition chain.
        """
        if not self._devices:
            self._devices = devices.device_info(
                self.config_devices,
                self.info,
                self.scan_ndim(None),
                short_names=self.saveoptions["short_names"],
                multivalue_positioners=self.saveoptions["multivalue_positioners"],
            )
        return self._devices

    @property
    def scan_number(self):
        return self.get_info("scan_nb")

    @property
    def _expected_subscans(self):
        """
        Subscan names for which there are devices defined.
        Ordered according to position in acquisition chain.
        """
        return list(sorted(self.devices.keys()))

    @property
    def _enabled_subscans(self):
        for subscan in self._subscans:
            if subscan.enabled:
                yield subscan

    @property
    def _enabled_and_expected_subscans(self):
        expected = self._expected_subscans
        for subscan in self._enabled_subscans:
            if subscan.name in expected:
                yield subscan

    def device(self, subscan, node):
        """
        Get device information of the node belonging to the subscan

        :param Subscan subscan:
        :param bliss.data.node.DataNode node:
        :returns dict:
        """
        fullname = node.fullname
        subdevices = self.devices[subscan.name]
        device = subdevices.get(fullname, None)
        if device is None:
            device = devices.update_device(subdevices, fullname)
        if not device["device_type"]:
            device["device_type"] = self._device_type(node)
        return device

    def _device_type(self, node):
        """
        Get device type from data node

        :param bliss.data.node.DataNode node:
        :returns str:
        """
        return "unknown{}D".format(len(node.shape))

    @contextmanager
    def nxroot(self, filename=None):
        """
        Yields the NXroot instance (h5py.File) or None
        when information is missing
        """
        if not filename:
            filename = self.filename
            if not filename:
                self._h5missing("filename")
        nxroot = self._nxroot.get(filename, None)
        if nxroot is None:
            if filename:
                try:
                    with nexus.nxRoot(filename, **self._nxroot_kwargs) as nxroot:
                        try:
                            self._nxroot[filename] = nxroot
                            yield nxroot
                        finally:
                            self._nxroot[filename] = None
                except OSError as e:
                    if nxroot is None and nexus.isLockedError(e):
                        self._exception_is_fatal = True
                        raise RuntimeError(nexus.lockedErrorMessage(filename)) from None
                    else:
                        raise
            else:
                yield None
        else:
            yield nxroot

    @property
    def _nxroot_kwargs(self):
        # TODO: h5py issue #1641
        # rootattrs = {
        #    "publisher": self.get_info("publisher", "Bliss"),
        #    "publisher_version": self.get_info("publisher_version", None),
        # }
        rootattrs = {"publisher_version": self.get_info("publisher_version", None)}
        return {
            "mode": "a",
            "enable_file_locking": self.saveoptions["enable_file_locking"],
            "swmr": self.saveoptions["swmr"],
            "rootattrs": rootattrs,
        }

    @contextmanager
    def _modify_nxroot(self, filename=None):
        with self.nxroot(filename=filename) as nxroot:
            if nxroot is None:
                yield nxroot
            else:
                with nxroot.protect():
                    yield nxroot

    @property
    def has_write_permissions(self):
        """
        This process has permission to write/create file and/or directory
        """
        filename = self.filename
        if os.path.exists(filename):
            # Check whether we can write to the file
            return os.access(filename, os.W_OK)
        else:
            # Check whether we can create the file (and possibly subdirs)
            dirname = os.path.dirname(filename)
            while dirname and dirname != os.sep:
                if os.path.exists(dirname):
                    if os.path.isdir(dirname):
                        return os.access(dirname, os.W_OK)
                    else:
                        return False
                else:
                    dirname = os.path.dirname(dirname)
            else:
                return False

    @contextmanager
    def nxentry(self, subscan):
        """
        :param Subscan subscan:

        Yields the NXentry instance (h5py.Group) or None
        when information is missing
        """
        with self.nxroot() as nxroot:
            if nxroot is None:
                yield None
                return
            if self._nxentry is None:
                nxentry = self._get_nxentry(nxroot, subscan)
                try:
                    self._nxentry = nxentry
                    yield nxentry
                finally:
                    self._nxentry = None
            else:
                yield self._nxentry

    def _get_nxentry(self, nxroot, subscan):
        """
        Create/get NXentry of subscan

        :param h5py.File nxroot:
        :param Subscan subscan:
        """
        name = self._nxentry_name(subscan)
        if not name:
            return None
        nxentry = nxroot.get(name, None)
        if nxentry is None:
            if not subscan.enabled:
                return None
            kwargs = self._nxentry_create_args()
            if not kwargs:
                return None
            try:
                nxentry = nexus.nxEntry(nxroot, name, raise_on_exists=True, **kwargs)
            except nexus.NexusInstanceExists:
                self._exception_is_fatal = True
                raise RuntimeError(
                    f"More than one writer is writing to {self.filename}"
                )
                # subscan.enabled = False
            else:
                self._nxentry_created = True
            self._on_subscan_creation(subscan)
        elif not self._nxentry_created:
            self._exception_is_fatal = True
            raise RuntimeError(f"Scan {name} already exists in {self.filename}")
        return nxentry

    def _on_subscan_creation(self, subscan):
        """
        Actions taken right after subscan NXentry creation

        :param Subscan subscan:
        """
        uri = repr(self.subscan_uri(subscan))
        name = repr(subscan.name)
        if subscan.enabled:
            msg = "Start writing subscan {} to {}"
            msg = msg.format(name, uri)
            self.logger.info(msg)
        else:
            msg = "Writing subscan {} is disabled destination {} exists (probably another writer exists for this session)"
            msg = msg.format(name, uri)
            self._set_state(self.STATES.FAULT, msg)

    def _nxentry_name(self, subscan):
        """
        Name of the NXentry associated with a subscan

        :param Subscan subscan:
        :returns str:
        """
        try:
            # The subscan name x.1, x.2, ... depends on the order
            # in which the
            i = self._expected_subscans.index(subscan.name)
        except ValueError:
            self._h5missing("subscan " + repr(subscan.name))
            return None
        try:
            name = scan_utils.scan_name(self.node, i + 1)
        except AttributeError as e:
            self._h5missing(str(e))
            return None
        return name

    def _nxentry_create_args(self):
        """
        Arguments for nxEntry creation

        :returns dict:
        """
        start_timestamp = self.get_info("start_timestamp")
        if not start_timestamp:
            self._h5missing("start_timestamp")
            return None
        title = self.get_info("title")
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
        Yields the measurement instance (h5py.Group) or None
        when NXentry is missing
        """
        with self.nxentry(subscan) as nxentry:
            if nxentry is None:
                yield None
            else:
                yield nexus.nxCollection(nxentry, "measurement")

    @contextmanager
    def nxnotes(self, subscan):
        """
        Yields the notes instance (h5py.Group) or None
        when NXentry is missing
        """
        with self.nxentry(subscan) as nxentry:
            if nxentry is None:
                yield None
            else:
                yield nexus.nxCollection(nxentry, "notes")

    def _h5missing(self, variable):
        """
        :param str variable:
        """
        self.logger.debug(
            "HDF5 group not created yet ({} missing)".format(repr(variable))
        )

    @property
    def plots(self):
        """
        NXdata signals
        """
        plots = self.flintplots
        for ndim in self.detector_ndims:
            plots["plot{}D".format(ndim)] = {"ndim": ndim}
        return plots

    @property
    def flintplots(self):
        display_extra = self.get_info("_display_extra", default={})
        items = display_extra.get("displayed_channels", None)
        if items is None:
            items = display_extra.get("plotselect", None)
        if items:
            return {"plotselect": {"items": items, "grid": True}}
        else:
            return {}

    @property
    def plotselect(self):
        """
        Default NXdata group
        """
        return ""

    def _create_plots(self, subscan):
        """
        Create default plot in Nexus structure

        :param Subscan subscan:
        """
        with self.nxentry(subscan) as nxentry:
            if nxentry is None:
                return
            default = None
            plots = self.plots
            if plots:
                positioners = [
                    dproxy
                    for _, dproxy in self.positioner_iter(
                        subscan, onlyprincipals=True, onlymasters=True
                    )
                ]
                plotselect = self.plotselect
                subscan.logger.info(f"Create {len(plots)} plots")
            else:
                subscan.logger.info("No plots defined for saving")
            for plotname, plotparams in plots.items():
                if plotname in nxentry:
                    subscan.logger.warning(
                        f"Cannot create plot {repr(plotname)} (name already exists)"
                    )
                    continue
                nxproxy = self._create_nxdata_proxy(subscan, plotname, **plotparams)
                if not nxproxy:
                    nxproxy.logger.warning("Not created (no signals)")
                    continue
                nxproxy.add_axes(positioners, self.saveorder)
                default = nxproxy.save(nxentry, default, plotselect)
            # Default plot
            with self._modify_nxroot():
                if default is None:
                    nexus.markDefault(nxentry)
                else:
                    nexus.markDefault(default)

    def _create_nxdata_proxy(self, subscan, plotname, ndim=-1, grid=False):
        """
        Select plot signals based on detector dimensions.

        :param Subscan subscan:
        :param str plotname:
        :param int ndim: detector dimensions
        :param bool grid: preserve scan shape
        :returns NXdataProxy:
        """
        nxproxy = NXdataProxy(plotname, parentlogger=subscan.logger)
        if ndim >= 0:
            for fullname, dproxy in self.detector_iter(subscan):
                if dproxy.detector_ndim == ndim:
                    nxproxy.add_signal(dproxy, grid)
        return nxproxy

    def _mark_done(self, subscan):
        """
        The NXentry is completed

        :param Subscan subscan:
        """
        if self.state == self.STATES.FAULT:
            subscan.logger.warning("Data NOT marked as DONE in HDF5")
            return
        with self.nxentry(subscan) as nxentry:
            if nxentry is not None:
                with self._modify_nxroot():
                    nexus.updated(nxentry, final=True, parents=True)
                subscan.logger.info("Data marked as DONE in HDF5")

    @property
    def instrument_name(self):
        return ""

    @property
    def positioner_info(self):
        return self.get_info("positioners", {})

    @property
    def motors(self):
        return list(self.positioner_info.get("positioners_start", {}).keys())

    @contextmanager
    def nxinstrument(self, subscan):
        """
        Yields the NXinstrument instance (h5py.Group) or None
        when NXentry is missing

        :param Subscan subscan:
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

        :param Subscan subscan:
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

        :param Subscan subscan:
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

        :param Subscan subscan:
        """
        with self.nxinstrument(subscan) as nxinstrument:
            if nxinstrument is None:
                yield None
            else:
                yield nexus.nxCollection(nxinstrument, "positioners" + suffix)

    def _init_subscan(self, subscan):
        """
        Things that can already be saved right after
        receiving the new subscan event.

        :param Subscan subscan:
        """
        self._save_positioners(subscan)

    def _finalize_subscan(self, subscan):
        """
        Save final subscan data.

        :param Subscan subscan:
        """
        with self._capture_finalize_exceptions():
            self._save_positioners(subscan)
        with self._capture_finalize_exceptions():
            self._create_plots(subscan)
        with self._capture_finalize_exceptions():
            self._fetch_subscan_metadata(subscan)
        with self._capture_finalize_exceptions():
            self._fetch_subscan_notes(subscan)

    @property
    def current_bytes(self):
        """
        Total bytes (data-only) of all subscans
        """
        nbytes = 0
        for subscan in self._subscans:
            for dproxy in subscan.datasets.values():
                if dproxy is not None:
                    nbytes += dproxy.current_bytes
        return nbytes

    @property
    def progress(self):
        """
        Mininal/maximal scan data progress
        """
        lst = []
        for subscan in self._subscans:
            for dproxy in list(subscan.datasets.values()):
                if dproxy is not None:
                    lst.append(dproxy.progress)
        if lst:
            return min(lst), max(lst)
        else:
            return 0, 0

    @property
    def progress_string(self):
        """
        Mininal/maximal scan data progress
        """
        progress = []
        for subscan in self._subscans:
            lst = []
            for dproxy in list(subscan.datasets.values()):
                if dproxy is not None:
                    lst.append(dproxy.progress_string)
            if lst:

                def getprogress(tpl):
                    return tpl[1]

                subscan_progress = "{}-{}".format(
                    min(lst, key=getprogress)[0], max(lst, key=getprogress)[0]
                )
            else:
                subscan_progress = "0pts-0pts"
            progress.append((subscan.name, subscan_progress))
        if progress:
            if len(progress) == 1:
                return progress[0][1]
            else:
                return " ".join([name + ":" + s for name, s in progress])
        else:
            return "0pts-0pts"

    def log_progress(self, msg=None):
        data = dataset_proxy.format_bytes(self.current_bytes)
        progress = self.progress_string
        duration = self.duration
        if msg:
            self.logger.info("{} ({} {} {})".format(msg, progress, data, duration))
        else:
            self.logger.info(" {} {} {}".format(progress, data, duration))

    @property
    def info_string(self):
        data = dataset_proxy.format_bytes(self.current_bytes)
        state = self.state.name
        progress = self.progress_string
        start = self.starttime.strftime("%Y-%m-%d %H:%M:%S")
        end = self.endtime
        if end:
            end = end.strftime("%Y-%m-%d %H:%M:%S")
        else:
            end = "not finished"
        duration = self.duration
        return "{} {} {} {}, start: {}, end: {}".format(
            state, progress, data, duration, start, end
        )

    @property
    def detector_ndims(self):
        """
        All detector dimensions
        """
        ret = set()
        for subscan in self._subscans:
            for dproxy in subscan.datasets.values():
                if dproxy is not None:
                    ret.add(dproxy.detector_ndim)
        return ret

    def _process_event(self, event_type, node, event_data):
        """
        Process event belonging to this scan
        """
        if self._first_event:
            # The NEW_NODE event for the scan node is no longer
            # emitted on the scan node itself so fake it here
            self._event_new_node(self.node)
            self._first_event = False
        if event_type == event_type.NEW_NODE:
            self._event_new_node(node)
        elif event_type == event_type.NEW_DATA:
            self._event_new_data(node, event_data)
        else:
            event_info = event_type.name, node.type, node.name, node.fullname
            self.logger.debug("Untreated event: {}".format(event_info))

    def _event_new_node(self, node):
        """
        Creation of a new Redis node
        """
        name = repr(node.name)
        if node.type in ["scan", "scan_group"]:
            self.logger.debug("Start scan " + name)
            self._event_start_scan(node)
        elif node.type == "channel":
            self.logger.debug("New channel " + name)
            self._event_new_datanode(node)
        elif node.type == "node_ref_channel":
            self.logger.debug("New reference channel " + name)
            self._event_new_datanode(node)
        elif node.type == "lima":
            self.logger.debug("New Lima " + name)
            self._event_new_datanode(node)
        elif node.parent.type in ["scan", "scan_group"]:
            self.logger.debug("New subscan " + name)
            self._event_new_subscan(node)
        else:
            self.logger.debug(
                "New {} node event on {} not treated".format(repr(str(node.type)), name)
            )

    def _event_new_subscan(self, node):
        """
        :param node bliss.data.node.DataNodeContainer:
        """
        subscan = Subscan(self, node, parentlogger=self.logger)
        self.logger.info("New subscan " + repr(subscan.name))
        if subscan.name not in self._expected_subscans:
            self._log_unexpected_subscan(subscan)
            # subscan.enabled = False
            # self._set_state(self.STATES.FAULT, msg)
        self._subscans.add(subscan)
        self._init_subscan(subscan)

    def _log_unexpected_subscan(self, subscan):
        msg = "Subscan {} not one of the expected subscans {}".format(
            repr(subscan.name), self._expected_subscans
        )
        self.logger.warning(msg)

    def _event_new_data(self, node, event_data):
        """
        Creation of a new data node
        """
        # New data in an existing Redis node
        name = repr(node.fullname)
        if node.type == "channel":
            self._fetch_data(node, event_data=event_data)
        elif node.type == "node_ref_channel":
            self._fetch_data(node, event_data=event_data)
        elif node.type == "lima":
            self._fetch_data(node, event_data=event_data)
        else:
            self.logger.warning(
                "New {} data for {} not treated".format(repr(str(node.type)), name)
            )

    def _event_start_scan(self, scan):
        """
        Scan has started

        :param ScanNode scan:
        """
        title = self.get_info("title", "")
        self.logger.info("title = " + repr(title))
        if not self.has_write_permissions:
            self._exception_is_fatal = True
            raise RuntimeError("Cannot write to {}".format(self.filename))

    def _event_new_datanode(self, node):
        """
        New data node is created

        :param bliss.data.node.DataNode node:
        """
        # Node will appear in HDF5 but not
        # necessarily with data (dset.shape[0] == 0)
        self._nodes.append(node)
        self._node_proxy(node)

    @property
    def is_scan_group(self):
        return self.node.type == "scan_group"

    def _node_proxy(self, node):
        """
        Get node proxy associated with node (create when needed).
        The subscan to which the node belongs too must be known,
        expected and enabled.

        :param bliss.data.node.DataNode node:
        :returns DatasetProxy or None:
        """
        if node.type == "node_ref_channel":
            return self._reference_proxy(node)
        else:
            return self._dataset_proxy(node)

    def _dataset_proxy(self, node):
        """
        Get dataset proxy associated with node (create when needed).
        The subscan to which the node belongs too must be known,
        expected and enabled.

        :param bliss.data.node.DataNode node:
        :returns DatasetProxy or None:
        """
        dproxy = None
        subscan = self._datanode_subscan(node)
        if subscan is None:
            # unknown, unexpected or disabled
            return dproxy
        # Proxy already initialized?
        datasets = subscan.datasets
        dproxy = datasets.get(node.fullname)
        if dproxy is not None:
            return dproxy
        # Already fully initialized in Redis?
        data_info = self._detector_data_info(node)
        if not data_info:
            return dproxy

        # Create parent: NXdetector, NXpositioner or measurement
        device = self.device(subscan, node)
        parentname = dataset_proxy.normalize_nexus_name(device["device_name"])
        if device["device_type"] in ("positioner", "positionergroup"):
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
                return dproxy
            # Save info associated to the device (not this specific dataset)
            nexus.dicttonx(device["device_info"], parent, update=True)
            parent = parent.name

        # Everything is ready to create the dataset
        scan_shape = self.scan_shape(subscan)
        scan_save_shape = self.scan_save_shape(subscan)
        dproxy = dataset_proxy.DatasetProxy(
            filename=self.filename,
            parent=parent,
            filecontext=self.nxroot,
            device=device,
            scan_shape=scan_shape,
            scan_save_shape=scan_save_shape,
            saveorder=self.saveorder,
            publishorder=self.saveorder,
            parentlogger=subscan.logger,
            **data_info,
        )
        datasets[node.fullname] = dproxy
        self._add_to_dataset_links(subscan, dproxy)
        subscan.logger.debug("New data node " + str(dproxy))
        return dproxy

    def _reference_proxy(self, node):
        """
        Get reference proxy associated with node (create when needed).
        The subscan to which the node belongs too must be known,
        expected and enabled.

        :param bliss.data.node.DataNode node:
        :returns ReferenceProxy or None:
        """
        rproxy = None
        subscan = self._datanode_subscan(node)
        if subscan is None:
            # unknown, unexpected or disabled
            return rproxy
        # Already initialized?
        references = subscan.references
        rproxy = references.get(node.fullname)
        if rproxy is not None:
            return rproxy

        # Scans can have subscans so we don't know
        # how many references to expect.
        # scan_shape = self.scan_shape(subscan)
        # nreferences = dataset_proxy.shape_to_size(scan_shape)
        #
        # If we want links to scans in /x.y/dependencies(@NXcollection):
        # parent = "/" + self._nxentry_name(subscan) + "/dependencies"
        rproxy = reference_proxy.ReferenceProxy(
            filename=self.filename,
            parent="/",
            filecontext=self.nxroot,
            nreferences=0,
            parentlogger=subscan.logger,
        )
        references[node.fullname] = rproxy
        subscan.logger.debug("New reference node " + str(rproxy))
        return rproxy

    def _datanode_subscan(self, node):
        """
        Get the subscan name to which this node belongs to
        when subscan is known, expected and enabled.

        :param bliss.data.node.DataNode node:
        :returns Subscan:
        """
        for subscan in self._subscans:
            if subscan.hasnode(node):
                break
        else:
            subscans = [subscan.fullname for subscan in self._subscans]
            self.logger.warning(
                "data node {} does not belong to any of the subscans {}".format(
                    repr(node.fullname), subscans
                )
            )
            return None
        if not subscan.enabled:
            self.logger.warning(
                "Writing of subscan {} is disabled (probably a concurrent writer)".format(
                    repr(subscan.name)
                )
            )
            return None
        if subscan.name not in self._expected_subscans:
            self._log_unexpected_subscan(subscan)
            return None
        return subscan

    def scan_size(self, subscan):
        """
        Number of points in the subscan (0 means variable-length)

        :param Subscan subscan:
        :returns int:
        """
        if subscan is None:
            return self.get_info("npoints", cache=True)
        # TODO: currently subscans always give 0 (npoints is not published in Redis)
        return self.get_subscan_info(subscan, "npoints", default=0, cache=True)

    def scan_ndim(self, subscan):
        """
        Number of dimensions of the subscan

        :param Subscan subscan:
        :returns int:
        """
        # TODO: currently subscans always give 1 (data_dim is not published in Redis)
        if self.scan_size(subscan) == 1:
            default = 0  # scalar
        else:
            default = 1  # vector
        return self.get_subscan_info(subscan, "data_dim", default, cache=True)

    def scan_shape(self, subscan):
        """
        Shape of the subscan

        :param Subscan subscan:
        :returns tuple:
        """
        ndim = self.scan_ndim(subscan)
        if ndim == 0:
            return tuple()
        elif ndim == 1:
            return (self.scan_size(subscan),)
        else:
            # Fast axis first
            s = tuple(
                self.get_subscan_info(subscan, "npoints{}".format(i), cache=True)
                for i in range(1, ndim + 1)
            )
            if self.saveorder.order == "C":
                # Fast axis last
                s = s[::-1]
            return s

    def scan_save_shape(self, subscan):
        """
        Potentially flattened `scan_shape`

        :param Subscan subscan:
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

        :param Subscan subscan:
        :returns int:
        """
        return len(self.scan_save_shape(subscan))

    def _fetch_data(self, node, event_data=None, last=False):
        """
        Get new data (if any) from a data node and create/insert/link in HDF5.

        :param bliss.data.node.DataNode node:
        :param EventData event_data:
        :param bool last: this will be the last fetch
        """
        # Skip when no data expected
        if not self._node_data_saved(node):
            if last:
                self.logger.info(f"no data to be saved for node {repr(node.fullname)}")
            return
        # Get/initialize dataset or reference proxy
        nproxy = self._node_proxy(node)
        if nproxy is None:
            if last:
                self._set_state(
                    self.STATES.FAULT,
                    f"node {repr(node.fullname)} lacks initialization info",
                )
            return
        # Get data or references (if any)
        self._fetch_new_data(node, nproxy, event_data=event_data)
        # Progress
        nproxy.log_progress(expect_complete=last)

    def _fetch_new_data(self, node, nproxy, event_data=None):
        """
        Get new data (if any) from a data node and create/insert/link in HDF5.

        :param bliss.data.node.DataNode node:
        :param EventData event_data:
        :param DatasetProxy or ReferenceProxy nproxy:
        """
        # Copy/link new data
        if node.type == "channel":
            # newdata = copied from Redis
            newdata = self._fetch_new_redis_data(nproxy, node, event_data=event_data)
            if newdata.shape[0]:
                nproxy.add_internal(newdata)
        elif node.type == "node_ref_channel":
            # newdata = copied from Redis
            newdata = self._fetch_new_redis_refdata(nproxy, node, event_data=event_data)
            if newdata:
                nproxy.add_references(newdata)
        else:
            # newdata = uri's and indices
            if nproxy.is_internal:
                external = False
            else:
                newdata, file_format = self._fetch_new_references(
                    nproxy, node, event_data=event_data
                )
                if not file_format:
                    return
                external, file_format = self._save_reference_mode(file_format)
            if external:
                if newdata:
                    nproxy.add_external(newdata, file_format)
            else:
                newdata = self._fetch_new_external_data(
                    nproxy, node, event_data=event_data
                )
                if newdata.shape[0]:
                    nproxy.add_internal(newdata)

    def _node_data_saved(self, node):
        """
        Check whether data associated for this node is actually saved.

        :param bliss.data.node.DataNode node:
        :returns bool or None: when None -> we don't know (yet)
        """
        if node.type == "lima":
            # MANUAL or missing: do not expect data
            # anything else: expect data
            return node.info.get("saving_mode", "MANUAL") != "MANUAL"
        else:
            return True

    def _detector_data_info(self, node):
        node_type = node.type
        if node_type == "lima":
            if not len(node.all_ref_data):
                return None
        data_expected = self._node_data_saved(node)

        # Number of images saved per file
        if node_type == "lima":
            external_images_per_file = node.images_per_file
        else:
            external_images_per_file = None

        # Detector data type known?
        dtype = node.dtype
        if data_expected and not dtype:
            # Detector data dtype not known at this point
            return None

        # Detector data shape known?
        detector_shape = node.shape
        if data_expected and not all(detector_shape):
            # Detector data shape not known at this point
            # TODO: this is why 0 cannot indicate variable length
            return None

        return {
            "dtype": dtype,
            "detector_shape": detector_shape,
            "external_images_per_file": external_images_per_file,
        }

    def _save_reference_mode(self, file_format):
        """
        Save reference as external link (or string uri) or copy data to hdf5
        """
        options = self.saveoptions
        if file_format == "hdf5":
            external = options["allow_external_hdf5"] and nexus.HASVIRTUAL
        elif file_format == "edf":
            external = options["allow_external_nonhdf5"]
        else:
            external = True
            file_format = None
        if not external and not options["copy_non_external"]:
            file_format = None
            external = True
        return external, file_format

    def _ensure_dataset_existance(self, node):
        """
        Make sure the dataset associated with this node is created (if not already done).

        :param bliss.data.node.DataNode node:
        """
        nproxy = self._node_proxy(node)
        if nproxy is None:
            msg = f"{repr(node.fullname)} not initialized (most likely missing info)"
            self._set_state(self.STATES.FAULT, msg)
        else:
            nproxy.ensure_existance()

    def _fetch_node_metadata(self, node, skip):
        """
        Get metadata (if any) from a data node and save in HDF5.

        :param bliss.data.node.DataNode node:
        :param set skip:
        """
        if node.type == "node_ref_channel":
            return
        # Get/initialize dataset proxy
        dproxy = self._dataset_proxy(node)
        if dproxy is None:
            self._set_state(
                self.STATES.FAULT, "no data for node {}".format(repr(node.fullname))
            )
            return
        # Add metadata to dataset
        metadata = {"units": node.info.get("unit")}
        dproxy.add_metadata(metadata, parent=False)
        # Add metadata to nxdetector/nxpositioner
        if dproxy.parent not in skip:
            if not dproxy.parent.endswith("measurement"):
                metadata = node.parent.info.get_all()
                metadata_keys = dproxy.device["metadata_keys"]
                if metadata_keys:
                    metadata = {
                        metadata_keys[k]: v
                        for k, v in metadata.items()
                        if k in metadata_keys
                    }
                dproxy.add_metadata(metadata, parent=True)
            skip.add(dproxy.parent)

    def _ensure_same_length(self, subscan):
        """
        Ensure the all datasets of a subscan have the same number of points.

        :param Subscan subscan:
        """
        expand = self.saveoptions["expand_variable_length"]
        scanshape = self.scan_save_shape(subscan)
        scanndim = len(scanshape)
        scanshapes = []
        for dproxy in subscan.datasets.values():
            scanshapes.append(dproxy.current_scan_save_shape)
        if expand:
            scanshape = tuple(max(lst) if any(lst) else 1 for lst in zip(*scanshapes))
        else:
            scanshape = tuple(
                min(i for i in lst if i) if any(lst) else 1 for lst in zip(*scanshapes)
            )
        for dproxy in subscan.datasets.values():
            dproxy.reshape(scanshape, None)

    def _fetch_new_redis_data(self, dproxy, node, event_data=None):
        """
        Get a copy of the new data provided by a 'channel' data node.

        :param DatasetProxy dproxy:
        :param bliss.data.channel.ChannelDataNode node:
        :param EventData event_data:
        :returns numpy.ndarray:
        """
        if event_data:
            return event_data.data
        else:
            return node.get_as_array(dproxy.npoints, -1)

    def _fetch_new_redis_refdata(self, rproxy, node, event_data=None):
        """
        Get new uris provided by a 'node_ref_channel' data node.

        :param ReferenceProxy rproxy:
        :param bliss.data.channel.ChannelDataNode node:
        :param EventData event_data:
        :returns lst(str):
        """
        result = []
        if event_data:
            nodes = event_data.data
        else:
            nodes = node.get(rproxy.npoints, -1)
        for refnode in nodes:
            if refnode.info.get("save"):
                result += scan_utils.scan_uris(refnode)
        return result

    def _fetch_new_references(self, dproxy, node, event_data=None):
        """
        Get references to the new data provided by the node.

        :param DatasetProxy dproxy:
        :param bliss.data.node.DataNode node:
        :param EventData event_data:
        :returns lst, str: references, file_format
        :raises RuntimeError:
        """
        if event_data:
            files = event_data.data
        else:
            files = []
            icurrent = dproxy.npoints
            # e.g node: bliss.data.lima.LimaImageChannelDataNode
            #     dataview: bliss.data.lima.LimaDataView
            dataview = node.get(icurrent, -1)
            if len(dataview):
                try:
                    files = dataview.all_image_references(saved=True)
                except Exception as e:
                    dproxy.logger.debug(f"Image not ready yet: {e}")
        # Create image URI's
        uris = []
        file_format0 = None
        for uri, suburi, index, file_format in files:
            # Validate format
            file_format = file_format.lower()
            if file_format.startswith("hdf5"):
                file_format = "hdf5"
                uri = uri + "::" + suburi
            if file_format0:
                if file_format != file_format0:
                    raise RuntimeError(
                        "Cannot handle mixed file formats (got {} instead of {})".format(
                            file_format, file_format0
                        )
                    )
            else:
                file_format0 = file_format
            uris.append((uri, index))
        return uris, file_format0

    def _fetch_new_external_data(self, dproxy, node, event_data=None):
        """
        Get a copy of the new data provided by a data node that publishes references.

        :param DatasetProxy dproxy:
        :param bliss.data.node.DataNode node:
        :param EventData event_data:
        :returns numpy.ndarray:
        """
        icurrent = dproxy.npoints
        # e.g node: bliss.data.lima.LimaImageChannelDataNode
        #     dataview: bliss.data.lima.LimaDataView
        dataview = node.get(icurrent, -1)
        lst = []
        try:
            for data in dataview:
                lst.append(data)
        except Exception as e:
            # Data is not ready (yet): RuntimeError, ValueError, ...
            dproxy.logger.debug("cannot get image data: {}".format(e))
        return numpy.array(lst)

    def positioner_iter(self, subscan, onlyprincipals=True, onlymasters=True):
        """
        Yields all positioner dataset handles

        :param Subscan subscan:
        :param bool onlyprincipals: only the principal value of each positioner
        :param bool onlymasters: only positioners that are master in the acquisition chain
        :returns str, DatasetProxy: fullname and dataset handles
        """
        for fullname, dproxy in subscan.datasets.items():
            if dproxy.device_type in ("positioner", "positionergroup"):
                if onlyprincipals and dproxy.data_type != "principal":
                    continue
                if onlymasters and dproxy.master_index < 0:
                    continue
                yield fullname, dproxy

    def detector_iter(self, subscan):
        """
        Yields all dataset handles except for positioners

        :param Subscan subscan:
        :returns str, DatasetProxy: fullname and dataset handle
        """
        for fullname, dproxy in subscan.datasets.items():
            if dproxy.device_type not in ("positioner", "positionergroup"):
                yield fullname, dproxy

    def _save_positioners(self, subscan):
        """
        Save fixed snapshots of motor positions.

        :param Subscan subscan:
        """
        info = self.positioner_info
        units = info.get("positioners_units", {})

        # Positions at the beginning of the scan
        positioners = info.get("positioners_start", {})
        subscan.logger.info("Save {} motor positions".format(len(positioners)))
        self._save_positioners_snapshot(
            subscan, positioners, units, "_start", overwrite=False
        )
        self._save_positioners_snapshot(
            subscan, positioners, units, "", overwrite=False
        )
        positioners = info.get("positioners_dial_start", {})
        self._save_positioners_snapshot(
            subscan, positioners, units, "_dial_start", overwrite=False
        )

        # Positions at the end of the scan
        positioners = info.get("positioners_end", {})
        self._save_positioners_snapshot(
            subscan, positioners, units, "_end", overwrite=True
        )
        positioners = info.get("positioners_dial_end", {})
        self._save_positioners_snapshot(
            subscan, positioners, units, "_dial_end", overwrite=True
        )

    def _save_positioners_snapshot(
        self, subscan, positions, units, suffix, overwrite=False
    ):
        """
        Save fixed snapshot of motor positions.

        :param Subscan subscan:
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

    def _add_to_dataset_links(self, subscan, dproxy):
        """
        Add links to this dataset.

        :param Subscan subscan:
        :param DatasetProxy dproxy:
        """
        self._add_to_measurement_group(subscan, dproxy)
        if dproxy.device_type in ("positioner", "positionergroup"):
            self._add_to_positioners_group(subscan, dproxy)

    def _add_to_measurement_group(self, subscan, dproxy):
        """
        Add link in measurement group.

        :param Subscan subscan:
        :param DatasetProxy dproxy:
        """
        with self.nxmeasurement(subscan) as measurement:
            if measurement is None:
                return
            if dproxy.parent == measurement.name:
                return
            linkname = dproxy.linkname
            if not linkname:
                dproxy.logger.warning("cannot be linked too")
                return
            linknames = [linkname]
            for linkname in linknames:
                if linkname in measurement:
                    self.logger.warning(
                        f"Duplicate name '{linkname}' in the measurement group. Rename this detector or positioner."
                    )
                else:
                    nexus.createLink(measurement, linkname, dproxy.path)

    def _add_to_positioners_group(self, subscan, dproxy):
        """
        Add link in positioners group.

        :param Subscan subscan:
        :param DatasetProxy dproxy:
        """
        with self.nxpositioners(subscan) as parent:
            if parent is None:
                return
            linkname = dproxy.linkname
            try:
                del parent[linkname]
            except KeyError:
                pass
            nexus.createLink(parent, linkname, dproxy.path)

    def _fetch_subscan_metadata(self, subscan):
        """
        Dump metadata for a subscan

        :param Subscan subscan:
        """
        with self.nxentry(subscan) as parent:
            if parent is None:
                return
            subscan.logger.info("Save scan metadata")
            info = self.info
            categories = set(info["scan_meta_categories"])
            categories -= {"positioners", "nexuswriter"}
            scan_meta = {}
            for cat in categories:
                add = info.get(cat, {})
                if set(add.keys()) - {"NX_class", "@NX_class"}:
                    scan_meta[cat] = add
            if scan_meta:
                try:
                    nexus.dicttonx(scan_meta, parent)
                except Exception as e:
                    self._set_state(self.STATES.FAULT, e)
                    subscan.logger.error(
                        "Scan metadata not saved due to exception:\n{}".format(
                            traceback.format_exc()
                        )
                    )
                else:
                    subscan.logger.info(
                        "Saved metadata categories: {}".format(list(scan_meta.keys()))
                    )

    def _fetch_subscan_notes(self, subscan):
        """
        Save notes for this subscan

        :param Subscan subscan:
        """
        notes = self.get_info("comments", [], cache=True)
        if not notes:
            return
        with self.nxnotes(subscan) as parent:
            if parent is None:
                return
            subscan.logger.info("Save scan notes")
            for i, note in enumerate(notes, 1):
                date = datetime.datetime.fromtimestamp(note["timestamp"])
                nexus.nxNote(
                    parent,
                    "note_{:02d}".format(i),
                    data=note["message"],
                    type="text/plain",
                    date=date,
                )
