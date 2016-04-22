___all__ = ['LinkamDsc']

import time
import os
import gevent
import logging
import bisect
from gevent import lock
import serial.serialutil as serial
from bliss.comm._serial import Serial
from bliss.comm.tcp import Tcp

class LinkamDsc(object):
    
    def __init__(self,name,config):
        """ Linkam controller with either hot stage or dsc stage
            config_-- controller configuration,
        """
        self.name = name
        self._logger = logging.getLogger(str(self))
        logging.basicConfig(level=10)
        if "serial_url" in config:
            self._cnx = Serial(config['serial_url'], 19200, bytesize=8, parity='N', stopbits=1, eol='\r', timeout=10)
        else:
            raise ValueError, "Must specify serial_url"

        #Possible values of the status byte
        self.STOPPED = 0x1
        self.HEATING = 0x10
        self.COOLING = 0x20
        self.HOLDINGLIMIT = 0x30
        self.HOLDINGTIME  = 0x40
        self.HOLDINGTEMP  = 0x50

        self.StatusToString = {
            self.STOPPED : "Stopped",
            self.HEATING : "Heating",
            self.COOLING : "Cooling",
            self.HOLDINGLIMIT : "Holding at the limit or limit reached end of ramp",
            self.HOLDINGTIME  : "Holding the limit time",
            self.HOLDINGTEMP  : "Holding the current temperature",
        }
        # Linkam error codes
        self.LINKAM_COOLING_TOOFAST = 0x01
        self.LINKAM_OPEN_CIRCUIT    = 0x02
        self.LINKAM_POWER_SURGE     = 0x04
        self.LINKAM_EXIT_300        = 0x08
        self.LINKAM_LINK_ERROR      = 0x20
        self.LINKAM_OK              = 0x80

        self.ErrorToString = {
            self.LINKAM_COOLING_TOOFAST : "Cooling too fast",
            self.LINKAM_OPEN_CIRCUIT : "Stage not connected or sensor is open circuit",
            self.LINKAM_POWER_SURGE : "Current protection due to overload",
            self.LINKAM_EXIT_300 : "No Exit (300 TS 1500 tried to exit profile at a temperature > 300 degrees)",
            self.LINKAM_LINK_ERROR : "Problems with RS-232 or TCP data transmission - RESET Linkam !",
            self.LINKAM_OK : "OK"
        }

        self._maximumTemp = config.get('max_temp', 1500.0)
        self._minimumTemp = config.get('min_temp', -196.0)
        self._model = config.get('model', "T95")
        self._profile_task = None
        self._lock = lock.Semaphore()
        self._hasDSC = self._hasDscStage()
        self._state = self.state()
        self._temperature = self._limit = self.getTemperature()
        self._rampNb = 1
        self._rate = 10
        self._holdTime = 1
        self._dscSamplingRate = 0.3;
        self._pumpSpeed = 0
        self._dscValue = 0
        self._startingRamp = 2
        self._pipe = os.pipe()

    def _clearBuffer(self):
        """ Sends a "B" command to clear the buffers """
        self._logger.debug("clearBuffer() called")
        self._cnx.write_readline("B\r")

    def hold(self):
        """ If the controller is heating or cooling, will hold at the current
            temperature until either a heat or a cool command is received.
        """
        self._logger.debug("hold() called")
        self._cnx.write_readline("O\r")

    def start(self):
        """ Start heating or cooling at the rate specified by the Rate setting """
        self._logger.debug("start called")
        self._cnx.write_readline("S\r")

    def stop(self):
        """ Informs the controller to stop heating or cooling. """
        self._logger.debug("stop() called");
        if self._profile_task == None:
            self._doStop()
        else:
            os.write(self._pipe[1],'|')

    def _doStop(self):
        self._cnx.write_readline("E\r");

    def heat(self):
        """ Forces heating. If while heating the controller finds that the temperature
            is at the limit it will hold at that value, otherwise it will heat up to the
            maximum temperature and stop.
        """
        self._logger.debug("heat() called");
        self._cnx.write_readline("H\r");

    def cool(self):
        """ Forces cooling. If while cooling the controller finds that the temperature
            is at the limit it will hold at that value, otherwise it will cool to the
            minimum temperature and stop. 
        """
        self._logger.debug("cool() called");
        self._cnx.write_readline("C\r");

    def setPumpAutomatic(self):
        """ Set pump in automatic mode, where the pump speed is controlled by the controller """
        self._logger.debug("pump automatic() called");
        self._cnx.write_readline("Pa0\r")

    def setPumpManual(self):
        """ Set pump in manual mode, where the pump speed is controlled by the PumpSpeed setting """
        self._logger.debug("pumpManual() called");
        self._cnx.write_readline("Pm0\r")

    @property
    def startingRamp(self):
        return self._startingRamp

    @startingRamp.setter
    def startingRamp(self,ramp):
        self._startingRamp = ramp

    @property
    def pumpSpeed(self):
        print "in pumpspeed getter", self._pumpSpeed
        return self._pumpSpeed

    @pumpSpeed.setter
    def pumpSpeed(self, speed):
        """ Sets the liquid nitrogen pump speed. 
            The speed can be 0 to 30
        """
        print "pumpspeed setter {0}".format(self._pumpSpeed)
        if speed < 0 or speed > 30:
            raise ValueError ("speed {0} out of range (0-30)".format(speed))
        self._pumpSpeed = speed
        print "char speed ","P{0}".format(chr(speed+48))
        self._cnx.write_readline("P{0}\r".format(chr(speed+48)))

    @property
    def rampNumber(self):
        return self._rampNb

    @rampNumber.setter
    def rampNumber(self, ramp):
        self._rampNb = ramp

    @property
    def rampLimit(self):
        return self._limit

    @rampLimit.setter
    def rampLimit(self, limit):
        """ Set limit / set point temperature.
            The limit is expressed to a resolution of 0.1degC, max value 99.9
        """
        if limit > self._maximumTemp or limit < self._minimumTemp:
            raise ValueError ("Temperature ramp limit {0} out of range ".format(limit))
        self._limit = limit
        self._cnx.write_readline(("L1%d\r" % int(round(limit * 10.0))))

    @property
    def rampHoldTime(self):
        return self._holdTime

    @rampHoldTime.setter
    def rampHoldTime(self, time):
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
        if rate > 99.99: #check this
            raise ValueError ("Temperature ramp limit {0} out of range (max is 99.99)".format(rate))
        self._rate = rate
        print "setting ramp rate"
        self._cnx.write_readline(("R1%d\r" % int(round(rate*100))));

    def _hasDscStage(self):
        reply = self._cnx.write_readline(chr(0xef) + "S\r")
        self._logger.debug("hasDscStage() reply was " + reply)
        return True if reply[0:3] == "DSC" else False

    def setStatusString(self, status):
        self.statusString = status

    def _getStatusString(self):
        """ Get the Linkam status """
        reply = self._cnx.write_readline("T\r")
        print [ord(c) for c in reply]
        return reply

    def setTemperature(self, temp):
        # This might not work for all controllers
        if self._profile_task != None or self._state == self.HEATING or self._state == self.COOLING:
            self._logger.error("already running")
        else:
            self.rampLimit = temp
            self.start();
        
    def getTemperature(self):
        """
        If a profile is running return the last cached temperature reading
        so as not to disturb the timing of the profile (this assumes the
        profile thread is updating the temperature in its loop)
        """
        if self._profile_task != None:
            with self._lock:
                return self._temperature
        else:
            reply = self._getStatusString()
            temperature = self._extractTemperature(reply[6:])
            if temperature < -273:
                raise ValueError ("temperature reading less than -273, check that the heating stage is connected and switched on")
            self._logger.debug("getTemperature() returned {0}".format(temperature))
            return temperature

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
            self._logger.error("invalid literal for int() with base 16: %s" % hexString)
            raise ValueError ("invalid literal for int() with base 16: %s" % hexString)


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
            return value;
        except ValueError:
            self._logger.error("invalid literal for int() with base 16: %s" % hexString)
            raise ValueError ("invalid literal for int() with base 16: %s" % hexString)

    def getDscData(self):
        """ Get temperature & DSC Data  """
        if not self._hasDSC:
            raise Exception ("No DSC stage connected")

        if self._profile_task != None:
            with self._lock:
                return [self._temperature, self._dscValue]
        else:
            return self._dscData()

    def _dscData(self):
        reply = self._cnx.write_readline("D\r")
        self._temperature = self._extractTemperature(reply[0:4])
        self._dscValue = self._extractDscValue(reply[4:8])
        if self._temperature < -273:
            raise ValueError ("temperature reading less than -273, check that the heating stage is connected and switched on")
        if self._dscValue == 32765: #if the buffer is full then clear it
            self.clearBuffer()
        return [self._temperature, self._dscValue]

    def state(self):
        """ return the Linkam state, errorcode and current temperature """
        reply = self._getStatusString()
        currentstate = ord(reply[0])
        errcode = ord(reply[1])
        self._pumpSpeed = ord(reply[2])-ord('P')-48
        temperature = self._extractTemperature(reply[6:])
        print "state",currentstate, errcode, temperature, self._pumpSpeed
        return [currentstate, errcode, temperature, self._pumpSpeed]

    def status(self):
        reply = self._getStatusString()
        key = ord(reply[0])
        err = ord(reply[1])

        if err == self.LINKAM_OK:
            status = self.StatusToString.get(key, "")
        else:
            status += self.ErrorToString.get(err, "")

        if self._profile_task != None:
            status += ": Profile is running"
        return status

    @property
    def dscSamplingRate(self):
        return self._dscSamplingRate

    @dscSamplingRate.setter
    def dscSamplingRate(self, rate):
        """ Set sampling rate for DSC (.3, .6, .9, 1.5, 3, 6, 9, 15, 30, 60, 90, or 150) """
        if not self._hasDSC:
            raise Exception ("No DSC stage connected")

        possible_range = (.3, .6, .9, 1.5, 3, 6, 9, 15, 30, 60, 90, 150)
        index = bisect.bisect_right(possible_range, rate, 0, 11)
        value = possible_range[index]/0.05
        self._logger.debug("dscSamplingRate() setting %f" % value)
        self._cnx.write_readline(chr(0xe7) + "%4d\r" % int(round(value)))

    def profile(self, ramps):
        """ Perform a temperature profile which is a series of ramps 
            Loads the ramp list (an array of tuples) and executes the profile in 
            a gevent thread. A ramp is a tuple (rate,limit,holdtime)
        """
        print ramps
        for (rate, limit, holdTime) in ramps: # get ramp and load it
            print rate,limit,holdTime

        if self._profile_task is None:
            self._ramps = ramps
            self._profile_task = gevent.spawn(self._run_profile, ramps)
        else:
            raise Exception("Linkam is already doing a profile. Use stop first")

    def _run_profile(self, ramps):
        currentRamp = 1
        abort = '+'
        try:
            state,errcode,self._temperature,_ = self.state() # get initial state
            for (rate, limit, holdTime) in ramps: # get ramp and load it
                print "loading",rate," ",limit," ",holdTime
                self.rampNumber = currentRamp
                self.rampRate = rate
                self.rampLimit = limit
                self.rampHoldTime = holdTime
                if self.startingRamp == currentRamp:
                    self._clearBuffer() #empty Linkam buffer ready to collect data
                if currentRamp == 1: 
                    self.start() # start ramping
                while True:
                    fd,_,_ = gevent.select.select([self._pipe[0]],[],[],0.1)
                    if fd: 
                        abort = os.read(self._pipe[0],1)
                        break # abort profile
                    newState,errcode,self._temperature,_ = self.state()
                    if self._hasDSC:
                        self._temperature, self._dscValue = self._dscData()
                    if errcode != self.LINKAM_OK:
                        raise Exception("Profile failed on ramp %d with error %s" % (currentRamp, self.ErrorToString.get(state)))
                    if newState != state and (state ==self.HEATING or state == self.COOLING) and newState == self.HOLDINGLIMIT:
                        if holdTime > 0:
                            fd,_,_ = gevent.select.select([self._pipe[0]],[],[],holdTime)
                            if fd:
                                print "aborting"
                                abort = os.read(self._pipe[0],1)
                        break # start the next ramp
                    state = newState
                currentRamp += 1
                print "startNext ramp", currentRamp
                if abort == '|': 
                    break
        finally:
            self._doStop()
            self.hold() # abort or last ramp finished
            self._profile_task = None

    def _timeStamp(self):
        theDate=str(datetime.datetime.now())
        dt = datetime.datetime.strptime(theDate, "%Y-%m-%d %H:%M:%S.%f")
        return time.mktime(dt.timetuple()) + (dt.microsecond / 1000000.0)
 