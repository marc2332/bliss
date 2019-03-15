# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

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
import io
import functools
import itertools
import traceback
import pickle
import base64

import gevent
import gevent.event

from tango import DevState, Util, Database, DbDevInfo
from tango.server import Device, attribute, command, device_property

from bliss import shell
from bliss.common import event
from bliss.common.utils import grouped
from bliss.config import settings
from bliss.config.static import get_config
from bliss.common.motor_group import Group

from . import utils


_log = logging.getLogger("bliss.tango")


def get_bliss_obj(name):
    return get_config().get(name)


def excepthook(etype, value, tb, show_tb=False):
    """Custom excepthook"""
    # The most important for the user is the error (not the traceback)
    # This except hook emphasises the error

    if etype == KeyboardInterrupt:
        return

    lines = traceback.format_exception_only(etype, value)
    for line in lines:
        print(line, end="", file=sys.stderr)
    if tb and show_tb:
        msg = "\n-- Traceback (most recent call last) -----------------"
        print(msg, file=sys.stderr)
        traceback.print_tb(tb)
        print(len(msg) * "-", file=sys.stderr)

    _log.exception("Unhandled exception occurred:")


excepthook_tb = functools.partial(excepthook, show_tb=True)


def sanatize_command(cmd):
    """
    sanatize command line (adds parenthesis if missing)
    (not very robust!!!)
    """
    if "(" in cmd or "=" in cmd:  # good python format
        return cmd

    cmd = cmd.split()
    return "{0}({1})".format(cmd[0], ", ".join(cmd[1:]))


class OutputChannel(io.StringIO):
    """channel to handle stdout/stderr across tango"""

    def consume(self):
        """consume buffer data"""
        self.seek(0)
        data = self.read()
        self.truncate(0)
        return data


class InputChannel(object):
    """channel to handle stdin across tango"""

    def __init__(self):
        self.__event = gevent.event.Event()
        self.__need_input = False
        self.__msg = None

    @property
    def need_input(self):
        """determine if the code is waiting for input"""
        return self.__need_input

    def readline(self):
        """readline from input"""
        self.__need_input = not self.__event.is_set()
        self.__event.wait()
        self.__event.clear()
        data = self.__msg
        self.__msg = None
        return data

    def write(self, msg):
        """write message to input"""
        self.__msg = msg
        self.__need_input = False
        self.__event.set()

    def isatty(self):
        """this is not a tty"""
        return False


_SHELL_INFO = None


def load_shell(session_name):
    result = shell.initialize(session_name)
    global _SHELL_INFO
    _SHELL_INFO = result
    return result


