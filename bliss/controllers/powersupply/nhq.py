# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import enum
import re
from functools import partial
import gevent

from bliss import global_map
from bliss.comm.util import get_comm
from bliss.common.utils import autocomplete_property
from bliss.common.session import get_current_session

from bliss.common.counter import SamplingCounter
from bliss.controllers.counter import SamplingCounterController

from bliss.common.logtools import log_info, log_debug
from bliss.common.soft_axis import SoftAxis
from bliss.common.axis import AxisState

from bliss.common.regulation import ExternalOutput

from bliss.common.protocols import IterableNamespace


"""
NHQ power supply, acessible via Serial line (RS232)

yml configuration example:

- class: Nhq
  module: powersupply.nhq
  plugin: bliss
  name: nhq
  timeout: 10
  tcp:
    # Does not work
    #ser2net://lid101:28000/dev/ttyRP19
    #baudrate: 9600    # max (other possible values: 300, 1200)

    # we use the port configuration
    # 28319:raw:0:/dev/ttyRP19:9600 remctl  kickolduser NOBREAK 
    url: lid101:28319
    
    # eol: "\r\n"

  counters:
    - counter_name: iav
      channel: A
      tag: voltage
      mode: SINGLE
    - counter_name: iac
      channel: A
      tag: current
      mode: SINGLE
    - counter_name: ibv
      channel: B
      tag: voltage
      mode: SINGLE
    - counter_name: ibc
      channel: B
      tag: current
      mode: SINGLE

  axes:
    - axis_name: oav
      channel: A
      tolerance: 10
      low_limit: 0
      high_limit: 250

    - axis_name: obv
      channel: B
"""


"""
-   class: NhqOutput    
    module: powersupply.nhq
    plugin: bliss
    name: nhq_output_A
    device: $nhq.chA
    unit: V
    #low_limit: 0.0           
    #high_limit: 100.0       
    ramprate: 10.0  #V/s        
            
"""


class NhqOutput(ExternalOutput):
    def __init__(self, name, config):
        super().__init__(config)
        self.mode = config.get("mode", "absolute")

    # ----------- BASE METHODS -----------------------------------------

    @property
    def ramprate(self):
        """ Get ramprate (in output unit per second) """

        log_debug(self, "ExternalOutput:get_ramprate")

        return self.device.ramprate

    @ramprate.setter
    def ramprate(self, value):
        """ Set ramprate (in output unit per second) """

        log_debug(self, "ExternalOutput:set_ramprate: %s" % (value))

        self.device.ramprate = value
        self._ramp.rate = value

    def is_ramping(self):
        """
        Get the ramping status.
        """

        log_debug(self, "ExternalOutput:is_ramping")

        return self.device.is_ramping

    def _start_ramping(self, value):
        """ Start the ramping process to target_value """

        log_debug(self, "ExternalOutput:_start_ramping %s" % value)

        self.device.setpoint = value

    def _stop_ramping(self):
        """ Stop the ramping process """

        log_debug(self, "ExternalOutput:_stop_ramping")
        self.device._stop_ramping()

    # ----------- METHODS THAT A CHILD CLASS MAY CUSTOMIZE ------------------

    def state(self):
        """ Return the state of the output device"""

        log_debug(self, "ExternalOutput:state")

        return self.device.status

    def read(self):
        """ Return the current value of the output device (in output unit) """

        log_debug(self, "ExternalOutput:read")

        return self.device.voltage

    def _set_value(self, value):
        """ Set the value for the output. Value is expressed in output unit """

        log_debug(self, "ExternalOutput:_set_value %s" % value)

        self.device.setpoint = value


class NhqCC(SamplingCounterController):
    def __init__(self, name, nhq):
        super().__init__(name)
        self.nhq = nhq

    def read_all(self, *counters):
        values = []
        for cnt in counters:
            values.append(self.nhq._channels[cnt.channel]._raw_read(cnt.tag))
        return values

    def read(self, counter):
        return self.nhq._channels[counter.channel]._raw_read(counter.tag)


