"""
Rontec MCA, acessible via serial line

yml configuration example:
name: mca
class: rontec
SLdevice: "rfc2217://lid30b2:28010"       #serial line name
calib_cf: "-0.40290063, 0.0050059618, 0"  #calibration coeficients
"""
from bliss.comm._serial import Serial
import math
import time
import numpy

class Rontec:

    ERANGE = {0:"10keV", 1:"20keV", 2:"40keV", 3:"80keV"}
    MCA_DEFAULTS = {"chmin":0, "chmax":4095}
    MCA_ERROR = {0: "General error or buffer overflow",
                 1: "Unknown command",
                 2: "Numeric parameter expected",
                 4: "Boolean parameter expected",
                 5: "Additional parameter expected",
                 6: "Unexpected parameter or character",
                 7: "Illegal numeric value",
                 8: "Unknown subcommand",
                 9: "Function not implemented or no hardware support",
                 13: "Hardware error",
                 14: "Illegal baud rate"}
                 
    def __init__(self, port=None, calib_file=None, calib_cf=[0,1,0], debug=False):
        """calib_file: rontec calibration file, should be like:
        
        #calibration factors
        0 0.00410435 1.2e-9
        """
        self.sl = Serial(port, baudrate=38400, eol='\r')
        self.calib_done = False
        self.preset_erange=None
        self.live_t = False
        self.roi_channel = None
        self.type = None
        self.times = {}
        self.debug = debug
        self.roi_dict = {}

        #connect to the hardware and make a reset
        self.reset(calib_file, calib_cf)

    def exit(self):
        self.sl.close()

    def _check_answer(self, asw, cmd):
        if not asw.startswith('!') or asw.startswith('!E'):
            e = 'Invalid answer from %s'% cmd
            if asw.startswith('!E'):
                _,err = asw.split(": ")
                e = e+': %s' %  Rontec.MCA_ERROR[int(err)]
            raise RuntimeError(e)
        else:
            if self.debug:
                print asw
            return asw

    def _calib_getch(self, energy):
        if not self.calib[2]:
            if self.calib[1]:
                return int((energy - self.calib[0])/self.calib[1])
            else:
                return 0
        cc = 1
        print self.calib
        if self.calib[1] > 0:
            cc = -1
        return int((self.calib[1]-cc*math.sqrt(math.pow(self.calib[1], 2)-4*(self.calib[0]-energy)*self.calib[2]))/(2*self.calib[2]))


    def _calib_getE(self, chan):
        return self.calib[0] + self.calib[1]*chan + self.calib[2]*math.pow(chan,2)

    def set_calibration(self, fname=None, calib_cf=None):
        """Set the energy calibration. Give a filename or a list of calibration factors.
           
           Kwargs:
               fname (str): optional filename with the calibration factors
               calib_cf (list): optional list of calibration factors
        
           Returns:
               list. Calibration factors.

           Raises:
               IOError, ValueError
        """
        if fname is None and calib_cf is None:
            raise ValueError("Either calibration file or calibration factors must be provided.")
        if isinstance(fname, str):
            calib_cf = []
            try:
                f = open(fname)
                for line in f:
                    if not line.startswith('#'):
                        calib_cf = map(float, line.split())
                    else:
                        pass
                f.close()
            except IOError:
                raise IOError('Cannot open %s' % fname)
        self.calib = calib_cf
        self.calib_done = calib_cf != [0,1,0]
        return self.calib

    def get_calibration(self):
        """Get the calibration factors list

        Returns:
            list. Calibration factors.
        """
        return self.calib
                
    def reset(self, calib_file=None, calib_cf=[0,1,0]):
        """Reset the controller and sets calibration

        Kwargs:
            calib_file (str): optional filename with the calibration factors
            calib_cf (list): optional list of calibration factors

        Returns:
            None

        Raises:
            RuntimeError, IOError, ValueError
        """
        self.sl.flush()

        #at reset Rontec sends two lines, we want the second one only
        asw = str(self.sl.write_readline("$##\r"))
        if not asw.__len__():
            raise RuntimeError('Invalid answer from reset')
        asw = self.sl.readline()
        if not asw.__len__():
            raise RuntimeError('Invalid answer from reset')
        type = asw.split()
        try:
            type.__len__() > 1
            #check if MAX/MMAX...
            if type[3] == "MMAX" or type[3] == "XDN":
                self.type = 2
            elif type[3] == "MAX":
                self.type = 1
        except Exception:
            raise RuntimeError('Invalid answer from reset')

        #check if live time accepted - depends on the firmware version
        self.sl.flush()
        asw = self.sl.write_readline("$LS\r")
        try:
            self._check_answer(asw, 'reset:livetime')
            self.live_t = True
        except RuntimeError as e:
            print e
            self.live_t = False

        self.chmin = Rontec.MCA_DEFAULTS["chmin"]
        self.chmax = Rontec.MCA_DEFAULTS["chmax"]
        if calib_file:
            self.set_calibration(calib_file)
        else:
            self.set_calibration(calib_cf=calib_cf)
        self.emin = self._calib_getE(self.chmin)
        self.emax = self._calib_getE(self.chmax)

        #last but not least - format the reading to be 4 bytes/channel, no clear after reading
        self.stop_acq()
        self.sl.flush()
        asw = str(self.sl.write_readline("$SM 4 0\r"))
        self._check_answer(asw, 'reset:set read fromat/mode')

    def set_presets(self, **kwargs):
        """Set presets parameters

           Keyword Args:
              ctime (float): real time [s]
              erange (int): the energy range, 0: 10 keV, 1: 20 keV, 2: 40 keV, 3: 80 keV
              fname (str): file name (full path) to save the raw data
           
           Returns:
              None
        """
        if kwargs.has_key("ctime"):
            #we want ms or cps - this is the IC/OC counters time(gate)
            ms_time = kwargs["ctime"] * 1000
            if ms_time < 0.001 or ms_time > 2000:
                gate_time = 1000 #1s - we want ICR and OCR in cps
            else:
                gate_time = ms_time
            asw = str(self.sl.write_readline("$CT %u\r" % gate_time))
            self._check_answer(asw, 'set_presets: ctime')

            self.times["real_time_preset"] = kwargs["ctime"]
            self.times["cycle_time_preset"] = gate_time/1000

        if kwargs.has_key("erange"):
            #set the energy range
            if kwargs["erange"] in Rontec.ERANGE:
                asw = str(self.sl.write_readline("$SE %d\r" % kwargs["erange"]))
                self._check_answer(asw, 'set_presets:erange')
                self.preset_erange = kwargs["erange"]

        if kwargs.has_key("fname"):
            self.fname = kwargs["fname"]

    def clear_spectrum(self):
        """Clear the acquired spectrum"""        
        self.sl.flush()
        asw = str(self.sl.write_readline("$CC\r"))
        self._check_answer(asw, 'clear_spectrum')

    def stop_acq(self):
        """Stop the running acquisition"""
        self.sl.flush()
        asw = str(self.sl.write_readline("$MP ON\r"))
        self._check_answer(asw, 'stop_acq')

    def start_acq(self, cnt_time=None):
        """Starts new acquisition. If cnt_time is not specified, counts for preset real time.
 
        Keyword Args:
            cnt_time (float, optional): count time in seconds; 0 means to count indefinitely.
  
        Returns:
            None 
        """
        if cnt_time >= 0:
            self.set_presets(ctime=cnt_time)
        else:
            cnt_time = self.times["real_time_preset"]
            
            
        #cnt_time is in s, firmware needs ms
        self.sl.flush()
        asw = str(self.sl.write_readline("$MT %d\r" % (cnt_time*1000)))
        self._check_answer(asw, 'start_acq')

    def set_roi(self, emin, emax, **kwargs):
        """Configure a ROI
 
        Args:
            emin (float): energy [keV] or channel number
            emax (float): energy [keV] or channel number

        Keyword Args:
            channel (int): output connector channel number (1-8)
            element (str): element name as in periodic table
            atomic_nb (int): element atomic number

        Returns:
            None

        Raises:
            KeyError
        """
        #check if input is energy [keV] or channels
        if emax > 80:
            self.chmin = emin
            self.chmax = emax
            if self.calib_done:
                self.emin = self._calib_getE(self.chmin)
                self.emax = self._calib_getE(self.chmax)
        else:
            self.emin = emin
            self.emax = emax
            if self.calib_done:
                self.chmin = self._calib_getch(self.emin)
                self.chmax = self._calib_getch(self.emax)
        if kwargs.has_key("channel") and self.type == 2:
            roi_channel = kwargs.get("channel",1)
            #test if channel is between 1 and 8
            if roi_channel < 1 or roi_channel > 8:
                raise KeyError("Channel number is should be between 1 and 8")
            self.roi_dict[roi_channel] = "%2.4f(%d) %2.4f(%d)" % (self.emin, self.chmin, self.emax, self.chmax)
            roi_str = "$SK %d %d %s %d %d\r" % (roi_channel, kwargs.get("atomic_nb", 34), kwargs.get("element", "Se"), emin*1000, emax*1000)
            self.sl.flush()
            asw = str(self.sl.write_readline(roi_str))
            self._check_answer(asw, 'set_roi')

    def clear_roi(self, **kwargs):
         """Clear ROI settings

         Keyword Args:
            channel (int): optional output connector channel number (1-8)
    
         Returns:
            None
         """
         self.chmin = Rontec.MCA_DEFAULTS["chmin"]
         self.chmax = Rontec.MCA_DEFAULTS["chmax"]
         if self.calib_done:
            self.emin = self._calib_getE(self.chmin)
            self.emax = self._calib_getE(self.chmax)
         if kwargs.has_key("channel") and self.type == 2:
             self.sl.flush()
             roi_channel = kwargs[channel]
             asw = str(self.sl.write_readline("$SK %d 0 0 0\r" % roi_channel))
             self._check_answer(asw, 'clear_roi')
             try:
                 self.roi_dict.pop(roi_channel)
             except KeyError:
                 pass
 
    def get_roi(self, **kwargs):
        """Get ROI settings

        Keyword Args:
            channel (int): output connector channel number (1-8)

        Returns:
            dict. ROI dictionary.
        """
        argout = {}
        argout["chmin"]= self.chmin
        argout["chmax"] =  self.chmax
        if kwargs.has_key("channel"):
            roi_channel = int(kwargs.get("channel"))
            #test if channel is between 1 and 8
            if roi_channel < 1 or roi_channel > 8:
                return argout
        else:
            roi_channel = 0

        if self.type == 2 and roi_channel:
            asw = str(self.sl.write_readline("$GK %d\r"% roi_channel))
            if self.debug:
                print asw
            self._check_answer(asw, 'get_roi')
            asw = asw[4:]
            argout["ext_roi"] = asw
            _,_,self.emin,self.emax = asw.split()
            self.emin = float(self.emin) / 1000
            self.emax = float(self.emax) / 1000
            self.roi_dict[roi_channel] = "%2.4f(%d) %2.4f(%d)" % (self.emin, self.chmin, self.emax, self.chmax)
        else:
            try:
                argout.pop("ext_roi")
            except KeyError:
                pass

        if self.calib_done:
            argout["chmin"] = self._calib_getch(self.emin)
            argout["chmax"] = self._calib_getch(self.emax)
        else:
            self.emin = self._calib_getE(self.chmin)
            self.emax = self._calib_getE(self.chmax)
        
        argout["emin"] = self.emin
        argout["emax"] = self.emax
        return argout

    def get_times(self):
        """Return a dictionary with the preset and elapsed real time [s], 
        elapsed live time (if possible) [s] and the dead time [%].

        Returns:
            dict. Times dictionary.

        Raises:
            RuntimeError
        """
        #real time elapsed
        self.sl.flush()
        asw = str(self.sl.write_readline("$MR\r"))
        self._check_answer(asw, 'get_time:real time elapsed')
        if self.debug:
            print asw
        try:
            _,rt = asw.split()
            #the answer is in ms, we return time in s
            self.times["real_time_elapsed"] = float(rt)/1000
            if self.times["real_time_preset"]:
                self.times["real_time_elapsed"] = self.times["real_time_preset"] - self.times["real_time_elapsed"]
                
        except:
            raise RuntimeError('Cannot get the elapsed real time')

        #dead time
        #get the ICR
        self.sl.flush()
        asw = str(self.sl.write_readline("$BC\r"))
        self._check_answer(asw, 'get_time:ICR')
        try:
            _,icr = asw.split()
            self.times["ICR"] = float(icr)
        except:
            raise RuntimeError('Cannot get the ICR')

        #get the OCR
        self.sl.flush()
        asw = str(self.sl.write_readline("$NC\r"))
        self._check_answer(asw, 'get_time:OCR')
        try:
            _,ocr = asw.split()
            #correct with the cycle time
            if ocr > self.times["cycle_time_preset"]:
                ocr = float(ocr) - self.times["cycle_time_preset"]
            self.times["OCR"] = float(ocr)
        except:
            raise RuntimeError('Cannot get the OCR')
        
        #calculate the dead time in %
        if self.times["ICR"] < 1000 or self.times["ICR"] < self.times["OCR"]:
            self.times["dead_time"] = 0
        else:
            self.times["deat_time"] = ((self.times["ICR"]-self.times["OCR"])/self.times["ICR"])*100.
        
        #live time elapsed
        if self.live_t:
            self.sl.flush()
            asw = str(self.sl.write_readline("$LR\r"))
            self._check_answer(asw, 'get_time:live time elapsed')
            try:
                _,lt = asw.split()
                #the answer is in ms, we return time in s
                self.times["live_time"] = float(lt)/1000
            except:
                raise RuntimeError('Cannot get the elapsed live time')
        return self.times
            
    def get_presets(self, **kwargs):
        """Get the preset parameters

        Keyword Args:
            ctime (float): Real time
            erange (int): energy range
            fname (str): filename where the data are stored

        Returns:
            dict.

        Raises:
            RuntimeError
        """
        if kwargs.has_key("ctime"):
            try:
                return self.times["real_time_preset"]
            except:
                raise RuntimeError('Count time not set')
        if kwargs.has_key("erange"):
            if self.preset_erange:
                return Rontec.ERANGE[self.preset_erange]
            else:
                self.sl.flush()
                asw = str(self.sl.write_readline("$FE\r"))
                self._check_answer(asw, 'get_presets:energy range')
                try:
                    _,rr = asw.split()
                    self.preset_erange = int(rr)
                    return Rontec.ERANGE[self.preset_erange]
                except:
                    raise RuntimeError('Energy range not set')

    def read_roi_data(self, save_data=False):
        """Reads ROI data

        Keyword Args:
            save_data (bool): save data in the file or not, defaults to False
     
        Returns:
            list. Raw data for the predefined ROI channels.
        """
        return self.read_raw_data(self.chmin, self.chmax, save_data)
        
    def read_data(self, chmin=0, chmax=4095, calib=False, save_data=False):
        """Reads the data

        Keyword Args:
            chmin (float): channel number or energy [keV], defaults to 0
            chmax (float): channel number or energy [keV], defaults to 4095
            calib (bool): use calibration, defaults to False
            save_data (bool): save data in the file or not, defaults to False
     
        Returns:
            numpy.array. x - channels or energy (if calib=True), y - data.
        """
        # the input is energy and the calibration is done
        if chmax < 30 and self.calib_done:
            chmin  = _calib_getch(chmin)
            chmax  = _calib_getch(chmax)
        y = self.read_raw_data(chmin, chmax, save_data)
        x = numpy.arange(y.__len__()).astype(numpy.float)
        if calib:
           x = self.calib[0] + self.calib[1]*x + self.calib[2]*math.pow(x,2)
        y = numpy.array(y).astype(numpy.float)
        data = numpy.array([x,y])
        #data = data.transpose()
        return data

    def read_raw_data(self, chmin=0, chmax=4095, save_data=False):
        """Reads raw data

        Keyword Args:
            chmin (int): channel number, defaults to 0
            chmax (int): channel number, defaults to 4095
            save_data (bool): save data in the file or not, defaults to False
     
        Returns:
            list. Raw data. 
        """
        size = int(chmax - chmin + 1)
        #read only what is asked
        self.sl.flush()
        asw = str(self.sl.write_readline("$SS %d,1,1,%d\r" % (chmin, size)))
        self._check_answer(asw, 'read_raw_data:handshake answer reading')
        #read again to get the data
        raw_data = self.sl.read(size=size*4,timeout=10)
        data = ' '.join([ "%02x" % ord(i) for i in raw_data]).split()
        if self.debug:
            print "read %d characters" % data.__len__()
        #we read 4 bytes/ch (hhhhhhhh ........ ........ llllllll)
        dd = [int('0x'+i+j+k+l,16) for i,j,k,l in zip(data[::4], data[1::4], data[2::4], data[3::4])]
        
        if save_data:
            fd = open(self.fname, "a+")
            fd.write("#\n#S 1  mcaacq %d\n" % self.times["real_time_preset"])
            if self.calib_done:
                fd.write("#@CALIB %g %g %g\n@A" % (self.calib[0], self.calib[1],self.calib[2]))
                fd.write(' '.join(map(str, dd)) + "\n")
        return dd

