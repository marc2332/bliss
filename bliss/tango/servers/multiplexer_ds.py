import sys
import PyTango
from bliss.controllers import multiplexer

class Multiplexer(PyTango.Device_4Impl) :
    def __init__(self,*args) :
        PyTango.Device_4Impl.__init__(self,*args)
        self.__multiplexer = None
        self.init_device()

    def init_device(self) :
        self.set_state(PyTango.DevState.FAULT)
        self.get_device_properties(self.get_device_class())
        self.__multiplexer = multiplexer.Multiplexer(self.ConfigFile)
        self.__multiplexer.load_program()
        self.set_state(PyTango.DevState.ON)

    def read_outputs(self,attr) :
        attr.set_value(self.__multiplexer.getOutputList())

    def read_outputs_status(self,attr) :
        returnList = []
        for item in self.__multiplexer.getGlobalStat().iteritems() :
            returnList.extend(item)
        attr.set_value(returnList)

    def read_outputs_key_name(self,attr) :
        returnList = []
        for item in self.__multiplexer.getKeyAndName().iteritems():
            returnList.extend(item)
        attr.set_value(returnList)

    def switch(self,values) :
        self.__multiplexer.switch(*values)

    def raw_com(self,values):
        return self.__multiplexer.raw_com(*values) or ""
    
    def getPossibleOutputValues(self,output_key) :
        return self.__multiplexer.getPossibleValues(output_key)

    def getOutputStat(self,output_key) :
        return self.__multiplexer.getOutputStat(output_key)
    
    def storeCurrentStat(self,stat) :
        self.__multiplexer.storeCurrentStat(stat)

    def restoreStat(self,stat) :
        self.__multiplexer.restoreStat(stat)

    def getSavedStats(self):
        return self.__multiplexer.getSavedStats()

    def removedSavedStat(self,stat) :
        self.__multiplexer.rmStat(stat)
        
class MultiplexerClass(PyTango.DeviceClass) :
    #    Class Properties
    class_property_list = {
        }


    #    Device Properties
    device_property_list = {
        'ConfigFile' :
        [PyTango.DevString,
         "Multiplexer configuration file",[]],
        }

    #    Command definitions
    cmd_list = {
        'switch':
        [[PyTango.DevVarStringArray,"output_key input_key synchronous"],
         [PyTango.DevVoid,""]],
        'raw_com':
        [[PyTango.DevVarStringArray,"message opiomId synchronous"],
         [PyTango.DevString,"result"]],
        'getPossibleOutputValues':
        [[PyTango.DevString,"output_key"],
         [PyTango.DevVarStringArray,"possible output values"]],
        'getOutputStat':
        [[PyTango.DevString,"output_key"],
         [PyTango.DevString,"output_value"]],
        'getSavedStats':
        [[PyTango.DevVoid,""],
         [PyTango.DevVarStringArray,"saved stats"]],
        'removedSavedStat':
        [[PyTango.DevString,"stat"],
         [PyTango.DevVoid,""]],
        'storeCurrentStat':
        [[PyTango.DevString,"stat"],
         [PyTango.DevVoid,'']],
        'restoreStat':
        [[PyTango.DevString,"stat"],
         [PyTango.DevVoid,'']],
        }

    #    Attribute definitions
    attr_list = {
        'outputs' :
        [[PyTango.DevString,
          PyTango.SPECTRUM,
          PyTango.READ,1024]],
        'outputs_status' :
        [[PyTango.DevString,
          PyTango.SPECTRUM,
          PyTango.READ,2048]],
        'outputs_key_name' :
        [[PyTango.DevString,
          PyTango.SPECTRUM,
          PyTango.READ,2048]],
        }
 
    
def main() :
    try:
        py = PyTango.Util(sys.argv)
        py.add_TgClass(MultiplexerClass,Multiplexer,'Multiplexer')
        U = PyTango.Util.instance()
        U.server_init()
        U.server_run()
    except PyTango.DevFailed,e:
        print '-------> Received a DevFailed exception:',e
    except Exception,e:
        print '-------> An unforeseen exception occured....',e


if __name__ == '__main__':
    main()
