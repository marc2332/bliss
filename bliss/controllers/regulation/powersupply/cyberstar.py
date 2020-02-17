# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
-   class: Cyberstar
    module: regulation.powersupply.cyberstar
    plugin: bliss
    model: X20005CH
    timeout: 3
    serial:
        url: ser2net://lid00limace:28000/dev/ttyS0

    daisy_chain: 
        - name: cyber1
          module_address: 0              # <== identify the module in the serial line        
          module_channel: 1              # <== identify the channel on the cyberstar module (for PPU5CH and X20005CH only )
          axis_name: cylow1
           

"""

import enum
import gevent
import weakref

from bliss import global_map
from bliss.comm.util import get_comm
from bliss.common.logtools import log_debug, log_info
from bliss.common.soft_axis import SoftAxis
from bliss.common.axis import AxisState

from bliss.common.counter import SamplingCounter
from bliss.controllers.counter import SamplingCounterController
from bliss.common.utils import autocomplete_property


_CYBERSTAR_MASTERS = weakref.WeakValueDictionary()


def get_cyberstar_master(config):
    """ get the master node and get/create the CyberstarMaster object """
    master_node = config.parent

    for k in _CYBERSTAR_MASTERS.keys():
        if k == master_node:
            return _CYBERSTAR_MASTERS[k]

    master = CyberstarMaster(master_node)
    _CYBERSTAR_MASTERS[master_node] = master
    # print("=== CREATE CYBERSTAR MASTER ", master, id(master_node))
    return master


class CyberstarCC(SamplingCounterController):
    def __init__(self, name, cyberstar):
        super().__init__(name)
        self.cyberstar = cyberstar

    def read_all(self, *counters):
        values = []
        for cnt in counters:
            if cnt.name == "sca_low":
                values.append(self.cyberstar.sca_low)
            elif cnt.name == "sca_up":
                values.append(self.cyberstar.sca_up)
        return values


class Cyberstar:
    @enum.unique
    class _Remote(enum.IntEnum):
        OFF = 0
        ON = 1

    class _Model(enum.IntEnum):
        X1000 = 0
        PPU5CH = 1
        CS96MCD = 2
        X2000 = 3
        X20005CH = 4

    def __init__(self, name, config):
        self._name = name
        self._config = config
        self._cyberstar_master = get_cyberstar_master(config)
        self._module_address = config["module_address"]
        self._model = self._cyberstar_master.model

        global_map.register(self, parents_list=[self._cyberstar_master])

        # --- check given model exist -------------------------
        if self._model not in [x.name for x in self._Model]:
            raise ValueError(
                f"Wrong cyberstar model {self._model}. Valid models are {[x.name for x in self._Model]}"
            )

        # --- get model id -----------------------
        self._mid = self._Model[self._model]

        # --- get channel id for xxx5CH models ---------------
        if self._mid in [1, 4]:
            self._module_channel = int(config["module_channel"])
        else:
            self._module_channel = None

        log_info(self, "Cyberstar:__init__")

        # --- obtain the available parameters for the given model ----
        self.model2params = {
            # model #param          #cmd             #range
            0: {  # ------- X1000 ------------
                "hv": [":SOUR:VOLT", [250, 1250]],
                "sca_low": [":SENS:SCA:LOW", [0, 10]],
                "sca_up": [":SENS:SCA:UPP", [0, 10]],
                "gain": [":INP:GAIN", [0, 100]],
                "peaking_time": [":SENS:PKT", [300, 500, 1000, 3000]],
                "remote": [":SYST:COMM:REM", [0, 1]],
                "delay": [":TRIG:ECO", [0, 1000]],
            },
            1: {  # ------- PPU5CH ------------
                "sca_low": [":CONF:LL", [0, 4]],
                "sca_up": [":CONF:UL", [0, 4]],
                "gain": [":CONF:GN", [0, 10]],
                "peaking_time": [":CONF:PT", [50, 100, 300, 1000]],
            },
            2: {  # ------- CS96MCD ------------
                "sca_low": [":SENS:SCA:LOW", [0, 10]],
                "sca_up": [":SENS:SCA:UPP", [0, 10]],
                "gain": [":INP:GAIN", [0, 100]],
                "peaking_time": [":SENS:PKT", [300, 500, 1000, 3000]],
            },
            3: {  # ------- X2000 ------------
                "hv": [":SOUR:VOLT", [0, 1250]],
                "sca_low": [":SENS:SCA:LOW", [0, 4]],
                "sca_up": [":SENS:SCA:UPP", [0, 4]],
                "gain": [":INP:GAIN", [0, 100]],
                "peaking_time": [":SENS:PKT", [50, 100, 300, 1000]],
            },
            4: {  # ------- X20005CH ------------
                "sca_low": [":SENS:SCA:LOW", [0, 4]],
                "sca_up": [":SENS:SCA:UPP", [0, 4]],
                "gain": [":INP:GAIN", [0, 100]],
                "peaking_time": [":SENS:PKT", [50, 100, 300, 1000]],
            },
        }

        self._params2txt = {
            "hv": "high_voltage",
            "sca_low": "sca_low",
            "sca_up": "sca_up",
            "gain": "gain",
            "peaking_time": "peaking_time",
            "remote": "remote_control",
            "delay": "delay",
        }

        self._params = self.model2params[self._mid]

        self._sca_mini = self._params["sca_low"][1][0]
        self._sca_maxi = self._params["sca_low"][1][1]

        # --- soft axis attributes for a scanable cyberstar ------
        self._sca_window_size = None
        self._axis_tolerance = None
        self._axis_state = AxisState("READY")

        self._soft_axis = None
        self._create_soft_axis()

        self._cc = CyberstarCC(self.name + "_cc", self)
        self._cc.create_counter(SamplingCounter, "sca_low", unit="V", mode="SINGLE")
        self._cc.create_counter(SamplingCounter, "sca_up", unit="V", mode="SINGLE")

    def __info__(self):
        return "\n".join(self._show())

    def __str__(self):
        # this is for the mapping: it needs a representation of instance
        return super().__repr__()

    # ------------ GENERAL METHODS USING THE MODULE_ID AS ARGUMENT ------------------------------

    def _get_value(self, param):
        """ Read the current value of a parameter on a given cyberstar module
        """

        plist = self._params.get(param)
        if plist is None:
            raise ValueError(f"Unknown parameter {param}.")

        rcmd = plist[0]
        idx = rcmd.find(":", 1)

        cmd = f"{rcmd[:idx]}{self._module_address}{rcmd[idx:]}"
        if self._module_channel is not None:
            cmd += f"{self._module_channel}"
        cmd += "?"

        ans = self._send_cmd(cmd)
        return float(ans)

    def _set_value(self, param, value):
        """ Set the current value of a parameter on a given cyberstar module
        """

        plist = self._params.get(param)
        if plist is None:
            raise ValueError(f"Unknown parameter {param}.")

        if param == "peaking_time":
            if value not in self._params[param][1]:
                raise ValueError(
                    f"Error: {param} value must be in {self._params[param][1]}"
                )
        else:
            if value < self._params[param][1][0] or value > self._params[param][1][1]:
                raise ValueError(
                    f"Error: {param} value must be in range [{self._params[param][1][0]}, {self._params[param][1][1]}]"
                )

        rcmd = plist[0]
        idx = rcmd.find(":", 1)

        cmd = f"{rcmd[:idx]}{self._module_address}{rcmd[idx:]}"
        if self._module_channel is not None:
            cmd += f"{self._module_channel}"
        cmd += f" {value}"

        self._send_cmd(cmd)

    def _send_cmd(self, command):
        log_info(self, f"_send_cmd '{command}' ")
        return self._cyberstar_master.send_cmd(command)

    def _clear(self):
        """ Reset the module_address in the serial chain """
        self._send_cmd(f"*RST{self._module_address}")

    def _show(self):
        """ Display all main parameters and values of the cyberstar module
            Prints:
              device ID, communication information,
              high voltage value, SCA low voltage, SCA high voltage,
              peaking time and gain
        """

        available_params = self._params.keys()

        info_list = []
        log_info(self, "show")
        info_list.append(f"name: {self.name}")
        info_list.append(f"com:  {self._cyberstar_master.comm}")
        info_list.append(f"module_address: {self.module_address}")

        if self._module_channel is not None:
            info_list.append(f"module_channel: {self.module_channel}")

        if "hv" in available_params:
            info_list.append(
                f"{self._params2txt['hv']:15s} = {self.high_voltage:6.4f}V  (range=[{self._params['hv'][1][0]}, {self._params['hv'][1][1]}])"
            )

        info_list.append(
            f"{self._params2txt['sca_low']:15s} = {self.sca_low:6.4f}V  (range=[{self._params['sca_low'][1][0]}, {self._params['sca_low'][1][1]}])"
        )
        info_list.append(
            f"{self._params2txt['sca_up']:15s} = {self.sca_up:6.4f}V  (range=[{self._params['sca_up'][1][0]}, {self._params['sca_up'][1][1]}])"
        )
        info_list.append(f"sca_window_size = {self.sca_window_size:6.4f}V")
        info_list.append(
            f"{self._params2txt['gain']:15s} = {str(self.gain):6}%  (range=[{self._params['gain'][1][0]}, {self._params['gain'][1][1]}])"
        )
        info_list.append(
            f"{self._params2txt['peaking_time']:15s} = {str(self.peaking_time):6}ns (range={self._params['peaking_time'][1]})"
        )

        if "delay" in available_params:
            info_list.append(f"{self._params2txt['delay']:15s} = {str(self.delay):6}s")

        if "remote" in available_params:
            info_list.append(
                f"{self._params2txt['remote']:15s}: {str(self._Remote(self.remote_control).name):6}\n"
            )

        return info_list

    @autocomplete_property
    def counters(self):
        """ Standard counter namespace """
        return self._cc.counters

    # ---- END USER METHODS ------------------------------------------------------------

    @property
    def name(self):
        return self._name

    @property
    def module_address(self):
        return self._module_address

    @property
    def module_channel(self):
        return self._module_channel

    @property
    def gain(self):
        log_debug(self, "Cyberstar:gain")
        return self._get_value("gain")

    @gain.setter
    def gain(self, value):
        log_debug(self, "Cyberstar:gain.setter %s" % value)
        self._set_value("gain", value)

    @property
    def peaking_time(self):
        log_debug(self, "Cyberstar:peaking_time")
        return int(self._get_value("peaking_time"))

    @peaking_time.setter
    def peaking_time(self, value):
        log_debug(self, "Cyberstar:peaking_time.setter %s" % value)
        self._set_value("peaking_time", value)

    @property
    def delay(self):
        log_debug(self, "Cyberstar:delay")
        return int(self._get_value("delay"))

    @delay.setter
    def delay(self, value):
        log_debug(self, "Cyberstar:delay.setter %s" % value)
        self._set_value("delay", value)

    @property
    def remote_control(self):
        log_info(self, "Cyberstar:remote_control")
        return int(self._get_value("remote"))

    @remote_control.setter
    def remote_control(self, value):
        log_info(self, "Cyberstar:remote_control.setter")
        self._set_value("remote", value)

    @property
    def high_voltage(self):
        log_debug(self, "Cyberstar:high_voltage")
        return self._get_value("hv")

    @high_voltage.setter
    def high_voltage(self, value):
        log_debug(self, "Cyberstar:high_voltage.setter %s" % value)
        self._set_value("hv", value)

    @property
    def sca_low(self):
        log_debug(self, "Cyberstar:sca_low")
        return self._get_value("sca_low")

    @sca_low.setter
    def sca_low(self, value):
        log_debug(self, "Cyberstar:sca_low.setter %s" % value)

        if value >= self.sca_up:
            raise ValueError(f"Error: sca_low value must be lower than sca_up")

        self._set_value("sca_low", value)
        self._update_sca_window_size()

    @property
    def sca_up(self):
        log_debug(self, "Cyberstar:sca_up")
        return self._get_value("sca_up")

    @sca_up.setter
    def sca_up(self, value):
        log_debug(self, "Cyberstar:sca_up.setter %s" % value)

        if value <= self.sca_low:
            raise ValueError(f"Error: sca_up value must be greater than sca_low")

        self._set_value("sca_up", value)
        self._update_sca_window_size()

    @property
    def sca_window_size(self):
        log_debug(self, "Cyberstar:sca_window_size")
        if self._sca_window_size is None:
            self._update_sca_window_size()

        return self._sca_window_size

    @sca_window_size.setter
    def sca_window_size(self, value):
        log_debug(self, "Cyberstar:sca_window_size.setter")
        delta = self._sca_maxi - self._sca_mini
        if value < 0 or value > delta:
            raise ValueError(
                f"Error: sca_window_size value must be in range [0, {delta}]"
            )

        sca_up = self.sca_low + value
        self._set_value("sca_up", sca_up)
        self._sca_window_size = value

    def _update_sca_window_size(self):
        self._sca_window_size = self.sca_up - self.sca_low

    # ---- SOFT AXIS METHODS TO MAKE THE CYBERSTAR SCANABLE -----------
    @property
    def axis(self):
        """ Return a SoftAxis object that makes the Cyberstar scanable.
            The axis will move sca_low and sca_up together so that it keeps the sca_window (=up-low) constant.
        """
        if self._soft_axis is None:
            self._create_soft_axis()

        return self._soft_axis

    def _create_soft_axis(self):

        axis_name = self._config.get("axis_name")
        name = axis_name if axis_name is not None else self.name + "_axis"

        self._soft_axis = SoftAxis(
            name,
            self,
            position="axis_position",
            move="axis_move",
            stop="axis_stop",
            state="axis_state",
            low_limit=float(self._params["sca_low"][1][0]),
            high_limit=float(self._params["sca_low"][1][1]),
            tolerance=self._axis_tolerance,
            unit="V",
        )

    def axis_position(self):
        """ Return the sca_low value as the current position of the associated soft axis"""

        return self.sca_low

    def axis_move(self, pos):
        """ Set the sca_low value as the new position of the associated soft axis keeping the sca_window_size (=up-low) constant"""

        if ((pos + self.sca_window_size) > self._sca_maxi) or (pos < self._sca_mini):
            ValueError(
                f"Error: cannot move outside limits [{self._sca_mini}, {self._sca_maxi - self._sca_window_size}] "
            )

        up_target = pos + self._sca_window_size
        if up_target < self._sca_mini or up_target > self._sca_maxi:
            raise ValueError(
                f"Error: sca_up value must be in range [{self._sca_mini}, {self._sca_maxi}]"
            )

        self._axis_state = AxisState("MOVING")

        self._set_value("sca_low", pos)
        self._set_value("sca_up", up_target)

        gevent.sleep(0.1)
        self._axis_state = AxisState("READY")

    def axis_stop(self):
        """ Stop the motion of the associated soft axis """
        pass

    def axis_state(self):
        """ Return the current state of the associated soft axis.
        """

        # Standard axis states:
        # MOVING : 'Axis is moving'
        # READY  : 'Axis is ready to be moved (not moving ?)'
        # FAULT  : 'Error from controller'
        # LIMPOS : 'Hardware high limit active'
        # LIMNEG : 'Hardware low limit active'
        # HOME   : 'Home signal active'
        # OFF    : 'Axis is disabled (must be enabled to move (not ready ?))'

        return self._axis_state


class CyberstarMaster:
    def __init__(self, config):
        self.config = config
        self.comm = get_comm(config)
        self.timeout = config.get("timeout", 3.0)
        self.model = config["model"].upper()

        global_map.register(self, children_list=[self.comm])

        self.comm.open()

    def send_cmd(self, command):
        """ Send a command to the controller
            Args:
              command (str): The command string
            Returns:
              Answer from the controller if ? in the command
        """
        log_info(self, f"send_cmd '{command}' ")

        command += "\n"

        if "?" in command:
            asw = self.comm.write_readline(
                command.encode(), timeout=self.timeout
            ).decode()
            self._check_com(asw[0], command)
            return asw[1:]
        else:
            asw = self.comm.write_read(command.encode(), timeout=self.timeout).decode()
            self._check_com(asw[0], command)

    def _check_com(self, ack, command):
        if ack != "\x06":
            error_msg = f"Timeout with {self.comm} and command {command}"
            # print(error_msg)
            self.comm.flush()
            raise ValueError(error_msg)