class Bliss(Device):
    """Bliss TANGO device class"""

    #: Session name (default: None, meaning use server instance name as
    #: session name)
    session_name = device_property(dtype=str, default_value=None)

    #: Sanitize or not the command to be executed
    #: If True, it will allow you to send a command like: 'wm th phi'
    #: If False, it will only accepts commands with python syntax: 'wm(th, phi)'
    #: Sanitize is not perfect! You simply cannot transform one language into
    #: another. Avoid the temptation of using it just to try to please the user
    #: with a 'spec' like syntax as much as possible
    sanatize_command = device_property(dtype=bool, default_value=False)

    def __init__(self, *args, **kwargs):
        self._log = logging.getLogger("bliss.tango.Bliss")
        self.__startup = True
        super(Bliss, self).__init__(*args, **kwargs)
        self.show_traceback = False

    def init_device(self):
        super(Bliss, self).init_device()
        self.set_state(DevState.INIT)
        self._log.info("Initializing device...")
        self.__tasks = {}
        self.__results = {}

        if not self.session_name:
            util = Util.instance()
            self.session_name = util.get_ds_inst_name()

        #self.__scan_listener = shell.ScanListener()
        if self.__startup:
            shell_info = _SHELL_INFO
        else:
            shell_info = shell.initialize(self.session_name)
        self.__user_ns, self.__session = shell_info
        self.__startup = False

        # redirect output
        self.__output_channel = OutputChannel()
        self.__error_channel = OutputChannel()
        self.__input_channel = InputChannel()
        sys.stdout = self.__output_channel
        sys.stderr = self.__error_channel
        sys.stdin = self.__input_channel

        # motion
        self.group_dict = {}

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
    def _object_names(self):
        return self.__session.object_names or []

    @attribute(dtype=[str])
    def session(self):
        return self.session_name

    @attribute(dtype=(str,), max_dim_x=10000)
    def object_names(self):
        return self._object_names

    @attribute(dtype=(str,), max_dim_x=10000)
    def axis_device_names(self):
        return [dev.get_name() for dev in self.__get_axis_devices().values()]

    @attribute(dtype=(str,), max_dim_x=10000)
    def tasks(self):
        return ["{0} {1}".format(tid, cmd) for tid, (_, cmd) in self.__tasks.items()]

    @attribute(dtype=(str,), max_dim_x=10000)
    def namespace(self):
        return list(self.__user_ns.keys())

    @attribute(dtype=(str,), max_dim_x=10000)
    def functions(self):
        return sorted(
            [
                name
                for name, obj in self.__user_ns.items()
                if not name.startswith("_") and callable(obj)
            ]
        )

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
        return ""

    @input_channel.setter
    def input_channel(self, inp):
        self.__input_channel.write(inp)

    @attribute(dtype=bool)
    def need_input(self):
        return self.__input_channel.need_input

    def __on_cmd_finished(self, task):
        del self.__tasks[id(task)]

    def __on_eval_finished(self, task):
        self.__on_cmd_finished(task)

        res = task.get()
        if res is not None:
            self.__results[id(task)] = base64.encodestring(
                pickle.dumps(res, protocol=-1)
            )

    def __evaluate(self, cmd):
        try:
            exec("_=" + cmd, self.__user_ns)
        except gevent.GreenletExit:
            raise (sys.exc_info())
        except Exception as e:
            sys.excepthook(*sys.exc_info())
            return e
        else:
            return self.__user_ns.get("_")

    def __execute(self, cmd):
        if self.sanatize_command:
            cmd = sanatize_command(cmd)
        try:
            exec(cmd, self.__user_ns)
        except gevent.GreenletExit:
            raise (sys.exc_info())
        except Exception as e:
            sys.excepthook(*sys.exc_info())

    def __reload(self):
        get_config().reload()

    def __get_axis_devices(self):
        util = Util.instance()
        result = dict()
        for dev in util.get_device_list("*"):
            dev_class = dev.get_device_class()
            if dev_class:
                class_name = dev_class.get_name()
                if class_name.startswith("BlissAxis_"):
                    axis = dev.axis
                    result[axis.name] = dev
        return result

    @command(dtype_in=str, dtype_out=int)
    def eval(self, cmd):
        self._log.info("evaluating: %s", cmd)
        task = gevent.spawn(self.__evaluate, cmd)
        task_id = id(task)
        self.__tasks[task_id] = task, cmd
        task.link(self.__on_eval_finished)
        return task_id

    @command(dtype_in=str, dtype_out=int)
    def execute(self, cmd):
        self._log.info("executing: %s", cmd)
        task = gevent.spawn(self.__execute, cmd)
        task_id = id(task)
        self.__tasks[task_id] = task, cmd
        task.link(self.__on_cmd_finished)
        return task_id

    @command(dtype_in=int, dtype_out=bool)
    def is_finished(self, cmd_id):
        return cmd_id not in self.__tasks

    @command(dtype_in=int, dtype_out=str)
    def get_result(self, cmd_id):
        res = self.__results.pop(cmd_id, "")
        return res

    @command(dtype_in=int, dtype_out=bool)
    def is_running(self, cmd_id):
        return cmd_id in self.__tasks

    @command(dtype_in=int, dtype_out=bool)
    def stop(self, cmd_id):
        try:
            task, cmd_line = self.__tasks[cmd_id]
            self._log.info("stopping: %s", cmd_line)
        except KeyError:
            return False
        task.kill(KeyboardInterrupt)
        return True

    @command(
        dtype_in=(str,),
        doc_in="Flat list of pairs motor, position",
        dtype_out=str,
        doc_out="Group identifier",
    )
    def axis_group_move(self, axes_pos):
        axes = map(get_bliss_obj, axes_pos[::2])
        axes_positions = map(float, axes_pos[1::2])
        axes_pos_dict = dict(zip(axes, axes_positions))
        group = Group(*axes)
        event.connect(group, "move_done", self.__on_axis_group_move_done)
        group.move(axes_pos_dict, wait=False)
        group_id = ",".join(map(":".join, grouped(axes_pos, 2)))
        self.group_dict[group_id] = group
        return group_id

    def __on_axis_group_move_done(self, move_done, **kwargs):
        if not move_done:
            return
        elif not self.group_dict:
            self._log.warning("move_done event with no group")
            return

        if "sender" in kwargs:
            sender = kwargs["sender"]
            group_id = [
                gid
                for gid, grp in self.group_dict.items()
                if grp.get_base_obj() == sender
            ][0]
        elif len(self.group_dict) == 1:
            group_id = list(self.group_dict.keys())[0]
        else:
            self._log.warning("cannot not identify group move_done")
            return

        self.group_dict.pop(group_id)

    @command(
        dtype_in=str,
        doc_in="Group identifier",
        dtype_out=[str],
        doc_out='"flat list of pairs motor, status',
    )
    def axis_group_state(self, group_id):
        """
        Return the individual state of motors in the group
        """
        if group_id not in self.group_dict:
            return []
        group = self.group_dict[group_id]

        def get_name_state_list(group):
            return [(name, str(axis.state)) for name, axis in group.axes.items()]

        name_state_list = get_name_state_list(group)
        return list(itertools.chain(*name_state_list))

    @command(dtype_in=str, doc_in="Group identifier")
    def axis_group_abort(self, group_id):
        """
        Abort motor group movement
        """
        if group_id not in self.group_dict:
            return
        group = self.group_dict[group_id]
        group.stop(wait=False)

    @command(
        dtype_in=str,
        doc_in="JSON representation of a map: <setting_name, setting_value>",
    )
    def set_settings(self, json_value):
        data = json.loads(json_value)
        for key, value in data.items():
            setting = settings.HashSetting(key)
            setting.set(value)

    @command(
        dtype_in=str,
        doc_in="JSON representation of list<setting_name>",
        dtype_out=str,
        doc_out="",
    )
    def get_settings(self, json_value):
        data = json.loads(json_value)
        result = {}
        if isinstance(data, dict):
            data = data.values()
        elif isinstance(data, str):
            data = (data,)
        for element in data:
            if element:
                setting = settings.HashSetting(element)
                result[element] = setting.get_all()
        return json.dumps(result)

    @command
    def reload_config(self):
        self.__reload()

    @command(
        dtype_in=bool,
        doc_in="reload (true to do a reload before "
        "apply configuration, false not to)",
    )
    def apply_config(self, reload):
        if reload:
            self._reload()
        for dev in self.__get_axis_devices().values():
            dev.axis.apply_config(reload=False)


