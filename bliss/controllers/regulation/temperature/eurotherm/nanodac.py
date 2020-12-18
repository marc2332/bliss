# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
    This class is the main controller of Eurotherm nanodac

    yml configuration example:

    - class: Nanodac
      plugin: regulation
      module: temperature.eurotherm.nanodac
      controller_ip: 160.103.30.184
      name: nanodac
      inputs:
        - name: nanodac_in1
          channel: 1
      outputs:
        - name: nanodac_out1
          channel: 1
      ctrl_loops:
        - name: nanodac_loop1
          channel: 1
          input: $nanodac_in1
          output: $nanodac_out1
"""

import gevent
import enum
from bliss.controllers.regulator import Controller
from bliss.comm import modbus
from bliss.common.logtools import log_debug_data, log_info
from .nanodac_mapping import get_nanodac_cmds
from bliss.common.utils import autocomplete_property, split_keys_to_tree


class PropertiesMenuNode:
    """ Takes a dict and add as many properties as keys in 'properties_dict'.
        If a dict value is a PropertiesMenuNode, the associated property is an autocomplete_property,
        returning that node.
        If the dict value is not a PropertiesMenuNode, a tuple of callbacks is expected to create
        the associated standard property.
        
        ex: if 'Loop.Ch1.Main.PV' should be a get/set property
            properties_dict['Loop'] = node1 with the 'Ch1' property returning the node node2
            properties_dict['Ch1']  = node2 with the 'Main' property returning the node node3
            properties_dict['Main'] = node3 with the 'PV' property
            properties_dict['PV']   = the (getter, setter, ...) associated to the 'node3.PV' property
    """

    # Meta code to add properties to a class from a dict
    def __new__(cls, properties_dict):

        cls = type(cls.__name__, (cls,), {})

        for key, value in properties_dict.items():

            try:
                int(key)
                key = f"Ch{key}"  # to avoid numbers as property name
            except ValueError:
                pass

            if isinstance(value, PropertiesMenuNode):

                def get_value(self, value=value):
                    return value

                setattr(cls, key, autocomplete_property(get_value))
            else:
                setattr(
                    cls, key, property(*value)
                )  # value as (getter_cb, setter_cb, ...)

        return object.__new__(cls)

    def __init__(self, properties_dict):
        pass


class nanodac:

    _CMDS_MAPPING = get_nanodac_cmds()

    """
        Nanodac hardware controller interface
    """

    VALID_INPUT_CHANNELS = enum.IntEnum("VALID_INPUT_CHANNELS", "ch1 ch2 ch3 ch4")

    VALID_LOOP_CHANNELS = enum.IntEnum("VALID_LOOP_CHANNELS", "ch1 ch2")

    # Possible manual choices : (float32|uint8|bool|time_t|string_t|int32|int16|eint32)
    _REGISTER_DTYPES = {
        "1B": ["uint8", "bool", "string_t", "time_t"],
        "2B": ["int16"],
        "4B": ["float32", "eint32", "int32"],
    }

    def __init__(self, host_ip):
        self.host_ip = host_ip

        self._load_cmds()
        self._init_com()

    def _recursive_build_of_cmds_tree(self, tree, exclude_key):
        """ Takes a tree (nested dicts) and build a tree of PropertiesMenuNodes.
            A PropertiesMenuNode has properties to access its sub-nodes.
            If the value (tree[k]) is a dict, it is introspected until it founds
            the leaf value (i.e not a dict or a dict with the 'exclude_key' key).
        """
        tmp = {}
        for k, v in list(tree.items()):
            if isinstance(v, dict) and (exclude_key not in v):
                # introspect nested dict
                tmp[k] = self._recursive_build_of_cmds_tree(
                    v, exclude_key
                )  # make value a node
            else:
                # make this key a PropertiesMenuNode property giving getter and setter
                def getter_cb(obj, cmd_info=v):
                    return self._send_cmd(cmd_info, None)

                def setter_cb(obj, value, cmd_info=v):
                    return self._send_cmd(cmd_info, value)

                tmp[k] = (getter_cb, setter_cb)

        return PropertiesMenuNode(tmp)

    def _load_cmds(self):
        """ Creates a PropertiesMenuNode tree to access all mapped commands as properties via self.cmds """
        tree = split_keys_to_tree(self._CMDS_MAPPING, "_")
        self.cmds = self._recursive_build_of_cmds_tree(tree, "registerHex")

    def _init_com(self):
        self.com = modbus.ModbusTcp(self.host_ip)

    def _get_register(self, cmd_info):
        reg = int(cmd_info["registerDec"])
        if reg < 0x4000:
            reg = 0x8000 + reg * 2
        return reg

    def _cmd_read(self, cmd_info):
        reg = self._get_register(cmd_info)
        dtype = cmd_info["type"]
        if dtype in self._REGISTER_DTYPES["4B"]:
            return self.com.read_holding_registers(reg, "f")
        elif dtype in self._REGISTER_DTYPES["1B"]:
            # Guessing here for 'string_t' type
            return self.com.read_holding_registers(reg, "h")
        elif dtype in self._REGISTER_DTYPES["2B"]:
            return self.com.read_holding_registers(reg, "h")
        else:
            raise ValueError(f"unknown parameter type '{dtype}' ")

    def _cmd_write(self, cmd_info, value):
        reg = self._get_register(cmd_info)
        dtype = cmd_info["type"]
        if dtype in self._REGISTER_DTYPES["4B"]:
            return self.com.write_float(reg, value)
        elif dtype in self._REGISTER_DTYPES["1B"]:
            return self.com.write_register(reg, "H", value)
        elif dtype in self._REGISTER_DTYPES["2B"]:
            raise ValueError(
                f"cannot write on Nanodac a parameter with type '{dtype}' (read only?)"
            )
        else:
            raise ValueError(f"unknown parameter type '{dtype}' ")

    def _send_cmd(self, cmd_info, value):
        """ Send a command based on cmd_info.
            If value is None it calls the read command.
            Else it calls the write command.

            cmd_info is a dict describing the command.
            ex: {
                "registerHex": "0200",
                "resolution": "1dp",
                "description": "Process variable",
                "registerDec": "512",
                "type": "float32",
                }
        """
        # print(f"_send_cmd: value={value}, cmd_info={cmd_info}")
        log_debug_data(self, "_send_cmd", cmd_info, value)

        if value is None:
            return self._cmd_read(cmd_info)
        else:
            return self._cmd_write(cmd_info, value)

    def send_cmd(self, cmd, value=None):
        cmd_info = self._CMDS_MAPPING[cmd]
        return self._send_cmd(cmd_info, value)

    def get_auto_tune(self, loop_channel):
        # self.Loop_1_Tune_AutotuneEnable
        cmd = f"Loop_{int(loop_channel)}_Tune_AutotuneEnable"
        return self.send_cmd(cmd)

    def set_auto_tune(self, loop_channel, enable):
        # self.Loop_1_Tune_AutotuneEnable = 1
        cmd = f"Loop_{int(loop_channel)}_Tune_AutotuneEnable"
        self.send_cmd(cmd, int(enable))

    def auto_tune(self, loop_channel):
        rate = self.get_ramprate(loop_channel)
        self.set_ramprate(loop_channel, 0)
        self.set_auto_tune(loop_channel, 1)

        while self.get_auto_tune(loop_channel) == 1:
            gevent.sleep(1)

        self.set_ramprate(loop_channel, rate)

    def is_manual(self, loop_channel):
        cmd = f"Loop_{int(loop_channel)}_Main_AutoMan"
        return bool(self.send_cmd(cmd))

    def is_auto(self, loop_channel):
        return not self.is_manual(loop_channel)

    def set_auto(self, loop_channel, enable):

        cmd = f"Loop_{int(loop_channel)}_Main_AutoMan"

        if enable:
            # self.Loop_1_Main_AutoMan = 0
            self.send_cmd(cmd, 0)
        else:
            # self.Loop_1_Main_AutoMan = 1
            self.send_cmd(cmd, 1)

    def loop_is_working(self, loop_channel, input_channel):

        # self.Channel_1_Main_Status
        cmd = f"Channel_{int(input_channel)}_Main_Status"
        status = self.send_cmd(cmd)

        if status == 0 and self.is_auto(loop_channel):
            return True
        else:
            return False

    def get_setpoint(self, loop_channel):
        # self.Loop_1_Main_TargetSP
        cmd = f"Loop_{int(loop_channel)}_Main_TargetSP"
        return self.send_cmd(cmd)

    def set_setpoint(self, loop_channel, value):
        # self.Loop_1_Main_TargetSP = float(value)
        cmd = f"Loop_{int(loop_channel)}_Main_TargetSP"
        self.send_cmd(cmd, float(value))

    def get_working_setpoint(self, loop_channel):
        # self.Loop_1_Main_WorkingSP
        cmd = f"Loop_{int(loop_channel)}_Main_WorkingSP"
        return self.send_cmd(cmd)

    def read_input(self, input_channel):
        # self.Channel_1_Main_PV
        cmd = f"Channel_{int(input_channel)}_Main_PV"
        return self.send_cmd(cmd)

    def read_output(self, loop_channel, output_channel):
        # self.Loop_1_OP_Ch1Out
        cmd = f"Loop_{int(loop_channel)}_OP_Ch{int(output_channel)}Out"
        return self.send_cmd(cmd)

    def set_output_value(self, loop_channel, output_channel, value):
        # self.Loop_1_OP_ManualOutVal = value
        cmd = f"Loop_{int(loop_channel)}_OP_ManualOutVal"
        self.send_cmd(cmd, value)

    def get_ramprate(self, loop_channel):
        # return self.Loop_1_SP_Rate
        cmd = f"Loop_{int(loop_channel)}_SP_Rate"
        return self.send_cmd(cmd)

    def set_ramprate(self, loop_channel, value):
        # self.Loop_1_SP_Rate = value
        cmd = f"Loop_{int(loop_channel)}_SP_Rate"
        self.send_cmd(cmd, value)

    def get_kp(self, loop_channel):
        # self.Loop_1_PID_ProportionalBand
        cmd = f"Loop_{int(loop_channel)}_PID_ProportionalBand"
        return self.send_cmd(cmd)

    def set_kp(self, loop_channel, value):
        # self.Loop_1_PID_ProportionalBand = value
        cmd = f"Loop_{int(loop_channel)}_PID_ProportionalBand"
        self.send_cmd(cmd, value)

    def get_ki(self, loop_channel):
        # self.Loop_1_PID_IntegralTime
        cmd = f"Loop_{int(loop_channel)}_PID_IntegralTime"
        return self.send_cmd(cmd)

    def set_ki(self, loop_channel, value):
        # self.Loop_1_PID_IntegralTime = value
        cmd = f"Loop_{int(loop_channel)}_PID_IntegralTime"
        self.send_cmd(cmd, value)

    def get_kd(self, loop_channel):
        # return self.Loop_1_PID_DerivativeTime
        cmd = f"Loop_{int(loop_channel)}_PID_DerivativeTime"
        return self.send_cmd(cmd)

    def set_kd(self, loop_channel, value):
        # self.Loop_1_PID_DerivativeTime = value
        cmd = f"Loop_{int(loop_channel)}_PID_DerivativeTime"
        self.send_cmd(cmd, value)

    def get_input_status(self, input_channel):
        # self.Channel_1_Main_Status
        cmd = f"Channel_{int(input_channel)}_Main_Status"
        return self.send_cmd(cmd)

    def get_output_status(self, loop_channel, output_channel):
        return "N/A"


class Nanodac(Controller):
    """
        Nanodac Regulation controller
    """

    # ------ init methods ------------------------

    def initialize_controller(self):
        """ 
        Initializes the controller (including hardware).
        """
        host = self.config["controller_ip"]
        self.hw_controller = nanodac(host)

    def initialize_input(self, tinput):
        """
        Initializes an Input class type object

        Args:
           tinput:  Input class type object          
        """
        log_info(self, "initialize_input")

        input_channel = tinput.config["channel"]
        if input_channel not in list(self.hw_controller.VALID_INPUT_CHANNELS):
            values = [x.value for x in self.hw_controller.VALID_INPUT_CHANNELS]
            raise ValueError(
                f"wrong channel '{input_channel}' for the input {tinput}. Should be in {values}"
            )

    def initialize_output(self, toutput):
        """
        Initializes an Output class type object

        Args:
           toutput:  Output class type object          
        """
        log_info(self, "initialize_output")

        # Note: for Nanodac, the output channel is the same as the loop channel.
        output_channel = toutput.config["channel"]
        if output_channel not in list(self.hw_controller.VALID_LOOP_CHANNELS):
            values = [x.value for x in self.hw_controller.VALID_LOOP_CHANNELS]
            raise ValueError(
                f"wrong channel '{output_channel}' for the output {toutput}. Should be in {values}"
            )
        toutput._master_loop_channel = toutput.config.get("master_loop_channel", 1)

    def initialize_loop(self, tloop):
        """
        Initializes a Loop class type object

        Args:
           tloop:  Loop class type object          
        """
        log_info(self, "initialize_loop")

        loop_channel = tloop.config["channel"]

        if loop_channel not in list(self.hw_controller.VALID_LOOP_CHANNELS):
            values = [x.value for x in self.hw_controller.VALID_LOOP_CHANNELS]
            raise ValueError(
                f"wrong channel '{loop_channel}' for the loop {tloop}. Should be in {values}"
            )

        # nanodac can have 2 output channels per loop (and it can have 2 loops)
        # so we need to store the associated loop channel into the output obj
        tloop.output._master_loop_channel = loop_channel

    # ------ get methods ------------------------

    def read_input(self, tinput):
        """
          
        """
        log_info(self, "Controller:read_input: %s" % (tinput))
        return self.hw_controller.read_input(tinput.channel)

    def read_output(self, toutput):
        """
        """
        log_info(self, "Controller:read_output: %s" % (toutput))

        # toutput.channel must be equal to tloop.channel
        return self.hw_controller.read_output(
            toutput._master_loop_channel, toutput.channel
        )

    def state_input(self, tinput):
        """
        """
        log_info(self, "Controller:state_input: %s" % (tinput))
        return self.hw_controller.get_input_status(tinput.channel)

    def state_output(self, toutput):
        """
        """
        log_info(self, "Controller:state_output: %s" % (toutput))
        return self.hw_controller.get_output_status(
            toutput._master_loop_channel, toutput.channel
        )

    # ------ PID methods ------------------------

    def set_kp(self, tloop, kp):
        """
        Set the PID P value
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object 
           kp: the kp value
        """
        log_info(self, "Controller:set_kp: %s %s" % (tloop, kp))
        self.hw_controller.set_kp(tloop.channel, kp)

    def get_kp(self, tloop):
        """
        Get the PID P value
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object 
        
        Returns:
           kp value
        """
        log_info(self, "Controller:get_kp: %s" % (tloop))
        return self.hw_controller.get_kp(tloop.channel)

    def set_ki(self, tloop, ki):
        """
        Set the PID I value
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object 
           ki: the ki value
        """
        log_info(self, "Controller:set_ki: %s %s" % (tloop, ki))
        self.hw_controller.set_ki(tloop.channel, ki)

    def get_ki(self, tloop):
        """
        Get the PID I value
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object 
        
        Returns:
           ki value
        """
        log_info(self, "Controller:get_ki: %s" % (tloop))
        return self.hw_controller.get_ki(tloop.channel)

    def set_kd(self, tloop, kd):
        """
        Set the PID D value
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object 
           kd: the kd value
        """
        log_info(self, "Controller:set_kd: %s %s" % (tloop, kd))
        self.hw_controller.set_kd(tloop.channel, kd)

    def get_kd(self, tloop):
        """
        Reads the PID D value
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Output class type object 
        
        Returns:
           kd value
        """
        log_info(self, "Controller:get_kd: %s" % (tloop))
        return self.hw_controller.get_kd(tloop.channel)

    def start_regulation(self, tloop):
        """
        Starts the regulation process.
        It must NOT start the ramp, use 'start_ramp' to do so.
        Raises NotImplementedError if not defined by inheriting class

        Args: 
           tloop:  Loop class type object
        """
        log_info(self, "Controller:start_regulation: %s" % (tloop))
        self.hw_controller.set_auto(tloop.channel, True)

    def stop_regulation(self, tloop):
        """
        Stops the regulation process.
        It must NOT stop the ramp, use 'stop_ramp' to do so.
        Raises NotImplementedError if not defined by inheriting class

        Args: 
           tloop:  Loop class type object
        """
        log_info(self, "Controller:stop_regulation: %s" % (tloop))
        self.hw_controller.set_auto(tloop.channel, False)

    # ------ setpoint methods ------------------------

    def set_setpoint(self, tloop, sp, **kwargs):
        """
        Set the current setpoint (target value).
        It must NOT start the PID process, use 'start_regulation' to do so.
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object
           sp:     setpoint (in tloop.input unit)
           **kwargs: auxilliary arguments
        """
        log_info(self, "Controller:set_setpoint: %s %s" % (tloop, sp))

        rate = self.get_ramprate(tloop)
        self.set_ramprate(tloop, 0)
        self.hw_controller.set_setpoint(tloop.channel, sp)
        self.set_ramprate(tloop, rate)

    def get_setpoint(self, tloop):
        """
        Get the current setpoint (target value)
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object

        Returns:
           (float) setpoint value (in tloop.input unit).
        """
        log_info(self, "Controller:get_setpoint: %s" % (tloop))
        return self.hw_controller.get_setpoint(tloop.channel)

    def get_working_setpoint(self, tloop):
        return self.hw_controller.get_working_setpoint(tloop.channel)

    # ------ setpoint ramping methods (optional) ------------------------

    def start_ramp(self, tloop, sp, **kwargs):
        """
        Start ramping to a setpoint
        It must NOT start the PID process, use 'start_regulation' to do so.
        Raises NotImplementedError if not defined by inheriting class

        Replace 'Raises NotImplementedError' by 'pass' if the controller has ramping but doesn't have a method to explicitly starts the ramping.
        Else if this function returns 'NotImplementedError', then the Loop 'tloop' will use a SoftRamp instead.

        Args:
           tloop:  Loop class type object
           sp:       setpoint (in tloop.input unit)
           **kwargs: auxilliary arguments
        """
        log_info(self, "Controller:start_ramp: %s %s" % (tloop, sp))
        self.hw_controller.set_setpoint(tloop.channel, sp)

    def stop_ramp(self, tloop):
        """
        Stop the current ramping to a setpoint
        It must NOT stop the PID process, use 'stop_regulation' to do so.
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object
        """
        log_info(self, "Controller:stop_ramp: %s" % (tloop))
        sp = self.read_input(tloop.input)
        self.hw_controller.set_setpoint(tloop.channel, sp)

    def is_ramping(self, tloop):
        """
        Get the ramping status.
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object

        Returns:
           (bool) True if ramping, else False.
        """
        log_info(self, "Controller:is_ramping: %s" % (tloop))
        return self.get_setpoint(tloop) != self.get_working_setpoint(tloop)

    def set_ramprate(self, tloop, rate):
        """
        Set the ramp rate
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object
           rate:   ramp rate (in input unit per second)
        """
        log_info(self, "Controller:set_ramprate: %s %s" % (tloop, rate))
        self.hw_controller.set_ramprate(tloop.channel, rate)

    def get_ramprate(self, tloop):
        """
        Get the ramp rate
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object
        
        Returns:
           ramp rate (in input unit per second)
        """
        log_info(self, "Controller:get_ramprate: %s" % (tloop))
        return self.hw_controller.get_ramprate(tloop.channel)

    # --- controller method to set the Output to a given value (optional) -----------

    def set_output_value(self, toutput, value):
        """
        Set the value on the Output device.
        Raises NotImplementedError if not defined by inheriting class

        Args:
           toutput: Output class type object 
           value: value for the output device (in output unit)      
        """
        log_info(self, "Controller:set_output_value: %s %s" % (toutput, value))
        self.hw_controller.set_output_value(
            toutput._master_loop_channel, toutput.channel, value
        )

    # --- Custom methods --------------------------
    @autocomplete_property
    def cmds(self):
        return self.hw_controller.cmds
