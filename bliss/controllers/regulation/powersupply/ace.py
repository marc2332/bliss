# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
-   class: Ace
    module: regulation.powersupply.ace
    plugin: bliss
    name: ace
    timeout: 3
    serial:
        url: ser2net://lid00limace:28000/dev/ttyS0

    axes:
        - name: ace_axe_low
          tag: low
        
        - name: ace_axe_win
          tag: win

        - name: ace_axe_hhv
          tag: hhv
    
    counters:
        - name: ace_cnt_counts
          tag: counts
          mode: LAST
        
        - name: ace_cnt_htemp
          tag: htemp
          unit: \xB0C
          mode: SINGLE

        - name: ace_cnt_hvcur
          tag: hvcur
          unit: uA
          mode: SINGLE

        - name: ace_cnt_hvmon
          tag: hvmon
          unit: V
          mode: SINGLE
"""

import time
import enum
import gevent

from functools import partial

from bliss.shell.standard import ShellStr
from bliss import global_map
from bliss.comm.util import get_comm
from bliss.common.logtools import log_debug, log_info
from bliss.common.soft_axis import SoftAxis
from bliss.common.axis import AxisState

from bliss.common.counter import SamplingCounter
from bliss.controllers.counter import SamplingCounterController
from bliss.scanning.acquisition.counter import SamplingCounterAcquisitionSlave
from bliss.common.utils import autocomplete_property
from bliss.common.protocols import counter_namespace


class AceAcquisitionSlave(SamplingCounterAcquisitionSlave):
    def prepare_device(self):
        pass

    def start_device(self):
        pass

    def stop_device(self):
        self.device.ace.stop_counting()

    def trigger(self):
        self._trig_time = time.time()
        self.device.ace.start_counting(self.count_time)
        self._event.set()


class AceCC(SamplingCounterController):
    def __init__(self, name, ace):
        super().__init__(name)
        self.ace = ace

    def get_acquisition_object(self, acq_params, ctrl_params, parent_acq_params):
        return AceAcquisitionSlave(self, ctrl_params=ctrl_params, **acq_params)

    def read_all(self, *counters):
        values = []
        for cnt in counters:
            if cnt.tag == "hvcur":
                values.append(self.ace.hvcur)
            elif cnt.tag == "hvmon":
                values.append(self.ace.hvmon)
            elif cnt.tag == "htemp":
                values.append(self.ace.htemp)
            elif cnt.tag == "counts":
                values.append(self.ace.counts)
        return values


class Ace:
    @enum.unique
    class _ScaMode(enum.IntEnum):
        INT = 1
        WIN = 2

    @enum.unique
    class _CountingSource(enum.IntEnum):
        SCA = 1
        TRG = 2

    def __init__(self, name, config):
        self._name = name
        self._config = config
        self.comm = get_comm(config)
        self.timeout = config.get("timeout", 3.0)

        global_map.register(self, children_list=[self.comm])

        self.comm.open()

        self._state_labels = {"D": "ready", "R": "running", "W": "wait", "A": "abort"}

        # --- obtain the available parameters for the given model ----
        self.model2params = {
            # model #param          #cmd             #range
            0: {
                "sca_hhv": ["HVOLT", [0, 600]],
                "sca_low": ["SCA", [-0.2, 5]],
                "sca_win": ["SCA", [0, 5]],
                "sca_mode": ["SCA", [1, 2]],
                "counting_source": ["CSRC"],
                "counter_status": ["CT DATA"],
                "alarm_mode": ["ALMODE"],
                "hvmon": ["HVMON"],
                "hvcur": ["HCURR"],
                "htemp": ["HTEMP"],
                "counts": ["CT DATA"],
            }
        }

        self._mid = 0  # just one model for now
        self._params = self.model2params[self._mid]

        # --- pseudo axes ------
        self._axes_tolerance = {"low": None, "win": None, "hhv": None}
        self._axes_state = {
            "low": AxisState("READY"),
            "win": AxisState("READY"),
            "hhv": AxisState("READY"),
        }
        self._soft_axes = {"low": None, "win": None, "hhv": None}
        self._create_soft_axes(config)

        # ---- Counters -------------------------------------------------------------
        self._create_counters(config)

    def __info__(self):
        return "\n".join(self._show())

    def __str__(self):
        # this is for the mapping: it needs a representation of instance
        return super().__repr__()

    # ------------ GENERAL METHODS USING THE MODULE_ID AS ARGUMENT ------------------------------

    def _get_value(self, param):
        """ Read the current value of a parameter on a given ace module
        """

        plist = self._params.get(param)
        if plist is None:
            raise ValueError(f"Unknown parameter {param}.")

        rcmd = plist[0]

        cmd = f"?{rcmd}"
        # print(f"SEND: {cmd}")
        ans = self.send_cmd(cmd)
        # print(f"RECV: {ans}")

        # ---------------
        if param == "sca_win":
            if "WIN" in ans:
                return ans.split()[2]
            else:
                return "No window value available with sca_mode = INT"
        elif param == "sca_low":
            return ans.split()[1]

        elif param == "sca_mode":
            return ans.split()[0]

        elif param == "sca_hhv":
            return ans.split()[0]

        # ---------------

        return ans

    def _set_value(self, param, value):
        """ Set the current value of a parameter on a given ace module
        """

        plist = self._params.get(param)
        if plist is None:
            raise ValueError(f"Unknown parameter {param}.")

        if param in ["sca_hhv", "sca_low", "sca_win"]:
            if value < self._params[param][1][0] or value > self._params[param][1][1]:
                raise ValueError(
                    f"Error: {param} value must be in range [{self._params[param][1][0]}, {self._params[param][1][1]}]"
                )

        # ------------------------------------------------------------------
        if param == "sca_win":
            asw = self.send_cmd("?%s" % self._params[param][0])
            lasw = asw.split()
            # SCA in window mode
            if len(lasw) == 3:
                mode = lasw[0]
                low_th = lasw[1]
                value = mode + " " + low_th + " " + str(value)
            else:
                print("It is not possible to set a window value sca_mode = INT.")
                return

        # ----------------------------------------------------------------

        rcmd = plist[0]
        cmd = f"{rcmd} {value}"
        # print(f"SEND: {cmd}")
        self.send_cmd(cmd)

    def send_cmd(self, command):
        """ Send a command to the controller
            Args:
              command (str): The command string
            Returns:
              Answer from the controller if ? in the command
        """
        log_info(self, f"send_cmd '{command}' ")

        command += "\r\n"
        # print("SEND CMD: %s"%command)
        if command.startswith("?"):

            if command.startswith("?INFO"):
                asw = self.comm.write_readlines(
                    command.encode(), 20, eol="\r\n", timeout=self.timeout
                )
                asw = "\n".join([line.decode() for line in asw])
            else:
                asw = self.comm.write_readline(
                    command.encode(), eol="\r\n", timeout=self.timeout
                ).decode()

            if "ERROR" in asw:
                error_msg = f"Timeout with {self.comm} and command: {command}"
                print(error_msg)
                gevent.sleep(0.5)
                self.comm.flush()

            return asw

        else:
            self.comm.write(command.encode(), timeout=self.timeout)

    def _clear(self):
        """ Reset the unit.
            Resets the internal hardware, resets the current settings to the default values
            and saves them in the internal non-volatile memory.
            In the current version of the firmware (01.02) the default settings are:
            ECHO OFF, GPIBX1, HVOLT = 200, LLTH = 1, WIN = 1V, GPIB_ADDR = 9. 
        """
        self.send_cmd("RESET")

    def _show(self):
        """ Display all main parameters and values of the ace module
            Prints:
              device ID, communication information,
              high voltage value, SCA low voltage, SCA high voltage,
              peaking time and gain
        """
        log_info(self, "show")
        info_list = []

        head_limits = self.send_cmd("?HLIM").split()
        if len(head_limits) == 3:
            maxhcurr, headresistor, maxhtemp = head_limits
        elif len(head_limits) == 2:
            maxhcurr, maxhtemp = head_limits
            headresistor = "N/A"
        else:
            maxhcurr = headresistor = maxhtemp = "N/A"

        maxhtemp = maxhtemp + " \xB0C"
        currtemp = self.send_cmd("?HTEMP") + " \xB0C"

        hv, hstate = self.send_cmd("?HVOLT").split()

        sca = self.send_cmd("?SCA").split()
        if len(sca) == 3:
            sca_mode, sca_low, sca_win = sca
        else:
            sca_mode, sca_low = sca
            sca_win = "N/A"

        info_list.append(f"VERSION:                        {self.send_cmd('?VER'):17s}")
        # info_list.append(f"NAME:                           {self.send_cmd('?NAME')}")
        info_list.append(
            f"SERIAL ADDRESS:                 {self.send_cmd('?ADDR'):17s}"
        )
        info_list.append(
            f"GPIB ADDRESS:                   {self.send_cmd('?GPIB'):17s}"
        )
        info_list.append(
            f"HEAD MAX CURRENT:               {maxhcurr +' mA':17s}  (range [0, 25])"
        )
        info_list.append(
            f"HEAD MAX TEMPERATURE:           {maxhtemp:17s}  (range=[0, 50])"
        )
        info_list.append(f"HEAD CURRENT TEMPERATURE:       {currtemp:17s}")
        info_list.append(
            f"HEAD BIAS VOLTAGE SETPOINT:     {hv +' V' + ' (' + hstate + ')':17s}  (range=[0, 600])"
        )
        # info_list.append(f"HEAD CURRENT BIAS VOLTAGE:      {self.send_cmd('?HVMON'):17s}")
        info_list.append(
            f"COUNTING SOURCE:                {self.send_cmd('?CSRC'):17s}"
        )
        info_list.append(f"SCA MODE:                       {sca_mode:17s}")
        info_list.append(
            f"SCA LOW:                        {sca_low +' V':17s}  (range=[-0.2, 5])"
        )
        info_list.append(
            f"SCA WIN:                        {sca_win +' V':17s}  (range=[0, 5])"
        )
        info_list.append(
            f"SCA PUSLE SHAPING:              {self.send_cmd('?OUT') +' ns':17s}  (range=[5, 10, 20, 30])"
        )
        info_list.append(
            f"GATE IN MODE:                   {self.send_cmd('?GLVL'):17s}"
        )
        info_list.append(
            f"TRIGGER IN MODE:                {self.send_cmd('?TLVL'):17s}"
        )
        info_list.append(
            f"SYNC OUTPUT MODE:               {self.send_cmd('?SOUT'):17s}"
        )
        info_list.append(
            f"ALARM MODE:                     {self.send_cmd('?ALMODE'):17s}"
        )
        info_list.append(
            f"RATE METER ALARM THRESHOLD:     {self.send_cmd('?ALRATE'):17s}  (range=[0, 1e8])"
        )
        info_list.append(
            f"ALARM THRESHOLD:                {self.send_cmd('?ALCURR') +' mA':17s}  (range=[0, 25])"
        )
        info_list.append(
            f"BUFFER OPTIONS:                 {self.send_cmd('?BUFFER'):17s}"
        )
        info_list.append(
            f"DATA FORMAT:                    {self.send_cmd('?DFORMAT'):17s}"
        )

        return info_list

    @autocomplete_property
    def counters(self):
        """ Standard counter namespace """

        if self.sca_mode == "INT":
            return counter_namespace(
                [self._cc.counters.sca_low, self._cc.counters.counts]
            )
        else:
            return self._cc.counters

    # ---- END USER METHODS ------------------------------------------------------------

    @property
    def name(self):
        return self._name

    @property
    def state(self):
        """ Returns the state of the head.
            Answer: {OK | NOHEAD | OVCURR | OVTEMP | HVERR}
            Returns {NOHEAD} when the power cable of the head is disconnected. 
            Returns {OVCURR | OVTEMP | HVERR} when one of theses parameters is out of range.
            Ranges are set by HLIM command. 
        """

        log_debug(self, "Ace:state")
        return self.send_cmd("?HSTATE")

    @property
    def sca_mode(self):
        """ Get the SCA mode: INT|WIN """
        log_debug(self, "Ace:sca_mode")
        return self._get_value("sca_mode")

    @sca_mode.setter
    def sca_mode(self, value):
        """ Set the SCA mode: INT|WIN
        """
        log_debug(self, "Ace:sca_mode.setter %s" % value)

        if value not in [x.value for x in self._ScaMode]:
            raise ValueError(
                f"Wrong value should be in { [ str(x.value) +' ('+ str(x.name)+')' for x in self._ScaMode ] }"
            )

        value = self._ScaMode(value).name
        self._set_value("sca_mode", value)

    @property
    def sca_low(self):
        """ Get the SCA low value"""
        log_debug(self, "Ace:sca_low")
        return float(self._get_value("sca_low"))

    @sca_low.setter
    def sca_low(self, value):
        """ Set the SCA low value (float)
        """
        log_debug(self, "Ace:sca_low.setter %s" % value)
        self._set_value("sca_low", value)

    @property
    def sca_win(self):
        """ Get the SCA window value"""
        log_debug(self, "Ace:sca_win")
        ans = self._get_value("sca_win")
        try:
            return float(ans)
        except ValueError:
            return ans

    @sca_win.setter
    def sca_win(self, value):
        """ Set the SCA window value (float)
        """
        log_debug(self, "Ace:sca_win.setter %s" % value)
        self._set_value("sca_win", value)

    @property
    def sca_hhv(self):
        """ Get the high voltage setpoint"""
        log_debug(self, "Ace:sca_hhv")
        ans = self._get_value("sca_hhv")
        try:
            return float(ans)
        except ValueError:
            return ans

    @sca_hhv.setter
    def sca_hhv(self, value):
        """ Set the high voltage setpoint (float)
        """
        log_debug(self, "Ace:sca_hhv.setter %s" % value)
        self._set_value("sca_hhv", value)

    @property
    def counting_source(self):
        """
        Query the current counting source.
        Answer: {SCA | TRG} 
        Returns the current counting source Trigger input of the front panel
        when TRG is set or Head input from rear panel when SCA is set. 
        """
        log_debug(self, "Ace:counting_source")
        return self._get_value("counting_source")

    @counting_source.setter
    def counting_source(self, value):
        """
        Selects the current counting source {1=SCA | 2=TRG}
        When TRG is selected, the trigger input is used as source of the counter. 
        In this mode ACE is used as a one channel 50 MHz counter. 
        In this mode the input signal should be TTL or NIM. 
        When SCA is selected the Rear input Head signal is used as source. 
        The SCA mode is the standard mode to use APD Head. 
        """

        log_debug(self, "Ace:counting_source.setter %s" % value)

        if value not in [x.value for x in self._CountingSource]:
            raise ValueError(
                f"Wrong value should be in { [ str(x.value) +' ('+ str(x.name)+')' for x in self._CountingSource ] }"
            )

        value = self._CountingSource(value).name
        self._set_value("counting_source", value)

    @property
    def counter_status(self):
        log_debug(self, "Ace:counter_status")
        asw = self._get_value("counter_status")
        lasw = asw.split()
        llasw = []
        counter_state = self._state_labels[lasw[0]]
        llasw.append("Actual counter state: %s" % counter_state)
        nremain = lasw[1]
        llasw.append("Remain count before end of repetitive count: %s" % nremain)
        ntotal = asw[2]
        llasw.append("Total number of count: %s" % ntotal)
        if len(lasw) > 3:
            time = lasw[3]
            llasw.append("Integration time: %s" % time)
            counts = lasw[4]
            llasw.append("Actual value of the count running: %s" % counts)
        return ShellStr("\n".join(llasw))

    def start_counting(self, count_time):
        us_time = int(1e6 * count_time)

        if us_time < 1 or us_time > 2 ** 31:
            raise ValueError(
                f"Ace counting time must be in range [0.000001, 2147.483648] second "
            )

        self.send_cmd("TCT %d" % us_time)

    def stop_counting(self):
        self.send_cmd("STCT")

    @property
    def counts(self):
        return float(self.send_cmd("?CT DATA").split()[4])

    @property
    def hvmon(self):
        return float(self._get_value("hvmon"))

    @property
    def hvcur(self):
        return float(self._get_value("hvcur"))

    @property
    def htemp(self):
        return float(self._get_value("htemp"))

    @property
    def alarm_mode(self):
        log_debug(self, "Ace:alarm_mode")
        return self._get_value("alarm_mode")

    @property
    def head_bias_voltage(self):
        log_debug(self, "Ace:head_bias_voltage")
        return float(self._get_value("hvmon"))

    # ---- SOFT AXIS METHODS TO MAKE THE ACE SCANABLE -----------

    def _create_soft_axes(self, config):

        axes_conf = config.get("axes", [])

        for conf in axes_conf:

            axis_name = conf["name"].strip()
            chan = conf["tag"].strip()
            name = axis_name if axis_name is not "" else self.name + "_axis_%s" % chan

            self._soft_axes[chan] = SoftAxis(
                name,
                self,
                position=partial(
                    self.axis_position, channel=chan
                ),  # "axis_%s_position"%chan,
                move=partial(self.axis_move, channel=chan),  # "axis_%s_move"%chan,
                stop=partial(self.axis_stop, channel=chan),  # "axis_%s_stop"%chan,
                state=partial(self.axis_state, channel=chan),  # "axis_%s_state"%chan,
                low_limit=float(self._params["sca_%s" % chan][1][0]),
                high_limit=float(self._params["sca_%s" % chan][1][1]),
                tolerance=self._axes_tolerance[chan],
                unit="V",
            )

    def axis_position(self, channel=None):
        """ Return the channel value as the current position of the associated soft axis"""
        if channel == "low":
            return self.sca_low
        elif channel == "win":
            return self.sca_win
        elif channel == "hhv":
            return self.sca_hhv
        else:
            raise ValueError(f"Ace.axis_position: unknown channel {channel}")

    def axis_move(self, pos, channel=None):
        """ Set the channel to a new value as the new position of the associated soft axis"""

        chan = "sca_%s" % channel

        if (pos > self._params[chan][1][1]) or (pos < self._params[chan][1][0]):
            ValueError(
                f"Error: cannot move outside limits [{self._params[chan][1][0]}, {self._params[chan][1][1]}] "
            )

        self._axes_state[channel] = AxisState("MOVING")
        self._set_value(chan, pos)
        gevent.sleep(0.1)
        self._axes_state[channel] = AxisState("READY")

    def axis_stop(self, channel=None):
        """ Stop the motion of the associated soft axis """
        pass

    def axis_state(self, channel=None):
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

        return self._axes_state[channel]

    # ---- COUNTERS METHODS ------------------------

    def _create_counters(self, config):

        cnts_conf = config.get("counters")
        if cnts_conf is None:
            return

        self._cc = AceCC(self.name + "_cc", self)

        for conf in cnts_conf:

            cnt_name = conf["name"].strip()
            chan = conf["tag"].strip()
            unit = conf.get("unit")
            mode = conf.get("mode", "SINGLE")
            name = cnt_name if cnt_name is not "" else self.name + "_cnt_%s" % chan

            cnt = self._cc.create_counter(SamplingCounter, name, unit=unit, mode=mode)
            cnt.tag = chan
