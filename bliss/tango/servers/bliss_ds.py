# -*- coding: utf-8 -*-

"""
Bliss TANGO device class

To configure it in Jive:
1. open Edit->Create server
2. Server (ServerName/Instance): 'Bliss/<session>'
   Class: Bliss
   Devices: <BL name>/bliss/<session name>
   click on *Register server*
3. Click on the 'properties' node of the bliss device you just created in
   jive tree
4. Add property: 'config_file'. Value is the absolute path of the session YML
                 configuration file
   Add property: 'session_name'. Value is the name of the session
                 (not mandatory. defaults to the server instance)
"""

import os
import sys
import json
import logging
import StringIO
import functools
import traceback

import six
import gevent
import gevent.event

from PyTango import DevState, Util
from PyTango.server import device_property
from PyTango.server import Device, DeviceMeta
from PyTango.server import attribute, command

from bliss.common import event
from bliss.common import data_manager
from bliss.common.scans import last_scan_data
from bliss.shell import initialize


_log = logging.getLogger('bliss.tango')


print_ = six.print_


def print_err_(*args, **kwargs):
    '''print error message'''
    kwargs['file'] = sys.stderr
    print_(*args, **kwargs)


def excepthook(etype, value, tb, show_tb=False):
    '''Custom excepthook'''
    # The most important for the user is the error (not the traceback)
    # This except hook emphasises the error

    if etype == KeyboardInterrupt:
        return

    lines = traceback.format_exception_only(etype, value)
    for line in lines:
        print_err_(line, end='')
    if tb and show_tb:
        msg = '\n-- Traceback (most recent call last) -----------------'
        print_err_(msg)
        traceback.print_tb(tb)
        print_err_(len(msg)*'-')

    _log.exception('Unhandled exception occurred:')

excepthook_tb = functools.partial(excepthook, show_tb=True)


def sanatize_command(cmd):
    '''
    sanatize command line (adds parenthesis if missing)
    (not very robust!!!)
    '''
    if '(' in cmd or '=' in cmd: # good python format
        return cmd

    cmd = cmd.split()
    return '{0}({1})'.format(cmd[0], ", ".join(cmd[1:]))


class OutputChannel(StringIO.StringIO):
    '''channel to handle stdout/stderr across tango'''

    def consume(self):
        '''consume buffer data'''
        self.seek(0)
        data = self.read()
        self.truncate(0)
        return data


class InputChannel(object):
    '''channel to handle stdin across tango'''
    def __init__(self):
        self.__event = gevent.event.Event()
        self.__need_input = False
        self.__msg = None

    @property
    def need_input(self):
        '''determine if the code is waiting for input'''
        return self.__need_input

    def readline(self):
        '''readline from input'''
        self.__need_input = not self.__event.is_set()
        self.__event.wait()
        self.__event.clear()
        data = self.__msg
        self.__msg = None
        return data

    def write(self, msg):
        '''write message to input'''
        self.__msg = msg
        self.__need_input = False
        self.__event.set()

    def isatty(self):
        '''this is not a tty'''
        return False


class ScanListener:
    '''listen to scan events and compose output'''

    HEADER = "Total {0.npoints} points, {0.total_acq_time} seconds\n\n" + \
             "Scan {0.scan_nb} {0.start_time_str} {0.filename} " + \
             "{0.session_name} user = {0.user_name}\n" + \
             "{0.title}\n\n" + \
             "{column_header}"

    def __init__(self, datamanager=None):
        dm = datamanager or data_manager.DataManager()
        event.connect(dm, 'scan_new', self.__on_scan_new)
        event.connect(dm, 'scan_data', self.__on_scan_data)
        event.connect(dm, 'scan_end', self.__on_scan_end)

    def __on_scan_new(self, scan, filename, motor_names, nb_points, counter_names):
        if scan.type == 'ct':
            return
        if isinstance(motor_names, str):
            motor_names = [motor_names]
        col_names = motor_names + counter_names
        point_nb_col_len = len(str(nb_points-1)) + 1 if nb_points else 6
        col_lens = map(len, col_names)
        col_templs = ["{{0:>{0}}}".format(min(col_len, 8)) for col_len in col_lens]
        col_names.insert(0, '#')
        col_templs.insert(0, "{{0:>{0}}}".format(point_nb_col_len))
        col_header = "  ".join([col_templs[i].format(m) for i, m in enumerate(col_names)])
        header = self.HEADER.format(scan, column_header=col_header)
        self.col_templs = ["{{0:>{0}g}}".format(min(col_len, 8)) for col_len in col_lens]
        self.col_templs.insert(0, "{{0:>{0}g}}".format(point_nb_col_len))
        print_(header)

    def __on_scan_data(self, scan, values):
        if scan.type == 'ct':
            return
        point_nb = len(scan.raw_data) - 1
        values = [point_nb] + values
        line = "  ".join([self.col_templs[i].format(v) for i, v in enumerate(values)])
        print_(line)

    def __on_scan_end(self, scan):
        if scan.type == 'ct':
            # ct is actually a timescan(npoints=1).
            names, values = scan.counter_names, last_scan_data()[-1]
            # First value is elapsed time since timescan started. We don't need it here
            values = values[1:]
            norm_values = values / scan.count_time
            col_len = max(map(len, names)) + 2
            template = '{{0:>{0}}} = {{1: 10g}} ({{2: 10g}}/s)'.format(col_len)
            lines = "\n".join([template.format(name, v, nv)
                               for name, v, nv in zip(names, values, norm_values)])
            msg = '\n{0}\n\n{1}'.format(scan.end_time_str, lines)
            print_(msg)

