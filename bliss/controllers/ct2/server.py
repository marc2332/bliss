# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


"""
CT2 (P201 and C208) interface over the network using zerorpc.

This requires zerorpc and msgpack_numpy.

Usage:

    $ python -m bliss.controllers.ct2.server
    Serving ct2 on tcp://0.0.0.0:8909 ...

Test on the client machine using:

    $ zerorpc tcp://hostname:8909 -?
"""

# Imports
import sys
import logging
import weakref
import argparse

import six
import louie
import gevent.queue
import zerorpc
import msgpack_numpy

from bliss.controllers.ct2 import card
from bliss.controllers.ct2 import device


DEFAULT_BIND = '0.0.0.0'
DEFAULT_PORT = 8909
DEFAULT_HEARTBEAT = 5
DEFAULT_CARD_TYPE = 'P201'
DEFAULT_CARD_ADDRESS = '/dev/ct2_0'
DEFAULT_LOG_LEVEL = 'INFO'

log = logging.getLogger('CT2Server')

# Patching

msgpack_numpy.patch()


class CT2(device.CT2):

    def __init__(self, *args, **kwargs):
        super(CT2, self).__init__(*args, **kwargs)
        
    @zerorpc.stream
    def events(self, signal=None):
        if signal is None:
            signal = louie.All
        log.info('new stream (signal=%s)', signal)
        stream = gevent.queue.Queue()
        def receiver(value, signal, sender):
            stream.put((signal, value))
        louie.connect(receiver, signal, self)
        for msg in stream:
            if msg is None:
                break
            yield msg

    def get_property(self, key):
        result = getattr(self, key)
        return result

    def set_property(self, key, value):
        setattr(self, key, value)


def create_device(card_type, address):
    config = {
        'class': card_type + 'Card',
        'address': address,
    }
    card_obj = card.create_and_configure_card(config)
    device = CT2(card_obj)
    return device


def run(bind=DEFAULT_BIND, port=DEFAULT_PORT, heartbeat=DEFAULT_HEARTBEAT,
        card_type=DEFAULT_CARD_TYPE, address=DEFAULT_CARD_ADDRESS):
    access = "tcp://{}:{}".format(bind, port)
    device = create_device(card_type, address)
    server = zerorpc.Server(device, heartbeat=heartbeat)
    server.bind(access)
    log.info('Serving CT2 on {access}...'.format(access=access))
    try:
        server.run()
    except KeyboardInterrupt:
        log.info('Interrupted. Bailing out!')
    finally:
        server.close()


def main(args=None):
    if args is None:
        args = sys.argv[1:]
    parser = argparse.ArgumentParser(description='CT2 server')
    parser.add_argument('--address', default=DEFAULT_CARD_ADDRESS, type=str,
                        help='card address')
    parser.add_argument('--type', default=DEFAULT_CARD_TYPE, type=str,
                        dest='card_type',
                        help='card type', choices=['P201', 'C208'])
    parser.add_argument('--port', default=DEFAULT_PORT, type=int,
                        help='server port')
    parser.add_argument('--bind', default=DEFAULT_BIND, type=str,
                        help='server bind')
    parser.add_argument('--heartbeat', default=DEFAULT_HEARTBEAT, type=int,
                        help='heartbeat')
    parser.add_argument('--log-level', default=DEFAULT_LOG_LEVEL, type=str,
                        help='log level',
                        choices=['DEBUG', 'INFO', 'WARN', 'ERROR'])

    arguments = vars(parser.parse_args(args))

    log_level = arguments.pop('log_level', DEFAULT_LOG_LEVEL).upper()
    fmt = '%(levelname)s %(asctime)-15s %(name)s: %(message)s'
    logging.basicConfig(level=getattr(logging, log_level), format=fmt)
    run(**arguments)


if __name__ == '__main__':
    main()
