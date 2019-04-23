# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

""" Meerstetter thermo-electric controller
    
    The code for the class Ltr1200 is based on the code found 
    for the class TECFamilyProtocol and the code for the class
    ltr1200 (BLISS temperature controller class) is based on the
    code for the class Temperature in the file
    ting:~blissadm/server/src/Temperature/LTR1200.py,
    which was created to be used by LTR1200TemperatureDS 
    Tango DS.

    Example of YML configuration:

        plugin: temperature
        class: ltr1200
        host: xxx  [can be hostname or IP address]
        dev_addr: 1
        outputs:
        - name: heater

"""

from bliss.controllers.temp import Controller

# TODO: see if need to add Input and Loop
#       [for the moment work only with Output object]
from bliss.common.temperature import Output

from bliss.comm import tcp

import struct

# Different debug levels are:
# log.NOTSET = 0, log.DEBUG = 10, log.INFO = 20, log.ERROR=40
import logging


def set_ltr_log_level(level):
    level = level.upper()
    logging.getLogger("Ltr1200").setLevel(level)
    logging.getLogger("ltr1200").setLevel(level)


# set_ltr_log_level('debug')

# from bliss.common.utils import object_method, object_method_type
from bliss.common.utils import object_attribute_get, object_attribute_type_get

# from bliss.common.utils import object_attribute_set, object_attribute_type_set


from . import mecom


######################################################################
#####################                           ######################
#####################  LTR1200 Low-Level Class  ######################
#####################                           ######################
######################################################################


class Ltr1200(object):
    """
    Low-level class which takes care of all the communication
    with the hardware with the help of other classes which 
    implement MeCom protocol
    """

    def __init__(self, host=None, dev_addr=1, timeout=10, debug=False):
        self.host = host
        self.dev_addr = dev_addr
        self.timeout = timeout

        # Port is always 50000 for Meerstetter TEC controller
        self._sock = tcp.Socket(self.host, 50000, self.timeout)

        self._tec = mecom.TECFamilyProtocol(self._sock, self.dev_addr)
        self.log = logging.getLogger("Ltr1200")
        self.log.info("__init__: %s %s %d" % (host, self._sock, dev_addr))

    def exit(self):
        self._sock.close()

    def init(self):
        self.log.info("init()")
        self.model = self._tec.getModel()
        self.log.debug("init(): Model = %s" % (self.model))
        # TODO: see what else could add here i.e. which other
        #       operations/actions would be suitable.

    def getModel(self):
        self.log.info("getModel()")
        # self.model = self._tec.putget("?IF",4)
        self.model = self._tec.getModel()
        self.log.debug("getModel: %s" % (self.model))
        return self.model

    def getObjectTemperature(self, instance):
        self.log.info("getObjectTemperature(): instance = %d" % (instance))
        answer = (self._tec._getParameter(1000, 8, instance)).decode()
        if answer is not None:
            answer = struct.unpack(">f", bytes.fromhex(answer))[0]
        self.log.debug("getObjectTemperature: temp = %s" % answer)
        return answer

    def getSinkTemperature(self, instance):
        self.log.info("getSinkTemperature(): instance = %d" % (instance))
        answer = (self._tec._getParameter(1001, 8, instance)).decode()
        if answer is not None:
            answer = struct.unpack(">f", bytes.fromhex(answer))[0]
        self.log.debug("getSinkTemperature: temp = %s" % answer)
        return answer

    def getTargetTemperature(self, instance):
        self.log.info("getTargetTemperature(): instance = %d" % (instance))
        answer = (self._tec._getParameter(1010, 8, instance)).decode()
        if answer is not None:
            answer = struct.unpack(">f", bytes.fromhex(answer))[0]
        self.log.debug("getTargetTemperature: temp = %s" % answer)
        return answer

    def setTargetTemperature(self, value, instance):
        self.log.info(
            "setTargetTemperature(): instance = %d, value = %f" % (instance, value)
        )
        answer = (self._tec._setParameter(3000, value, instance)).decode()
        self.log.debug("setTargetTemperature: %s" % answer)  # ACK
        return answer

    def getOutputCurrent(self, instance):
        self.log.info("getOutputCurrent(): instance = %d" % (instance))
        answer = (self._tec._getParameter(1020, 8, instance)).decode()
        if answer is not None:
            answer = struct.unpack(">f", bytes.fromhex(answer))[0]
        self.log.debug("getOutputCurrent: current = %s" % answer)
        return answer

    def getOutputVoltage(self, instance):
        self.log.info("getOutputVoltage(): instance = %d" % (instance))
        answer = (self._tec._getParameter(1021, 8, instance)).decode()
        if answer is not None:
            answer = struct.unpack(">f", bytes.fromhex(answer))[0]
        self.log.debug("getOutputVoltage: voltage = %s" % answer)
        return answer

    def getDriverStatus(self, instance):
        self.log.info("getDriverStatus(): instance = %d" % (instance))
        answer = (self._tec._getParameter(1080, 8, instance)).decode()
        description = [
            "Init",
            "Ready",
            "Run",
            "Error",
            "Bootloader",
            "Device will Reset within 200ms",
        ]
        if answer is not None:
            answer = description[int(answer)]
        self.log.debug("getDriverStatus: status = %s" % answer)
        return answer

    def ResetDevice(self):
        self.log.info("ResetDevice()")
        self._tec.putget("RS")

    def EmergencyStop(self):
        self.log.info("EmergencyStop()")
        self._tec.putget("ES")


