# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Bliss controller for Microdiff model MD2 and MD2S, using the EMBL Exporter
protocol for communication.

Example YAML_ configuration:
class: MD2
module: mx.md2
exporter_address: "wid30bmd2s:9001"
axes:
  -
    name: sampx
    root_name: "CentringX"
    steps_per_unit: 1
"""
import gevent
from bliss.controllers.motor import Controller
from bliss.common.axis import AxisState
from bliss.comm.Exporter import Exporter
from bliss import global_map


class MD2(Controller):
    """Implement the MD2 motors as bliss ones."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        host, port = self.config.get("exporter_address").split(":")
        self._exporter = Exporter(host, int(port))
        global_map.register(self, children_list=[self._exporter])
        self.pos_attr_suffix = "Position"
        self.state_cmd = "getMotorState"

    def initialize(self):
        """Initialize."""
        # velocity and acceleration are not mandatory in config
        self.axis_settings.config_setting["velocity"] = False
        self.axis_settings.config_setting["acceleration"] = False

        # read the state to check if the MD2 application replies.
        self._get_swstate()

    def initialize_axis(self, axis):
        """Get the axis root name from the config.
        Args:
            axis (Axis): The axis object.
        """
        axis.root_name = axis.config.get("root_name")

    def read_position(self, axis):
        """ Read the position.
        Args:
            axis (Axis): The axis object.
        Returns:
            (float): The position.
        """
        cmd = axis.root_name + self.pos_attr_suffix
        return self._exporter.read_property(cmd)

    def state(self, axis):
        """The motor state as AxisState.
        Args:
            axis (Axis): The axis object.
        Returns:
            (AxisState): The state of the motor.
        """
        state = self._exporter.execute(self.state_cmd, axis.root_name)
        return AxisState(state.upper())

    def start_all(self, *motion_list):
        """ Move simultaneouslu all the motors, defined in motion list.
        Args:
            motion_list (list): List of motions (Motion).
        """
        if len(motion_list) > 1:
            # prepare the command
            cmd = ""
            for mot in motion_list:
                name = mot.axis.root_name
                pos = mot.target_pos
                cmd += "%s=%0.3f;" % (name, pos)
            self._exporter.execute("startSimultaneousMoveMotors", cmd)
        else:
            self.start_one(motion_list[0])

    def start_one(self, motion):
        """Start to move the motor.
        Args:
            motion (Motion): Motion class input .
        """
        cmd = motion.axis.root_name + self.pos_attr_suffix
        self._exporter.write_property(cmd, motion.target_pos)

    def stop(self, axis=None):
        """Stop the motor.
        Args:
            axis (Axis): The axis object (not used).
        """
        self._exporter.execute("abort")

    def close(self):
        """Disconnect from the hardware"""
        self._exporter.disconnect()

    def home_search(self, axis, switch=None):
        """ Search a home switch
        Atgs:
            axis (Axis): The axis object.
            switch: Not used.
        """
        self._exporter.execute("startHomingMotor", axis.root_name)
        self._wait_ready(40)

    def home_state(self, axis):
        """State of the axis, as there is no MD2 application command for
           the home state.
        Returns:
            ((AxisState): The state of the motor.
        """
        return self.state(axis)

    def _get_hwstate(self):
        """Get the hardware state, reported by the MD2 application.
        Returns:
            (string): The state.
        """
        try:
            return self._exporter.read_property("HardwareState")
        except Exception:
            return "Ready"

    def _get_swstate(self):
        """Get the software state, reported by the MD2 application.
        Returns:
            (string): The state.
        """
        return self._exporter.read_property("State")

    def _ready(self):
        """ Get the "Ready" state - software abd hardware.
        Returns:
            (bool): True if both "Ready", False otherwise.
        """
        if self._get_swstate() == "Ready" and self._get_hwstate() == "Ready":
            return True
        return False

    def _wait_ready(self, timeout=3):
        """Wait for the stete to be "Ready".
        Args:
            timeout (float): waiting time [s].
        Raises:
            (gevent.Timeout): timeout elapsed.
        """
        with gevent.Timeout(timeout):
            while not self._ready():
                gevent.sleep(0.01)