def register_server(
    server_type,
    server_instance,
    domain=None,
    family="bliss",
    member=None,
    klass=None,
    db=None,
):
    try:
        __register_server(
            server_type,
            server_instance,
            domain=domain,
            family=family,
            member=member,
            klass=klass,
            db=db,
        )
    except KeyboardInterrupt:
        print_("\n\nCtrl-C pressed. Exiting...")
        sys.exit(0)


def __register_server(
    server_type,
    server_instance,
    domain=None,
    family="bliss",
    member=None,
    klass=None,
    db=None,
):
    beamline = os.environ.get("BEAMLINENAME", "bliss")
    server_name = "{0}/{1}".format(server_type, server_instance)
    domain = domain or beamline
    member = member or server_instance
    klass = klass or server_type
    db = db or Database()
    dev_name = "{0}/{1}/{2}".format(domain, family, member)

    config_dir = "~/local/beamline_control"
    config_file = os.path.join(config_dir, "{0}.yml".format(beamline))

    # try to find which configuration file to use.
    # if we are not able we ask the user.
    print_("'{0}' is not configured yet.".format(server_instance))
    if not os.path.exists(os.path.expanduser(config_file)):
        config_file = ""
    config_file = input("config. file [{0}]? ".format(config_file)) or config_file
    config_file = os.path.expanduser(config_file)
    if not config_file:
        print_("No configuration file was given. Exiting...")
        sys.exit(-1)
    if not os.path.exists(os.path.expanduser(config_file)):
        print_("Could not find configuration file. Exiting...")
        sys.exit(-2)

    properties = dict(config_file=config_file)

    # ask the user for the session name
    session_name = server_instance
    session_name = input("session name {0}? ".format(session_name)) or session_name
    if session_name != server_instance:
        properties["session_name"] = session_name

    _log.info(
        "registering new server: %s with %s device %s", server_name, klass, dev_name
    )
    info = DbDevInfo()
    info.server = server_name
    info._class = klass
    info.name = dev_name

    db.add_device(info)
    db.put_device_property(dev_name, dict(config_file=config_file))


