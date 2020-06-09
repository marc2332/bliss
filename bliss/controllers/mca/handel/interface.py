"""Python interface to handel API."""

from __future__ import absolute_import

import os
import inspect
import logging
from functools import reduce

import numpy
import gevent
from bliss.common import event

from .error import check_error, HandelError
from ._cffi import handel, ffi
from .stats import stats_from_normal_mode
from .parser import parse_xia_ini_file
from .mapping import parse_mapping_buffer

__all__ = [
    "init",
    "init_handel",
    "exit",
    "get_num_detectors",
    "get_detectors",
    "get_detector_from_channel",
    "start_run",
    "stop_run",
    "get_channel_realtime",
    "get_spectrum_length",
    "get_spectrum",
    "get_spectrums",
    "is_channel_running",
    "is_running",
    "get_module_statistics",
    "get_statistics",
    "get_buffer_length",
    "get_raw_buffer",
    "get_buffer_data",
    "is_buffer_full",
    "is_buffer_overrun",
    "set_buffer_done",
    "get_buffer_current_pixel",
    "get_current_pixel",
    "set_maximum_pixels_per_buffer",
    "any_buffer_overrun",
    "all_buffer_full",
    "set_all_buffer_done",
    "get_all_buffer_data",
    "synchronized_poll_data",
    "get_baseline_length",
    "get_baseline",
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
    "get_module_number_of_channels",
    "get_module_channel_at",
    "get_module_channels",
    "get_grouped_channels",
    "get_channels",
    "get_master_channels",
    "get_trigger_channels",
    "set_acquisition_value",
    "get_acquisition_value",
    "remove_acquisition_value",
    "apply_acquisition_values",
    "get_handel_version",
    "get_config_files",
    "get_config",
]

MAX_STRING_LENGTH = 80

LOGGER = logging.getLogger("HANDEL_rpc")


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


def merge_buffer_data(*data):
    if not data:
        return {}, {}
    # Use first argument as result
    result, data = data[0], data[1:]
    # Copy other arguments into the result
    for sources in data:
        for source, dest in zip(sources, result):
            for key, dct in source.items():
                dest.setdefault(key, {})
                dest[key].update(dct)
    return result


# Initializing handel


def init(*path):
    """ Called at BLISS object init.
    """
    filename = to_bytes(os.path.join(*path))
    LOGGER.debug(f"init (config={filename})")

    code = handel.xiaInit(filename)
    check_error(code)


def init_handel():
    """ Called at server startup.
    """
    LOGGER.debug("init_handel --")

    code = handel.xiaInitHandel()
    check_error(code)


def exit():
    LOGGER.debug(f"exit()")
    code = handel.xiaExit()
    check_error(code)


# Detectors


def get_num_detectors():
    """ Return the number of detectors configured
    """
    num = ffi.new("unsigned int *")
    code = handel.xiaGetNumDetectors(num)
    check_error(code)
    return num[0]


def get_detectors():
    """ ???
    """
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

# int xiaGetDetectorItem(char *alias, char *name, void *value);
# int xiaGetDetectors_VB(unsigned int index, char *alias);

# Run control


def start_run(channel=None, resume=False):
    """
    """
    LOGGER.debug(f"start_run(channel={channel})")

    if channel is None:
        channel = -1  # All channels
    code = handel.xiaStartRun(channel, resume)
    check_error(code)


def stop_run(channel=None):
    """
    """
    LOGGER.debug(f"stop_run(channel={channel})")

    if channel is None:
        channel = -1  # All channels
    code = handel.xiaStopRun(channel)
    check_error(code)


def get_channel_realtime(channel):
    time = ffi.new("double *")
    code = handel.xiaGetRunData(channel, b"realtime", time)
    check_error(code)
    return time[0]


def get_spectrum_length(channel):
    length = ffi.new("unsigned long *")
    code = handel.xiaGetRunData(channel, b"mca_length", length)
    check_error(code)
    return length[0]


def get_spectrum(channel):
    LOGGER.debug(f"get_spectrum(channel={channel})")
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
    # It turns out running contains 2 bits of information
    # - bit 0: whether the channel is acquiring
    # - bit 1: whether the channel is running (in the start_run/stop_run sense)
    # We're interested in the first bit of information here
    _running = bool(running[0] & 0x1)

    return _running


def is_running():
    """Return True if any channel is running, False otherwise."""

    running = any(is_channel_running(channel) for channel in get_channels())

    if LOGGER.level == logging.DEBUG:
        if running:
            print(f"R ", end="")
        else:
            print(f"Not Running")

    return running


# Statistics

