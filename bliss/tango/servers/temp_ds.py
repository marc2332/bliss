# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import absolute_import

import os
import sys
import types

import json

import tango
from tango.server import Device, attribute, command
from tango.server import get_worker

import bliss.common.log as elog
from bliss.common import temperature
from bliss.config.static import get_config

types_conv_tab_inv = {
    tango.DevVoid: "None",
    tango.DevDouble: "float",
    tango.DevString: "str",
    tango.DevLong: "int",
    tango.DevBoolean: "bool",
    tango.DevVarFloatArray: "float_array",
    tango.DevVarDoubleArray: "double_array",
    tango.DevVarLongArray: "long_array",
    tango.DevVarStringArray: "string_array",
    tango.DevVarBooleanArray: "bool_array",
}

types_conv_tab = dict((v, k) for k, v in types_conv_tab_inv.items())
types_conv_tab.update(
    {
        None: tango.DevVoid,
        str: tango.DevString,
        int: tango.DevLong,
        float: tango.DevDouble,
        bool: tango.DevBoolean,
    }
)

access_conv_tab = {
    "r": tango.AttrWriteType.READ,
    "w": tango.AttrWriteType.WRITE,
    "rw": tango.AttrWriteType.READ_WRITE,
}

access_conv_tab_inv = dict((v, k) for k, v in access_conv_tab.items())

_STATE_MAP = {
    "READY": tango.DevState.ON,
    "FAULT": tango.DevState.FAULT,
    "ALARM": tango.DevState.ALARM,
    "RUNNING": tango.DevState.RUNNING,
}


class BlissInput(Device):
    @property
    def channel_object(self):
        config = get_config()
        name = self.get_name().rsplit("/", 1)[-1]
        return config.get(name)

    @attribute(dtype="string")
    def name(self):
        return self.channel_object.name

    @attribute(dtype=float)
    def value(self):
        return self.channel_object.read()

    @attribute(dtype="string")
    def typedev(self):
        return "input"

    @command(dtype_out="DevVarStringArray")
    def GetCustomCommandList(self):
        """
        Returns the list of custom commands.
        JSON format.
        """
        _cmd_list = self.channel_object.custom_methods_list

        argout = list()

        for _cmd in _cmd_list:
            self.debug_stream("Custom command : %s" % _cmd[0])
            argout.append(json.dumps(_cmd))

        return argout

    @command(dtype_in="string")
    def Wraw(self, st):
        self.channel_object.controller.Wraw(st)

    @command(dtype_out="string")
    def Rraw(self):
        return self.channel_object.controller.Rraw()

    @command(dtype_in="string", dtype_out="string")
    def WRraw(self, st):
        return self.channel_object.controller.WRraw(st)

    @command(dtype_out=float)
    def read(self):
        return self.channel_object.read()

    def dev_state(self):
        state = self.channel_object.state()
        return _STATE_MAP[state]

    def dev_status(self):
        self.__status = "We are in {0} state".format(self.dev_state())
        return self.__status

    def init_device(self):
        Device.init_device(self)


