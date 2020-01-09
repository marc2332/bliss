# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

# import enum
from bliss.shell.standard import ShellStr
from bliss.common.regulation import Input, Output, Loop, lazy_init
from bliss.common.utils import autocomplete_property


class Curve:
    def __init__(self, input_object):
        self.controller = input_object.controller
        self.channel = input_object.channel

    @property
    def used(self):
        """ Get the input curve used
            Returns:
                curve number (int): 0=none, 1->20 standard, 21->41 user defined curves
                curve name (str): limited to 15 characters
                curve SN (str): limited to 10 characters (Standard,...)
                curve format (int): 1=mV/K, 2=V/K, 3=Ohms/K, 4=logOhms/K
                curve temperature limit (float): in Kelvin
                curve temperature coefficient (int): 1=negative, 2=positive
        """
        return self.controller.used_curve(self.channel)

    def select(self, crvn):
        """ Set the curve to be used on a given input.
            Warning: the specified has to match with the type input.
            If not, the set curve number is 0 :(
            Hint: Set
              crvn (int): curve number: 0=none, 1->20 standard,
                                        21->41 user defined
        
        """
        self.controller.select_curve(crvn, self.channel)

    def show_all(self):
        self.controller.show_all_curves()

    def load(self, crvn, crvfile):
        self.controller.write_curve(crvn, crvfile)

    def delete(self, crvn):
        self.controller.delete_curve(crvn)


class LakeshoreInput(Input):
    @autocomplete_property
    @lazy_init
    def curve(self):
        return Curve(self)

    @lazy_init
    def __info__(self):
        return "\n".join(self.controller.show(self.name))

    def __str__(self):
        # this is for the mapping: it needs a representation of instance
        return super().__repr__()

    @property
    @lazy_init
    def alarm_status(self):
        """ Get the high and low alarm state for given input
            Args:
              None
            Returns:
              high and low alarm state (str, str): "On/Off"
        """
        return self.controller.alarm_status(self)

    @lazy_init
    def alarm_reset(self):
        """ Clears both the high and low status of all alarms
            Args:
              None (though this command does not need the input channel,
                    we put it here, since alarms are related to the state
                    on input like for ex. measured temperature above 
                    alarm high-limit etc.)
            Returns:
              None
        """
        self.controller.alarm_reset()

    @lazy_init
    def set_filter_params(self, onoff=None, points=None, window=None):
        """ return the input filter parameters
            args:
                onoff  (int): specifies whether the filter function is 1 = ON or 0 = OFF
                points (int): specifies how many data points the filtering function
                              uses. Valid range = 2 to 64.
                window (int): specifies what percent of full scale reading
                              limits the filtering function. Reading changes
                              greater than this percentage reset the filter.
                              Valid range: 1 to 10%.
        
        """
        self.controller.set_filter_params(
            self, onoff=onoff, points=points, window=window
        )

    @property
    @lazy_init
    def filter_params(self):
        """ return the input filter parameters
            Returns:
                dict{
                    onoff  (int): specifies whether the filter function is 1 = ON or 0 = OFF
                    points (int): specifies how many data points the filtering function
                                uses. Valid range = 2 to 64.
                    window (int): specifies what percent of full scale reading
                                limits the filtering function. Reading changes
                                greater than this percentage reset the filter.
                    }
        """
        return self.controller.get_filter_params(self)

    @property
    def valid_sensor_types(self):
        lines = ["\n"]
        for stp in self.controller.SensorTypes:
            lines.append(f"{stp.name} = {stp.value}")

        return ShellStr("\n".join(lines))

    @autocomplete_property
    def sensor_types_enum(self):
        return self.controller.SensorTypes

    @lazy_init
    def set_sensor_type(self, sensor_type, compensation=0):
        """ set the sensor type 
            Args:
                sensor_type   (int): see 'valid_sensor_types'
                compensation  (int): 0=off or 1=on
            
            <compensation> Specifies input compensation where 0 = off and 1 = on.
            Reversal for thermal EMF compensation if input is resistive, room compensation if input is thermocouple.
            Always 0 if input is a diode.    
            
        """
        self.controller.set_sensor_type(self, sensor_type, compensation)

    @property
    @lazy_init
    def sensor_type(self):
        """ get the sensor type 
            Returns:
                dict: {sensor_type: (int), compensation: (int) }
        """
        return self.controller.get_sensor_type(self)


class LakeshoreOutput(Output):
    @lazy_init
    def __info__(self):
        return "\n".join(self.controller.show(self.name))

    def __str__(self):
        # this is for the mapping: it needs a representation of instance
        return super().__repr__()

    @property
    @lazy_init
    def value_percent(self):
        return self.controller.read_value_percent(self)

    @property
    def valid_ranges(self):
        lines = ["\n"]
        for rag in self.controller.HeaterRange:
            lines.append(f"{rag.name} = {rag.value}")
        return ShellStr("\n".join(lines))

    @autocomplete_property
    def ranges_enum(self):
        return self.controller.HeaterRange

    @property
    @lazy_init
    def range(self):
        return self.controller.get_heater_range(self)

    @range.setter
    @lazy_init
    def range(self, value):
        self.controller.set_heater_range(self, value)


class LakeshoreLoop(Loop):
    @lazy_init
    def __info__(self):
        return "\n".join(self.controller.show(self.name))

    def __str__(self):
        # this is for the mapping: it needs a representation of instance
        return super().__repr__()

    @property
    def valid_modes(self):
        lines = ["\n"]
        for mode in self.controller.Mode:
            lines.append(f"{mode.name} = {mode.value}")
        return ShellStr("\n".join(lines))

    @autocomplete_property
    def modes_enum(self):
        return self.controller.Mode

    @property
    @lazy_init
    def mode(self):
        return self.controller.get_loop_mode(self)

    @mode.setter
    @lazy_init
    def mode(self, mode):
        self.controller.set_loop_mode(self, mode)

    @property
    def valid_units(self):
        lines = ["\n"]
        for unit in self.controller.Unit:
            lines.append(f"{unit.name} = {unit.value}")
        return ShellStr("\n".join(lines))

    @autocomplete_property
    def units_enum(self):
        return self.controller.Unit

    @property
    @lazy_init
    def unit(self):
        return self.controller.get_loop_unit(self)

    @unit.setter
    @lazy_init
    def unit(self, unit):
        self.controller.set_loop_unit(self, unit)

    @property
    @lazy_init
    def params(self):
        return self.controller.get_loop_params(self)

    # @lazy_init
    # def set_params(self):
    #     self.controller.set_loop_params(self, input_channel=None, unit=None)

    @property
    @lazy_init
    def ramp_info(self):

        ramp_dict = {}
        ramp_dict["sp"] = self.setpoint
        ramp_dict["rate"] = self.controller.get_ramprate(self)

        if self.controller.is_ramping_enabled(self):
            ramp_dict["state"] = "ON"
        else:
            ramp_dict["state"] = "OFF"

        if self.controller.is_ramping(self):
            ramp_dict["ramp_state"] = "RAMPING"
        else:
            ramp_dict["ramp_state"] = "NOT RAMPING"

        return ramp_dict
