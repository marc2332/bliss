"""
:term:`SCPI` helpers (:class:`~bliss.comm.scpi.SCPI` class and \
:func:`~bliss.comm.scpi.BaseSCPIDevice` )

Example::

    >>> from bliss.comm.scpi import SCPI

    >>> # SCPI object initiated with standard SCPI commands (*IDN, *CLS, etc)
    >>> scpi = SCPI(gpib={'url': 'enet://example.com', 'pad': 15})

    >>> # another way is to create the interface before and assign it to SCPI:
    >>> from bliss.comm.gpib import Gpib
    >>> interface = Gpib(url="enet://example.com", pad=15)
    >>> scpi = SCPI(interface)

    # functional API
    >>> scpi('*IDN?')
    [('*idn?',
      {'manufacturer': 'KEITHLEY INSTRUMENTS INC.',
       'model': 'MODEL 6485',
       'serial': '1008577',
       'version': 'B03   Sep 25 2002 10:53:29/A02  /E'})]

    # dict like API
    >>> scpi['*IDN']
    {'manufacturer': 'KEITHLEY INSTRUMENTS INC.',
     'model': 'MODEL 6485',
     'serial': '1008577',
     'version': 'B03   Sep 25 2002 10:53:29/A02  /E'}

     # dict assignment

"""


import re
import inspect
from functools import partial

import numpy

from .util import get_interface
from .exceptions import CommunicationError, CommunicationTimeout
from bliss.common import session
from bliss.common.logtools import LogMixin


def decode_IDN(s):
    manuf, model, serial, version = map(str.strip, s.split(","))
    return dict(manufacturer=manuf, model=model, serial=serial, version=version)


def __decode_Err(s):
    code, desc = map(str.strip, s.split(",", 1))
    return dict(code=int(code), desc=desc[1:-1])


def __decode_ErrArray(s):
    msgs = map(str.strip, s.split(","))
    result = []
    for i in range(0, len(msgs), 2):
        code, desc = int(msgs[i]), msgs[i + 1][1:-1]
        if code == 0:
            continue
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


__decode_IntArray = partial(numpy.fromstring, dtype=int, sep=",")
__decode_FloatArray = partial(numpy.fromstring, dtype=float, sep=",")

#: SCPI command
#: accepts the following keys:
#:
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

IntCmd = partial(Cmd, get=int, set=str)
IntCmdRO = partial(Cmd, get=int)
IntCmdWO = partial(Cmd, set=str)

FloatCmd = partial(Cmd, get=float, set=str)
FloatCmdRO = partial(Cmd, get=float)
FloatCmdWO = partial(Cmd, set=str)

StrCmd = partial(Cmd, get=str, set=str)
StrCmdRO = partial(Cmd, get=str)
StrCmdWO = partial(Cmd, set=str)

IntArrayCmdRO = partial(Cmd, get=__decode_IntArray)
FloatArrayCmdRO = partial(Cmd, get=__decode_FloatArray)
StrArrayCmd = partial(Cmd, get=lambda x: x.split(","), set=lambda x: ",".join(x))
StrArrayCmdRO = partial(Cmd, get=lambda x: x.split(","))

OnOffCmd = partial(Cmd, get=__decode_OnOff, set=__encode_OnOff)
OnOffCmdRO = partial(Cmd, get=__decode_OnOff)
OnOffCmdWO = partial(Cmd, set=__encode_OnOff)
BoolCmd = OnOffCmd
BoolCmdRO = OnOffCmdRO
BoolCmdWO = OnOffCmdWO

IDNCmd = partial(Cmd, get=decode_IDN, doc="identification query")

ErrCmd = partial(Cmd, get=__decode_Err)
ErrArrayCmd = partial(Cmd, get=__decode_ErrArray)


def min_max_cmd(cmd_expr):
    """
    Find the shortest and longest version of a SCPI command expression

    Example::

    >>> min_max_cmd('SYSTem:ERRor[:NEXT]')
    ('SYST:ERR', 'SYSTEM:ERROR:NEXT')
    """
    result_min, optional = "", 0
    for c in cmd_expr:
        if c.islower():
            continue
        if c == "[":
            optional += 1
            continue
        if c == "]":
            optional -= 1
            continue
        if optional:
            continue
        result_min += c
    result_min = result_min.lstrip(":")
    result_max = cmd_expr.replace("[", "").replace("]", "").upper().lstrip(":")
    return result_min, result_max