"""
handel.xiaGetRunData(master, b'module_statistics_2', data)
read statistics of a whole module and put results in data.
0: realtime
1: trigger livetime
2: reserved    (energy livetime for XMAP)
3: triggers
4: MCA events
5: ICR
6: OCR
7: reserved    (underflows for XMAP)
8: reserved    (overflows for XMAP)

stats_from_normal_mode() returns a Stats named-tuple
'realtime livetime triggers events icr ocr deadtime'
"""


def get_module_statistics(module):
    LOGGER.debug(f"get_module_statistics(module={module})")
    channels = get_module_channels(module)
    # FalconX requires a spectrum read for the statistics to be updated
    if get_module_type(module).startswith("falconx"):
        for channel in channels:
            if channel >= 0:
                try:
                    get_spectrum(channel)
                except HandelError:
                    pass
    # Prepare buffer
    data_size = 9 * len(channels)
    master = next(c for c in channels if c >= 0)
    array = numpy.zeros(data_size, dtype="double")
    data = ffi.cast("double *", array.ctypes.data)
    # Run handel call
    code = handel.xiaGetRunData(master, b"module_statistics_2", data)
    check_error(code)
    # Parse raw data
    return {
        channel: stats_from_normal_mode(array[index * 9 :])
        for index, channel in enumerate(channels)
        if channel >= 0
    }


def get_statistics():
    """Return the statistics for all enabled channels as a dictionary."""
    result = {}
    # We're not using get_master_channels here.
    # That's because each FalconX channels is its own master, even though
    # the statistics can be accessed with a single call per module.
    for module in get_modules():
        result.update(get_module_statistics(module))

    LOGGER.debug(f"get_statistics()")
    LOGGER.debug("result=", result)

    return result


# Buffer


def get_buffer_length(master):
    length = ffi.new("unsigned long *")
    code = handel.xiaGetRunData(master, b"buffer_len", length)
    check_error(code)
    buf_len = length[0]
    LOGGER.debug(f"get_buffer_length(master={master}) --> {buf_len}")

    return buf_len


def is_buffer_full(master, buffer_id):
    bid = to_buffer_id(buffer_id)
    command = b"buffer_full_%c" % bid
    result = ffi.new("unsigned short *")
    code = handel.xiaGetRunData(master, command, result)
    check_error(code)
    ibf = bool(result[0])

    LOGGER.debug(f"is_buffer_full(master={master}, buffer_id={buffer_id}) --> {ibf}")

    return ibf


def is_buffer_overrun(master):
    result = ffi.new("unsigned short *")
    code = handel.xiaGetRunData(master, b"buffer_overrun", result)
    check_error(code)
    ibo = bool(result[0])
    LOGGER.debug(f"is_buffer_overrun(master={master}) --> {ibo}")
    return ibo


def get_raw_buffer(master, buffer_id):
    LOGGER = logging.getLogger("HANDEL_rpc")
    LOGGER.debug(f"get_raw_buffer(master={master} buff id={buffer_id})")

    bid = to_buffer_id(buffer_id)
    command = b"buffer_%c" % bid
    length = get_buffer_length(master)
    array = numpy.zeros(length * 2, dtype="uint16")
    data = ffi.cast("uint32_t *", array.ctypes.data)
    code = handel.xiaGetRunData(master, command, data)
    check_error(code)
    # Check magic number
    if array[0] == 0:
        raise RuntimeError(
            f"The buffer {str(buffer_id)} associated with channel {master} is empty"
        )
    # Return array
    return array


def get_buffer_data(master, buffer_id):
    LOGGER.debug(f"get_buffer_date(master={master} buff id={buffer_id})")
    raw = get_raw_buffer(master, buffer_id)
    return parse_mapping_buffer(raw)


def get_buffer_current_pixel(master):
    current = ffi.new("unsigned long *")
    code = handel.xiaGetRunData(master, b"current_pixel", current)
    check_error(code)

    cur_pix = current[0]
    LOGGER.debug(f"get_buffer_current_pixel(master={master}) --> {cur_pix}")

    return cur_pix


def set_buffer_done(master, buffer_id):
    """Flag the the buffer as read and return an overrun detection.

    False means no overrun have been detected.
    True means a possible overrun have been detected.
    """
    bid = to_buffer_id(buffer_id)
    code = handel.xiaBoardOperation(master, b"buffer_done", bid)
    check_error(code)
    other = b"b" if bid == b"a" else b"a"
    overrun = is_buffer_full(master, other) and is_channel_running(master)
    LOGGER.debug(
        f"get_raw_buffer(master={master} buff id={buffer_id} )   overrun={overrun}"
    )
    return overrun


# Synchronized run


