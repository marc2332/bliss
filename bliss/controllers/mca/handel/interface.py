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
    "start_run",
    "stop_run",
    "get_run_data_length",
    "get_run_data",
    "load_system",
    "save_system",
    "start_system",
    "enable_log_output",
    "disable_log_output",
    "set_log_output",
    "set_log_level",
    "close_log",
    "set_acquisition_value",
    "get_acquisition_value",
    "get_handel_version",
]


# Helpers


def to_bytes(arg):
    if isinstance(arg, bytes):
        return arg
    return arg.encode()


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
    arg = [ffi.new("char []", 80) for _ in range(n)]
    code = handel.xiaGetDetectors(arg)
    check_error(code)
    return tuple(ffi.string(x).decode() for x in arg)


# int xiaAddDetectorItem(char *alias, char *name, void *value);
# int xiaModifyDetectorItem(char *alias, char *name, void *value);
# int xiaGetDetectorItem(char *alias, char *name, void *value);
# int xiaGetDetectors_VB(unsigned int index, char *alias);
# int xiaRemoveDetector(char *alias);
# int xiaDetectorFromDetChan(int detChan, char *alias);


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


# int xiaDoSpecialRun(int detChan, char *name, void *info);
# int xiaGetSpecialRunData(int detChan, char *name, void *value);


# System


def load_system(filename):
    # Is this an alias to xiaInit?
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

# int xiaNewModule(char *alias);
# int xiaAddModuleItem(char *alias, char *name, void *value);
# int xiaModifyModuleItem(char *alias, char *name, void *value);
# int xiaGetModuleItem(char *alias, char *name, void *value);
# int xiaGetNumModules(unsigned int *numModules);
# int xiaGetModules(char *modules[]);
# int xiaGetModules_VB(unsigned int index, char *alias);
# int xiaRemoveModule(char *alias);
# int xiaModuleFromDetChan(int detChan, char *alias);


# Channel set

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


# int xiaRemoveAcquisitionValues(int detChan, char *name);
# int xiaUpdateUserParams(int detChan);
# int xiaGainOperation(int detChan, char *name, void *value);
# int xiaGainCalibrate(int detChan, double deltaGain);
# int xiaGetParameter(int detChan, const char *name, unsigned short *value);
# int xiaSetParameter(int detChan, const char *name, unsigned short value);
# int xiaGetNumParams(int detChan, unsigned short *numParams);
# int xiaGetParamData(int detChan, char *name, void *value);
# int xiaGetParamName(int detChan, unsigned short index, char *name);


# Operation

# int xiaBoardOperation(int detChan, char *name, void *value);
# int xiaMemoryOperation(int detChan, char *name, void *value);
# int xiaCommandOperation(int detChan, byte_t cmd, unsigned int lenS, byte_t *send, unsigned int lenR, byte_t *recv);


# Analysis

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


# int xiaSetIOPriority(int pri);
# int xiaMemStatistics(unsigned long *total, unsigned long *current, unsigned long *peak);
# void xiaMemSetCheckpoint(void);
# void xiaMemLeaks(char *);
