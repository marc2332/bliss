# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common.task import task
from bliss.common.cleanup import cleanup
from bliss.common.event import dispatcher
from bliss.config import channels
import time
import socket

"""
Fast shutter, controlled by IcePAP. If the home switch is active, the shutter
is open.
Configuration:
class: fshutter
name: fshut
fshutter_mot: $fshut_mot  #reference to the icepap motor
musst:  $musst            #reference to the musst object (if any)
step: 0.25                #relative move to open/close the shutter, if no musst
shift: 0.16               #shift from the home search position to set as 0
icepap_steps: 500         #icepap steps to move when external trigger received
"""


class fshutter:
    def __init__(self, name, config):
        self.fshutter_mot = config["fshutter_mot"]
        self._state_chan = channels.Channel(
            "fshutter:%s" % name, callback=self.__state_changed
        )

        try:
            self.musst = config["musst"]
            try:
                self.icepap_steps = config["icepap_steps"]
            except:
                self.icepap_steps = 500
        except:
            self.musst = None
            self.step = config["step"]
            self.icepap_steps = self.fshutter_mot.steps_per_unit * self.step

        self.shift = config["shift"] / self.fshutter_mot.steps_per_unit

        self.enastate = None
        self.state

    def _state(self):
        enastate = self.enastate
        if self.musst:
            return "CLOSED" if self.musst.putget("?VAL CH1") == "0" else "OPENED"
        else:
            if enastate:
                self.disable()
            if self.fshutter_mot.state.READY:
                if self.fshutter_mot.state.HOME:
                    if enastate:
                        self.enable(self.icepap_steps)
                    return "OPENED"
                else:
                    if enastate:
                        self.enable(self.icepap_steps)
                    return "CLOSED"
            else:
                if enastate:
                    self.enable(self.icepap_steps)
                return "UNKNOWN"

    @property
    def state(self):
        st = self._state()
        self._state_chan.value = st
        return st

    def __state_changed(self, st):
        dispatcher.send("state", self, st)

    def _toggle_state_icepap(self):
        self.disable()
        self.fshutter_mot.rmove(self.step, wait=True)
        self.enable()

    def _toggle_state(self):
        if self.musst:
            if not self.enastate:
                self.enable(self.icepap_steps)
            btrig = int(self.musst.putget("?BTRIG"))
            self.musst.putget("#BTRIG %d" % (1 - btrig))
            self._state_chan.value = "MOVING"
            # 'moving' state is not reported properly
            # by libicepap in shutter mode
            while True:
                fstatus = int(self._icepap_query("?FSTATUS %d\n").split()[-1], 16)
                moving = (fstatus & 1 << 10) or (fstatus & 1 << 11)
                if moving:
                    time.sleep(0.01)
                else:
                    break
        else:
            self._toggle_state_icepap()
        return self.state

    def msopen(self):
        state = self.state
        if state == "CLOSED":
            # already closed
            return
        self._toggle_state()

    def msclose(self):
        state = self.state
        if state == "OPENED":
            # already open
            return
        self._toggle_state()

    def open(self):
        state = self.state
        print("shutter is %s" % state)

        if state == "OPENED":
            # already open
            return

        new_state = self._toggle_state()
        print("now is %s" % new_state)

    def close(self):
        state = self.state
        print("shutter state is %s" % state)

        if state == "CLOSED":
            # already closed
            return

        new_state = self._toggle_state()
        print("now is %s" % new_state)

    def _icepap_query(self, cmd_str):
        """Send directly to Icepap controller"""
        motor_address = self.fshutter_mot.config.get("address", int)
        controller_host = self.fshutter_mot.controller.host
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((controller_host, 5000))
        if not cmd_str.endswith("\n"):
            cmd_str += "\n"
        s.sendall(cmd_str % motor_address)
        return s.recv(1024)

    def _cfg(self, up, down):
        if up == down:
            return self._icepap_query("#%d:stop")
        else:
            self._icepap_query("#%%d:listdat %d %d 2" % (up, down))
            return self._icepap_query("#%d:ltrack inpos")

    def disable(self):
        self.enastate = False
        return self._cfg(0, 0)

    def enable(self, steps=500):
        self.enastate = True
        return self._cfg(0, steps)

    @task
    def home(self):
        def home_cleanup():
            self.fshutter_mot.velocity = self.fshutter_mot.config_velocity
            self.enable()

        with cleanup(home_cleanup):
            self.disable()

            self.fshutter_mot.velocity = 0.3
            if self.musst:
                self.musst.putget("#BTRIG 0")

            status = self._icepap_query("#%d:?STATUS")
            status = int(status.split()[1], 16)

            if status & 0x00100000 == 0:
                self.fshutter_mot.home(-1)

            elif status & 0x00100000 == 1048576:
                self.fshutter_mot.home(1)
            else:
                raise RuntimeError("bad status")

            self.fshutter_mot.sync_hard()
            self.fshutter_mot.rmove(self.shift)
            self.fshutter_mot.dial = 0
            self.fshutter_mot.position = 0
            self._icepap_query("#%d:POS INPOS 0")
            if self.musst:
                self.musst.putget("#ABORT")
                self.musst.putget("#CH CH1 0")
