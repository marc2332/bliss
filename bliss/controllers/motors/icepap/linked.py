# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common.axis import (
    Axis,
    NoSettingsAxis,
    DEFAULT_POLLING_TIME,
    lazy_init,
    Motion,
)
from . import _ackcommand, _command
from bliss.common.utils import autocomplete_property
import types
import gevent


class LinkedAxis(Axis):
    def __init__(self, name, controller, config):
        Axis.__init__(self, name, controller, config)
        if config.get("address") is None:
            self.config.set("address", name)
        self.__real_axes_namespace = None
        self.__in_disprotected_move = False

    def _init_hardware(self):
        linked_axis = self.controller.get_linked_axis()
        if linked_axis.get(self.address) is None:
            raise RuntimeError(
                "Linked axis named %s doesn't exist ;"
                "linked axis configured in the system are : %s"
                % (self.address, linked_axis.keys())
            )

    def _init_software(self):
        # check if real motors are also defined in the config
        linked_axis = self.controller.get_linked_axis()
        mot_addresses = linked_axis.get(self.address)

        for name, axis in self.controller.axes.items():
            if axis.config.get("address", lambda x: x) in mot_addresses:
                raise RuntimeError(
                    "Cannot initialize linked axis '%s',"
                    " real axis '%s' found in controller configuration"
                    % (self.name, axis.name)
                )

    @autocomplete_property
    @lazy_init
    def real_axes(self):
        if self.__real_axes_namespace is None:
            real_axes = {}
            linked_axis = self.controller.get_linked_axis()
            mot_addresses = linked_axis.get(self.address)

            for address in mot_addresses:
                axis_name = _command(self.controller._cnx, "%d:?NAME" % address)
                config_dict = {
                    "autopower": False,
                    "steps_per_unit": self.steps_per_unit,
                    "acceleration": self.acceleration,
                    "velocity": self.velocity,
                }
                real_axis = NoSettingsAxis(axis_name, self.controller, config_dict)
                real_axis.address = address
                real_axis.no_offset = True
                self.controller._Controller__initialized_axis[real_axis] = True
                real_axes[axis_name] = real_axis
            self.__real_axes_namespace = types.SimpleNamespace(**real_axes)
        return self.__real_axes_namespace

    @lazy_init
    def sync(self, user_position):
        """
        Synchronizes all real linked axes members of the given virtual axis
        to the given position. No motion will take place.
        The position is given in user units of the virtual axis.
        """
        dial_position = self.user2dial(user_position)
        for slave_axis in self.real_axes.__dict__.values():
            slave_axis.dial = dial_position

        self.acceleration = self.acceleration
        self.velocity = self.velocity
        # Reset control encoder
        # TODO: if any?
        _ackcommand(self.controller._cnx, "CTRLRST %s" % self.address)
        # switch power on (should re-enable the closed loop)
        self.on()

        self.sync_hard()

        self.position = user_position

        return self.position

    @lazy_init
    def get_info(self):
        """
        Return information about the given virtual axis configured 
        as a motor in the current SPEC session.
        The list of real axes linked together should not be configured 
        but can be accessed through dedicated commands (linkedmv, linkedhome, etc).
        """

        cnx = self.controller._cnx
        linked_axis = self.controller.get_linked_axis()

        r = "Virtual axis          : %s\n" % self.name
        r += "POWER                 : %s\n" % _command(cnx, "?POWER %s" % self.address)
        real_axes = linked_axis.get(self.address, list())
        r += "Real linked axes      : %r\n" % real_axes
        position = int(_command(cnx, "?POS %s" % self.address))
        r += "Indexer steps         : %s\n" % position
        r += "Indexer in user unit  : %s\n" % (position / self.steps_per_unit)

        for add in real_axes:
            pre_cmd = "%s:" % add
            r += "\n"
            r += "Real axis             : %s\n" % _command(cnx, pre_cmd + "?NAME")
            has = "NO" if _command(cnx, pre_cmd + "?CFG HOMESRC") == "NONE" else "YES"
            r += "Home switch           : %s\n" % has
            r += (
                "Homing                : %s\n"
                % _command(cnx, pre_cmd + "?HOMESTAT").split()[0]
            )
            has = "NO" if _command(cnx, pre_cmd + "?CFG CTRLENC") == "NONE" else "YES"
            r += "Control encoder       : %s\n" % has
            pos = int(_command(cnx, pre_cmd + "?POS"))
            r += "Indexer steps         : %s\n" % pos
            measure = int(_command(cnx, pre_cmd + "?POS MEASURE"))
            r += "Encoder steps         : %s\n" % measure
            try:
                homepos = _command(cnx, pre_cmd + "?HOMEPOS")
            except RuntimeError:
                homepos = "unavailable"
            r += "Homepos steps         : %s\n" % homepos
            r += "Indexer user unit     : %s\n" % (pos / self.steps_per_unit)
            r += "Encoder user unit     : %s\n" % (measure / self.steps_per_unit)
            r += "Closed loop           : %s\n" % _command(cnx, pre_cmd + "?PCLOOP")
        return r

    @lazy_init
    def _disprotected_command(self, cmd, wait=True, polling_time=DEFAULT_POLLING_TIME):
        try:
            self.__in_disprotected_move = True
            with self._lock:
                if self.is_moving:
                    raise RuntimeError("axis %s state is %r" % (self.name, "MOVING"))

                # create motion object for hooks
                motion = Motion(self, None, None)
                self._Axis__execute_pre_move_hook(motion)

                def start_one(controller, motions):
                    cnx = controller._cnx
                    _command(
                        cnx,
                        cmd,
                        pre_cmd="#DISPROT ALL %s ; "
                        % " ".join(
                            (str(rm.address) for rm in self.real_axes.__dict__.values())
                        ),
                    )
                    # IcePAP status is not immediately MOVING after home search command is sent
                    gevent.sleep(0.2)

                def stop_one(controller, motions):
                    controller.stop(motions[0].axis)

                self._group_move.move(
                    {self.controller: [motion]},
                    start_one,
                    stop_one,
                    wait=False,
                    polling_time=polling_time,
                )
        finally:
            self.__in_disprotected_move = False
        if wait:
            self.wait_move()

    @property
    @lazy_init
    def _hw_position(self):
        if self.__in_disprotected_move or self.is_moving:
            # do not really read hw pos when moving,
            # since it can be a disprotected move, that
            # would report an error
            return self.dial
        else:
            return super()._hw_position

    @lazy_init
    def home(self, switch=1, wait=True, polling_time=DEFAULT_POLLING_TIME):
        raise NotImplementedError(
            "Linked axis homing cannot be an automatic procedure, see with electronics unit."
        )
