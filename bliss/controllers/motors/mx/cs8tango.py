import logging
from bliss import setup_globals
from bliss.common.tango import DeviceProxy
from bliss.controllers.motor import Controller
from bliss.common.event import dispatcher
from bliss.common.axis import AxisState
import gevent
import gevent.lock
import time
import types
import sys


class cs8tango(Controller):
    def __init__(self, *args, **kwargs):
        Controller.__init__(self, *args, **kwargs)

        self._lock = gevent.lock.Semaphore()

    def initialize(self):
        # velocity and acceleration are not mandatory in config
        self.axis_settings.config_setting["velocity"] = False
        self.axis_settings.config_setting["acceleration"] = False

    def initialize_axis(self, axis):
        axis.settings.set("dial_position", self.read_position(axis))
        axis.settings.set("state", self.state(axis))

    def state(self, axis):
        with self._lock:
            return (
                AxisState("MOVING")
                if setup_globals.robodiff.robot.getCachedVariable(
                    "TaskStatus"
                ).getValue()
                != "-1"
                else AxisState("READY")
            )

    def stop(self, axis):
        with self._lock:
            r = setup_globals.robodiff
            r.abort()

    def start_one(self, motion):
        name = motion.axis.config.get("cs8name")
        r = setup_globals.robodiff.robot
        with self._lock:
            r.setVal3GlobalVariableDouble("n_%s" % name, str(motion.target_pos))
            r.executeTask("Move%s" % name)

    def read_position(self, axis):
        name = axis.config.get("cs8name")
        val3_varname = "n_Read%s" % name
        r = setup_globals.robodiff.robot
        if self.state(axis).READY:
            with self._lock:
                r.executeTask("Read%s" % name)
        return float(r.getVal3GlobalVariableDouble(val3_varname))
