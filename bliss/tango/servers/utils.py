# -*- coding: utf-8 -*-

"""
tango server utilities
"""


import os
import sys

import tango


def get_server_info(argv=None):
    """
    Returns a tuple with three elements: server type, server instance, server name

    Example: ('Bliss', 'sixc', 'Bliss/sixc')
    """

    argv = argv or sys.argv

    file_name = os.path.basename(argv[0])
    server_type = os.path.splitext(file_name)[0]
    instance_name = argv[1]
    server_instance = "/".join((server_type, instance_name))
    return server_type, instance_name, server_instance


def get_devices_from_server(argv=None, db=None):
    """
    Returns the devices already registered. dict< str(tango class name): list(device names) >
    """
    argv = argv or sys.argv
    db = db or tango.Database()

    # get sub devices
    _, _, personal_name = get_server_info(argv)
    result = list(db.get_device_class_list(personal_name))

    # dict<dev_name: tango_class_name>
    dev_dict = dict(zip(result[::2], result[1::2]))

    class_dict = {}
    for dev, class_name in dev_dict.items():
        devs = class_dict.setdefault(class_name, [])
        devs.append(dev)

    class_dict.pop("DServer", None)

    return class_dict
