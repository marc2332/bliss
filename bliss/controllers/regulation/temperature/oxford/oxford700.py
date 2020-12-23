# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import enum
from bliss.common.logtools import log_info
from bliss.controllers.regulator import Controller
from .oxfordcryo import OxfordCryostream

from bliss.controllers.regulation.temperature.oxford import OxfordInput as Input
from bliss.controllers.regulation.temperature.oxford import OxfordOutput as Output
from bliss.controllers.regulation.temperature.oxford import OxfordLoop as Loop


"""
   - class: oxford700
     plugin: regulation
     module: temperature.oxford.oxford700
     serial:
        url: rfc2217://lid032:28008
        
     inputs:
        - name: ox_in
     outputs:
        - name: ox_out
     ctrl_loops:
        - name: ox_loop
          input: $ox_in
          output: $ox_out
          ramprate: 350   # (optional) default/starting ramprate [K/hour]
"""


class Oxford700(Controller):
    """
    Oxford700 Regulation controller
    """

    class TAGTOCHAN(enum.IntEnum):
        GAS = 1
        EVAP = 2
        SUCT = 3
        FLOW = 4

    def __init__(self, config):
        super().__init__(config)

        self.hw_controller = None
        self._ramp_rate = None
        self._ramprate_min = 1
        self._ramprate_max = 360

    def __info__(self):
        return self.hw_controller.statusPacket.__info__()

    # ------ init methods ------------------------

    def initialize_controller(self):
        """ 
        Initializes the controller (including hardware).
        """

        self.hw_controller = OxfordCryostream(self.config)

    def initialize_input(self, tinput):
        """
        Initializes an Input class type object
        """
        if tinput.channel is None:
            tinput._channel = 1

        elif tinput.channel not in list(self.TAGTOCHAN):
            raise ValueError(
                f"wrong channel '{tinput.channel}' for the input {tinput}. Should be in {list(self.TAGTOCHAN)}"
            )

    def initialize_output(self, toutput):
        """
        Initializes an Output class type object
        """
        if toutput.channel is None:
            toutput._channel = 1

        elif toutput.channel not in list(self.TAGTOCHAN):
            raise ValueError(
                f"wrong channel '{toutput.channel}' for the input {toutput}. Should be in {list(self.TAGTOCHAN)}"
            )

    def initialize_loop(self, tloop):
        """
        Initializes a Loop class type object
        """
        pass

    # ------ get methods ------------------------

    def read_input(self, tinput):
        """
        Reads an Input class type object
        """
        log_info(self, "Controller:read_input: %s" % (tinput))

        if tinput.channel == self.TAGTOCHAN.GAS:
            return self.hw_controller.read_gas_temperature()
        elif tinput.channel == self.TAGTOCHAN.EVAP:
            return self.hw_controller.read_evap_temperature()
        elif tinput.channel == self.TAGTOCHAN.SUCT:
            return self.hw_controller.read_suct_temperature()

    def read_output(self, toutput):
        """
        Reads an Output class type object
        """
        log_info(self, "Controller:read_output: %s" % (toutput))

        if toutput.channel == self.TAGTOCHAN.GAS:
            return self.hw_controller.read_gas_heat()
        elif toutput.channel == self.TAGTOCHAN.EVAP:
            return self.hw_controller.read_evap_heat()
        elif toutput.channel == self.TAGTOCHAN.SUCT:
            return self.hw_controller.read_suct_heat()
        elif toutput.channel == self.TAGTOCHAN.FLOW:
            return self.hw_controller.read_gas_flow()

    def state_input(self, tinput):
        """
        Return a string representing state of an Input object
        """
        log_info(self, "Controller:state_input: %s" % (tinput))
        return self.hw_controller.read_alarm()

    def state_output(self, toutput):
        """
        Return a string representing state of an Output object
        """
        log_info(self, "Controller:state_output: %s" % (toutput))
        rmode = self.hw_controller.read_run_mode()
        phase = self.hw_controller.read_phase()
        return (rmode, phase)

    # ------ PID methods ------------------------

    def set_kp(self, tloop, kp):
        """
        Set the PID P value
        """
        log_info(self, "Controller:set_kp: %s %s" % (tloop, kp))
        pass

    def get_kp(self, tloop):
        """
        Get the PID P value
        """
        log_info(self, "Controller:get_kp: %s" % (tloop))
        return "N/A"

    def set_ki(self, tloop, ki):
        """
        Set the PID I value
        """
        log_info(self, "Controller:set_ki: %s %s" % (tloop, ki))
        pass

    def get_ki(self, tloop):
        """
        Get the PID I value
        """
        log_info(self, "Controller:get_ki: %s" % (tloop))
        return "N/A"

    def set_kd(self, tloop, kd):
        """
        Set the PID D value
        """
        log_info(self, "Controller:set_kd: %s %s" % (tloop, kd))
        pass

    def get_kd(self, tloop):
        """
        Reads the PID D value
        """
        log_info(self, "Controller:get_kd: %s" % (tloop))
        return "N/A"

    def start_regulation(self, tloop):
        """
        Starts the regulation process
        """
        log_info(self, "Controller:start_regulation: %s" % (tloop))
        pass

    def stop_regulation(self, tloop):
        """
        Stops the regulation process
        """
        log_info(self, "Controller:stop_regulation: %s" % (tloop))
        pass

    # ------ setpoint methods ------------------------

    def set_setpoint(self, tloop, sp, **kwargs):
        """
        Set the current setpoint (target value)
        """
        # with oxford the setpoint is given through ramp and cool cmds only
        log_info(self, "Controller:set_setpoint: %s %s" % (tloop, sp))
        pass

    def get_setpoint(self, tloop):
        """
        Get the current setpoint (target value)
        """
        log_info(self, "Controller:get_setpoint: %s" % (tloop))
        return self.hw_controller.read_target_temperature()

    def get_working_setpoint(self, tloop):
        """
        Get the current working setpoint (setpoint along the ramp)
        """
        return self.hw_controller.read_gas_setpoint()

    # ------ setpoint ramping methods (optional) ------------------------

    def start_ramp(self, tloop, sp, **kwargs):
        """
        Start ramping to a setpoint
        """
        log_info(self, "Controller:start_ramp: %s %s" % (tloop, sp))

        rate = self.get_ramprate(tloop)

        if rate == 0:
            if sp < self.get_setpoint(tloop):
                self.hw_controller.cool(sp)
            else:
                self.hw_controller.ramp(self._ramprate_max, sp)
        else:
            self.hw_controller.ramp(rate, sp)

    def stop_ramp(self, tloop):
        """
        Stop the current ramping
        """
        log_info(self, "Controller:stop_ramp: %s" % (tloop))
        self.hw_controller.pause()

    def is_ramping(self, tloop):
        """
        Get the ramping status
        """
        log_info(self, "Controller:is_ramping: %s" % (tloop))
        return self.hw_controller.is_ramping()

    def set_ramprate(self, tloop, rate):
        """
        Set the ramp rate in [K/hr]
        """
        log_info(self, "Controller:set_ramprate: %s %s" % (tloop, rate))

        if rate == 0:
            self._ramp_rate = 0
        else:
            rate = max(rate, self._ramprate_min)
            self._ramp_rate = min(rate, self._ramprate_max)

        # ramp to current setpoint with the new ramprate
        sp = self.get_setpoint(tloop)
        self.start_ramp(tloop, sp)

    def get_ramprate(self, tloop):
        """
        Get the ramp rate in [K/hr]
        """
        log_info(self, "Controller:get_ramprate: %s" % (tloop))

        if self._ramp_rate is None:
            cur_rate = self.hw_controller.read_ramprate()
            self._ramp_rate = (
                cur_rate
                if cur_rate != 0
                else tloop.config.get("ramprate", self._ramprate_max)
            )

        return self._ramp_rate

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
        raise NotImplementedError

    # --- Custom methods ------------------------------

    def turbo(self, enable):
        """ Switch on/off the turbo gas flow"""
        self.hw_controller.turbo(bool(enable))

    def cool(self, temp):
        """ Make gas temperature decrease to a set value as quickly as possible
            Args:
              temp (float): final temperature [K]
        """
        self.hw_controller.cool(temp)

    def plat(self, duration):
        """ Maintain temperature fixed for a certain time.
            Args:
              duration (int): time [minutes]
        """
        self.hw_controller.plat(duration)

    def pause(self):
        """ Start temporary hold """
        self.hw_controller.pause()

    def resume(self):
        """Exit temporary hold """
        self.hw_controller.resume()

    def end(self, rate):
        """ System shutdown with Ramp Rate to go back to temperature of 300K
            Args:
              rate (int): ramp rate [K/hour]
        """
        self.hw_controller.end(rate)

    def hold(self):
        """ Maintain temperature fixed indefinitely, until start issued """
        self.hw_controller.hold()

    def stop(self):
        """ Immediately halt the Cryostream Cooler,turning off the pump and
            all the heaters - used for emergency only
        """
        self.hw_controller.stop()

    def purge(self):
        """ Warm up the Coldhead as quickly as possible """
        self.hw_controller.purge()

    def restart(self):
        """ Restart a Cryostream which has shutdown """
        self.hw_controller.restart()
