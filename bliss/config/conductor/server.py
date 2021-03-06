# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


# Imports

import os
import sys
import json
import codecs
import shutil
import logging
import argparse
import weakref
import socket
import signal
import traceback
import pkgutil
import tempfile
import gevent
import ipaddress
import subprocess
from contextlib import contextmanager, ExitStack
from gevent import select
from gevent import monkey
from gevent.socket import cancel_wait_ex

from bliss.common import event
from . import protocol
from .. import redis as redis_conf
from functools import reduce
from . import client
from . import connection


try:
    import win32api
except ImportError:
    IS_WINDOWS = False
else:
    IS_WINDOWS = True


# Globals

_waitstolen = dict()
_options = None
_lock_object = {}
_client_to_object = weakref.WeakKeyDictionary()
_client_to_name = weakref.WeakKeyDictionary()
_waiting_lock = weakref.WeakKeyDictionary()
uds_port_name = None


beacon_logger = logging.getLogger("beacon")
tango_logger = beacon_logger.getChild("tango")
redis_logger = beacon_logger.getChild("redis")
redis_data_logger = beacon_logger.getChild("redis_data")
web_logger = beacon_logger.getChild("web")
log_server_logger = beacon_logger.getChild("log_server")
log_viewer_logger = beacon_logger.getChild("log_viewer")


# Helpers


class _WaitStolenReply(object):
    def __init__(self, stolen_lock):
        self._stolen_lock = dict()
        for client, objects in stolen_lock.items():
            self._stolen_lock[client] = b"|".join(objects)
        self._client2info = dict()

    def __enter__(self):
        for client, message in self._stolen_lock.items():
            event = gevent.event.Event()
            client2sync = _waitstolen.setdefault(message, dict())
            client2sync[client] = event
            client.sendall(protocol.message(protocol.LOCK_STOLEN, message))
        return self

    def __exit__(self, *args, **keys):
        for client, message in self._stolen_lock.items():
            client2sync = _waitstolen.pop(message, None)
            if client2sync is not None:
                client2sync.pop(client, None)
            if client2sync:
                _waitstolen[message] = client2sync

    def wait(self, timeout):
        with gevent.Timeout(
            timeout, RuntimeError("some client(s) didn't reply to stolen lock")
        ):
            for client, message in self._stolen_lock.items():
                client2sync = _waitstolen.get(message)
                if client2sync is not None:
                    sync = client2sync.get(client)
                    sync.wait()


# Methods


def _releaseAllLock(client_id):
    objset = _client_to_object.pop(client_id, set())
    for obj in objset:
        _lock_object.pop(obj)
    # Inform waiting client
    tmp_dict = dict(_waiting_lock)
    for client_sock, tlo in tmp_dict.items():
        try_lock_object = set(tlo)
        if try_lock_object.intersection(objset):
            objs = _waiting_lock.pop(client_sock)
            try:
                client_sock.sendall(protocol.message(protocol.LOCK_RETRY))
            except OSError:
                # maybe this client is dead or whatever
                continue


def _lock(client_id, prio, lock_obj, raw_message):
    all_free = True
    for obj in lock_obj:
        socket_id, compteur, lock_prio = _lock_object.get(obj, (None, None, None))
        if socket_id and socket_id != client_id:
            if prio > lock_prio:
                continue
            all_free = False
            break

    if all_free:
        stolen_lock = {}
        for obj in lock_obj:
            socket_id, compteur, lock_prio = _lock_object.get(obj, (client_id, 0, prio))
            if socket_id != client_id:  # still lock
                pre_obj = stolen_lock.get(socket_id, None)
                if pre_obj is None:
                    stolen_lock[socket_id] = [obj]
                else:
                    pre_obj.append(obj)
                _lock_object[obj] = (client_id, 1, prio)
                objset = _client_to_object.get(socket_id, set())
                objset.remove(obj)
            else:
                compteur += 1
                new_prio = lock_prio > prio and lock_prio or prio
                _lock_object[obj] = (client_id, compteur, new_prio)

        try:
            with _WaitStolenReply(stolen_lock) as w:
                w.wait(3.)
        except RuntimeError:
            beacon_logger.warning("some client(s) didn't reply to the stolen lock")

        obj_already_locked = _client_to_object.get(client_id, set())
        _client_to_object[client_id] = set(lock_obj).union(obj_already_locked)

        client_id.sendall(protocol.message(protocol.LOCK_OK_REPLY, raw_message))
    else:
        _waiting_lock[client_id] = lock_obj