def set_maximum_pixels_per_buffer():
    """Set the maximum number of pixels per buffer.

    It makes sure all the modules are configured with the same value,
    in order to be able to perform synchronized run.
    """
    set_acquisition_value("num_map_pixels_per_buffer", -1)
    value = min(
        get_acquisition_value("num_map_pixels_per_buffer", master)
        for master in get_master_channels()
    )
    LOGGER.debug(f"set_maximum_pixels_per_buffer()  {value}")
    set_acquisition_value("num_map_pixels_per_buffer", value)


def any_buffer_overrun():
    """Return True if an overrun has been detected by the hardware on any
    module, False otherwise.
    """
    return any(is_buffer_overrun(master) for master in get_master_channels())


def all_buffer_full(buffer_id):
    """Return True if all the given buffers are full and ready to be read,
    False otherwise.
    """
    return all(is_buffer_full(master, buffer_id) for master in get_master_channels())


def set_all_buffer_done(buffer_id):
    """Flag all the given buffers as read and return an overrun detection.

    False means no overrun have been detected.
    True means an overrun have been detected.
    """
    overruns = [set_buffer_done(master, buffer_id) for master in get_master_channels()]
    return any(overruns)


def get_current_pixel():
    """Get the current pixel reported by the hardware."""

    current_pixel = max(
        get_buffer_current_pixel(master) for master in get_master_channels()
    )

    LOGGER.debug(f"get_current_pixel() ->  {current_pixel}")

    return current_pixel


def get_all_buffer_data(buffer_id):
    """Get and merge all the buffer data from the different channels.

    Return a tuple (spectrums, statistics) where both values are dictionaries
    of dictionaries, first indexed by pixel and then by channel."""
    data = [get_buffer_data(master, buffer_id) for master in get_master_channels()]

    LOGGER.debug(f"get_all_buffer_data(buffer_id={buffer_id}")

    return merge_buffer_data(*data)


def synchronized_poll_data(done=set()):
    """Convenient helper for buffer management in mapping mode.

    It assumes that all the modules are configured with the same number
    of pixels per buffer.

    It includes:
    - Hardware overrun detection
    - Software overrun detection
    - Current pixel readout
    - Buffer readout and data parsing
    - Buffer flaging after readout

    If an overrun is detected, a RuntimeError exception is raised.

    Return a tuple (current_pixel, spectrums, statistics) where both
    the spectrums and statistics values are dictionaries of dictionaries,
    first indexed by pixel and then by channel. If there is no data to
    report, those values are empty dicts.
    """
    data = {"a": None, "b": None}
    overrun_error = RuntimeError("Buffer overrun!")
    # Get info from hardware
    current_pixel = get_current_pixel()
    full = {x for x in data if all_buffer_full(x)}
    # Overrun from hardware
    if any_buffer_overrun():
        raise overrun_error
    # FalconX hack
    # The buffer_done command does not reset the full flag.
    # It's only reset when the buffer starts being filled up again.
    # For this reason, we need to remember full flags from the previous call.
    # This is exactly what the done set does.
    done &= full  # Reset done flags
    full -= done  # Don't read twice
    done |= full  # Set done flags
    # Read data from buffers
    for x in full:
        data[x] = get_all_buffer_data(x)
        # Overrun from set_buffer_done
        if set_all_buffer_done(x):
            raise overrun_error
    # Extract data
    args = filter(None, data.values())
    spectrums, stats = merge_buffer_data(*args)
    # Return
    return current_pixel, spectrums, stats


# Baseline


def get_baseline_length(channel):
    length = ffi.new("unsigned long *")
    code = handel.xiaGetRunData(channel, b"baseline_length", length)
    check_error(code)
    return length[0]


def get_baseline(channel):
    length = get_baseline_length(channel)
    array = numpy.zeros(length, dtype="uint32")
    data = ffi.cast("uint32_t *", array.ctypes.data)
    code = handel.xiaGetRunData(channel, b"baseline", data)
    check_error(code)
    return array


# Not exposed

# int xiaDoSpecialRun(int detChan, char *name, void *info);
# int xiaGetSpecialRunData(int detChan, char *name, void *value);


# System


def load_system(*path):
    """ ???
    """
    LOGGER.debug(f"load_system()")
    filename = to_bytes(os.path.join(*path))
    code = handel.xiaLoadSystem(b"handel_ini", filename)
    check_error(code)


def save_system(*path):
    """ ???
    """
    LOGGER.debug(f"save_system()")
    filename = to_bytes(os.path.join(*path))
    code = handel.xiaSaveSystem(b"handel_ini", filename)
    check_error(code)


def start_system():
    """
    """
    LOGGER.debug(f"start_system()")

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

# int xiaGetFirmwareItem(char *alias, unsigned short decimation, char *name, void *value);
# int xiaGetNumFirmwareSets(unsigned int *numFirmware);
# int xiaGetFirmwareSets(char *firmware[]);
# int xiaGetFirmwareSets_VB(unsigned int index, char *alias);
# int xiaGetNumPTRRs(char *alias, unsigned int *numPTRR);


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


