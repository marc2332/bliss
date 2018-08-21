from bliss.common import log

from bliss.controllers.temperature.lakeshore.lakeshore import Base
from bliss.controllers.temperature.lakeshore.lakeshore330 import LakeShore330


class LakeShore332(LakeShore330):
    MODE332 = (
        "Off",
        "Manual PID",
        "Zone",
        "Open Loop",
        "Auto Tune PID",
        "Auto Tune PI",
        "Auto Tune P",
    )

    def __init__(self, comm_type, url, **kwargs):
        _ls = LakeShore330(comm_type, url, **kwargs)
        self._comm = _ls._comm
        self.eos = _ls.eos

    def cset(self, channel, **kwargs):
        """ Read/Set Control Loop Parameters
            Args:
               channel(int): loop channel. Valid entries: 1 or 2
            Kwargs:
               input (str): which input to control from. Valid entries: A or B
               off (bool): switch on (True) or off (False) the control loop
          Returns:
               None if set
               input (str): which input to control from
               off (bool): control loop on/off
        """
        self._channel = channel
        inp = kwargs.get("input", "")
        off = kwargs.get("off")
        if isinstance(off, bool):
            self.send_cmd("CSET", inp, 1, int(off))
        else:
            asw = send_cmd("CSET?").split(",")
            return asw[1], bool(asw[3])

    def cmode(self, channel, mode=None):
        """ Read/Set Control Loop Mode
            Args:
               channel(int): loop channel. Valid entries: 1 or 2
               mode (int): control mode. Valid entries: 1=Manual PID,
                           2=Zone, 3=Open Loop, 4=AutoTune PID,
                           5=AutoTune PI, 6=AutoTune P
          Returns:
               None if set
               mode (int): mode
        """
        self._channel = channel
        if mode:
            self.send_cmd("CMODE", mode)
        else:
            return LakeShore332.MODE332[int(self.send_cmd("CMODE?"))]


class lakeshore332(Base):
    def __init__(self, config, *args):
        comm_type = None
        extra_param = None
        if "gpib" in config:
            comm_type = "gpib"
            url = config["gpib"]["url"]
            extra_param = config["gpib"]["pad"]
            eos = config.get("gpib").get("eos", "\r\n")
        elif "serial" in config:
            comm_type = "serial"
            url = config["serial"]["url"]
            extra_param = config.get("serial").get("baudrate")
            eos = config.get("serial").get("eos", "\r\n")
        elif "tcp" in config:
            comm_type = "tcp"
            url = config["tcp"]["url"]
            eos = config.get("tcp").get("eos", "\r\n")
        else:
            raise ValueError("Must specify gpib or serial url")

        _lakeshore = LakeShore332(comm_type, url, extra_param=extra_param, eos=eos)
        Base.__init__(self, _lakeshore, config, *args)
