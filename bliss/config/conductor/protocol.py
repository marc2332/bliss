# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import struct

DEFAULT_UDP_SERVER_PORT = 8020

HEADER_SIZE = struct.calcsize("<ii")

UNKNOW_MESSAGE = -1

CONFIG = 1

(LOCK, UNLOCK, LOCK_OK_REPLY, LOCK_RETRY, LOCK_STOLEN, LOCK_STOLEN_OK_REPLY) = (
    20,
    21,
    22,
    23,
    24,
    25,
)

(REDIS_QUERY, REDIS_QUERY_ANSWER) = (30, 31)

# keep it for now for backward compatibility
(POSIX_MQ_QUERY, POSIX_MQ_OK, POSIX_MQ_FAILED, POSIX_MQ_OPENED) = (40, 41, 42, 43)

(CONFIG_GET_FILE, CONFIG_GET_FILE_FAILED, CONFIG_GET_FILE_OK) = (50, 51, 52)

(CONFIG_GET_DB_BASE_PATH, CONFIG_DB_FILE_RX, CONFIG_DB_END, CONFIG_DB_FAILED) = (
    60,
    61,
    62,
    63,
)

(CONFIG_SET_DB_FILE, CONFIG_SET_DB_FILE_FAILED, CONFIG_SET_DB_FILE_OK) = (70, 71, 72)

(CONFIG_REMOVE_FILE, CONFIG_REMOVE_FILE_FAILED, CONFIG_REMOVE_FILE_OK) = (80, 81, 82)

(CONFIG_MOVE_PATH, CONFIG_MOVE_PATH_FAILED, CONFIG_MOVE_PATH_OK) = (83, 84, 85)

(CONFIG_GET_DB_TREE, CONFIG_GET_DB_TREE_FAILED, CONFIG_GET_DB_TREE_OK) = (86, 87, 88)

(
    CONFIG_GET_PYTHON_MODULE,
    CONFIG_GET_PYTHON_MODULE_FAILED,
    CONFIG_GET_PYTHON_MODULE_RX,
    CONFIG_GET_PYTHON_MODULE_END,
) = (90, 91, 92, 93)

(UDS_QUERY, UDS_OK, UDS_FAILED) = (100, 101, 102)

(CLIENT_SET_NAME, CLIENT_GET_NAME, CLIENT_NAME_OK) = (110, 111, 112)


(WHO_LOCKED, WHO_LOCKED_FAILED, WHO_LOCKED_RX, WHO_LOCKED_END) = (120, 121, 122, 123)


class IncompleteMessage(Exception):
    pass


def message(cmd, contents=b""):
    return b"%s%s" % (struct.pack("<ii", cmd, len(contents)), contents)


def unpack_header(header):
    return struct.unpack("<ii", header)


def unpack_message(s):
    if len(s) < HEADER_SIZE:
        raise IncompleteMessage
    messageType, messageLen = struct.unpack("<ii", s[:HEADER_SIZE])
    if len(s) < HEADER_SIZE + messageLen:
        raise IncompleteMessage
    message = s[HEADER_SIZE : HEADER_SIZE + messageLen]
    remaining = s[HEADER_SIZE + messageLen :]
    return messageType, message, remaining
