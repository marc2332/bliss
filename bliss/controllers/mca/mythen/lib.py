import enum
import operator
from functools import partial
from collections import namedtuple

from six.moves import reduce

import numpy as np
from gevent.lock import Semaphore as Lock
from bliss.comm.tcp import Socket
from bliss.config.channels import Cache

# Constants

UDP_PORT = 1030
TCP_PORT = 1031


RETURN_TYPES = {
    "char": (1, bytes.decode),
    "int": (4, partial(np.frombuffer, dtype=np.int32)),
    "float": (4, partial(np.frombuffer, dtype=np.float32)),
    "long long": (8, partial(np.frombuffer, dtype=np.int64)),
}


MATERIALS = {0: "silicon"}

ERROR_CODES = {
    -1: "Unknown command",
    -2: "Invalid argument",
    -3: "Unknown settings",
    -4: "Out of memory",
    -5: "Module calibration files not found",
    -6: "Readout failed",
    -7: "Acquisition not finished",
    -8: "Failure while reading temperature and humidity sensor",
    -9: "Invalid license key",
    -10: "Flatfield file not found",
    -11: "Bad channel file not found",
    -12: "Energy calibration file not found",
    -13: "Noise file not found",
    -14: "Trimbit file not found",
    -15: "Invalid format of the flatfield file",
    -16: "Invalid format of the bad channel file",
    -17: "Invalid format of the energy calibration file",
    -18: "Invalid format of the noise file",
    -19: "Invalid format of the trimbit file",
    -20: "Version file not found",
    -21: "Invalid format of the version file",
    -22: "Gain calibration file not found",
    -23: "Invalid format of the gain calibration file",
    -24: "Dead time file not found",
    -25: "Invalid format of the dead time file",
    -26: "High voltage file not found",
    -27: "Invalid format of high voltage file",
    -28: "Energy threshold relation file not found",
    -29: "Invalid format of the energy threshold relation file",
    -30: "Could not create log file",
    -31: "Could not close log file",
    -32: "Could not read log file",
    -50: "No modules connected",
    -51: "Error during module communication",
    -52: "DCS initialization failed",
    -53: "Could not store customer flatfield",
}


# Types


class MythenError(IOError):
    pass


class MythenCommandError(MythenError):
    def __init__(self, error_code, command):
        self.error_code = error_code
        self.error_message = ERROR_CODES.get(error_code)
        self.command = command
        self.args = error_code, self.error_message, command

    def __str__(self):
        return "[Error {}] {} ({!r})".format(
            self.error_code, self.error_message, self.command
        )


class MythenCompatibilityError(MythenError):
    def __init__(self, version, requirement, command):
        self.version = version
        self.requirement = requirement
        self.command = command
        self.args = version, requirement, command

    def __str__(self):
        str_version = ".".join(map(str, self.version))
        str_requirement = self.requirement[:2] + " " + self.requirement[2:]
        return "[Version {}] Command {!r} requires version {}".format(
            str_version, self.command, str_requirement
        )


Status = namedtuple("Status", "running inactive_exposure empty_buffer")

Polarity = enum.IntEnum("Polarity", "Low High", start=0)


# Helpers


def run_command(sock, command, return_type="int", return_shape=(), payload=b""):
    # Get return info
    return_size = reduce(operator.mul, return_shape, 1)
    nbytes, decode = RETURN_TYPES[return_type]
    nbytes_error, decode_error = RETURN_TYPES["int"]
    # Craft the command
    if not isinstance(command, str):
        command = " ".join(map(str, command))
    # Send the command
    raw_command = command.encode()
    if payload:
        raw_command += b" " + payload
    total_size = nbytes * return_size
    with sock.lock:
        sock.write(raw_command)
        raw_data = sock.raw_read(total_size)
        if len(raw_data) == nbytes_error:
            error_code = np.asscalar(decode_error(raw_data))
            if error_code < 0:
                raise MythenCommandError(error_code, command)
        if len(raw_data) != total_size:
            raw_data += sock.read(total_size - len(raw_data))

    # Decode the data
    data = decode(raw_data)
    # Return string
    if return_type == "char":
        return data.split("\x00")[0]
    # Return scalar
    if return_shape == ():
        return np.asscalar(data)
    # Return array
    data.shape = return_shape
    return data


def convert(array, nbits):
    dtypes = {24: "int32", 16: "int16", 8: "int8", 4: "int8"}
    array.dtype = dtypes[nbits]
    if nbits == 24:
        array = array << 8 >> 8
    if nbits == 4:
        array = np.stack([array << 4 >> 4, array >> 4], axis=-1)
        array.shape = (array.size,)
    return array


