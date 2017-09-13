"""Python interface to handel API."""

from __future__ import absolute_import

import os
from collections import namedtuple

import numpy

from .error import check_error
from ._cffi import handel, ffi
from .parser import parse_xia_ini_file

__all__ = [
    "init",
    "init_handel",
    "exit",
    "new_detector",
    "get_num_detectors",
    "get_detectors",
    "get_detector_from_channel",
    "start_run",
    "stop_run",
    "get_spectrum_length",
    "get_spectrum",
    "get_spectrums",
    "is_channel_running",
    "is_running",
    "get_module_statistics",
    "get_statistics",
    "get_buffer_length",
    "get_buffer_full",
    "get_buffer",
    "buffer_done",
    "load_system",
    "save_system",
    "start_system",
    "enable_log_output",
    "disable_log_output",
    "set_log_output",
    "set_log_level",
    "close_log",
    "get_num_modules",
    "get_modules",
    "get_module_from_channel",
    "get_module_type",
    "get_module_interface",
    "get_module_channels",
    "get_grouped_channels",
    "get_channels",
    "set_acquisition_value",
    "get_acquisition_value",
    "remove_acquisition_value",
    "apply_acquisition_values",
    "get_handel_version",
]

MAX_STRING_LENGTH = 80


# Helpers

Stats = namedtuple("Stats", "realtime livetime triggers events icr ocr deadtime")


def to_bytes(arg):
    if isinstance(arg, bytes):
        return arg
    return arg.encode()


def to_buffer_id(bid):
    bid = to_bytes(bid.lower())
    if bid in (b"a", b"b"):
        return bid
    msg = "{!r} is not a valid buffer id"
    raise ValueError(msg.format(bid))


# Initializing handel


def init(*path):
    filename = to_bytes(os.path.join(*path))
    code = handel.xiaInit(filename)
    check_error(code)


def init_handel():
    code = handel.xiaInitHandel()
    check_error(code)


def exit():
    code = handel.xiaExit()
    check_error(code)


# Detectors


def new_detector(alias):
    alias = to_bytes(alias)
    code = handel.xiaNewDetector(alias)
    check_error(code)


def get_num_detectors():
    num = ffi.new("unsigned int *")
    code = handel.xiaGetNumDetectors(num)
    check_error(code)
    return num[0]


def get_detectors():
    n = get_num_detectors()
    arg = [ffi.new("char []", MAX_STRING_LENGTH) for _ in range(n)]
    code = handel.xiaGetDetectors(arg)
    check_error(code)
    return tuple(ffi.string(x).decode() for x in arg)


def get_detector_from_channel(channel):
    alias = ffi.new("char []", MAX_STRING_LENGTH)
    code = handel.xiaDetectorFromDetChan(channel, alias)
    check_error(code)
    return ffi.string(alias).decode()


# Not exposed

# int xiaAddDetectorItem(char *alias, char *name, void *value);
# int xiaModifyDetectorItem(char *alias, char *name, void *value);
# int xiaGetDetectorItem(char *alias, char *name, void *value);
# int xiaGetDetectors_VB(unsigned int index, char *alias);
# int xiaRemoveDetector(char *alias);


# Run control


def start_run(channel=None, resume=False):
    if channel is None:
        channel = -1  # All channels
    code = handel.xiaStartRun(channel, resume)
    check_error(code)


def stop_run(channel=None):
    if channel is None:
        channel = -1  # All channels
    code = handel.xiaStopRun(channel)
    check_error(code)


def get_spectrum_length(channel):
    length = ffi.new("unsigned long *")
    code = handel.xiaGetRunData(channel, b"mca_length", length)
    check_error(code)
    return length[0]


def get_spectrum(channel):
    length = get_spectrum_length(channel)
    array = numpy.zeros(length, dtype="uint32")
    data = ffi.cast("uint32_t *", array.ctypes.data)
    code = handel.xiaGetRunData(channel, b"mca", data)
    check_error(code)
    return array


def get_spectrums():
    """Return the spectrums for all enabled channels as a dictionary."""
    return {channel: get_spectrum(channel) for channel in get_channels()}


def is_channel_running(channel):
    running = ffi.new("short *")
    code = handel.xiaGetRunData(channel, b"run_active", running)
    check_error(code)
    return bool(running[0])


def is_running():
    """Return True if any channel is running, False otherwise."""
    return any(map(is_channel_running, get_channels()))


# Statistics


def get_module_statistics(module):
    # Get raw data
    channels = get_module_channels(module)
    data_size = 7 * len(channels)
    master = next(c for c in channels if c != -1)
    array = numpy.zeros(data_size, dtype="double")
    data = ffi.cast("double *", array.ctypes.data)
    code = handel.xiaGetRunData(master, b"module_statistics", data)
    check_error(code)
    # Parse raw data
    result = {}
    for index, channel in enumerate(channels):
        if channel != -1:
            realtime = array[index * 7 + 0]
            livetime = array[index * 7 + 1]
            triggers = int(array[index * 7 + 3])
            events = int(array[index * 7 + 4])
            icr = int(array[index * 7 + 5])
            ocr = int(array[index * 7 + 6])
            deadtime = 1 - float(ocr) / icr if icr != 0 else 1.0
            result[channel] = Stats(
                realtime, livetime, triggers, events, icr, ocr, deadtime
            )
    return result