class BlissOutput(Device):
    @property
    def channel_object(self):
        config = get_config()
        name = self.get_name().rsplit("/", 1)[-1]
        return config.get(name)

    @attribute(dtype="string")
    def name(self):
        return self.channel_object.name

    @attribute(dtype=float)
    def value(self):
        return self.channel_object.read()

    @attribute(dtype="string")
    def typedev(self):
        return "output"

    @attribute(dtype=float)
    def limit_low(self):
        return self.channel_object.limits[0]

    @attribute(dtype=float)
    def limit_high(self):
        return self.channel_object.limits[1]

    @attribute(dtype=float)
    def deadband(self):
        return self.channel_object.deadband

    @attribute(dtype=float)
    def ramprate(self):
        return self.channel_object.ramprate()

    @ramprate.write
    def ramprate(self, ramp):
        self.channel_object.ramprate(ramp)

    @attribute(dtype=float)
    def setpoint(self):
        return self.channel_object.ramp()

    @attribute(dtype=float)
    def dwell(self):
        return self.channel_object.dwell()

    @dwell.write
    def dwell(self, dw):
        self.channel_object.dwell(dw)

    @attribute(dtype=float)
    def step(self):
        return self.channel_object.step()

    @step.write
    def step(self, stp):
        self.channel_object.step(stp)

    @attribute(dtype=float)
    def pollramp(self):
        return self.channel_object.pollramp()

    @pollramp.write
    def pollramp(self, pr):
        self.channel_object.pollramp(pr)

    @attribute(dtype="DevState")
    def rampstate(self):
        return _STATE_MAP[self.channel_object.rampstate()]

    @command(dtype_out=float)
    def read(self):
        return self.channel_object.read()

    @command(dtype_in=float)
    def ramp(self, sp):
        self.channel_object.ramp(sp)

    @command(dtype_in=float)
    def set(self, sp):
        self.channel_object.set(sp)

    @command
    def stop(self):
        self.channel_object.stop()

    @command
    def abort(self):
        self.channel_object.abort()

    @command(dtype_in="string")
    def Wraw(self, st):
        self.channel_object.controller.Wraw(st)

    @command(dtype_out="string")
    def Rraw(self):
        return self.channel_object.controller.Rraw()

    @command(dtype_in="string", dtype_out="string")
    def WRraw(self, st):
        return self.channel_object.controller.WRraw(st)

    @command(dtype_out="DevVarStringArray")
    def GetCustomCommandList(self):
        """
        Returns the list of custom commands.
        JSON format.
        """
        _cmd_list = self.channel_object.custom_methods_list

        argout = list()

        for _cmd in _cmd_list:
            self.debug_stream("Custom command : %s" % _cmd[0])
            argout.append(json.dumps(_cmd))

        return argout

    def dev_state(self):
        return get_worker().execute(self._dev_state)

    def _dev_state(self):
        state = self.channel_object.state()
        return _STATE_MAP[state]

    def dev_status(self):
        self.__status = "We are in {0} state".format(self.dev_state())
        return self.__status

    def init_device(self):
        Device.init_device(self)


class BlissLoop(Device):
    @property
    def channel_object(self):
        config = get_config()
        name = self.get_name().rsplit("/", 1)[-1]
        return config.get(name)

    @attribute(dtype="string")
    def name(self):
        return self.channel_object.name

    @attribute(dtype="string")
    def typedev(self):
        return "loop"

    @attribute(dtype="string")
    def input_name(self):
        return self.channel_object.input.name

    @attribute(dtype="string")
    def input_device(self):
        return getdevicefromname("BlissInput", self.channel_object.input.name)

    @attribute(dtype="string")
    def output_name(self):
        return self.channel_object.output.name

    @attribute(dtype="string")
    def output_device(self):
        return getdevicefromname("BlissOutput", self.channel_object.output.name)

    @attribute(dtype=float)
    def kp(self):
        return self.channel_object.kp()

    @kp.write
    def kp(self, kkp):
        self.channel_object.kp(kkp)

    @attribute(dtype=float)
    def ki(self):
        return self.channel_object.ki()

    @ki.write
    def ki(self, kki):
        self.channel_object.ki(kki)

    @attribute(dtype=float)
    def kd(self):
        return self.channel_object.kd()

    @kd.write
    def kd(self, kkd):
        self.channel_object.kd(kkd)

    @command(dtype_out="DevVarStringArray")
    def GetCustomCommandList(self):
        """
        Returns the list of custom commands.
        JSON format.
        """
        _cmd_list = self.channel_object.custom_methods_list

        argout = list()

        for _cmd in _cmd_list:
            self.debug_stream("Custom command : %s" % _cmd[0])
            argout.append(json.dumps(_cmd))

        return argout

    @command
    def on(self):
        self.channel_object.on()

    @command
    def off(self):
        self.channel_object.off()

    @command(dtype_out=float)
    def read_input(self):
        return self.channel_object.input.read()

    def dev_state(self):
        return get_worker().execute(self._dev_state)

    def _dev_state(self):
        state = self.channel_object.input.state()
        return _STATE_MAP[state]

    def dev_status(self):
        self.__status = "We are in {0} state".format(self.dev_state())
        return self.__status

    def init_device(self):
        Device.init_device(self)


def getdevicefromname(klass=None, name=None):
    mykey = klass + "_" + name
    return dev_map.get(mykey, None)[0]


