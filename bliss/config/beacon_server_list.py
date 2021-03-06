#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
import gevent
from gevent import socket
from bliss.config.conductor.connection import ip4_broadcast_discovery


def main():
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    ip4_broadcast_discovery(udp)

    replied_host = set()
    try:
        with gevent.Timeout(3., "END"):
            while True:
                msg, address = udp.recvfrom(8192)
                msg = msg.decode()
                host, port = msg.split("|")
                replied_host.add((host, port))
    except gevent.Timeout:
        pass

    if replied_host:
        max_host_len = max([len(host) for host, port in replied_host])
        format = "{0: <%d} {1}" % max_host_len
        print((format.format("HOST", "PORT")))
        for host, port in sorted(replied_host):
            print((format.format(host, port)))
    else:
        print("No response!!!")


if __name__ == "__main__":
    main()
