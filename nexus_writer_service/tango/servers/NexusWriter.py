# -*- coding: utf-8 -*-
#
# This file is part of the NexusWriter project
#
# Code is maintained by the ESRF Data Analysis Unit.
#
# Original author: Wout de Nolf
#
# Copyright (c) 2015-2020 ESRF
#
# Distributed under the terms of the LGPL license.
# See LICENSE.txt for more info.

""" Bliss writer service

"""

# PyTango imports
import tango
from tango import DebugIt
from tango.server import run
from tango.server import Device
from tango.server import attribute, command
from tango.server import device_property
from tango import AttrQuality, DispLevel, DevState
from tango import AttrWriteType, PipeWriteType
import enum

# Additional import
# PROTECTED REGION ID(NexusWriter.additionnal_import) ENABLED START #
import gevent
import logging
import re
import os
import sys
import itertools
from tango import Attribute

from nexus_writer_service.patching import freeze_subprocess
import nexus_writer_service
from nexus_writer_service.subscribers import session_writer
from nexus_writer_service.subscribers.scan_writer_base import NexusScanWriterBase
from nexus_writer_service.utils import log_levels


def session_tango_state(state):
    SessionWriterStates = session_writer.NexusSessionWriter.STATES
    if state == SessionWriterStates.INIT:
        return DevState.INIT
    elif state == SessionWriterStates.ON:
        return DevState.ON
    elif state == SessionWriterStates.RUNNING:
        return DevState.RUNNING
    elif state == SessionWriterStates.OFF:
        return DevState.OFF
    elif state == SessionWriterStates.FAULT:
        return DevState.FAULT
    else:
        return DevState.UNKNOWN


def scan_tango_state(state):
    ScanWriterStates = NexusScanWriterBase.STATES
    if state == ScanWriterStates.INIT:
        return DevState.INIT
    elif state == ScanWriterStates.ON:
        return DevState.ON
    elif state == ScanWriterStates.OFF:
        return DevState.OFF
    elif state == ScanWriterStates.FAULT:
        return DevState.FAULT
    else:
        return DevState.UNKNOWN


def align_listofstrings(lst, alignsep=","):
    """Align a list of string on a separator
    """
    if not lst:
        return lst
    if alignsep == " ":
        parts = [re.sub(r"\s+", " ", s).strip().split(alignsep) for s in lst]
    else:
        parts = [s.split(alignsep) for s in lst]
    if len(lst) > 1:
        fmtlst = [
            "{{:>{}}}".format(max(map(len, items)))
            for items in itertools.zip_longest(*parts, fillvalue="")
        ]
        parts = [items + [""] * (len(fmtlst) - len(items)) for items in parts]
        fmtlst[-1] = fmtlst[-1].replace(">", "<")
        fmt = " ".join(fmtlst)
        return [s for items in parts for s in fmt.format(*items).split("\n")]
    else:
        return " ".join(parts[0]).split("\n")


def strftime(tm):
    """
    :param DateTime tm:
    :returns str:
    """
    if tm is None:
        return "not finished"
    else:
        return tm.strftime("%Y-%m-%d %H:%M:%S")


read_log_level = {
    logging.NOTSET: 0,
    logging.DEBUG: 1,
    logging.INFO: 2,
    logging.WARNING: 3,
    logging.ERROR: 4,
    logging.CRITICAL: 5,
}

write_log_level = {v: k for k, v in read_log_level.items()}


read_resource_profiling = {
    p: i for i, p in enumerate(NexusScanWriterBase.PROFILE_PARAMETERS)
}
write_resource_profiling = {i: p for p, i in read_resource_profiling.items()}


# PROTECTED REGION END #    //  NexusWriter.additionnal_import

__all__ = ["NexusWriter", "main"]


class Resource_profiling(enum.IntEnum):
    """Python enumerated type for Resource_profiling attribute."""

    OFF = 0
    CPU30 = 1
    CPU50 = 2
    CPU100 = 3
    WALL30 = 4
    WALL50 = 5
    WALL100 = 6
    MEM30 = 7
    MEM50 = 8
    MEM100 = 9


class Writer_log_level(enum.IntEnum):
    """Python enumerated type for Writer_log_level attribute."""

    NOTSET = 0
    DEBUG = 1
    INFO = 2
    WARN = 3
    ERROR = 4
    FATAL = 5


class Tango_log_level(enum.IntEnum):
    """Python enumerated type for Tango_log_level attribute."""

    NOTSET = 0
    DEBUG = 1
    INFO = 2
    WARN = 3
    ERROR = 4
    FATAL = 5


