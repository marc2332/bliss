import gevent
from .opiom import Opiom
from bliss.config import static
from bliss.config.settings import HashObjSetting
from collections import OrderedDict

class Output:
    class Node:
        def __init__(self,opiomId,register,shift,mask,value,parentNode) :
            self.__opiomId = opiomId
            self.__register = register.upper()
            shift = int(shift)
            self.__mask = int(mask,16) << shift
            self.__value = int(value) << shift
            self.__parent = parentNode

        def switch(self,opioms,synchronous) :
            if self.__parent:
                self.__parent.switch(opioms,False)

            op = opioms[self.__opiomId]
            cmd = '%s 0x%x 0x%x' % (self.__register,self.__value,self.__mask)
            if synchronous:
                op.comm_ack(cmd)
            else:
                op.comm(cmd)

        def isActive(self,opiom_registers) :
            activeFlag = True
            if self.__parent:
                activeFlag = self.__parent.isActive(opiom_registers)

            registerValue = opiom_registers[self.__opiomId][self.__register]
            return activeFlag and ((registerValue & self.__mask) == self.__value)

    def __init__(self,multiplex,name='',**keys) :
        self.__multiplex = multiplex
        self.__name = name
        self.__nodes = {}
        self.__build_values(**keys)

    def name(self) :
        return self.__name

    def getSwitchList(self) :
        return self.__nodes.keys()

    def switch(self,switchValue,synchronous) :
        switchValue = switchValue.upper()
        try:
            node = self.__nodes[switchValue]
        except KeyError:
            raise ValueError(switchValue)

        node.switch(self.__multiplex._opioms,synchronous)

    def getStat(self,opiom_register) :
        for key,node in self.__nodes.iteritems() :
            if node.isActive(opiom_register) :
                return key

    def __build_values(self,opiomId = 0,register = '',shift = '0',
                       mask = '0',chained_value = '0',parentNode = None,**configDict) :
        for key,values in configDict.iteritems() :
            key = key.upper()
            if key.startswith('OPIOM') :
                if register:
                    nextParentNode = Output.Node(opiomId,register,shift,
                                             mask,chained_value,parentNode)
                else:
                    nextParentNode = parentNode
                self.__build_values(opiomId = getOpiomId(key),parentNode = nextParentNode,**values)
            else:
                self.__nodes[key] = Output.Node(opiomId,register,shift,mask,
                                                values,parentNode)