def cmd_expr_to_reg_expr_str(cmd_expr):
    """
    Return a regular expression string from the given SCPI command expression.
    """
    # Basicaly we replace [] -> ()?, and LOWercase -> LOW(ercase)?
    # Also we add :? optional to the start and $ to the end to make sure
    # we have an exact match
    reg_expr, low_zone = r"\:?", False
    for c in cmd_expr:
        cl = c.islower()
        if not cl:
            if low_zone:
                reg_expr += ")?"
            low_zone = False
        if c == "[":
            reg_expr += "("
        elif c == "]":
            reg_expr += ")?"
        elif cl:
            if not low_zone:
                reg_expr += "("
            low_zone = True
            reg_expr += c.upper()
        elif c in "*:":
            reg_expr += "\\" + c
        else:
            reg_expr += c

    # if cmd expr ends in lower case we close the optional zone 'by hand'
    if low_zone:
        reg_expr += ")?"

    return reg_expr + "$"


def cmd_expr_to_reg_expr(cmd_expr):
    """
    Return a compiled regular expression object from the given SCPI command
    expression.
    """
    return re.compile(cmd_expr_to_reg_expr_str(cmd_expr), re.IGNORECASE)


class Commands(object):
    r"""
    A dict like container for SCPI commands. Construct a Commands object like a
    dict.  When creating a Commands object, *args* must either:

    * another *Commands* object
    * a dict where keys must be SCPI command expressions
      (ex: `SYSTem:ERRor[:NEXT]`) and values instances of *Cmd*
    * a sequence of pairs where first element must be SCPI command expression
      and second element an instance of *Cmd*

    *kwargs* should also be SCPI command expressions; *kwargs* values should be
    instances of *Cmd*.

    The same way, assignment keys should be SCPI command expressions and
    assignment values should be instances of *Cmd*.

    Examples::

        from bliss.comm.scpi import FuncCmd, ErrCmd, IntCmd, Commands

        # c1 will only have \*CLS command
        c1 = Commands({'*CLS': FuncCmd(doc='clear status'),
                       '*RST': FuncCmd(doc='reset')})

        # c2 will have \*CLS and VOLTage commands
        c2 = Commands(c1, VOLTage=IntCmd())

        # add error command to c2
        c2['SYSTem:ERRor[:NEXT]'] = ErrCmd()

    Access to a command will return the same command for different SCPI command
    alternatives. Note that access to command is done through a specific form
    of SCPI command and not the entire SCPI command expression (as opposed to
    the assignment):

        >>> err_cmd1 = c2['SYST:ERR']
        >>> err_cmd2 = c2[':system:error:next']
        >>> print(err_cm1 == err_cmd2)
        True
    """

    def __init__(self, *args, **kwargs):
        self.command_expressions = {}
        self._command_cache = {}
        for arg in args:
            self.update(arg)
        self.update(kwargs)

    def __setitem__(self, cmd_expr, command):
        min_cmd, max_cmd = min_max_cmd(cmd_expr)
        cmd_info = dict(
            command,
            re=cmd_expr_to_reg_expr(cmd_expr),
            min_command=min_cmd,
            max_command=max_cmd,
        )
        self.command_expressions[cmd_expr] = cmd_info
        return cmd_info

    def __getitem__(self, cmd_name):
        cmd = self.get_command(cmd_name)
        if cmd is None:
            raise KeyError(cmd_name)
        return cmd

    def __contains__(self, cmd_name):
        return self.get(cmd_name) is not None

    def __len__(self):
        return len(self.command_expressions)

    def get_command(self, cmd_name):
        cmd_expr = self.get_command_expression(cmd_name)
        return self.command_expressions[cmd_expr]

    def get_command_expression(self, cmd_name):
        cmd_name_u = cmd_name.upper()
        try:
            return self._command_cache[cmd_name_u]
        except KeyError:
            for cmd_expr, cmd_info in self.command_expressions.items():
                reg_expr = cmd_info["re"]
                if reg_expr.match(cmd_name):
                    self._command_cache[cmd_name.upper()] = cmd_expr
                    return cmd_expr
        raise KeyError(cmd_name)

    def get(self, cmd_name, default=None):
        try:
            return self.get_command(cmd_name)
        except KeyError:
            return default

    def update(self, commands):
        if isinstance(commands, Commands):
            self.command_expressions.update(commands.command_expressions)
            self._command_cache.update(commands._command_cache)
        elif isinstance(commands, dict):
            for cmd_expr, cmd in commands.items():
                self[cmd_expr] = cmd
        else:
            for cmd_expr, cmd in commands:
                self[cmd_expr] = cmd