def _unlock(client_id, priority, unlock_obj):
    unlock_object = []
    client_locked_obj = _client_to_object.get(client_id, None)
    if client_locked_obj is None:
        return

    for obj in unlock_obj:
        socket_id, compteur, prio = _lock_object.get(obj, (None, None, None))
        if socket_id and socket_id == client_id:
            compteur -= 1
            if compteur <= 0:
                _lock_object.pop(obj)
                try:
                    client_locked_obj.remove(obj)
                    _lock_object.pop(obj)
                except KeyError:
                    pass
                unlock_object.append(obj)
            else:
                _lock_object[obj] = (client_id, compteur, prio)

    unlock_object = set(unlock_object)
    tmp_dict = dict(_waiting_lock)
    for client_sock, tlo in tmp_dict.items():
        try_lock_object = set(tlo)
        if try_lock_object.intersection(unlock_object):
            objs = _waiting_lock.pop(client_sock)
            client_sock.sendall(protocol.message(protocol.LOCK_RETRY))


def _clean(client):
    _releaseAllLock(client)


def _send_redis_info(client_id, local_connection):
    port = _options.redis_port
    host = socket.gethostname()
    if local_connection:
        port = _options.redis_socket
        host = "localhost"

    contents = b"%s:%s" % (host.encode(), str(port).encode())

    client_id.sendall(protocol.message(protocol.REDIS_QUERY_ANSWER, contents))


def _send_redis_data_server_info(client_id, message, local_connection):
    try:
        message_key, _ = message.split(b"|")
    except ValueError:  # message is bad, skip it
        return
    port = _options.redis_data_port
    if port == 0:
        client_id.sendall(
            protocol.message(
                protocol.REDIS_DATA_SERVER_FAILED,
                b"%s|Redis Data server is not started" % (message_key),
            )
        )
    else:
        if local_connection:
            port = _options.redis_data_socket
            host = "localhost"
        else:
            host = socket.gethostname()
        contents = b"%s|%s|%s" % (message_key, host.encode(), str(port).encode())
        client_id.sendall(protocol.message(protocol.REDIS_DATA_SERVER_OK, contents))


def _send_config_file(client_id, message):
    try:
        message_key, file_path = message.split(b"|")
    except ValueError:  # message is bad, skip it
        return
    file_path = file_path.decode().replace("../", "")  # prevent going up
    full_path = os.path.join(_options.db_path, file_path)
    try:
        with open(full_path, "rb") as f:
            buffer = f.read()
            client_id.sendall(
                protocol.message(
                    protocol.CONFIG_GET_FILE_OK, b"%s|%s" % (message_key, buffer)
                )
            )
    except IOError:
        client_id.sendall(
            protocol.message(
                protocol.CONFIG_GET_FILE_FAILED,
                b"%s|File doesn't exist" % (message_key),
            )
        )


def __find_module(client_id, message_key, path, parent_name=None):
    for importer, name, ispkg in pkgutil.walk_packages([path]):
        module_name = name if parent_name is None else "%s.%s" % (parent_name, name)
        client_id.sendall(
            protocol.message(
                protocol.CONFIG_GET_PYTHON_MODULE_RX,
                b"%s|%s|%s"
                % (
                    message_key,
                    module_name.encode(),
                    importer.find_module(name).get_filename().encode(),
                ),
            )
        )
        if ispkg:
            __find_module(client_id, message_key, os.path.join(path, name), module_name)


def _get_python_module(client_id, message):
    try:
        message_key, start_module_path = message.split(b"|")
    except ValueError:
        client_id.sendall(
            protocol.message(
                protocol.CONFIG_GET_PYTHON_MODULE_FAILED,
                b"%s|Can't split message (%s)" % (message_key, message),
            )
        )
        return

    start_module_path = start_module_path.decode().replace(
        "../", ""
    )  # prevent going up
    start_module_path = os.path.join(_options.db_path, start_module_path)

    __find_module(client_id, message_key, start_module_path)
    client_id.sendall(
        protocol.message(protocol.CONFIG_GET_PYTHON_MODULE_END, b"%s|" % message_key)
    )


def __remove_empty_tree(base_dir=None, keep_empty_base=True):
    """
    Helper to remove empty directory tree.

    If *base_dir* is *None* (meaning start at the beacon server base directory),
    the *keep_empty_base* is forced to True to prevent the system from removing
    the beacon base path

    :param base_dir: directory to start from [default is None meaning start at
                     the beacon server base directory
    :type base_dir: str
    :param keep_empty_base: if True (default) doesn't remove the given
                            base directory. Otherwise the base directory is
                            removed if empty.
    """
    if base_dir is None:
        base_dir = _options.db_path
        keep_empty_base = False

    for dir_path, dir_names, file_names in os.walk(base_dir, topdown=False):
        if keep_empty_base and dir_path == base_dir:
            continue
        if file_names:
            continue
        for dir_name in dir_names:
            full_dir_name = os.path.join(dir_path, dir_name)
            if not os.listdir(full_dir_name):  # check if directory is empty
                os.removedirs(full_dir_name)