def recreate(db=None, new_server=False, typ="inputs"):
    global dev_map
    #    import pdb; pdb.set_trace()
    if db is None:
        db = tango.Database()

    # some io definitions.
    if typ == "inputs":
        classname = "BlissInput"
        classmsg = "input"
    elif typ == "outputs":
        classname = "BlissOutput"
        classmsg = "output"
    elif typ == "ctrl_loops":
        classname = "BlissLoop"
        classmsg = "loop"
    else:
        print "Type %s not recognized. Exiting" % typ
        sys.exit(255)

    server_name, instance_name, server_instance = get_server_info()

    registered_servers = set(db.get_instance_name_list("BlissTempManager"))

    # check if server exists in database. If not, create it.
    if instance_name not in registered_servers:
        if new_server:
            register_server(db=db)
        else:
            print "The device server %s is not defined in database. " "Exiting!" % server_instance
            print "hint: start with '-n' to create a new one automatically"
            sys.exit(255)

    dev_map = get_devices_from_server(db=db)

    io_names = get_server_io_names(typ=typ)

    # gather info about current io registered in database and
    # new io from config

    curr_ios = {}
    for dev_class, dev_names in dev_map.items():
        if not dev_class.startswith(classname):
            continue
        for dev_name in dev_names:
            curr_io_name = dev_name.rsplit("/", 1)[-1]
            curr_ios[curr_io_name] = dev_name, dev_class

    io_names_set = set(io_names)
    curr_io_names_set = set(curr_ios)
    new_io_names = io_names_set.difference(curr_io_names_set)
    old_io_names = curr_io_names_set.difference(io_names_set)

    domain = os.environ.get("BEAMLINENAME", "bliss")
    family = "temperature"
    member = instance_name

    # remove old io
    for io_name in old_io_names:
        dev_name, klass_name = curr_ios[io_name]
        elog.debug("removing old %s %s (%s)" % (classmsg, dev_name, io_name))
        db.delete_device(dev_name)

    # add new io
    for io_name in new_io_names:
        dev_name = "%s/%s_%s/%s" % (domain, family, member, io_name)
        info = tango.DbDevInfo()
        info.server = server_instance
        info._class = "%s_%s" % (classname, io_name)
        info.name = dev_name
        elog.debug("adding new %s %s (%s)" % (classmsg, dev_name, io_name))
        db.add_device(info)
        # try to create alias if it doesn't exist yet
        try:
            db.get_device_alias(io_name)
        except tango.DevFailed:
            elog.debug("registering alias for %s (%s)" % (dev_name, io_name))
            db.put_device_alias(dev_name, io_name)

    cfg = get_config()
    io_objs, tango_classes = [], []
    for io_name in curr_io_names_set:
        io_obj = cfg.get(io_name)
        io_objs.append(io_obj)
        tango_base_class = globals()[classname]
        tango_class = __create_tango_class(io_obj, tango_base_class)
        tango_classes.append(tango_class)

    return io_objs, tango_classes


def get_devices_from_server(argv=None, db=None):
    if db is None:
        db = tango.Database()

    if argv is None:
        argv = sys.argv

    # get sub devices
    _, _, personalName = get_server_info(argv)
    result = list(db.get_device_class_list(personalName))

    # dict<dev_name: tango_class_name>
    dev_dict = dict(zip(result[::2], result[1::2]))

    class_dict = {}
    for dev, class_name in dev_dict.items():
        devs = class_dict.setdefault(class_name, [])
        devs.append(dev)

    class_dict.pop("DServer", None)

    return class_dict


def register_server(db=None):
    if db is None:
        db = tango.Database()

    server_name, instance_name, server_instance = get_server_info()

    domain = os.environ.get("BEAMLINENAME", "bliss")
    dev_name = "{0}/temperature/{1}".format(domain, instance_name)
    elog.info(" registering new server: %s" % dev_name)
    info = tango.DbDevInfo()
    info.server = server_instance
    info._class = "DServer"
    info.name = "DServer/" + server_instance
    print server_instance
    db.add_device(info)