def get_module_type(alias=None):
    if alias is None:
        # Get all the values
        values = [get_module_type(alias) for alias in get_modules()]
        # Compare the values
        value = reduce(lambda c, x: c if c == x else None, values)
        # Inconsistency
        if value is None:
            raise ValueError("The module type differs from module to module")
        # Return
        return value
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
            if channel >= 0
        )
    )


def get_master_channels():
    """Return one active channel for each buffer."""
    # For the FalconX, each channel has its own buffer
    if get_module_type().startswith("falconx"):
        return get_channels()
    # Otherwise, one channel per module is enough
    return tuple(
        next(channel for channel in groups if channel >= 0)
        for groups in get_grouped_channels()
    )


def get_trigger_channels():
    """Return the list of channels that can be used
    as gate master or sync master."""
    return tuple(
        groups[0] for groups in get_grouped_channels() if groups and groups[0] >= 0
    )


# Not exposed

# int xiaGetModuleItem(char *alias, char *name, void *value);
# int xiaGetModules_VB(unsigned int index, char *alias);


# Parameters


def get_acquisition_value(name, channel=None):
    # Get values for all channels
    if channel is None:
        # Get all the values
        values = [get_acquisition_value(name, channel) for channel in get_channels()]
        # Compare the values
        value = reduce(lambda c, x: c if c == x else None, values)
        # Inconsistency
        if value is None:
            raise ValueError(
                "The acquisition value {name} differs from channel to channel"
            )
        # Return
        return value
    # Get value for a single channel
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
        for master in get_master_channels():
            apply_acquisition_values(master)
        return
    # Apply single
    dummy = ffi.new("int *")
    code = handel.xiaBoardOperation(channel, b"apply", dummy)
    check_error(code)


def trigger():
    module = inspect.getmodule(trigger)
    try:
        stop_run()
        start_run()
        while is_running():
            gevent.idle()
        stop_run()
        spectrums = get_spectrums()
        statistics = get_statistics()
        event.send(module, "data", (spectrums, statistics))
    except Exception as e:
        event.send(module, "data", e)


HARDWARE_READING_TASK = None


def start_hardware_reading():
    global HARDWARE_READING_TASK
    if HARDWARE_READING_TASK:
        raise RuntimeError("Reading task is not finnished")
    nbpoints = get_acquisition_value("num_map_pixels")
    HARDWARE_READING_TASK = gevent.spawn(_hardware_poll_points, nbpoints)


def wait_hardware_reading():
    global HARDWARE_READING_TASK
    if HARDWARE_READING_TASK:
        try:
            return HARDWARE_READING_TASK.get()
        finally:
            HARDWARE_READING_TASK = None


def _hardware_poll_points(npoints):
    module = inspect.getmodule(_hardware_poll_points)
    queue = gevent.queue.Queue()
    try:
        raw_read_task = gevent.spawn(_raw_read, npoints, queue)
        for args in queue:
            event.send(module, "data", args)
    finally:
        event.send(module, "data", StopIteration)
        if raw_read_task.ready():
            raw_read_task.get()  # in case of exception
        else:
            raw_read_task.kill()


def _raw_read(acquisition_number, queue):
    try:

        def poll_data(sent):
            print("call polling")
            current, data, statistics = synchronized_poll_data()
            points = list(range(sent, sent + len(data)))
            # Check data integrity
            if sorted(data) != sorted(statistics) != points:
                raise RuntimeError("The polled data overlapped during the acquisition")
            sent += len(data)
            # Send the data
            for n in points:
                queue.put((data[n], statistics[n]))
            # Finished
            # we should go in this test to send the end of the acquisition
            print("poll_data", sent, current, acquisition_number)
            if sent == current == acquisition_number:
                raise StopIteration
            # Sleep
            gevent.sleep(0)
            return sent

        sent = 0
        while is_running():
            sent = poll_data(sent)
        # get last points
        poll_data(sent)
    except StopIteration:
        pass
    except Exception as e:
        queue.put(e)
        raise
    finally:
        queue.put(StopIteration)


# Not exposed

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


# Files


def get_config_files(*path):
    """Return all the ini files in path (including subdirectories)."""

    path = os.path.join(*path)
    ext = b".ini" if isinstance(path, bytes) else ".ini"
    sep = b"/" if isinstance(path, bytes) else "/"
    return [
        os.path.relpath(os.path.join(dp, f), path).lstrip(sep)
        for dp, dn, fn in os.walk(path)
        for f in fn
        if f.endswith(ext)
    ]


def get_config(*path):
    """Read and return the given config file as a dictionary."""
    filename = os.path.join(*path)
    with open(filename) as f:
        return parse_xia_ini_file(f.read())
