# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


from bliss.common.logtools import log_info
from bliss.controllers.regulator import Controller
from .oxfordcryo import OxfordCryostream


class Oxford700(Controller):
    """
    Oxford700 Regulation controller
    """

    def __init__(self, config):
        super().__init__(config)

        self.hw_controller = None
        # self._ramp_rate = None
        # self._setpoint = None
        self._is_paused = False

    def __info__(self):
        return self.hw_controller.statusPacket.__info__()

    # ------ init methods ------------------------

    def initialize_controller(self):
        """ 
        Initializes the controller (including hardware).
        """

        self.hw_controller = OxfordCryostream(self.config)

        # self._ramp_rate = self.hw_controller.read_ramprate()
        # self._setpoint = self.hw_controller.read_target_temperature()
        self._is_paused = self.hw_controller.is_paused()

    def initialize_input(self, tinput):
        """
        Initializes an Input class type object

        Args:
           tinput:  Input class type object          
        """
        pass

    def initialize_output(self, toutput):
        """
        Initializes an Output class type object

        Args:
           toutput:  Output class type object          
        """
        pass

    def initialize_loop(self, tloop):
        """
        Initializes a Loop class type object

        Args:
           tloop:  Loop class type object          
        """
        pass

    # ------ get methods ------------------------

    def read_input(self, tinput):
        """
        Reads an Input class type object
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tinput:  Input class type object 

        Returns:
           read value  (in input unit)    
        """
        log_info(self, "Controller:read_input: %s" % (tinput))
        # read_evap_temperature / read_suct_temperature
        return self.hw_controller.read_gas_temperature()

    def read_output(self, toutput):
        """
        Reads an Output class type object
        Raises NotImplementedError if not defined by inheriting class

        Args:
           toutput:  Output class type object 

        Returns:
           read value (in output unit)         
        """
        log_info(self, "Controller:read_output: %s" % (toutput))
        # read_gas_flow / read_gas_heat / read_evap_heat
        return self.hw_controller.read_suct_heat()

    def state_input(self, tinput):
        """
        Return a string representing state of an Input object.
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tinput:  Input class type object

        Returns:
           object state string. This is one of READY/RUNNING/ALARM/FAULT
        """
        log_info(self, "Controller:state_input: %s" % (tinput))
        return self.hw_controller.read_alarm()  # read_sample_error

    def state_output(self, toutput):
        """
        Return a string representing state of an Output object.
        Raises NotImplementedError if not defined by inheriting class

        Args:
           toutput:  Output class type object

        Returns:
           object state string. This is one of READY/RUNNING/ALARM/FAULT
        """
        log_info(self, "Controller:state_output: %s" % (toutput))
        rmode = self.hw_controller.read_run_mode()
        phase = self.hw_controller.read_phase()
        return (rmode, phase)

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
        pass

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
        return 0

    def set_ki(self, tloop, ki):
        """
        Set the PID I value
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object 
           ki: the ki value
        """
        log_info(self, "Controller:set_ki: %s %s" % (tloop, ki))
        pass

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
        return 0

    def set_kd(self, tloop, kd):
        """
        Set the PID D value
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object 
           kd: the kd value
        """
        log_info(self, "Controller:set_kd: %s %s" % (tloop, kd))
        pass

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
        return 0

    def start_regulation(self, tloop):
        """
        Starts the regulation process.
        It must NOT start the ramp, use 'start_ramp' to do so.
        Raises NotImplementedError if not defined by inheriting class

        Args: 
           tloop:  Loop class type object
        """
        log_info(self, "Controller:start_regulation: %s" % (tloop))
        pass

    def stop_regulation(self, tloop):
        """
        Stops the regulation process.
        It must NOT stop the ramp, use 'stop_ramp' to do so.
        Raises NotImplementedError if not defined by inheriting class

        Args: 
           tloop:  Loop class type object
        """
        log_info(self, "Controller:stop_regulation: %s" % (tloop))
        pass

    # ------ setpoint methods ------------------------

    def set_setpoint(self, tloop, sp, **kwargs):
        """
        Set the current setpoint (target value).
        It must NOT start the PID process, use 'start_regulation' to do so.
        
        Args:
           tloop:  Loop class type object
           sp:     setpoint (in tloop.input unit)
           **kwargs: auxilliary arguments
        """
        log_info(self, "Controller:set_setpoint: %s %s" % (tloop, sp))
        # self._setpoint = sp
        # self.hw_controller.cool(sp)
        pass

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
        # if self._setpoint is None:
        #    self._setpoint = self.hw_controller.read_target_temperature()
        # return self._setpoint
        return self.hw_controller.read_target_temperature()

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

        rate = self.get_ramprate(tloop)
        # self._setpoint = sp

        # if self._is_paused:
        #     self.hw_controller.resume()
        #     self._is_paused = False

        self.hw_controller.ramp(rate, sp)

    def stop_ramp(self, tloop):
        """
        Stop the current ramping to a setpoint
        It must NOT stop the PID process, use 'stop_regulation' to do so.
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object
        """
        log_info(self, "Controller:stop_ramp: %s" % (tloop))
        # if not self._is_paused:  # self.hw_controller.is_paused()
        #     self._is_paused = True
        self.hw_controller.pause()

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
        return self.hw_controller.is_ramping()

    def set_ramprate(self, tloop, rate):
        """
        Set the ramp rate
        Args:
           tloop:  Loop class type object
           rate:   ramp rate (in input unit per second)
        """
        log_info(self, "Controller:set_ramprate: %s %s" % (tloop, rate))
        # self._ramp_rate = rate
        sp = self.get_setpoint(tloop)
        self.hw_controller.ramp(rate, sp)

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
        # if self._ramp_rate is None:
        #     self._ramp_rate = self.hw_controller.read_ramprate()
        # return self._ramp_rate
        return self.hw_controller.read_ramprate()

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
        self.hw_controller.turbo(bool(enable))

    def cool(self, temp):
        self.hw_controller.cool(temp)

    def plat(self, duration):
        self.hw_controller.plat(duration)

    def pause(self):
        self.hw_controller.pause()

    def resume(self):
        self.hw_controller.resume()
