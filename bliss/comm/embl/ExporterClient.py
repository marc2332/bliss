"""
  Project: JLib

  Date       Author    Changes
  01.07.09   Gobbo     Created

  Copyright 2009 by European Molecular Biology Laboratory - Grenoble
"""

from warnings import warn
from .StandardClient import *

CMD_SYNC_CALL = "EXEC"
CMD_ASNC_CALL = "ASNC"
CMD_METHOD_LIST = "LIST"
CMD_PROPERTY_READ = "READ"
CMD_PROPERTY_WRITE = "WRTE"
CMD_PROPERTY_LIST = "PLST"
CMD_NAME = "NAME"
RET_ERR = "ERR:"
RET_OK = "RET:"
RET_NULL = "NULL"
EVENT = "EVT:"

PARAMETER_SEPARATOR = "\t"
ARRAY_SEPARATOR = ""
# 0x001F


class ExporterClient(StandardClient):
    def onMessageReceived(self, msg):
        if msg[:4] == EVENT:
            try:
                evtstr = msg[4:]
                tokens = evtstr.split(PARAMETER_SEPARATOR)
                self.onEvent(tokens[0], tokens[1], int(tokens[2]))
            except:
                # print("Error processing event: " + str(sys.exc_info()[1]))
                pass
        else:
            StandardClient.onMessageReceived(self, msg)

    def get_method_list(self):
        cmd = CMD_METHOD_LIST
        ret = self.sendReceive(cmd)
        ret = self.__process_return(ret)
        if ret is None:
            return None
        ret = ret.split(PARAMETER_SEPARATOR)
        if len(ret) > 1:
            if ret[-1] == "":
                ret = ret[0:-1]
        return ret

    def get_property_list(self):
        cmd = CMD_PROPERTY_LIST
        ret = self.sendReceive(cmd)
        ret = self.__process_return(ret)
        if ret is None:
            return None
        ret = ret.split(PARAMETER_SEPARATOR)
        if len(ret) > 1:
            if ret[-1] == "":
                ret = ret[0:-1]
        return ret

    def get_server_object_name(self):
        cmd = CMD_NAME
        ret = self.sendReceive(cmd)
        return self.__process_return(ret)

    def __process_return(self, ret):
        if ret[:4] == RET_ERR:
            raise RuntimeError(ret[4:])
        elif ret == RET_NULL:
            return None
        elif ret[:4] == RET_OK:
            return ret[4:]
        else:
            raise ProtocolError

    def execute(self, method, pars=None, timeout=-1):
        cmd = CMD_SYNC_CALL + " " + method + " "
        if pars is not None:
            if isinstance(pars, list) or isinstance(pars, tuple):
                for par in pars:
                    par = self.create_array_parameter(par)
                    cmd += str(par) + PARAMETER_SEPARATOR
            else:
                cmd += str(pars)
        ret = self.sendReceive(cmd, timeout)
        return self.__process_return(ret)

    def execute_async(self, method, pars=None):
        cmd = CMD_ASNC_CALL + " " + method + " "
        if pars is not None:
            for par in pars:
                cmd += str(par) + PARAMETER_SEPARATOR
        return self.send(cmd)

    def write_property(self, prop, value, timeout=-1):
        if isinstance(value, list) or isinstance(value, tuple):
            value = self.create_array_parameter(value)
        cmd = CMD_PROPERTY_WRITE + " " + prop + " " + str(value)
        ret = self.sendReceive(cmd, timeout)
        return self.__process_return(ret)

    def read_property(self, prop, timeout=-1):
        cmd = CMD_PROPERTY_READ + " " + prop
        ret = self.sendReceive(cmd, timeout)
        return self.__process_return(ret)

    def parse_array(self, value):
        value = str(value)
        if value.startswith(ARRAY_SEPARATOR):
            if value == ARRAY_SEPARATOR:
                return []
            value = value.lstrip(ARRAY_SEPARATOR).rstrip(ARRAY_SEPARATOR)
            return value.split(ARRAY_SEPARATOR)
        return None

    def create_array_parameter(self, value):
        ret = "" + ARRAY_SEPARATOR
        if value is not None:
            if isinstance(value, list) or isinstance(value, tuple):
                for item in value:
                    ret = ret + str(item)
                    ret = ret + ARRAY_SEPARATOR
            else:
                ret = ret + str(value)
        return ret

    def onEvent(self, name, value, timestamp):
        pass

    """ deprecated """

    def getMethodList(self):
        warn(
            "getMethodList is deprecated. Use get_method_list instead",
            DeprecationWarning,
        )
        return self.get_method_list()

    def getPropertyList(self):
        warn(
            "getPropertyList is deprecated. Use get_property_list instead",
            DeprecationWarning,
        )
        return self.get_property_list()

    def getServerObjectName(self):
        warn(
            "getServerObjectName is deprecated. Use get_server_object_name instead",
            DeprecationWarning,
        )
        return self.get_server_object_name()

    def createArrayParameter(self, value):
        warn(
            "createArrayParameter is deprecated. Use create_array_parameter instead",
            DeprecationWarning,
        )
        return self.create_array_parameter(value)

    def parseArray(self, value):
        warn("parseArray is deprecated. Use parse_array instead", DeprecationWarning)
        return self.parse_array(value)

    def __processReturn(self, ret):
        warn(
            "__processReturn is deprecated. Use __process_return instead",
            DeprecationWarning,
        )
        try:
            return __process_return(ret)
        except (RuntimeError, ProtocolError) as ex:
            raise ex

    def writeProperty(self, prop, value, timeout=-1):
        warn(
            "writeProperty is deprecated. Use write_property instead",
            DeprecationWarning,
        )
        self.write_property(prop, value, timeout)

    def readProperty(self, prop, timeout=-1):
        warn(
            "readProperty is deprecated. Use read_property instead", DeprecationWarning
        )
        return self.read_property(prop, timeout)

    def executeAsync(self, method, pars=None):
        warn(
            "executeAsync is deprecated. Use execute_async instead", DeprecationWarning
        )
        return self.execute_async(method, pars)

    def readPropertyAsString(self, prop):
        return self.read_property(prop)

    def readPropertyAsFloat(self, prop):
        return float(self.read_property(prop))

    def readPropertyAsInt(self, prop):
        return int(self.read_property(prop))

    def readPropertyAsBoolean(self, prop):
        if self.read_property(prop) == "true":
            return True
        return False

    def readPropertyAsStringArray(self, prop):
        ret = self.read_property(prop)
        return self.parse_array(ret)
