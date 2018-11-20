# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""TCP communication module (:class:`~bliss.comm.tcp.Tcp`, \
:class:`~bliss.comm.tcp.Socket` and :class:`~bliss.comm.tcp.Command`)
"""

__all__ = ["Tcp", "Socket", "Command"]

import re
import errno
import gevent
from gevent import socket, event, queue, lock
import time
import logging
import weakref
from bliss.common.event import send

from .exceptions import CommunicationError, CommunicationTimeout
from ..common.greenlet_utils import KillMask
from .util import HexMsg

from bliss.common.cleanup import error_cleanup, capture_exceptions


class SocketTimeout(CommunicationTimeout):
    """Socket timeout error"""


# Decorator function for read/write functions.
# Performs reading of data via "_raw_read_task" in self.connect()
def try_connect_socket(fu):
    def rfunc(self, *args, **kwarg):
        write_func = fu.func_name.startswith("write")
        prev_timeout = kwarg.get("timeout", None)

        if (not self._connected) and ((not self._data) or write_func):
            # connects if :
            #   not already connected
            #   AND
            #   "write"-function   OR   no data are present.
            self.connect(timeout=prev_timeout)

        if not self._connected:
            kwarg.update({"timeout": 0.})
            try:
                with KillMask():
                    return fu(self, *args, **kwarg)
            except SocketTimeout:
                self.connect(timeout=prev_timeout)
                kwarg.update({"timeout": prev_timeout})

        with KillMask():
            try:
                return fu(self, *args, **kwarg)
            except gevent.Timeout:
                raise
            except:
                try:
                    self.close()
                except:
                    pass
                raise

    return rfunc


class BaseSocket:
    """Raw socket class. Provides raw socket access.
    Consider using :class:`Tcp`."""

    def __init__(
        self,
        host=None,
        port=None,
        eol="\n",  # end of line for each rx message
        timeout=5.,  # default timeout for read write
    ):
        self._host = host
        self._port = port
        self._fd = None
        self._timeout = timeout
        self._connected = False
        self._eol = eol
        self._data = ""
        self._event = event.Event()
        self._raw_read_task = None
        self._lock = lock.RLock()
        self._logger = logging.getLogger(str(self))
        self._debug = self._logger.debug

    def __del__(self):
        self.close()

    def __str__(self):
        return "{0}({1}:{2})".format(self.__class__.__name__, self._host, self._port)

    @property
    def lock(self):
        return self._lock

    def open(self):
        if not self._connected:
            self.connect()

    def connect(self, host=None, port=None, timeout=None):
        local_host = host or self._host
        local_port = port or self._port
        local_timeout = timeout if timeout is not None else self._timeout
        self._debug("connect(host=%s,port=%d)", local_host, local_port)

        self.close()

        self._host = local_host
        self._port = local_port

        with self._lock:
            if self._connected:
                return True
            err_message = "connection timeout on socket(%s, %d)" % (
                self._host,
                self._port,
            )
            with gevent.Timeout(local_timeout, SocketTimeout(err_message)):
                self._fd = self._connect(local_host, local_port)
            self._connected = True

        self._raw_read_task = gevent.spawn(
            self._raw_read, weakref.proxy(self), self._fd
        )
        send(self, "connect", True)

        return True

    def _connect(self, host, port):
        """
        This method return a socket for a new connection.
        Should be implemented in inherited classes
        """
        raise NotImplementedError

    def close(self):
        if self._connected:
            try:
                self._shutdown()
            except:  # probably closed one the server side
                pass
            try:
                self._fd.close()
            finally:
                if self._raw_read_task:
                    self._raw_read_task.kill()
                    self._raw_read_task = None
                self._data = ""
                self._connected = False
                self._fd = None
                send(self, "connect", False)

    def _shutdown(self):
        """
        This method disconnect properly the socket,
        not always needed but could be implemented into inherited classes
        """
        pass

    @try_connect_socket
    def raw_read(self, maxsize=None, timeout=None):
        timeout_errmsg = "timeout on socket(%s, %d)" % (self._host, self._port)
        with gevent.Timeout(timeout or self._timeout, SocketTimeout(timeout_errmsg)):
            while not self._data:
                self._event.wait()
                self._event.clear()
                if not self._connected:
                    raise socket.error(errno.EPIPE, "Broken pipe")
        if maxsize:
            msg = self._data[:maxsize]
            self._data = self._data[maxsize:]
        else:
            msg = self._data
            self._data = ""
        return msg

    @try_connect_socket
    def read(self, size=1, timeout=None):
        timeout_errmsg = "timeout on socket(%s, %d)" % (self._host, self._port)
        with capture_exceptions() as capture:
            with gevent.Timeout(
                timeout or self._timeout, SocketTimeout(timeout_errmsg)
            ):
                while len(self._data) < size:
                    with capture():
                        self._event.wait()
                        self._event.clear()
                    if capture.failed:
                        other_exc = [
                            x
                            for _, x, _ in capture.failed
                            if not isinstance(x, gevent.Timeout)
                        ]
                        if not other_exc:
                            if len(self._data) < size:
                                continue
                        else:
                            break
                    if not self._connected:
                        raise socket.error(errno.EPIPE, "Broken pipe")
            msg = self._data[:size]
            self._data = self._data[size:]
            return msg

    @try_connect_socket
    def readline(self, eol=None, timeout=None):
        return self._readline(eol, timeout)

    def _readline(self, eol=None, timeout=None):
        timeout_errmsg = "timeout on socket(%s, %d)" % (self._host, self._port)
        with capture_exceptions() as capture:
            with gevent.Timeout(
                timeout or self._timeout, SocketTimeout(timeout_errmsg)
            ):
                local_eol = eol or self._eol
                eol_pos = self._data.find(local_eol)
                while eol_pos == -1:
                    with capture():
                        self._event.wait()
                        self._event.clear()

                    eol_pos = self._data.find(local_eol)

                    if capture.failed:
                        other_exc = [
                            x
                            for _, x, _ in capture.failed
                            if not isinstance(x, gevent.Timeout)
                        ]
                        if not other_exc:
                            if eol_pos == -1:
                                continue
                        else:
                            break
                    if not self._connected:
                        raise socket.error(errno.EPIPE, "Broken pipe")

            msg = self._data[:eol_pos]
            self._data = self._data[eol_pos + len(local_eol) :]
            return msg

    @try_connect_socket
    def write(self, msg, timeout=None):
        with self._lock:
            self._sendall(msg)

    def _write(self, msg, timeout=None):
        self._sendall(msg)

    @try_connect_socket
    def write_read(self, msg, write_synchro=None, size=1, timeout=None):
        with self._lock:
            self._sendall(msg)
            if write_synchro:
                write_synchro.notify()
            return self.read(size=size, timeout=timeout)

    @try_connect_socket
    def write_readline(self, msg, write_synchro=None, eol=None, timeout=None):
        with self._lock:
            with gevent.Timeout(
                timeout or self._timeout, SocketTimeout("write_readline timed out")
            ):
                self._sendall(msg)
                if write_synchro:
                    write_synchro.notify()
                return self.readline(eol=eol, timeout=timeout)

    @try_connect_socket
    def write_readlines(
        self, msg, nb_lines, write_synchro=None, eol=None, timeout=None
    ):
        with self._lock:
            with gevent.Timeout(
                timeout or self._timeout,
                SocketTimeout("write_readlines(%r, %d) timed out" % (msg, nb_lines)),
            ):
                self._sendall(msg)
                if write_synchro:
                    write_synchro.notify()

                start_time = time.time()
                str_list = []
                for ii in range(nb_lines):
                    str_list.append(self.readline(eol=eol, timeout=timeout))

                    # Reduces timeout by duration of previous readline command.
                    if timeout:
                        timeout = timeout - (time.time() - start_time)
                        if timeout < 0:
                            timeout = 0

                    start_time = time.time()

                return str_list

    def flush(self):
        self._data = ""

    def _sendall(self, data):
        raise NotImplementedError

    @staticmethod
    def _raw_read(sock, fd):
        raise NotImplementedError


class Socket(BaseSocket):
    def _connect(self, host, port):
        fd = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        fd.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        fd.setsockopt(socket.SOL_IP, socket.IP_TOS, 0x10)
        fd.connect((host, port))
        return fd

    def _shutdown(self):
        self._fd.shutdown(socket.SHUT_RDWR)

    def _sendall(self, data):
        self._debug("Tx: %r %r", data, HexMsg(data))
        return self._fd.sendall(data)

    @staticmethod
    def _raw_read(sock, fd):
        try:
            while 1:
                raw_data = fd.recv(16 * 1024)
                sock._debug("Rx: %r %r", raw_data, HexMsg(raw_data))
                if raw_data:
                    sock._data += raw_data
                    sock._event.set()
                else:
                    break
        except:
            pass
        finally:
            try:
                sock._raw_read_task = None
                sock.close()
            except socket.error:
                pass
            except ReferenceError:
                pass
            finally:
                try:
                    sock._event.set()
                except ReferenceError:
                    pass


class CommandTimeout(CommunicationTimeout):
    """Command timeout error"""


def try_connect_command(fu):
    def rfunc(self, *args, **kwarg):
        timeout = kwarg.get("timeout")
        if not self._connected:
            self.connect(timeout=timeout)

        if not self._connected:
            prev_timeout = kwarg.get("timeout", None)
            kwarg.update({"timeout": 0.})
            try:
                with KillMask():
                    return fu(self, *args, **kwarg)
            except CommandTimeout:
                self.connect(timeout=timeout)
                kwarg.update({"timeout": prev_timeout})
        with KillMask():
            try:
                return fu(self, *args, **kwarg)
            except gevent.Timeout:
                raise
            except:
                try:
                    self.close()
                except:
                    pass
                raise

    return rfunc


class Command:
    """Raw command class. Provides command like API through sockets.
    Consider using :class:`Tcp` with url starting with  *command://* instead."""

    class Transaction:
        def __init__(self, socket, transaction, clear_transaction=True):
            self.__socket = socket
            self.__transaction = transaction
            self.__clear_transaction = clear_transaction
            self.data = ""

        def __enter__(self):
            return self

        def __exit__(self, *args):
            with self.__socket._lock:
                try:
                    trans_index = self.__socket._transaction_list.index(
                        self.__transaction
                    )
                except ValueError:  # not in list weird
                    return

                if trans_index is 0:
                    while not self.__transaction.empty():
                        read_value = self.__transaction.get()
                        if not isinstance(read_value, socket.error):
                            self.data += read_value

                    if (
                        self.__clear_transaction
                        and len(self.__socket._transaction_list) > 1
                    ):
                        self.__socket._transaction_list[1].put(self.data)
                    else:
                        self.__transaction.put(self.data)

                if self.__clear_transaction:
                    self.__socket._transaction_list.pop(trans_index)

    def __init__(
        self,
        host,
        port,
        eol="\n",  # end of line for each rx message
        timeout=5.,  # default timeout for read write
    ):
        self._host = host
        self._port = port
        self._fd = None
        self._timeout = timeout
        self._connected = False
        self._eol = eol
        self._event = event.Event()
        self._raw_read_task = None
        self._transaction_list = []
        self._lock = lock.RLock()
        self._logger = logging.getLogger(self.__class__.__name__)
        self._debug = self._logger.debug

    def __del__(self):
        self.close()

    @property
    def lock(self):
        return self._lock

    def open(self):
        if not self._connected:
            self.connect()

    def connect(self, host=None, port=None, timeout=None):
        local_host = host or self._host
        local_port = port or self._port
        local_timeout = timeout if timeout is not None else self._timeout
        if self._connected:
            prev_ip_host, prev_port = s.getpeername()
            try:
                prev_name, aliaslist, _ = socket.gethostbyaddr(prev_ip_host)
            except socket.herror:
                prev_name = prev_ip_host

            fqdn_host = socket.getfqdn(host)
            if port != prev_port or (fqdn_host != prev_name and name not in aliaslist):
                self.close()

        with self._lock:
            if self._connected:
                return True

            self._fd = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            err_msg = "timeout on command(%s, %d)" % (local_host, local_port)
            with gevent.Timeout(local_timeout, CommandTimeout(err_msg)):
                self._fd.connect((local_host, local_port))
            self._fd.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self._fd.setsockopt(socket.SOL_IP, socket.IP_TOS, 0x10)
            self._host = local_host
            self._port = local_port
            self._raw_read_task = gevent.spawn(
                self._raw_read, weakref.proxy(self), self._fd
            )
            self._connected = True

        send(self, "connect", True)
        return True

    def close(self):
        with self._lock:
            if self._connected:
                try:
                    self._fd.shutdown(socket.SHUT_RDWR)
                except:  # probably closed one the server side
                    pass
                try:
                    self._fd.close()
                finally:
                    if self._raw_read_task:
                        self._raw_read_task.kill()
                        self._raw_read_task = None
                    self._transaction_list = []
                    send(self, "connect", False)

    @try_connect_command
    def _read(self, transaction, size=1, timeout=None, clear_transaction=True):
        with Command.Transaction(self, transaction, clear_transaction) as ctx:
            timeout_errmsg = "timeout on socket(%s, %d)" % (self._host, self._port)
            with gevent.Timeout(
                timeout or self._timeout, CommandTimeout(timeout_errmsg)
            ):
                ctx.data = ""
                while len(ctx.data) < size:
                    read_value = transaction.get()
                    if isinstance(read_value, socket.error):
                        raise read_value
                    ctx.data += read_value

                msg = ctx.data[:size]
                ctx.data = ctx.data[size:]
        return msg

    @try_connect_command
    def _readline(self, transaction, eol=None, timeout=None, clear_transaction=True):
        with Command.Transaction(self, transaction, clear_transaction) as ctx:
            with gevent.Timeout(
                timeout or self._timeout,
                CommandTimeout("timeout on socket(%s, %d)" % (self._host, self._port)),
            ):
                local_eol = eol or self._eol
                ctx.data = ""
                eol_pos = -1
                while eol_pos == -1:
                    read_value = transaction.get()
                    if isinstance(read_value, socket.error):
                        raise read_value
                    ctx.data += read_value
                    eol_pos = ctx.data.find(local_eol)

                msg = ctx.data[:eol_pos]
                ctx.data = ctx.data[eol_pos + len(local_eol) :]

        return msg

    @try_connect_command
    def _write(self, msg, timeout=None, transaction=None, create_transaction=True):
        with self._lock:
            if transaction is None and create_transaction:
                transaction = self.new_transaction()
            self._debug("Tx: %r %r", msg, HexMsg(msg))
            with error_cleanup(self._pop_transaction, transaction=transaction):
                self._fd.sendall(msg)
        return transaction

    def write(self, msg, timeout=None):
        return self._write(msg, timeout=timeout, create_transaction=False)

    @try_connect_command
    def write_read(self, msg, write_synchro=None, size=1, timeout=None):
        transaction = self._write(msg)
        if write_synchro:
            write_synchro.notify()
        return self._read(size=size, timeout=timeout, transaction=transaction)

    @try_connect_command
    def write_readline(self, msg, write_synchro=None, eol=None, timeout=None):
        with gevent.Timeout(
            timeout or self._timeout, CommandTimeout("write_readline timed out")
        ):
            transaction = self._write(msg)
            if write_synchro:
                write_synchro.notify()
            return self._readline(eol=eol, timeout=timeout, transaction=transaction)

    @try_connect_command
    def write_readlines(
        self, msg, nb_lines, write_synchro=None, eol=None, timeout=None
    ):
        with gevent.Timeout(
            timeout or self._timeout,
            CommandTimeout("write_readlines(%s,%d) timed out" % (msg, nb_lines)),
        ):
            transaction = self._write(msg)

            if write_synchro:
                write_synchro.notify()

            start_time = time.time()
            str_list = []
            for ii in range(nb_lines):
                clear_transaction = ii == nb_lines - 1
                str_list.append(
                    self._readline(
                        eol=eol,
                        timeout=timeout,
                        transaction=transaction,
                        clear_transaction=clear_transaction,
                    )
                )

                # Reduces timeout by duration of previous readline command.
                if timeout:
                    timeout = timeout - (time.time() - start_time)
                    if timeout < 0:
                        timeout = 0

                start_time = time.time()
            return str_list

    @staticmethod
    def _raw_read(command, fd):
        try:
            while 1:
                raw_data = fd.recv(16 * 1024)
                with command._lock:
                    if raw_data and command._transaction_list:
                        command._transaction_list[0].put(raw_data)
                    else:
                        break
        except:
            pass
        finally:
            try:
                command._raw_read_task = None
                transaction_list = command._transaction_list
                command.close()
            except socket.error:
                pass
            except ReferenceError:
                pass
            try:
                # inform all pending transaction that the socket is closed
                with command._lock:
                    for trans in transaction_list:
                        trans.put(socket.error(errno.EPIPE, "Broken pipe"))
            except ReferenceError:
                pass

    def new_transaction(self):
        data_queue = queue.Queue()
        self._transaction_list.append(data_queue)
        return data_queue

    def _pop_transaction(self, transaction=None):
        index = self._transaction_list.index(transaction)
        self._transaction_list.pop(index)


class TcpError(CommunicationError):
    """TCP communication error"""


class Tcp(object):
    """TCP object. You can access raw socket layer (default) or with a command
    like API (prefix url with *command://* scheme). Example::

        from bliss.comm.tcp import Tcp

        cmd = Tcp('iceid001.esrf.fr:5000')
    """

    SOCKET, COMMAND = range(2)

    def __new__(cls, url=None, **keys):
        if url.lower().startswith("command://"):
            parse = re.compile("^(command://)([^:/]+?):([0-9]+)$")
            match = parse.match(url)
            if match is None:
                raise TcpError("Command: url is not valid (%s)" % url)
            host, port = match.group(2), int(match.group(3))
            return Command(host, port, **keys)
        else:
            parse = re.compile("^(socket://)?([^:/]+?):([0-9]+)$")
            match = parse.match(url)
            if match is None:
                raise TcpError("Socket: url is not valid (%s)" % url)
            host, port = match.group(2), int(match.group(3))
            return Socket(host, port, **keys)