def get_statistics():
    """Return the statistics for all enabled channels as a dictionary."""
    result = {}
    for module in get_modules():
        result.update(get_module_statistics(module))
    return result


# Buffer


def get_buffer_length(channel):
    length = ffi.new("unsigned long *")
    code = handel.xiaGetRunData(channel, b"buffer_len", length)
    check_error(code)
    return length[0]


def get_buffer_full(channel, buffer_id):
    bid = to_buffer_id(buffer_id)
    command = b"buffer_full_%c" % bid
    result = ffi.new("unsigned short *")
    code = handel.xiaGetRunData(channel, command, result)
    check_error(code)
    return bool(result[0])


def get_buffer(channel, buffer_id):
    bid = to_buffer_id(buffer_id)
    command = b"buffer_%c" % bid
    length = get_buffer_length(channel)
    array = numpy.zeros(length, dtype="uint32")
    data = ffi.cast("uint32_t *", array.ctypes.data)
    code = handel.xiaGetRunData(channel, command, data)
    check_error(code)
    return array


def buffer_done(channel, buffer_id):
    bid = to_buffer_id(buffer_id)
    code = handel.xiaBoardOperation(channel, b"buffer_done", bid)
    check_error(code)


# Not exposed

# int xiaDoSpecialRun(int detChan, char *name, void *info);
# int xiaGetSpecialRunData(int detChan, char *name, void *value);


# System


def load_system(*path):
    filename = to_bytes(os.path.join(*path))
    code = handel.xiaLoadSystem(b"handel_ini", filename)
    check_error(code)


def save_system(*path):
    filename = to_bytes(os.path.join(*path))
    code = handel.xiaSaveSystem(b"handel_ini", filename)
    check_error(code)


def start_system():
    code = handel.xiaStartSystem()
    check_error(code)


# Logging


def enable_log_output():
    code = handel.xiaEnableLogOutput()
    check_error(code)


def disable_log_output():
    code = handel.xiaSuppressLogOutput()
    check_error(code)


def set_log_level(level):
    code = handel.xiaSetLogLevel(level)
    check_error(code)


def set_log_output(filename):
    filename = to_bytes(filename)
    code = handel.xiaSetLogOutput(filename)
    check_error(code)


def close_log():
    code = handel.xiaCloseLog()
    check_error(code)


# Firmware

# Not exposed

# int xiaNewFirmware(char *alias);
# int xiaAddFirmwareItem(char *alias, char *name, void *value);
# int xiaModifyFirmwareItem(char *alias, unsigned short decimation, char *name, void *value);
# int xiaGetFirmwareItem(char *alias, unsigned short decimation, char *name, void *value);
# int xiaGetNumFirmwareSets(unsigned int *numFirmware);
# int xiaGetFirmwareSets(char *firmware[]);
# int xiaGetFirmwareSets_VB(unsigned int index, char *alias);
# int xiaGetNumPTRRs(char *alias, unsigned int *numPTRR);
# int xiaRemoveFirmware(char *alias);
# int xiaDownloadFirmware(int detChan, char *type);


# Module


def get_num_modules():
    num_modules = ffi.new("unsigned int *")
    code = handel.xiaGetNumModules(num_modules)
    check_error(code)
    return num_modules[0]


def get_modules():
    n = get_num_modules()
    arg = [ffi.new("char []", MAX_STRING_LENGTH) for _ in range(n)]
    code = handel.xiaGetModules(arg)
    check_error(code)
    return tuple(ffi.string(x).decode() for x in arg)


def get_module_from_channel(channel):
    alias = ffi.new("char []", MAX_STRING_LENGTH)
    code = handel.xiaModuleFromDetChan(channel, alias)
    check_error(code)
    return ffi.string(alias).decode()


def get_module_type(alias):
    alias = to_bytes(alias)
    value = ffi.new("char []", MAX_STRING_LENGTH)
    code = handel.xiaGetModuleItem(alias, b"module_type", value)
    check_error(code)
    return ffi.string(value).decode()


def get_module_interface(alias):
    alias = to_bytes(alias)
    value = ffi.new("char []", MAX_STRING_LENGTH)
    code = handel.xiaGetModuleItem(alias, b"interface", value)
    check_error(code)
    return ffi.string(value).decode()


# Channels


def get_module_number_of_channels(alias):
    alias = to_bytes(alias)
    value = ffi.new("int *")
    code = handel.xiaGetModuleItem(alias, b"number_of_channels", value)
    check_error(code)
    return value[0]


