import os
import sys
import time
import bisect
import datetime
from warnings import warn

import gevent
from gevent import lock
import serial.serialutil as serial

from bliss.comm.util import get_comm, SERIAL
from bliss.common.event import dispatcher
from bliss.common.data_manager import ScanFile
from bliss.common.logtools import *
from bliss import global_map

__all__ = ["LinkamDsc", "LinkamScanFile", "LinkamScan"]


class LinkamScanFile(ScanFile):
    def __init__(self, filename):
        self.scan_n = 1

        # find next scan number
        if os.path.exists(filename):
            with file(filename) as f:
                for line in iter(f.readline, ""):
                    if line.startswith("#S"):
                        self.scan_n += 1

        self.file_obj = file(filename, "a+")

    def write_header(self):
        self.file_obj.write(
            "#S %d\n#D %s\n"
            % (self.scan_n, datetime.datetime.now().strftime("%a %b %d %H:%M:%S %Y"))
        )
        self.file_obj.flush()


class LinkamScan:
    def __init__(self, linkamDevice, filename):
        self._linkamDevice = linkamDevice
        self._scanFile = LinkamScanFile(filename)
        dispatcher.connect(self.handle_data_event, "linkam_profile_data", linkamDevice)
        dispatcher.connect(
            self.handle_startstop_event, "linkam_profile_start", linkamDevice
        )
        dispatcher.connect(
            self.handle_startstop_event, "linkam_profile_end", linkamDevice
        )

    def handle_data_event(self, data, signal=None, sender=None):
        if signal == "linkam_profile_data":
            self._scanFile.write(
                "{0} {1} {2} {3}\n".format(data[0], data[1], data[2], data[3])
            )

    def handle_startstop_event(self, signal=None, sender=None):
        if signal == "linkam_profile_start":
            self._scanFile.write_header()
        elif signal == "linkam_profile_end":
            self._scanFile.close()
            dispatcher.disconnect(
                self.handle_data_event, "linkam_profile_data", self._linkamDevice
            )
            dispatcher.disconnect(
                self.handle_startstop_event, "linkam_profile_start", self._linkamDevice
            )
            dispatcher.disconnect(
                self.handle_startstop_event, "linkam_profile_end", self._linkamDevice
            )