class rontec:
    def __init__(self, name, config):
        self.mca = Rontec(config["SLdevice"])
        calib_cf = config["calib_cf"]
        self.calib_cf = []
        try:
            for i in calib_cf.split(","):
                self.calib_cf.append(float(i))
            self.set_calibration(calib_cf = self.calib_cf)
        except:
            self.calib_cf = [0, 1, 0]

    def read_raw_data(self, chmin=0, chmax=4095, save_data=False):
        return self.mca.read_raw_data(chmin, chmax, save_data)

    def read_roi_data(self,save_data=False):
        return self.mca.read_roi_data(save_data)

    def read_data(self, chmin=0, chmax=4095, calib=False, save_data=False):
        return self.mca.read_data(chmin, chmax, calib, save_data)

    def set_calibration(self, fname=None, calib_cf=[0, 1, 0]):
        return self.mca.set_calibration(fname, calib_cf)

    def get_calibration(self):
        return self.mca.get_calibration()

    def set_roi(self, emin, emax, **kwargs):
        self.mca.set_roi(emin, emax, **kwargs)

    def get_roi(self, **kwargs):
        return self.mca.get_roi(**kwargs)

    def clear_roi(self, **kwargs):
        self.mca.clear_roi(**kwargs)

    def get_times(self):
        return self.mca.get_times()

    def get_presets(self, **kwargs):
        return self.mca.get_presets(**kwargs)

    def set_presets(self, **kwargs):
        self.mca.set_presets(**kwargs)

    def start_acq (self, cnt_time=None):
        self.mca.start_acq(cnt_time)

    def stop_acq (self):
        self.mca.stop_acq()

    def clear_spectrum (self):
        self.mca.clear_spectrum()

if __name__ == '__main__':
    #det = Rontec("/dev/ttyR8")
    #det = Rontec("ser2net://lid30b2:8800/dev/ttyR8")
    #port number found in ser2net.conf of lid30b2
    det = Rontec("rfc2217://lid30b2:28010")

    det.clear_spectrum()
    det.set_calibration(calib_cf=[-0.40290063, 0.0050059618, 0])

    det.set_roi(2, 15, channel=1)
    cd = det.get_roi(channel=1)
    print cd
    det.set_presets(erange=1, ctime=5, fname="/tmp/newdata.mca")
    print "erange ", det.get_presets(erange="erange")
    print "ctime", det.get_presets(ctime="ctime")
    det.start_acq()
    bbb = det.get_times()
    print bbb
    time.sleep(5)
    cc = det.get_times()
    print cc
    aaa = det.read_data(0,4095)
    print aaa
    #bbb = det.read_raw_data(0,100)
    bbb = det.read_raw_data(save_data=True)
    print sum(bbb)/cc["real_time_elapsed"]

