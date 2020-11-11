import gevent

from bliss import global_map
from bliss.comm.util import get_comm
from bliss.common.greenlet_utils import protect_from_kill
from bliss.common.counter import SamplingCounter, SamplingMode
from bliss.controllers.counter import SamplingCounterController
from bliss.common.axis import AxisState
from bliss.controllers.motor import Controller


class Bcdu8:
        
    def __init__(self, name, config_tree):

        self._name = name

        # Commands
        self.calib = Bcdu8CommandCalib(self)
        self.chan = Bcdu8CommandChan(self)
        self.delay = Bcdu8CommandDelay(self)      
        # Communication
        self._cnx = get_comm(config_tree, timeout=3)
        global_map.register(self, children_list=[self._cnx])

    def __info__(self):
        info_str  = f"BCDU8\n\n"
        info_str += f"Name:   {self._name}\n"
        info_str += f"Host:   {self._cnx._host}\n"
        info_str += f"Socket: {self._cnx._port}\n\n"
        info_str += self._comm("?CONFIG")
        return info_str

    def help(self):
        ret = self._comm("?HELP")
        print(ret)
        
    def command(self, cmd):
        return(self._comm(cmd))
        
    """
    Check Methods
    """
    def _check_unit(self, unit, cmd):
        if unit.lower() not in ["ps", "ns", "us", "ms", "s"]:
            raise RuntimeError(f"{self._name}.{cmd} - unit - [ps | ns | us | ms | s]")
            
    def _check_output_first(self, output, cmd):
        if output.upper() not in ["O1", "O2"]:
            raise RuntimeError(f"{self._name}.{cmd} - output - [O1 | O2]")
            
    def _check_output_all(self, output, cmd):
        if output.upper() not in ["O1", "O2", "O2", "O3", "O4", "O5", "O6", "O7", "O8"]:
            raise RuntimeError(f"{self._name}.{cmd} - output - [O1 | O2 | O3 | O4 | O5 | O6 | O7 | O8]")
    
    def _check_polarity(self, polarity, cmd):
        if polarity not in ["NORMAL", "INVERTED"]:
            raise RuntimeError(f"{self._name}.{cmd} - polarity - [NORMAL | INVERTED]")
    
    def _check_perid(self, period, cmd):
        if period < 8 or period > 71303168:
            raise RuntimeError(f"{self._name}.{cmd} - period - [8 - 71303168 (34x32x256x256)]")
    
    def _check_offon(self, offon, cmd):
        if offon.lower() not in ["off", "on"]:
            raise RuntimeError(f"{self._name}.{cmd} - offon - [off | on]")

    """
    Ethernet Communication
    """

    def _comm_ack(self, msg):
        return self.comm("#" + msg)

    @protect_from_kill
    def _comm(self, cmd, timeout=None, text=True):
        self._cnx.open()
        with self._cnx._lock:
            self._cnx._write((cmd + "\r\n").encode())
            if cmd.startswith("?") or msg.startswith("#"):
                msg = self._cnx._readline(timeout=timeout)
                cmd = cmd.strip("#").split(" ")[0]
                msg = msg.replace((cmd + " ").encode(), "".encode())
                if msg.startswith("$".encode()):
                    msg = self._cnx._readline(
                        #transaction=transaction,
                        #clear_transaction=False,
                        eol="$\n",
                        timeout=timeout,
                    )
                    return msg.strip("$\n".encode()).decode()
                elif msg.startswith("ERROR".encode()):
                    raise RuntimeError(msg.decode())
                if text:
                    return (msg.strip("\r\n".encode())).decode()
                else:
                    return msg.strip("\r\n".encode())
            
