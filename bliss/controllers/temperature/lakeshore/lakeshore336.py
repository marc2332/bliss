from bliss.common import log

from bliss.controllers.temperature.lakeshore.lakeshore import Base
from bliss.controllers.temperature.lakeshore.lakeshore330 import LakeShore330


class LakeShore336(LakeShore330):

    MODE336 = ('Off', 'Closed Loop' 'Zone', 'Open Loop', 'Monitor Out',
               'Warmup Supply', 'Auto Tune P', 'Auto Tune PI', 'Auto Tune PID')

    def __init__(self, comm_type, url, **kwargs):
        _ls = LakeShore330(comm_type, url, **kwargs)
        self._comm = _ls._comm

    def outmode(self, **kwargs):
        """ Read/Set Output Mode Parameters. Modes 4 and 5 are only valid for
            Analog Outputs (3 and 4)
            Kwargs:
               mode (int): control mode: 0=Off, 1=Closed Loop PID,
                           2=Zone, 3=Open Loop, 4=Monitor Out,
                           5=Warmup Supply.
               input (int): input to use for control: 0=None), 1=A,
                            2=B, 3=C, 4=D (5=Input D2, 6=Input D3,
                            7=Input D4, 8=Input D5 for 3062 option)
          Returns:
               None if set
               mode (str): control mode
               input (int): input channel
        """
        mode = kwargs.get('mode')
        inp = kwargs.get('input')
        if None not in (mode, inp):
            self.send_cmd('OUTMODE', mode, inp)
        else:
            mode, inp = send_cmd('OUTMODE?').split(',')
            return LakeShore336.MODE336[int(mode)], int(inp)


class lakeshore336(Base):

    def __init__(self, config, *args):
        comm_type = None
        extra_param = None
        if 'gpib' in config:
            comm_type = 'gpib'
            url = config['gpib']['url']
            extra_param = config['gpib']['pad']
            eos = config.get('gpib').get('eos', "\r\n")
        elif 'serial' in config:
            comm_type = 'serial'
            url = config['serial']['url']
            extra_param = config.get('serial').get('baudrate')
            eos = config.get('serial').get('eos', "\r\n")
        elif 'tcp' in config:
            comm_type = 'tcp'
            url = config['tcp']['url']
            eos = config.get('tcp').get('eos', "\r\n")
        else:
            raise ValueError("Must specify gpib or serial url")

        _lakeshore = LakeShore336(comm_type, url,
                                  extra_param=extra_param, eos=eos)
        Base.__init__(self, _lakeshore, config, *args)
