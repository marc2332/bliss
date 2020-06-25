# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
import os
import enum
import socket
import numpy
import xdrlib
import struct
from collections import namedtuple
from ..sunrpc import Packer, Unpacker, UDPClient, TCPClient

MANAGER_SERVER_ID = 100
MANAGER_SERVER_VERSION = 4


class MgrPacker(Packer):
    def pack_config(self, args):
        self.pack_string(socket.gethostname().encode())
        self.pack_int(0)
        self.pack_int(0)


class MgrUnpacker(Unpacker):
    def unpack_config(self):
        # Message
        mgr_hostname = self.unpack_string()
        mgr_server_id = self.unpack_int()
        mgr_version = self.unpack_int()

        # DB
        db_hostanme = self.unpack_string()
        db_id = self.unpack_int()
        db_version = self.unpack_int()

        self.reset(b"")
        """
        self.unpack_int()         # STATUS
        self.unpack_int()         # ERROR
        self.unpack_int()         # SECURITY

        self.unpack_int()         # LENGHT
        """
        return db_hostanme, db_id, db_version


class MgrClient(UDPClient):
    def __init__(self, host):
        super().__init__(host.encode(), MANAGER_SERVER_ID, MANAGER_SERVER_VERSION)
        self.packer = MgrPacker()
        self.unpacker = MgrUnpacker(b"")

    def get_config(self):
        return self.make_call(
            1, None, self.packer.pack_config, self.unpacker.unpack_config
        )


class DBPacker(Packer):
    def pack_string_array(self, resources):
        self.pack_array(resources, self.pack_string)


ServerId = namedtuple("ServerId", "hostname id version error")

ServerInfo = namedtuple(
    "ServerInfo",
    "dev_type dev_exported dev_class"
    " server_name personal_name process_name"
    " server_version hostname pid program_num",
)


class DBUnpacker(Unpacker):
    def unpack_server_id(self):
        hostname = self.unpack_string()
        server_id = self.unpack_uint()
        server_version = self.unpack_uint()
        db_error = self.unpack_int()
        if db_error:
            raise RuntimeError(f"Taco error {db_error}")
        return ServerId(hostname, server_id, server_version, db_error)

    def unpack_server_info(self):
        device_type = self.unpack_uint()
        device_exported = self.unpack_int()
        device_class = self.unpack_string()
        server_name = self.unpack_string()
        personal_name = self.unpack_string()
        process_name = self.unpack_string()
        server_version = self.unpack_uint()
        hostname = self.unpack_string()
        pid = self.unpack_uint()
        program_num = self.unpack_uint()
        db_err = self.unpack_int()
        if db_err:
            raise RuntimeError(f"Taco error nb {db_err}")
        return ServerInfo(
            device_type,
            device_exported,
            device_class,
            server_name,
            personal_name,
            process_name,
            server_version,
            hostname,
            pid,
            program_num,
        )


class DbClient(TCPClient):
    def __init__(self, host):
        mgr = MgrClient(host)
        db_hostanme, db_id, db_version = mgr.get_config()
        super().__init__(db_hostanme, db_id, db_version)
        mgr.close()

        self.packer = DBPacker()
        self.unpacker = DBUnpacker(b"")

    def server_info(self, devicename):
        return self.make_call(
            27,
            devicename.encode(),
            self.packer.pack_string,
            self.unpacker.unpack_server_info,
        )

    def check(self, servername):
        return self.make_call(
            6,
            servername.encode(),
            self.packer.pack_string,
            self.unpacker.unpack_server_id,
        )

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


DEV_TYPE = enum.Enum(
    "DEV_TYPE",
    {
        "VOID": 0,
        "BOOLEAN": 1,
        "SHORT": 2,
        "LONG": 3,
        "FLOAT": 4,
        "DOUBLE": 5,
        "STRING": 6,
        "CHARARR": 9,
        "SHORTARR": 10,
        "LONGARR": 11,
        "FLOATARR": 12,
        "DOUBLEARR": 68,
    },
)

_Command = namedtuple("Command", "name num in_type out_type")


