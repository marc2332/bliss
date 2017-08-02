"""Python interface to handel API."""

from __future__ import absolute_import

import numpy

from .error import check_return_value, check_error
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


@check_return_value
def init(filename):
    filename = to_bytes(filename)
    return handel.xiaInit(filename)


@check_return_value
def init_handel():
    return handel.xiaInitHandel()


@check_return_value
def exit():
    return handel.xiaExit()


# Detectors


@check_return_value
def new_detector(alias):
    alias = to_bytes(alias)
    return handel.xiaNewDetector(alias)


def get_num_detectors():
    num = ffi.new("unsigned int *")
    check_error(handel.xiaGetNumDetectors(num))
    return num[0]


def get_detectors():
    n = get_num_detectors()
    arg = [ffi.new("char []", 80) for _ in range(n)]
    check_error(handel.xiaGetDetectors(arg))
    return tuple(ffi.string(x).decode() for x in arg)


# int xiaAddDetectorItem(char *alias, char *name, void *value);
# int xiaModifyDetectorItem(char *alias, char *name, void *value);
# int xiaGetDetectorItem(char *alias, char *name, void *value);
# int xiaGetDetectors_VB(unsigned int index, char *alias);
# int xiaRemoveDetector(char *alias);
# int xiaDetectorFromDetChan(int detChan, char *alias);


# Run control


@check_return_value
def start_run(channel, resume=False):
    return handel.xiaStartRun(channel, resume)


@check_return_value
def stop_run(channel):
    return handel.xiaStopRun(channel)


def get_run_data_length(channel):
    length = ffi.new("unsigned long *")
    check_error(handel.xiaGetRunData(channel, "mca_length", length))
    return length[0]


def get_run_data(channel):
    length = get_run_data_length(channel)
    array = numpy.zeros(length, dtype="uint")
    data = ffi.cast("unsigned long *", array.ctypes.data)
    check_error(handel.xiaGetRunData(channel, "mca", data))
    return array


# int xiaDoSpecialRun(int detChan, char *name, void *info);
# int xiaGetSpecialRunData(int detChan, char *name, void *value);


# System


@check_return_value
def load_system(filename):
    # Is this an alias to xiaInit?
    filename = to_bytes(filename)
    return handel.xiaLoadSystem(b"handel_ini", filename)


@check_return_value
def save_system(filename):
    filename = to_bytes(filename)
    return handel.xiaSaveSystem(b"handel_ini", filename)


@check_return_value
def start_system():
    return handel.xiaStartSystem()


# Logging


@check_return_value
def enable_log_output():
    return handel.xiaEnableLogOutput()


@check_return_value
def disable_log_output():
    return handel.xiaSuppressLogOutput()


@check_return_value
def set_log_level(level):
    return handel.xiaSetLogLevel(level)


@check_return_value
def set_log_output(filename):
    filename = to_bytes(filename)
    return handel.xiaSetLogOutput(filename)


@check_return_value
def close_log():
    return handel.xiaCloseLog()


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
    check_error(handel.xiaSetAcquisitionValues(channel, name, pointer))


def get_acquisition_value(channel, name):
    name = to_bytes(name)
    pointer = ffi.new("double *")
    check_error(handel.xiaGetAcquisitionValues(channel, name, pointer))
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
