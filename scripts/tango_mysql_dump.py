#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import argparse
import MySQLdb
from bliss.config import static


def main(host=None, user=None, passwd=None):
    config = static.get_config()

    conn = MySQLdb.connect(host=host, user=user, passwd=passwd, db="tango")
    cursor = conn.cursor()
    cursor.execute('select name,server,class from device where ior like "ior:%"')
    server2nodes = {}
    device2nodes = {}
    for name, server, klass in cursor:
        if name.startswith("dserver"):
            continue

        node = server2nodes.get(server)
        if node is None:
            node = static.ConfigNode(
                config.root, filename="tango/%s.yml" % server.replace("/", "_")
            )
            exe_name, personal = server.split("/")
            node["server"] = exe_name
            node["personal_name"] = personal
            server2nodes[server] = node

        device_node = static.ConfigNode(node)
        device_node["tango_name"] = name
        device_node["class"] = klass
        device2nodes[name] = device_node
        device_list = node.get("device")
        if device_list is None:
            node["device"] = [device_node]
        else:
            device_list.append(device_node)
    # properties
    cursor = conn.cursor()
    cursor.execute(
        "select device,name,value from property_device order by device,count"
    )
    for device, name, value in cursor:
        device_node = device2nodes.get(device)
        if device_node is None:
            continue
        properties = device_node.get("properties")
        if properties is None:
            properties = static.ConfigNode(device_node)
            device_node["properties"] = properties

        values = properties.get(name)
        if values is None:
            properties[name] = value
        else:
            if isinstance(values, list):
                values.append(value)
            else:
                properties[name] = [values, value]

    for node in server2nodes.values():
        node.save()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", dest="host", help="host where mysql is running")
    parser.add_argument("--user", dest="user", help="mysql user")
    parser.add_argument("--passwd", dest="passwd", help="mysql password")
    options = parser.parse_args()
    main(host=options.host, user=options.user, passwd=options.passwd)