def __import(package):
    __import__(package)
    return sys.modules[package]


def __initialize(args, db=None):
    args = args or sys.argv
    db = db or Database()

    klasses = [Bliss]

    # initialize logging
    fmt = "%(levelname)-8s %(asctime)s %(name)s: %(message)s"
    logging.basicConfig(level=logging.INFO, format=fmt)

    server_type, server_instance, server_name = utils.get_server_info(args)
    registered_servers = set(db.get_instance_name_list(server_type))

    # check if server exists in database. If not, create it.
    if server_instance not in registered_servers:
        register_server(server_type, server_instance, db=db)

    device_map = utils.get_devices_from_server(args)

    # if in a jive wizard workflow, return no axis
    if not device_map.get("Bliss", ()):
        return klasses

    bliss_dev_name = device_map["Bliss"][0]

    props = db.get_device_property(bliss_dev_name, ("session_name",))
    session_name = props.get("session_name", [None])[0] or server_instance

    this_dir = os.path.dirname(os.path.abspath(__file__))
    suffix = "_ds.py"
    inits = []

    shell_info = ns, session = load_shell(session_name)

    object_names = session.object_names or []

    info = dict(
        server_type=server_type,
        server_instance=server_instance,
        session_name=session_name,
        device_map=device_map,
        manager_device_name=bliss_dev_name,
        object_names=object_names,
        shell_info=shell_info,
    )

    for name in os.listdir(this_dir):
        if name.startswith("."):
            continue
        if name.endswith(suffix):
            module_name = "{0}.{1}".format(__package__, name[:-3])
            _log.info("searching for init in %s...", module_name)
            try:
                module = __import(module_name)
            except ImportError as ie:
                _log.warning(
                    "failed to search for init in %s: %s", module_name, str(ie)
                )
            else:
                if hasattr(module, "initialize_bliss") and callable(
                    module.initialize_bliss
                ):
                    _log.info("found init in %s", module_name)
                    try:
                        mod_klasses = module.initialize_bliss(info, db=db)
                        klasses.extend(mod_klasses)
                    except Exception as e:
                        _log.warning("failed to initialize %s: %s", module_name, str(e))
                        _log.debug("details:", exc_info=1)
    return klasses


def main(args=None, **kwargs):
    from tango import GreenMode
    from tango.server import run

    kwargs["green_mode"] = GreenMode.Gevent

    args = list(sys.argv if args is None else args)
    args[0] = "Bliss"

    if len(args) == 1:
        args.append("-?")

    if "-?" in args:
        klasses = (Bliss,)
    else:
        klasses = __initialize(args=args)

    return run(klasses, args=args, **kwargs)


if __name__ == "__main__":
    main()