class Multiplexer:
    SAVED_STATS_KEY = "saved stats"
    def __init__(self,configFile) :
        self._opioms = {}
        self.__outputs = {}

        if not os.path.isfile(configFile):
            self.__configFilePath= "%s/%s"%(OPIOM_BASE_PATH, configFile)
        else:
            self.__configFilePath= configFile

        config = ConfigDict.ConfigDict(filelist=[self.__configFilePath])
        for key,value in config.iteritems() :
            key = key.upper()
            if key.startswith('OPIOM') :
                self._opioms[getOpiomId(key)] = OpiomComm(**value)
            else:
                self.__outputs[key] = Output(self,**value)

        basepath,configFilename = os.path.split(self.__configFilePath)
        basefilename,ext = os.path.splitext(configFilename)
        self.__statFilePath = os.path.join(basepath,"%s_saved_stats%s" % (basefilename,ext))
        statConfig = ConfigDict.ConfigDict(filelist=[self.__statFilePath])
        self.__stat = {}
        for statname,d in statConfig.get(self.SAVED_STATS_KEY,{}).iteritems() :
            tmpDict = {}
            for opiomId,registerValues in d.iteritems():
                try:
                    opiomId = int(opiomId)
                except:
                    continue
                tmpDict[opiomId] = registerValues
            self.__stat[statname] = tmpDict
        self.__debug= False

    def setDebug(self, flag):
        self.__debug= flag is True
        for opiom in self._opioms.itervalues():
            opiom.setDebug(self.__debug)

    def getDebug(self):
        return self.__debug

    def getConfigPath(self) :
        return [self.__configFilePath, self.__statFilePath]

    def getOutputList(self) :
        return self.__outputs.keys()

    def getPossibleValues(self,output_key) :
        output_key = output_key.upper()
        return self.__outputs[output_key].getSwitchList()

    def getKeyAndName(self) :
        return dict([(key,output.name()) for key,output in self.__outputs.iteritems()])

    def getName(self,output_key) :
        output_key = output_key.upper()
        return self.__outputs[output_key].name()

    def switch(self,output_key,input_key,synchronous = False):
        output_key = output_key.upper()
        input_key = input_key.upper()
        if self.__debug:
            print "Multiplexer.switch %s to %s"%(output_key, input_key)
        try:
            output = self.__outputs[output_key]
        except KeyError:
            raise ValueError("Multiplexer don't have the ouput %s" % output_key)
        else:
            try:
                output.switch(input_key,synchronous)
            except ValueError,err:
                raise ValueError("%s is not available for output %s" % (str(err),output_key))

    def raw_com(self,message,opiomId = 1,synchronous = False) :
        opiomId = int(opiomId)
        try:
            opiom = self._opioms[opiomId]
        except KeyError:
            raise ValueError("Multiplexer don't have opiom with %d id" % opiomId)

        if synchronous:
            return opiom.comm_ack(message)
        else:
            return opiom.comm(message)

    def getOutputStat(self,output_key) :
        output_key = output_key.upper()
        if self.__debug:
            print "Multiplexer.getOutputStat %s"%output_key
        output = self.__outputs[output_key]
        opiomRegister = {}
        for opiomId,comm in self._opioms.iteritems() :
            comm._ask_register_values()
        for opiomId,comm in self._opioms.iteritems() :
            opiomRegister[opiomId] = comm._read_register_values()

        return output.getStat(opiomRegister)

    def storeCurrentStat(self,name) :
        opiomRegister = {}
        for opiomId,comm in self._opioms.iteritems() :
            comm._ask_register_values()
        for opiomId,comm in self._opioms.iteritems() :
            opiomRegister[opiomId] = comm._read_register_values()

        self.__stat[name] = opiomRegister
        self.__saveStats()

    def restoreStat(self,name) :
        try:
            opiomRegister = self.__stat[name]
        except KeyError:
             raise ValueError("Multiplexer don't have the stat %s" % name)

        for opiomId,reg in opiomRegister.iteritems() :
            for regName,value in reg.iteritems() :
                self._opioms[opiomId].comm("%s 0x%x" % (regName,value))

    def rmStat(self,name) :
        try:
            self.__stat.pop(name)
        except KeyError:
            raise ValueError("Multiplexer don't have the stat %s" % name)

        self.__saveStats(False)

    def getSavedStats(self) :
        return self.__stat.keys()

    def __saveStats(self,update = True) :
        statConfig = ConfigDict.ConfigDict(filelist=[self.__statFilePath])
        if update:
            try:
                statConfig[self.SAVED_STATS_KEY].update(self.__stat)
            except KeyError:
                statConfig[self.SAVED_STATS_KEY] = self.__stat
        else:
            statConfig[self.SAVED_STATS_KEY] = self.__stat
        statConfig.write(self.__statFilePath)

    def getGlobalStat(self) :
        if self.__debug:
            print "Multiplexer.getGlobalStat"
        opiomRegister = {}
        for opiomId,comm in self._opioms.iteritems() :
            comm._ask_register_values()
        for opiomId,comm in self._opioms.iteritems() :
            opiomRegister[opiomId] = comm._read_register_values()
        outputStat = {}
        for key,output in self.__outputs.iteritems() :
            outputStat[key] = output.getStat(opiomRegister)
        return outputStat

    def load_program(self) :
        for opiom in self._opioms.values() :
            opiom.load_program()

    def getOpiomProg(self) :
        progs= {}
        for opiomId,comm in self._opioms.iteritems() :
            progs[opiomId]= comm.prog()
        return progs

    def dumpOpiomSource(self, opiomId) :
        try:
            com= self._opioms[opiomId]
        except KeyError:
            raise ValueError("Multiplexer do not have opiomId %d" % opiomId)

        print "OPIOMID:", opiomId
        print "Prog.Source:"
        print com.source()
        print "End of Prog.Source."

def getOpiomId(opiomKey) :
    try:
        return int(opiomKey[5:])
    except ValueError:
        return 0

if __name__ == '__main__':
    m = Multiplexer('example.config')
    print m.getGlobalStat()