def get_server_io_names(instance_name=None, typ="inputs"):

    if typ == "inputs" or typ == "outputs" or typ == "ctrl_loops":
        pass
    else:
        print "Type %s not recognized. Exiting" % typ
        sys.exit(255)

    if instance_name is None:
        _, instance_name, _ = get_server_info()

    cfg = get_config()
    result = []
    for item_name in cfg.names_list:
        item_cfg = cfg.get_config(item_name)
        if item_cfg.plugin == "temperature" and instance_name in item_cfg.get(
            "tango_server", ()
        ):
            ctrl_inputs_cfg = item_cfg.parent.get(typ) or ()
            for ctrl_input in ctrl_inputs_cfg:
                name = ctrl_input.get("name") or ""
                if name == item_name:
                    result.append(item_name)
    return result


def get_server_info(argv=None):
    if argv is None:
        argv = sys.argv

    file_name = os.path.basename(argv[0])
    server_name = os.path.splitext(file_name)[0]
    instance_name = argv[1]
    server_instance = "/".join((server_name, instance_name))
    return server_name, instance_name, server_instance


def initialize_logging(argv):
    try:
        log_param = [param for param in argv if "-v" in param]
        if log_param:
            log_param = log_param[0]
            # print "-vN log flag found   len=%d" % len(log_param)
            if len(log_param) > 2:
                tango_log_level = int(log_param[2:])
            elif len(log_param) > 1:
                tango_log_level = 4
            else:
                print "BlissTempManager.py - ERROR LOG LEVEL"

            if tango_log_level == 1:
                elog.level(40)
            elif tango_log_level == 2:
                elog.level(30)
            elif tango_log_level == 3:
                elog.level(20)
            else:
                elog.level(10)
        else:
            # by default : show INFO
            elog.level(20)
            tango_log_level = 0
    except tango.DevFailed:
        print traceback.format_exc()
        elog.exception("Error in initializing logging")
        sys.exit(0)


def __create_tango_class(obj, klass):
    klass_name = klass.__name__
    tango_klass_name = "%s_%s" % (klass_name, obj.name)
    BlissClass = klass.TangoClassClass
    new_class_class = types.ClassType(
        "%sClass_%s" % (klass_name, obj.name), (BlissClass,), {}
    )
    new_class = types.ClassType(tango_klass_name, (klass,), {})
    new_class.TangoClassName = tango_klass_name
    new_class.TangoClassClass = new_class_class

    new_class_class.attr_list = dict(BlissClass.attr_list)
    new_class_class.cmd_list = dict(BlissClass.cmd_list)

    """
    CUSTOM COMMANDS
    """
    # Search and adds custom commands.
    _cmd_list = obj.custom_methods_list
    elog.debug("'%s' custom commands:" % obj.name)
    elog.debug(", ".join(map(str, _cmd_list)))

    def create_cmd(cmd_name):
        def cmd(self, *args, **kwargs):
            method = getattr(self.channel_object, cmd_name)
            return get_worker().execute(method, *args, **kwargs)

        return cmd

    _attr_list = obj.custom_attributes_list

    for (fname, (t1, t2)) in _cmd_list:
        # Skip the attr set/get methods
        attr = [n for n, t, a in _attr_list if fname in ["set_%s" % n, "get_%s" % n]]
        if attr:
            continue

        setattr(new_class, fname, create_cmd(fname))

        tin = types_conv_tab[t1]
        tout = types_conv_tab[t2]

        new_class_class.cmd_list.update({fname: [[tin, ""], [tout, ""]]})

        elog.debug("   %s (in: %s, %s) (out: %s, %s)" % (fname, t1, tin, t2, tout))

    # CUSTOM ATTRIBUTES
    elog.debug("'%s' custom attributes:" % obj.name)
    elog.debug(", ".join(map(str, _attr_list)))

    for name, t, access in _attr_list:
        attr_info = [types_conv_tab[t], tango.AttrDataFormat.SCALAR]
        if "r" in access:

            def read(self, attr):
                method = getattr(self.channel_object, "get_" + attr.get_name())
                value = get_worker().execute(method)
                attr.set_value(value)

            setattr(new_class, "read_%s" % name, read)
        if "w" in access:

            def write(self, attr):
                method = getattr(self.channel_object, "set_" + attr.get_name())
                value = attr.get_write_value()
                get_worker().execute(method, value)

            setattr(new_class, "write_%s" % name, write)

        write_dict = {"r": "READ", "w": "WRITE", "rw": "READ_WRITE"}
        attr_write = getattr(tango.AttrWriteType, write_dict[access])
        attr_info.append(attr_write)
        new_class_class.attr_list[name] = [attr_info]

    return new_class