# Mythen interface


class MythenInterface:
    def __init__(self, hostname):
        self._lock = Lock()
        self.name = f"mythen:{hostname}"
        self._sock = Socket(hostname, TCP_PORT)
        self._version_cache = Cache(self, "version", default_value=None)

    @property
    def version(self):
        if self._version_cache.value == None:
            version = self.get_version()
            self._version_cache.value = version
        return self._version_cache.value

    def close(self):
        self._sock.close()

    def _run_command(self, *args, **kwargs):
        with self._lock:
            return run_command(self._sock, *args, **kwargs)

    def _check_version(self, requirement, command):
        sign, version = requirement[:2], requirement[2:]
        sign = {">=": operator.ge, "<=": operator.le}[sign]
        version = tuple(map(int, version.split(".")))
        if not sign(self.version, version):
            raise MythenCompatibilityError(self.version, requirement, command)

    # Special getters

    def get_version(self):
        version = self._run_command("-get version", "char", (7,))
        return tuple(map(int, version[1:].split(".")))

    def get_nmodules(self):
        return self._run_command("-get nmodules", "int")

    def get_modchannels(self):
        nmodules = self.get_nmodules()
        if self.version < (4,):
            return (1280,) * nmodules
        shape = (nmodules,)
        modchannels = self._run_command("-get modchannels", "int", shape)
        return tuple(modchannels)

    def get_nchannels(self):
        modchannels = self.get_modchannels()
        return sum(modchannels)

    # General getters

    def get_assemblydate(self):
        assemblydate = self._run_command("-get assemblydate", "char", (50,))
        return assemblydate.rstrip("\n")

    def get_badchannels(self):
        shape = (self.get_nchannels(),)
        return self._run_command("-get badchannels", "int", shape)

    def get_commandid(self):
        return self._run_command("-get commandid", "int")

    def get_commandsetid(self):
        command = "-get commandsetid"
        self._check_version(">=4.0.0", command)
        return self._run_command(command, "int")

    def get_dcstemperature(self):
        command = "-get dcstemperature"
        self._check_version(">=4.0.0", command)
        return self._run_command(command, "float")

    def get_frameratemax(self):
        command = "-get frameratemax"
        self._check_version(">=4.0.0", command)
        return self._run_command(command, "float")

    def get_fwversion(self):
        command = "-get fwversion"
        self._check_version(">=4.0.0", command)
        return self._run_command(command, "char", (9,))

    def get_humidity(self):
        command = "-get humidity"
        self._check_version(">=4.0.0", command)
        shape = (self.get_nmodules(),)
        array = self._run_command(command, "float", shape)
        return tuple(array)

    def get_highvoltage(self):
        command = "-get hv"
        self._check_version(">=4.0.0", command)
        shape = (self.get_nmodules(),)
        array = self._run_command(command, "int", shape)
        return tuple(array)

    def get_modfwversion(self):
        command = "-get modfwversion"
        self._check_version(">=4.0.1", command)
        shape = (self.get_nmodules() * 8 + 1,)
        return self._run_command(command, "char", shape)

    def get_modnum(self):
        shape = (self.get_nmodules(),)
        array = self._run_command("-get modnum", "int", shape)
        return tuple(map(hex, array))

    def get_module(self):
        return self._run_command("-get module", "int")

    def get_nmaxmodules(self):
        return self._run_command("-get nmaxmodules", "int")

    def get_sensormaterial(self):
        shape = (self.get_nmodules(),)
        array = self._run_command("-get sensormaterial", "int", shape)
        return tuple(MATERIALS.get(x, x) for x in array)

    def get_sensorthickness(self):
        shape = (self.get_nmodules(),)
        array = self._run_command("-get sensorthickness", "int", shape)
        return tuple(array)

    def get_sensorwidth(self):
        command = "-get sensorwidth"
        self._check_version(">=4.0.0", command)
        shape = (self.get_nmodules(),)
        array = self._run_command(command, "int", shape)
        return tuple(array)

    def get_systemnum(self):
        return self._run_command("-get systemnum", "int")

    def get_temperature(self):
        command = "-get temperature"
        self._check_version(">=4.0.0", command)
        shape = (self.get_nmodules(),)
        array = self._run_command(command, "float", shape)
        return tuple(array)

    def get_testversion(self):
        command = "-get testversion"
        self._check_version(">=4.0.0", command)
        return self._run_command(command, "char", (7,))

    # General commands

    def select_module(self, module_id):
        command = "-module {}".format(module_id)
        self._run_command(command, "int")

    def select_all_modules(self):
        self.select_module(0xffff)

    def set_nmodules(self, nmodules):
        command = "-nmodules {}".format(nmodules)
        self._run_command(command, "int")

    def reset(self):
        self._run_command("-reset", "int")

    # Acquisition control

    def get_delayafterframe(self):
        time_100ns = self._run_command("-get delafter", "long long")
        return float(time_100ns) / 1e7

    def set_delayafterframe(self, time=0.):
        time_100ns = int(time * 1e7)
        command = "-delafter {}".format(time_100ns)
        self._run_command(command, "int")

    def get_nframes(self):
        return self._run_command("-get frames", "int")

    def set_nframes(self, nframes=1):
        command = "-frames {}".format(nframes)
        self._run_command(command, "int")

    def get_nbits(self):
        return self._run_command("-get nbits", "int")

    def set_nbits(self, nbits=24):
        command = "-nbits {}".format(nbits)
        self._run_command(command, "int")

    def get_exposure_time(self):
        time_100ns = self._run_command("-get time", "long long")
        return float(time_100ns) / 1e7

    def set_exposure_time(self, time=1.):
        time_100ns = int(time * 1e7)
        command = "-time {}".format(time_100ns)
        self._run_command(command, "int")

    def get_status(self):
        bits = self._run_command("-get status", "int")
        args = bits & 0x00001, bits & 0x00008, bits & 0x10000
        return Status(*map(bool, args))

    def get_readouttimes(self):
        command = "-get readouttimes"
        self._check_version(">=4.0.0", command)
        array = self._run_command(command, "long long", (4,))
        return dict(zip([24, 16, 8, 4], array))

    def start(self):
        self._run_command("-start", "int")

    def stop(self):
        self._run_command("-stop", "int")

    def readout(self, n=1):
        command = "-readout {}".format(n)
        if n > 1:
            self._check_version(">=4.0.0", command)
        shape = n, self.get_nchannels()
        return self._run_command(command, "int", shape)

    def raw_readout(self, nbits=None, nchannels=None):
        command = "-readoutraw"
        self._check_version("<=3.0.0", command)
        # Get nbits argument
        if nbits is None:
            nbits = self.get_nbits()
        # Get nchannels argument
        if nchannels is None:
            nchannels = self.get_nchannels()
        # Get shape
        nbits_to_factor = {24: 1, 16: 2, 8: 4, 4: 8}
        shape = (nchannels // nbits_to_factor[nbits],)
        # Run the command
        array = self._run_command(command, "int", shape)
        # Decode result
        return convert(array, nbits)

    # Detector settings

    def get_energy(self):
        shape = (self.get_nmodules(),)
        array = self._run_command("-get energy", "float", shape)
        return tuple(array)

    def set_energy(self, energy=8.05):
        command = "-energy {}".format(energy)
        self._run_command(command, "int")

    def get_energymin(self):
        shape = (self.get_nmodules(),)
        array = self._run_command("-get energymin", "float", shape)
        return tuple(array)

    def get_energymax(self):
        shape = (self.get_nmodules(),)
        array = self._run_command("-get energymax", "float", shape)
        return tuple(array)

    def get_kthresh(self):
        shape = (self.get_nmodules(),)
        array = self._run_command("-get kthresh", "float", shape)
        return tuple(array)

    def set_kthresh(self, kthresh=6.4):
        command = "-kthresh {}".format(kthresh)
        self._run_command(command, "int")

    def get_kthreshmin(self):
        shape = (self.get_nmodules(),)
        array = self._run_command("-get kthreshmin", "float", shape)
        return tuple(array)

    def get_kthreshmax(self):
        shape = (self.get_nmodules(),)
        array = self._run_command("-get kthreshmax", "float", shape)
        return tuple(array)

    def set_kthresh_and_energy(self, kthresh=6.4, energy=8.05):
        command = "-kthreshenergy {} {}".format(kthresh, energy)
        self._run_command(command, "int")

    def load_predefined_settings(self, element):
        element = element.capitalize().strip()
        if element not in ("Cu", "Mo", "Cr", "Ag"):
            raise ValueError("Element {} is not supported".format(element))
        command = "-settings {}".format(element)
        self._run_command(command, "int")

    # Data correction

    def badchannelinterpolation_enabled(self):
        command = "-get badchannelinterpolation"
        value = self._run_command(command, "int")
        return bool(value)

    def enable_badchannelinterpolation(self, enable):
        command = "-badchannelinterpolation {}".format(int(enable))
        self._run_command(command, "int")

    def flatfieldcorrection_enabled(self):
        command = "-get flatfieldcorrection"
        value = self._run_command(command, "int")
        return bool(value)

    def enable_flatfieldcorrection(self, enable):
        command = "-flatfieldcorrection {}".format(int(enable))
        self._run_command(command, "int")

    def get_flatfield(self):
        shape = (self.get_nchannels(),)
        return self._run_command("-get flatfield", "int", shape)

    def load_flatfield(self, slot):
        command = "-loadflatfield {}".format(slot)
        self._check_version(">=4.0.0", command)
        self._run_command(command, "int")

    def set_flatfield(self, slot, correction):
        command = "-flatfield {}".format(slot)
        self._check_version(">=4.0.0", command)
        correction = np.array(correction, dtype="uint32")
        correction.shape = (self.get_nchannels(),)
        payload = correction.tobytes()
        self._run_command(command, "int", payload=payload)

    def get_flatfield_cutoff(self):
        return self._run_command("-get cutoff", "int")

    def ratecorrection_enabled(self):
        command = "-get ratecorrection"
        value = self._run_command(command, "int")
        return bool(value)

    def enable_ratecorrection(self, enable):
        command = "-ratecorrection {}".format(int(enable))
        self._run_command(command, "int")

    def get_ratecorrection_deadtime(self):
        shape = (self.get_nmodules(),)
        tau_ns = self._run_command("-get tau", "float", shape)
        return tuple(tau_ns / 1e9)

    def set_ratecorrection_deadtime(self, tau):
        # Use predefined values
        if tau < 0:
            tau_ns = -1
        # Use provided argument
        else:
            tau_ns = int(tau * 1e9)
        command = "-tau {}".format(tau_ns)
        self._run_command(command, "int")

    # Trigger / Gate

    def enable_continuoustrigger(self, enable):
        command = "-conttrigen {}".format(int(enable))
        self._run_command(command, "int")

    def continuoustrigger_enabled(self):
        command = "-get conttrig"
        value = self._run_command(command, "int")
        return bool(value)

    def enable_singletrigger(self, enable):
        command = "-trigen {}".format(int(enable))
        self._run_command(command, "int")

    def singletrigger_enabled(self):
        command = "-get trig"
        value = self._run_command(command, "int")
        return bool(value)

    def get_delaybeforeframe(self):
        command = "-get delbef"
        delay_100ns = self._run_command(command, "long long")
        return delay_100ns / 1e7

    def set_delaybeforeframe(self, delay=0.):
        delay_100ns = int(delay * 1e7)
        command = "-delbef {}".format(delay_100ns)
        self._run_command(command, "int")

    def enable_gatemode(self, enable):
        command = "-gateen {}".format(int(enable))
        self._run_command(command, "int")

    def gatemode_enabled(self):
        command = "-get gate"
        value = self._run_command(command, "int")
        return bool(value)

    def get_ngates(self):
        command = "-get gates"
        return self._run_command(command, "int")

    def set_ngates(self, ngates=1):
        command = "-gates {}".format(ngates)
        self._run_command(command, "int")

    def get_inputpolarity(self):
        command = "-get inpol"
        self._check_version("<=3.0.0", command)
        value = self._run_command(command, "int")
        return Polarity(value)

    def set_inputpolarity(self, polarity):
        command = "-inpol {}".format(int(polarity))
        self._check_version("<=3.0.0", command)
        self._run_command(command, "int")

    def get_outputpolarity(self):
        command = "-get outpol"
        self._check_version("<=3.0.0", command)
        value = self._run_command(command, "int")
        return Polarity(value)

    def set_outputpolarity(self, polarity):
        command = "-outpol {}".format(int(polarity))
        self._check_version("<=3.0.0", command)
        self._run_command(command, "int")

    # Debugging

    def start_logging(self):
        command = "-log start"
        self._run_command(command, "int")

    def stop_logging(self):
        command = "-log stop"
        size = self._run_command(command, "int")
        command = "-log read"
        return self._run_command(command, "char", (size,))

    def logging_running(self):
        command = "-log status"
        self._check_version(">=4.0.1", command)
        value = self._run_command(command, "int")
        return bool(value)

    def test_pattern(self):
        command = "-testpattern"
        shape = (self.get_nchannels(),)
        return self._run_command(command, "int", shape)