class NhqChannel:
    def __init__(self, nhq, channel):
        self.nhq = nhq
        self.channel = channel
        self._chan_num = self.nhq._CHANNEL[channel].value
        self._module_status = None
        self._auto_mode_has_been_set = False

    def __info__(self, show_module_info=True):
        info_list = []

        info_list.append(f"=== Channel '{self.channel}' ===")

        if show_module_info:
            if self._module_status is None:
                self.module_status

            info_list.append("")
            for k, v in self._module_status.items():
                info_list.append(f"{k:12s}: {v}")
            info_list.append("")

        st = self.status
        info_list.append(f"Status      : {st} ({self.nhq._STATUS2INFO[st]})")
        info_list.append(
            f"Voltage     : {str(self.voltage)+'V':9s} (limit={self.voltage_limit}%)"
        )
        info_list.append(
            f"Current     : {str(self.current)+'A':9s} (limit={self.current_limit}%)"
        )
        info_list.append(f"Setpoint    : {self.setpoint}V")
        info_list.append(f"Ramp rate   : {self.ramprate}V/s")
        info_list.append(f"Current trip: {self.current_trip}")

        return "\n".join(info_list)

    def _raw_read(self, tag):
        """ Read actual current or voltage 
            Args:
              tag (str): Valid entries: ['voltage', 'current']            

            Returns:
              (float): Voltage or current value
        """
        log_info(self, "raw_read")
        if tag == "voltage":
            return float(self.nhq.send_cmd("U", channel=self._chan_num))
        elif tag == "current":
            return float(self.nhq.send_cmd("I", channel=self._chan_num))

    def _read_limit(self, tag):
        """ Read the current or voltage limit
            Args:
              tag (str): Valid entries: ['voltage', 'current']            

            Returns:
              (float): Voltage or current value
        """
        log_info(self, "_read_limit")
        if tag == "voltage":
            return float(self.nhq.send_cmd("M", channel=self._chan_num))
        elif tag == "current":
            return float(self.nhq.send_cmd("N", channel=self._chan_num))

    def _start_ramping(self):
        """Command to start the ramping after changing the setpoint.
           If AUTO_START is TRUE, this command is not necessary.
        """
        log_info(self, "_start_ramping")
        return self.nhq.send_cmd("G", channel=self._chan_num)

    def _stop_ramping(self):
        # if self.is_ramping:
        self.setpoint = self.voltage

    # == HIDE THE AUTO START METHODS AND ALWAYS USE AUTO_START = TRUE
    # == (see self._auto_mode_has_been_set)

    # @property
    # def auto_start(self):
    #     log_info(self, "auto_start_getter")
    #     return int(self.nhq.send_cmd("A", channel=self._chan_num))

    # @auto_start.setter
    # def auto_start(self, enable):
    #     log_info(self, "auto_start_setter")

    #     if enable:
    #         value = 8
    #     else:
    #         value = 0

    #     self.nhq.send_cmd("A", channel=self._chan_num, arg=value)

    @property
    def name(self):
        return self.nhq.name + ".ch%s" % self.channel

    @property
    def status(self):
        log_info(self, "status")
        st = self.nhq.send_cmd("S", channel=self._chan_num).split("=")[1].strip()

        # IF CURRENT TRIP IS ACTIVATED SET SETPOINT TO ZERO TO AVOID A LOOP OF RAMPING/TRIPPING
        # WHICH HAPPEN IF IN AUTO_START MODE (RAMP RESTARTS AS SOON AS TRP STATUS IS READ)
        if st == "TRP":
            self.setpoint = 0
            # print("Current trip has been activated: setpoint has been reset to 0 !")
            raise RuntimeError(
                "Current trip has been activated: setpoint has been reset to 0 !"
            )

        return st

    def _read_module_status(self):

        int_module_status = int(self.nhq.send_cmd("T", channel=self._chan_num))

        minfo = {}

        if int_module_status & 2:
            # print("Control manual")
            minfo["Control"] = "manual"
        else:
            # print("Control via RS232 interface.")
            minfo["Control"] = "RS232"

        if int_module_status & 4:
            # print("Polarity set to positive.")
            minfo["Polarity"] = "positive"
        else:
            # print("Polarity set to negative.")
            minfo["Polarity"] = "negative"

        if int_module_status & 8:
            # print("Front panel HV-ON switch in OFF position.")
            minfo["HV-ON switch"] = "OFF"
        else:
            # print("Front panel HV-ON switch in ON position.")
            minfo["HV-ON switch"] = "ON"

        if int_module_status & 16:
            # print("KILL-ENABLE is on.")
            minfo["KILL-ENABLE"] = "ON"
        else:
            # print("KILL-ENABLE is off.")
            minfo["KILL-ENABLE"] = "OFF"

        if int_module_status & 32:
            # print("INHIBIT signal was/is active.")
            minfo["INHIBIT"] = "active"
        else:
            # print("INHIBIT signal is inactive.")
            minfo["INHIBIT"] = "inactive"

        if int_module_status & 64:
            # print("Vmax or Imax is/was exceeded.")
            minfo["Err"] = "Vmax or Imax is/was exceeded"

        if int_module_status & 128:
            # print("Quality of output voltage not givent at present.")
            minfo["Quality"] = "Quality of output voltage not givent at present"

        return minfo

    @property
    def module_status(self):
        log_info(self, "module_status_getter")
        self._module_status = self._read_module_status()
        return self._module_status

    @property
    def voltage(self):
        return self._raw_read("voltage")

    @property
    def current(self):
        return self._raw_read("current")

    @property
    def voltage_limit(self):
        return self._read_limit("voltage")

    @property
    def current_limit(self):
        return self._read_limit("current")

    @property
    def current_trip(self):
        log_info(self, "_read_current_trip")
        return float(self.nhq.send_cmd("L", channel=self._chan_num))

    @current_trip.setter
    def current_trip(self, value):
        log_info(self, "_write_current_trip")
        value = abs(int(value))
        self.nhq.send_cmd("L", channel=self._chan_num, arg=value)

    @property
    def setpoint(self):
        """ read the voltage setpoint of the given channel """
        log_info(self, "setpoint_getter")
        return float(self.nhq.send_cmd("D", channel=self._chan_num))

    @setpoint.setter
    def setpoint(self, value):
        """ set the voltage setpoint of the given channel """
        log_info(self, "setpoint_setter")
        value = abs(int(value))

        # SET THE AUTO MODE TO AVOID CALLING START RAMPING AFTER SETTING SETPOINT
        if not self._auto_mode_has_been_set:
            self.nhq.send_cmd("A", channel=self._chan_num, arg=8)
            self._auto_mode_has_been_set = True

        self.nhq.send_cmd("D", channel=self._chan_num, arg=value)

    @property
    def ramprate(self):
        """ read the voltage setpoint ramprate (V/s) of the given channel """
        log_info(self, "ramprate_getter")
        return float(self.nhq.send_cmd("V", channel=self._chan_num))

    @ramprate.setter
    def ramprate(self, value):
        """ set the voltage setpoint ramprate (V/s) of the given channel """
        log_info(self, "ramprate_setter")
        value = int(value)
        if value < 2 or value > 255:
            raise ValueError("Ramprate value must be in range [2,255]")
        self.nhq.send_cmd("V", channel=self._chan_num, arg=value)

    @property
    def is_at_setpoint(self):
        return bool(self.status == "ON")

    @property
    def is_ramping(self):
        return bool(self.status in ["L2H", "H2L"])