######################################################################
#####################                           ######################
#####################  LTR1200 Controller Class ######################
#####################                           ######################
######################################################################


class ltr1200(Controller):
    def __init__(self, config, *args):

        if "host" not in config:
            raise RuntimeError("Should have host name or IP address in config")
        host = config["host"]

        if "dev_addr" not in config:
            dev_addr = 1
        else:
            dev_addr = config["dev_addr"]

        self._ltr1200 = Ltr1200(host, dev_addr)

        Controller.__init__(self, config, *args)
        self.log = logging.getLogger("ltr1200")
        self.log.info("__init__: %s %d" % (host, dev_addr))

    def initialize(self):
        ###config = dict(self.config) -- to use if no __init__()
        ###print 'HELLO'

        self._ltr1200.init()

    def __del__(self):
        self._ltr1200.exit()

    # Remark: In various calls here below use 1 for the instance parameter
    #         though this is its default value and so it could be omitted
    #         in the parameter list.
    #         TODO: see how can pass instance if want it to be different from 1
    def read_output(self, toutput):
        self.log.info("read_output()")
        obj_temp = self._ltr1200.getObjectTemperature(1)
        self.log.debug("Object temperature = %f C" % obj_temp)
        return obj_temp

        # set Set Point Temperature

    def set(self, toutput, sp, **kwargs):
        self.log.info("set() = set SP temperature: %f C" % sp)
        self._ltr1200.setTargetTemperature(sp, 1)

        # get Set Point Temperature

    def get_setpoint(self, toutput):
        self.log.info("get_setpoint() = get SP temperature")
        sp_temp = self._ltr1200.getTargetTemperature(1)
        self.log.debug("SP temperature = %f C" % sp_temp)
        return sp_temp

    def state_output(self, toutput):
        self.log.info("state_output()")
        out_state = self._ltr1200.getDriverStatus(1)
        self.log.debug("driver status = %s" % out_state)
        return out_state

        # Remark:
        # =======
        # For reading/getting entities like:
        #  - Model (= Firmware ID string),
        #  - Get Sink Temperature,
        #  - Get Output Current,
        #  - etc.
        # must use CUSTOM commands/attributes.

    @object_attribute_type_get(type_info=("str"), type=Output)
    def get_model(self, toutput):
        self.log.info("get_model(= firmware identification string)")
        model = self._ltr1200.getModel()
        self.log.debug("Firmware id string = %s" % model)
        return model

    @object_attribute_type_get(type_info=("float"), type=Output)
    def get_sink_temperature(self, toutput):
        self.log.info("get_sink_temperature: ")
        sink_temp = self._ltr1200.getSinkTemperature(1)
        self.log.debug("sink_temperature = %f C" % sink_temp)
        return sink_temp

    @object_attribute_type_get(type_info=("float"), type=Output)
    def get_output_current(self, toutput):
        self.log.info("get_output_current: ")
        op_current = self._ltr1200.getOutputCurrent(1)
        self.log.debug("output_current = %f A" % op_current)
        return op_current

    @object_attribute_type_get(type_info=("float"), type=Output)
    def get_output_voltage(self, toutput):
        self.log.info("get_output_voltage: ")
        op_voltage = self._ltr1200.getOutputVoltage(1)
        self.log.debug("output_voltage = %f V" % op_voltage)
        return op_voltage