def _remove_config_file(client_id, message):
    try:
        message_key, file_path = message.split(b"|")
    except ValueError:  # message is bad, skip it
        return
    file_path = file_path.decode().replace("../", "")  # prevent going up
    full_path = os.path.join(_options.db_path, file_path)
    try:
        if os.path.isfile(full_path):
            os.remove(full_path)
        elif os.path.isdir(full_path):
            shutil.rmtree(full_path)

        # walk back in directory tree removing empty directories. Do this to
        # prevent future rename operations to inadvertely ending up inside a
        # "transparent" directory instead of being renamed
        __remove_empty_tree()
        msg = (protocol.CONFIG_REMOVE_FILE_OK, b"%s|0" % (message_key,))
    except IOError:
        msg = (
            protocol.CONFIG_REMOVE_FILE_FAILED,
            b"%s|File/directory doesn't exist" % message_key,
        )
    else:
        event.send(__name__, "config_changed")

    client_id.sendall(protocol.message(*msg))


def _move_config_path(client_id, message):
    # should work on both files and folders
    # it can be used for both move and rename
    try:
        message_key, src_path, dst_path = message.split(b"|")
    except ValueError:  # message is bad, skip it
        return
    src_path = src_path.decode().replace("../", "")  # prevent going up
    src_full_path = os.path.join(_options.db_path, src_path)

    dst_path = dst_path.decode().replace("../", "")  # prevent going up
    dst_full_path = os.path.join(_options.db_path, dst_path)

    try:
        # make sure the parent directory exists
        parent_dir = os.path.dirname(dst_full_path)
        if not os.path.isdir(parent_dir):
            os.makedirs(parent_dir)
        shutil.move(src_full_path, dst_full_path)

        # walk back in directory tree removing empty directories. Do this to
        # prevent future rename operations to inadvertely ending up inside a
        # "transparent" directory instead of being renamed
        __remove_empty_tree()
        msg = (protocol.CONFIG_MOVE_PATH_OK, b"%s|0" % (message_key,))
    except IOError as ioe:
        msg = (
            protocol.CONFIG_MOVE_PATH_FAILED,
            b"%s|%s: %s" % (message_key, ioe.filename, ioe.strerror),
        )
    else:
        event.send(__name__, "config_changed")
    client_id.sendall(protocol.message(*msg))


def _send_config_db_files(client_id, message):
    try:
        message_key, sub_path = message.split(b"|")
    except ValueError:  # message is bad, skip it
        return
    # convert sub_path to unicode
    sub_path = sub_path.decode()
    sub_path = sub_path.replace("../", "")  # prevent going up
    if sub_path:
        path = os.path.join(_options.db_path, sub_path)
    else:
        path = _options.db_path
    try:
        for root, dirs, files in os.walk(path, followlinks=True):
            try:
                files.remove("__init__.yml")
            except ValueError:  # init not in files list
                pass
            else:
                files.insert(0, "__init__.yml")
            for filename in files:
                if filename.startswith("."):
                    continue
                basename, ext = os.path.splitext(filename)
                if ext == ".yml":
                    full_path = os.path.join(root, filename)
                    rel_path = full_path[len(_options.db_path) + 1 :]
                    try:
                        with codecs.open(full_path, "r", "utf-8") as f:
                            raw_buffer = f.read().encode("utf-8")
                            msg = protocol.message(
                                protocol.CONFIG_DB_FILE_RX,
                                b"%s|%s|%s"
                                % (message_key, rel_path.encode(), raw_buffer),
                            )
                            client_id.sendall(msg)
                    except Exception as e:
                        sys.excepthook(*sys.exc_info())
                        client_id.sendall(
                            protocol.message(
                                protocol.CONFIG_DB_FAILED,
                                b"%s|%s" % (message_key, repr(e).encode()),
                            )
                        )
    except Exception as e:
        sys.excepthook(*sys.exc_info())
        client_id.sendall(
            protocol.message(
                protocol.CONFIG_DB_FAILED, b"%s|%s" % (message_key, repr(e).encode())
            )
        )
    finally:
        client_id.sendall(
            protocol.message(protocol.CONFIG_DB_END, b"%s|" % (message_key))
        )


def __get_directory_structure(base_dir):
    """
    Helper that creates a nested dictionary that represents the folder structure of base_dir
    """
    result = {}
    base_dir = base_dir.rstrip(os.sep)
    start = base_dir.rfind(os.sep) + 1
    for path, dirs, files in os.walk(base_dir, followlinks=True, topdown=True):
        # with topdown=True, the search can be pruned by altering 'dirs'
        dirs[:] = [d for d in dirs if d not in (".git",)]
        folders = path[start:].split(os.sep)
        subdir = dict.fromkeys((f for f in files if "~" not in f))
        parent = reduce(dict.get, folders[:-1], result)
        parent[folders[-1]] = subdir
    assert len(result) == 1
    return result.popitem()