@six.add_metaclass(DeviceMeta)
class Bliss(Device):
    """Bliss TANGO device class"""

    #: Config file name (mandatory)
    config_file = device_property(dtype=str)

    #: Session name (default: None, meaning use server instance name as
    #: session name)
    session_name = device_property(dtype=str, default_value=None)

    #: Sanatize or not the command to be executed
    #: If True, it will allow you to send a command like: 'wm th phi'
    #: If False, it will only accepts commands with python syntax: 'wm(th, phi)'
    #: Sanatize is not perfect! You simply cannot transform one language into
    #: another. Avoid the temptation of using it just to try to please the user
    #: with a 'spec' like syntax as much as possible
    sanatize_command = device_property(dtype=bool, default_value=False)

    def __init__(self, *args, **kwargs):
        self._log = logging.getLogger('bliss.tango.Bliss')
        Device.__init__(self, *args, **kwargs)
        self.show_traceback = False

    def init_device(self):
        Device.init_device(self)
        self.set_state(DevState.INIT)
        self._log.info('Initializing device...')
        self.__tasks = {}

        if self.config_file is None:
            self.set_state(DevState.FAULT)
            self.set_status('missing config_file property')
            return

        self.config_file = os.path.expanduser(self.config_file)
        if self.session_name is None:
            util = Util.instance()
            self.session_name = util.get_ds_inst_name()

        self.__scan_listener = ScanListener()
        self.__user_ns, _, (self.__setup, _) = initialize(self.config_file,
                                                          self.session_name)

        # redirect output
        self.__output_channel = OutputChannel()
        self.__error_channel = OutputChannel()
        self.__input_channel = InputChannel()
        sys.stdout = self.__output_channel
        sys.stderr = self.__error_channel
        sys.stdin = self.__input_channel

        self.set_state(DevState.STANDBY)

    def dev_state(self):
        if self.__tasks:
            return DevState.RUNNING
        return self.get_state()

    def dev_status(self):
        nb_tasks = len(self.__tasks)
        if nb_tasks:
            self.__status = "Running {0} commands".format(nb_tasks)
        else:
            self.__status = "Waiting for commands"
        return self.__status

    @property
    def _session(self):
        return self.__setup.get(self.session_name, {})

    @property
    def _setup_file(self):
        return self._session.get('file') or ''

    @property
    def _object_names(self):
        return self._session.get('config_objects')

    @attribute(dtype=str)
    def setup(self):
        return json.dumps(self.__setup)

    @attribute(dtype=str)
    def session(self):
        return json.dumps(self._session)

    @attribute(dtype=str)
    def setup_file(self):
        return self._setup_file

    @attribute(dtype=(str,), max_dim_x=10000)
    def object_names(self):
        return self._object_names

    @attribute(dtype=(str,), max_dim_x=10000)
    def tasks(self):
        return ['{0} {1}'.format(tid, cmd) for tid, (_, cmd) in self.__tasks.items()]

    @attribute(dtype=(str,), max_dim_x=10000)
    def namespace(self):
        return self.__user_ns.keys()

    @attribute(dtype=(str,), max_dim_x=10000)
    def functions(self):
        return sorted([name for name, obj in self.__user_ns.items()
                       if not name.startswith('_') and callable(obj)])

    @attribute(dtype=bool, memorized=True, hw_memorized=True)
    def show_traceback(self):
        return sys.excepthook == excepthook_tb

    @show_traceback.setter
    def show_traceback(self, yesno):
        sys.excepthook = excepthook_tb if yesno else excepthook
        self._log.info("'show traceback' set to %s", yesno)

    @attribute(dtype=str)
    def output_channel(self):
        return self.__output_channel.consume()

    @attribute(dtype=str)
    def error_channel(self):
        return self.__error_channel.consume()

    @attribute(dtype=str)
    def input_channel(self):
        return ''

    @input_channel.setter
    def input_channel(self, inp):
        self.__input_channel.write(inp)

    @attribute(dtype=bool)
    def need_input(self):
        return self.__input_channel.need_input

    def __on_cmd_finished(self, task):
        del self.__tasks[id(task)]

    def __execute(self, cmd):
        if self.sanatize_command:
            cmd = sanatize_command(cmd)
        try:
            six.exec_(cmd, self.__user_ns)
        except gevent.GreenletExit:
            six.reraise(*sys.exc_info())
        except:
            sys.excepthook(*sys.exc_info())

    @command(dtype_in=str, dtype_out=int)
    def execute(self, cmd):
        self._log.info('executing: %s', cmd)
        task = gevent.spawn(self.__execute, cmd)
        task_id = id(task)
        self.__tasks[task_id] = task, cmd
        task.link(self.__on_cmd_finished)
        return task_id

    @command(dtype_in=int, dtype_out=bool)
    def is_finished(self, cmd_id):
        return cmd_id not in self.__tasks

    @command(dtype_in=int, dtype_out=bool)
    def is_running(self, cmd_id):
        return cmd_id in self.__tasks

    @command(dtype_in=int, dtype_out=bool)
    def stop(self, cmd_id):
        try:
            task, cmd_line = self.__tasks[cmd_id]
            self._log.info('stopping: %s', cmd_line)
        except KeyError:
            return False
        task.kill(KeyboardInterrupt)
        return True


def main(args=None, **kwargs):
    from PyTango import GreenMode
    from PyTango.server import run
    kwargs['green_mode'] = GreenMode.Gevent
    fmt = '%(levelname)-8s %(asctime)s %(name)s: %(message)s'
    logging.basicConfig(level=logging.INFO, format=fmt)
    return run((Bliss,), args=args, **kwargs)


if __name__ == '__main__':
    main()
