__all__ = ['Cmd', 'FuncCmd', 'ErrCmd', 'ErrArrayCmd',
           'OnOffCmd', 'OnOffCmdRO', 'OnOffCmdRW',
           'BoolCmd', 'BoolCmdRO', 'BoolCmdRW',
           'IntCmd', 'IntCmdRO', 'IntCmdWO',
           'FloatCmd', 'FloatCmdRO', 'FloatCmdWO',
           'StrCmd', 'StrCmdRO', 'StrCmdWO',
           'IntArrayCmdRO', 'FloatArrayCmdRO',
           'commands', 'command_aliases']

from functools import partial

import numpy

def __decode_IDN(s):
    manuf, model, serial, version = map(str.strip, s.split(','))
    model = model.split(" ", 1)[-1]
    return dict(manufacturer=manuf, model=model, serial=serial, version=version)

def __decode_Err(s):
    code, desc = map(str.strip, s.split(',', 1))
    return dict(code=int(code), desc=desc[1:-1])

def __decode_ErrArray(s):
    msgs = map(str.strip, s.split(','))
    result = []
    for i in range(0, len(msgs), 2):
        code, desc = int(msgs[i]), msgs[i+1][1:-1]
        if code == 0: continue
        result.append(dict(code=code, desc=desc))
    return result

def __decode_OnOff(s):
    su = s.upper()
    if su in ("1", "ON"):
        return True
    elif su in ("0", "OFF"):
        return False
    else:
        raise ValueError("Cannot decode OnOff value {0}".format(s))

def __encode_OnOff(s):
    if s in (0, False, "off", "OFF"):
        return "OFF"
    elif s in (1, True, "on", "ON"):
        return "ON"
    else:
        raise ValueError("Cannot encode OnOff value {0}".format(s))

__decode_IntArray = partial(numpy.fromstring, dtype=int, sep=',')
__decode_FloatArray = partial(numpy.fromstring, dtype=float, sep=',')

#: SCPI command
#: accepts the following keys:
#:
#:   - cmd_name - command name (str, optional, default is the name of the key
#:                in the dictionary it is in)
#:   - func_name - functional API name (str, optional, default is the cmd_name)
#:   - doc - command documentation (str, optional)
#:   - get - translation function called on the result of a query.
#:           If not present means command cannot be queried.
#:           If present and is None means ignore query result
#:   - set - translation function called before a write.
#:           If not present means command cannot be written.
#:           If present and is None means it doesn't receive any argument
Cmd = dict

FuncCmd = partial(Cmd, set=None)

IntCmd = partial(Cmd, get=int, set=int)
IntCmdRO = partial(Cmd, get=int)
IntCmdWO = partial(Cmd, set=int)

FloatCmd = partial(Cmd, get=float, set=float)
FloatCmdRO = partial(Cmd, get=float)
FloatCmdWO = partial(Cmd, set=float)

StrCmd = partial(Cmd, get=str, set=str)
StrCmdRO = partial(Cmd, get=str)
StrCmdWO = partial(Cmd, set=str)

IntArrayCmdRO = partial(Cmd, get=__decode_IntArray)
FloatArrayCmdRO = partial(Cmd, get=__decode_FloatArray)
StrArrayCmd = partial(Cmd, get=lambda x: x.split(','), set=lambda x: ",".join(x))
StrArrayCmdRO = partial(Cmd, get=lambda x: x.split(','))

OnOffCmd = partial(Cmd, get=__decode_OnOff, set=__encode_OnOff)
OnOffCmdRO = partial(Cmd, get=__decode_OnOff)
OnOffCmdWO = partial(Cmd, set=__encode_OnOff)
BoolCmd = OnOffCmd
BoolCmdRO = OnOffCmdRO
BoolCmdWO = OnOffCmdWO

ErrCmd = partial(Cmd, get=__decode_Err)
ErrArrayCmd = partial(Cmd, get=__decode_ErrArray)

commands = {
    '*CLS': FuncCmd(doc='clear status'),
    '*ESE': IntCmd(doc='standard event status enable register'),
    '*ESR': IntCmdRO(doc='standard event event status register'),
    '*IDN': Cmd(get=__decode_IDN, doc='identification query'),
    '*OPC': IntCmdRO(set=None, doc='operation complete'),
    '*OPT': IntCmdRO(doc='return model number of any installed options'),
    '*RCL': IntCmdWO(set=int, doc='return to user saved setup'),
    '*RST': FuncCmd(doc='reset'),
    '*SAV': IntCmdWO(doc='save the preset setup as the user-saved setup'),
    '*SRE': IntCmdWO(doc='service request enable register'),
    '*STB': StrCmdRO(doc='status byte register'),
    '*TRG': FuncCmd(doc='bus trigger'),
    '*TST': Cmd(get=lambda x : not decode_OnOff(x),
                doc='self-test query'),
    '*WAI': FuncCmd(doc='wait to continue'),

    'SYSTem:ERRor[:NEXT]': ErrCmd(doc='return and clear oldest system error'),
}