def _send_config_db_tree(client_id, message):
    try:
        message_key, sub_path = message.split(b"|")
    except ValueError:  # message is bad, skip it
        return
    sub_path = sub_path.replace(b"../", b"")  # prevent going up
    look_path = (
        sub_path and os.path.join(_options.db_path, sub_path) or _options.db_path
    )

    try:
        _, tree = __get_directory_structure(look_path)
        msg = (
            protocol.CONFIG_GET_DB_TREE_OK,
            b"%s|%s" % (message_key, json.dumps(tree).encode()),
        )
    except Exception as e:
        sys.excepthook(*sys.exc_info())
        msg = (
            protocol.CONFIG_GET_DB_TREE_FAILED,
            b"%s|Failed to get tree: %s" % (message_key, str(e).encode()),
        )
    client_id.sendall(protocol.message(*msg))


def _write_config_db_file(client_id, message):
    first_pos = message.find(b"|")
    second_pos = message.find(b"|", first_pos + 1)

    if first_pos < 0 or second_pos < 0:  # message malformed
        msg = protocol.message(
            protocol.CONFIG_SET_DB_FILE_FAILED,
            b"%s|%s" % (message, "Malformed message"),
        )
        client_id.sendall(msg)
        return

    message_key = message[:first_pos]
    file_path = message[first_pos + 1 : second_pos].decode()
    content = message[second_pos + 1 :]
    file_path = file_path.replace("../", "")  # prevent going up
    full_path = os.path.join(_options.db_path, file_path)
    full_dir = os.path.dirname(full_path)
    if not os.path.isdir(full_dir):
        os.makedirs(full_dir)
    try:
        with open(full_path, "wb") as f:
            f.write(content)
            msg = protocol.message(
                protocol.CONFIG_SET_DB_FILE_OK, b"%s|0" % message_key
            )
    except BaseException:
        msg = protocol.message(
            protocol.CONFIG_SET_DB_FILE_FAILED,
            b"%s|%s" % (message_key, traceback.format_exc().encode()),
        )
    else:
        event.send(__name__, "config_changed")
    client_id.sendall(msg)


def _send_uds_connection(client_id, client_hostname):
    client_hostname = client_hostname.decode()
    try:
        if uds_port_name and client_hostname == socket.gethostname():
            client_id.sendall(protocol.message(protocol.UDS_OK, uds_port_name.encode()))
        else:
            client_id.sendall(protocol.message(protocol.UDS_FAILED))
    except BaseException:
        sys.excepthook(*sys.exc_info())


def _get_set_client_id(client_id, messageType, message):
    message_key, message = message.split(b"|")
    if messageType is protocol.CLIENT_SET_NAME:
        _client_to_name[client_id] = message
    msg = b"%s|%s" % (message_key, _client_to_name.get(client_id, b""))
    client_id.sendall(protocol.message(protocol.CLIENT_NAME_OK, msg))


def _send_who_locked(client_id, message):
    message_key, *names = message.split(b"|")
    if not names:
        names = list(_lock_object.keys())

    for name in names:
        socket_id, compteur, lock_prio = _lock_object.get(name, (None, None, None))
        if socket_id is None:
            continue
        msg = b"%s|%s|%s" % (
            message_key,
            name,
            _client_to_name.get(socket_id, b"Unknown"),
        )
        client_id.sendall(protocol.message(protocol.WHO_LOCKED_RX, msg))
    client_id.sendall(protocol.message(protocol.WHO_LOCKED_END, b"%s|" % message_key))


def _send_log_server_address(client_id, message):
    message_key, *names = message.split(b"|")
    port = _options.log_server_port
    host = socket.gethostname().encode()
    if not port:
        # lo log server
        client_id.sendall(
            protocol.message(
                protocol.LOG_SERVER_ADDRESS_FAIL,
                b"%s|%s" % (message_key, b"no log server"),
            )
        )
    else:
        client_id.sendall(
            protocol.message(
                protocol.LOG_SERVER_ADDRESS_OK, b"%s|%s|%d" % (message_key, host, port)
            )
        )


def _send_unknow_message(client_id, message):
    client_id.sendall(protocol.message(protocol.UNKNOW_MESSAGE, message))