class _ClientPacker(Packer):
    def query(self, ds_id):
        self.pack_int(ds_id)
        self.pack_array([], self.pack_string)

    def ping(self, devicename):
        self.pack_string(devicename)
        self.pack_int(0)
        self.pack_int(0)
        self.pack_int(0)
        self.pack_array([], self.pack_string)

    # @xdrlib.raise_conversion_error

    def pack_dev_int(self, x):
        self.pack_uint(1)
        self.pack_int(x)

    pack_dev_short = pack_dev_int
    pack_dev_bool = pack_dev_int

    def pack_dev_float(self, x):
        self.pack_uint(1)
        self.pack_float(x)

    def pack_dev_double(self, x):
        self.pack_uint(1)
        self.pack_double(x)

    def pack_dev_unicode(self, x):
        self.pack_uint(1)
        self.pack_string(x.encode())

    def pack_dev_chararr(self, x):
        self.pack_uint(1)
        arr = numpy.array(x, dtype=numpy.int8)
        self.pack_uint(len(arr))
        self._Packer__buf.write(arr.tobytes())

    def pack_dev_shortarr(self, x):
        self.pack_uint(1)
        arr = numpy.array(x, dtype.numpy.int16)
        self.pack_uint(len(arr))
        self._Packer__buf.write(arr.tobytes())

    def pack_dev_intarr(self, x):
        self.pack_uint(1)
        arr = numpy.array(x, dtype.numpy.int32)
        self.pack_uint(len(arr))
        self._Packer__buf.write(arr.tobytes())

    def pack_dev_floatarr(self, x):
        self.pack_uint(1)
        arr = numpy.array(x, dtype.numpy.float32)
        self.pack_uint(len(arr))
        self._Packer__buf.write(arr.tobytes())

    def pack_dev_doublearr(self, x):
        self.pack_uint(1)
        arr = numpy.array(x, dtype.numpy.double)
        self.pack_uint(len(arr))
        self._Packer__buf.write(arr.tobytes())

    def pack_server_data(self, args):
        """
        struct _server_data {
 	DevLong 		ds_id;
	DevLong 		cmd;
	DevLong 		argin_type;
	DevLong 		argout_type;
	DevArgument 		argin;
 	DevLong 		access_right;
 	DevLong 		client_id;
	DevVarArgumentArray 	var_argument;
        };
        """
        ds_id, command, packer, argin = args
        self.pack_int(ds_id)
        self.pack_int(command.num)
        self.pack_int(command.in_type.value)
        self.pack_int(command.out_type.value)
        if packer is None:
            self.pack_string(b"")
        else:
            packer(argin)

        self.pack_int(0)  # access_right
        self.pack_int(0)  # client_id
        self.pack_list([], self.pack_string)