class Bcdu8CommandCalib:
    def __init__(self, bcdu8):
        self._bcdu8 = bcdu8
        self._name = "CALIB"
                
    def __info__(self):
        desc =  "Command:\n"
        desc += "    calib.set({\"O1\"|\"O2\"}, <calValue>, {\"ps\"|\"ns\"|\"us\"|\"ms\"|\"s\"})\n"
        desc += "Query:\n"
        desc += "    calib.get({\"O1\"|\"O2\"} , {\"ps\"|\"ns\"|\"us\"|\"ms\"|\"s\"})"
        return desc
        
    def set(self, output, calValue, unit):
        self._bcdu8._check_output_first(output, "calib")
        self._bcdu8._check_unit(unit, "calib")
        self._bcdu8._comm(f"{self._name} {output} {calValue} {unit}")
        
    def get(self, output, unit):
        self._bcdu8._check_output_first(output, "calib")
        self._bcdu8._check_unit(unit, "calib")
        return(self._bcdu8._comm(f"?{self._name} {output} {unit}"))
            
class Bcdu8CommandChan:
    def __init__(self, bcdu8):
        self._bcdu8 = bcdu8
        self._name = "CHAN"
                
    def __info__(self):
        desc =  "Command:\n"
        desc += "    chan.set(\"O<n>\", \"[{NORMAL|INVERTED}]\", \"[<period>]\", \"[<width>]\", \"[<delay>]\")\n"
        desc += "       or\n"
        desc += "    chan.set(\"O<n>\" \"{OFF|ON}\")\n"
        desc += "Query:\n"
        desc += "    chan.get(\"O<n>\")"
        return desc
        
    def set(self, output, offon=None, polarity=None, period=None, width=None, delay=None):
        # TO DO: check width and delay
        self._bcdu8._check_output_all(output, "chan")
        cmd = f"{self._name} {output}"
        if offon is not None:
            self._bcdu8_check_offon(offon, "chan")
            cmd += f" {offon}"
        else:
            if polarity is not None:
                self._bcdu8_check_polarity(polarity, "chan")
                cmd += " {polarity}"
            if period is not None:
                self._bcdu8_check_period(period, "chan")
                cmd += " PERIOD {period}"
            if width is not None:
                cmd += " WIDTH {width}"
            if delay is not None:
                cmd += " DELAY {delay}"
        self._bcdu8._comm(cmd)
        
    def get(self, output):
        self._bcdu8._check_output_all(output, "chan")
        return(self._bcdu8._comm(f"?{self._name} {output}"))
            
class Bcdu8CommandDelay:
    def __init__(self, bcdu8):
        self._bcdu8 = bcdu8
        self._name = "DELAY"
                
    def __info__(self):
        desc =  "Command:\n"
        desc += "    delay.set(\"O<n>\", <chanDelay>, [{\"ps\"|\"ns\"|\"us\"|\"ms\"|\"s\"}])\n"
        desc += "Query:\n"
        desc += "    delay.get(\"O<n>\", [{\"ps\"|\"ns\"|\"us\"|\"ms\"|\"s\"}])\n"
        desc += "       or\n"        
        desc += "    delay.get(\"{O1|O2} #\")"
        return desc
        
    def set(self, output, offon=None, polarity=None, period=None, width=None, delay=None):
        # TO DO: check width and delay
        self._bcdu8._check_output_all(output, "chan")
        cmd = f"{self._name} {output}"
        if offon is not None:
            self._bcdu8_check_offon(offon, "chan")
            cmd += f" {offon}"
        else:
            if polarity is not None:
                self._bcdu8_check_polarity(polarity, "chan")
                cmd += " {polarity}"
            if period is not None:
                self._bcdu8_check_period(period, "chan")
                cmd += " PERIOD {period}"
            if width is not None:
                cmd += " WIDTH {width}"
            if delay is not None:
                cmd += " DELAY {delay}"
        self._bcdu8._comm(cmd)
        
    def get(self, output, unit=None):
        if output.upper() in ["O1 #", "O2 #"]:
            return self._bcdu8._comm(f"?{self._name} {output}")
        else:
            self._bcdu8._check_output_all(output, "delay")
            self._bcdu8._check_unit(unit, "delay")
            return(self._bcdu8._comm(f"?{self._name} {output} {unit}"))