COMMANDS = Commands(
    {
        "*CLS": FuncCmd(doc="clear status"),
        "*ESE": IntCmd(doc="standard event status enable register"),
        "*ESR": IntCmdRO(doc="standard event event status register"),
        "*IDN": IDNCmd(),
        "*OPC": IntCmdRO(set=None, doc="operation complete"),
        "*OPT": IntCmdRO(doc="return model number of any installed options"),
        "*RCL": IntCmdWO(set=int, doc="return to user saved setup"),
        "*RST": FuncCmd(doc="reset"),
        "*SAV": IntCmdWO(doc="save the preset setup as the user-saved setup"),
        "*SRE": IntCmdWO(doc="service request enable register"),
        "*STB": StrCmdRO(doc="status byte register"),
        "*TRG": FuncCmd(doc="bus trigger"),
        "*TST": Cmd(get=lambda x: not decode_OnOff(x), doc="self-test query"),
        "*WAI": FuncCmd(doc="wait to continue"),
        "SYSTem:ERRor[:NEXT]": ErrCmd(doc="return and clear oldest system error"),
    }
)


class SCPIError(CommunicationError):
    """
    Base :term:`SCPI` error
    """


def sanitize_msgs(*msgs, **opts):
    """
    Transform a tuple of messages into a list  of
    (<individual commands>, <individual queries>, <full_message>):

    if strict_query=True, sep=';', eol='\n' (default):
        msgs = ('*rst', '*idn?;*cls') =>
            (['*RST', '*IDN?', '*CLS'], ['*IDN?'], '*RST\n*IDN?\n*CLS')

    if strict_query=False, sep=';', eol='\n' (default):
        msgs = ('*rst', '*idn?;*cls') =>
            (['*RST', '*IDN?', '*CLS'], ['*IDN?'], '*RST\n*IDN?;*CLS')
    """
    eol = opts.get("eol", "\n")
    # eol has to be a string
    if isinstance(eol, bytes):
        eol = eol.decode()
    sep = opts.get("sep", ";")
    strict_query = opts.get("strict_query", True)
    # in case a single message comes with several eol separated commands
    msgs = eol.join(msgs).split(eol)
    result, commands, queries = [], [], []
    for msg in msgs:
        sub_result = []
        for cmd in msg.split(sep):
            cmd = cmd.strip()
            if not cmd:
                continue
            commands.append(cmd)
            is_query = "?" in cmd
            if is_query:
                queries.append(cmd)
            if is_query and strict_query:
                if sub_result:
                    result.append(sep.join(sub_result))
                    sub_result = []
                result.append(cmd)
            else:
                sub_result.append(cmd)
        if sub_result:
            result.append(sep.join(sub_result))
    return commands, queries, eol.join(result) + eol