def _client_rx(client, local_connection):
    tcp_data = b""
    try:
        stopFlag = False
        while not stopFlag:
            try:
                raw_data = client.recv(16 * 1024)
            except BaseException:
                break

            if raw_data:
                tcp_data = b"%s%s" % (tcp_data, raw_data)
            else:
                break

            data = tcp_data
            c_id = client

            while data:
                try:
                    messageType, message, data = protocol.unpack_message(data)
                    if messageType == protocol.LOCK:
                        lock_objects = message.split(b"|")
                        prio = int(lock_objects.pop(0))
                        _lock(c_id, prio, lock_objects, message)
                    elif messageType == protocol.UNLOCK:
                        lock_objects = message.split(b"|")
                        prio = int(lock_objects.pop(0))
                        _unlock(c_id, prio, lock_objects)
                    elif messageType == protocol.LOCK_STOLEN_OK_REPLY:
                        client2sync = _waitstolen.get(message)
                        if client2sync is not None:
                            sync = client2sync.get(c_id)
                            if sync is not None:
                                sync.set()
                    elif messageType == protocol.REDIS_QUERY:
                        _send_redis_info(c_id, local_connection)
                    elif messageType == protocol.REDIS_DATA_SERVER_QUERY:
                        _send_redis_data_server_info(c_id, message, local_connection)
                    elif messageType == protocol.CONFIG_GET_FILE:
                        _send_config_file(c_id, message)
                    elif messageType == protocol.CONFIG_GET_DB_BASE_PATH:
                        _send_config_db_files(c_id, message)
                    elif messageType == protocol.CONFIG_GET_DB_TREE:
                        _send_config_db_tree(c_id, message)
                    elif messageType == protocol.CONFIG_SET_DB_FILE:
                        _write_config_db_file(c_id, message)
                    elif messageType == protocol.CONFIG_REMOVE_FILE:
                        _remove_config_file(c_id, message)
                    elif messageType == protocol.CONFIG_MOVE_PATH:
                        _move_config_path(c_id, message)
                    elif messageType == protocol.CONFIG_GET_PYTHON_MODULE:
                        _get_python_module(c_id, message)
                    elif messageType == protocol.UDS_QUERY:
                        _send_uds_connection(c_id, message)
                    elif messageType in (
                        protocol.CLIENT_SET_NAME,
                        protocol.CLIENT_GET_NAME,
                    ):
                        _get_set_client_id(c_id, messageType, message)
                    elif messageType == protocol.WHO_LOCKED:
                        _send_who_locked(c_id, message)
                    elif messageType == protocol.LOG_SERVER_ADDRESS_QUERY:
                        _send_log_server_address(c_id, message)
                    else:
                        _send_unknow_message(c_id, message)
                except ValueError:
                    sys.excepthook(*sys.exc_info())
                    break
                except protocol.IncompleteMessage:
                    r, _, _ = select.select([client], [], [], .5)
                    if not r:  # if timeout, something wired, close the connection
                        data = None
                        stopFlag = True
                    break
                except BaseException:
                    sys.excepthook(*sys.exc_info())
                    beacon_logger.error("Error with client id %r, close it", client)
                    raise

            tcp_data = data
    except BaseException:
        sys.excepthook(*sys.exc_info())
    finally:
        try:
            _clean(client)
        finally:
            client.close()


@contextmanager
def pipe():
    rp, wp = os.pipe()
    try:
        yield (rp, wp)
    finally:
        os.close(wp)
        os.close(rp)


def log_tangodb_started():
    """Raise exception when tango database not started in 10 seconds
    """
    from bliss.tango.clients.utils import wait_tango_db

    try:
        wait_tango_db(port=_options.tango_port, db=2)
    except Exception:
        tango_logger.error("Tango database NOT started")
        raise
    else:
        tango_logger.info("Tango database started")


@contextmanager
def start_webserver(web_app, webapp_port):
    """Part of the 'Beacon server'"""
    web_logger.info(f"Web application '{web_app.name}' listening on port {webapp_port}")

    # Note: Flask uses click.echo for direct stdout printing
    #       werkzeug._internal._log sets the log level of logger "werkzeug" to INFO
    web_app.logger.propagate = True  # use root logger
    web_app.logger.handlers = []
    try:
        from werkzeug import _internal
    except ImportError:
        pass
    else:
        _internal._logger = web_app.logger.getChild("werkzeug")

    with spawn_context(
        web_app.run,
        host="0.0.0.0",
        port=webapp_port,
        debug=web_app.debug,
        use_debugger=True,
        use_reloader=False,  # prevent forking a subprocess
        threaded=False,
    ):
        yield


@contextmanager
def start_udp_server():
    """Part of the 'Beacon server'"""
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    udp.bind(("", protocol.DEFAULT_UDP_SERVER_PORT))
    try:
        yield udp
    finally:
        udp.close()


@contextmanager
def start_tcp_server():
    """Part of the 'Beacon server'"""
    tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tcp.bind(("", _options.port))
    tcp.listen(512)  # limit to 512 clients
    try:
        yield tcp
    finally:
        tcp.close()


@contextmanager
def start_uds_server():
    """Part of the 'Beacon server'"""
    global uds_port_name
    if IS_WINDOWS:
        uds_port_name = None
        yield None
        return
    path = tempfile._get_default_tempdir()
    random_name = next(tempfile._get_candidate_names())
    uds_port_name = os.path.join(path, f"beacon_{random_name}.sock")
    try:
        uds = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        uds.bind(uds_port_name)
        os.chmod(uds_port_name, 0o777)
        uds.listen(512)
        try:
            yield uds
        finally:
            uds.close()
    finally:
        try:
            os.unlink(uds_port_name)
        except Exception:
            pass


