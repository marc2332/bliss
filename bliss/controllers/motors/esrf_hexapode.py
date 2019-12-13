# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""\
ESRF hexapod

YAML_ configuration example:

.. code-block:: yaml

    plugin: emotion
    class: esrf_hexapode
    tango_name: d23/hexapod/mirror
    hexapode_name: hexa_mirror
    axes:
      - name: h1tx
        role: tx
      - name: h1ty
        role: ty
      - name: h1tz
        role: tz
      - name: h1rx
        role: rx
      - name: h1ry
        role: ry
      - name: h1rz
        role: rz

Comments:
    + When reading tango DS attribute, the role in dex are as follow:
        0   -   X
        1   -   Y
        2   -   Z
        3   -   RotZ
        4   -   RotY
        5   -   RotX
    + Unit are fixed: mm for x,y,z and mRad for rx, ry, rz
      Tango DS return mm and deg
    + Doing a HomeSearch only (Not a hard Reset) is working but then the Tango DS will
      prevent you to move anymore beacause Legs state=LIMIT => DS state=FAULT
      TO BE CHANGE in the DS
      The way to go out of this situation is to run a hard reset !!!

"""

import time
import math
import gevent

from bliss.controllers.motor import Controller
from bliss.common.axis import AxisState
from bliss.common.tango import DevState, DeviceProxy

from bliss import global_map
from bliss.common.logtools import *

from bliss.shell.cli.user_dialog import (
    UserMsg,
    UserYesNo,
    UserChoice,
    UserFloatInput,
    Container,
)

from bliss.shell.cli.pt_widgets import display, BlissDialog

__author__ = "Jens Meyer / Gilles Berruyer - ESRF ISDD SOFTGROUP BLISS - June 2019"


class esrf_hexapode(Controller):
    """ Class to implement BLISS motor controller of esrf hexapode controlled
    via tango device server
    """

    def __init__(self, *args, **kwargs):
        Controller.__init__(self, *args, **kwargs)

        global_map.register(self)

        self.device = None
        self.roles = {}
        self.last_read = None
        self.hexa_pos = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        self.tango_name = self.config.get("tango_name")

        if not self.tango_name:
            _err_msg = (
                f"'tango_name' not defined in config for {self.config.get('name')}"
            )
            log_error(self, _err_msg)
            raise RuntimeError(_err_msg)

    """
    BLISS MOTOR CONTROLLER
    """

    def initialize(self):
        """Controller initialization actions. """

        # Get a proxy on Hexapode Tango DS.
        self.device = DeviceProxy(self.tango_name)

        self.roles = {}
        self.roles["tx"] = 0
        self.roles["ty"] = 1
        self.roles["tz"] = 2
        self.roles["rz"] = 3
        self.roles["ry"] = 4
        self.roles["rx"] = 5

        self.last_read = None

        self.hexa_pos = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

    def initialize_axis(self, axis):
        """ Axes initialization actions """
        role = axis.config.get("role")
        if role not in self.roles:
            raise ValueError(f"ESRF_hexapode: Invalid role {role} for axis {axis.name}")

    """
    Actions to perform at controller closing.
    """

    def finalize(self):
        pass

    """
    Moving Hexapode motors
    """

    def start_one(self, motion):
        return self.start_all(motion)

    def start_all(self, *motion_list):

        # Get current position of x,y,z,rx,ry,rz
        hexa_pos = self.device.read_attribute("Position").value

        # Change values for roles which are asked to be moved
        for motion in motion_list:
            role = motion.axis.config.get("role")
            if role in ("rx", "ry", "rz"):
                hexa_pos[self.roles[role]] = math.degrees(motion.target_pos / 1000.0)
            else:
                hexa_pos[self.roles[role]] = motion.target_pos

        self.device.Move(hexa_pos)

    def move_tz(self, pos):
        hexa_pos = self.device.read_attribute("Position").value
        print(f"Moving from\n{hexa_pos}\n", end="")
        hexa_pos[2] = hexa_pos[2] + pos
        print(f"To\n{hexa_pos}")
        self.device.Move(hexa_pos)

    """
    Read Position
    """

    def read_position(self, axis):

        # Get current position of x,y,z,rx,ry,rz if nerver done or
        # done more than 5ms before
        if (self.last_read is None) or ((time.time() - self.last_read) > 0.005):
            self.hexa_pos = self.device.read_attribute("Position").value
            self.last_read = time.time()

        role = axis.config.get("role")
        pos = self.hexa_pos[self.roles[role]]
        if role in ("rx", "ry", "rz"):
            pos = math.radians(pos) * 1000

        return pos

    """
    State
    """

    def state(self, axis):
        _state = self.device.state()

        if _state == DevState.ON:
            return AxisState("READY")

        if _state == DevState.MOVING:
            return AxisState("MOVING")

        return AxisState("READY")

    """
    Must send a command to the controller to abort the motion of given axis.
    """

    def stop(self, axis):
        self.device.Stop()

    def stop_all(self, *motion_list):
        self.device.Stop()

    """
    Velocity
    """

    def read_velocity(self, axis):
        return float(axis.config.get("velocity"))

    def set_velocity(self, axis, velocity):
        pass

    """
    Acceleration
    """

    def read_acceleration(self, axis):
        return float(axis.config.get("acceleration"))

    def set_acceleration(self, axis, acc):
        pass

    """
    END of Motor Controller
    """

    """
    Hexapode Usefull Functions
    """

    def hexa_home_search(self):
        with hexapode_cleanup(self, "hexa_home_search"):
            self.SearchHome()

    def hexa_soft_reset(self):
        self.device.Reset(1)

    def hexa_get_actuators_status(self):

        lstate = self.device.read_attribute("ActuatorStatus").value

        hexa_state = ["", "", "", "", "", ""]
        for leg in range(6):
            if lstate[leg] & 0x01:
                hexa_state[leg] = f"{hexa_state[leg]} READY"
            if lstate[leg] & 0x02:
                hexa_state[leg] = f"{hexa_state[leg]} MOVING"
            if lstate[leg] & 0x04:
                hexa_state[leg] = f"{hexa_state[leg]} UPLIM"
            if lstate[leg] & 0x08:
                hexa_state[leg] = f"{hexa_state[leg]} DOWNLIM"
            if lstate[leg] & 0x10:
                hexa_state[leg] = f"{hexa_state[leg]} HOME"
            if lstate[leg] & 0x20:
                hexa_state[leg] = f"{hexa_state[leg]} SEARCH"
            if lstate[leg] & 0x80:
                hexa_state[leg] = f"{hexa_state[leg]} FAULT"

        return hexa_state

    def __info__(self):
        """Standard method called by BLISS Shell info helper."""
        return self.info(menu=False)

    def info(self, menu=False):
        """Return a string information about hexapod positions
        This method can be used by both menu() and info() methods.
        """

        if menu:
            line_str = ""
        else:
            line_str = "    "

        # Description
        hexa_desc = self.device.read_attribute("Description").value
        hexa_mode = self.device.read_attribute("Mode").value
        hexa_stat = self.device.status()

        msg_desc = f"{line_str}Description : {hexa_desc}"
        msg_desc = f"{msg_desc}\n{line_str}Status      : {hexa_stat[:-1]}"
        if hexa_mode == 0:
            msg_desc = f"{msg_desc}\n{line_str}Mode        : Normal"
        elif hexa_mode == 1:
            msg_desc = f"{msg_desc}\n{line_str}Mode        : Simulation"
        else:
            msg_desc = f"{msg_desc}\n{line_str}Mode        : Unknown"

        # Actuator State
        hexa_state = self.hexa_get_actuators_status()

        # Actuator Length
        hexa_length = self.device.read_attribute("LegLength").value

        # Hexapode Position
        hexa_pos = self.device.read_attribute("Position").value

        msg_pos = f"{line_str}Tx         = %8.5f (mm)   | Leg1 = %8.4f - %s" % (
            hexa_pos[0],
            hexa_length[0],
            hexa_state[0],
        )
        msg_pos = (
            f"{msg_pos}\n{line_str}Ty         = %8.5f (mm)   | Leg1 = %8.4f - %s"
            % (hexa_pos[1], hexa_length[1], hexa_state[1])
        )
        msg_pos = (
            f"{msg_pos}\n{line_str}Tz         = %8.5f (mm)   | Leg2 = %8.4f - %s"
            % (hexa_pos[2], hexa_length[2], hexa_state[2])
        )
        msg_pos = (
            f"{msg_pos}\n{line_str}Rx / Psi   = %8.5f (mrad) | Leg3 = %8.4f - %s"
            % (math.radians(hexa_pos[5]) * 1000.0, hexa_length[3], hexa_state[3])
        )
        msg_pos = (
            f"{msg_pos}\n{line_str}Ry / Theta = %8.5f (mrad) | Leg4 = %8.4f - %s"
            % (math.radians(hexa_pos[4]) * 1000.0, hexa_length[4], hexa_state[4])
        )
        msg_pos = (
            f"{msg_pos}\n{line_str}Rz / Phi   = %8.5f (mrad) | Leg5 = %8.4f - %s"
            % (math.radians(hexa_pos[3]) * 1000.0, hexa_length[5], hexa_state[5])
        )

        msg_desc += "\n\n"
        msg_desc += msg_pos

        return msg_desc

    def hexa_show(self, menu=False):
        """Shell user level method to get info about current hexapode."""
        info_str = self.info(menu)

        if menu:
            msg_widget = UserMsg(label=f"{info_str}\n")
            msg_title = f"{self.name}: {self.device}"
            display(msg_widget, title=msg_title)
        else:
            print("")
            print(f"    Name        : {self.name}")
            print(f"    Device      : {self.device}")
            print(f"{info_str}\n")

    def hexa_set_ref_pos(self):
        """User level interactive method to ???
        This method uses `user_dialog` functions."""

        hexa_curr_pos = self.device.read_attribute("Position").value
        old_ref_pos = self.device.read_attribute("RefPosition").value

        dlg_old_tx = UserMsg(label="Tx (mm)   : %8.4f" % (hexa_curr_pos[0]))
        dlg_old_ty = UserMsg(label="Ty (mm)   : %8.4f" % (hexa_curr_pos[1]))
        dlg_old_tz = UserMsg(label="Tz (mm)   : %8.4f" % (hexa_curr_pos[2]))
        dlg_old_rx = UserMsg(
            label="Rx (mrad) : %8.4f" % (math.radians(hexa_curr_pos[5]) * 1000.0)
        )
        dlg_old_ry = UserMsg(
            label="Ry (mrad) : %8.4f" % (math.radians(hexa_curr_pos[4]) * 1000.0)
        )
        dlg_old_rz = UserMsg(
            label="Rz (mrad) : %8.4f" % (math.radians(hexa_curr_pos[3]) * 1000.0)
        )
        cont_curr = Container(
            [dlg_old_tx, dlg_old_ty, dlg_old_tz, dlg_old_rx, dlg_old_ry, dlg_old_rz],
            title="Current Positions",
            border=1,
        )

        dlg_new_tx = UserFloatInput(label="Tx (mm)   :", defval=hexa_curr_pos[0])
        dlg_new_ty = UserFloatInput(label="Ty (mm)   :", defval=hexa_curr_pos[1])
        dlg_new_tz = UserFloatInput(label="Tz (mm)   :", defval=hexa_curr_pos[2])
        dlg_new_rx = UserFloatInput(
            label="Rx (mrad) :", defval=math.radians(hexa_curr_pos[5]) * 1000.0
        )
        dlg_new_ry = UserFloatInput(
            label="Ry (mrad) :", defval=math.radians(hexa_curr_pos[4]) * 1000.0
        )
        dlg_new_rz = UserFloatInput(
            label="Rz (mrad) :", defval=math.radians(hexa_curr_pos[3]) * 1000.0
        )
        cont_new = Container(
            [dlg_new_tx, dlg_new_ty, dlg_new_tz, dlg_new_rx, dlg_new_ry, dlg_new_rz],
            title="New Positions",
            border=1,
        )

        rep = BlissDialog(
            [[cont_curr, cont_new]], title=f"{self.name}: Change Reference Positions"
        ).show()

        if rep != False:

            hexa_pos = [
                hexa_curr_pos[0],
                hexa_curr_pos[1],
                hexa_curr_pos[2],
                hexa_curr_pos[3],
                hexa_curr_pos[4],
                hexa_curr_pos[5],
            ]
            hexa_pos.append(float(rep[dlg_new_tx]))
            hexa_pos.append(float(rep[dlg_new_ty]))
            hexa_pos.append(float(rep[dlg_new_tz]))
            hexa_pos.append(math.degrees(float(rep[dlg_new_rz]) / 1000.0))
            hexa_pos.append(math.degrees(float(rep[dlg_new_ry]) / 1000.0))
            hexa_pos.append(math.degrees(float(rep[dlg_new_rx]) / 1000.0))

            self.device.SetRefPosition(hexa_pos)

            new_ref_pos = self.device.read_attribute("RefPosition").value

            msg = "Old Reference Positions         New Reference Positions"
            msg = f"{msg}\n\nTx : %8.4f (mm)       Tx : %8.4f (mm)" % (
                old_ref_pos[0],
                new_ref_pos[0],
            )
            msg = f"{msg}\nTy : %8.4f (mm)       Ty : %8.4f (mm)" % (
                old_ref_pos[1],
                new_ref_pos[1],
            )
            msg = f"{msg}\nTz : %8.4f (mm)       Tz : %8.4f (mm)" % (
                old_ref_pos[2],
                new_ref_pos[2],
            )
            msg = f"{msg}\nRx : %8.4f (mrad)     Rx : %8.4f (mrad)" % (
                math.radians(old_ref_pos[5]) * 1000.0,
                math.radians(new_ref_pos[5]) * 1000.0,
            )
            msg = f"{msg}\nRy : %8.4f (mrad)     Ry : %8.4f (mrad)" % (
                math.radians(old_ref_pos[4]) * 1000.0,
                math.radians(new_ref_pos[4]) * 1000.0,
            )
            msg = f"{msg}\nRz : %8.4f (mrad)     Rz : %8.4f (mrad)" % (
                math.radians(old_ref_pos[3]) * 1000.0,
                math.radians(new_ref_pos[3]) * 1000.0,
            )
            msg = f"{msg}\n\nSave New Reference Positions in Hexapode Server ?"

            dlg = UserYesNo(label=msg)
            rep = display(dlg, title=f"{self.name}: Save New Reference Position ?")

            if rep:
                # TODO: Jens to tell me how to change Tango DS properties dynamically
                print("Changing Hexapode Tango DS Properties !!!")

    def hexa_move_legs(self):
        """User level interactive method to ???
        This method uses `user_dialog` functions."""

        curr_leg_length = self.device.read_attribute("LegLength").value

        dlg_curr_l1 = UserMsg(label=f"Leg 1 (mm) : %8.4f" % (curr_leg_length[0]))
        dlg_curr_l2 = UserMsg(label=f"Leg 2 (mm) : %8.4f" % (curr_leg_length[1]))
        dlg_curr_l3 = UserMsg(label=f"Leg 3 (mm) : %8.4f" % (curr_leg_length[2]))
        dlg_curr_l4 = UserMsg(label=f"Leg 4 (mm) : %8.4f" % (curr_leg_length[3]))
        dlg_curr_l5 = UserMsg(label=f"Leg 5 (mm) : %8.4f" % (curr_leg_length[4]))
        dlg_curr_l6 = UserMsg(label=f"Leg 6 (mm) : %8.4f" % (curr_leg_length[5]))
        cont_curr = Container(
            [
                dlg_curr_l1,
                dlg_curr_l2,
                dlg_curr_l3,
                dlg_curr_l4,
                dlg_curr_l5,
                dlg_curr_l6,
            ],
            title="Current Positions",
            border=1,
        )

        dlg_new_l1 = UserFloatInput(label="Leg 1 (mm) :", defval=curr_leg_length[0])
        dlg_new_l2 = UserFloatInput(label="Leg 2 (mm) :", defval=curr_leg_length[1])
        dlg_new_l3 = UserFloatInput(label="Leg 3 (mm) :", defval=curr_leg_length[2])
        dlg_new_l4 = UserFloatInput(label="Leg 4 (mm) :", defval=curr_leg_length[3])
        dlg_new_l5 = UserFloatInput(label="Leg 5 (mm) :", defval=curr_leg_length[4])
        dlg_new_l6 = UserFloatInput(label="Leg 6 (mm) :", defval=curr_leg_length[5])
        cont_new = Container(
            [dlg_new_l1, dlg_new_l2, dlg_new_l3, dlg_new_l4, dlg_new_l5, dlg_new_l6],
            title="Move to Positions",
            border=1,
        )

        rep = BlissDialog(
            [[cont_curr, cont_new]], title=f"{self.name}: Move Legs", ok_text="Move"
        ).show()

        if rep != False:

            with hexapode_cleanup(self, "hexa_move_legs"):

                new_leg_length = [
                    float(rep[dlg_new_l1]),
                    float(rep[dlg_new_l2]),
                    float(rep[dlg_new_l3]),
                    float(rep[dlg_new_l4]),
                    float(rep[dlg_new_l5]),
                    float(rep[dlg_new_l6]),
                ]
                self.device.MoveActuators(new_leg_length)

                print(f"\n   Moving {self.name} Hexapode Legs\n")
                print(
                    "       Leg1   |   Leg2   |   Leg3   |   Leg4   |   Leg5   |   Leg6"
                )
                print(
                    "     ---------------------------------------------------------------"
                )
                print(
                    "     %8.4f | %8.4f | %8.4f | %8.4f | %8.4f | %8.4f "
                    % (
                        new_leg_length[0],
                        new_leg_length[1],
                        new_leg_length[2],
                        new_leg_length[3],
                        new_leg_length[4],
                        new_leg_length[5],
                    )
                )

                while self.device.State() != DevState.MOVING:
                    gevent.sleep(0.01)

                while self.device.State() == DevState.MOVING:

                    curr_leg_length = self.device.read_attribute("LegLength").value
                    print(
                        "     %8.4f | %8.4f | %8.4f | %8.4f | %8.4f | %8.4f"
                        % (
                            curr_leg_length[0],
                            curr_leg_length[1],
                            curr_leg_length[2],
                            curr_leg_length[3],
                            curr_leg_length[4],
                            curr_leg_length[5],
                        ),
                        end="\r",
                    )
                    gevent.sleep(0.01)

                print("\n")

    def hexa_move(self):
        """User level interactive method to ???
        This method uses `user_dialog` functions."""

        curr_pos = self.device.read_attribute("Position").value

        dlg_curr_tx = UserMsg(label=f"Tx (mm)   : %8.4f" % curr_pos[0])
        dlg_curr_ty = UserMsg(label=f"Ty (mm)   : %8.4f" % curr_pos[1])
        dlg_curr_tz = UserMsg(label=f"Tz (mm)   : %8.4f" % curr_pos[2])
        dlg_curr_rx = UserMsg(
            label=f"Rx (mrad) : %8.4f" % math.radians(float(curr_pos[5])) * 1000.0
        )
        dlg_curr_ry = UserMsg(
            label=f"Ry (mrad) : %8.4f" % math.radians(float(curr_pos[4])) * 1000.0
        )
        dlg_curr_rz = UserMsg(
            label=f"Rz (mrad) : %8.4f" % math.radians(float(curr_pos[3])) * 1000.0
        )
        cont_curr = Container(
            [
                dlg_curr_tx,
                dlg_curr_ty,
                dlg_curr_tz,
                dlg_curr_rx,
                dlg_curr_ry,
                dlg_curr_rz,
            ],
            title="Current Hexapode Positions",
            border=1,
        )

        dlg_new_tx = UserFloatInput(label="Tx (mm)   :", defval=curr_pos[0])
        dlg_new_ty = UserFloatInput(label="Ty (mm)   :", defval=curr_pos[1])
        dlg_new_tz = UserFloatInput(label="Tz (mm)   :", defval=curr_pos[2])
        dlg_new_rx = UserFloatInput(
            label="Rx (mrad) :", defval=math.radians(float(curr_pos[5])) * 1000.0
        )
        dlg_new_ry = UserFloatInput(
            label="Ry (mrad) :", defval=math.radians(float(curr_pos[4])) * 1000.0
        )
        dlg_new_rz = UserFloatInput(
            label="Rz (mrad) :", defval=math.radians(float(curr_pos[3])) * 1000.0
        )
        cont_new = Container(
            [dlg_new_tx, dlg_new_ty, dlg_new_tz, dlg_new_rx, dlg_new_ry, dlg_new_rz],
            title="Move Hexapode to Positions",
            border=1,
        )

        rep = BlissDialog(
            [[cont_curr, cont_new]], title=f"{self.name}: Move Hexapode", ok_text="Move"
        ).show()

        if rep != False:

            new_pos = [
                float(rep[dlg_new_tx]),
                float(rep[dlg_new_ty]),
                float(rep[dlg_new_tz]),
                math.degrees(float(rep[dlg_new_rz]) / 1000.0),
                math.degrees(float(rep[dlg_new_ry]) / 1000.0),
                math.degrees(float(rep[dlg_new_rx]) / 1000.0),
            ]

            with hexapode_cleanup(self, "hexa_move"):

                self.device.Move(new_pos)

                print(f"\nMoving {self.name} Hexapode Legs\n")
                print(
                    "        Tx    |    Ty    |    Tz    |    Rx    |    Ry    |    Rz"
                )
                print(
                    "     --------------------------------------------------------------"
                )
                print(
                    "     %8.4f | %8.4f | %8.4f | %8.4f | %8.4f | %8.4f "
                    % (
                        new_pos[0],
                        new_pos[1],
                        new_pos[2],
                        new_pos[5],
                        new_pos[4],
                        new_pos[3],
                    )
                )

                while self.device.State() != DevState.MOVING:
                    gevent.sleep(0.01)

                while self.device.State() == DevState.MOVING:

                    curr_pos = self.device.read_attribute("Position").value
                    print(
                        "     %8.4f | %8.4f | %8.4f | %8.4f | %8.4f | %8.4f"
                        % (
                            curr_pos[0],
                            curr_pos[1],
                            curr_pos[2],
                            curr_pos[5],
                            curr_pos[4],
                            curr_pos[3],
                        ),
                        end="\r",
                    )
                    gevent.sleep(0.01)

                print("\n")

    def hexa_switch_mode(self):
        old_mode = self.device.read_attribute("Mode").value
        if old_mode == 0:
            new_mode = 1
        else:
            new_mode = 0
        self.device.write_attribute("Mode", new_mode)

    def hexa_set_legs(self):
        """User level interactive method to ???
        This method uses `user_dialog` functions."""

        curr_leg_length = self.device.read_attribute("LegLength").value

        dlg_curr_l1 = UserMsg(label=f"Leg 1 (mm) : %8.4f" % (curr_leg_length[0]))
        dlg_curr_l2 = UserMsg(label=f"Leg 2 (mm) : %8.4f" % (curr_leg_length[1]))
        dlg_curr_l3 = UserMsg(label=f"Leg 3 (mm) : %8.4f" % (curr_leg_length[2]))
        dlg_curr_l4 = UserMsg(label=f"Leg 4 (mm) : %8.4f" % (curr_leg_length[3]))
        dlg_curr_l5 = UserMsg(label=f"Leg 5 (mm) : %8.4f" % (curr_leg_length[4]))
        dlg_curr_l6 = UserMsg(label=f"Leg 6 (mm) : %8.4f" % (curr_leg_length[5]))
        cont_curr = Container(
            [
                dlg_curr_l1,
                dlg_curr_l2,
                dlg_curr_l3,
                dlg_curr_l4,
                dlg_curr_l5,
                dlg_curr_l6,
            ],
            title="Current Positions",
            border=1,
        )

        dlg_new_l1 = UserFloatInput(label="Leg 1 (mm) :", defval=curr_leg_length[0])
        dlg_new_l2 = UserFloatInput(label="Leg 2 (mm) :", defval=curr_leg_length[1])
        dlg_new_l3 = UserFloatInput(label="Leg 3 (mm) :", defval=curr_leg_length[2])
        dlg_new_l4 = UserFloatInput(label="Leg 4 (mm) :", defval=curr_leg_length[3])
        dlg_new_l5 = UserFloatInput(label="Leg 5 (mm) :", defval=curr_leg_length[4])
        dlg_new_l6 = UserFloatInput(label="Leg 6 (mm) :", defval=curr_leg_length[5])
        cont_new = Container(
            [dlg_new_l1, dlg_new_l2, dlg_new_l3, dlg_new_l4, dlg_new_l5, dlg_new_l6],
            title="New Positions",
            border=1,
        )

        rep = BlissDialog(
            [[cont_curr, cont_new]],
            title=f"{self.name}: Set Legs Positions",
            ok_text="Set",
        ).show()

        new_leg_length = [
            float(rep[dlg_new_l1]),
            float(rep[dlg_new_l2]),
            float(rep[dlg_new_l3]),
            float(rep[dlg_new_l4]),
            float(rep[dlg_new_l5]),
            float(rep[dlg_new_l6]),
        ]
        self.device.write_attribute("LegLength", new_leg_length)

    def hexa_home_search(self):

        with hexapode_cleanup(self, "hexa_home_search"):

            self.device.SearchHome()

            print(f"\n   {self.name}: Home Search\n")
            print(
                "     Leg1          | Leg2          | Leg3          | Leg4          | Leg5          | Leg6          "
            )
            print(
                "    -----------------------------------------------------------------------------------------------"
            )

            while self.device.State() != DevState.MOVING:
                gevent.sleep(0.01)

            while self.device.State() == DevState.MOVING:

                hexa_state = self.hexa_get_actuators_status()
                print(
                    "    %-14s |%-14s |%-14s |%-14s |%-14s |%-14s"
                    % (
                        hexa_state[0],
                        hexa_state[1],
                        hexa_state[2],
                        hexa_state[3],
                        hexa_state[4],
                        hexa_state[5],
                    ),
                    end="\r",
                )
                gevent.sleep(0.01)

            print(f"\n\n {self.name} Home Search Done\n")

    def hexa_hard_reset(self):

        with hexapode_cleanup(self, "hexa_hard_reset"):

            self.device.Reset(0)

            print(f"\n   {self.name}: Hard Reset\n")
            print(
                "     Leg1          | Leg2          | Leg3          | Leg4          | Leg5          | Leg6          "
            )
            print(
                "    -----------------------------------------------------------------------------------------------"
            )

            while self.device.State() != DevState.MOVING:
                gevent.sleep(0.01)

            while self.device.State() == DevState.MOVING:

                hexa_state = self.hexa_get_actuators_status()
                print(
                    "    %-14s |%-14s |%-14s |%-14s |%-14s |%-14s"
                    % (
                        hexa_state[0],
                        hexa_state[1],
                        hexa_state[2],
                        hexa_state[3],
                        hexa_state[4],
                        hexa_state[5],
                    ),
                    end="\r",
                )
                gevent.sleep(0.1)

            print(f"\n\n {self.name} Hard Reset Done\n")

    def hexa_calc(self):
        """User level interactive method to ???
        This method uses `user_dialog` functions."""

        curr_pos = self.device.read_attribute("Position").value

        curr_leg_length = self.device.read_attribute("LegLength").value

        fin = False

        while not fin:

            dlg_new_tx = UserFloatInput(label="Tx (mm)   :", defval=curr_pos[0])
            dlg_new_ty = UserFloatInput(label="Ty (mm)   :", defval=curr_pos[1])
            dlg_new_tz = UserFloatInput(label="Tz (mm)   :", defval=curr_pos[2])
            dlg_new_rx = UserFloatInput(
                label="Rx (mrad) :", defval=math.radians(curr_pos[5]) / 1000.0
            )
            dlg_new_ry = UserFloatInput(
                label="Ry (mrad) :", defval=math.radians(curr_pos[4]) / 1000.0
            )
            dlg_new_rz = UserFloatInput(
                label="Rz (mrad) :", defval=math.radians(curr_pos[3]) / 1000.0
            )
            cont_new = Container(
                [
                    dlg_new_tx,
                    dlg_new_ty,
                    dlg_new_tz,
                    dlg_new_rx,
                    dlg_new_ry,
                    dlg_new_rz,
                ],
                title="Hexapode Positions",
                border=1,
            )

            dlg_curr_l1 = UserMsg(label=f"Leg 1 (mm) : %8.4f" % (curr_leg_length[0]))
            dlg_curr_l2 = UserMsg(label=f"Leg 2 (mm) : %8.4f" % (curr_leg_length[1]))
            dlg_curr_l3 = UserMsg(label=f"Leg 3 (mm) : %8.4f" % (curr_leg_length[2]))
            dlg_curr_l4 = UserMsg(label=f"Leg 4 (mm) : %8.4f" % (curr_leg_length[3]))
            dlg_curr_l5 = UserMsg(label=f"Leg 5 (mm) : %8.4f" % (curr_leg_length[4]))
            dlg_curr_l6 = UserMsg(label=f"Leg 6 (mm) : %8.4f" % (curr_leg_length[5]))
            cont_curr = Container(
                [
                    dlg_curr_l1,
                    dlg_curr_l2,
                    dlg_curr_l3,
                    dlg_curr_l4,
                    dlg_curr_l5,
                    dlg_curr_l6,
                ],
                title="Current Positions",
                border=1,
            )

            rep = BlissDialog(
                [[cont_new, cont_curr]],
                title=f"{self.name}: Calculate Leg Positions",
                ok_text="Calculate",
            ).show()

            print(rep)
            if rep == False:
                fin = True
            else:
                curr_pos = [
                    float(rep[dlg_new_tx]),
                    float(rep[dlg_new_ty]),
                    float(rep[dlg_new_tz]),
                    math.degrees(float(rep[dlg_new_rz]) / 1000.0),
                    math.degrees(float(rep[dlg_new_ry]) / 1000.0),
                    math.degrees(float(rep[dlg_new_rx]) / 1000.0),
                ]
                curr_leg_length = self.device.CheckPosition(curr_pos)

    """
    Hexapode Menu
    """

    def menu(self):
        """Access to the BlissDialog-based menu from shell.
        Menu allows to:
        * show info
        * stop hexapode
        * make a soft reset (ie:???)
        * make a full reset (ie:???)
        * calculate and check positions.
        """
        choices = [
            (1, "Show Hexapode"),
            (2, "STOP"),
            (3, "Soft Reset"),
            (4, "Full Reset (Move Ref. + Move Nominal)"),
            (5, "Calc. and Check Positions"),
        ]
        menu_choice = UserChoice(values=choices)

        menu_not_implemented = UserMsg("Command Not Implemented")

        fin = False
        while not fin:

            rep = BlissDialog(
                [[menu_choice]], title="Hexapode Menu", cancel_text="Quit"
            ).show()

            if not rep:
                fin = True
            else:
                if rep[menu_choice] == 1:
                    self.hexa_show(menu=True)

                if rep[menu_choice] == 2:
                    self.device.Stop()

                if rep[menu_choice] == 3:
                    self.hexa_soft_reset()

                if rep[menu_choice] == 4:
                    self.hexa_hard_reset()

                if rep[menu_choice] == 5:
                    self.hexa_calc()

                if rep[menu_choice] not in (1, 2, 3, 4, 5):
                    display(menu_not_implemented)


class hexapode_cleanup:
    """ """

    def __init__(self, hexapode, cmd_name):
        self.hexapode = hexapode
        self.cmd_name = cmd_name

    def __enter__(self):
        pass

    def __exit__(self, exep_type, exep_value, exep_tb):

        if exep_type is not None:
            print(f"\n\nCommand {self.cmd_name} end by {exep_type.__name__}")
            self.hexapode.device.Stop()

        return False
