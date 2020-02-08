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
Configurable Nexus writer listening to Redis events of a scan
"""

import os
import re
import datetime
import logging
from contextlib import contextmanager
from . import scan_writer_base
from ..io import nexus
from ..utils import scan_utils


logger = logging.getLogger(__name__)


cli_saveoptions = dict(scan_writer_base.cli_saveoptions)
cli_saveoptions["stackmca"] = {
    "dest": "stack_mcas",
    "action": "store_true",
    "help": "Merged MCA datasets in application definition",
}


def default_saveoptions():
    return {
        options["dest"]: options["action"] == "store_false"
        for options in cli_saveoptions.values()
    }


class NexusScanWriterConfigurable(scan_writer_base.NexusScanWriterBase):
    """
    Listen to events of a particular scan and write the result in Nexus format.
    Extra information in Redis needed (see `devices.redis_info` and `..data.generator`).
    """

    def __init__(self, *args, **kwargs):
        """
        The locks are only used to protect nxroot creation/updating.
        This is not needed for the nxentry because only one writer
        will create/update it.

        :param args: see `NexusScanWriterBase`
        :param kwargs: see `NexusScanWriterBase`
        """
        for option, default in default_saveoptions().items():
            kwargs[option] = kwargs.get(option, default)
        if kwargs.get("parentlogger") is None:
            kwargs["parentlogger"] = logger
        super().__init__(*args, **kwargs)
        self._applications = {"appxrf": self._save_application_xrf}

    @property
    def config_writer(self):
        """
        Writer information not published by the core Bliss library
        """
        return self.get_info("nexuswriter", default={})

    @property
    def instrument_name(self):
        return self.config_writer.get("instrument", "")

    @property
    def config_devices(self):
        """
        Extra information on devices
        """
        return self.config_writer.get("devices", {})

    @property
    def config_technique(self):
        """
        Technique information belonging to this scan
        """
        return self.config_writer.get("technique", {})

    @property
    def technique_name(self):
        """
        Applications definitions defined for this scan
        """
        return self.config_technique.get("name", "")

    @property
    def applications(self):
        """
        Applications definitions defined for this scan
        """
        return self.config_technique.get("applications", {})

    @property
    def plots(self):
        """
        NXdata signals
        """
        return self.config_technique.get("plots", {})

    @property
    def plotselect(self):
        """
        Default NXdata group
        """
        return self.config_technique.get("plotselect", "")

    def _select_plot_signals(self, subscan, plotname, items=None, ndim=-1, grid=False):
        """
        Select plot signals as specified in the static beamline configuration.

        :param Subscan subscan:
        :param str plotname:
        :param list items: signal names for plotting
        :param int ndim: detector dimensions in case no items
        :param bool grid: preserve scan shape
        :returns dict: (str, tuple): (str, [(name, value, attrs)])
        """
        if items:
            signaldict = {}
            for configname in items:
                for fullname, dproxy in self.detector_iter(subscan):
                    if self._matching_fullname(configname, fullname):
                        self._add_signal(plotname, grid, dproxy, signaldict)
        else:
            signaldict = super()._select_plot_signals(
                subscan, plotname, ndim=ndim, grid=grid
            )
        return signaldict

    def _init_subscan(self, subscan):
        """
        Things that can already be saved right after
        receiving the new subscan event.

        :param Subscan subscan:
        """
        super()._init_subscan(subscan)
        self._create_master_links(subscan)

    def _finalize_subscan(self, subscan):
        """
        Save final subscan data.

        :param Subscan subscan:
        """
        super()._finalize_subscan(subscan)
        self._save_applications(subscan)

    def mca_iter(self, subscan):
        """
        Yields all principal mca dataset handle

        :param Subscan subscan:
        :returns str, DatasetProxy: fullname and dataset handle
        """
        for fullname, dproxy in subscan.datasets.items():
            if dproxy.device_type == "mca" and dproxy.data_type == "principal":
                yield fullname, dproxy

    def _get_application(self, nxapplidef, attr, default=None):
        """
        Get parameter from application definition

        :param dict nxapplidef:
        :param str attr:
        """
        ret = nxapplidef.get(attr, None)
        if ret is None:
            self.logger.warning(
                "Application definition incomplete ({} is missing)".format(repr(attr))
            )
            ret = default
        return ret

    def _device_type(self, node):
        """
        Get device type from data node

        :param bliss.data.node.DataNode node:
        :returns str:
        """
        device_type = self._device_type_from_applications(node)
        if not device_type:
            device_type = "unknown{}D".format(len(node.shape))
        return device_type

    def _device_type_from_applications(self, node):
        """
        Get device type from application definitions

        :param bliss.data.node.DataNode node:
        :returns str:
        """
        for name, nxapplidef in self.applications.items():
            name = name.lower()
            if name == "xrf":
                devicetype = self._device_type_xrf(node, nxapplidef)
            if devicetype:
                return devicetype
        return ""

    def _device_type_xrf(self, node, xrfapplidef):
        """
        Get device type from the XRF application definition

        :param bliss.data.node.DataNode node:
        :param dict xrfapplidef:
        :returns str:
        """
        ndim = len(node.shape)
        if ndim == 1:
            return "mca"
        fullname = node.fullname
        if ndim == 0:
            counternames = [
                self._get_application(xrfapplidef, "I0"),
                self._get_application(xrfapplidef, "It"),
            ]
            if any(
                self._matching_fullname(configname, fullname)
                for configname in counternames
            ):
                return "sensor"
        return ""

    @contextmanager
    def nxapplication(self, subscan, name, definition_name):
        """
        Yields the NXsubentry instance (h5py.Group) or None
        when NXentry is missing

        :param Subscan subscan:
        :param str name: name of the NXsubentry
        :param str definition_name: Nexus application definition
        """
        with self.nxentry(subscan) as nxentry:
            if nxentry is None:
                yield None
                return
            # Find nxapplication (when existing)
            for child in nxentry:
                nxsubentry = nxentry[child]
                if (
                    child == name
                    and nexus.isNxClass(nxsubentry, "NXsubentry")
                    and definition_name == nxsubentry.attrs.get("definition", None)
                ):
                    break
            else:
                nxsubentry = None
            if nxsubentry is None:
                # Create nxapplication
                ret = self._nxapplication_create_args(name, definition_name)
                if ret is None:
                    yield None
                    return
                args, kwargs = ret
                nxsubentry = nexus.nxSubEntry(nxentry, *args, **kwargs)
            yield nxsubentry

    def _nxapplication_create_args(self, name, definition_name):
        """
        Arguments for application nxSubEntry creation

        :param str name:
        :param str definition_name:
        :returns tuple, dict:
        """
        start_timestamp = self.get_info("start_timestamp")
        if not start_timestamp:
            self._h5missing("start_timestamp")
            return None
        start_time = datetime.datetime.fromtimestamp(start_timestamp)
        datasets = {"definition": definition_name}
        args = (name,)
        kwargs = {"start_time": start_time, "datasets": datasets}
        return args, kwargs

    def _save_applications(self, subscan):
        """
        Save a Nexus application definitions

        :param Subscan subscan:
        """
        for name, nxapplidef in self.applications.items():
            nxclass = nxapplidef.get("class").lower()
            save_app = self._applications.get(nxclass)
            if save_app is not None:
                save_app(subscan, name, nxapplidef)

    def _save_application_xrf(self, subscan, name, xrfapplidef):
        """
        Save XRF Nexus application definition

        :param Subscan subscan:
        :param str name:
        :param dict xrfapplidef:
        """
        with self.nxapplication(subscan, name, "APPxrf") as nxsubentry:
            if nxsubentry is None:
                return
            self.logger.info("Create 'APPxrf' Nexus application")
            self._save_application_i0(subscan, nxsubentry, xrfapplidef)
            self._save_application_it(subscan, nxsubentry, xrfapplidef)
            self._save_application_mca(subscan, nxsubentry, xrfapplidef)
            nexus.updated(nxsubentry, final=True, parents=False)

    def _save_application_i0(self, subscan, parent, nxapplidef):
        """
        Add beam monitor to the application

        :param h5py.Group parent: application subentry
        :param dict nxapplidef:
        """
        I0configname = self._get_application(nxapplidef, "I0")
        I0appliname = "i0"
        self._save_application_link(subscan, parent, I0configname, I0appliname)

    def _save_application_it(self, subscan, parent, nxapplidef):
        """
        Add sample transmission to the application

        :param h5py.Group parent: application subentry
        :param dict nxapplidef:
        """
        Itconfigname = self._get_application(nxapplidef, "It")
        Itappliname = "it"
        self._save_application_link(subscan, parent, Itconfigname, Itappliname)

    def _save_application_mca(self, subscan, parent, xrfapplidef):
        """
        Add MCA's tp the application

        :param Subscan subscan:
        :param h5py.Group parent: application subentry
        :param dict xrfapplidef:
        """
        # Mca names from the beamline configuration
        confignames = self._get_application(xrfapplidef, "mca", [])
        if not confignames:
            # All MCA's when not specified
            for fullname, dproxy in self.mca_iter(subscan):
                confignames.append(fullname)
            confignames = sorted(confignames)
        if not confignames:
            self.logger.warning("Application definition incomplete (no mca's found)")
            return

        # Links or concatenate?
        concatenate = self.saveoptions["stack_mcas"]
        aslinks = len(confignames) == 1 or not concatenate
        if aslinks:
            method = self._save_application_links
        else:
            method = self._save_application_merged

        # Add mca
        withsuffix = len(confignames) > 1 and not concatenate
        if withsuffix:
            mcaapplinamefmt = "mca{:02d}"
        else:
            mcaapplinamefmt = "mca"
        method(
            subscan,
            parent,
            confignames,
            mcaapplinamefmt,
            devicetype="mca",
            datatype="principal",
        )

        if withsuffix:
            mcaapplinamefmt = "elapsed_time_mca{:02d}"
        else:
            mcaapplinamefmt = "elapsed_time"
        method(
            subscan,
            parent,
            confignames,
            mcaapplinamefmt,
            devicetype="mca",
            datatype="realtime",
        )

        if withsuffix:
            mcaapplinamefmt = "live_time_mca{:02d}"
        else:
            mcaapplinamefmt = "live_time"
        method(
            subscan,
            parent,
            confignames,
            mcaapplinamefmt,
            devicetype="mca",
            datatype="livetime",
        )

    def _save_application_merged(
        self, subscan, parent, confignames, appliname, virtual=True, **kwargs
    ):
        """
        Add datasets to an application as one single dataset,
        virtual or merged copy.

        :param Subscan subscan:
        :param h5py.Dataset parent: application subentry
        :param list(str) confignames: names specified in the beamline
                                      static configuration
        :param str applifmt: format for application definition name
        :param bool virtual: virtual dataset or copy
        :param **kwargs: see `_iter_fullnames`
        """
        if not confignames or appliname in parent:
            return
        uris = []
        for configname in confignames:
            notfoundmsg = "Application definition incomplete ({} not found for {})".format(
                repr(configname), repr(appliname)
            )
            for fullname in self._iter_fullnames(
                subscan, configname, notfoundmsg=notfoundmsg, **kwargs
            ):
                dproxy = subscan.datasets[fullname]
                with dproxy.open() as dset:
                    if not uris:
                        value = {
                            "data": uris,
                            "fillvalue": dset.fillvalue,
                            "axis": 0,
                            "newaxis": True,
                            "virtual": virtual,
                        }
                        attrs = dset.attrs
                    uris.append(nexus.getUri(dset))
        if uris:
            nexus.nxCreateDataSet(parent, appliname, value, attrs)

    def _save_application_links(self, subscan, parent, confignames, applifmt, **kwargs):
        """
        Add dataset links to an application.

        :param Subscan subscan:
        :param h5py.Dataset parent: application subentry
        :param list(str) confignames: names specified in the beamline
                                      static configuration
        :param str applifmt: format for application definition name
        :param **kwargs: see `_iter_fullnames`
        :returns list(str): Redis fullnames
        """
        if not confignames:
            return
        for i, configname in enumerate(confignames):
            appliname = applifmt.format(i)
            self._save_application_link(
                subscan, parent, configname, appliname, **kwargs
            )

    def _save_application_link(self, subscan, parent, configname, appliname, **kwargs):
        """
        Link to a dataset in the application definition

        :param h5py.Group parent: application subentry
        :param str configname: name specified in the beamline
                               static configuration
        :param str appliname: name in the Nexus application definition
        :param **kwargs: see `_iter_fullnames`
        """
        if not configname or appliname in parent:
            return
        notfoundmsg = "Application definition incomplete ({} not found for {})".format(
            repr(configname), repr(appliname)
        )
        for fullname in self._iter_fullnames(
            subscan, configname, notfoundmsg=notfoundmsg, **kwargs
        ):
            dproxy = subscan.datasets[fullname]
            nexus.createLink(parent, appliname, dproxy.path)

    def _matching_fullname(self, configname, fullname):
        """
        Checks whether a Redis node's full name is referred to
        by name from the writer configuration.

        Examples:
            "iodet" refers to "simulation_diode_controller:iodet"
            "xmap1:det0" refers to "xmap1:realtime_det0"
            "xmap1:det0" refers to "simxmap1:spectrum_det0"

        :param str configname: from the writer configuration
        :param str fullname: node.fullname
        """
        seps = r"[\.:]"
        configparts = re.split(seps, configname)
        fullparts = re.split(seps, fullname)
        return all(
            pfull.endswith(pconfig)
            for pfull, pconfig in zip(fullparts[::-1], configparts[::-1])
        )

    def _iter_fullnames(
        self, subscan, configname, devicetype=None, datatype=None, notfoundmsg=None
    ):
        """
        Yield all Redis node's full names referred to by a name
        from the writer configuration.

        :param Subscan subscan:
        :param str configname: name specified in the beamline
                               static configuration
        :param str devicetype: device type
        :param str datatype: data type
        :param str notfoundmsg:
        :yields str: Redis node fullname
        """
        incomplete = True
        for fullname, dproxy in self.detector_iter(subscan):
            if self._matching_fullname(configname, fullname):
                if (devicetype == dproxy.device_type or not devicetype) and (
                    datatype == dproxy.data_type or not datatype
                ):
                    incomplete = False
                    yield fullname
        if incomplete and notfoundmsg:
            self.logger.warning(notfoundmsg)

    @property
    def master_files(self):
        """
        :returns list(str): 
        """
        return list(scan_utils.scan_master_filenames(self.node).values())

    def _create_master_links(self, subscan):
        """
        Links to the scan's NXentry

        :param Subscan subscan:
        """
        filenames = self.master_files
        if not filenames:
            return
        with self.nxentry(subscan) as nxentry:
            if nxentry is None:
                return
            self.logger.info("Create scan links in masters ...")
            linkname, ext = os.path.splitext(os.path.basename(nxentry.file.filename))
            linkname += ": " + nxentry.name[1:]
            for filename in filenames:
                with self.nxroot(filename=filename) as nxroot:
                    if nxroot is None:
                        continue
                    if linkname in nxroot:
                        continue
                    self.logger.info(
                        "Create link {} in master {}".format(
                            repr(linkname), repr(filename)
                        )
                    )
                    lnk = nexus.createLink(nxroot, linkname, nxentry)