def udp_server_main(sock, beacon_port):
    """Beacon server: listen on UDP port
    """
    port = sock.getsockname()[1]
    beacon_logger.info("start listening on UDP port %s", port)

    try:
        udp_reply = b"%s|%d" % (socket.gethostname().encode(), beacon_port)

        while True:
            try:
                buff, address = sock.recvfrom(8192)
            except cancel_wait_ex:
                return
            send_flag = True
            if buff.find(b"Hello") > -1:
                if _options.add_filter:
                    for add in _options.add_filter:
                        if ipaddress.ip_address(address[0]) in ipaddress.ip_network(
                            add
                        ):
                            break
                    else:
                        send_flag = False
            if send_flag:
                beacon_logger.info(
                    "UDP: address request from %s. Replying with %r", address, udp_reply
                )
                sock.sendto(udp_reply, address)
            else:
                beacon_logger.info(
                    "UDP: filter address %s with filter %a",
                    address,
                    _options.add_filter,
                )
    finally:
        beacon_logger.info("stop listening on UDP port %s", port)


def tcp_server_main(sock):
    """Beacon server: listen on TCP port
    """
    port = sock.getsockname()[1]
    beacon_logger.info("start listening on TCP port %s", port)
    beacon_logger.info("configuration path: %s", _options.db_path)
    try:
        while True:
            try:
                newSocket, addr = sock.accept()
            except cancel_wait_ex:
                return
            newSocket.setsockopt(socket.SOL_IP, socket.IP_TOS, 0x10)
            localhost = addr[0] == "127.0.0.1"
            gevent.spawn(_client_rx, newSocket, localhost)
    finally:
        beacon_logger.info("stop listening on TCP port %s", port)


def ensure_global_beacon_connection(beacon_port):
    """Avoid auto-discovery of port for the global connection object.
    """
    if client._default_connection is None:
        client._default_connection = connection.Connection("localhost", beacon_port)


def uds_server_main(sock):
    """Beacon server: listen on UDS socket
    """
    beacon_logger.info("start listening on UDS socket %s", uds_port_name)
    try:
        while True:
            try:
                newSocket, addr = sock.accept()
            except cancel_wait_ex:
                return
            gevent.spawn(_client_rx, newSocket, True)
    finally:
        beacon_logger.info("stop listening on UDS socket %s", uds_port_name)


def stream_to_log(stream, log_func):
    """Forward a stream to a log function
    """
    gevent.get_hub().threadpool.maxsize += 1
    while True:
        msg = gevent.os.tp_read(stream, 8192)
        if msg:
            log_func(msg.decode())


@contextmanager
def logged_subprocess(args, logger, **kw):
    """Subprocess with stdout/stderr logging
    """
    with pipe() as (rp_out, wp_out):
        with pipe() as (rp_err, wp_err):
            log_stdout = gevent.spawn(stream_to_log, rp_out, logger.info)
            log_stderr = gevent.spawn(stream_to_log, rp_err, logger.error)
            greenlets = [log_stdout, log_stderr]
            proc = subprocess.Popen(args, stdout=wp_out, stderr=wp_err, **kw)
            msg = f"(pid={proc.pid}) {repr(' '.join(args))}"
            beacon_logger.info(f"started {msg}")
            try:
                yield
            finally:
                beacon_logger.info(f"terminating {msg}")
                proc.terminate()
                gevent.killall(greenlets)
                beacon_logger.info(f"terminated {msg}")


@contextmanager
def spawn_context(func, *args, **kw):
    g = gevent.spawn(func, *args, **kw)
    try:
        yield
    finally:
        g.kill()


def wait():
    """Wait for exit signal
    """

    with pipe() as (rp, wp):

        def sigterm_handler(*args, **kw):
            # This is executed in the hub so use a pipe
            # Find a better way:
            # https://github.com/gevent/gevent/issues/1683
            os.write(wp, b"!")

        event = gevent.event.Event()

        def sigterm_greenlet():
            # Graceful shutdown
            gevent.get_hub().threadpool.maxsize += 1
            gevent.os.tp_read(rp, 1)
            beacon_logger.info("Received a termination signal")
            event.set()

        with spawn_context(sigterm_greenlet):
            # Binds system signals.
            signal.signal(signal.SIGTERM, sigterm_handler)
            if IS_WINDOWS:
                signal.signal(signal.SIGINT, sigterm_handler)
                # ONLY FOR Win7 (COULD BE IGNORED ON Win10 WHERE CTRL-C PRODUCES A SIGINT)
                win32api.SetConsoleCtrlHandler(sigterm_handler, True)
            else:
                signal.signal(signal.SIGHUP, sigterm_handler)
                signal.signal(signal.SIGQUIT, sigterm_handler)

            try:
                event.wait()
            except KeyboardInterrupt:
                beacon_logger.info("Received a keyboard interrupt")
            except Exception as exc:
                sys.excepthook(*sys.exc_info())
                beacon_logger.critical("An unexpected exception occured:\n%r", exc)


