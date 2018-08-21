# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

__all__ = ["NanoBpm", "main"]

import time
import numpy
import struct
import math
import logging
from warnings import warn
from bliss.common.utils import OrderedDict
import gevent
from gevent import lock

from bliss.comm.util import get_comm, TCP


def _config_property(key, doc_str):
    def get(self):
        return self._deviceConfig[key]

    def set(self, value):
        self._deviceConfig[key] = value
        self.setDeviceConfig()

    return property(get, set, doc=doc_str)


def _fit_property(key, doc_str):
    def get(self):
        return self._fitParameters[key]

    def set(self, value):
        self._fitParameters[key] = value
        self.setDeviceParameters()

    return property(get, set, doc=doc_str)


def _v_result_property(key, doc_str):
    def get(self):
        return self._vertFitResultParameters[key]

    def set(self, value):
        self._vertFitResultParameters[key] = value
        self.setDeviceParameters()

    return property(get, set, doc=doc_str)


def _h_result_property(key, doc_str):
    def get(self):
        return self._horFitResultParameters[key]

    def set(self, value):
        self._horFitResultParameters[key] = value
        self.setDeviceParameters()

    return property(get, set, doc=doc_str)


class NanoBpm(object):
    # Errors codes
    NO_ERROR, CODE1, CODE2, CODE3, CODE4, CODE5, CODE6, CODE7, CODE8 = range(9)
    BPP8, BPP16, BPP32 = range(3)

    SETTINGS = _config_property("Settings", "Configuration settings")
    GAIN = _config_property("Gain", "Set device gain")
    OFFSET = _config_property("Offset", "Set device offset")
    LINEINTTIME = _config_property("LineIntTime", "Line time")
    YEND = _config_property("YEnd", "ROI Y end")
    FRAMEINTTIME = _config_property("FrameIntTime", "Frame time")
    YSTART = _config_property("YStart", "ROI Y start")
    XSTART = _config_property("XStart", "ROI X start")
    XEND = _config_property("XEnd", "ROI X end")
    ADCPHASE = _config_property("AdcPhase", "adc phase")
    SUBTRACTDARK = _config_property(
        "SubtractDarkImage", "Subtract the stored dark image"
    )

    MAXDELTACHISQ = _fit_property("MaxDeltaChiSq", "Maximum Delta CHI squared")
    THRESHOLD = _fit_property("Threshold", "Threshold")
    MAXITER = _fit_property("MaxIter", "Maximum nos. of iterations")
    FILTERSPAN = _fit_property("FilterSpan", "Filter span")
    FILTERCTRL = _fit_property(
        "FilterCtrl", "Filter enable/disable & running average/median"
    )

    V_MAXWIDTH = _v_result_property("MaxWidth", "Maximum width allowed in um")
    V_MINWIDTH = _v_result_property("MinWidth", "Minimum width allowed in um")
    V_MINRSQ = _v_result_property("MinRSQ", "Minimum RSQ allowed")
    V_MINAMP = _v_result_property("MinAmp", "Minimum intensity allowed")
    V_CALIBCOEFF = _v_result_property("CalibCoeff", "Calibration coefficient")
    V_CALIBOFF = _v_result_property("CalibOffset", "Calibration offset")

    H_MAXWIDTH = _h_result_property("MaxWidth", "Maximum width allowed in um")
    H_MINWIDTH = _h_result_property("MinWidth", "Minimum width allowed in um")
    H_MINRSQ = _h_result_property("MinRSQ", "Minimum RSQ allowed")
    H_MINAMP = _h_result_property("MinAmp", "Minimum intensity allowed")
    H_CALIBCOEFF = _h_result_property("CalibCoeff", "Calibration coefficient")
    H_CALIBOFF = _h_result_property("CalibOffset", "Calibration offset")

    class DataSelector:
        # DataSelector bit fields
        XCOG = 1
        YCOG = 2
        XPROFILE = 4
        YPROFILE = 8
        HISTOGRAM = 16
        QUADSUM = 32
        XPROFILE_FIT = 64
        YPROFILE_FIT = 128
        # only for stream data
        IMAGE = 256

    class Control:
        # Control word bit fields
        COLLECT_SUM = 1
        STORE_DARK = 2
        PROGRESS_UPDATE = 4

    callbacks = []

    def __init__(self, name, config):
        """ FireFlash hardware controller.

        name -- the controller's name
        config -- controller configuration,
        in this dictionary we need to have:
        command_url -- url of the command port
        control_url -- url of the control port
        """
        # Status bits for getStatus command
        self.StatusBits = {"IDLE": 0, "BUSY": 1, "REMOTE": 2, "STREAMING": 4}
        # Status bits for Remote Data Toggle
        self.ToggleBits = {"OFF": 0, "XFIT": 1, "YFIT": 2, "COG": 4}

        try:
            self.command_socket = get_comm(self.config["command"], ctype=TCP)
        except KeyError:
            command_url = config["command_url"]
            warn(
                "'command_url' keyword is deprecated." " Use 'command: tcp' instead",
                DeprecationWarning,
            )
            comm_cfg = {"tcp": {"url": command_url}}
            self.command_socket = get_comm(comm_cfg)

        try:
            self.control_socket = get_comm(self.config["control"], ctype=TCP)
        except KeyError:
            control_url = config["control_url"]
            warn(
                "'control_url' keyword is deprecated." " Use 'control: tcp' instead",
                DeprecationWarning,
            )
            comm_cfg = {"tcp": {"url": control_url}}
            self.control_socket = get_comm(comm_cfg)

        # Commands ready packed in network byte order
        self.commandReset = struct.pack(">H", 0xAA00)
        self.commandInterrupt = struct.pack(">H", 0xAA01)
        self.commandStatus = struct.pack(">H", 0xAA02)
        self.commandDataToggle = struct.pack(">H", 0xAA03)
        self.commandGetDeviceInfo = struct.pack(">H", 0xAA20)
        self.commandSetConfig = struct.pack(">H", 0xAA22)
        self.commandGetConfig = struct.pack(">H", 0xAA21)
        self.commandGetIntTime = struct.pack(">H", 0xAA23)
        self.commandSetIntTime = struct.pack(">H", 0xAA24)
        self.commandSetParams = struct.pack(">H", 0xAA26)
        self.commandGetParams = struct.pack(">H", 0xAA27)
        self.commandReadImage16 = struct.pack(">H", 0xAA30)
        self.commandReadImage8 = struct.pack(">H", 0xAA31)
        self.commandReadDark16 = struct.pack(">H", 0xAA32)
        self.commandAve16Sum32 = struct.pack(">H", 0xAA33)
        self.commandContinuous = struct.pack(">H", 0xAA37)
        self.commandStreamData = struct.pack(">H", 0xAA3A)

        self._errorCode2string = {
            self.NO_ERROR: "No Error",
            self.CODE1: "Error parsing .ini file",
            self.CODE2: "Could not establish network connection",
            self.CODE3: "Network data transfer failed",
            self.CODE4: "Incorrect FPGA type",
            self.CODE5: "Invalid argument or config param error",
            self.CODE6: "I^C-bus communication error",
            self.CODE7: "Memory initialization error",
            self.CODE8: "I^C-bus initialization error",
        }
        # Device Info structure keys
        self._deviceInfoKeys = [
            "ProcessorType",
            "ProcessorVersion",
            "FPGAType",
            "FPGAVersion",
            "BoardType",
            "BoardVersion",
            "BuidYear",
            "BuildMonth",
            "Buildday",
            "BuildHour",
            "BuildMinute",
            "BuildSecond",
            "SWMajor",
            "SWMinor",
            "SWbuild",
            "FirmWare Major",
            "FirmWareMinor",
            "FirmWareBuild" ", BoardID",
        ]
        # Device configuration parameter keys
        self._deviceConfigKeys = [
            "Settings",
            "Gain",
            "Offset",
            "LineIntTime",
            "YEnd",
            "FrameIntTime",
            "YStart",
            "XStart",
            "XEnd",
            "AdcPhase",
            "SubtractDarkImage",
        ]
        # Image Descriptor keys
        self._imageDescriptorKeys = [
            "FrameNb",
            "IntegrationTime",
            "XSize",
            "YSize",
            "InternalPtr",
        ]
        self._quadConfigKeys = [
            "XCentre",
            "YCentre",
            "WinStartX",
            "WinEndX",
            "WinStartY",
            "WinEndY",
        ]
        self._sensorConfigKeys = ["YSize", "DarkImageSubtract"]
        # device parameter keys
        self._deviceParameterKeys = [
            "configurationKeys",
            "DAC0Keys",
            "DAC1Keys",
            "DAC2keys",
            "DAC3Keys",
            "fitParameterKeys",
            "verticalFitResultCriteria",
            "horizontalFitResultCriteria",
        ]
        self._configurationKeys = [
            "Control",
            "XStart",
            "YStart",
            "Width",
            "Height",
            "Gain",
            "SensorFineOffset",
            "SensorCourseOffset",
            "IntegrationTime",
            "ImageClock",
            "AdcPhase",
            "Orientation",
            "RampInc",
        ]
        self._DAC0Keys = self._DAC1Keys = self._DAC2Keys = self._DAC3Keys = [
            "MinOutVoltage",
            "MaxOutVoltage",
            "MinDACCode",
            "MaxDACCode",
            "Action;",
        ]
        self._fitParameterKeys = [
            "MaxDeltaChiSq",
            "Threshold",
            "MaxIter",
            "FilterSpan",
            "FilterCtrl",
        ]
        self._fitResultCriteriaKeys = [
            "MaxWidth",
            "MinWidth",
            "MinRSQ",
            "MinAmp",
            "CalibCoeff",
            "CalibOffset",
        ]

        self._logger = logging.getLogger("NanoBpmCtrl.NanoBpm")
        logging.basicConfig(level=logging.INFO)
        self._logger.setLevel(logging.DEBUG)
        self._controlWord = 0
        self._nbFramesToSum = 8
        self._thread = None
        self._lock = lock.Semaphore()
        self._remoteDataSelector = 0
        self._frameNbAcquired = -1
        self._actionByte = 0
        self._imageDescriptor = None
        self._configurationParameters = None
        self._dac0Parameters = None
        self._dac1Parameters = None
        self._dac2Parameters = None
        self._dac3Parameters = None
        self._fitParameters = None
        self._vertFitResultParameters = None
        self._horFitResultParameters = None
        self._deviceInfo = self.getDeviceInfo()
        self._deviceConfig = self.getDeviceConfig()
        self._deviceParameters = self.getDeviceParameters()
        # This defines the quad window as the full Image - We do not use the Quad's ROI
        self._quadConfig = OrderedDict(
            zip(
                self._quadConfigKeys,
                (
                    (self._deviceConfig["XEnd"] - self._deviceConfig["XStart"]) / 2,
                    (self._deviceConfig["YEnd"] - self._deviceConfig["YStart"]) / 2,
                    self._deviceConfig["XStart"],
                    self._deviceConfig["XEnd"],
                    self._deviceConfig["YStart"],
                    self._deviceConfig["YEnd"],
                ),
            )
        )

    def subscribe(self, cbfunc):
        self.callbacks.append(cbfunc)

    @property
    def CoG(self):
        return self._CoG

    @property
    def xProfile(self):
        return [float(x) for x in self._xProfile]

    @property
    def yProfile(self):
        return [float(x) for x in self._yProfile]

    @property
    def xFit(self):
        return self._xFit

    @property
    def yFit(self):
        return self._yFit

    @property
    def frameNbAcquired(self):
        return self._frameNbAcquired

    @property
    def nbFramesToSum(self):
        return self._nbFramesToSum

    @nbFramesToSum.setter
    def nbFramesToSum(self, frames):
        """ Set the number of frames to average or sum """
        self._nbFramesToSum = frames

    @property
    def storeDark(self):
        return self._controlWord & self.Control.STORE_DARK

    @storeDark.setter
    def storeDark(self, store_dark):
        """ Enable/disable store dark image mode """
        if store_dark:
            self._controlWord |= self.Control.STORE_DARK
        else:
            self._controlWord &= ~self.Control.STORE_DARK

    @property
    def collectSum32(self):
        return self._controlWord & self.Control.COLLECT_SUM

    @collectSum32.setter
    def collectSum32(self, collect_sum):
        """ Enable/disable collect 32 bit summed images """
        if collect_sum:
            self._controlWord |= self.Control.COLLECT_SUM
        else:
            self._controlWord &= ~self.Control.COLLECT_SUM

    def _checkReplyOK(self, command_sent, reply):
        errorCode = struct.unpack(">I", reply[2:])[0]
        if command_sent != reply[0:2]:
            self._logger.error(
                "Acknowledged the wrong Code: sent {0} replied {1}".format(
                    [ord(c) for c in command_sent], [ord(c) for c in reply[0:2]]
                )
            )
            return False
        elif errorCode != self.NO_ERROR:
            self._logger.error(
                "Acknowledgement error: %s" % self._errorCode2string[errorCode]
            )
            return False
        else:
            return True

    def getDeviceInfo(self):
        """ Get the basic information about the hardware and software configuration of the device
        """
        reply = self.command_socket.write_read(
            self.commandGetDeviceInfo, size=70, timeout=100
        )
        if self._checkReplyOK(self.commandGetDeviceInfo, reply[0:6]):
            data = numpy.ndarray((32,), dtype=">u2", buffer=reply[6:])
            return OrderedDict(zip(self._deviceInfoKeys, data))
        else:
            return None

    def getDeviceConfig(self):
        """ Read the current device configuration from the nanoBpm """
        reply = self.command_socket.write_read(
            self.commandGetConfig, size=28, timeout=10
        )
        if self._checkReplyOK(self.commandGetConfig, reply[0:6]):
            return OrderedDict(
                zip(self._deviceConfigKeys, struct.unpack(">11H", reply[6:]))
            )
        else:
            return None

    def setDeviceConfig(self):
        """ set the current config values """
        buff = struct.pack(">11H", *self._deviceConfig.values())
        reply = self.command_socket.write_read(
            self.commandSetConfig + buff, size=6, timeout=10
        )
        return self._checkReplyOK(self.commandSetConfig, reply[0:6])

    def getIntegrationTime(self):
        self.getDeviceParameters()
        return self._configurationParameters["IntegrationTime"]

    def setIntegrationTime(self, time):
        self._configurationParameters["IntegrationTime"] = time
        self.setDeviceParameters()

    def setDeviceParameters(self):
        buff = struct.pack(">8Hf4H", *self._configurationParameters.values())
        buff += struct.pack(">ff3H", *self._dac0Parameters.values())
        buff += struct.pack(">ff3H", *self._dac1Parameters.values())
        buff += struct.pack(">ff3H", *self._dac2Parameters.values())
        buff += struct.pack(">ff3H", *self._dac3Parameters.values())
        buff += struct.pack(">ff3H", *self._fitParameters.values())
        buff += struct.pack(">6f", *self._vertFitResultParameters.values())
        buff += struct.pack(">6f", *self._horFitResultParameters.values())
        reply = self.command_socket.write_read(
            self.commandSetParams + buff, size=6, timeout=10
        )
        return self._checkReplyOK(self.commandSetParams, reply)

    def getDeviceParameters(self):
        reply = self.command_socket.write_read(
            self.commandGetParams, size=152, timeout=10
        )
        if self._checkReplyOK(self.commandGetParams, reply[0:6]):
            self._configurationParameters = OrderedDict(
                zip(self._configurationKeys, struct.unpack(">8Hf4H", reply[6:34]))
            )
            self._dac0Parameters = OrderedDict(
                zip(self._DAC0Keys, struct.unpack(">ff3H", reply[34:48]))
            )
            self._dac1Parameters = OrderedDict(
                zip(self._DAC1Keys, struct.unpack(">ff3H", reply[48:62]))
            )
            self._dac2Parameters = OrderedDict(
                zip(self._DAC2Keys, struct.unpack(">ff3H", reply[62:76]))
            )
            self._dac3Parameters = OrderedDict(
                zip(self._DAC3Keys, struct.unpack(">ff3H", reply[76:90]))
            )
            self._fitParameters = OrderedDict(
                zip(self._fitParameterKeys, struct.unpack(">ff3H", reply[90:104]))
            )
            self._vertFitResultParameters = OrderedDict(
                zip(self._fitResultCriteriaKeys, struct.unpack(">6f", reply[104:128]))
            )
            self._horFitResultParameters = OrderedDict(
                zip(self._fitResultCriteriaKeys, struct.unpack(">6f", reply[128:]))
            )
            return OrderedDict(
                zip(
                    self._deviceParameterKeys,
                    [
                        self._configurationParameters,
                        self._dac0Parameters,
                        self._dac1Parameters,
                        self._dac2Parameters,
                        self._dac3Parameters,
                        self._fitParameters,
                        self._vertFitResultParameters,
                        self._horFitResultParameters,
                    ],
                )
            )
        else:
            return None

    def deviceReset(self):
        reply = self.control_socket.write_read(self.commandReset, size=6, timeout=10)
        return self._checkReplyOK(self.commandReset, reply)

    def deviceInterrupt(self):
        reply = self.control_socket.write_read(
            self.commandInterrupt, size=6, timeout=10
        )
        return self._checkReplyOK(self.commandInterrupt, reply)

    def getDeviceStatus(self):
        reply = self.control_socket.write_read(self.commandStatus, size=8, timeout=10)
        if self._checkReplyOK(self.commandStatus, reply[0:6]):
            return struct.unpack(">H", reply[6:])[0] & 0x8

    def remoteDataToggle(self):
        buf = struct.pack(">H", self._remoteDataSelector)
        reply = self.command_socket.write_read(
            self.commandDataToggle + buf, size=6, timeout=10
        )
        return self._checkReplyOK(self.commandDataToggle, reply)

    def readImage8(self):
        reply = self.command_socket.write_read(
            self.commandReadImage8, size=20, timeout=10
        )
        if self._checkReplyOK(self.commandReadImage8, reply[0:6]):
            imageDescriptor = OrderedDict(
                zip(self._imageDescriptorKeys, struct.unpack(">HIHHI", reply[6:]))
            )
            self._frameNbAcquired = imageDescriptor["FrameNb"]
            self._logger.debug(
                "imageDescriptor returned image size [{0},{1}]".format(
                    imageDescriptor["XSize"], imageDescriptor["YSize"]
                )
            )

            image_length = imageDescriptor["XSize"] * imageDescriptor["YSize"]
            data = self.command_socket.read(size=image_length, timeout=10)
            #  need to invert X & Y to get the real image)
            image = numpy.ndarray(
                shape=(imageDescriptor["YSize"], imageDescriptor["XSize"]),
                dtype=">u1",
                buffer=data,
            )
            # do callback function
            imageData = (self.BPP8, image)
            for doCallback in self.callbacks:
                doCallback(None, None, None, None, None, imageData)

    def readImage16(self):
        reply = self.command_socket.write_read(
            self.commandReadImage16, size=20, timeout=10
        )
        if self._checkReplyOK(self.commandReadImage16, reply[0:6]):
            imageDescriptor = OrderedDict(
                zip(self._imageDescriptorKeys, struct.unpack(">HIHHI", reply[6:]))
            )
            self._frameNbAcquired = imageDescriptor["FrameNb"]
            image_length = imageDescriptor["XSize"] * imageDescriptor["YSize"] * 2
            data = self.command_socket.read(size=image_length, timeout=10)
            image = numpy.ndarray(
                shape=(imageDescriptor["YSize"], imageDescriptor["XSize"]),
                dtype=">u2",
                buffer=data,
            )
            # do callback function
            imageData = (self.BPP16, image)
            for doCallback in self.callbacks:
                doCallback(None, None, None, None, None, imageData)

    def readDark16(self):
        reply = self.command_socket.write_read(
            self.commandReadDark16, size=20, timeout=10
        )
        if self._checkReplyOK(self.commandReadDark16, reply[0:6]):
            imageDescriptor = OrderedDict(
                zip(self._imageDescriptorKeys, struct.unpack(">HIHHI", reply[6:]))
            )
            self._frameNbAcquired = imageDescriptor["FrameNb"]
            image_length = imageDescriptor["XSize"] * imageDescriptor["YSize"] * 2
            data = self.command_socket.read(size=image_length, timeout=10)
            image = numpy.ndarray(
                shape=(imageDescriptor["YSize"], imageDescriptor["XSize"]),
                dtype=">u2",
                buffer=data,
            )
            # do callback function
            imageData = (self.BPP16, image)
            for doCallback in self.callbacks:
                doCallback(None, None, None, None, None, imageData)

    def readAve16Sum32(self):
        buf = struct.pack(">HH", self._nbFramesToSum, self._controlWord)
        reply = self.command_socket.write_read(
            self.commandAve16Sum32 + buf, size=20, timeout=4000
        )
        if self._checkReplyOK(self.commandAve16Sum32, reply[0:6]):
            imageDescriptor = OrderedDict(
                zip(self._imageDescriptorKeys, struct.unpack(">HIHHI", reply[6:]))
            )
            self._frameNbAcquired = imageDescriptor["FrameNb"]
            if self._controlWord & self.Control.COLLECT_SUM:
                bytes = 4
                type = ">u4"
                depth = self.BPP32
            else:
                type = ">u2"
                bytes = 2
                depth = self.BPP16
            image_length = imageDescriptor["XSize"] * imageDescriptor["YSize"] * bytes
            data = self.command_socket.read(size=image_length, timeout=10)
            image = numpy.ndarray(
                shape=(imageDescriptor["YSize"], imageDescriptor["XSize"]),
                dtype=type,
                buffer=data,
            )
            # do callback function
            imageData = (depth, image)
            for doCallback in self.callbacks:
                doCallback(None, None, None, None, None, imageData)

    def readContinuousFrame(self, dataSelector):
        self._logger.debug(
            "readContinuousFrame(): dataSelector {0}".format(dataSelector)
        )
        buf = struct.pack(">B6H", dataSelector, *self._quadConfig.values())
        reply = self.command_socket.write_read(
            self.commandContinuous + buf, size=10, timeout=10
        )
        sensorConfig = struct.unpack(">3H", reply[:6])
        self._logger.debug(
            "readContinuousFrame(): sensor config [{0},{1}]".format(
                sensorConfig[0], sensorConfig[1]
            )
        )
        payloadSize = struct.unpack(">I", reply[6:])
        while 1:
            reply = self.command_socket.read(size=14, timeout=10)
            imageDescriptor = OrderedDict(
                zip(self._imageDescriptorKeys, struct.unpack(">HIHHI", reply))
            )
            self._frameNbAcquired = imageDescriptor["FrameNb"]
            xsize = imageDescriptor["XSize"]
            ysize = imageDescriptor["YSize"]
            self._logger.debug(
                "readContinuousFrame(): image size [{0},{1}]".format(xsize, ysize)
            )
            self._logger.debug("readContinuousFrame(): payload {0}".format(payload))
            data = self.command_socket.read(size=payloadSize[0], timeout=10)
            nextIndex = 0
            (imageSum, XMultAcc, YMultAcc) = struct.unpack(">3Q", data[:24])
            nextIndex += 24
            xprofile = numpy.ndarray(
                shape=(xsize,),
                dtype=">u4",
                buffer=data[nextIndex : nextIndex + xsize * 4],
            )
            nextIndex += xsize * 4
            yprofile = numpy.ndarray(
                shape=(ysize,),
                dtype=">u4",
                buffer=data[nextIndex : nextIndex + ysize * 4],
            )
            nextIndex += ysize * 4
            if dataSelector & self.DataSelector.XPROFILE_FIT:
                xfit = numpy.ndarray(
                    shape=(xsize,), dtype=">u4", buffer=data[nextIndex : nextIndex + 40]
                )
                self._logger.debug("readContinuousFrame(): xfit {0}".format(xfit))
                nextIndex += 20
            else:
                xfit = None
            if dataSelector & self.DataSelector.YPROFILE_FIT:
                yfit = numpy.ndarray(
                    shape=(xsize,), dtype=">u4", buffer=data[nextIndex : nextIndex + 40]
                )
                self._logger.debug("readContinuousFrame(): yfit {0}".format(yfit))
                nextIndex += 20
            else:
                yfit = None
            xcog = XMultAcc / imageSum
            ycog = YMultAcc / imageSum
            cog = (xcog, ycog)
            self._logger.debug(
                "readContinuousFrame(): xcog,ycog [{0},{1}]".format(xcog, ycog)
            )
            # do callback function
            for func in self.callbacks:
                func(cog, xprofile, yprofile, xfit, yfit)
            self._logger.debug(
                "readContinuousFrame(): actionByte {0}".format(self._actionByte)
            )
            buf = struct.pack(">B", self._actionByte)
            self.command_socket.write(buf)
            if self._actionByte == 0:
                break

    def startContinuousFrame(self):
        # select(XCoG + YCoG and X + Y Profiles)
        dataSelector = self.DataSelector.XCOG | self.DataSelector.YCOG
        dataSelector |= self.DataSelector.XPROFILE | self.DataSelector.YPROFILE
        #        dataSelector |= self.DataSelector.XPROFILE_FIT | self.DataSelector.YPROFILE_FIT
        self._actionByte = 1
        self._logger.info("startContinuousFrame(): Starting")
        self._thread = gevent.spawn(self.readContinuousFrame, dataSelector)

    def stopContinuousFrame(self):
        with self._lock:
            self._actionByte = 0
        gevent.joinall([self._thread])
        self._thread = None

    def startDataStreaming(self):
        dataSelector = self.DataSelector.XCOG | self.DataSelector.YCOG
        dataSelector |= self.DataSelector.XPROFILE | self.DataSelector.YPROFILE
        dataSelector |= self.DataSelector.XPROFILE_FIT | self.DataSelector.YPROFILE_FIT
        # image cannot be selected with anything else
        if dataSelector & self.DataSelector.IMAGE:
            dataSelector & ~0xe
        self._thread = gevent.spawn(self.streamData, dataSelector)
        self._logger.info(
            "startDataStreaming(): data selector {0}".format(dataSelector)
        )

    def stopDataStreaming(self):
        self.deviceInterrupt()
        self._thread.kill()
        gevent.joinall([self._thread])
        self._thread = None

    def streamData(self, dataSelector):
        buf = struct.pack(">7H", dataSelector, *self._quadConfig.values())
        reply = self.command_socket.write_read(
            self.commandStreamData + buf, size=10, timeout=10
        )
        (xsize, ysize, darkSubtract) = struct.unpack(">3H", reply[:6])
        self._logger.debug("streamData(): sensor config [{0},{1}]".format(xsize, ysize))
        (payloadSize,) = struct.unpack(">I", reply[6:10])
        self._logger.debug("streamData(): payload size {0}".format(payloadSize))
        while 1:
            try:
                data = self.command_socket.read(size=payloadSize, timeout=10)
            except:
                break
            (frameNb,) = struct.unpack(">H", data[:2])
            self._logger.debug("streamData(): frame nos {0}".format(frameNb))
            nextIndex = 2
            cog = xfit = yfit = xprofile = yprofile = None
            xcentre = ycentre = 0.0  # beware 0.0 means do nothing
            if dataSelector & self.DataSelector.IMAGE:
                self._logger.debug("streamData(): decode image {0}".format(len(data)))
                image = numpy.ndarray(
                    shape=(ysize, xsize), dtype=">u1", buffer=data[2:]
                )
            if (
                dataSelector & self.DataSelector.XCOG
                and dataSelector & self.DataSelector.YCOG
            ):
                (imageSum, XMultAcc, YMultAcc) = struct.unpack(
                    ">3Q", data[nextIndex : nextIndex + 24]
                )
                self._logger.debug(
                    "streamData(): imageSum, XMultAcc, YMultAcc {0} {1} {2}".format(
                        imageSum, XMultAcc, YMultAcc
                    )
                )
                nextIndex += 24
                # Deprecated use cog from profile fitting instead
                # xcog = XMultAcc / imageSum
                # ycog = YMultAcc / imageSum
                # cog = (xcog, ycog)
            if dataSelector & self.DataSelector.XPROFILE:
                self._logger.debug(
                    "streamData(): decode xprofile from {0} to {1}".format(
                        nextIndex, nextIndex + xsize * 4
                    )
                )
                xprofile = numpy.ndarray(
                    shape=(xsize,),
                    dtype=">u4",
                    buffer=data[nextIndex : nextIndex + xsize * 4],
                )
                nextIndex += xsize * 4
                self._logger.debug(
                    "streamData(): x {0} {1} {2}".format(
                        xprofile[0], xprofile[1], xprofile[ysize - 1]
                    )
                )
            if dataSelector & self.DataSelector.YPROFILE:
                self._logger.debug(
                    "streamData(): decode yprofile from {0} to {1}".format(
                        nextIndex, nextIndex + xsize * 4
                    )
                )
                yprofile = numpy.ndarray(
                    shape=(ysize,),
                    dtype=">u4",
                    buffer=data[nextIndex : nextIndex + ysize * 4],
                )
                nextIndex += ysize * 4
                self._logger.debug(
                    "streamData(): y {0} {1} {2}".format(
                        yprofile[0], yprofile[1], yprofile[ysize - 1]
                    )
                )
            if dataSelector & self.DataSelector.XPROFILE_FIT:
                self._logger.debug(
                    "streamData(): decode xprofile fit from {0} to {1}".format(
                        nextIndex, nextIndex + 20
                    )
                )
                (xb, xa, x0, xsigma, xrsq) = struct.unpack(
                    ">5f", data[nextIndex : nextIndex + 20]
                )
                self._logger.debug(
                    "streamData(): xfit {0} {1} {2} {3} {4}".format(
                        xb, xa, x0, xsigma, xrsq
                    )
                )
                nextIndex += 20
                if xrsq <= 1.0 and xrsq > 0.8:  # its a good fit
                    xfit = (xb, xa, x0, xsigma, xrsq)
                    if x0 <= xsize:
                        xcentre = x0
            if dataSelector & self.DataSelector.YPROFILE_FIT:
                self._logger.debug(
                    "streamData(): decode yprofile fit from {0} to {1}".format(
                        nextIndex, nextIndex + 20
                    )
                )
                (yb, ya, y0, ysigma, yrsq) = struct.unpack(
                    ">5f", data[nextIndex : nextIndex + 20]
                )
                self._logger.debug(
                    "streamData(): yfit {0} {1} {2} {3} {4}".format(
                        yb, ya, y0, ysigma, yrsq
                    )
                )
                nextIndex += 20
                if yrsq <= 1.0 and yrsq > 0.8:  # its a good fit
                    yfit = (yb, ya, y0, ysigma, yrsq)
                    if y0 <= ysize:
                        ycentre = y0
            cog = (xcentre, ycentre)
            # do callback function
            for doCallback in self.callbacks:
                doCallback(cog, xprofile, yprofile, xfit, yfit, None)
