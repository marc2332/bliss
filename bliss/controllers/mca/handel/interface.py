"""Python interface to handel API."""

from __future__ import absolute_import

import numpy

from .error import check_error
from ._cffi import handel, ffi

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
    "get_run_data_length",
    "get_run_data",
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
    "set_acquisition_value",
    "get_acquisition_value",
    "remove_acquisition_value",
    "apply_acquisition_value",
    "get_handel_version",
]

MAX_STRING_LENGTH = 80


# Helpers


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


def init(filename):
    filename = to_bytes(filename)
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


def start_run(channel, resume=False):
    code = handel.xiaStartRun(channel, resume)
    check_error(code)


def stop_run(channel):
    code = handel.xiaStopRun(channel)
    check_error(code)


def get_run_data_length(channel):
    length = ffi.new("unsigned long *")
    code = handel.xiaGetRunData(channel, b"mca_length", length)
    check_error(code)
    return length[0]


def get_run_data(channel):
    length = get_run_data_length(channel)
    array = numpy.zeros(length, dtype="uint")
    data = ffi.cast("unsigned long *", array.ctypes.data)
    code = handel.xiaGetRunData(channel, b"mca", data)
    check_error(code)
    return array


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
    array = numpy.zeros(length, dtype="uint")
    data = ffi.cast("unsigned long *", array.ctypes.data)
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


def load_system(filename):
    filename = to_bytes(filename)
    code = handel.xiaLoadSystem(b"handel_ini", filename)
    check_error(code)


def save_system(filename):
    filename = to_bytes(filename)
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


def set_acquisition_value(channel, name, value):
    name = to_bytes(name)
    pointer = ffi.new("double *", value)
    code = handel.xiaSetAcquisitionValues(channel, name, pointer)
    check_error(code)


def get_acquisition_value(channel, name):
    name = to_bytes(name)
    pointer = ffi.new("double *")
    code = handel.xiaGetAcquisitionValues(channel, name, pointer)
    check_error(code)
    return pointer[0]


def remove_acquisition_value(channel, name):
    name = to_bytes(name)
    code = handel.xiaRemoveAcquisitionValues(channel, name)
    check_error(code)


def apply_acquisition_value(channel):
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