class Nhq:
    @enum.unique
    class _CHANNEL(enum.IntEnum):
        none = 0
        A = 1
        B = 2

    def __init__(self, name, config):
        self._name = name
        self._config = config
        self._comm = get_comm(config)
        self._timeout = config.get("timeout", 3.0)
        self._comm_delay = 0.05
        self._lock = gevent.lock.Semaphore()

        self._unit_number = None
        self._software_version = None
        self._vout_max = None
        self._iout_max = None

        self._STATUS2INFO = {
            "ON": "Output voltage according to set voltage",
            "OFF": "Channel front panel switch off",
            "MAN": "Channel is on, set to manual mode",
            "ERR": "Vmax or Imax is / was exceeed",
            "INH": "Inhibit signal is / was active",
            "QUA": "Quality of output voltage not given at present",
            "L2H": "Output voltage increasing",
            "H2L": "Output voltage failing",
            "LAS": "Look at Status (only after G-command)",
            "TRP": "Current trip was active",
        }

        global_map.register(self, children_list=[self._comm])

        # --- NhqChannels ------
        self._channels = {"A": NhqChannel(self, "A"), "B": NhqChannel(self, "B")}

        # --- pseudo axes ------
        self._polling_time = 0.1
        self._axes_tolerance = {"A": None, "B": None}
        # self._axes_state = {"A": AxisState("READY"), "B": AxisState("READY")}
        self._soft_axes = {"A": None, "B": None}
        self._create_soft_axes(config)

        # ---- Counters -------------------------------------------------------------
        self._create_counters(config)

        self._comm.open()

    def __info__(self, level=1):
        info_list = []
        print(
            f"Gathering information from {self._config['tcp'].to_dict()}, please wait few seconds...\n"
        )
        # Get full identification string
        if self._unit_number is None:
            identifier_dict = self.module_info
            self._unit_number = identifier_dict["unit_number"]
            self._software_version = identifier_dict["software_version"]
            self._vout_max = identifier_dict["vout_max"]
            self._iout_max = identifier_dict["iout_max"]

        info_list.append(
            f"=== Controller {self.name} (sn{self._unit_number} ver{self._software_version}) ==="
        )
        info_list.append("")
        # info_list.append(f"Unit number     : {self.unit_number}")
        # info_list.append(f"Software version: {self.software_version}")
        if level > 1:
            info_list.append(f"Break time      : {self.break_time}ms")
        info_list.append(f"Maximum voltage : {self._vout_max}")
        info_list.append(f"Maximum current : {self._iout_max}")
        info_list.append("")

        txt = "\n".join(info_list)

        if level == 1:
            s1, v1 = self.chA.status, self.chA.voltage
            try:
                s2, v2 = self.chB.status, self.chB.voltage
            except ValueError:
                # no channel B on this device
                s2, v2 = None, None

            txt += f"Channel A state : {s1} @ {v1}V\n"
            if not None in (s2, v2):
                txt += f"Channel B state : {s2} @ {v2}V\n"

        else:
            txt += "\n" + self.chA.__info__(show_module_info=False) + "\n"
            try:
                txt += "\n" + self.chB.__info__(show_module_info=False) + "\n"
            except Exception:
                pass

        return txt

    def __str__(self):
        # this is for the mapping: it needs a representation of instance
        return super().__repr__()

    @property
    def module_info(self):
        """ Get the module identifier
            Returns: {unit_number, software_version, Vout_max, Iout_max}
        """

        log_info(self, "module_info_getter")
        info = self.send_cmd("#").split(";")
        unit_number = info[0]
        software_version = info[1]
        vout_max = info[2]
        iout_max = info[3]
        return {
            "unit_number": unit_number,
            "software_version": software_version,
            "vout_max": vout_max,
            "iout_max": iout_max,
        }

    @property
    def break_time(self):
        """ Return the minimum time between 2 characters sent in a communication with the hw device"""
        log_info(self, "break_time_getter")
        return float(self.send_cmd("W"))

    @break_time.setter
    def break_time(self, value):
        """ Write the break_time in ms (in range [0, 255]) """
        log_info(self, "break_time_setter")
        value = int(value)
        if value < 0 or value > 255:
            raise ValueError("break_time value must be in range [0, 255]")
        self.send_cmd("W", arg=value)

    # ---- END USER METHODS ------------------------------------------------------------

    @property
    def name(self):
        return self._name

    @autocomplete_property
    def axes(self):
        return IterableNamespace(**{v.name: v for v in self._soft_axes.values()})

    @autocomplete_property
    def chA(self):
        return self._channels["A"]

    @autocomplete_property
    def chB(self):
        return self._channels["B"]

    @autocomplete_property
    def counters(self):
        """ Standard counter namespace """

        return self._cc.counters

    def send_cmd(self, command, channel=None, arg=None):
        """ Send a command to the controller
            Args:
              command (str): The command string
              args: Possible variable number of parameters
            Returns:
              Answer from the controller if ? in the command
        """

        log_info(self, "send_cmd")

        with self._lock:

            # print("in send_cmd channel1 = {}".format(channel))
            cr = "\r"
            lf = "\n"
            if channel is None:
                if arg is not None:
                    arg = str(arg)
                    command = f"{command}={arg}"
            else:
                channel = str(channel)
                # print("in send_cmd channel2 = {}".format(channel))
                if arg is None:
                    command = f"{command}{channel}"
                else:
                    arg = str(arg)
                    command = f"{command}{channel}={arg}"

            # print(f"SEND COMMAND: {command}")

            for tx in command:
                self._comm.write(tx.encode())
                rx = self._comm.raw_read(1)
                rx = rx.decode()
                # print(f"tx = {tx}, rx_decode = {rx}")
                # assert tx == rx

            self._comm.write(cr.encode())
            # print("tx = \\r")
            rx = self._comm.raw_read(1)
            # print(rx)
            rx = rx.decode()
            # print(rx)
            # assert cr == rx

            self._comm.write(lf.encode())
            # print("tx = \\n")
            rx = self._comm.raw_read(1)
            rx = rx.decode()
            # print(rx)
            # assert lf == rx

            if "=" not in command:
                # Power supply needs time to think
                gevent.sleep(self._comm_delay)
                asw = self._comm._readline(eol="\r\n")
                asw = asw.decode()

                if asw.startswith("-"):
                    # negative value
                    sign = "-"
                    asw = asw[1:]
                else:
                    sign = ""

                if asw[-3] == "-":
                    f = asw.split("-")
                    asw = f"{sign}{f[0]}E-{f[1]}"
                if re.search(r"\?", asw):
                    asw = f"Error. Unexpected reply = {asw}"
                    self._comm.flush()
                # print(asw)
                return asw
            else:
                # Power supply needs time to think
                gevent.sleep(self._comm_delay)
                self._comm._readline(eol="\r\n")

    # ---- SOFT AXIS METHODS TO MAKE THE ACE SCANABLE -----------

    def _create_soft_axes(self, config):

        axes_conf = config.get("axes", [])

        for conf in axes_conf:

            name = conf["axis_name"].strip()
            chan = conf["channel"].strip().upper()

            low_limit = conf.get("low_limit")
            high_limit = conf.get("high_limit")

            tol = conf.get("tolerance")
            if tol:
                self._axes_tolerance[chan] = float(tol)

            if chan not in ["A", "B"]:
                raise ValueError(f"Nhq counter {name}: 'channel' must be in ['A', 'B']")

            self._soft_axes[chan] = SoftAxis(
                name,
                self,
                position=partial(self._axis_position, channel=chan),
                move=partial(self._axis_move, channel=chan),
                stop=partial(self._axis_stop, channel=chan),
                state=partial(self._axis_state, channel=chan),
                low_limit=low_limit,
                high_limit=high_limit,
                tolerance=self._axes_tolerance[chan],
                unit="V",
            )

    def _axis_position(self, channel=None):
        """ Return the actual voltage of the given channel as the current position of the associated soft axis """
        return abs(self._channels[channel].voltage)

    def _axis_move(self, pos, channel=None):
        """ Set the voltage setpoint to a new value as the target position of the associated soft axis"""
        st = self._channels[channel].status
        if st != "ON":
            raise ValueError(
                f"axis {self._soft_axes[channel].name} not ready (state={st})!"
            )
        self._channels[channel].setpoint = pos

    def _axis_stop(self, channel=None):
        """ Stop the motion of the associated soft axis """
        self._channels[channel]._stop_ramping()

    def _axis_state(self, channel=None):
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

        # return AxisState("READY")

        st = self._channels[channel].status

        if st == "ON":
            return AxisState("READY")
        elif st in ["L2H", "H2L"]:
            return AxisState("MOVING")
        else:
            return AxisState("FAULT")

    # ---- COUNTERS METHODS ------------------------

    def _create_counters(self, config, export_to_session=True):

        cnts_conf = config.get("counters")
        if cnts_conf is None:
            return

        tag2unit = {"voltage": "V", "current": "A"}
        self._cc = NhqCC(self.name + "_cc", self)
        self._cc.max_sampling_frequency = config.get("max_sampling_frequency", 1)

        for conf in cnts_conf:

            name = conf["counter_name"].strip()
            chan = conf["channel"].strip().upper()
            tag = conf["tag"].strip().lower()
            mode = conf.get("mode", "SINGLE")

            if chan not in ["A", "B"]:
                raise ValueError(f"Nhq counter {name}: 'channel' must be in ['A', 'B']")

            if tag not in ["voltage", "current"]:
                raise ValueError(
                    f"Nhq counter {name}: 'tag' must be in ['voltage', 'current']"
                )

            cnt = self._cc.create_counter(
                SamplingCounter, name, unit=tag2unit[tag], mode=mode
            )
            cnt.channel = chan
            cnt.tag = tag

            if export_to_session:
                current_session = get_current_session()
                if current_session is not None:
                    if (
                        name in current_session.config.names_list
                        or name in current_session.env_dict.keys()
                    ):
                        raise ValueError(
                            f"Cannot export object to session with the name '{name}', name is already taken! "
                        )

                    current_session.env_dict[name] = cnt