class _ClientUnPacker(Unpacker):
    def command_list(self):
        nb_commands = self.unpack_uint()
        cmds = list()
        for i in range(nb_commands):
            cmd_id = self.unpack_int()
            in_type = self.unpack_int()
            out_type = self.unpack_int()
            cmds.append((cmd_id, in_type, out_type))

        class_name = self.unpack_fstring(32)
        error = self.unpack_int()
        if error:
            raise RuntimeError(f"Taco error nb {error}")

        status = self.unpack_int()
        nb_arguments = self.unpack_int()
        commands = dict()
        for i, (cmd_id, in_type, out_type) in zip(range(nb_arguments), cmds):
            argument_type = self.unpack_int()
            argument_nb = self.unpack_int()
            cmd_name = self.unpack_string()
            try:
                commands[cmd_name.decode()] = _Command(
                    cmd_name.decode(), cmd_id, DEV_TYPE(in_type), DEV_TYPE(out_type)
                )
            except ValueError:
                raise ValueError(
                    "Taco one of those type are not yet managed"
                    f" {in_type} or {out_type}"
                )
        return commands

    def ping(self):
        server_name = self.unpack_fstring(80)
        ds_id = self.unpack_int()
        status = self.unpack_int()
        error = self.unpack_int()
        if error:
            raise RuntimeError(f"Taco error nb {error}")
        nb_arguments = self.unpack_uint()
        for i in range(nb_arguments):
            argument_type = self.unpack_int()
            argument = self.unpack_string()
        return ds_id

    def unpack_dev_int(self):
        nb = self.unpack_uint()
        return self.unpack_int()

    unpack_dev_short = unpack_dev_int
    unpack_dev_bool = unpack_dev_int

    def unpack_dev_float(self):
        nb = self.unpack_uint()
        return self.unpack_float()

    def unpack_dev_double(self):
        nb = self.unpack_uint()
        return self.unpack_float()

    def unpack_dev_unicode(self):
        nb = self.unpack_uint()
        val = self.unpack_string()
        return val.decode()

    def unpack_dev_chararr(self):
        nb = self.unpack_uint()
        nb_element = self.unpack_uint()
        i = self.get_position()
        j = i + nb_element
        self.set_position(j)
        buf = self.get_buffer()
        data = buf[i:j]
        if len(data) < nb_element:
            raise EOFError
        return numpy.frombuffer(data, dtype=numpy.int8)

    def unpack_dev_shortarr(self):
        nb = self.unpack_uint()
        nb_element = self.unpack_uint()
        i = self.get_position()
        j = i + nb_element * 2
        self.set_position(j)
        buf = self.get_buffer()
        data = buf[i:j]
        if len(data) < nb_element * 2:
            raise EOFError
        return numpy.frombuffer(data, dtype=numpy.int16)

    def unpack_dev_intarr(self):
        nb = self.unpack_uint()
        nb_element = self.unpack_uint()
        i = self.get_position()
        j = i + nb_element * 4
        self.set_position(j)
        buf = self.get_buffer()
        data = buf[i:j]
        if len(data) < nb_element * 4:
            raise EOFError
        return numpy.frombuffer(data, dtype=">i4")

    def unpack_dev_floatarr(self):
        nb = self.unpack_uint()
        nb_element = self.unpack_uint()
        i = self.get_position()
        j = i + nb_element * 4
        self.set_position(j)
        buf = self.get_buffer()
        data = buf[i:j]
        if len(data) < nb_element * 4:
            raise EOFError
        return numpy.frombuffer(data, dtype=">f4")

    def unpack_dev_doublearr(self):
        nb = self.unpack_uint()
        nb_element = self.unpack_uint()
        i = self.get_position()
        j = i + nb_element * 8
        self.set_position(j)
        buf = self.get_buffer()
        data = buf[i:j]
        if len(data) < nb_element * 8:
            raise EOFError
        return numpy.frombuffer(data, dtype=">d")

    def unpack_client_data_header(self):
        status = self.unpack_int()
        error = self.unpack_int()
        if error:
            raise RuntimeError(f"Taco error {error}")
        argout_type = self.unpack_int()
        return status, argout_type


class _Client(TCPClient):
    def __init__(self, host, serv_id, serv_version):
        super().__init__(host, serv_id, serv_version)

        self.packer = _ClientPacker()
        self.unpacker = _ClientUnPacker(b"")


def auto_connect(fn):
    def f(self, *args, **kwarg):
        self.connect()
        try:
            return fn(self, *args, **kwarg)
        except:
            if self._connection:
                cnx = self._connection
                self._connection = None
                self._commands = dict()
                cnx.close()
            raise

    return f


