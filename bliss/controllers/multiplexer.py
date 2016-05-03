from serial import serial_for_url
import os
import struct

from bliss.comm import serial
from bliss.comm import tcp
OPIOM_BASE_PATH='/users/blissadm/local/isg/opiom'

class OpiomComm:
    FSIZE = 256

    def __init__(self,name,config_tree): #serial=0,program='',**keys) :
        if "serial" in config_tree:
            self._cnx = serial.Serial(config_tree['serial'],timeout = 3)
        elif "socket" in config_tree:
            self._cnx = tcp.Tcp(config_tree['socket'],timeout = 3)
        else:
            raise RuntimeError("opiom: need to specify a communication url")
        
        self._cnx.flush()
        self.__program = config_tree['program']
        self.__debug = False
        msg = self.comm("?VER")
        if not msg.startswith('OPIOM') :
            msg = self.comm("?VER")
            if not msg.startswith('OPIOM') :
                raise IOError("No opiom connected at %s" % serial)
        self.comm("MODE normal")

    def __repr__(self) :
        return "Opiom : %s with program %s" % (self._cnx,self.__program)

    def setDebug(self, flag) :
        self.__debug = flag is True

    def getDebug(self):
        return self.__debug

    def __debugMsg(self, wr, msg):
        if self.__debug:
            print "%-5.5s on %s > %s"%(wr, self._cnx.name, msg)

    def info(self) :
        return self.comm("?INFO")

    def source(self) :
        return self.comm("?SRC")

    def prog(self) :
        info = self.info()
        for line in info.split('\n') :
            if line.startswith('PLD prog:') :
                return line.split(':')[1].strip('\n\t ')

    def error(self) :
        return self.comm("?ERR")

    def registers(self) :
        return {'IM':int(self.comm("?IM"),base=16),
                'IMA':int(self.comm("?IMA"),base=16)}

    def inputs_stat(self) :
        input_front = int(self.comm("?I"),base=16)
        input_back = int(self.comm("?IB"),base=16)

        self._display_bits('I',input_front)
        self._display_bits('IB',input_back)

    def outputs_stat(self) :
        output_front = int(self.comm("?O"),base=16)
        output_back = int(self.comm("?OB"),base=16)

        self._display_bits('O',output_front)
        self._display_bits('OB',output_back)

    def raw_write(self,msg) :
        self._cnx.write(msg)

    def raw_bin_write(self,binmsg):
        nb_block = len(binmsg) / self.FSIZE
        nb_bytes = len(binmsg) % self.FSIZE
        lrc = (nb_bytes + nb_block + sum([ord(x) for x in binmsg])) & 0xff
        rawMsg = struct.pack('BBB%dsBB' % len(binmsg),0xff,nb_block,nb_bytes,
                             binmsg,lrc,13)
        self._cnx.write(rawMsg)

    def comm_ack(self,msg) :
        return self.comm('#' + msg)

    def comm(self,msg) :
        with self._cnx._lock:
            self._cnx.open()
            self._cnx._write(msg + '\r\n')
            if msg.startswith('?') or msg.startswith('#') :
                msg = self._cnx._readline()
                if msg.startswith('$') :
                    msg = self._cnx._readline('$\r\n')
                self.__debugMsg("Read", msg.strip('\n\r'))
                return msg.strip('\r\n')
                

    def load_program(self) :
        pldid = self.comm("?PLDID")
        file_pldid,file_project = self._getFilePLDIDandPROJECT()
        if file_pldid and file_pldid != pldid:
            print "Load program:",self.__program
            srcsz = int(self.comm("?SRCSZ").split()[0])
            offsets,opmfile = self._getoffset()
            if((offsets["src_c"] - offsets["src_cc"]) < srcsz) :
                SRCST = offsets["src_cc"]
                srcsz = offsets["src_c"] - offsets["src_cc"]
            else:
                SRCST = offsets["src_c"]
                srcsz = offsets["jed"] - offsets["src_c"]
            binsz = offsets['size'] - offsets['jed']


            sendarray = opmfile[SRCST:SRCST+srcsz]
            sendarray += opmfile[offsets["jed"]:]

            if self.comm_ack("MODE program") != "OK" :
                raise IOError("Can't program opiom %s" % str(self))

            if self.comm_ack('PROG %d %d %d %d "%s"' % (binsz,srcsz,self.FSIZE,
                                                        int(file_pldid),
                                                        file_project)) != "OK" :
                self.comm("MODE normal")
                raise IOError("Can't start programming opiom %s" % str(self))

            for frame_n,index in enumerate(range(0,len(sendarray),self.FSIZE)) :
                self.raw_write("#*FRM %d\r" % frame_n)
                self.raw_bin_write(sendarray[index:index+self.FSIZE])
                answer = self._read()
                if(answer != "OK") : break


    def _display_bits(self,prefix,bits) :
        for i in range(1,9) :
            print "%s%d\t" % (prefix,i),
        print
        for i in range(8):
            if((bits >> i) & 0x1) :
                print "1\t",
            else:
                print "0\t",

        print

    def _getoffset(self) :
        f = file(os.path.join(OPIOM_BASE_PATH,self.__program + '.opm'))
        line = f.read(14)
        f.seek(0)
        opmfile = f.read()
        size = f.tell()
        header,src,src_cc,src_c,jed = struct.unpack('<5H',line[3:13])
        return {'header' : header,'src' : src,
                'src_cc': src_cc,'src_c' : src_c,
                'jed' :jed,'size':size},opmfile

    def _getFilePLDIDandPROJECT(self) :
        TOKEN = '#pldid#'
        PROJECT_TOKEN= '#project#'

        f = file(os.path.join(OPIOM_BASE_PATH,self.__program + '.opm'))
        begin = -1
        for line in f:
            begin = line.find(TOKEN)
            if begin > -1:
                break
        if begin > -1 :
            subline = line[begin + len(TOKEN):]
            end = subline.find(TOKEN)
            pldid = subline[:end]

            begin = line.find(PROJECT_TOKEN)
            subline = line[begin + len(PROJECT_TOKEN):]
            project = subline[:subline.find(PROJECT_TOKEN)]
            return pldid,project

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

