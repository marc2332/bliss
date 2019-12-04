#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


# original c++ server: /segfs/dserver/classes++/modbus/wago/src

import os
import sys
import time
import numpy

import tango
from tango import DebugIt, DevState, Attr, SpectrumAttr
from tango.server import Device, device_property, attribute, command

from bliss.comm.util import get_comm
from bliss.controllers.wago.wago import *
from bliss.common.utils import flatten
from bliss.config.static import get_config

# Device States Description
# ON : The motor powered on and is ready to move.
# MOVING : The motor is moving
# FAULT : The motor indicates a fault.
# ALARM : The motor indicates an alarm state for example has reached
# a limit switch.
# OFF : The power on the moror drive is switched off.
# DISABLE : The motor is in slave mode and disabled for normal use


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

access_conv_tab = {
    "r": tango.AttrWriteType.READ,
    "w": tango.AttrWriteType.WRITE,
    "rw": tango.AttrWriteType.READ_WRITE,
}

access_conv_tab_inv = dict((v, k) for k, v in access_conv_tab.items())


class Wago(Device):
    beacon_name = device_property(dtype=str, doc="Object name inside Beacon")
    iphost = device_property(dtype=str, default_value="", doc="ip address of Wago PLC")
    TCPTimeout = device_property(dtype=int, default_value=1000, doc="timeout in ms")
    config = device_property(
        dtype=tango.DevVarCharArray, default_value="", doc="I/O modules attached to PLC"
    )
    # modbusDevName = device_property(dtype=str, default_value="")  # its a link
    # __SubDevices = device_property(dtype=str, default_value="")  # its a link

    @DebugIt()
    def delete_device(self):
        self.wago.close()

    @DebugIt()
    def init_device(self, *args, **kwargs):
        super().init_device(*args, **kwargs)
        self.set_state(DevState.STANDBY)

        # configuration can be given through Beacon if beacon_name is provided
        # this will generate self.iphost and self.config
        if self.beacon_name:
            config = get_config()
            yml_config = config.get_config(self.beacon_name)
            if yml_config is None:
                raise RuntimeError(
                    f"Could not find a Beacon object with name {self.beacon_name}"
                )
            try:
                self.iphost = yml_config["modbustcp"]["url"]
            except KeyError:
                raise RuntimeError(
                    "modbustcp url should be given in Beacon configuration"
                )
            self.config = ModulesConfig.from_config_tree(yml_config).mapping_str

        self.TurnOn()  # automatic turn on to mimic C++ Device Server

    @command
    @DebugIt()
    def TurnOn(self):
        if not self.iphost:
            msg = "'iphost' property is not properly configured, could not connect to Wago"
            self.error_stream(msg)
            self.set_state(DevState.FAULT)
            raise RuntimeError(msg)
        conf = {"modbustcp": {"url": self.iphost, "timeout": self.TCPTimeout / 1000}}
        comm = get_comm(conf)

        try:
            self.set_state(DevState.INIT)
            self.debug_stream("Setting Wago modules mapping")
            modules_config = ModulesConfig(self.config, ignore_missing=True)
        except Exception as exc:
            self.error_stream(f"Exception on Wago setting modules mapping: {exc}")
            self.set_state(DevState.FAULT)
            return
        else:
            self.wago = WagoController(comm, modules_config)

        try:
            self.debug_stream("Trying to connect to Wago")
            self.wago.connect()
        except Exception as exc:
            self.error_stream(f"Exception on Wago connection: {exc}")
            self.set_state(DevState.FAULT)
            return
        else:
            self.debug_stream("Connected to Wago")
            self._attribute_factory()
            self.set_state(DevState.ON)

    @command
    @DebugIt()
    def TurnOff(self):
        if self.get_state() == DevState.ON:
            self.wago.close()
        self.set_state(DevState.OFF)

    def dev_status(self):
        """
        Tango Status informations
        """
        return self.wago.status()

    # --------
    # Commands
    # --------

    @command(
        doc_in="Return all channel keys",
        dtype_out=tango.DevVarShortArray,
        doc_out="mapped channels",
    )
    @DebugIt()
    def DevGetKeys(self):
        """
        Returns:
            list of int: logical channels mapped in the PLC
        """
        return list(self.wago.logical_keys.values())

    @command(
        dtype_in=tango.DevVarShortArray,
        doc_in="[0] : MSB=I/O LSB=Bit/Word (ex: 0x4957 = (`I`<<8)+`W`)\n"
        "[1] : offset in wago controller memory (ex: 0x16)",
        dtype_out=tango.DevVarShortArray,
        doc_out="[0] : logical device key\n" "[1] : logical channel",
    )
    @DebugIt()
    def DevHard2Log(self, array_in):
        """
        Given some information about the position of a register in Wago memory
        it returns the corresponding logical device key and logical channel

        Args:
           In:   DevVarShortArray array_in
                            [0] : first byte of short is 'I' for input 'O' for output,
                                  second byte is 'B' for bit value, 'W' for word value
                            [1] : offset in wago memory

        Returns:
           Out:  DevVarShortArray
                            [0] : logical device key
                            [1] : logical device channel
        """

        return self.wago.devhard2log(array_in)

    def _read_phys(self, tango_attribute):
        self.debug_stream(
            f"tango attribute {tango_attribute.get_data_format()} {tango_attribute.get_data_size()}"
        )
        name = tango_attribute.get_name()
        value = self.DevReadPhys(self.DevName2Key(name))
        if len(value) == 1:
            # single value
            tango_attribute.set_value(value[0])
        else:
            # array of values
            tango_attribute.set_value(value)

    def _write_phys(self, tango_attribute):
        self.debug_stream(
            f"tango attribute {tango_attribute.get_data_format()} {tango_attribute.get_data_size()}"
        )
        name = tango_attribute.get_name()
        value = tango_attribute.get_write_value()

        if isinstance(value, numpy.ndarray):
            value = list(value)
        value = self.DevWritePhys(flatten([self.DevName2Key(name)] + [value]))

    def _attribute_factory(self):
        """
        Creates dynamic attributes from device_property 'config'
        """
        attrs = {}

        for (
            key,
            (logical_device, physical_channel, physical_module, module_type, _, _),
        ) in self.wago.physical_mapping.items():
            if logical_device not in attrs:
                attrs[logical_device] = {}
                attrs[logical_device]["size"] = 1
            else:
                attrs[logical_device]["size"] += 1

        for (
            key,
            (logical_device, physical_channel, physical_module, module_type, _, _),
        ) in self.wago.physical_mapping.items():
            # find the type of attribute
            type_ = MODULES_CONFIG[module_type][READING_TYPE]

            # determination of variable type

            if type_ in ("thc", "fs10", "fs20", "fs4-20"):
                # temperature and Analog requires Float
                var_type = tango.DevDouble
            elif type_ in ("ssi24", "ssi32", "637"):
                # encoder requires Long
                var_type = tango.DevLong
            elif type_ in ("digital"):
                # digital requires boolean
                var_type = tango.DevBoolean
            else:
                raise NotImplementedError

            module_info = MODULES_CONFIG[module_type]

            # determination of read/write type
            if type_ in ("thc",):
                read_write = "r"
            elif type_ in ("thc", "fs10", "fs20", "fs4-20"):
                if module_info[ANA_IN] == module_info[N_CHANNELS]:
                    read_write = "r"
                elif module_info[ANA_OUT] == module_info[N_CHANNELS]:
                    read_write = "rw"
                else:
                    raise NotImplementedError
            elif type_ in ("ssi24", "ssi32", "637"):
                read_write = "r"
            elif type_ in ("digital"):
                if module_info[DIGI_IN] == module_info[N_CHANNELS]:
                    read_write = "r"
                elif module_info[DIGI_OUT] == module_info[N_CHANNELS]:
                    read_write = "rw"
                else:
                    raise NotImplementedError(
                        f"Digital I/O number of channels should be equal to total for {module_type}"
                    )
            else:
                raise NotImplementedError

            # define read and write methods
            _read_channel = lambda: None
            _write_channel = lambda: None

            if "r" in read_write:
                _read_channel = self._read_phys
            if "w" in read_write:
                _write_channel = self._write_phys

            attrs[logical_device]["type"] = var_type
            attrs[logical_device]["read_write"] = access_conv_tab[read_write]
            attrs[logical_device]["_read_channel"] = _read_channel
            attrs[logical_device]["_write_channel"] = _write_channel

        for attr, values in attrs.items():
            self.debug_stream(f"Factory for {attr} is {values}")
        # creating dynamic attributes
        for logical_device, d_ in attrs.items():
            try:
                if d_["size"] > 1:
                    # if it is an array attribute should be a spectrum
                    self.add_attribute(
                        SpectrumAttr(
                            logical_device, d_["type"], d_["read_write"], d_["size"]
                        ),
                        r_meth=d_["_read_channel"],
                        w_meth=d_["_write_channel"],
                    )
                else:
                    # else it is a scalar
                    self.add_attribute(
                        Attr(logical_device, d_["type"], d_["read_write"]),
                        r_meth=d_["_read_channel"],
                        w_meth=d_["_write_channel"],
                    )
            except Exception as exc:
                self.error_stream(
                    f"Exception {exc} on _attribute_factory for logical_device:{logical_device}, {d_}"
                )
                raise

    @command(
        dtype_in=tango.DevShort,
        doc_in="Numerical key",
        dtype_out=str,
        doc_out="Logical device name",
    )
    @DebugIt()
    def DevKey2Name(self, key):
        """
        From a key (channel enumeration) to the assigned text name

        Example:
            >>> DevKey2Name(3)
            b"gabsTf3"
        """
        return self.wago.devkey2name(key)

    @command(
        dtype_in=tango.DevVarShortArray,
        doc_in="[0] : logical device key\n[1] : logical channel",
        dtype_out=tango.DevVarShortArray,
        doc_out="[0] : offset in wago controller memory (ex: 0x16)\n"
        "[1] : MSB=I/O LSB=Bit/Word (ex: 0x4957 = (`I`<<8)+`W`)\n"
        "[2] : module reference (ex: 469)\n"
        "[3] : module number (1st is 0)\n"
        "[4] : physical channel of the module (ex: 1 for the 2nd)Logical device name\n",
    )
    @DebugIt()
    def DevLog2Hard(self, array_in):
        """
        Args:
            array_in (list): Logical Device Key (int), Logical Channel (int)

        Notes:
            Logical Channels is 0 if there is only one name associated to that Key

        Example Config:
            750-504, foh2ctrl, foh2ctrl, foh2ctrl, foh2ctrl
            750-408,2 foh2pos, sain2, foh2pos, sain4
            750-408, foh2pos, sain6, foh2pos, sain8

        >>> DevLog2Hard((0,2)) # gives the third channel with the name foh2ctrl

        >>> DevLog2Hard((1,0)) # gives the first channel with the name foh2pos

        >>> DevLog2Hard((2,0)) # gives the first (and only) channel with the name sain2

        >>> DevLog2Hard((2,1)) # will fail because there is only one channel with name sain2

        Output:
            [0] : offset in wago controller memory (ex: 0x16)
            [1] : MSB=I/O LSB=Bit/Word (ex: 0x4957 = ('I'<<8)+'W')
            [2] : module reference (ex: 469)
            [3] : module number (1st is 0)
            [4] : physical channel of the module (ex: 1 for the 2nd)

        """
        return self.wago.devlog2hard(array_in)

    @command(
        dtype_in=str,
        doc_in="Logical device name",
        dtype_out=tango.DevShort,
        doc_out="Numerical key",
    )
    @DebugIt()
    def DevName2Key(self, name):
        """
        Return the numerical keys associated to a logical name.

        Args:
            Arg(s) In:   DevString *vargin - logical device name

        Returns:
            Arg(s) Out:  DevShort *vargout - numerical key
            long *error - pointer to error code (in the case of failure)

        """
        return self.wago.devname2key(name)

    @command(
        dtype_in=tango.DevShort,
        doc_in="Logical device",
        dtype_out=tango.DevVarShortArray,
        doc_out="Array of bit values",
    )
    @DebugIt()
    def DevReadDigi(self, key):
        """
        """
        return self.DevReadNoCacheDigi(key)

    @command(
        dtype_in=tango.DevShort,
        doc_in="Logical device",
        dtype_out=tango.DevVarShortArray,
        doc_out="Array of bit values",
    )
    @DebugIt()
    def DevReadNoCacheDigi(self, key):
        """
        """
        value = self.wago.get(self.wago.devkey2name(key), convert_values=False)
        try:
            len(value)
        except TypeError:
            value = [value]
        return value

    @command(
        dtype_in=tango.DevShort,
        doc_in="Logical device index",
        dtype_out=tango.DevVarFloatArray,
        doc_out="Array of values",
    )
    @DebugIt()
    def DevReadNoCachePhys(self, key):
        """
        """
        value = self.wago.get(self.wago.devkey2name(key))
        try:
            len(value)
        except TypeError:
            value = [value]
        return value

    @command(
        dtype_in=tango.DevShort,
        doc_in="Logical device index",
        dtype_out=tango.DevVarFloatArray,
        doc_out="Array of values",
    )
    @DebugIt()
    def DevReadPhys(self, key):
        """
        """
        return self.DevReadNoCachePhys(key)

    @command(
        dtype_in=tango.DevVarShortArray,
        doc_in="""[0] : code of command to execute (ex: 0x010c for ILCK_RESET)
        [1] : 1st parameter
        [2] : 2nd parameter
        """,
        dtype_out=tango.DevVarShortArray,
        doc_out="""[0] : 1st argout or error code
        [1] : 2nd argout
        etc
        """,
    )
    @DebugIt()
    def DevWcComm(self, command, *params):

        """
        Executes a command in the wago controller programm.
        The communication is done using the ISG protocol.

        Args:
           In:   DevVarShortArray *vargin  - 
                            [0] : code of command to execute (ex: 0x010c for ILCK_RESET)
                            [1] : 1st parameter
                            [2] : 2nd parameter
                            etc

        Returns:
            Arg(s) Out:  DevVarShortArray *vargout - 
                            [0] : 1st argout or error code
                            [1] : 2nd argout 
                            etc

        """
        return self.wago.devwccomm(command, *params)

    @command(
        dtype_in=tango.DevVarShortArray,
        doc_in="Logical device key, than pairs of channel,value",
        dtype_out=tango.DevVoid,
        doc_out="nothing",
    )
    @DebugIt()
    def DevWriteDigi(self, array):
        self.DevWritePhys(array)

    @command(
        dtype_in=tango.DevVarFloatArray,
        doc_in="Logical device key, than pairs of channel,value",
        dtype_out=tango.DevVoid,
        doc_out="nothing",
    )
    @DebugIt()
    def DevWritePhys(self, array):
        """
        """
        self.wago.devwritephys(array)


def main(argv=sys.argv):

    from tango import GreenMode
    from tango.server import run

    run([Wago], green_mode=GreenMode.Gevent)


if __name__ == "__main__":
    main()
