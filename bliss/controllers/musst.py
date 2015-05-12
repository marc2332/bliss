import numpy
import weakref
from bliss.comm.gpib import Gpib

def _get_simple_property(command_name,
                         doc_sring):
    def get(self):
        return self.putget("?%s" % command_name)
    def set(self,value) :
        return self.putget("%s %s" % (command_name,value))
    return property(get,set,doc=doc_sring)

def _simple_cmd(command_name,doc_sring):
    def exec_cmd(self):
        return self.putget(command_name)
    return property(exec_cmd,doc=doc_sring)

class musst(object):
    class channel(object):
        COUNTER,ENCODER,SSI,ADC10,ADC5 = range(5)
        def __init__(self,musst,channel_id) :
            self._musst = weakref.ref(musst)
            self._channel_id = channel_id
            self._mode = None
            self._string2mode = {
                "CNT" : self.COUNTER,
                "ENCODER" : self.ENCODER,
                "SSI" : self.SSI,
                "ADC" : self.ADC10}
        @property
        def value(self):
            musst = self._musst()
            string_value = musst.putget("?CH CH%d" % self._channel_id).split()[0]
            return self._convert(string_value)

        @value.setter
        def value(self,val):
            musst = self._musst()
            musst.putget("CH CH%d %s" % (self._channel_id,val))

        @property
        def status(self):
            musst = self._musst()
            status_string = musst.putget("?CH CH%d" % self._channel_id).split()[1]
            return musst._string2state.get(status_string)

        def run(self):
            self._cnt_cmd("RUN")

        def stop(self):
            self._cnt_cmd("STOP")
            
        def _cnt_cmd(self,cmd):
            self._read_config()
            if(self._mode == self.COUNTER or
               self._mode == self.ENCODER):
                musst = self._musst()
                musst.putget("CH CH%d %s" % (self._channel_id,cmd))
            else:
                raise RuntimeError("%s command on "\
                                   "channel %d is not allowed in this mode" % (cmd,self._channel_id))

        def _convert(self,string_value):
            self._read_config()
            if self._mode == self.COUNTER:
                return int(string_value)
            elif(self._mode == self.ADC10):
                return int(string_value) * (10. / 0x7fffffff)
            elif(self._mode == self.ADC5):
                return int(string_value) * (5. / 0x7fffffff)
            else:                       # not managed yet
                return string_value

        def _read_config(self) :
            if self._mode is None:
                musst = self._musst()
                string_config = musst.putget("?CHCFG CH%d" % self._channel_id)
                split_config = string_config.split()
                self._mode = self._string2mode.get(split_config[0])
                if self._mode == self.ADC10: # TEST if it's not a 5 volt ADC
                    if len(split_config) > 1 and split_config[1].find('5') > -1:
                        self._mode = self.ADC5

    ADDR    = _get_simple_property("ADDR","Set/query serial line address")
    BTRIG   = _get_simple_property("BTRIG","Set/query the level of the TRIG out B output signal")
    NAME    = _get_simple_property("NAME","Set/query module name")
    EBUFF   = _get_simple_property("EBUFF","Set/ query current event buffer")
    HBUFF   = _get_simple_property("HBUFF","Set/ query current histogram buffer")

    ABORT   = _simple_cmd("ABORT","Program abort")
    RESET   = _simple_cmd("RESET","Musst reset")
    CLEAR   = _simple_cmd("CLEAR","Delete the current program")
    LIST    = _simple_cmd("?LIST","List the current program")
    DBINFO  = _simple_cmd("?DBINFO *","Returns the list of installed daughter boards")
    HELP    = _simple_cmd("?HELP","Query list of available commands")
    INFO    = _simple_cmd("?INFO","Query module configuration")
    RETCODE = _simple_cmd("?RETCODE","Query exit or stop code")

    #STATE
    NOPROG_STATE,BADPROG_STATE,IDLE_STATE,RUN_STATE,BREAK_STATE,STOP_STATE,ERROR_STATE = range(7)
    #FREQUENCY TIMEBASE
    F_1KHZ, F_10KHZ, F_100KHZ, F_1MHZ, F_10MHZ, F_50MHZ = range(6)
    def __init__(self,name,config_tree):
        """Base Musst controller.

        name -- the controller's name
        config_tree -- controller configuration,
        in this dictionary we need to have:
        gpib_url -- url of the gpib controller i.s:enet://gpib0.esrf.fr
        gpib_pad -- primary address of the musst controller
        gpib_timeout -- communication timeout, default is 1s
        """
        
        self.name = name
        self._cnx = Gpib(config_tree["gpib_url"],
                         pad = config_tree["gpib_pad"],
                         timeout = config_tree.get("gpib_timeout",0.5))
        self._string2state = {
            "NOPROG" : self.NOPROG_STATE,
            "BADPROG" : self.BADPROG_STATE,
            "IDLE" : self.IDLE_STATE,
            "RUN" : self.RUN_STATE,
            "BREAK" : self.BREAK_STATE,
            "STOP" : self.STOP_STATE,
            "ERROR" : self.ERROR_STATE
            }

        self.__frequency_convertion = {
            self.F_1KHZ   : "1KHZ",
            self.F_10KHZ  : "10KHZ",
            self.F_100KHZ : "100KHZ",
            self.F_1MHZ   : "1MHZ",
            self.F_10MHZ  : "10MHZ",
            self.F_50MHZ  : "50MHZ",

            "1KHZ"        : self.F_1KHZ,
            "10KHZ"       : self.F_10KHZ,
            "100KHZ"      : self.F_100KHZ,
            "1MHZ"        : self.F_1MHZ,
            "10MHZ"       : self.F_10MHZ,
            "50MHZ"       : self.F_50MHZ
            }
            

    def putget(self,msg,ack = False):
        """ Raw connection to the Musst card.

        msg -- the message you want to send
        ack -- if True, wait the an acknowledge (synchronous)
        """

        if(ack is True and
           not (msg.startswith("?") or msg.startswith("#"))):
           msg = "#" + msg

        ack = msg.startswith('#')
           
        with self._cnx._lock:
            self._cnx.open()
            self._cnx._write(msg)
            if msg.startswith("?") or ack:
                answer = self._cnx._readline('\n')
                if answer == '$':
                    return self._cnx._readline('$\n')
                elif ack:
                    return answer == "OK"
                else:
                    return answer

    def run(self,entryPoint=""):
        """ Execute program.

        entryPoint -- program name or a program label that
        indicates the point from where the execution should be carried out
        """
        return self.putget("#RUN %s" % entryPoint)

    def ct(self,time=None):
        """Starts the system timer, all the counting channels
        and the MCA. All the counting channels
        are previously cleared.

        time -- If specified, the counters run for that time.
        """
        if time is not None:
            return self.putget("#RUNCT %d" % time)
        else:
            return self.putget("#RUNCT")

    def upload_program(self, program_data):
        """ Upload a program.

        program_data -- program data you want to upload
        """
        self.putget("#CLEAR")
        formatted_prog= "".join(("+%s\n" % l for l in program_data.splitlines()))
        self._cnx.write(formatted_prog)
        if self.STATE != self.IDLE_STATE:
            raise RuntimeError(self.STATE)
        return True

    #    def get_data(self, nlines, npts, buf=0):
    def get_data(self,nb_counters, from_event_id = 0,):
        """ Read event musst data.

        nb_counters -- number counter you have in your program storelist
        from_event_id -- from which event you want to read

        Returns event data organized by event_id,counters
        """
        
        buffer_size,nb_buffer = self.get_event_buffer_size()
        buffer_memory = buffer_size * nb_buffer
        current_offset,current_buffer_id = self.get_event_memory_pointer()
        current_offset = current_buffer_id * buffer_size + current_offset

        from_offset = (from_event_id * nb_counters) % buffer_memory
        current_offset = current_offset / nb_counters * nb_counters
        if current_offset >= from_offset:
            nb_lines = (current_offset - from_offset) / nb_counters
            data = numpy.empty((nb_lines,nb_counters),dtype = numpy.int32)
            self._read_data(from_offset,current_offset,data)
        else:
            nb_lines = current_offset / nb_counters
            first_nblines = (buffer_memory - from_offset) / nb_counters
            nb_lines += first_nblines
            data = numpy.empty((nb_lines,nb_counters),dtype = numpy.int32)
            self._read_data(from_offset,buffer_memory,data)
            self._read_data(0,current_offset,data[first_nblines:])
        return data

    def _read_data(self,from_offset,to_offset,data):
        BLOCK_SIZE = 8*1024
        total_bytes = to_offset - from_offset
        data_pt = data.flat
        for offset,data_offset in zip(xrange(from_offset,to_offset,BLOCK_SIZE),
                                      xrange(0,total_bytes,BLOCK_SIZE)):
            size_to_read = min(BLOCK_SIZE,total_bytes)
            total_bytes -= BLOCK_SIZE
            with self._cnx._lock:
                self._cnx.open()
                self._cnx._write("?*EDAT %d %d %d" % (size_to_read,0,offset))
                data_pt[data_offset:data_offset+size_to_read] = \
                numpy.frombuffer(self._cnx.raw_read(),dtype=numpy.int32)

    def get_event_buffer_size(self):
        """ query event buffer size.

        Returns buffer size and number of buffers
        """
        return [int(x) for x in self.putget("?ESIZE").split()]

    def set_event_buffer_size(self,buffer_size,nb_buffer = 1):
        """ set event buffer size.

        buffer_size -- request buffer size
        nb_buffer -- the number of allocated buffer
        """
        return self.putget("ESIZE %d %d" % (buffer_size,nb_buffer))

    def get_histogram_buffer_size(self):
        """ query histogram buffer size.
        
        Returns buffer size and number of buffers
        """
        return [int(x) for x in self.putget("?HSIZE").split()]

    
    def set_histogram_buffer_size(self,buffer_size,nb_buffer = 1):
        """ set histogram buffer size.

        buffer_size -- request buffer size
        nb_buffer -- the number of allocated buffer
        """
        return self.putget("HSIZE %d %d" % (buffer_size,nb_buffer))

    def get_event_memory_pointer(self):
        """Query event memory pointer.

        Returns the current position of the event data memory pointer (offset,buffN)
        """
        return [int(x) for x in self.putget("?EPTR").split()]

    def set_event_memory_pointer(self,offset,buff_number = 0):
        """Set event memory pointer.

        Sets the internal event data memory pointer to point
        to the data position at offset <offset> in the buffer number <buff_number>.
        """
        return self.putget("EPTR %d %d" % (offset,buff_number))

    @property
    def STATE(self):
        """ Query module state """
        return self._string2state.get(self.putget("?STATE"))

    @property
    def TMRCFG(self):
        """ Set/query main timer timebase """
        return self.__frequency_convertion.get(self.putget("?TMRCFG"))
    
    @TMRCFG.setter
    def TMRCFG(self,value):
        if value not in self.__frequency_convertion:
            raise ValueError("Value not allowed")

        if not isinstance(value,str):
            value = self.__frequency_convertion.get(value)
        return self.putget("TMRCFG %s" % value)

    def get_channel(self,channel_id):
        if 0 < channel_id <= 6:
            return self.channel(self,channel_id)
        else:
            raise RuntimeError("musst doesn't have channel id %d" % channel_id)