def __get_type_name(temp):
    temp_type = None
    if isinstance(temp, temperature.Input):
        temp_type = "Input"
    elif isinstance(temp, temperature.Output):
        temp_type = "Output"
    elif isinstance(temp, temperature.Loop):
        temp_type = "Loop"
    return temp_type


def recreate_bliss(server_name, manager_dev_name, temp_names, dev_map, db=None):
    db = db or tango.Database()
    config = get_config()
    curr_temps = {}
    for dev_class, dev_names in dev_map.items():
        if (
            not dev_class.startswith("BlissInput_")
            and not dev_class.startswith("BlissOutput_")
            and not dev_class.startswith("BlissLoop_")
        ):
            continue
        for dev_name in dev_names:
            curr_temp_name = dev_name.rsplit("/", 1)[-1]

            try:
                config.get(curr_temp_name)
            except:
                elog.info("Error instantiating %s (%s):" % (curr_temp_name, dev_name))
                traceback.print_exc()
            curr_temps[curr_temp_name] = dev_name, dev_class

    temp_names_set = set(temp_names)
    curr_temp_names_set = set(curr_temps)
    new_temp_names = temp_names_set.difference(curr_temp_names_set)
    old_temp_names = curr_temp_names_set.difference(temp_names_set)

    domain, family, member = manager_dev_name.split("/", 2)

    # remove old temps
    for temp_name in old_temp_names:
        dev_name, klass_name = curr_temps[temp_name]
        elog.debug("removing old temp %s (%s)" % (dev_name, temp_name))
        db.delete_device(dev_name)

    # add new temps
    for temp_name in new_temp_names:
        temp = config.get(temp_name)
        temp_type = __get_type_name(temp)
        dev_name = "%s/%s_%s/%s" % (domain, family, member, temp_name)
        info = tango.DbDevInfo()
        info.server = server_name
        info._class = "Bliss%s_%s" % (temp_type, temp_name)
        info.name = dev_name
        elog.debug("adding new temp %s (%s)" % (dev_name, temp_name))
        db.add_device(info)
        # try to create alias if it doesn't exist yet
        try:
            db.get_device_alias(temp_name)
        except tango.DevFailed:
            elog.debug("registering alias for %s (%s)" % (dev_name, temp_name))
            db.put_device_alias(dev_name, temp_name)

    temps, tango_classes = [], []
    for temp_name in temp_names_set:
        temp = config.get(temp_name)
        temp_type = __get_type_name(temp)
        temps.append(temp)
        tango_base_class = globals()["Bliss" + temp_type]
        tango_class = __create_tango_class(temp, tango_base_class)
        tango_classes.append(tango_class)

    return temps, tango_classes


# callback from the Bliss server
def initialize_bliss(info, db=None):
    shell_info = info["shell_info"]
    object_names = info["object_names"]
    server_type = info["server_type"]
    server_instance = info["server_instance"]
    server_name = server_type + "/" + server_instance

    cfg = get_config()

    temp_names = []
    for name in object_names:
        obj_cfg = cfg.get_config(name)
        # if tango_server is defined it means it is manually added
        if "tango_server" in obj_cfg:
            continue
        if obj_cfg.plugin == "temperature":
            temp_names.append(name)

    objs, classes = recreate_bliss(
        server_name, info["manager_device_name"], temp_names, info["device_map"], db=db
    )
    return classes


def main(argv=None):
    from tango import GreenMode
    from tango.server import run

    if argv is None:
        argv = sys.argv
    argv = list(argv)

    try:
        argv.remove("-n")
        new_server = True
    except ValueError:
        new_server = False

    initialize_logging(argv)
    inputs, tango_input_classes = recreate(new_server=new_server, typ="inputs")
    outputs, tango_output_classes = recreate(new_server=new_server, typ="outputs")
    loops, tango_loop_classes = recreate(new_server=new_server, typ="ctrl_loops")
    tango_classes = tango_input_classes + tango_output_classes + tango_loop_classes
    run(tango_classes, args=argv, green_mode=GreenMode.Gevent)


if __name__ == "__main__":
    main()