def configure_logging():
    """Configure the root logger:
        * set log level according to CLI arguments
        * send DEBUG and INFO to STDOUT
        * send WARNING, ERROR and CRITICAL to STDERR
    """
    log_fmt = "%(levelname)s %(asctime)-15s %(name)s: %(message)s"

    rootlogger = logging.getLogger()
    rootlogger.setLevel(_options.log_level.upper())

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(lambda record: record.levelno < logging.WARNING)
    handler.setFormatter(logging.Formatter(log_fmt))
    rootlogger.addHandler(handler)

    handler = logging.StreamHandler(sys.stderr)
    handler.addFilter(lambda record: record.levelno >= logging.WARNING)
    handler.setFormatter(logging.Formatter(log_fmt))
    rootlogger.addHandler(handler)


def main(args=None):
    # Monkey patch needed for web server
    # just keep for consistency because it's already patched
    # in __init__ in bliss project
    from gevent import monkey

    monkey.patch_all(thread=False)

    # Argument parsing
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db-path",
        "--db_path",
        dest="db_path",
        default=os.environ.get("BEACON_DB_PATH", "./db"),
        help="database path",
    )
    parser.add_argument(
        "--redis-port",
        "--redis_port",
        dest="redis_port",
        default=6379,
        type=int,
        help="redis connection port",
    )
    parser.add_argument(
        "--redis-conf",
        "--redis_conf",
        dest="redis_conf",
        default=redis_conf.get_redis_config_path(),
        help="path to alternative redis configuration file",
    )
    parser.add_argument(
        "--redis-data-port",
        "--redis_data_port",
        dest="redis_data_port",
        default=6380,
        type=int,
        help="redis data connection port (0 mean don't start redis data server)",
    )
    parser.add_argument(
        "--redis-data-conf",
        "--redis_data_conf",
        dest="redis_data_conf",
        default=redis_conf.get_redis_data_config_path(),
        help="path to alternative redis configuration file for data server",
    )
    parser.add_argument(
        "--redis-data-socket",
        dest="redis_data_socket",
        default="/tmp/redis_data.sock",
        help="Unix socket for redis (default to /tmp/redis_data.sock)",
    )

    parser.add_argument(
        "--port",
        dest="port",
        type=int,
        default=int(os.environ.get("BEACON_PORT", 0)),
        help="server port (default to BEACON_PORT environment variable, "
        "otherwise takes a free port)",
    )
    parser.add_argument(
        "--tango-port",
        "--tango_port",
        dest="tango_port",
        type=int,
        default=0,
        help="tango server port (default to 0: disable)",
    )
    parser.add_argument(
        "--tango-debug-level",
        "--tango_debug_level",
        dest="tango_debug_level",
        type=int,
        default=0,
        help="tango debug level (default to 0: WARNING,1:INFO,2:DEBUG)",
    )
    parser.add_argument(
        "--webapp-port",
        "--webapp_port",
        dest="webapp_port",
        type=int,
        default=9030,
        help="web server port for beacon configuration (0: disable)",
    )
    parser.add_argument(
        "--homepage-port",
        "--homepage_port",
        dest="homepage_port",
        type=int,
        default=9010,
        help="web port for the homepage (0: disable)",
    )
    parser.add_argument(
        "--log-server-port",
        "--log_server_port",
        dest="log_server_port",
        type=int,
        default=9020,
        help="logger server port (0: disable)",
    )
    parser.add_argument(
        "--log-output-folder",
        "--log_output_folder",
        dest="log_output_folder",
        type=str,
        default="/var/log/bliss",
        help="logger output folder (default is /var/log/bliss)",
    )
    parser.add_argument(
        "--log-size",
        "--log_size",
        dest="log_size",
        type=float,
        default=10,
        help="Size of log rotating file in MegaBytes (default is 10)",
    )
    parser.add_argument(
        "--log-viewer-port",
        "--log_viewer_port",
        dest="log_viewer_port",
        type=int,
        default=9080,
        help="Web port for the log viewer socket (0: disable)",
    )
    parser.add_argument(
        "--redis-socket",
        "--redis_socket",
        dest="redis_socket",
        default="/tmp/redis.sock",
        help="Unix socket for redis (default to /tmp/redis.sock)",
    )
    parser.add_argument(
        "--log-level",
        "--log_level",
        default="INFO",
        type=str,
        choices=["DEBUG", "INFO", "WARN", "ERROR"],
        help="log level",
    )

    parser.add_argument(
        "--add-filter",
        dest="add_filter",
        default=[],
        action="append",
        help="address filter (i.e 127.0.0.1 only localhost will be advertised\n"
        "or 172.24.8.0/24 only advertised this sub-network ",
    )

    global _options
    _options = parser.parse_args(args)

    # Pimp my path
    _options.db_path = os.path.abspath(os.path.expanduser(_options.db_path))

    # Logging configuration
    configure_logging()

    with ExitStack() as context_stack:
        # For sub-processes
        env = dict(os.environ)

        # Start the Beacon server
        ctx = start_udp_server()
        udp_socket = context_stack.enter_context(ctx)
        ctx = start_tcp_server()
        tcp_socket = context_stack.enter_context(ctx)
        ctx = start_uds_server()
        uds_socket = context_stack.enter_context(ctx)
        beacon_port = tcp_socket.getsockname()[1]
        env["BEACON_HOST"] = "%s:%d" % ("localhost", beacon_port)

        # Logger server application
        if _options.log_server_port > 0:
            # Logserver executable
            args = [sys.executable]
            args += ["-m", "bliss.config.conductor.log_server"]

            # Arguments
            args += ["--port", str(_options.log_server_port)]
            if not _options.log_output_folder:
                log_folder = os.path.join(str(_options.db_path), "logs")
            else:
                log_folder = str(_options.log_output_folder)

            # Start log server when the log folder is writeable
            if os.access(log_folder, os.R_OK | os.W_OK | os.X_OK):
                args += ["--log-output-folder", log_folder]
                args += ["--log-size", str(_options.log_size)]
                beacon_logger.info(
                    "launching log_server on port: %s", _options.log_server_port
                )
                ctx = logged_subprocess(args, log_server_logger, env=env)
                context_stack.enter_context(ctx)

                # Logviewer Web application
                if not IS_WINDOWS and _options.log_viewer_port > 0:
                    args = ["tailon"]
                    args += ["-b", f"0.0.0.0:{_options.log_viewer_port}"]
                    args += [os.path.join(_options.log_output_folder, "*")]
                    ctx = logged_subprocess(args, log_viewer_logger, env=env)
                    context_stack.enter_context(ctx)
            else:
                log_server_logger.warning("Log path doesn't exist: %s", log_folder)
                log_server_logger.warning("Log server not started")

        # Start redis
        if IS_WINDOWS:
            redis_options = [
                "redis-server",
                _options.redis_conf,
                "--port",
                "%d" % _options.redis_port,
            ]
            redis_data_options = [
                "redis-server",
                _options.redis_data_conf,
                "--port",
                "%d" % _options.redis_data_port,
            ]
        else:
            redis_options = [
                "redis-server",
                _options.redis_conf,
                "--unixsocket",
                _options.redis_socket,
                "--unixsocketperm",
                "777",
                "--port",
                "%d" % _options.redis_port,
            ]
            redis_data_options = [
                "redis-server",
                _options.redis_data_conf,
                "--unixsocket",
                _options.redis_data_socket,
                "--unixsocketperm",
                "777",
                "--port",
                "%d" % _options.redis_data_port,
            ]

        ctx = logged_subprocess(redis_options, redis_logger, cwd=_options.db_path)
        context_stack.enter_context(ctx)

        if _options.redis_data_port > 0:
            ctx = logged_subprocess(
                redis_data_options, redis_data_logger, cwd=_options.db_path
            )
            context_stack.enter_context(ctx)

        # Start Tango database
        if _options.tango_port > 0:
            # Tango database executable
            args = [sys.executable]
            args += ["-m", "bliss.tango.servers.databaseds"]

            # Arguments
            args += ["-l", str(_options.tango_debug_level)]
            args += ["--db_access", "beacon"]
            args += ["--port", str(_options.tango_port)]
            args += ["2"]

            # Start tango database
            ctx = logged_subprocess(args, tango_logger, env=env)
            context_stack.enter_context(ctx)
            ctx = spawn_context(log_tangodb_started)
            context_stack.enter_context(ctx)

        # Start processing Beacon requests
        if uds_socket is not None:
            ctx = spawn_context(uds_server_main, uds_socket)
            context_stack.enter_context(ctx)
        if tcp_socket is not None:
            ctx = spawn_context(tcp_server_main, tcp_socket)
            context_stack.enter_context(ctx)
        if udp_socket is not None:
            ctx = spawn_context(udp_server_main, udp_socket, beacon_port)
            context_stack.enter_context(ctx)

        # Config web application
        if _options.webapp_port > 0:
            try:
                import flask
            except ImportError:
                web_logger.error(
                    "flask cannot be imported: web application won't be available"
                )
            else:
                from .web.configuration.config_app import web_app as config_app

                ensure_global_beacon_connection(beacon_port)
                ctx = start_webserver(config_app, _options.webapp_port)
                context_stack.enter_context(ctx)

        # Homepage web application
        if _options.homepage_port > 0:
            try:
                import flask
            except ImportError:
                web_logger.error(
                    "flask cannot be imported: web application won't be available"
                )
            else:
                from .web.homepage.homepage_app import web_app as homepage_app

                ensure_global_beacon_connection(beacon_port)
                homepage_app.config_port = _options.webapp_port
                homepage_app.log_port = _options.log_viewer_port
                ctx = start_webserver(homepage_app, _options.homepage_port)
                context_stack.enter_context(ctx)

        # Wait for exit signal
        wait()


if __name__ == "__main__":
    main()
