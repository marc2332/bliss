"""
Keithley meters.


A demo is available from the command line:

$ python -m Salsa.controllers.keithley <url> <pad>

"""

import logging

from bliss.comm.scpi import scpify
from .keithley_mapping import commands, model_commands


@scpify(cmds=commands, model_cmds=model_commands)
class KeithleyScpi(object):
    __doc__ = """
    Keithley instrument through SCPI interface. Can be used with any Keithley
    SCPI capable device (custom commands implemented for models {0})

    Example usage::

        from bliss.comm.gpib import Gpib
        from Salsa.core.controllers.keithley import KeithleyScpi

        gpib = Gpib('enet://gpibhost', pad=10)
        keithley = KeithleyScpi(gpib)

        print( keithley('*IDN?') )
        print( keithley['*IDN'] )
        print( keithley.idn() )

    """.format(', '.join(model_commands.keys()))

    def __init__(self):
        self._logger = logging.getLogger(str(self))
        self._debug = self._logger.debug

    def __str__(device):
        return '{0}({1})'.format(device.__class__.__name__, device.language)


def main():
    """
    Start a Keithley console

    The following example will start a Keithley console with one Keithley
    instrument called *k*::

        $ python -m Salsa.controllers.keithley gpib --pad=15 enet://gpibhost

        keithley> print( k['*IDN?'] )

     """

    import sys
    import argparse
    
    try:
        import serial
    except:
        serial = None

    parser = argparse.ArgumentParser(description=main.__doc__)

    parser.add_argument('--log-level', type=str, default='info',
                        choices=['debug', 'info', 'warning', 'error'],
                        help='log level [default: info]')
    parser.add_argument('--scpi-log-level', type=str, default='info',
                        choices=['trace', 'debug', 'info', 'warning', 'error'],
                        help='log level for scpi object[default: info]')
    parser.add_argument('--keithley-log-level', type=str, default='info',
                        choices=['trace', 'debug', 'info', 'warning', 'error'],
                        help='log level for keithley object[default: info]')
    parser.add_argument('--gevent', action='store_true', default=False,
                        help='enable gevent in console [default: False]')

    subparsers = parser.add_subparsers(title='connection', dest='connection',
                                       description='valid type of connections',
                                       help='choose one type of connection')
    
    gpib_parser = subparsers.add_parser('gpib', help='GPIB connection')
    add = gpib_parser.add_argument
    add('url', type=str, 
        help='gpib instrument url (ex: gpibhost, enet://gpibhost:5000)')
    add('--pad', type=int, required=True, help='primary address')
    add('--sad', type=int, default=0, help='secondary address [default: 0]')
    add('--tmo', type=int, default=10,
        help='gpib timeout (gpib tmo unit) [default: 11 (=1s)]')
    add('--eos', type=str, default='\n', help=r"end of string [default: '\n']")
    add('--timeout', type=float, default=1.1, 
        help='socket timeout [default: 1.1]')

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
    
    log_level = getattr(logging, vargs.pop('log_level').upper())
    keithley_log_level = vargs.pop('keithley_log_level').upper()
    scpi_log_level = vargs.pop('scpi_log_level').upper()
    logging.basicConfig(level=log_level,
                        format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    gevent_arg = vargs.pop('gevent')

    conn = vargs.pop('connection')
    kwargs = { conn: vargs }
    mode = not gevent_arg and 'interactive, no gevent' or 'gevent'
    keithley = KeithleyScpi(**kwargs)
    keithley._logger.setLevel(keithley_log_level)
    keithley.language._logger.setLevel(scpi_log_level)
    local = dict(k=keithley)
    banner = '\nWelcome to Keithley console ' \
             '(connected to {0}) ({1})\n'.format(keithley, mode)

    sys.ps1 = 'keithley> '
    sys.ps2 = len(sys.ps1)*'.'

    if gevent_arg:
        try:
            from gevent.monkey import patch_sys
        except ImportError:
            mode = 'no gevent'
        else:
            patch_sys()

    import code
    code.interact(banner=banner, local=local)


if __name__ == "__main__":
    main()