class LinkamDsc:
    def __init__(self, name, config):
        """ Linkam controller with either hot stage or dsc stage
            config_-- controller configuration,
        """
        self.name = name
        try:
            self._cnx = get_comm(config, SERIAL, baudrate=19200, eol="\r", timeout=10)
        except ValueError:
            if "serial_url" in config:
                warn(
                    "'serial_url' keyword is deprecated. Use 'serial' instead",
                    DeprecationWarning,
                )
                comm_cfg = {"serial": {"url": config["serial_url"]}}
                self._cnx = get_comm(comm_cfg, baudrate=19200, eol="\r", timeout=10)
            else:
                raise ValueError("Must specify serial")

        global_map.register(
            self, parents_list=["controllers"], children_list=[self._cnx], tag=self.name
        )

        # Possible values of the status byte
        self.STOPPED = 0x1
        self.HEATING = 0x10
        self.COOLING = 0x20
        self.HOLDINGLIMIT = 0x30
        self.HOLDINGTIME = 0x40
        self.HOLDINGTEMP = 0x50

        self.StatusToString = {
            self.STOPPED: "Stopped",
            self.HEATING: "Heating",
            self.COOLING: "Cooling",
            self.HOLDINGLIMIT: "Holding the limit time",
            self.HOLDINGTEMP: "Holding the current temperature",
        }
        # Linkam error codes
        self.LINKAM_COOLING_TOOFAST = 0x01
        self.LINKAM_OPEN_CIRCUIT = 0x02
        self.LINKAM_POWER_SURGE = 0x04
        self.LINKAM_EXIT_300 = 0x08
        self.LINKAM_LINK_ERROR = 0x20
        self.LINKAM_OK = 0x80

        self.ErrorToString = {
            self.LINKAM_COOLING_TOOFAST: "Cooling too fast",
            self.LINKAM_OPEN_CIRCUIT: "Stage not connected or sensor is open circuit",
            self.LINKAM_POWER_SURGE: "Current protection due to overload",
            self.LINKAM_EXIT_300: "No Exit (300 TS 1500 tried to exit profile at a temperature > 300 degrees)",
            self.LINKAM_LINK_ERROR: "Problems with RS-232 data transmission - RESET Linkam !",
            self.LINKAM_OK: "OK",
        }

        self._maximumTemp = config.get("max_temp", 1500.0)
        self._minimumTemp = config.get("min_temp", -196.0)
        self._model = config.get("model", "T95")
        self._profile_task = None
        self._lock = lock.Semaphore()
        self._hasDSC = self._hasDscStage()
        (self._state, self._errCode, _, _) = self._getStatus()
        self._temperature = self.getTemperature()
        self._limit = self._temperature
        self._rampNb = 1
        self._rate = 10
        self._holdTime = 1
        self._dscSamplingRate = 0.3
        self._statusString = None
        self._pumpSpeed = 0
        self._dscValue = 0.
        self._startingRamp = 1
        self._pollTime = 0.1
        self._pipe = os.pipe()
        self._hold = True
        self._tstamp = 0
        self._profileCompleteCallback = None
        self._profileData = [[]]

    def subscribe(self, cbfunc):
        self._profileCompleteCallback = cbfunc

    def _clearBuffer(self):
        """ Sends a "B" command to clear the buffers """
        log_debug(self, "clearBuffer() called")
        self._cnx.write_readline("B\r")

    def hold(self):
        """ If the controller is heating or cooling, will hold at the current
            temperature until either a heat or a cool command is received.
        """
        log_debug(self, "hold() called")
        self._cnx.write_readline("O\r")

    def start(self):
        """ Start heating or cooling at the rate specified by the Rate setting """
        log_debug(self, "start called")
        self._cnx.write_readline("S\r")

    def stop(self):
        """ Informs the controller to stop heating or cooling. """
        log_debug(self, "stop() called")
        if self._profile_task is None:
            self._doStop()
        else:
            os.write(self._pipe[1], "|")

    def _doStop(self):
        self._cnx.write_readline("E\r")

    def heat(self):
        """ Forces heating. If while heating the controller finds that the temperature
            is at the limit it will hold at that value, otherwise it will heat up to the
            maximum temperature and stop.
        """
        log_debug(self, "heat() called")
        self._cnx.write_readline("H\r")

    def cool(self):
        """ Forces cooling. If while cooling the controller finds that the temperature
            is at the limit it will hold at that value, otherwise it will cool to the
            minimum temperature and stop. 
        """
        log_debug(self, "cool() called")
        self._cnx.write_readline("C\r")

    def setPumpAutomatic(self):
        """ Set pump in automatic mode, where the pump speed is controlled by the controller """
        log_debug(self, "pump automatic() called")
        self._cnx.write_readline("Pa0\r")

    def setPumpManual(self):
        """ Set pump in manual mode, where the pump speed is controlled by the PumpSpeed setting """
        log_debug(self, "pumpManual() called")
        self._cnx.write_readline("Pm0\r")

    @property
    def pollTime(self):
        return self._pollTime

    @pollTime.setter
    def pollTime(self, time):
        self._pollTime = time

    @property
    def startingRamp(self):
        return self._startingRamp

    @startingRamp.setter
    def startingRamp(self, ramp):
        self._startingRamp = ramp

    @property
    def profileData(self):
        return self._profileData

    @profileData.setter
    def profileData(self, profile):
        self._profileData = profile

    @property
    def pumpSpeed(self):
        return self._pumpSpeed

    @pumpSpeed.setter
    def pumpSpeed(self, speed):
        """ Sets the liquid nitrogen pump speed.
            The speed can be 0 to 30
        """
        if speed < 0 or speed > 30:
            raise ValueError("speed {0} out of range (0-30)".format(speed))
        self._pumpSpeed = speed
        log_debug(self, "pump speed() P{0}".format(chr(speed + 48)))
        self._cnx.write_readline("P{0}\r".format(chr(speed + 48)))

    @property
    def rampNumber(self):
        return self._rampNb

    @property
    def rampLimit(self):
        return self._limit

    @rampLimit.setter
    def rampLimit(self, limit):
        """ Set limit / set point temperature.
            The limit is expressed to a resolution of 0.1degC, max value 99.9
        """
        if limit > self._maximumTemp or limit < self._minimumTemp:
            raise ValueError("Temperature ramp limit {0} out of range ".format(limit))
        self._limit = limit
        log_debug(self, "rampLimit() Set limit to {0}".format(self._limit))
        self._cnx.write_readline(("L1%d\r" % int(round(limit * 10.0))))

    @property
    def rampHoldTime(self):
        return self._holdTime

    @rampHoldTime.setter
    def rampHoldTime(self, time):
        """ Set the profile hold time (in seconds).
        """
        self._holdTime = time

    @property
    def rampRate(self):
        return self._rate

    @rampRate.setter
    def rampRate(self, rate):
        """ Set rate (in degrees/minute).
            The heating/cooling rate is expressed to a resolution of 0.01degC/min.
            The maximum is 99.99degC/min.
         """
        if rate > 99.99:  # check this
            raise ValueError(
                "Temperature ramp limit {0} out of range (max is 99.99)".format(rate)
            )
        self._rate = rate
        log_debug(self, "rampRate() set to {0}".format(rate))
        self._cnx.write_readline(("R1%d\r" % int(round(rate * 100))))

    def _hasDscStage(self):
        reply = self._cnx.write_readline(chr(0xef) + "S\r").strip()
        log_debug(self, "hasDscStage() reply was " + reply)
        return True if reply[0:3] == "DSC" else False

    def setTemperature(self, temp):
        # This might not work for all controllers
        if (
            self._profile_task is not None
            or self._state == self.HEATING
            or self._state == self.COOLING
        ):
            log_error(self, "already running")
        else:
            self.rampLimit = temp

    #            self.start();

    def _extractTemperature(self, hexString):
        """ Extracts the current temperature from a four byte string (from either a T or D reply)
            Positive values have range 0 to 0x3A98 representing 0 to 15000
            Negative values from -1960 to -1 are represented as 0xF858 (63576) to 0xFFFF (65535).
        """
        try:
            value = int(hexString, 16)
            if value > 32768:
                value -= 65536
            return float(value / 10.0)
            # Sometimes the temperature part of a reply string seems to be invalid
            # even though sensible error and status values have been returned so we
            # catch the normally uncaught ValueError to deal with this
        except ValueError:
            log_error(self, "invalid literal for int() with base 16: %s" % hexString)
            raise ValueError("invalid literal for int() with base 16: %s" % hexString)

    def _temperatureData(self):
        reply = self._getRawStatus()
        temperature = self._extractTemperature(reply[6:])
        if temperature < -273:
            raise ValueError(
                "temperature reading less than -273, check that the heating stage is connected and switched on"
            )
        #        log_debug(self, "getTemperature() returned {0}".format(temperature))
        return temperature

    def getTemperature(self):
        """
        If a profile is running return the last cached temperature reading
        so as not to disturb the timing of the profile (this assumes the
        profile thread is updating the temperature in its loop)
        """
        if self._profile_task is None:
            return self._temperatureData()
        else:
            return self._temperature

    def _extractDscValue(self, hexString):
        """ Extracts DCS value from a four byte string.
            Positive values have range 0 to 7FFF representing 0 to 32764
            Values 32765, 32766 and 32767 have special meaning.
            Negative values from -32767 to -1 are represented as 8001 (32769) to FFFF (65535).
            NB value 32768 is not mentioned in the instructions and so will, of course, never appear.
         """
        try:
            value = int(hexString, 16)
            if value > 32768:
                value -= 65536
            return value
        except ValueError:
            log_error(self, "invalid literal for int() with base 16: %s" % hexString)
            raise ValueError("invalid literal for int() with base 16: %s" % hexString)

    def _dscData(self):
        reply = self._cnx.write_readline("D\r")
        tstamp = self._timeStamp()
        temperature = self._extractTemperature(reply[0:4])
        dscValue = self._extractDscValue(reply[4:8])
        if temperature < -273:
            raise ValueError(
                "temperature reading less than -273, check that the heating stage is connected and switched on"
            )
        if dscValue == 32765:  # if the buffer is full then clear it
            self._clearBuffer()
        return (temperature, dscValue, tstamp)

    def getDscData(self):
        """ Get temperature & DSC Data  """
        if not self._hasDSC:
            raise Exception("No DSC stage connected")

        if self._profile_task is None:
            temperature, dscValue, _ = self._dscData()
            return (temperature, dscValue, -1.0)
        else:
            return (self._temperature, self._dscValue, self._tstamp)

    def _getRawStatus(self):
        """ Get the Linkam status """
        return self._cnx.write_readline("T\r")

    def _getStatus(self):
        """ The raw status also includes the current temperature
            also generate the time stamp close to the reading
            required for file saving
        """
        reply = self._getRawStatus()
        tstamp = self._timeStamp()
        state = ord(reply[0])
        errcode = ord(reply[1])
        temperature = self._extractTemperature(reply[6:])
        #        log_debug(self, "state {0}, errcode {1}".format(state, errcode))
        return (state, errcode, temperature, tstamp)

    def isProfileRunning(self):
        return False if self._profile_task is None else True

    def _getStatusString(self, state, err):
        if err == self.LINKAM_OK:
            return self.StatusToString.get(state, "")
        else:
            return self.ErrorToString.get(err, "")

    def _updateState(self, state, errcode, temperature, dsc, tstamp):
        """ Use this to set state whilst profile is running """
        if self._profile_task is not None:
            with self._lock:
                self._state = state
                self._errCode = errcode
                self._temperature = temperature
                self._tstamp = tstamp
                self._dscValue = dsc
        if tstamp is not None:
            self._tstamp = self._tstamp - self._start_tstamp
            #            log_debug(self, "sending ts, temp, dsc {0},{1},{2}".format(self._tstamp, self._temperature, self._dscValue))
            dispatcher.send(
                "linkam_profile_data",
                self,
                (tstamp, self._tstamp, self._temperature, self._dscValue),
            )

    def _getState(self):
        """ return the Linkam state, errorcode and current temperature whilst profile is running """
        if self._profile_task is not None:
            (state, errcode, temperature, tstamp) = self._getStatus()
            return (state, errcode, temperature, tstamp)
        else:
            None

    def status(self):
        if self._profile_task is None:
            (state, errcode, _, _) = self._getStatus()
            status = self._getStatusString(state, errcode)
        else:
            status = (
                self._getStatusString(self._state, self._errCode)
                + ": Profile is running"
            )
        #        log_debug(self, "status() {0}".format(status))
        return status

    @property
    def dscSamplingRate(self):
        return self._dscSamplingRate

    @dscSamplingRate.setter
    def dscSamplingRate(self, rate):
        """ Set sampling rate for DSC (.3, .6, .9, 1.5, 3, 6, 9, 15, 30, 60, 90, or 150) """
        if not self._hasDSC:
            raise Exception("No DSC stage connected")

        possible_range = (.3, .6, .9, 1.5, 3, 6, 9, 15, 30, 60, 90, 150)
        index = bisect.bisect_right(possible_range, rate, 0, 11)
        value = possible_range[index] / 0.05
        log_debug(self, "dscSamplingRate() setting %f" % value)
        self._cnx.write_readline(chr(0xe7) + "%4d\r" % int(round(value)))

    def profile(self, ramps):
        """ Perform a temperature profile which is a series of ramps 
            Loads the ramp list (an array of tuples) and executes the profile in 
            a gevent thread. A ramp is a tuple (rate,limit,holdtime)
        """
        if self._profile_task is None:
            with self._lock:
                self._ramps = ramps
                self._profile_task = gevent.spawn(self._run_profile, ramps)
        else:
            raise Exception("Linkam is already doing a profile. Use stop first")

    def _run_profile(self, ramps):
        currentRamp = 1
        abort = "+"
        self._start_tstamp = 0.0
        try:
            state, errcode, temperature, _ = self._getState()  # get initial state
            if errcode != self.LINKAM_OK:
                log_error(
                    self,
                    "Profile received Linkam errcode: {0}".format(
                        self.ErrorToString.get(errCode)
                    ),
                )
                temperature = -273.15
            self._updateState(state, errcode, temperature, 0.0, None)
            for (rate, limit, holdTime) in ramps:  # get ramp and load it
                log_debug(
                    self,
                    "loading rate={0} limit={1} holdtime={2}".format(
                        rate, limit, holdTime
                    ),
                )
                with self._lock:
                    self._rampNb = currentRamp
                    self.rampRate = rate
                    self.rampLimit = limit
                    self.rampHoldTime = holdTime
                if self._startingRamp == currentRamp:
                    self._clearBuffer()  # empty Linkam buffer ready to collect data
                if currentRamp == 1:
                    dispatcher.send("linkam_profile_start", self)
                    self.start()  # start ramping
                    state, errcode, temperature, self._start_tstamp = (
                        self._getState()
                    )  # get initial state
                    if errcode != self.LINKAM_OK:
                        log_error(
                            self,
                            "Profile received Linkam errcode: {0}".format(
                                self.ErrorToString.get(errCode)
                            ),
                        )
                        temperature = -273.15
                    self._updateState(state, errcode, temperature, 0.0, None)
                while 1:
                    fd, _, _ = gevent.select.select([self._pipe[0]], [], [], 0.1)
                    if fd:
                        abort = os.read(self._pipe[0], 1)
                        break  # abort profile
                    newState, errcode, temperature, tstamp = self._getState()
                    if errcode != self.LINKAM_OK:
                        log_error(
                            self,
                            "Profile received Linkam errcode: {0}".format(
                                self.ErrorToString.get(errCode)
                            ),
                        )
                        temperature = -273.15
                    if self._hasDSC:
                        temperature, dsc, tstamp = self._dscData()
                        if currentRamp >= self._startingRamp:
                            if (
                                temperature != 32767 and dsc != 32767
                            ):  # no valid data we're sampling too quickly
                                self._updateState(
                                    newState, errcode, temperature, dsc, tstamp
                                )
                        else:
                            self._updateState(
                                newState, errcode, temperature, 0.0, tstamp
                            )
                    else:
                        self._updateState(newState, errcode, temperature, 0.0, tstamp)

                    if newState != state and (
                        newState == self.HOLDINGLIMIT or newState == self.HOLDINGTEMP
                    ):
                        log_debug(self, "changed state to {0}".format(newState))
                        if holdTime > 0.0:
                            state = newState
                            log_debug(
                                self, "start to do hold for {0}seconds".format(holdTime)
                            )
                            self._hold = True
                            gevent.spawn(self._run_hold_timer, holdTime)
                            while self._hold:
                                fd, _, _ = gevent.select.select(
                                    [self._pipe[0]], [], [], 0.1
                                )
                                if fd:
                                    abort = os.read(self._pipe[0], 1)
                                    break
                                newState, errcode, temperature, tstamp = (
                                    self._getState()
                                )
                                if errcode != self.LINKAM_OK:
                                    log_error(
                                        self,
                                        "Profile received Linkam errcode: {0}".format(
                                            self.ErrorToString.get(errCode)
                                        ),
                                    )
                                    temperature = -273.15
                                if self._hasDSC:
                                    if currentRamp >= self._startingRamp:
                                        temperature, dsc, tstamp = self._dscData()
                                        if (
                                            temperature != 32767 and dsc != 32767
                                        ):  # no valid data we're sampling too quickly
                                            self._updateState(
                                                newState,
                                                errcode,
                                                temperature,
                                                dsc,
                                                tstamp,
                                            )
                                    else:
                                        self._updateState(
                                            newState, errcode, temperature, 0.0, tstamp
                                        )
                                else:
                                    self._updateState(
                                        newState, errcode, temperature, 0.0, tstamp
                                    )
                        log_debug(
                            self,
                            "starting next ramp {0} state {1} newstate {2}".format(
                                currentRamp + 1, state, newState
                            ),
                        )
                        break  # start the next ramp
                    state = newState

                currentRamp += 1
                if abort == "|":
                    break  # abort the profile
        except:
            sys.excepthook(*sys.exc_info())
            #            log_error(self, self.ErrorToString.get(errCode))
            self.rampLimit = self._temperature
        finally:
            log_debug(self, "doing finally")
            self.rampLimit = self._temperature
            dispatcher.send("linkam_profile_end", self)
            self._profileCompleteCallback()
            with self._lock:
                self._profile_task = None

    def _run_hold_timer(self, holdTime):
        log_debug(self, "starting hold timer")
        rc = gevent.select.select([self._pipe[0]], [], [], holdTime)
        with self._lock:
            log_debug(self, "select finished rc = {0}".format(rc))
            self._hold = False

    def _timeStamp(self):
        theDate = str(datetime.datetime.now())
        dt = datetime.datetime.strptime(theDate, "%Y-%m-%d %H:%M:%S.%f")
        return time.mktime(dt.timetuple()) + (dt.microsecond / 1000000.0)