def get_module_channel_at(alias, index):
    alias = to_bytes(alias)
    value = ffi.new("int *")
    key = b"channel%d_alias" % index
    code = handel.xiaGetModuleItem(alias, key, value)
    check_error(code)
    return value[0]


def get_module_channels(alias):
    """Return the module channels properly indexed."""
    number_of_channels = get_module_number_of_channels(alias)
    return tuple(
        get_module_channel_at(alias, index) for index in range(number_of_channels)
    )


def get_grouped_channels():
    """Return the indexed channels grouped by modules."""
    return tuple(get_module_channels(alias) for alias in get_modules())


def get_channels():
    """Return all the enabled channels."""
    return tuple(
        sorted(
            channel
            for channels in get_grouped_channels()
            for channel in channels
            if channel != -1
        )
    )


# Not exposed

# int xiaNewModule(char *alias);
# int xiaAddModuleItem(char *alias, char *name, void *value);
# int xiaModifyModuleItem(char *alias, char *name, void *value);
# int xiaGetModuleItem(char *alias, char *name, void *value);
# int xiaGetModules_VB(unsigned int index, char *alias);
# int xiaRemoveModule(char *alias);


# Channel set

# Not exposed

# int xiaAddChannelSetElem(unsigned int detChanSet, unsigned int newChan);
# int xiaRemoveChannelSetElem(unsigned int detChan, unsigned int chan);
# int xiaRemoveChannelSet(unsigned int detChan);


# Parameters


def get_acquisition_value(name, channel):
    name = to_bytes(name)
    pointer = ffi.new("double *")
    code = handel.xiaGetAcquisitionValues(channel, name, pointer)
    check_error(code)
    return pointer[0]


def set_acquisition_value(name, value, channel=None):
    if channel is None:
        channel = -1  # All channels
    name = to_bytes(name)
    pointer = ffi.new("double *", value)
    code = handel.xiaSetAcquisitionValues(channel, name, pointer)
    check_error(code)


def remove_acquisition_value(name, channel=None):
    if channel is None:
        channel = -1  # All channels
    name = to_bytes(name)
    code = handel.xiaRemoveAcquisitionValues(channel, name)
    check_error(code)


def apply_acquisition_values(channel=None):
    # Apply all
    if channel is None:
        # Only one apply operation by module is required
        grouped = get_grouped_channels()
        for master in map(max, grouped):
            apply_acquisition_values(master)
        return
    # Apply single
    dummy = ffi.new("int *")
    code = handel.xiaBoardOperation(channel, b"apply", dummy)
    check_error(code)


# Not exposed

# int xiaUpdateUserParams(int detChan);
# int xiaGainOperation(int detChan, char *name, void *value);
# int xiaGainCalibrate(int detChan, double deltaGain);
# int xiaGetParameter(int detChan, const char *name, unsigned short *value);
# int xiaSetParameter(int detChan, const char *name, unsigned short value);
# int xiaGetNumParams(int detChan, unsigned short *numParams);
# int xiaGetParamData(int detChan, char *name, void *value);
# int xiaGetParamName(int detChan, unsigned short index, char *name);


# Operation

# Not exposed

# int xiaBoardOperation(int detChan, char *name, void *value) with mapping_pixel_next (int 0);
# int xiaMemoryOperation(int detChan, char *name, void *value);
# int xiaCommandOperation(int detChan, byte_t cmd, unsigned int lenS, byte_t *send, unsigned int lenR, byte_t *recv);


# Analysis

# Not exposed

# int xiaFitGauss(long data[], int lower, int upper, float *pos, float *fwhm);
# int xiaFindPeak(long *data, int numBins, float thresh, int *lower, int *upper);


# Debugging


def get_handel_version():
    rel = ffi.new("int *")
    min = ffi.new("int *")
    maj = ffi.new("int *")
    pretty = ffi.new("char *")
    handel.xiaGetVersionInfo(rel, min, maj, pretty)
    return maj[0], min[0], rel[0]


# Not exposed

# int xiaSetIOPriority(int pri);
# int xiaMemStatistics(unsigned long *total, unsigned long *current, unsigned long *peak);
# void xiaMemSetCheckpoint(void);
# void xiaMemLeaks(char *);


# Files


def get_config_files(*path):
    """Return all the ini files in path (including subdirectories)."""
    path = os.path.join(*path)
    ext = b".ini" if isinstance(path, bytes) else ".ini"
    sep = b"/" if isinstance(path, bytes) else "/"
    return [
        os.path.join(dp, f).lstrip(path).lstrip(sep)
        for dp, dn, fn in os.walk(path)
        for f in fn
        if f.endswith(ext)
    ]


def get_config(*path):
    """Read and return the given config file as a dictionary."""
    filename = os.path.join(*path)
    with open(filename) as f:
        return parse_xia_ini_file(f.read())
