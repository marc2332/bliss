# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
-   class: Ace
    module: sca.ace
    plugin: bliss
    name: acedet
    timeout: 10
    #serial:
    #    url: ser2net://lid00limace:28000/dev/ttyS0
    gpib:
        url: tango_gpib_device_server://id10/gpib_40/0
        pad: 9
    axes:
        - axis_name: apdthl
          tag: low

        - axis_name: apdwin
          tag: win

        - axis_name: apdhv
          tag: hhv

    counters:
        - counter_name: apdcnt
          tag: counts

        - counter_name: apdtemp
          tag: htemp
          unit: °C
          mode: MEAN

        - counter_name: apdcurr
          tag: hcurr
          unit: uA
          mode: MEAN

        - counter_name: apdhvmon
          tag: hvmon
          unit: V
          mode: MEAN
"""

import enum
import gevent
from gevent import event

from functools import partial

from bliss.shell.standard import ShellStr
from bliss import global_map
from bliss.comm.util import get_comm
from bliss.common.logtools import log_debug, log_info
from bliss.common.soft_axis import SoftAxis
from bliss.common.axis import AxisState

from bliss.common.counter import Counter, SamplingCounter
from bliss.controllers.counter import CounterController, SamplingCounterController


from bliss.scanning.acquisition.counter import BaseCounterAcquisitionSlave

from bliss.common.utils import autocomplete_property
from bliss.common.protocols import counter_namespace

from bliss.common.session import get_current_session
from bliss.common.greenlet_utils import protect_from_kill


class AceIAS(BaseCounterAcquisitionSlave):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._reading_event = event.Event()

    def prepare(self):
        pass

    def start(self):
        self._stop_flag = False
        self._reading_event.clear()

    def stop(self):
        self._stop_flag = True
        self._reading_event.set()
        if not self.device.ace.counter_is_ready:
            self.device.ace.counting_stop()

    def trigger(self):
        self.device.ace.counting_start(self.count_time)
        gevent.sleep(self.count_time)
        self._reading_event.set()

    def reading(self):
        self._reading_event.wait()
        self._reading_event.clear()
        with gevent.Timeout(2.0):
            while not self._stop_flag:
                status, nremain, ntotal, ctime, counts = self.device.read_counts()
                if status == "D":
                    self._emit_new_data([[counts]])
                    break
                else:
                    gevent.sleep(0.001)


class AceICC(CounterController):
    def __init__(self, name, ace):
        super().__init__(name)
        self.ace = ace

    def get_acquisition_object(self, acq_params, ctrl_params, parent_acq_params):
        return AceIAS(self, ctrl_params=ctrl_params, **acq_params)

    def get_default_chain_parameters(self, scan_params, acq_params):

        try:
            count_time = acq_params["count_time"]
        except KeyError:
            count_time = scan_params["count_time"]

        try:
            npoints = acq_params["npoints"]
        except KeyError:
            npoints = scan_params["npoints"]

        params = {"count_time": count_time, "npoints": npoints}

        return params

    def read_counts(self):
        """ returns status, nremain, ntotal, time, counts """
        return self.ace.putget("?CT DATA").split()


class AceSCC(SamplingCounterController):
    def __init__(self, name, ace):
        super().__init__(name)
        self.ace = ace

    def read_all(self, *counters):
        values = []
        for cnt in counters:
            if cnt.tag == "hcurr":
                values.append(self.ace.head_hcurr)
            elif cnt.tag == "hvmon":
                values.append(self.ace.head_hvmon)
            elif cnt.tag == "htemp":
                values.append(self.ace.head_temp)
            else:
                # returned number of data must be equal to the length of '*counters'
                # so raiseError if one of the received counter is not handled
                raise ValueError(f"Unknown counter {cnt} with tag {cnt.tag} !")

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
        self._comm = get_comm(config)
        self._timeout = config.get("timeout", 3.0)
        self._count_time = None

        gpib = config.get("gpib")
        if gpib:
            gpib["eol"] = ""
            self._txterm = b""
            self._rxterm = b"\n"
        else:
            self._txterm = b"\r"
            self._rxterm = b"\r\n"

        global_map.register(self, children_list=[self._comm])

        self._comm.open()

        self._state_labels = {"D": "ready", "R": "running", "W": "wait", "A": "abort"}

        # --- obtain the available parameters for the given model ----
        self._model2params = {
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
                "hcurr": ["HCURR"],
                "htemp": ["HTEMP"],
                "counts": ["CT DATA"],
            }
        }

        self._mid = 0  # just one model for now
        self._params = self._model2params[self._mid]

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
        ans = self.putget(cmd)
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
            asw = self.putget("?%s" % self._params[param][0])
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
        self.putget(cmd)

    @protect_from_kill
    def putget(self, command):
        """ Send a command to the controller
            Args:
              command (str): The command string
            Returns:
              Answer from the controller if ? in the command
        """
        log_info(self, f"putget '{command}' ")

        cmd = command.encode() + self._txterm

        if command.startswith("?"):

            if command.startswith("?INFO"):
                asw = self._comm.write_readlines(
                    cmd, 20, eol=self._rxterm, timeout=self._timeout
                )
                asw = "\n".join([line.decode() for line in asw])
            else:
                asw = self._comm.write_readline(
                    cmd, eol=self._rxterm, timeout=self._timeout
                ).decode()

            if "ERROR" in asw:
                error_msg = f"Timeout with {self._comm} and command: {command}"
                print(error_msg)
                gevent.sleep(0.5)
                self._comm.flush()

            return asw

        else:
            self._comm.write(cmd, timeout=self._timeout)

    def _clear(self):
        """ Reset the unit.
            Resets the internal hardware, resets the current settings to the default values
            and saves them in the internal non-volatile memory.
            In the current version of the firmware (01.02) the default settings are:
            ECHO OFF, GPIBX1, HVOLT = 200, LLTH = 1, WIN = 1V, GPIB_ADDR = 9. 
        """
        self.putget("RESET")

    def _show(self):
        """ Display all main parameters and values of the ace module
            Prints:
              device ID, communication information,
              high voltage value, SCA low voltage, SCA high voltage,
              peaking time and gain
        """
        log_info(self, "show")
        info_list = []

        version = self.putget("?VER")
        info_list.append(f"ACE card: {self.name}, {version}")
        info_list.append(self._comm.__info__())

        head_limits = self.putget("?HLIM").split()
        if len(head_limits) == 3:
            maxhcurr, headresistor, maxhtemp = head_limits
        elif len(head_limits) == 2:
            maxhcurr, maxhtemp = head_limits
            headresistor = "N/A"
        else:
            maxhcurr = headresistor = maxhtemp = "N/A"

        maxhtemp = maxhtemp + " \xB0C"
        currtemp = self.putget("?HTEMP") + " \xB0C"

        hv, hstate = self.putget("?HVOLT").split()

        sca = self.putget("?SCA").split()
        if len(sca) == 3:
            sca_mode, sca_low, sca_win = sca
        else:
            sca_mode, sca_low = sca
            sca_win = "N/A"

        info_list.append(
            f"HEAD MAX CURRENT:               {maxhcurr +' mA':17s}  (range=[0, 25])"
        )
        info_list.append(
            f"HEAD MAX TEMPERATURE:           {maxhtemp:17s}  (range=[0, 50])"
        )
        info_list.append(f"HEAD CURRENT TEMPERATURE:       {currtemp:17s}")
        info_list.append(
            f"HEAD BIAS VOLTAGE SETPOINT:     {hv +' V' + ' (' + hstate + ')':17s}  (range=[0, 600])"
        )
        info_list.append(f"COUNTING SOURCE:                {self.putget('?CSRC'):17s}")
        info_list.append(f"SCA MODE:                       {sca_mode:17s}")
        info_list.append(
            f"SCA LOW:                        {sca_low +' V':17s}  (range=[-0.2, 5])"
        )
        info_list.append(
            f"SCA WIN:                        {sca_win +' V':17s}  (range=[0, 5])"
        )
        info_list.append(
            f"SCA PUSLE SHAPING:              {self.putget('?OUT') +' ns':17s}  (range=[5, 10, 20, 30])"
        )
        info_list.append(f"GATE IN MODE:                   {self.putget('?GLVL'):17s}")
        info_list.append(f"TRIGGER IN MODE:                {self.putget('?TLVL'):17s}")
        info_list.append(f"SYNC OUTPUT MODE:               {self.putget('?SOUT'):17s}")
        info_list.append(
            f"ALARM MODE:                     {self.putget('?ALMODE'):17s}"
        )
        info_list.append(
            f"RATE METER ALARM THRESHOLD:     {self.putget('?ALRATE'):17s}  (range=[0, 1e8])"
        )
        info_list.append(
            f"ALARM THRESHOLD:                {self.putget('?ALCURR') +' mA':17s}  (range=[0, 25])"
        )
        info_list.append(
            f"BUFFER OPTIONS:                 {self.putget('?BUFFER'):17s}"
        )
        info_list.append(
            f"DATA FORMAT:                    {self.putget('?DFORMAT'):17s}"
        )
        info_list.append("\nAxes")
        info_list.append("----")
        for axis in self._soft_axes:
            info_list.append(f"{axis}: {self._soft_axes[axis].name}")
        info_list.append("\nCounters")
        info_list.append("--------")
        for cnt in self.counters:
            info_list.append(f"{cnt.tag}: {cnt.name}")

        return info_list

    @autocomplete_property
    def counters(self):
        """ Standard counter namespace """

        if self.sca_mode == "INT":
            return counter_namespace(
                [self._scc.counters.sca_low, self._icc.counters.counts]
            )
        else:
            return self._scc.counters + self._icc.counters

    # ---- END USER METHODS ------------------------------------------------------------

    @property
    def name(self):
        return self._name

    @property
    def sca_mode(self):
        """ Get the SCA mode: INT|WIN """
        log_debug(self, "Ace:sca_mode")
        return self._get_value("sca_mode")

    @sca_mode.setter
    def sca_mode(self, value):
        """ Set the SCA mode: INT|WIN

        INT: count all photons from low energy at the limit of noise to high energy
        WIN: In window mode the counter make the difference between Low-level discriminator count 
             and High-level discriminator count. Users do not access to high-level discriminator 
             threshold but only the difference between low level and high level. 
             This difference is the window size. 
             To resolve PHD a window of 10 to 30mv is a good compromise between count rate and resolution.
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
    def hhv_state(self):
        """ Get the high voltage state: ON|OFF"""
        log_debug(self, "Ace:hhv_state")
        ans = self.putget("?HVOLT").split()[1]
        return ans

    def hhv_on(self):
        log_debug(self, "Ace:hhv_on")
        cmd = f"HVOLT {self.sca_hhv} ON"
        self.putget(cmd)

    def hhv_off(self):
        log_debug(self, "Ace:hhv_off")
        cmd = f"HVOLT {self.sca_hhv} OFF"
        self.putget(cmd)

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

    def counting_start(self, count_time):

        # ACE can work in 3 different modes of acquisition:

        # 1) Software triggered => "TCT coun_time" => starts counting when cmd received by FirmeWare

        # 2) Hardware triggered => "TCT coun_time EXT" => starts counting when a trigger signal is send to the Trigger input.

        # 3) 'Continous' mode => Each count on the SCA head produces a signal/pulse sent on the output of the ACE ( SCA OUT TTL or NIM)
        #    In this case no need to start counting using the TCT command.

        self._count_time = count_time

        if self.counter_is_ready():

            us_time = int(1e6 * count_time)

            if us_time < 1 or us_time > 2 ** 31:
                raise ValueError(
                    "Ace counting time must be in range [0.000001, 2147.483648] second "
                )

            self.putget("TCT %d" % us_time)
        else:
            raise RuntimeError("Ace counter not ready!")

    def counting_stop(self):
        self.putget("STCT")

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
            itime = lasw[3]
            llasw.append("Integration time: %s" % itime)
            counts = lasw[4]
            llasw.append("Actual value of the count running: %s" % counts)
        return ShellStr("\n".join(llasw))

    def counter_is_ready(self):
        asw = self._get_value("counter_status")
        lasw = asw.split()
        if lasw[0] != "D":
            return False
        else:
            return True

    @property
    def counts(self):
        """ Read the counts value of the on-going or last TCT measurement """
        log_debug(self, "Ace:counts")
        ans = self.putget("?CT DATA").split()
        return float(ans[4])

    @property
    def head_state(self):
        """ Returns the state of the head.
            Answer: {OK | NOHEAD | OVCURR | OVTEMP | HVERR}
            Returns {NOHEAD} when the power cable of the head is disconnected. 
            Returns {OVCURR | OVTEMP | HVERR} when one of theses parameters is out of range.
            Ranges are set by HLIM command. 
        """

        log_debug(self, "Ace:state")
        return self.putget("?HSTATE")

    @property
    def head_hvmon(self):
        log_debug(self, "Ace:hvmon")
        return float(self._get_value("hvmon"))

    @property
    def head_hcurr(self):
        log_debug(self, "Ace:hcurr")
        return float(self._get_value("hcurr"))

    @property
    def head_temp(self):
        log_debug(self, "Ace:htemp")
        return float(self._get_value("htemp"))

    @property
    def alarm_mode(self):
        log_debug(self, "Ace:alarm_mode")
        return self._get_value("alarm_mode")

    # ---- SOFT AXIS METHODS TO MAKE THE ACE SCANABLE -----------

    def _create_soft_axes(self, config):

        axes_conf = config.get("axes", [])

        for conf in axes_conf:

            name = conf["axis_name"].strip()
            chan = conf["tag"].strip()

            self._soft_axes[chan] = SoftAxis(
                name,
                self,
                position=partial(self._axis_position, channel=chan),
                move=partial(self._axis_move, channel=chan),
                stop=partial(self._axis_stop, channel=chan),
                state=partial(self._axis_state, channel=chan),
                low_limit=float(self._params["sca_%s" % chan][1][0]),
                high_limit=float(self._params["sca_%s" % chan][1][1]),
                tolerance=self._axes_tolerance[chan],
                unit="V",
            )

    def _axis_position(self, channel=None):
        """ Return the channel value as the current position of the associated soft axis"""
        if channel == "low":
            return self.sca_low
        elif channel == "win":
            return self.sca_win
        elif channel == "hhv":
            return self.sca_hhv
        else:
            raise ValueError(f"Ace.axis_position: unknown channel {channel}")

    def _axis_move(self, pos, channel=None):
        """ Set the channel to a new value as the new position of the associated soft axis"""

        chan = "sca_%s" % channel

        if (pos > self._params[chan][1][1]) or (pos < self._params[chan][1][0]):
            ValueError(
                f"Error: cannot move outside limits [{self._params[chan][1][0]}, {self._params[chan][1][1]}] "
            )

        self._axes_state[channel] = AxisState("MOVING")
        self._set_value(chan, pos)
        # gevent.sleep(0.1)
        self._axes_state[channel] = AxisState("READY")

    def _axis_stop(self, channel=None):
        """ Stop the motion of the associated soft axis """
        pass

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

        return self._axes_state[channel]

    # ---- COUNTERS METHODS ------------------------

    def _create_counters(self, config, export_to_session=True):

        cnts_conf = config.get("counters")
        if cnts_conf is None:
            return

        self._scc = AceSCC(self.name, self)
        self._icc = AceICC(self.name, self)

        self._scc.max_sampling_frequency = config.get("max_sampling_frequency", 1)

        for conf in cnts_conf:

            name = conf["counter_name"].strip()
            chan = conf["tag"].strip()
            unit = conf.get("unit")
            mode = conf.get("mode", "SINGLE")

            if chan == "counts":
                cnt = self._icc.create_counter(Counter, name, unit=unit)
            else:
                cnt = self._scc.create_counter(
                    SamplingCounter, name, unit=unit, mode=mode
                )

            cnt.tag = chan

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