class Client:
    def __init__(self, devicename, db_host=None):
        """
        Taco client. If the device server is running,
        Taco Commands will be available as simple methods.

        devicename -- should be something like **id10/flex/1**
        db_host -- is the host where the Taco database run.
        if None, will use the environment variable **NETHOST**.
        """
        if db_host is None:
            try:
                db_host = os.environ["NETHOST"]
            except KeyError:
                raise RuntimeError(
                    "Specify **db_host** or fill" " NETHOST environement"
                )
        self._db_host = db_host
        self._devicename = devicename
        self._connection = None
        self._commands = dict()

    def __del__(self):
        if self._connection:
            self._connection.close()

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)

        self.connect()

        cmd = self._commands.get(name)
        if cmd is None:
            raise AttributeError(name)

        packer_func = self._get_packer(cmd.in_type)
        unpacker_func = self._get_unpacker(cmd.out_type)
        cnx = self._connection

        def unpack():
            """
            struct _client_data {
  	    DevLong 		status;
	    DevLong 		error;
	    DevLong 		argout_type;
	    DevArgument 		argout;
	    DevVarArgumentArray 	var_argument;
            };
            """
            status, argout_type = cnx.unpacker.unpack_client_data_header()
            if argout_type != cmd.out_type.value:
                raise RuntimeError(
                    f"Taco error argout rx {argout_type} != {cmd.out_type}"
                )
            if unpacker_func:
                argout = unpacker_func()
            else:
                argout = None
                cnx.unpacker.unpack_string()

            var_argument_nb = cnx.unpacker.unpack_uint()
            for i in range(var_argument_nb):
                lenght = cnx.unpacker.unpack_uint()
                arg_type = cnx.unpacker.unpack_int()
                argument = cnx.unpacker.unpack_string()
            return argout

        def f(arg=None):
            try:
                return cnx.make_call(
                    3,
                    (self._ds_id, cmd, packer_func, arg),
                    cnx.packer.pack_server_data,
                    unpack,
                )
            except:
                self.close()
                raise

        return f

    def __dir__(self):
        try:
            self.connect()
        except RuntimeError:
            pass
        return ["connect", "close", "ping", "get_commands"] + list(self._commands)

    def _get_packer(self, dev_type):
        dev = {
            DEV_TYPE.VOID: None,
            DEV_TYPE.BOOLEAN: self._connection.packer.pack_dev_bool,
            DEV_TYPE.SHORT: self._connection.packer.pack_dev_short,
            DEV_TYPE.LONG: self._connection.packer.pack_dev_int,
            DEV_TYPE.FLOAT: self._connection.packer.pack_dev_float,
            DEV_TYPE.DOUBLE: self._connection.packer.pack_dev_double,
            DEV_TYPE.STRING: self._connection.packer.pack_dev_unicode,
            DEV_TYPE.CHARARR: self._connection.packer.pack_dev_chararr,
            DEV_TYPE.SHORTARR: self._connection.packer.pack_dev_shortarr,
            DEV_TYPE.LONGARR: self._connection.packer.pack_dev_intarr,
            DEV_TYPE.FLOATARR: self._connection.packer.pack_dev_floatarr,
            DEV_TYPE.DOUBLEARR: self._connection.packer.pack_dev_doublearr,
        }
        try:
            return dev[dev_type]
        except KeyError:
            raise KeyError(f"Not yet manage {dev_type}")

    def _get_unpacker(self, dev_type):
        dev = {
            DEV_TYPE.VOID: None,
            DEV_TYPE.BOOLEAN: self._connection.unpacker.unpack_dev_bool,
            DEV_TYPE.SHORT: self._connection.unpacker.unpack_dev_short,
            DEV_TYPE.LONG: self._connection.unpacker.unpack_dev_int,
            DEV_TYPE.FLOAT: self._connection.unpacker.unpack_dev_float,
            DEV_TYPE.DOUBLE: self._connection.unpacker.unpack_dev_double,
            DEV_TYPE.STRING: self._connection.unpacker.unpack_dev_unicode,
            DEV_TYPE.CHARARR: self._connection.unpacker.unpack_dev_chararr,
            DEV_TYPE.SHORTARR: self._connection.unpacker.unpack_dev_shortarr,
            DEV_TYPE.LONGARR: self._connection.unpacker.unpack_dev_intarr,
            DEV_TYPE.FLOATARR: self._connection.unpacker.unpack_dev_floatarr,
            DEV_TYPE.DOUBLEARR: self._connection.unpacker.unpack_dev_doublearr,
        }
        try:
            return dev[dev_type]
        except KeyError:
            raise KeyError(f"Not yet manage {dev_type}")

    def connect(self):
        """
        Establish the connection to the server
        """
        if self._connection is None:
            with DbClient(self._db_host) as taco_db:
                server_info = taco_db.server_info(self._devicename)
            self._connection = _Client(
                server_info.hostname,
                server_info.program_num,
                server_info.server_version,
            )
            self._server_info = server_info
            self._ds_id = self.ping()
            self._commands = self.get_commands()

    def close(self):
        """
        close the connection with the server
        """
        if self._connection:
            cnx = self._connection
            self._connection = None
            cnx.close()

    @auto_connect
    def ping(self):
        """
        Simple ping to check is the server is alive
        """
        return self._connection.make_call(
            1,
            self._devicename.encode(),
            self._connection.packer.ping,
            self._connection.unpacker.ping,
        )

    @auto_connect
    def get_commands(self):
        """
        Return the all server's commands 
        """
        return self._connection.make_call(
            5,
            self._ds_id,
            self._connection.packer.query,
            self._connection.unpacker.command_list,
        )
