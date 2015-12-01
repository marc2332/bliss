"""
SCPI helper class. Defines the language above the interface (TCP, GPIB, Serial)

Example:

    from bliss.comm.scpi import Scpi

    scpi = Scpi(gpib={'url': 'enet://example.com', 'pad': 15})

    # another way is to create the interface before and assign it to Scpi:

    from bliss.comm.gpib import Gpib
    interface = Gpib(url="enet://example.com", pad=15)
    scpi = Scpi(interface)

    print( scpi('*IDN?') )
    print( scpi['*IDN'] )
    print( scpi.get_idn() )
"""

import inspect
import logging
import functools

import numpy

from .util import get_interface

from .scpi_mapping import commands

class ScpiException(Exception):
    pass

def _sanatize_msgs(*msgs):
    result = []
    for msg in msgs:
        msg = msg.replace('\n', ';')
        for c in msg.split(";"):
            c = c.upper().strip()
            if not c: continue
            if not c.startswith(":"):
                c = ":" + c
            result.append(c)
    return ";".join(result)

class Scpi(object):
    """
    SCPI language. Although it can be used directly, the main idea is that it
    ia used by an SCPI capable instrument. Example::

        from bliss.comm import scpi

        class Keithley6482(object):

            def __init__(self, interface):
                cmds = dict(scpi.commands)
                cmds['OUTP1'] = OnOffCmd()
                cmds['OUTP2'] = OnOffCmd()
                self.language = scpi.Scpi(interface=interface, commands=cmds)

    Direct usage example::

        from bliss.comm.scpi import Scpi

        scpi = Scpi(gpib=dict(url="enet://gpibhost", pad=10))
        print scpi("*IDN?")
    """

    def __init__(self, *args, **kwargs):
        interface, args, kwargs = get_interface(*args, **kwargs)
        self.interface = interface
        self._logger = logging.getLogger(str(self))
        self._debug = self._logger.debug
        cmds = kwargs.get('commands')
        if cmds is None:
            cmds = commands
            self.register_commands(cmds)

    def __getitem__(self, cmd):
        cmd = cmd.upper()
        command = self.commands[cmd]
        if not 'get' in command:
            raise ScpiException('command {0} is not gettable'.format(cmd))
        result = self.command(cmd + "?")
        if result:
            return result[0][1]

    def __setitem__(self, cmd, value):
        cmd = cmd.upper()
        command = self.commands[cmd]
        if not 'set' in command:
            raise ScpiException('command {0} is not settable'.format(cmd))
        setter = command['set']
        if setter is not None:
            cmd = "{0} {1}".format(cmd, setter(value))
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

    def register_commands(self, cmds):
        """
        API for the instrument. Instrument should register its commands.
        Any previously registered commands will be unset.

        :param cmds: commands to be registered
        :type cmds: dict<str:Cmd>
        """
        cmds = dict(cmds)
        for k, v in cmds.items():
            v['cmd_name'] = v.get('cmd_name', k)

        self.commands = {}
        for cmd_name, cmd in cmds.items():
            # first add members to class
            full_cmd_name, min_cmd_name, getter, setter = _safe_add_command(self, cmd_name, cmd)
            # store commads as upper case to make search possible
            self.commands[full_cmd_name.upper()] = cmd
            self.commands[min_cmd_name.upper()] = cmd

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
            idn, ese = instrument.command('*ESE 1; *IDN?;', *ESE?')

        .. note::
            a direct call to the scpi object has the same effect
            (ex: ``idn, ese = instrument('*ESE 1; *IDN?;', *ESE?')``)

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
        Perfoms query(ies). If raw is True a single string is returned.
        Otherwise the result is a sequence where each item is the query result
        processed according to the registered command data type.

        The method supports interleaving query commands with operations. The
        resulting sequence length corresponds to the number of queries in the
        message.

        Examples::

            # ask for instrument identification
            idn = instrument.read('*IDN?')

            # reset the instrument (would be more correct to use
            # instrumment('*RST') directly)
            instrumment.read('*RST')

            # set ESE to 1 and ask for IDN and ESE
            idn, ese = instrument.read('*ESE 1; *IDN?; *ESE?')

        :param msg: raw message to be queried. Example: "*IDN?"
        :type msg: str
        :return: the read result
        :rtype: str
        """
        raw = kwargs.get('raw', False)
        msg = _sanatize_msgs(*msgs)
        self._logger.debug("[start] read '%s'", msg)
        raw_result = self.interface.write_readline(msg)
        self._logger.debug("[ end ] read '%s'='%s'", msg, raw_result)
        if raw:
            return raw_result
        queries = [q[1:-1] for q in msg.split(";") if q.endswith("?")]
        raw_results = raw_result.split(";")
        if len(queries) != len(raw_results):
            msg = "expected {0} results (got {1}".format(queries, raw_results)
            raise ScpiException(msg)
        results = []
        for query, result in zip(queries, raw_results):
            command = self.commands.get(query)
            if command:
                getf = command.get('get', None)
                if getf:
                    try:
                        result = getf(result)
                    except:
                        self._debug('Failed to convert result. Details:',
                                    exc_info=1)
            results.append((query, result))
        return results

    def write(self, *msgs, **kwargs):
        """
        Execute non query command(s).

        Examples::
            # set ESE to 1
            instrument.write("*ESE 1")

            # reset the instrument
            instrumment.write('*RST')
        """
        if any(["?" in msg for msg in msgs]):
            raise ScpiException("Cannot write a query")
        msg = _sanatize_msgs(*msgs)
        self._logger.debug("[start] write '%s'", msg)
        raw_result = self.interface.write(msg)
        self._logger.debug("[ end ] write '%s'", msg)

    _MAX_ERR_STACK_SIZE = 20
    def get_errors(self):
        """
        Return error stack or None if no errors in instrument queue

        :return: error stack or None if no errors in instrument queue
        :rtype: seq<str>
        """

        stack, fix_retries, err = [], 5, dict(code=0)
        # clear local stack
        while fix_retries:
            try:
                err = self.get_syst_err()
            except RuntimeError: # timeout: there's no comm: bail out
                raise
            except:
                fix_retries -= 1
                continue
            break
        while err['code'] != 0 and len(stack) < self._MAX_ERR_STACK_SIZE:
            stack.append(err)
            err = self.get_syst_err()
        return stack or None

def __to_cmd_name(cmd_name):
    res, res_min, optional_zone = '', '', False
    for c in cmd_name:
        if c == ']':
            optional_zone = False
            continue
        if c.islower() or optional_zone:
            res += c
            continue
        if c == '[':
            optional_zone = True
            continue
        res += c
        res_min += c
    return res, res_min

def __to_func_name(cmd_name):
    return cmd_name.replace('*', '').replace(':', '_').lower()

def __safe_add_method(klass, method, name=None):
    name = name and name or method.__name__
    if not hasattr(klass, name):
        setattr(klass, name, method)

def _safe_add_command(element, cmd_name, cmd):
    is_class = inspect.isclass(element)
    if is_class:
        klass = element
    else:
        device = element
        klass = element.__class__
    class_name = klass.__name__
    has_getter, has_setter = 'get' in cmd, 'set' in cmd
    has_func_name = 'func_name' in cmd
    getter, setter, doc = cmd.get('get'), cmd.get('set'), cmd.get('doc', '')

    full_cmd_name, min_cmd_name = __to_cmd_name(cmd_name)

    if has_func_name and not all((has_getter, has_setter)):
        full_func_name = min_func_name = cmd['func_name']
        get_name, set_name = full_func_name, full_func_name
        get_min_name, set_min_name = full_func_name, full_func_name
    else:
        full_func_name = __to_func_name(full_cmd_name)
        min_func_name = __to_func_name(min_cmd_name)
        if has_setter and setter is None and not has_getter:
            # pure command: method name without "set_" prefix
            get_name, set_name = None,  full_func_name
            get_min_name, set_min_name = None, min_func_name
        else:
            get_name, set_name = "get_" + full_func_name, "set_" + full_func_name
            get_min_name, set_min_name = "get_" + min_func_name, "set_" + min_func_name

    get_cmd, set_cmd = None, None

    if has_getter:
        if is_class:
            def get_cmd(device):
                return device[full_cmd_name]
        else:
            def get_cmd():
                return device[full_cmd_name]
        get_cmd.__name__ = get_name
        get_cmd.__doc__ = doc
        __safe_add_method(element, get_cmd, name=get_name)
        __safe_add_method(element, get_cmd, name=get_min_name)

    if has_setter:
        if setter is None:
            if is_class:
                def set_cmd(device):
                    device.write(full_cmd_name)
            else:
                def set_cmd():
                    device.write(full_cmd_name)
        else:
            if is_class:
                def set_cmd(device, value):
                    device[full_cmd_name] = value
            else:
                def set_cmd(value):
                    device[full_cmd_name] = value
        set_cmd.__name__ = set_name
        set_cmd.__doc__ = doc
        __safe_add_method(element, set_cmd, name=set_name)
        __safe_add_method(element, set_cmd, name=set_min_name)
    return full_cmd_name, min_cmd_name, get_cmd, set_cmd

def scpify_init_cmds(device, cmds=None, model_cmds=None, patch_cmds=True):
    all_cmds = {}
    if cmds is not None:
        all_cmds.update(cmds)

    if model_cmds is not None and model_cmds:
        try:
            idn = device._language('*IDN?')[0][1]
        except:
            device._logger.warning('failed to initialize commands (comm error)')
            device._logger.debug('Details:', exc_info=1)
        else:
            model = idn['model']
            all_cmds.update(dict(model_cmds.get(model, {})))
    device._commands = all_cmds
    device._language.register_commands(all_cmds)

    if patch_cmds:
        for cmd_name, cmd in all_cmds.items():
            _, _, getter, setter = _safe_add_command(device, cmd_name, cmd)
            if getter:
                device._dir.add(getter.__name__)
            if setter:
                device._dir.add(setter.__name__)

def scpify(klass=None, cmds=None, model_cmds=None, patch_cmds=True):
    """
    To be used as a decorator to enable SCPI capabilities on an instrument.

    This decorator overwrites the constructor(__init__) with one constructor
    expecting an *interface* argument or an 'interface' keyword argument,
    consuming it. Tthe remaining arguments and keyword arguments are passed to
    the original class __init__ method.

    When not implemented by the class, this decorator adds __getitem__,
    __setitem__, __getattr__, __dir__ methods and language and commands
    python properties.

    Example::

        import collections

        from bliss.comm.scpi import Scpi, scpify, commands, Cmd, OnOffCmd
        K_CMDS = dict(commands)
        K_CMDS.update({
            "REN": Cmd(doc="goes into remote when next addressed to listen"),
            "IFC": Cmd(doc="reset interface; all devices go into talker and listener idle states"),
        })

        K_MODEL_CMDS = collections.defaultdict(dict)
        K_MODEL_CMDS.update({
            "6482": {
                "OUTP1": OnOffCmd(),
                "OUTP2": OnOffCmd(),
            },
            "6485": {
            }
        })

        @scpify(cmds=K_CMDS, model_cmds=K_MODEL_CMDS)
        class KeithleyScpi(object):
            pass
    """

    if klass is None:
        return functools.partial(scpify, cmds=cmds, model_cmds=model_cmds,
                                 patch_cmds=patch_cmds)

    if cmds is None:
        cmds = {}
    if model_cmds is None:
        model_cmds = {}

    def init(device, *args, **kwargs):
        interface, args, kwargs = get_interface(*args, **kwargs)
        device._interface = interface
        device._language = Scpi(interface=interface)
        device._dir = set(dir(device.__class__))
        device._dir.update(set(dir(device._language)))
        device.__init_orig__(*args, **kwargs)

    klass.__init_orig__ = klass.__init__
    klass.__init__ = init

    if not hasattr(klass, "_init_cmds"):
        def _init_cmds(device):
            return scpify_init_cmds(device, cmds=cmds, model_cmds=model_cmds,
                                    patch_cmds=patch_cmds)
        klass._init_cmds = _init_cmds

    if not callable("__call__"):
        def __call__(device, *args, **kwargs):
            return device.language(*args, **kwargs)
        __call__.__doc__ = Scpi.__call__.__doc__
        klass.__call__ = __call__

    def __getattr__(device, name):
        return getattr(device._language, name)
    __safe_add_method(klass, __getattr__)

    def __getitem__(device, name):
        return device.language[name]
    __safe_add_method(klass, __getitem__)

    def __setitem__(device, name, value):
        device.language[name] = value
    __safe_add_method(klass, __setitem__)

    def __dir__(device):
        return list(device._dir)
    __safe_add_method(klass, __dir__)

    def language(device):
        if not hasattr(device, '_commands'):
            device._init_cmds()
        return device._language
    __safe_add_method(klass, property(language), name='language')

    def _commands(device):
        return device.language.commands
    __safe_add_method(klass, property(_commands), name='commands')

    if patch_cmds:
        for cmd_name, cmd in cmds.items():
            _safe_add_command(klass, cmd_name, cmd)

    return klass

def main(argv=None):
    """
    Start a SCPI console

    The following example will start a SCPI console with one SCPI instrument
    called *s*::

        $ python -m Salsa.core.communications.scpi gpib --pad=15 enet://gpibhost

        scpi> print s['*IDN']
    """

    import sys
    import argparse

    try:
        import serial
    except:
        serial = None

    parser = argparse.ArgumentParser(description=main.__doc__)

    parser.add_argument('--log-level', type=str, default='info',
                        choices=['trace', 'debug', 'info', 'warning', 'error'],
                        help='global log level [default: info]')
    parser.add_argument('--scpi-log-level', type=str, default='info',
                        choices=['trace', 'debug', 'info', 'warning', 'error'],
                        help='log level for scpi object[default: info]')
    parser.add_argument('--gevent', action='store_true', default=False,
                        help='enable gevent in console [default: False]')

    subparsers = parser.add_subparsers(title="connection", dest="connection",
                                       description="valid type of connections",
                                       help="choose one type of connection")

    gpib_parser = subparsers.add_parser('gpib', help='GPIB connection')
    add = gpib_parser.add_argument
    add('url', type=str,
        help='gpib instrument url (ex: gpibhost, enet://gpibhost:5000)')
    add('--pad', type=int, required=True, help='primary address')
    add('--sad', type=int, default=0, help='secondary address [default: 0]')
    add('--tmo', type=int, default=10,
        help='gpib timeout (gpib tmo unit) [default: 10 (=300ms)]')
    add('--eos', type=str, default='\n', help=r"end of string [default: '\n']")
    add('--timeout', type=float, default=0.4,
        help='socket timeout [default: 0.4]')

    tcp_parser = subparsers.add_parser('tcp', help='TCP connection')
    add = tcp_parser.add_argument
    add('url', type=str,
        help='tcp instrument url (ex: host:5000, socket://host:5000)')
    add('--port', required=True, type=int, help='port')
    add('--timeout', type=float, default=5, help='timeout')
    add('--eol', type=str, default='\n',
        help=r"end of line [default: '\n']")

    if serial:
        serial_parser = subparsers.add_parser('serial',
                                              help='serial line connection')
        add = serial_parser.add_argument
        add('port', type=str,
            help='serial instrument port (ex: rfc2217://.., ser2net://..)')
        add('--baudrate', type=int, default=9600, help='baud rate')
        add('--bytesize', type=int, choices=[6, 7, 8],
            default=serial.EIGHTBITS, help='byte size')
        add('--parity', choices=serial.PARITY_NAMES.keys(),
            default=serial.PARITY_NONE, help='parity type')
        add('--timeout', type=float, default=5, help='timeout')
        add('--stopbits', type=float, choices=[1, 1.5, 2],
            default=serial.STOPBITS_ONE, help='stop bits')
        add('--xonxoff', action='store_true', default=False, help='')
        add('--rtscts', action='store_true', default=False, help='')
        add('--write-timeout', dest='writeTimeout', type=float, default=None,
            help='')
        add('--dsrdtr', action='store_true', default=False, help='')
        add('--interchar-timeout', dest='interCharTimeout', type=float,
            default=None, help='')
        add('--eol', type=str, default='\n',
            help="end of line [default: '\\n']")

    args = parser.parse_args()
    vargs = vars(args)

    log_level = vargs.pop('log_level').upper()
    scpi_log_level = vargs.pop('scpi_log_level').upper()
    logging.basicConfig(level=log_level,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    gevent_arg = vargs.pop('gevent')

    conn = vargs.pop('connection')
    kwargs = { conn: vargs }
    mode = not gevent_arg and "interactive, no gevent" or "gevent"
    scpi = Scpi(**kwargs)
    scpi._logger.setLevel(scpi_log_level)
    local = dict(s=scpi)
    banner = "\nWelcome to SCPI console " \
             "(connected to {0}) ({1})\n".format(scpi, mode)

    sys.ps1 = "scpi> "
    sys.ps2 = len(sys.ps1)*"."

    if gevent_arg:
        try:
            from gevent.monkey import patch_sys
        except ImportError:
            mode = "no gevent"
        else:
            patch_sys()

    import code
    code.interact(banner=banner, local=local)

if __name__ == "__main__":
  main()
