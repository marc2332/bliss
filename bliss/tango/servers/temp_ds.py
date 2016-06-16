# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import sys

import PyTango
from PyTango.server import Device, DeviceMeta, attribute, command

import bliss.common.log as elog
from bliss.config.static import get_config


_STATE_MAP = {
  'READY': PyTango.DevState.ON,
  'FAULT': PyTango.DevState.FAULT,
  'ALARM': PyTango.DevState.ALARM,
  'RUNNING': PyTango.DevState.RUNNING,
}

class BlissInput(Device):
    __metaclass__ = DeviceMeta

    @attribute(dtype=str)
    def channel(self):
        return self.input_channel.channel

    @property
    def input_channel(self):
        config = get_config()
        name = self.get_name().rsplit('/', 1)[-1] 
	return config.get(name) 

    @command(dtype_out=float)
    def read(self):
        return self.input_channel.read()       

    def dev_state(self):
        state = self.input_channel.state()
        return _STATE_MAP[state]

    def dev_status(self):
        self.__status = 'We are in {0} state'.format(self.dev_state())
        return self.__status

    def init_device(self):
        Device.init_device(self)
        
def recreate(db=None, new_server=False):

    if db is None:
        db = PyTango.Database()

    server_name, instance_name, server_instance = get_server_info()
    registered_servers = set(db.get_instance_name_list('BlissTempManager'))

    # check if server exists in database. If not, create it.
    if instance_name not in registered_servers:
        if new_server:
            register_server(db=db)
        else:
            print "The device server %s is not defined in database. " \
                  "Exiting!" % server_instance
            print "hint: start with '-n' to create a new one automatically"
            sys.exit(255)

    dev_map = get_devices_from_server(db=db)

    input_names = get_server_input_names()

    # gather info about current inputs registered in database and
    # new input from config

    curr_inputs = {}
    for dev_class, dev_names in dev_map.items():
        if not dev_class.startswith('BlissInput'):
            continue
        for dev_name in dev_names:
            curr_input_name = dev_name.rsplit("/", 1)[-1]
            curr_inputs[curr_input_name] = dev_name, dev_class

    input_names_set = set(input_names)
    curr_input_names_set = set(curr_inputs)
    new_input_names = input_names_set.difference(curr_input_names_set)
    old_input_names = curr_input_names_set.difference(input_names_set)

    domain = os.environ.get('BEAMLINENAME', 'bliss')
    family = 'temperature'
    member = instance_name

    # remove old inputs
    for input_name in old_input_names:
        dev_name = curr_inputs[input_name]
        elog.debug('removing old input %s (%s)' % (dev_name, input_name))
        db.delete_device(dev_name)

    # add new inputs
    for input_name in new_input_names:
        dev_name = "%s/%s_%s/%s" % (domain, family, member, input_name)
        info = PyTango.DbDevInfo()
        info.server = server_instance
        info._class = 'Blissinput' 
        info.name = dev_name
        elog.debug('adding new input %s (%s)' % (dev_name, input_name))
        db.add_device(info)
        # try to create alias if it doesn't exist yet
        try:
            db.get_device_alias(input_name)
        except PyTango.DevFailed:
            elog.debug('registering alias for %s (%s)' % (dev_name, input_name))
            db.put_device_alias(dev_name, input_name)

    return input_names

def get_devices_from_server(argv=None, db=None):
    if db is None:
        db = PyTango.Database()

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

    class_dict.pop('DServer', None)

    return class_dict

def register_server(db=None):
    if db is None:
        db = PyTango.Database()

    server_name, instance_name, server_instance = get_server_info()

    domain = os.environ.get('BEAMLINENAME', 'bliss')
    dev_name = '{0}/temperature/{1}'.format(domain, instance_name)
    elog.info(" registering new server: %s" % dev_name)
    info = PyTango.DbDevInfo()
    info.server = server_instance
    info._class = 'DServer'
    info.name = 'DServer/' + server_instance
    print server_instance
    db.add_device(info)

def get_server_input_names(instance_name=None):
    if instance_name is None:
        _, instance_name, _ = get_server_info()

    cfg = get_config()
    result = []
    for item_name in cfg.names_list:
        item_cfg = cfg.get_config(item_name)
        if item_cfg.plugin == 'temperature' and \
           instance_name in item_cfg.get('tango_server', ()):
            ctrl_inputs_cfg = item_cfg.parent.get('inputs') or ()
            for ctrl_input in ctrl_inputs_cfg:
                name = ctrl_input.get('name') or ''
                if name == item_name:
                    result.append(item_name)
    return result

def get_server_info(argv=None):
    if argv is None:
        argv = sys.argv

    file_name = os.path.basename(argv[0])
    server_name = os.path.splitext(file_name)[0]
    instance_name = argv[1]
    server_instance = '/'.join((server_name, instance_name))
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
    except PyTango.DevFailed:
        print traceback.format_exc()
        elog.exception("Error in initializing logging")
        sys.exit(0)

def main(argv=None):
    from PyTango import GreenMode
    from PyTango.server import run

    if argv is None:
        argv = sys.argv
    argv = list(argv)

    try:
        argv.remove('-n')
        new_server = True
    except ValueError:
        new_server = False

    initialize_logging(argv)
    input_names = recreate(new_server=new_server)
    run([BlissInput,], args=argv, green_mode=GreenMode.Gevent)    

if __name__ == "__main__":
    main()