class SCPI(LogMixin):
    """
    :term:`SCPI` language helper.

    Although it can be used directly, the main idea is
    that it is used by an :term:`SCPI` capable instrument. Example::

        from bliss.comm import scpi

        class Keithley6482(object):

            def __init__(self, interface):
                cmds = scpi.Commands(COMMANDS)
                cmds['OUTP1'] = OnOffCmd()
                cmds['OUTP2'] = OnOffCmd()
                self.language = scpi.SCPI(interface=interface, commands=cmds)

    Direct usage example::

        from bliss.comm.scpi import SCPI

        scpi = SCPI(gpib=dict(url="enet://gpibhost", pad=10))

        # functional API
        print scpi('*IDN?')

        # dict like API ( [cmd] == (cmd+"?") )
        print scpi['*IDN']
    """

    def __init__(self, interface=None, commands=COMMANDS, **kwargs):
        self.interface = interface
        session.get_current().map.register(
            self, parents_list=["comms"], children_list=[self.interface], tag=str(self)
        )
        self._strict_query = kwargs.get("strict_query", True)
        self._contexts = []
        self._eol = interface._eol
        self.commands = Commands(commands)

    def enter_context(self):
        context = dict(commands=[], result=None)
        self._contexts.append(context)
        return context

    __enter__ = enter_context

    def exit_context(self, etype, evalue, etraceback):
        context = self._contexts.pop()
        commands = context["commands"]
        if commands and etype is None:
            context["result"] = self(*commands, sep=";")

    __exit__ = exit_context

    def __getitem__(self, cmd):
        command = self.commands[cmd]
        if "get" not in command:
            raise SCPIError("command {0} is not gettable".format(cmd))
        result = self.command(cmd + "?")
        if result:
            return result[0][1]

    def __setitem__(self, cmd, value):
        cmd = self.__to_write_command(cmd, value)
        return self.write(cmd)

    def __str__(self):
        return "{0}({1})".format(self.__class__.__name__, self.interface)

    def __call__(self, *cmds, **kwargs):
        """
        Executes command(s).

        Examples::

            # ask for instrument identification
            idn = instrument('*IDN?')

            # reset the instrument
            instrumment('*RST')

            # set ESE to 1 and ask for IDN and ESE
            idn, ese = instrument('*ESE 1', '*IDN?', '*ESE?')

        :param cmds: individual commands to send
        :type cmds: str
        :return: if any of the individual commands is a query return a sequence
                 of all results (even if only one query is done)
        :rtype: seq<obj> or None
        """
        return self.command(*cmds, **kwargs)

    def __to_write_command(self, cmd, value=None):
        """
        Transform <command> [<value>] into a string to be sent over the wire
        """
        command = self.commands[cmd]
        is_set = "set" in command
        if not is_set:
            raise SCPIError("command {0!r} is not settable".format(cmd))
        setter = command["set"]
        if setter is not None:
            cmd = "{0} {1}".format(cmd, setter(value))
        return cmd

    def __to_write_commands(self, *args, **kwargs):
        cmds, queries, msg = sanitize_msgs(*args, **kwargs)
        if queries:
            raise SCPIError("Cannot write a query")
        return msg

    def command(self, *cmds, **kwargs):
        """
        Execute a command.

        If at least one of the commands in the message is a query (any of the
        commands called with *?*), this call has the same effect as
        :py:meth:`read`. Otherwise it has the same effect as :py:meth:`write`.

         Examples::

            # ask for instrument identification
            idn = instrument.command('*IDN?')

            # reset the instrument
            instrumment.command('*RST')

            # set ESE to 1 and ask for IDN and ESE
            idn, ese = instrument.command('*ESE 1; *IDN?; *ESE?')

        .. note::
            a direct call to the scpi object has the same effect
            (ex: ``idn, ese = instrument('*ESE 1; *IDN?; *ESE?')``)

        .. seealso::
            :py:meth:`__call__`, :py:meth:`write`, :py:meth:`read`
        """
        is_read = any(["?" in cmd for cmd in cmds])
        if is_read:
            f = self.read
        else:
            f = self.write
        return f(*cmds, **kwargs)

    def read(self, *msgs, **kwargs):
        """
        Perfoms query(ies). If keyword argument *raw* is *True*, a single
        string is returned. Otherwise (default), the result is a sequence
        where each item is the query result processed according to the
        registered command data type.

        The method supports interleaving query commands with operations. The
        resulting sequence length corresponds to the number of queries in the
        message. Each result is a pair (query, return value)

        If inside a with statement, the command is buffered until the end of
        the context exit.

        Examples::

            >>> # ask for instrument identification
            >>> instrument.read('*IDN?')
            {'manufacturer': 'KEITHLEY INSTRUMENTS INC.',
             'model': '6485',
             'serial': '1008577',
             'version': 'B03   Sep 25 2002 10:53:29/A02  /E'}

            >>> # reset the instrument (would be more correct to use
            >>> # instrumment('*RST') directly)
            >>> instrumment.read('*RST')

            >>> # set ESE to 1 and ask for IDN and ESE
            >>> (_, idn), (_, ese) = instrument.read('*ESE 1; *IDN?; *ESE?')

        Args:
            *msgs (str): raw message to be queried (ex: "\*IDN?")
            **kwargs: supported kwargs: *raw* (default: False), *eol*,
                      *sep* (command separator)
        Returns:
            list: list of query results. Each result is a pair
                  (query, return value)

        Raises:
            SCPIError: in case an of unexpected result
            CommunicationError: in case of device not accessible
            CommunicationTimeout: in case device does not respond
        """
        if self._contexts:
            context = self._contexts[-1]["commands"].extend(msgs)
            return
        raw = kwargs.get("raw", False)
        eol = kwargs.setdefault("eol", self._eol)
        strict_query = kwargs.setdefault("strict_query", self._strict_query)
        cmds, queries, msg = sanitize_msgs(*msgs, **kwargs)
        self._logger.debug("[start] read %r", msg)
        raw_results = self.interface.write_readlines(msg.encode(), len(queries))
        raw_results = [r.decode() for r in raw_results]
        self._logger.debug("[ end ] read %r=%r", msg, raw_results)
        if raw:
            return raw_results
        if len(queries) != len(raw_results):
            msg = "expected {0} results (got {1}".format(queries, raw_results)
            raise SCPIError(msg)
        results = []
        for query, result in zip(queries, raw_results):
            query_cmd = query.split(" ", 1)[0].rstrip("?")
            command = self.commands.get(query_cmd)
            if command:
                getf = command.get("get", None)
                if getf:
                    try:
                        result = getf(result)
                    except:
                        self._logger.debug(
                            "Failed to convert result. Details:", exc_info=1
                        )
            results.append((query, result))
        return results

    def write(self, *msgs, **kwargs):
        """
        Execute non query command(s).

        If inside a with statement, the command is buffered until the end of
        the context exit.

        Examples::

            # set ESE to 1
            instrument.write("*ESE 1")

            # reset the instrument
            instrumment.write('*RST')

        Args:
            *msgs (str): raw command (ex: "\*CLS")

        Raises:
            CommunicationError: in case of device not accessible
            CommunicationTimeout: in case device does not respond

        """
        if self._contexts:
            context = self._contexts[-1]["commands"].extend(msgs)
            return
        msg = self.__to_write_commands(*msgs, **kwargs)
        self._logger.debug("[start] write %r", msg)
        self.interface.write(msg.encode())
        self._logger.debug("[ end ] write %r", msg)

    _MAX_ERR_STACK_SIZE = 20

    def get_errors(self):
        """
        Return error stack or None if no errors in instrument queue

        Returns:
            list: error stack or None if no errors in instrument queue
        """

        stack, fix_retries, err = [], 5, dict(code=0)
        # clear local stack
        while fix_retries:
            try:
                err = self.get_syst_err()
            except CommunicationTimeout:  # timeout: there's no comm: bail out
                raise
            except:
                fix_retries -= 1
                continue
            break
        while err["code"] != 0 and len(stack) < self._MAX_ERR_STACK_SIZE:
            stack.append(err)
            err = self.get_syst_err()
        return stack or None


class BaseSCPIDevice(LogMixin):
    """Base SCPI device class"""

    def __init__(self, *args, **kwargs):
        interface, args, kwargs = get_interface(*args, **kwargs)
        commands = kwargs.pop("commands", {})
        self.interface = interface
        self.language = SCPI(interface=interface, commands=commands)
        session.get_current().map.register(
            self, children_list=[self.language], tag=str(self)
        )

    def __str__(self):
        return "{0}({1})".format(type(self).__name__, self.language)

    def __call__(self, *args, **kwargs):
        return self.language(*args, **kwargs)

    __call__.__doc__ = SCPI.__call__.__doc__

    def __getattr__(self, name):
        return getattr(self.language, name)

    def __getitem__(self, name):
        return self.language[name]

    def __setitem__(self, name, value):
        self.language[name] = value

    def __enter__(self):
        return self.language.enter_context()

    def __exit__(self, etype, evalue, etraceback):
        return self.language.exit_context(etype, evalue, etraceback)