class NexusWriter(Device):
    """

    **Properties:**

    - Device Property
        session
            - Bliss session name
            - Type:'DevString'
        keepshape
            - Keep shape of multi-dimensional grid scans
            - Type:'DevBoolean'
        multivalue_positioners
            - Group positioners values
            - Type:'DevBoolean'
        enable_external_nonhdf5
            - Enable external non-hdf5 files like edf (ABSOLUTE LINK!)
            - Type:'DevBoolean'
        disable_external_hdf5
            - Disable external hdf5 files (virtual datasets)
            - Type:'DevBoolean'
        copy_non_external
            - Copy data instead of saving the uri when external linking is disabled
            - Type:'DevBoolean'
        noconfig
            - Do not use extra writer information from Redis
            - Type:'DevBoolean'
        stackmca
            - Merged MCA datasets in application definition
            - Type:'DevBoolean'
        required_disk_space
            - Minimum required disk space in MB to allow the writer to start
            - Type:'DevDouble'
    """

    # PROTECTED REGION ID(NexusWriter.class_variable) ENABLED START #

    def getfromself(self, name):
        """Get python attribute
        """
        v = getattr(self, name)
        if isinstance(v, Attribute):
            # Tango attribute
            return getattr(self.proxy, name)
        else:
            # Tango property or python attribute
            return v

    @property
    def saveoptions(self):
        """When an option is not a device property or attribute,
        use the hard-coded default.
        """
        saveoptions = session_writer.default_saveoptions()
        for name, info in session_writer.all_cli_saveoptions().items():
            if "action" in info:
                store_true = info["action"] == "store_true"
                try:
                    v = self.getfromself(name) == store_true
                except AttributeError:
                    continue
            else:
                try:
                    v = self.getfromself(name)
                except AttributeError:
                    continue
            if name == "resource_profiling":
                # isinstance(v, Resource_profiling) is not True ???
                v = write_resource_profiling[v]
            saveoptions[info["dest"]] = v
        return saveoptions

    # PROTECTED REGION END #    //  NexusWriter.class_variable

    # -----------------
    # Device Properties
    # -----------------

    session = device_property(dtype="DevString", mandatory=True)

    keepshape = device_property(dtype="DevBoolean", default_value=False)

    multivalue_positioners = device_property(dtype="DevBoolean", default_value=False)

    enable_external_nonhdf5 = device_property(dtype="DevBoolean", default_value=False)

    disable_external_hdf5 = device_property(dtype="DevBoolean", default_value=False)

    copy_non_external = device_property(dtype="DevBoolean", default_value=False)

    noconfig = device_property(dtype="DevBoolean", default_value=False)

    stackmca = device_property(dtype="DevBoolean", default_value=False)

    required_disk_space = device_property(dtype="DevDouble", default_value=200)

    # ----------
    # Attributes
    # ----------

    resource_profiling = attribute(
        dtype=Resource_profiling, access=AttrWriteType.READ_WRITE
    )

    writer_log_level = attribute(
        dtype=Writer_log_level, access=AttrWriteType.READ_WRITE
    )

    tango_log_level = attribute(dtype=Tango_log_level, access=AttrWriteType.READ_WRITE)

    scan_states = attribute(dtype=("DevState",), max_dim_x=10000)

    scan_uris = attribute(dtype=("DevString",), max_dim_x=10000)

    scan_names = attribute(dtype=("DevString",), max_dim_x=10000)

    scan_start = attribute(dtype=("DevString",), max_dim_x=10000)

    scan_end = attribute(dtype=("DevString",), max_dim_x=10000)

    scan_info = attribute(dtype=("DevString",), max_dim_x=10000)

    scan_duration = attribute(dtype=("DevString",), max_dim_x=10000)

    scan_progress = attribute(dtype=("DevString",), max_dim_x=10000)

    scan_states_info = attribute(dtype=("DevString",), max_dim_x=10000)

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        """Initialises the attributes and properties of the NexusWriter."""
        Device.init_device(self)
        # PROTECTED REGION ID(NexusWriter.init_device) ENABLED START #
        self.proxy = tango.DeviceProxy(self.get_name())
        self.session_writer = getattr(self, "session_writer", None)
        if self.session_writer is None:
            log_levels.init_tango_log_level(device=self)
            self.session_writer = session_writer.NexusSessionWriter(
                self.session, parentlogger=None, **self.saveoptions
            )
        self.start()
        # PROTECTED REGION END #    //  NexusWriter.init_device

    def always_executed_hook(self):
        """Method always executed before any TANGO command is executed."""
        # PROTECTED REGION ID(NexusWriter.always_executed_hook) ENABLED START #
        # PROTECTED REGION END #    //  NexusWriter.always_executed_hook

    def delete_device(self):
        """Hook to delete resources allocated in init_device.

        This method allows for any memory or other resources allocated in the
        init_device method to be released.  This method is called by the device
        destructor and by the device Init command.
        """
        # PROTECTED REGION ID(NexusWriter.delete_device) ENABLED START #
        self.session_writer.stop(successfull=True, wait=True, timeout=3)
        # PROTECTED REGION END #    //  NexusWriter.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_resource_profiling(self):
        # PROTECTED REGION ID(NexusWriter.resource_profiling_read) ENABLED START #
        """Return the resource_profiling attribute."""
        return read_resource_profiling[self.session_writer.resource_profiling]
        # PROTECTED REGION END #    //  NexusWriter.resource_profiling_read

    def write_resource_profiling(self, value):
        # PROTECTED REGION ID(NexusWriter.resource_profiling_write) ENABLED START #
        """Set the resource_profiling attribute."""
        self.session_writer.resource_profiling = write_resource_profiling[value]
        # PROTECTED REGION END #    //  NexusWriter.resource_profiling_write

    def read_writer_log_level(self):
        # PROTECTED REGION ID(NexusWriter.writer_log_level_read) ENABLED START #
        """Return the writer_log_level attribute."""
        return read_log_level[nexus_writer_service.logger.getEffectiveLevel()]
        # PROTECTED REGION END #    //  NexusWriter.writer_log_level_read

    def write_writer_log_level(self, value):
        # PROTECTED REGION ID(NexusWriter.writer_log_level_write) ENABLED START #
        """Set the writer_log_level attribute."""
        nexus_writer_service.logger.setLevel(write_log_level[value])
        # PROTECTED REGION END #    //  NexusWriter.writer_log_level_write

    def read_tango_log_level(self):
        # PROTECTED REGION ID(NexusWriter.tango_log_level_read) ENABLED START #
        """Return the tango_log_level attribute."""
        return read_log_level[log_levels.tango_get_log_level()]
        # PROTECTED REGION END #    //  NexusWriter.tango_log_level_read

    def write_tango_log_level(self, value):
        # PROTECTED REGION ID(NexusWriter.tango_log_level_write) ENABLED START #
        """Set the tango_log_level attribute."""
        log_levels.tango_set_log_level(write_log_level[value], device=self)
        # PROTECTED REGION END #    //  NexusWriter.tango_log_level_write

    def read_scan_states(self):
        # PROTECTED REGION ID(NexusWriter.scan_states_read) ENABLED START #
        """Return the scan_states attribute."""
        statedict = self.session_writer.scan_state()
        return list(map(scan_tango_state, statedict.values()))
        # PROTECTED REGION END #    //  NexusWriter.scan_states_read

    def read_scan_uris(self):
        # PROTECTED REGION ID(NexusWriter.scan_uris_read) ENABLED START #
        """Return the scan_uris attribute."""
        uscan = self.session_writer.scan_uri()
        lst = [f"{scan}:,{value}" for scan, value in uscan.items()]
        return align_listofstrings(lst)
        # PROTECTED REGION END #    //  NexusWriter.scan_uris_read

    def read_scan_names(self):
        # PROTECTED REGION ID(NexusWriter.scan_names_read) ENABLED START #
        """Return the scan_names attribute."""
        return list(self.session_writer.scan_names())
        # PROTECTED REGION END #    //  NexusWriter.scan_names_read

    def read_scan_start(self):
        # PROTECTED REGION ID(NexusWriter.scan_start_read) ENABLED START #
        """Return the scan_start attribute."""
        data = self.session_writer.scan_start()
        lst = [f"{scan}:,{strftime(value)}" for scan, value in data.items()]
        return align_listofstrings(lst)
        # PROTECTED REGION END #    //  NexusWriter.scan_start_read

    def read_scan_end(self):
        # PROTECTED REGION ID(NexusWriter.scan_end_read) ENABLED START #
        """Return the scan_end attribute."""
        data = self.session_writer.scan_end()
        lst = [f"{scan}:,{strftime(value)}" for scan, value in data.items()]
        return align_listofstrings(lst)
        # PROTECTED REGION END #    //  NexusWriter.scan_end_read

    def read_scan_info(self):
        # PROTECTED REGION ID(NexusWriter.scan_info_read) ENABLED START #
        """Return the scan_info attribute."""
        pscan = self.session_writer.scan_progress_info()
        lst = [
            f"{scan}:{subscan}:,{value}" if len(psubscan) > 1 else f"{scan}:,{value}"
            for scan, psubscan in pscan.items()
            for subscan, value in psubscan.items()
        ]
        return align_listofstrings(lst)
        # PROTECTED REGION END #    //  NexusWriter.scan_info_read

    def read_scan_duration(self):
        # PROTECTED REGION ID(NexusWriter.scan_duration_read) ENABLED START #
        """Return the scan_duration attribute."""
        dscan = self.session_writer.scan_duration()
        lst = [f"{scan}:,{value}" for scan, value in dscan.items()]
        return align_listofstrings(lst)
        # PROTECTED REGION END #    //  NexusWriter.scan_duration_read

    def read_scan_progress(self):
        # PROTECTED REGION ID(NexusWriter.scan_progress_read) ENABLED START #
        """Return the scan_progress attribute."""
        pscan = self.session_writer.scan_progress()
        lst = [
            f"{scan}:{subscan}:,{value}" if len(psubscan) > 1 else f"{scan}:,{value}"
            for scan, psubscan in pscan.items()
            for subscan, value in psubscan.items()
        ]
        return align_listofstrings(lst)
        # PROTECTED REGION END #    //  NexusWriter.scan_progress_read

    def read_scan_states_info(self):
        # PROTECTED REGION ID(NexusWriter.scan_states_info_read) ENABLED START #
        """Return the scan_states_info attribute."""
        data = self.session_writer.scan_state_info()
        lst = [
            f"{name}:,{scan_tango_state(state).name},{reason}"
            for name, (state, reason) in data.items()
        ]
        return align_listofstrings(lst)
        # PROTECTED REGION END #    //  NexusWriter.scan_states_info_read

    # --------
    # Commands
    # --------

    @DebugIt()
    def dev_state(self):
        # PROTECTED REGION ID(NexusWriter.State) ENABLED START #
        """
        This command gets the device state (stored in its device_state data member) and returns it to the caller.

        :return:'DevState'
        Device state
        """
        return session_tango_state(self.session_writer.state)
        # PROTECTED REGION END #    //  NexusWriter.State

    @DebugIt()
    def dev_status(self):
        # PROTECTED REGION ID(NexusWriter.Status) ENABLED START #
        """
        This command gets the device status (stored in its device_status data member) and returns it to the caller.

        :return:'ConstDevString'
        Device status
        """
        return self.session_writer.state_reason
        # PROTECTED REGION END #    //  NexusWriter.Status

    @command(dtype_in="DevString", doc_in="scan", dtype_out="DevState")
    @DebugIt()
    def scan_state(self, argin):
        # PROTECTED REGION ID(NexusWriter.scan_state) ENABLED START #
        """

        :param argin: 'DevString'
        scan_name

        :return:'DevState'
        """
        statedict = self.session_writer.scan_state(argin)
        return scan_tango_state(statedict.get(argin, None))
        # PROTECTED REGION END #    //  NexusWriter.scan_state

    @command(dtype_in="DevString", doc_in="scan  name", dtype_out="DevVarStringArray")
    @DebugIt()
    def scan_uri(self, argin):
        # PROTECTED REGION ID(NexusWriter.scan_uri) ENABLED START #
        """

        :param argin: 'DevString'
        scan

        :return:'DevVarStringArray'
        """
        uridict = self.session_writer.scan_uri(name=argin)
        return uridict.get(argin, [])
        # PROTECTED REGION END #    //  NexusWriter.scan_uri

    @command(dtype_in="DevString", doc_in="scan name", dtype_out="DevBoolean")
    @DebugIt()
    def scan_has_write_permissions(self, argin):
        # PROTECTED REGION ID(NexusWriter.scan_has_write_permissions) ENABLED START #
        """

        :param argin: 'DevString'

        :return:'DevBoolean'
        """
        return self.session_writer.scan_has_write_permissions(argin)
        # PROTECTED REGION END #    //  NexusWriter.scan_has_write_permissions

    @command(dtype_in="DevString", doc_in="scan name", dtype_out="DevBoolean")
    @DebugIt()
    def scan_exists(self, argin):
        # PROTECTED REGION ID(NexusWriter.scan_exists) ENABLED START #
        """

        :param argin: 'DevString'

        :return:'DevBoolean'
        """
        return self.session_writer.scan_exists(argin)
        # PROTECTED REGION END #    //  NexusWriter.scan_exists

    @command(dtype_in="DevString", doc_in="scan name")
    @DebugIt()
    def stop_scan(self, argin):
        # PROTECTED REGION ID(NexusWriter.stop_scan) ENABLED START #
        """
        Stop a scan writer gracefully (stops processing events and finalizes file writing).

        :param argin: 'DevString'
        scan name

        :return:None
        """
        self.session_writer.stop_scan_writer(argin, kill=False)
        # PROTECTED REGION END #    //  NexusWriter.stop_scan

    @command(dtype_in="DevString", doc_in="scan name")
    @DebugIt()
    def kill_scan(self, argin):
        # PROTECTED REGION ID(NexusWriter.kill_scan) ENABLED START #
        """
        Kill the scan writer greenlet

        :param argin: 'DevString'
        scan name

        :return:None
        """
        self.session_writer.stop_scan_writer(argin, kill=True)
        # PROTECTED REGION END #    //  NexusWriter.kill_scan

    @command()
    @DebugIt()
    def stop(self):
        # PROTECTED REGION ID(NexusWriter.stop) ENABLED START #
        """
        Stop accepting Redis events (start scan, stop scan). Running scan writers will never be stopped automatically (use ``stop_scan(scan_name)``).

        :return:None
        """
        self.session_writer.stop(successfull=True)
        # PROTECTED REGION END #    //  NexusWriter.stop

    @command()
    @DebugIt()
    def start(self):
        # PROTECTED REGION ID(NexusWriter.start) ENABLED START #
        """
        Start accepting Redis events (start scan, stop scan).

        :return:None
        """
        # Fill with device properties (attributes are already set)
        self.session_writer.update_saveoptions(**self.saveoptions)
        self.session_writer.start()
        # PROTECTED REGION END #    //  NexusWriter.start

    @command(dtype_in="DevString", doc_in="scan name", dtype_out="DevString")
    @DebugIt()
    def scan_state_reason(self, argin):
        # PROTECTED REGION ID(NexusWriter.scan_state_reason) ENABLED START #
        """
        The reason why this scan is in this state.

        :param argin: 'DevString'
        scan name

        :return:'DevString'
        """
        statedict = self.session_writer.scan_state_info(name=argin)
        return statedict.get(argin, (None, ""))[1]
        # PROTECTED REGION END #    //  NexusWriter.scan_state_reason

    @command(dtype_in="DevString", doc_in="absolute path")
    @DebugIt()
    def makedirs(self, argin):
        # PROTECTED REGION ID(NexusWriter.makedirs) ENABLED START #
        """
        Create directories recursively and do not complain when they exist already

        :param argin: 'DevString'

        :return:None
        """
        if not os.path.isabs(argin):
            raise ValueError("Path must be absolute")
        os.makedirs(argin, exist_ok=True)
        # PROTECTED REGION END #    //  NexusWriter.makedirs

    @command()
    @DebugIt()
    def purge_scans(self):
        # PROTECTED REGION ID(NexusWriter.purge_scans) ENABLED START #
        """
        Purge successfully finished scans

        :return:None
        """
        self.session_writer.purge_scan_writers(delay=False)
        # PROTECTED REGION END #    //  NexusWriter.purge_scans

    @command(dtype_in="DevString", doc_in="scan name", dtype_out="DevBoolean")
    @DebugIt()
    def scan_has_required_disk_space(self, argin):
        # PROTECTED REGION ID(NexusWriter.scan_has_required_disk_space) ENABLED START #
        """
        Check whether there is enough disk space for the scan

        :param argin: 'DevString'
        scan name

        :return:'DevBoolean'
        """
        return self.session_writer.scan_has_required_disk_space(argin)
        # PROTECTED REGION END #    //  NexusWriter.scan_has_required_disk_space


# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    """Main function of the NexusWriter module."""
    # PROTECTED REGION ID(NexusWriter.main) ENABLED START #

    # Enable gevents for the server
    kwargs.setdefault("green_mode", tango.GreenMode.Gevent)
    return run((NexusWriter,), args=args, **kwargs)
    # PROTECTED REGION END #    //  NexusWriter.main


if __name__ == "__main__":
    main()
