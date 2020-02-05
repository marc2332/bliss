# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from StaubCom import robot
from bliss.common.utils import grouped
from bliss.common.task import task
from bliss.common.cleanup import cleanup, error_cleanup
from bliss.config import static as static_config
from functools import wraps
import copy
import gevent
import math
import time
import datetime
import itertools
import subprocess
import os
import shutil
import sys
import configparser
import ast
import inspect
import numpy
import logging
import collections
from logging.handlers import TimedRotatingFileHandler

robodiff_log = logging.getLogger("flex")
robodiff_log.setLevel(logging.DEBUG)
robodiff_log_formatter = logging.Formatter(
    "%(name)s %(levelname)s %(asctime)s %(message)s"
)
robodiff_log_handler = None
robodiff_log.propagate = False
staubcom_logger = logging.getLogger("ROBOT")
staubcom_logger.propagate = False

from bliss.common import event


def grouper(iterable, n):
    args = [iter(iterable)] * n
    return itertools.zip_longest(fillvalue=None, *args)


BUSY = False
DEFREEZING = False


def notwhenbusy(func):
    @wraps(func)
    def _(self, *args, **kw):
        # if caller is self, then we can always execute
        frame = inspect.currentframe(1)
        caller = frame.f_locals.get("self", None)
        if self == caller:
            return func(self, *args, **kw)
        else:
            global BUSY
            global DEFREEZING
            if BUSY or DEFREEZING:
                raise RuntimeError("Cannot execute while robot is busy")
            else:
                try:
                    BUSY = True
                    return func(self, *args, **kw)
                finally:
                    BUSY = False

    return _


class BackgroundGreenlets(object):
    def __init__(self, *args):
        self.func_args = args
        self.greenlets = list()

    def kill_greenlets(self, _):
        gevent.killall(self.greenlets)

    def __enter__(self):
        for f, fargs in grouper(self.func_args, 2):
            self.greenlets.append(gevent.spawn_later(0.2, f, *fargs))
        return self

    def execute(self, func, *args, **kwargs):
        self.g = gevent.spawn(func, *args, **kwargs)
        self.g.link(self.kill_greenlets)
        return self.g.get()

    def __exit__(self, *args, **kwargs):
        pass


RobotMotors = collections.namedtuple(
    "robodiff_motors",
    "fshut chi phi sampx sampy phiy phiz apz bstopz DtoX focus y z dw phienc phiyenc phizenc",
)


class Robodiff(object):
    def __init__(self, name, config, config_objects=None):
        self._config_objects = config_objects
        self.cs8_ip = config.get("ip")
        self.robot = None
        self.robot_exceptions = []
        self.crash = 0
        self._stop_fountain_task = None
        self.user_name = None

        robot.setLogFile(config.get("log_file"))
        robot.setExceptionLogFile(config.get("exception_file"))
        global robodiff_log_handler
        robodiff_log_handler = TimedRotatingFileHandler(
            config.get("flex_log_file"), when="midnight", backupCount=7
        )
        robodiff_log_handler.setFormatter(robodiff_log_formatter)
        robodiff_log.addHandler(robodiff_log_handler)
        robodiff_log.info("")
        robodiff_log.info("")
        robodiff_log.info("")
        robodiff_log.info("#" * 50)
        robodiff_log.info("RoboDiff Initialised")

    def connect(self):
        if self._config_objects is None:
            from bliss import setup_globals

            for m in RobotMotors._fields:
                setattr(self, m, getattr(setup_globals, m))
            self.zoom = setup_globals._zoom
            self.musst = setup_globals.musst1
            self.musst2 = setup_globals.musst2
            self.detcover = setup_globals.detcover
            self.wcid30m = setup_globals.wcid30m
            self.wcid30p = setup_globals.wcid30p
            self.dm_reader = setup_globals.dm_reader
            self.pilatus = setup_globals.pilatus
            self.cryo = setup_globals.cryostream
            self.i0 = setup_globals.i0
            self.i1 = setup_globals.i1
            self.acc_margin = 3500
            self.config_acc_margin = 6000
            self.shutter_predelay = 62e-3
            self.shutter_postdelay = 17e-3
            self.musst_sampling = 50
            self.diag_n = 0
            self.pilatus_deadtime = float(
                static_config.get_config().get_config(self.pilatus.name)["deadtime"]
            )
        robodiff_log.info("connecting to Flex")
        self.robot = robot.Robot("flex", self.cs8_ip)
        event.connect(self.robot, "robot_exception", self._enqueue_robot_exception_msg)
        robodiff_log.info("Connection done")

    def diode(self, read_i0=True, read_i1=True):
        i0_counts = 0
        i1_counts = 0
        if read_i0:
            i0_counts = abs(self.i0.read())
        if read_i1:
            i1_counts = abs(self.i1.read())
        return i0_counts, i1_counts

    def _enqueue_robot_exception_msg(self, msg):
        self.robot_exceptions.append(msg)

    def state(self):
        robot_state = str(self.robot.getState())
        if robot_state == "READY":
            # check dewar
            robot_state = self.dw.state
            if robot_state == "READY":
                # check dm reader
                return self.dm_reader.state
        return "MOVING"

    @task
    def _simultaneous_move(self, *args):
        axis_list = []
        for axis, target in grouped(args, 2):
            axis_list.append(axis)
            axis.wait_move()
            axis.move(target, wait=False)
        return [axis.wait_move() for axis in axis_list]

    @task
    def _simultaneous_rmove(self, *args):
        axis_list = []
        for axis, target in grouped(args, 2):
            axis_list.append(axis)
            axis.wait_move()
            axis.rmove(target, wait=False)
        return [axis.wait_move() for axis in axis_list]

    def get_cachedVariable_list(self):
        return list(self.robot._cached_variables.keys())

    @notwhenbusy
    def setSpeed(self, speed):
        if 0 <= speed <= 100:
            robodiff_log.info("Set speed to %d" % speed)
            self.robot.setSpeed(speed)
            robodiff_log.info("Speed is at %s" % str(self.robot.getSpeed()))

    @notwhenbusy
    def enablePower(self, state):
        state = bool(state)
        for i in range(0, 10):
            self.robot.enablePower(state)
            if state:
                if self.robot.getCachedVariable("IsPowered").getValue() == "true":
                    break
            else:
                if self.robot.getCachedVariable("IsPowered").getValue() == "false":
                    break
            gevent.sleep(1)
        if i == 9 and self.robot.getCachedVariable("IsPowered") is not state:
            msg = "Cannot set power to %s" % str(state)
            robodiff_log.error(msg)
            raise RuntimeError(msg)
        robodiff_log.info("Power set to %s" % state)

    def abort(self):
        self.robot.abort()
        robodiff_log.info("Robot aborted")

    def set_io(self, dio, boolean):
        robodiff_log.info("Set IO %s to %s" % (dio, str(bool(boolean))))
        if bool(boolean):
            self.robot.execute("data:" + dio + "=true")
        else:
            self.robot.execute("data:" + dio + "=false")

    def get_robot_cache_variable(self, varname):
        try:
            return self.robot.getCachedVariable(varname).getValue()
        except Exception:
            return ""

    def dewar_port(self, dw_port):
        self.set_portNumber(dw_port)
        self._dewar_port()

    def robodiff_reset(self):
        self._robodiff_reset()

    def reset_move(self):
        self._reset_move()
        self.robot.executeTask("reset", timeout=5)

    def prestart_robodiff(self, cellNumber, SampleNumber):
        self._simultaneous_move(
            self.phiz,
            0,
            self.phiy,
            0,
            self.bstopz,
            self.bstopz.low_limit,
            self.sampx,
            0,
            self.sampy,
            0,
            self.phi,
            0,
            self.apz,
            self.apz.low_limit,
            self.DtoX,
            self.DtoX.high_limit,
        )
        self.zoom.move(1, wait=False)
        self.robodiff_reset()
        self.wcid30m.set("lightin", 0)
        self.set_cellNumber(cellNumber)
        self.set_sampleNumber(SampleNumber)

    def move_to_park(self):
        self._simultaneous_move(
            self.phiz,
            0,
            self.phiy,
            0,
            self.bstopz,
            self.bstopz.low_limit,
            self.sampx,
            0,
            self.sampy,
            0,
            self.phi,
            0,
            self.apz,
            self.apz.low_limit,
            self.DtoX,
            self.DtoX.high_limit,
        )
        self.robodiff_reset()
        self.wcid30m.set("lightin", 0)
        self.detcover.set_in()
        with cleanup(self.update_motors):
            self._MoveToPark()

    def move_to_gonio(self):
        self._simultaneous_move(
            self.phiz,
            0,
            self.phiy,
            0,
            self.bstopz,
            self.bstopz.low_limit,
            self.sampx,
            0,
            self.sampy,
            0,
            self.phi,
            0,
            self.apz,
            self.apz.low_limit,
            self.DtoX,
            self.DtoX.high_limit,
        )
        self.robodiff_reset()
        self.wcid30m.set("lightin", 0)
        self.detcover.set_in()
        with cleanup(self.update_motors):
            self._MoveToGonio()
        self.move_to_focus()

    def move_to_bin(self):
        self._simultaneous_move(
            self.phiz,
            0,
            self.phiy,
            0,
            self.bstopz,
            self.bstopz.low_limit,
            self.sampx,
            0,
            self.sampy,
            0,
            self.phi,
            0,
            self.apz,
            self.apz.low_limit,
            self.DtoX,
            self.DtoX.high_limit,
        )
        self.robodiff_reset()
        self.wcid30m.set("lightin", 0)
        self.detcover.set_in()
        with cleanup(self.update_motors):
            self._MoveToBin()

    def move_to_beam(self):
        with cleanup(self.update_motors):
            self._move_to_beam()

    def move_from_beam(self):
        with cleanup(self.update_motors):
            self._move_from_beam()

    def update_motors(self):
        for m in (self.chi, self.focus, self.y, self.z):
            m.sync_hard()

    def move_to_focus(self):
        move_task = self._simultaneous_move(
            self.sampx, 0.88, self.sampy, -0.47, wait=False
        )
        self._move_roboDiff_XYZ(-1.2, -1.17, 1.66)
        try:
            move_task.get(timeout=30)
        except:
            sys.excepthook(*sys.exc_info())
            raise RuntimeError("Cannot move sampx, sampy")

    def yag_in(self):
        self._simultaneous_move(
            self.phiz,
            0,
            self.phiy,
            0,
            self.bstopz,
            self.bstopz.low_limit,
            self.sampx,
            0,
            self.sampy,
            0,
            self.phi,
            0,
            self.apz,
            self.apz.low_limit,
            self.DtoX,
            self.DtoX.high_limit,
        )
        self.robodiff_reset()
        self.wcid30m.set("lightin", 0)
        self.detcover.set_in()
        self._pick_yag()
        self._move_roboDiff_XYZ(0.0, 0.1, 0.3)
        self._simultaneous_move(self.sampx, 0, self.sampy, 0)

    def yag_out(self):
        self._simultaneous_move(
            self.phiz,
            0,
            self.phiy,
            0,
            self.bstopz,
            self.bstopz.low_limit,
            self.sampx,
            0,
            self.sampy,
            0,
            self.phi,
            0,
            self.apz,
            self.apz.low_limit,
            self.DtoX,
            self.DtoX.high_limit,
        )
        self.robodiff_reset()
        self.wcid30m.set("lightin", 0)
        self.detcover.set_in()
        with cleanup(self.update_motors):
            self._drop_yag()

    def prepare_DC(self):
        move_task = self._simultaneous_move(
            self.sampx,
            0.88,
            self.sampy,
            -0.47,
            self.DtoX,
            235,
            self.apz,
            -20,
            self.bstopz,
            -20,
            wait=False,
        )
        self._move_roboDiff_XYZ(-1.2, -1.17, 1.66)
        self.lightin(False)
        move_task.get(timeout=30)

    def stop_fountain(self):
        self.wcid30p.set("keep_cold", 0)

    @task
    def set_detcover(self, set_in=True):
        with gevent.Timeout(
            10, RuntimeError("Could not put detector %s" % ("in" if set_in else "out"))
        ):
            if set_in:
                self.detcover.set_in()
            else:
                self.detcover.set_out()

    def load_sample(self, CellNumber, PuckNumber, SampleNumber):
        while True:
            try:
                temperature = self.cryo.read()
            except AttributeError:
                raise
            except Exception:
                sys.excepthook(*sys.exc_info())
                gevent.sleep(0.5)
                continue
            else:
                if temperature > 300.0:
                    raise RuntimeError("Cryostreaming warming up")
                break
        if self.crash >= 2:
            self.reset_move()
            raise RuntimeError("Too many crashes")
        with cleanup(self.update_motors):
            if self._stop_fountain_task is not None:
                self._stop_fountain_task.kill()
            self._stop_fountain_task = gevent.spawn_later(60 * 60, self.stop_fountain)
            self.wcid30p.set("keep_cold", 1)
            detcover_task = self.set_detcover(wait=False)
            if PuckNumber > 3 or SampleNumber > 10:
                raise RuntimeError("Cannot set puck/sample number")
            SampleNb = SampleNumber + (PuckNumber - 1) * 10
            prestart_task = gevent.spawn(self.prestart_robodiff, CellNumber, SampleNb)
            self.dw.move(CellNumber)
            detcover_task.get()
            prestart_task.get()
            res = self._load()
            if not res:
                return False
            self.wcid30m.set("lightin", 0)
            self.prepare_DC()
            return True

    def unload_sample(self, CellNumber, PuckNumber, SampleNumber, retry=True):
        if self.crash >= 2:
            self.reset_move()
            raise RuntimeError("Too many crashes")
        self._saved_apz = self.apz.position
        with cleanup(self.update_motors):
            detcover_task = self.set_detcover(wait=False)
            if PuckNumber > 3 or SampleNumber > 10:
                raise RuntimeError("Cannot set puck/sample number")
            SampleNb = SampleNumber + (PuckNumber - 1) * 10
            self.wcid30m.set("lightin", 0)
            prestart_task = gevent.spawn(self.prestart_robodiff, CellNumber, SampleNb)
            self.dw.move(CellNumber + 2)
            if retry:
                n = 120
            else:
                n = 1
            for i in range(n):
                if self.dm_reader.sample_is_present(PuckNumber, SampleNumber) == (
                    True,
                    False,
                ):
                    break
                if self.dm_reader.sample_is_present(PuckNumber, SampleNumber) == (
                    True,
                    True,
                ):
                    if i == n - 1:
                        raise RuntimeError("Vial present")
                if self.dm_reader.sample_is_present(PuckNumber, SampleNumber) == (
                    False,
                    False,
                ):
                    if i == n - 1:
                        raise RuntimeError("No Puck")
                if i > 1 and i <= 9:
                    time.sleep(2)
                    print("Puck or vial present, Checking again in 2s")
                if i > 9 and i <= 59:
                    time.sleep(10)
                    print("Puck or vial present, Checking again in 10s")
                if i > 59:
                    time.sleep(20)
                    print("Puck or vial present, Checking again in 20s")

            self.dw.move(CellNumber)
            softfill_task = gevent.spawn(self._do_soft_fill)
            with error_cleanup(softfill_task.kill):
                self.wcid30m.set("lightin", 0)
                try:
                    detcover_task.get(timeout=15)
                except:
                    raise RuntimeError("Cannot put detector cover in")
                prestart_task.get()
                softfill_task.get()
            self._unload()
            self.wcid30m.set("cryo_out", 0)

    def _do_soft_fill(self, duration=10):
        return

    def dewar_load(self, cellNumber):
        self.dw.move(cellNumber + 5)

    def set_portNumber(self, portNumber):
        self.robot.setVal3GlobalVariableDouble("nPortNumber", str(portNumber))

    def set_sampleNumber(self, SampleNumber):
        self.robot.setVal3GlobalVariableDouble("nSampleNumber", str(SampleNumber))

    def set_cellNumber(self, cellNumber):
        self.robot.setVal3GlobalVariableDouble("nCellNumber", str(cellNumber))

    def get_sampleNumber(self, SampleNbVar="nSampleNumber"):
        return self.robot.getVal3GlobalVariableDouble(SampleNbVar)

    def _dewar_port(self):
        self.robot.executeTask("open_dewar", timeout=5)
        if self.get_robot_cache_variable("sTaskReturn") == "ABORTED":
            raise RuntimeError("aborted")

    def _MoveToPark(self):
        self.robot.executeTask("MoveToPark", timeout=15)
        if self.get_robot_cache_variable("sTaskReturn") == "ABORTED":
            raise RuntimeError("aborted")

    def _MoveToBin(self):
        self.robot.executeTask("MoveToBin", timeout=15)
        if self.get_robot_cache_variable("sTaskReturn") == "ABORTED":
            raise RuntimeError("aborted")

    def _move_to_beam():
        self.robot.executeTask("MoveToBeam", timeout=15)
        if self.get_robot_cache_variable("sTaskReturn") == "ABORTED":
            raise RuntimeError("aborted")

    def _move_from_beam():
        self.robot.executeTask("MoveFromBeam", timeout=15)
        if self.get_robot_cache_variable("sTaskReturn") == "ABORTED":
            raise RuntimeError("aborted")

    def _MoveToGonio(self):
        self.robot.executeTask("MoveToGonio", timeout=15)
        if self.get_robot_cache_variable("sTaskReturn") == "ABORTED":
            raise RuntimeError("aborted")

    def _pick_yag(self):
        self.robot.executeTask("Pick_YAG", timeout=15)
        if self.get_robot_cache_variable("sTaskReturn") == "ABORTED":
            raise RuntimeError("aborted")

    def _drop_yag(self):
        self.robot.executeTask("Drop_YAG", timeout=15)
        if self.get_robot_cache_variable("sTaskReturn") == "ABORTED":
            raise RuntimeError("aborted")

    def move_kappa(self, target):
        self.robot.setVal3GlobalVariableDouble("n_Kappa", str(target))
        self.robot.executeTask("MoveKappa", timeout=5)

    def move_y(self, target):
        self.robot.setVal3GlobalVariableDouble("n_Y", str(target))
        self.robot.executeTask("MoveY", timeout=5)

    def move_z(self, target):
        self.robot.setVal3GlobalVariableDouble("n_Z", str(target))
        self.robot.executeTask("MoveZ", timeout=5)

    def move_focus(self, target):
        self.robot.setVal3GlobalVariableDouble("n_Focus", str(target))
        self.robot.executeTask("MoveFocus", timeout=5)

    def _move_roboDiff_XYZ(self, n_Focus, n_Y, n_Z):
        with cleanup(self.update_motors):
            self.robot.setVal3GlobalVariableDouble("n_Focus", str(n_Focus))
            self.robot.setVal3GlobalVariableDouble("n_Y", str(n_Y))
            self.robot.setVal3GlobalVariableDouble("n_Z", str(n_Z))
            self.robot.executeTask("Move_FocusYZ", timeout=5)

    def _robodiff_reset(self):
        self.robot.executeTask("RoboD_prepare")
        if self.get_robot_cache_variable("sTaskReturn") == "ABORTED":
            raise RuntimeError("aborted")

    def _reset_move(self):
        self.robot.executeTask("reset", timeout=5)

    def executeTask(self, *args, **kwargs):
        output = self.robot.executeTask(*args, **kwargs)
        return self.robot.getCachedVariable("sTaskReturn").getValue()

    def logfile(self, msg):
        self.logpath = os.path.join(os.environ["HOME"], "log")
        with open(os.path.join(self.logpath, "RoboDiff.logfile"), "a+") as f:
            f.write("%s : %s \n" % (time.ctime(), msg))

    def _load(self):
        task_output = self.executeTask("load")
        robot_sampleNb = self.get_sampleNumber()
        sample = 1 + ((robot_sampleNb - 1) % 10)
        puck = 1 + ((robot_sampleNb - 1) // 10)
        cell = self.dw.position
        log_msg = (
            "("
            + str(int(cell))
            + ", "
            + str(int(puck))
            + ", "
            + str(int(sample))
            + ") "
        )

        if task_output == "ABORTED":
            self.set_sampleNumber(0)
            self.logfile(log_msg + "Load aborted")
            raise RuntimeError("aborted")
        elif task_output == "Crash - Vial lost in movefrombeam (Puck)":
            if self.get_sampleNumber("nSampleLoaded") != self.get_sampleNumber():
                self.set_sampleNumber(0)
            self.logfile(log_msg + "Error --- Load Crash in movefrombeam (Puck)")
            self.crash += 1
            self.robot_init()
            return False
        elif task_output == "Crash - Vial lost in movefrombeam (Beam)":
            if self.get_sampleNumber("nSampleLoaded") != self.get_sampleNumber():
                self.set_sampleNumber(0)
            self.logfile(log_msg + "Error --- Load Crash in movefrombeam (Beam)")
            self.crash += 1
            self.robot_init()
            return False
        elif task_output == "Sample ON":
            if self.get_sampleNumber("nSampleLoaded") != self.get_sampleNumber():
                self.set_sampleNumber(0)
            self.logfile(log_msg + "ERROR --- Load sample on")
            return False
        elif task_output == "No sample in puck":
            if self.get_sampleNumber("nSampleLoaded") != self.get_sampleNumber():
                self.set_sampleNumber(0)
            self.logfile(log_msg + "ERROR --- Load no sample in puck")
            return False
        elif task_output == "Vial lost in movefrombeam":
            if self.get_sampleNumber("nSampleLoaded") != self.get_sampleNumber():
                self.set_sampleNumber(0)
            self.logfile(log_msg + "ERROR --- Load Vial lost in movefrombeam")
            return False
        elif task_output == "Vial lost in unload":
            if self.get_sampleNumber("nSampleLoaded") != self.get_sampleNumber():
                self.set_sampleNumber(0)
            self.logfile(log_msg + "ERROR --- Load Vial lost in unload")
            return False
        elif task_output == "Sample lost on assistant":
            if self.get_sampleNumber("nSampleLoaded") != self.get_sampleNumber():
                self.set_sampleNumber(0)
            self.logfile(log_msg + "ERROR --- Load Sample lost on assistant")
            return False
        elif task_output == "Vial lost in movetobeam":
            if self.get_sampleNumber("nSampleLoaded") != self.get_sampleNumber():
                self.set_sampleNumber(0)
            self.logfile(log_msg + "ERROR --- Load Vial lost in move to beam")
            return False
        self.crash = 0
        self.logfile(log_msg + "Load done")
        return True

    def _unload(self):
        task_output = self.executeTask("unload")
        robot_sampleNb = self.get_sampleNumber()
        sample = 1 + ((robot_sampleNb - 1) % 10)
        puck = 1 + ((robot_sampleNb - 1) // 10)
        cell = self.dw.position
        log_msg = (
            "("
            + str(int(cell))
            + ", "
            + str(int(puck))
            + ", "
            + str(int(sample))
            + ") "
        )
        if task_output == "ABORTED":
            self.set_sampleNumber(0)
            self.logfile(log_msg + "%s : Unload aborted" % self.user_name)
            raise RuntimeError("aborted")
        elif task_output == "Crash - Vial lost in unload movefrombeam (Beam)":
            self.set_sampleNumber(0)
            self.logfile(
                log_msg
                + "%s : Error --- Unload Crash in movefrombeam (Beam)" % self.user_name
            )
            self.crash += 1
            self.robot_init()
            return False
        elif task_output == "Crash - Vial lost in unload":
            self.set_sampleNumber(0)
            self.logfile(
                log_msg + "%s : Error --- Unload Crash in unload" % self.user_name
            )
            self.crash += 1
            self.robot_init()
            return False
        elif task_output == "Vial lost in movefrombeam":
            self.set_sampleNumber(0)
            self.logfile(
                log_msg
                + "%s : ERROR --- Unload Vial lost in movefrombeam" % self.user_name
            )
            return False
        elif task_output == "Sample ON":
            self.set_sampleNumber(0)
            self.logfile(log_msg + "%s : ERROR --- Unload sample on" % self.user_name)
            return False
        elif task_output == "Vial lost in unload":
            self.set_sampleNumber(0)
            self.logfile(
                log_msg + "%s : ERROR --- Unload vial lost in unload" % self.user_name
            )
            return False
        elif task_output == "Cannot remove sample":
            self.set_sampleNumber(0)
            self.logfile(
                log_msg
                + "%s : ERROR --- Unload cannot remove sample in trash" % self.user_name
            )
            return False
        elif task_output == "Cannot remove sample in movefrombeam":
            self.set_sampleNumber(0)
            self.logfile(
                log_msg
                + "%s : ERROR --- Unload cannot remove sample in trash (movefrombeam)"
                % self.user_name
            )
            return False
        self.logfile(log_msg + "%s : Unload done" % self.user_name)
        self.set_sampleNumber(0)
        self.crash = 0
        return True

    def phi_init(self):
        self.phi.velocity = self.phi.config_velocity
        self.phi.acceleration = self.phi.config_acceleration
        print("   Searching home on phi")
        self.phi.home(1)
        print("   Found home")
        print("   move back to 0")
        self.phi.rmove(self.phi.config.get("init_offset", float))
        print("   Phi at 0")
        self.phi.dial = 0
        self.phi.position = 0
        self.musst.ABORT  # in case a program is running
        self.musst.putget("#CH CH2 0")

    def centring_table_init(self):
        self.sampx.apply_config()
        self.sampy.apply_config()
        print("   Searching lim- on sampx and sampy")
        self.sampx.hw_limit(-1, wait=False)
        self.sampy.hw_limit(1, wait=False)
        with gevent.Timeout(30, RuntimeError("Timeout while searching for limits")):
            self.sampx.wait_move()
            self.sampy.wait_move()
        print("   Found lim- on sampx and sampy")
        print("   Moving sampx and sampy at the center...")
        self.sampx.rmove(self.sampx.config.get("init_offset", float), wait=False)
        self.sampy.rmove(self.sampy.config.get("init_offset", float), wait=False)
        self.sampx.wait_move()
        self.sampy.wait_move()
        print("   Done.")
        self.sampx.position = 0
        self.sampx.dial = 0
        self.sampy.position = 0
        self.sampy.dial = 0
        self.musst.putget("#CH CH5 0")
        self.musst.putget("#CH CH6 0")

    def robot_table_init(self):
        self.phiy.apply_config()
        self.phiz.apply_config()
        print("   Searching lim- on phiy")
        with gevent.Timeout(20, RuntimeError("Timeout while searching for phiy lim-")):
            self.phiy.hw_limit(-1)
        print("   Found lim- on phiy")
        print("   Moving phiy at the center")
        self.phiy.rmove(-self.phiy.config.get("init_offset", float))
        print("   phiy at the center")
        print("   Searching lim- on phiz")
        with gevent.Timeout(20, RuntimeError("Timeout while searching for phiy lim-")):
            self.phiz.hw_limit(-1)
        print("   Found lim- on phiz")
        print("   move phiz at the center")
        self.phiz.rmove(self.phiz.config.get("init_offset", float), wait=True)
        print("   phiz at the center")
        self.phiy.position = 0
        self.phiy.dial = 0
        self.phiz.position = 0
        self.phiz.dial = 0
        self.musst.ABORT
        self.musst.putget("#CH CH3 0")
        self.musst.putget("#CH CH4 0")

    def robot_init(self):
        print("Robot table init")
        self.robot_table_init()
        print("Centering table init")
        self.centring_table_init()
        print("Phi init")
        self.phi_init()

    def cell_pos_init(self, cellNumber=0, robot_init=True):
        # TO DO INIT of sampx, sampy, phiy,phiz and phi
        if robot_init:
            self.robot_init()
        else:
            self._simultaneous_move(
                self.sampx,
                0,
                self.sampy,
                0,
                self.phiy,
                0,
                self.phiz,
                0,
                self.phi,
                0,
                wait=True,
            )
        if cellNumber == 0:
            for cellNumber in range(1, 9):
                print("Puck origins search on cell ", cellNumber)
                self.robodiff_reset()
                self.dw.move(cellNumber)
                self.set_cellNumber(str(cellNumber))
                self.robot.executeTask("Align")
            self.move_to_park()
            return "Done"
        if cellNumber >= 1 and cellNumber <= 8:
            print("Puck origins search on cell ", cellNumber)
            self.robodiff_reset()
            self.dw.move(cellNumber)
            self.set_cellNumber(str(cellNumber))
            self.robot.executeTask("Align")
            self.move_to_park()
            return "Done"

    def dw_check_pos(self):
        print("Check is done on cell 1, puck position 1")
        dwpos = self.dw.position
        for i in range(1, 11):
            self.dw.move(i)
            time.sleep(1)
            rot_trans = self.dm_reader.get_RotTrans()
            print("pos ", i)
            print("Rotation= ", rot_trans[2], " degrees")
            print(
                "Reference image center found at ",
                rot_trans[0],
                " pixels and ",
                rot_trans[1],
                " pixels",
            )

    def _musst_oscil(self, e1, e2, esh1, esh2, trigger):
        delta = self.musst_sampling
        self.musst.set_variable("E1", int(e1))
        self.musst.set_variable("E2", int(e2))
        self.musst.set_variable("ESH1", int(esh1))
        self.musst.set_variable("ESH2", int(esh2))
        # MUSST buffer can have a max of 2Mb/4 = 500 000 Values
        # STORELIST contains TIMER SMPX SMPY RBY RBZ DET_RET
        # there is 8 values
        max_pts = 524288.0 / 9
        pts = abs(e1 - e2) / float(delta)
        n = max_pts / pts
        if n < 1.0:
            delta_slow = int((delta / n) // 1) + 1
        else:
            delta_slow = delta
        self.musst.set_variable("DE", int(delta))
        self.musst.set_variable("DE_SLOW", int(delta_slow))
        self.musst.set_variable("DETTRIG", int(trigger))
        self.musst.putget("#CH CH3 0")
        print(
            "\ne1=",
            e1,
            "e2=",
            e2,
            "esh1=",
            esh1,
            "esh2=",
            esh2,
            "delta=",
            delta,
            "delta_slow=",
            delta_slow,
            "trigger=",
            trigger,
        )
        self.musst.putget("#RUN OSCILLPX")

    def _musst_oscil_newMUSST(self, e1, e2, esh1, esh2, trigger):
        delta = self.musst_sampling
        self.musst.set_variable("E1", int(e1))
        self.musst.set_variable("E2", int(e2))
        self.musst.set_variable("ESH1", int(esh1))
        self.musst.set_variable("ESH2", int(esh2))
        # MUSST buffer can have a max of 2Mb/4 = 500 000 Values
        # STORELIST contains TIMER ROBY_ENC ROBZ_ENC DET_STATE IODATA
        # there is 6 values
        max_pts = 524288.0 / 6
        pts = abs(e1 - e2) / float(delta)
        n = max_pts / pts
        if n < 1.0:
            delta_slow = int((delta / n) // 1) + 1
        else:
            delta_slow = delta
        self.musst.set_variable("DE", int(delta))
        self.musst.set_variable("DE_SLOW", int(delta_slow))
        self.musst.set_variable("DETTRIG", int(trigger))
        self.musst.putget("#CH CH1 0 RUN")
        self.musst.putget("#BTRIG 0")
        self.musst.putget("#IO !IO12")
        print(
            "\ne1=",
            e1,
            "e2=",
            e2,
            "esh1=",
            esh1,
            "esh2=",
            esh2,
            "delta=",
            delta,
            "delta_slow=",
            delta_slow,
            "trigger=",
            trigger,
        )
        self.musst.putget("#RUN OSCILLPX")

    def _musst_prepare_newMUSST(
        self, e1, e2, esh1, esh2, pixel_detector_trigger_steps, exp_time
    ):
        self.musst.ABORT
        self.musst.CLEAR
        self.musst.putget("#HSIZE 0")
        self.musst.putget("#ESIZE 524288")
        self.musst.upload_file("oscillPX_newMUSST.mprg")
        self._musst_oscil_newMUSST(e1, e2, esh1, esh2, pixel_detector_trigger_steps)
        self.musst2.ABORT
        self.musst2.CLEAR
        self.musst2.putget("#HSIZE 0")
        self.musst2.putget("#ESIZE 524288")
        self.musst2.upload_file("mesh2_musst2.mprg")
        self.musst2.putget("#CH CH2 0 RUN")
        self.musst2.putget("#RUN MESH2_STILL")

    def _musst_prepare(
        self, e1, e2, esh1, esh2, pixel_detector_trigger_steps, exp_time
    ):
        self.musst.ABORT
        self.musst.CLEAR
        self.musst.putget("#HSIZE 0")
        self.musst.putget("#ESIZE 524288")
        self.musst.upload_file("oscillPX.mprg")
        self._musst_oscil(e1, e2, esh1, esh2, pixel_detector_trigger_steps)

        # DN try 2nd MUSST called musst2
        self.musst2.ABORT
        self.musst2.CLEAR
        self.musst2.putget("#HSIZE 0")
        self.musst2.putget("#ESIZE 524288")
        self.musst2.upload_file("oscillPX-musst2.mprg")
        # DN total exposure time * DTIME which is 1ms
        # MUSST buffer can have a max of 2Mb/4 = 500 000 Values
        # STORELIST contains TIMER SMPX SMPY RBY RBZ DET_RET
        # there is 6 values I put 7 to be safe
        div = int(exp_time * 1000 / (500000 / 7))
        self.musst2.set_variable("NPOINTS", int(int((exp_time * 1000) / (div + 1))))
        self.musst2.set_variable("DTIME", int(1000 * (div + 1)))
        self.musst2.putget("#RUN OSCILLPX2")

    def _helical_calc(self, helical_pos, exp_time):
        hp = copy.deepcopy(helical_pos)
        start = hp["1"]
        end = hp["2"]
        start_phiz = start["phiz"]
        start_phiy = start["phiy"]
        if start.get("y") is not None:
            # we prevent phiz from moving at all if request comes from mxcube
            # end["phiz"]=end["z"]
            # start["phiz"]=start["z"]
            end["phiz"] = 0
            start["phiz"] = 0
            end["phiy"] = end["y"]
            start["phiy"] = start["y"]
        else:
            self.acc_margin = 300
        logging.info("%r", hp)
        # phiz has to move if chi==90 for example, phiy has to move if chi==0
        helical = {
            "phiy": {
                "trajectory": end.get("phiy", 0) - start.get("phiy", 0),
                "motor": self.phiy,
                "start": start_phiy,
            },
            "phiz": {
                "trajectory": end.get("phiz", 0) - start.get("phiz", 0),
                "motor": self.phiz,
                "start": start_phiz,
            },
            "sampx": {
                "trajectory": end["sampx"] - start["sampx"],
                "motor": self.sampx,
                "start": start.get("sampx"),
            },
            "sampy": {
                "trajectory": end["sampy"] - start["sampy"],
                "motor": self.sampy,
                "start": start.get("sampy"),
            },
        }
        for motor_name in helical.keys():
            hm = helical[motor_name]
            hm["distance"] = abs(hm["trajectory"])
            if hm["distance"] <= 5E-3:
                del helical[motor_name]
                continue
            hm["backlash"] = helical[motor_name]["motor"].controller.backlash(
                hm["motor"].name, hm["start"], hm["start"] + hm["trajectory"]
            )
            hm["d"] = math.copysign(1, hm["trajectory"])
            steps = helical[motor_name]["distance"] * abs(hm["motor"].steps_per_unit)
            hm["velocity"] = steps / float(exp_time)
        return helical

    def helical_oscil(
        self,
        omega_start_ang,
        omega_stop_ang,
        helical_pos,
        exp_time,
        nb_pass=1,
        save_diagnostic=True,
        operate_shutter=True,
        nb_lines=1,
    ):
        def oscil_cleanup(
            phi_v=self.phi.config_velocity,
            phi_a=self.phi.config_acceleration,
            phiz_v=self.phiz.config_velocity,
            phiz_a=self.phiz.config_acceleration,
            phiy_v=self.phiy.config_velocity,
            phiy_a=self.phiy.config_acceleration,
            sampx_v=self.sampx.config_velocity,
            sampx_a=self.sampx.config_acceleration,
            sampy_v=self.sampy.config_velocity,
            sampy_a=self.sampy.config_acceleration,
        ):
            for motor_name in ("phi", "phiz", "phiy", "sampx", "sampy"):
                getattr(self, motor_name).velocity = locals()[motor_name + "_v"]
                getattr(self, motor_name).acceleration = locals()[motor_name + "_a"]
            self.acc_margin = self.config_acc_margin

        # print "#"*50, "apz=", self.apz.position
        while self.diode(True, False)[0] < 1e-08:  # and self.PSS_State():
            print("Waiting for beam to be back (i0)")
            time.sleep(10)

        while True:
            try:
                temperature = self.cryo.read()
            except AttributeError:
                raise
            except Exception:
                sys.excepthook(*sys.exc_info())
                gevent.sleep(0.5)
                continue
            else:
                if temperature > 140.0:
                    print("==" * 50)
                    print("Cryostreaming warming up")
                    print("==" * 50)
                    cell = self.dw.position
                    sample = self.get_sampleNumber("nSampleLoaded")
                    if sample <= 10:
                        puck = 1
                    elif sample > 10 and sample <= 20:
                        puck = 2
                        sample = sample - 10
                    elif sample > 20 and sample <= 30:
                        puck = 3
                        sample = sample - 20
                    else:
                        raise RuntimeError("Wrong puck number")
                    self.unload_sample(cell, puck, sample)
                    raise RuntimeError("Cryostreaming warming up")
                break

        if True:
            hp = copy.deepcopy(helical_pos)
            initial = hp["1"]
            initial_phiy = initial["phiy"]
            initial_phiz = initial["phiz"]
            final = hp["2"]
            final_phiy = final["phiy"]
            final_phiz = final["phiz"]
            dist_phiy = abs(initial_phiy - final_phiy)
            dist_phiz = abs(initial_phiz - final_phiz)
            expo = self.pilatus._proxy.acq_expo_time
            # nb_lines= 1 #Olof to say
            nb_images_per_line = self.pilatus._proxy.acq_nb_frames / nb_lines
            if dist_phiy < 0.05 and dist_phiz > 0.05:
                self.vert_mesh_still2(
                    initial_phiy,
                    final_phiy,
                    initial_phiz,
                    final_phiz,
                    nb_images_per_line,
                    expo,
                    nb_lines,
                )
            else:
                self.hor_mesh_still2(
                    initial_phiy,
                    final_phiy,
                    initial_phiz,
                    final_phiz,
                    nb_images_per_line,
                    expo,
                    nb_lines,
                )

    def _oscil_calc(self, start_ang, stop_ang, exp_time, nb_pass):
        abs_ang = math.fabs(stop_ang - start_ang)
        if stop_ang > start_ang:
            d = 1
        else:
            raise RuntimeError("cannot do reverse oscillation")
        osctime = float(exp_time) / int(nb_pass)
        velocity = float(abs_ang) / osctime
        # step_size = math.fabs(self.phi.steps_per_unit)
        step_size = math.fabs(self.phi.steps_per_unit)
        calc_velocity = velocity * step_size
        acc_time = self.phi.config_acctime
        acc_steps = (acc_time * calc_velocity) / 2
        acc_ang = acc_steps / float(step_size)
        max_ang = acc_ang
        oscil_start = start_ang - d * (max_ang + self.acc_margin / step_size)
        oscil_final = stop_ang + d * (max_ang + self.acc_margin / step_size)
        return d, oscil_start, oscil_final, velocity, calc_velocity, acc_time, acc_ang

    def oscil(
        self,
        start_ang,
        stop_ang,
        exp_time,
        nb_pass=1,
        save_diagnostic=True,
        operate_shutter=True,
        helical=False,
    ):
        while self.diode(True, False)[0] < 1e-08:  # and self.PSS_State():
            print("Waiting for beam to be back (i0)")
            time.sleep(10)
        while True:
            try:
                temperature = self.cryo.read()
            except AttributeError:
                raise
            except Exception:
                sys.excepthook(*sys.exc_info())
                gevent.sleep(0.5)
                continue
            else:
                if temperature > 140.0:
                    print("==" * 50)
                    print("Cryostreaming warming up")
                    print("==" * 50)
                    cell = self.dw.position
                    sample = self.get_sampleNumber("nSampleLoaded")
                    if sample <= 10:
                        puck = 1
                    elif sample > 10 and sample <= 20:
                        puck = 2
                        sample = sample - 10
                    elif sample > 20 and sample <= 30:
                        puck = 3
                        sample = sample - 20
                    else:
                        raise RuntimeError("Wrong puck number")
                    self.unload_sample(cell, puck, sample)
                    raise RuntimeError("Cryostreaming warming up")
                break
        d, oscil_start, oscil_final, velocity, calc_velocity, acc_time, acc_ang = self._oscil_calc(
            start_ang, stop_ang, exp_time, nb_pass
        )

        def oscil_cleanup(v=self.phi.config_velocity, a=self.phi.config_acceleration):
            self.phi.velocity = v
            self.phi.acceleration = a

        with cleanup(oscil_cleanup):
            self.fshut.close()
            self.phi.move(oscil_start)
            self.phi.velocity = velocity
            self.phi.acctime = acc_time
            encoder_step_size = self.phienc.steps_per_unit
            phi_encoder_pos = self.phienc.read() * encoder_step_size
            pixel_detector_trigger_steps = encoder_step_size * start_ang
            shutter_predelay_steps = math.fabs(
                float(self.shutter_predelay * velocity * encoder_step_size)
            )
            shutter_postdelay_steps = math.fabs(
                float(self.shutter_postdelay * velocity * encoder_step_size)
            )
            # max_step_ang = encoder_step_size * (acc_ang + self.acc_margin * velocity / self.phi.steps_per_unit)
            # DN Wrong way of using margin should be calculated according to delay of the shutter and omega speed
            # TO BE DONE
            max_step_ang = encoder_step_size * acc_ang + self.acc_margin
            e1 = start_ang * encoder_step_size - d * (max_step_ang) + 5
            e2 = stop_ang * encoder_step_size + d * (max_step_ang) - 5
            esh1 = start_ang * encoder_step_size - d * shutter_predelay_steps
            esh2 = stop_ang * encoder_step_size - d * shutter_postdelay_steps
            if operate_shutter:
                # DN NEW MUSST
                self._musst_prepare_newMUSST(
                    e1, e2, esh1, esh2, pixel_detector_trigger_steps, exp_time
                )
            self.phi.move(oscil_final)
            if save_diagnostic:
                # DN NEW MUSST
                self.save_musst_diags_newMUSST(wait=False)

    def _get_diagnostic(self, phi_encoder_pos):
        npoints = int(self.musst.get_variable("NPOINTS"))
        nlines = npoints  # variable name should be changed in musst program
        diag_data = numpy.zeros((nlines, 8), dtype=numpy.float)
        data = self.musst.get_data(8)
        # first column contains time in microseconds,
        # convert it to milliseconds
        diag_data[:, 0] = data[:, 0] / 1000.0
        # velocity in
        #     v(i) = [ x(i) - x(i-1) ] /  [ t(i) - t(i-1) ]
        # then convert from steps/microsec into deg/sec
        step_size = math.fabs(self.phienc.steps_per_unit)
        diag_data[1:, 1] = [
            xi - prev_xi for xi, prev_xi in zip(data[:, 2][1:], data[:, 2])
        ]
        diag_data[1:, 1] /= [
            float(ti - prev_ti) for ti, prev_ti in zip(data[:, 0][1:], data[:, 0])
        ]
        diag_data[:, 1] *= 1E6 / float(step_size)
        diag_data[0, 1] = diag_data[1, 1]
        # save pos in degrees
        diag_data[:, 2] = data[:, 2] / float(step_size)
        # I0 values
        diag_data[:, 3] = 10 * (data[:, 5] / float(0x7FFFFFFF))
        # diag_data[:,3]=-data[:,5]/20000.0
        # I1 values
        # diag_data[:,4]=10*(data[:,5]/float(0x7FFFFFFF))
        diag_data[:, 4] = 10 * (data[:, 6] / float(0x7FFFFFFF))
        # shutter cmd (Btrig)
        diag_data[:, 5] = data[:, 7]
        # shutter status
        diag_data[:, 6] = data[:, 1]  # & 0x0001)/0x0001
        # detector status
        diag_data[:, 7] = data[:, 3]
        # save SAMP step 5
        # diag_data[:,8]=-data[:,6]/20000.0
        return diag_data

    def _get_diagnostic_newMUSST(self, phi_encoder_pos):
        self.musst2.ABORT
        npoints = int(self.musst.get_variable("NPOINTS"))
        nlines = npoints  # variable name should be changed in musst program
        diag_data = numpy.zeros((nlines, 7), dtype=numpy.float)
        data = self.musst.get_data(6)
        # save TIME
        diag_data[:, 0] = data[:, 0]
        # Save PHI velocity in
        #     v(i) = [ x(i) - x(i-1) ] /  [ t(i) - t(i-1) ]
        # then convert from steps/microsec into deg/sec
        step_size = math.fabs(self.phienc.steps_per_unit)
        diag_data[1:, 1] = [
            xi - prev_xi for xi, prev_xi in zip(data[:, 2][1:], data[:, 2])
        ]
        diag_data[1:, 1] /= [
            float(ti - prev_ti) for ti, prev_ti in zip(data[:, 0][1:], data[:, 0])
        ]
        diag_data[:, 1] *= 1E6 / float(step_size)
        diag_data[0, 1] = diag_data[1, 1]
        # save PHI pos in degrees
        diag_data[:, 2] = data[:, 2] / float(step_size)
        # PHIY values
        step_size = math.fabs(self.phiyenc.steps_per_unit)
        diag_data[:, 3] = data[:, 3] / float(step_size)
        # PHIZ values
        step_size = math.fabs(self.phizenc.steps_per_unit)
        diag_data[:, 4] = data[:, 4] / float(step_size)
        # shutter cmd (Btrig)
        diag_data[:, 5] = data[:, 5]
        # Det State
        diag_data[:, 6] = data[:, 1]
        return diag_data

    def _get_diagnostic2(self):
        npoints = int(self.musst2.get_variable("NPOINTS"))
        nlines = npoints  # variable name should be changed in musst program
        diag_data = numpy.zeros((nlines, 6), dtype=numpy.float)
        data = self.musst2.get_data(6)
        # first column contains time in microseconds,
        # convert it to milliseconds
        diag_data[:, 0] = data[:, 0] / 1000.0
        # save sampx pos in mm
        diag_data[:, 1] = data[:, 1] / self.sampx.steps_per_unit
        # save sampy pos in mm
        diag_data[:, 2] = data[:, 2] / self.sampy.steps_per_unit
        # save phiy pos in mm
        diag_data[:, 3] = data[:, 3] / self.phiyenc.steps_per_unit
        # save phiz pos in mm
        diag_data[:, 4] = data[:, 4] / self.phiz.enc.steps_per_unit
        # save detector state
        diag_data[:, 5] = data[:, 5]
        return diag_data

    def _get_diagnostic2_newMUSST(self):
        self.musst2.ABORT
        npoints = int(self.musst2.get_variable("NPOINTS"))
        nlines = npoints  # variable name should be changed in musst program
        diag_data = numpy.zeros((nlines, 5), dtype=numpy.float)
        data = self.musst2.get_data(5)
        # first column contains time in microseconds,
        # convert it to milliseconds
        diag_data[:, 0] = data[:, 0]
        diag_data[:, 1:5] = data[:, 1:5]
        return diag_data

    def merge_diag(self, enc_pos=0):
        diag_musst1 = self._get_diagnostic(enc_pos)
        diag_musst2 = self._get_diagnostic2()
        self.diag_n += 1
        rows_musst1, cols_musst1 = diag_musst1.shape
        rows_musst2, cols_musst2 = diag_musst2.shape
        # search in musst1 column 7 (det status)
        det_status = diag_musst1[0, 7]
        line = 0
        for i in diag_musst1[:, 7]:
            if i == det_status + 1:
                start_line = line
                break
            line += 1
        start_time = diag_musst1[start_line, 0]
        diag_musst2[:, 0] += start_time
        rows, cols = diag_musst2.shape
        with open(self.diagfile, "a+") as diagfile:
            diagfile.write(
                "\n#S %d\n#D %s\n"
                % (
                    self.diag_n,
                    datetime.datetime.now().strftime("%a %b %d %H:%M:%S %Y"),
                )
            )
            diagfile.write("#N %d\n" % cols)
            diagfile.write(
                "#L Time(ms)  SampX  SampY  PhiY  PhiZ  Detector Acquiring\n"
            )
            numpy.savetxt(diagfile, diag_musst2)
            diagfile.write("\n\n")

    @task
    def save_diagnostic_newMUSST(self, phi_encoder_pos=0):
        diag_data = self._get_diagnostic_newMUSST(phi_encoder_pos)
        self.diag_n += 1
        rows, cols = diag_data.shape
        self.user_name = self.diagfile.split("/")[3]
        if self.user_name == "inhouse":
            self.user_name = self.diagfile.split("/")[4]
        with open(self.diagfile, "a+") as diagfile:
            diagfile.write(
                "\n#S %d\n#D %s\n"
                % (
                    self.diag_n,
                    datetime.datetime.now().strftime("%a %b %d %H:%M:%S %Y"),
                )
            )
            diagfile.write("#N %d\n" % cols)
            diagfile.write("#L Time(us)  Phi vel  Phi  PhiY  PhiZ  Sh Cmd  Det State\n")
            numpy.savetxt(diagfile, diag_data)
            diagfile.write("\n\n")

    @task
    def save_diagnostic(self, phi_encoder_pos=0):
        diag_data = self._get_diagnostic(phi_encoder_pos)
        self.diag_n += 1
        rows, cols = diag_data.shape
        self.user_name = self.diagfile.split("/")[3]
        if self.user_name == "inhouse":
            self.user_name = self.diagfile.split("/")[4]
        with open(self.diagfile, "a+") as diagfile:
            diagfile.write(
                "\n#S %d\n#D %s\n"
                % (
                    self.diag_n,
                    datetime.datetime.now().strftime("%a %b %d %H:%M:%S %Y"),
                )
            )
            diagfile.write("#N %d\n" % cols)
            diagfile.write(
                "#L Time(ms)  Speed  Phi  I0  I1  Shut Cmd  Shut State  Detector Acquiring\n"
            )
            numpy.savetxt(diagfile, diag_data)
            diagfile.write("\n\n")

    @task
    def save_diagnostic2_newMUSST(self):
        diag_data = self._get_diagnostic2_newMUSST()
        self.diag_n += 1
        rows, cols = diag_data.shape
        with open(self.diagfile, "a+") as diagfile:
            diagfile.write(
                "\n#S %d\n#D %s\n"
                % (
                    self.diag_n,
                    datetime.datetime.now().strftime("%a %b %d %H:%M:%S %Y"),
                )
            )
            diagfile.write("#N %d\n" % cols)
            diagfile.write("#L Time(us)  SH State  Det STATE  I0 Diode  I1 Diode\n")
            numpy.savetxt(diagfile, diag_data)
            diagfile.write("\n\n")

    @task
    def save_diagnostic2(self):
        diag_data = self._get_diagnostic2()
        self.diag_n += 1
        rows, cols = diag_data.shape
        with open(self.diagfile, "a+") as diagfile:
            diagfile.write(
                "\n#S %d\n#D %s\n"
                % (
                    self.diag_n,
                    datetime.datetime.now().strftime("%a %b %d %H:%M:%S %Y"),
                )
            )
            diagfile.write("#N %d\n" % cols)
            diagfile.write(
                "#L Time(ms)  SampX  SampY  PhiY  PhiZ  Detector Acquiring\n"
            )
            numpy.savetxt(diagfile, diag_data)
            diagfile.write("\n\n")

    @task
    def save_musst_diags_newMUSST(self):
        self.save_diagnostic_newMUSST(wait=True)

    @task
    def save_musst_diags(self):
        t0 = time.time()
        print("!" * 50, "diag on musst 2")
        self.save_diagnostic2(wait=True)
        print(time.time() - t0)
        t0 = time.time()
        print("!" * 50, "diag on musst 1")
        self.save_diagnostic(wait=True)
        print(time.time() - t0)

    def mesh_diagnostic1(self, scan_nb, nb_images_per_line):
        data = self.musst.get_data(6)
        nlines = len(data)
        diag_data = numpy.zeros((nlines, 7), dtype=numpy.float)
        # save TIME
        diag_data[:, 0] = data[:, 0]
        # Save PHI velocity in
        #     v(i) = [ x(i) - x(i-1) ] /  [ t(i) - t(i-1) ]
        # then convert from steps/microsec into deg/sec
        step_size = math.fabs(self.phienc.steps_per_unit)
        diag_data[1:, 1] = [
            xi - prev_xi for xi, prev_xi in zip(data[:, 2][1:], data[:, 2])
        ]
        diag_data[1:, 1] /= [
            float(ti - prev_ti) for ti, prev_ti in zip(data[:, 0][1:], data[:, 0])
        ]
        diag_data[:, 1] *= 1E6 / float(step_size)
        diag_data[0, 1] = diag_data[1, 1]
        # save PHI pos in degrees
        diag_data[:, 2] = data[:, 2] / float(step_size)
        # PHIY values
        step_size = math.fabs(self.phiyenc.steps_per_unit)
        diag_data[:, 3] = data[:, 3] / float(step_size)
        # PHIZ values
        step_size = math.fabs(self.phizenc.steps_per_unit)
        diag_data[:, 4] = data[:, 4] / float(step_size)
        # shutter cmd (Btrig)
        diag_data[:, 5] = data[:, 5]
        # Det State
        diag_data[:, 6] = data[:, 1]
        rows, cols = diag_data.shape
        with open(self.diagfile, "a+") as diagfile:
            if scan_nb == 1:
                diagfile.write(
                    "\n#S %d\n#D %s\n"
                    % (
                        self.diag_n,
                        datetime.datetime.now().strftime("%a %b %d %H:%M:%S %Y"),
                    )
                )
                diagfile.write("#N %d\n" % cols)
                diagfile.write(
                    "#L Time(us)  Phi vel  Phi  PhiY  PhiZ  Sh Cmd  Det State\n"
                )
            numpy.savetxt(diagfile, diag_data)
            if scan_nb == 1:
                diagfile.write("\n\n")

    def mesh_diagnostic2(self, scan_nb):
        data = self.musst2.get_data(6)
        nlines = len(data)
        diag_data = numpy.zeros((nlines, 5), dtype=numpy.float)
        # first column contains time in microseconds,
        # convert it to milliseconds
        diag_data[:, 0] = data[:, 0]
        diag_data[:, 1:5] = data[:, 1:5]
        rows, cols = diag_data.shape
        with open(self.diagfile, "a+") as diagfile:
            if scan_nb == 1:
                diagfile.write(
                    "\n#S %d\n#D %s\n"
                    % (
                        self.diag_n,
                        datetime.datetime.now().strftime("%a %b %d %H:%M:%S %Y"),
                    )
                )
                diagfile.write("#N %d\n" % cols)
                diagfile.write("#L Time(us)  SH State  Det STATE  I0 Diode  I1 Diode\n")
            numpy.savetxt(diagfile, diag_data)
            if scan_nb == 1:
                diagfile.write("\n\n")

    def musst_mesh(
        self,
        e1,
        e2,
        esh1,
        esh2,
        edet,
        exp_time,
        nb_images_per_line,
        nb_lines,
        direction,
    ):
        time.sleep(2)
        self.musst.ABORT
        self.musst.CLEAR
        self.musst.putget("#HSIZE 0")
        self.musst.putget("#ESIZE 524288")
        self.musst.upload_file("mesh_musst1.mprg")
        self.musst.set_variable("E1", int(e1))
        self.musst.set_variable("E2", int(e2))
        self.musst.set_variable("ESH1", int(esh1))
        self.musst.set_variable("ESH2", int(esh2))
        self.musst.set_variable("EDET", int(edet))
        self.musst.set_variable("EXPO", int(exp_time * 1e+6))
        self.musst.set_variable("READOUT", (self.pilatus_deadtime * 1e+6))
        self.musst.set_variable("NB_IMG_PER_LINES", int(nb_images_per_line))
        self.musst.set_variable("NB_LINES", int(nb_lines))
        self.musst.putget("#RUN MESH_STILL")

    def musst1_mesh2(
        self, e1, e2, esh1, esh2, edet, delta, exp_time, nb_images_per_line, direction
    ):
        self.musst.ABORT
        self.musst.CLEAR
        self.musst.putget("#HSIZE 0")
        self.musst.putget("#ESIZE 524288")
        if direction == "hor":
            self.musst.upload_file("hor_mesh2_musst1.mprg")
        elif direction == "vert":
            self.musst.upload_file("vert_mesh2_musst1.mprg")
        else:
            return "No or wrong direction"
        self.musst.set_variable("E1", int(e1))
        self.musst.set_variable("E2", int(e2))
        self.musst.set_variable("ESH1", int(esh1))
        self.musst.set_variable("ESH2", int(esh2))
        self.musst.set_variable("EDET", int(edet))
        self.musst.set_variable("DE", int(delta * 1e+6))
        self.musst.set_variable("EXPO", int(exp_time * 1e+6))
        self.musst.set_variable("READOUT", int(self.pilatus_deadtime * 1e+6))
        self.musst.set_variable("NB_IMG_PER_LINES", int(nb_images_per_line))
        self.musst.putget("#RUN MESH2_STILL")

    def musst2_mesh2(self, delta, nb_images_per_line):
        self.musst2.ABORT
        self.musst2.CLEAR
        self.musst2.putget("#HSIZE 0")
        self.musst2.putget("#ESIZE 524288")
        self.musst2.upload_file("mesh2_musst2.mprg")
        self.musst2.set_variable("DE", int(delta * 1e+6))
        self.musst2.set_variable("NB_IMG_PER_LINES", int(nb_images_per_line))
        self.musst2.putget("#RUN MESH2_STILL")

    def hor_mesh_calc(self, phiy_start, phiy_initial, phiy_final, phiy_end, phiy_vel):
        phiy_enc_step_size = abs(self.phiyenc.steps_per_unit)
        e1 = phiy_start * phiy_enc_step_size
        e2 = phiy_end * phiy_enc_step_size
        esh1 = (phiy_initial - self.shutter_predelay * phiy_vel) * phiy_enc_step_size
        esh2 = (phiy_final - self.shutter_postdelay * phiy_vel) * phiy_enc_step_size
        edet = phiy_initial * phiy_enc_step_size
        return e1, e2, esh1, esh2, edet

    def vert_mesh_calc(self, phiz_start, phiz_initial, phiz_final, phiz_end, phiz_vel):
        phiz_enc_step_size = abs(self.phizenc.steps_per_unit)
        e1 = phiz_start * phiz_enc_step_size
        e2 = phiz_end * phiz_enc_step_size
        esh1 = (phiz_initial - self.shutter_predelay * phiz_vel) * phiz_enc_step_size
        esh2 = (phiz_final - self.shutter_postdelay * phiz_vel) * phiz_enc_step_size
        edet = phiz_initial * phiz_enc_step_size
        return e1, e2, esh1, esh2, edet

    def powder_mesh(self):
        self.phiz.move(0)
        for j in numpy.arange(-.075, .125, .050):
            self.phiy.move(j)
            self.phi.move(0)
            for i in numpy.arange(0, 183.6, 3.6):
                self.phi.move(i)
                name = "phi" + str(i) + "_" + str(j * 1000) + "_"
                self.vert_mesh_still2(
                    j,
                    j,
                    -0.3,
                    0.3,
                    60,
                    0.1,
                    1,
                    "/lbsram/data/id30a1/inhouse/opid30a1/didier/69-3b",
                    name,
                )

    def vert_mesh_still2(
        self,
        phiy_initial=-0.5,
        phiy_final=0.5,
        phiz_initial=-0.05,
        phiz_final=0.05,
        nb_images_per_line=33,
        expo=0.0333,
        nb_lines=1,
        dir_name="/lbsram/didier",
        prefix="test",
    ):
        self.musst.ABORT
        self.musst2.ABORT
        phiz_step_size = self.phiz.steps_per_unit
        phiz_vel = abs(
            (phiz_final - phiz_initial)
            / (nb_images_per_line * (expo + self.pilatus_deadtime))
        )
        # phiz_acc_dist = (self.phiz.config_acceleration * phiz_vel) / 2
        phiz_acc_dist = (self.phiz.config_acctime * phiz_vel) / 2
        delta = expo / 10.
        phiz_start = phiz_initial - (phiz_acc_dist + self.acc_margin / phiz_step_size)
        phiz_end = phiz_final + (phiz_acc_dist + self.acc_margin / phiz_step_size)
        i = 0
        for phiy_pos in numpy.linspace(phiy_initial, phiy_final, nb_lines):
            i += 1
            self.phiz.velocity = self.phiz.config_velocity
            self.phiz.move(phiz_start)
            self.phiy.move(phiy_pos)
            self.musst.putget("#CH CH1 0 RUN")
            self.musst2.putget("#CH CH2 0 RUN")
            self.musst.putget("#BTRIG 0")
            if self.acc_margin < (self.shutter_predelay * phiz_vel * phiz_step_size):
                return "acc_margin too short"
            e1, e2, esh1, esh2, edet = self.vert_mesh_calc(
                phiz_start, phiz_initial, phiz_final, phiz_end, phiz_vel
            )
            print(e1, e2, esh1, esh2, edet, delta)
            self.musst1_mesh2(
                e1, e2, esh1, esh2, edet, delta, expo, nb_images_per_line, "vert"
            )
            self.musst2_mesh2(delta, nb_images_per_line)
            self.phiz.velocity = phiz_vel  # * phiz_step_size)
            self.phiz.move(phiz_end)
            time.sleep(1)
            while self.musst.STATE != self.musst.IDLE_STATE:
                time.sleep(0.1)
            self.musst2.ABORT
            t0 = time.time()
            self.mesh_diagnostic1(1, nb_images_per_line)
            print("saving diag: ", time.time() - t0, " s")
            self.phiz.velocity = self.phiz.config_velocity
        return "Done"

    def hor_mesh_still2(
        self,
        phiy_initial=-0.05,
        phiy_final=0.05,
        phiz_initial=-0.5,
        phiz_final=0.5,
        nb_images_per_line=33,
        expo=0.0333,
        nb_lines=3,
        dir_name="/lbsram/didier",
        prefix="test",
    ):
        self.musst.ABORT
        self.musst2.ABORT
        phiy_step_size = self.phiy.steps_per_unit
        if phiy_step_size < 0:
            d = -1
        else:
            d = 1
        phiy_step_size = abs(phiy_step_size)
        phiy_vel = abs(
            (phiy_final - phiy_initial)
            / (nb_images_per_line * (expo + self.pilatus_deadtime))
        )
        # phiy_acc_dist = (self.phiy.config_acceleration * phiy_vel) / 2
        phiy_acc_dist = (self.phiy.config_acctime * phiy_vel) / 2
        phiy_start = phiy_initial + d * (
            phiy_acc_dist + self.acc_margin / phiy_step_size
        )
        phiy_end = phiy_final - d * (phiy_acc_dist + self.acc_margin / phiy_step_size)
        delta = expo / 10
        i = 0
        for phiz_pos in numpy.linspace(phiz_initial, phiz_final, nb_lines):
            i += 1
            self.phiy.velocity = self.phiy.config_velocity
            self.phiy.move(phiy_start)
            self.phiz.move(phiz_pos)
            self.musst.putget("#CH CH1 0 RUN")
            self.musst2.putget("#CH CH2 0 RUN")
            self.musst.putget("#BTRIG 0")
            if self.acc_margin < (self.shutter_predelay * phiy_vel * phiy_step_size):
                return "acc_margin too short"
            e1, e2, esh1, esh2, edet = self.hor_mesh_calc(
                phiy_start, phiy_initial, phiy_final, phiy_end, phiy_vel
            )
            print(e1, e2, esh1, esh2, edet, delta)
            self.musst1_mesh2(
                e1, e2, esh1, esh2, edet, delta, expo, nb_images_per_line, "hor"
            )
            self.musst2_mesh2(delta, nb_images_per_line)
            self.phiy.velocity = phiy_vel  # * phiy_step_size)
            self.phiy.move(phiy_end)
            while self.musst.STATE != self.musst.IDLE_STATE:
                time.sleep(0.1)
            self.musst2.ABORT
            t0 = time.time()
            self.mesh_diagnostic1(1, nb_images_per_line)
            print("saving diag: ", time.time() - t0, " s")
            self.phiy.velocity = self.phiy.config_velocity
        return "Done"

    def mesh_still(
        self,
        phiy_initial=-0.05,
        phiy_final=0.05,
        phiz_initial=-0.5,
        phiz_final=0.5,
        nb_images_per_line=33,
        expo=0.0333,
        nb_lines=3,
        dir_name="/lbsram/didier",
        prefix="test",
    ):
        self.ltrack_disable()
        self.pilatus._proxy.stopAcq()
        self.pilatus._proxy.stopAcq()
        self.musst.ABORT
        self.musst.putget("#IO !IO12")
        self.musst.putget("#CH CH1 0")
        phiy_step_size = abs(self.phiy.steps_per_unit)
        if self.phiy.steps_per_unit < 0:
            d = -1
        phiy_vel = abs(
            (phiy_final - phiy_initial)
            / (nb_images_per_line * (expo + self.pilatus_deadtime))
        )
        # phiy_acc_dist = (self.phiy.config_acceleration * phiy_vel) / 2
        phiy_acc_dist = (self.phiy.config_acctime * phiy_vel) / 2
        phiy_start = phiy_initial + d * (
            phiy_acc_dist + self.acc_margin / phiy_step_size
        )
        self.phiy.move(phiy_start)
        self.phiy.velocity = phiy_vel  # * phiy_step_size)
        phiy_end = phiy_start + (
            2 * (phiy_acc_dist + self.acc_margin / phiy_step_size)
            + (phiy_final - phiy_initial)
        )
        if (d * phiy_start * phiy_step_size) < (d * phiy_end * phiy_step_size):
            self.musst.putget("#IO !IO8")
            self.phiy.controller._icepap_comm("#%d:POS INPOS 0", self.phiy.name)
            self.phiy.controller._icepap_comm(
                "#%%d:LISTDAT %d %d 2"
                % (d * phiy_start * phiy_step_size, d * phiy_end * phiy_step_size),
                self.phiy.name,
            )
            self.phiy.controller._icepap_comm("#%d:LTRACK INPOS", self.phiy.name)
        elif (d * phiy_start * phiy_step_size) > (d * phiy_end * phiy_step_size):
            self.musst.putget("#IO IO8")
            self.phiy.controller._icepap_comm("#%d:POS INPOS 1", self.phiy.name)
            self.phiy.controller._icepap_comm(
                "#%%d:LISTDAT %d %d 2"
                % (d * phiy_end * phiy_step_size, d * phiy_start * phiy_step_size),
                self.phiy.name,
            )
            self.phiy.controller._icepap_comm("#%d:LTRACK INPOS", self.phiy.name)
        else:
            return "Error in mesh scan"
        phiz_step_size = abs(self.phiz.step_per_unit)
        if self.phiz.step_per_unit < 0:
            d = -1
        self.phiz.move(phiz_initial)
        self.musst.putget("#IO !IO9")
        self.phiz.controller._icepap_comm("#%d:POS INPOS 0", self.phiz.name)
        self.phiz.controller._icepap_comm(
            "#%%d:LISTDAT %d %d %d"
            % (
                d * phiz_initial * phiz_step_size,
                d * phiz_final * phiz_step_size,
                nb_lines + 1,
            ),
            self.phiz.name,
        )
        self.phiz.controller._icepap_comm("#%d:LTRACK INPOS", self.phiz.name)
        raise RuntimeError("Need work on Pilatus")
        # self.pilatus.set_detector_filenames(prefix, dir_name)
        # self.pilatus.prepare_acquisition(nb_images_per_line * nb_lines, expo)
        # self.pilatus.detector.start_acquisition()
        if self.acc_margin < (self.shutter_predelay * phiy_vel * phiy_step_size):
            return "acc_margin too short"
        e1, e2, esh1, esh2, edet = self.mesh_calc(
            phiy_start, phiy_initial, phiy_final, phiy_end, phiy_vel
        )
        print(e1, e2, esh1, esh2, edet)
        self.musst_mesh(e1, e2, esh1, esh2, edet, expo, nb_images_per_line, nb_lines)
        while self.musst.STATE != self.musst.IDLE_STATE:
            time.sleep(0.1)
        return "Done"

    def lightout(self, wait=True):
        self.wcid30m.set("lightin", 0)
        if wait:
            while self.wcid30m.get("light_is_out") == False:
                time.sleep(0.1)

    def lightin(self, wait=True):
        self.wcid30m.set("lightin", 1)
        if wait:
            while self.wcid30m.get("light_is_in") == False:
                time.sleep(0.1)

    def _get_diagnostic_SRX(self):
        npoints = int(self.musst.get_variable("NPOINTS"))
        nlines = npoints  # variable name should be changed in musst program
        diag_data = numpy.zeros((nlines, 6), dtype=numpy.float)
        data = self.musst.get_data(7)
        # first column contains time in microseconds,
        # convert it to milliseconds
        diag_data[:, 0] = data[:, 0] / 1000.0
        # save shutter state
        diag_data[:, 1] = data[:, 1]
        # save det_ret
        diag_data[:, 2] = data[:, 2]
        # save I0
        diag_data[:, 3] = 10 * data[:, 4] / float(0x7FFFFFFF)
        # save I1
        diag_data[:, 4] = 10 * data[:, 5] / float(0x7FFFFFFF)
        # save USERVAL which is SHUTTER_CMD and DET_CMD
        diag_data[:, 5] = data[:, 6]
        return diag_data

    @task
    def save_diagnostic_SRX(self, diagfile):
        diag_data = self._get_diagnostic_SRX()
        self.diag_n += 1
        rows, cols = diag_data.shape
        with open(diagfile, "a+") as diagfile:
            diagfile.write(
                "\n#S %d\n#D %s\n"
                % (
                    self.diag_n,
                    datetime.datetime.now().strftime("%a %b %d %H:%M:%S %Y"),
                )
            )
            diagfile.write("#N %d\n" % cols)
            diagfile.write(
                "#L Time(ms)  Shutter State  Det Acq.  I0  I1  Shutter/Det. Cmd\n"
            )
            numpy.savetxt(diagfile, diag_data)
            diagfile.write("\n\n")

    def _musst_SRX_prepare(self, exp_time, delay_in_sec=0.5):
        self.musst.ABORT
        self.musst.upload_file("SRX_PX.mprg")

        # DN total exposure time * DTIME which is 1ms
        # MUSST buffer can have a max of 2Mb/4 = 500 000 Values
        # STORELIST contains TIMER I0_IN I1_IN USERVAL SHUTTER_STATE DET_RET SPARE
        # there is 6 values I put 7 to be safe
        tot_time = delay_in_sec + self.shutter_predelay + exp_time + delay_in_sec
        div = int(tot_time * 1000 / (500000 / 7))
        if div != 0:
            raise RuntimeError("exposure too long MUSST prog could fail")
        self.musst.ABORT
        self.musst.set_variable("TOTALTIME", int(tot_time * 1e+6))
        self.musst.set_variable("DTIME", int((div + 1.0) * 1e+3))
        self.musst.set_variable("TSH1", int(self.shutter_predelay * 1e+6))
        self.musst.set_variable("EXPTIME", int(exp_time * 1e+6))
        self.musst.set_variable("TSH2", int(self.shutter_postdelay * 1e+6))
        self.musst.set_variable("DELAY", int(delay_in_sec * 1e+6))

    def SRX_prepare(self):
        self._simultaneous_move(
            self.phiy, self.phiy.low_limit, self.phiz, self.phiz.low_limit
        )
        print("Now ready to align the starting point using the Robot")

    def SRX_prepare_acq(self, aperture):
        xml = xmlrpclib.Server("http://capek:7171")
        xml.set_aperture(aperture)
        self.wcid30m.set("lightin", 0)
        while self.wcid30m.get("light_is_in") != False:
            time.sleep(0.1)
        self.detcover.set_out()
        self.tg_bsh = DeviceProxy("ID30/bsh/5")
        self.tg_bsh.open()

    def SRX_DC(
        self,
        aperture="10 um",
        length_in_mm=2.4,
        height_in_mm=2.4,
        space_in_um=40.0,
        dir_name="/lbsram/data/visitor/mx1676/id30a1/20150728/cellB",
        img_name="SRX",
        nb_images=150,
        exp_time=0.02,
    ):
        diag_task = None
        n_height = 1
        tot_exp_time = nb_images * (exp_time + self.pilatus_dead_time)
        self._musst_SRX_prepare(tot_exp_time, 0.5)
        diag_task = None
        self.SRX_prepare_acq(aperture)
        # create dir on lbsram
        subprocess.Popen(
            "ssh %s@pilatus301 mkdir --parents %s" % (os.environ["USER"], dir_name),
            shell=True,
            stdin=None,
            stdout=None,
            stderr=None,
        ).wait
        # create directory on Nice
        os.system("mkdir --parents %s" % (dir_name[7:]))
        if length_in_mm > abs(
            self.phiy.low_limit - self.phiy.high_limit
        ) or height_in_mm > abs(self.phiy.low_limit - self.phiy.high_limit):
            raise RuntimeError("need to implement this option")
        array_height = numpy.arange(
            self.phiz.low_limit,
            self.phiz.low_limit + height_in_mm,
            space_in_um / 1000.0,
        )
        array_length = numpy.arange(
            self.phiy.low_limit,
            self.phiy.low_limit + length_in_mm,
            space_in_um / 1000.0,
        )
        for i in array_height:
            # create dir on lbsram
            subprocess.Popen(
                "ssh %s@pilatus301 mkdir --parents %s"
                % (os.environ["USER"], dir_name + "/" + str(n_height)),
                shell=True,
                stdin=None,
                stdout=None,
                stderr=None,
            ).wait
            # create directory on Nice
            os.system("mkdir --parents %s" % (dir_name[7:] + "/" + str(n_height)))
            n_line = 1
            self.phiz.move(i)
            for j in array_length:
                self.phiy.move(j)
                t0 = time.time()
                prefix = img_name + "_" + str(n_line) + "_"
                acq_status_chan = self.pilatus.detector.getChannelObject("acq_status")
                while acq_status_chan.getValue() != "Ready":
                    acq_status_chan = self.pilatus.detector.getChannelObject(
                        "acq_status"
                    )
                    print("error: ", acq_status_chan.getValue())
                    time.sleep(0.02)
                    if time.time() - t0 > 0.5:
                        subprocess.Popen(
                            "ssh opid30@pilatus301 df",
                            shell=True,
                            stdin=None,
                            stdout=None,
                            stderr=None,
                        )
                        return "Time error"
                print(self.pilatus.detector.getChannelObject("acq_status").getValue())
                self.pilatus.set_detector_filenames(
                    prefix, dir_name + "/" + str(n_height)
                )
                self.pilatus.prepare_acquisition(nb_images, exp_time)
                self.pilatus.detector.start_acquisition()
                if diag_task is not None:
                    diag_task.get()
                t0 = time.time()
                self.musst.putget("#RUN SRX_PX")
                time.sleep(1)
                while self.musst.STATE != self.musst.IDLE_STATE:
                    time.sleep(0.05)
                print("musst run ", time.time() - t0)
                diagfile = dir_name[7:] + "/" + str(n_height) + "/" + "diag_SRX.dat"
                diag_task = self.save_diagnostic_SRX(diagfile, wait=False)
                n_line += 1
            n_height += 1
        self.tg_bsh.close()
        return "Done"

    def detector_test(
        self,
        dir_name="/lbsram/data/visitor/mx1583/id30a1/20150223/test2",
        img_name="SRX",
        nb_images=200,
        exp_time=0.010,
    ):
        # create dir on lbsram
        subprocess.Popen(
            "ssh %s@pilatus301 mkdir --parents %s" % (os.environ["USER"], dir_name),
            shell=True,
            stdin=None,
            stdout=None,
            stderr=None,
        ).wait
        # create directory on Nice
        os.system("mkdir --parents %s" % (dir_name[7:]))
        for i in range(1, 125):
            # create dir on lbsram
            subprocess.Popen(
                "ssh %s@pilatus301 mkdir --parents %s"
                % (os.environ["USER"], dir_name + "/" + str(i)),
                shell=True,
                stdin=None,
                stdout=None,
                stderr=None,
            ).wait
            # create directory on Nice
            os.system("mkdir --parents %s" % (dir_name[7:] + "/" + str(i)))

            for j in range(1, 125):
                prefix = img_name + "_" + str(j) + "_"
                t0 = time.time()
                acq_status_chan = self.pilatus.detector.getChannelObject("acq_status")
                while acq_status_chan.getValue() != "Ready":
                    acq_status_chan = self.pilatus.detector.getChannelObject(
                        "acq_status"
                    )
                    print("error: ", acq_status_chan.getValue())
                    time.sleep(0.05)
                    print(prefix)
                    if time.time() - t0 > 1.0:
                        subprocess.Popen(
                            "df", shell=True, stdin=None, stdout=None, stderr=None
                        )
                        return "Time error"
                self.pilatus.set_detector_filenames(prefix, dir_name + "/" + str(i))
                self.pilatus.detector.getChannelObject("acq_trigger_mode").setValue(
                    "EXTERNAL_TRIGGER"
                )
                self.pilatus.prepare_acquisition(nb_images, exp_time)
                self.pilatus.detector.start_acquisition()
                time.sleep(4)
        return "Done"

    def mailto(self):
        fp = open(textfile, "rb")
        msg = MIMEText(fp.read())
        fp.close()
        msg["Subject"] = "The contents of %s" % textfile
        msg["From"] = "opid30@esrf.fr"
        msg["To"] = "nurizzo@esrf.fr"
        s = smtplib.SMTP("localhost")
        s.sendmail(me, [you], msg.as_string())
        s.quit()

    def dw_test(self):
        for i in range(0, 100):
            print(i)
            self.dw.move(2)
            self.dw.move(5)
            self.dw.move(3)
            self.dw.move(5)
            self.dw.move(1)
            self.dw.move(3)
            self.dw.move(1)
            self.dw.move(6)
            self.dw.move(8)
            self.dw.move(6)
            self.dw.move(4)

    def centring_test(self):
        for i in range(0, 100):
            print(i)
            self.phi.move(45 * i)
            self.sampx.move(1.5)
            self.sampy.move(1.5)
            self.sampx.move(-1.5)
            self.sampy.move(-1.5)
            self.phiz.move(.5)
            self.phiy.move(.5)
            self.phiz.move(-.5)
            self.phiy.move(-.5)

    def phi_test(self):
        with open(os.path.join(os.environ["HOME"], "phi_test.dat"), "a+") as f:
            n = 0
            while True:
                with open(os.path.join(os.environ["HOME"], "phi_test.dat"), "a+") as f:
                    f.write("n= %s \n" % n)
                    self.phi.move(0)
                    phi_pos = self.phi.position
                    enc_pos_icepap = self.phienc.read() * self.phienc.steps_per_unit
                    enc_pos_musst = self.musst.putget("#?CH CH2")[:-3]
                    f.write(
                        "phi position (icepap controller)= %s   encoder position (icepap controller)= %s  encoder position (musst) %s \n"
                        % (phi_pos, enc_pos_icepap, enc_pos_musst)
                    )
                    self.phi.move(180)
                    phi_pos = self.phi.position
                    enc_pos_icepap = self.phienc.read() * self.phienc.steps_per_unit
                    enc_pos_musst = self.musst.putget("#?CH CH2")[:-3]
                    f.write(
                        "phi position (icepap controller)= %s   encoder position (icepap controller)= %s  encoder position (musst) %s \n"
                        % (phi_pos, enc_pos_icepap, enc_pos_musst)
                    )
                    n += 1
                    f.close()

    def beam_profile(
        self, length_in_mm=0.5, height_in_mm=0.5, space_in_um=5.0, filename="test.dat"
    ):
        array_height = numpy.arange(
            self.phiz.high_limit - height_in_mm,
            self.phiz.high_limit,
            space_in_um / 1000.0,
        )
        array_length = numpy.arange(
            self.phiy.high_limit - length_in_mm,
            self.phiy.high_limit,
            space_in_um / 1000.0,
        )
        for i in array_height:
            n_line = 1
            self.phiz.move(i)
            for j in array_length:
                self.phiy.move(j)
                i1 = self.diode(False, True)[1]
                n_line += 1
                with open(os.path.join(os.environ["HOME"], filename), "a+") as f:
                    f.write("phiz= %s phiy= %s i1= %s \n" % (i, j, i1))
        return "Done"

    def beam_profile_withAP(self):
        self.apy.move(0.0068)
        self.apz.move(1.5232)
        self.beam_profile(0.5, 0.5, 5.0, "7um.dat")
        self.apy.move(0.0069)
        self.apz.move(0.3271)
        self.beam_profile(0.5, 0.5, 5.0, "10um.dat")
        self.apy.move(0.012)
        self.apz.move(-0.8389)
        self.beam_profile(0.5, 0.5, 5.0, "15um.dat")
        self.apy.move(0.022)
        self.apz.move(-2.070)
        self.beam_profile(0.5, 0.5, 5.0, "30um.dat")
        self.apy.move(0.0135555)
        self.apz.move(-3.252777)
        self.beam_profile(0.5, 0.5, 5.0, "50um.dat")
        self.apy.move(-0.02322222222)
        self.apz.move(-11)
        self.beam_profile(0.5, 0.5, 5.0, "out-big.dat")

    def SOC(self, rot=360.0, step=5.0, delay=2.0, cycle=5):
        self.phi.move(0)
        self.musst.putget("#BTRIG 0")
        for i in range(0, cycle):
            print("#" * 50)
            print("cycle = ", i)
            while self.phi.position >= 0.0 and self.phi.position < rot:
                self.trig(delay)
                if self.phi.position <= rot - step:
                    self.phi.move_relative(step)
            self.trig(delay)
            print("phi(backlash1) = ", self.phi.position)
            self.phi.move_relative(45)
            print("phi(backlash2) = ", self.phi.position)
            self.phi.move_relative(-45)
            while self.phi.position > 0.0 and self.phi.position <= rot:
                self.trig(delay)
                if self.phi.position >= step:
                    self.phi.move_relative(-step)
            self.trig(delay)
            print("phi(backlash1) = ", self.phi.position)
            self.phi.move_relative(-45)
            print("phi(backlash2) = ", self.phi.position)
            self.phi.move_relative(45)
        return "DONE"

    def SOC_uni(self, rot=360.0, step=5.0, delay=2.0, cycle=5):
        self.phi.move(0)
        self.musst.putget("#BTRIG 0")
        tot_rot = rot * (cycle)
        self.trig(delay)
        while self.phi.position >= 0.0 and self.phi.position < tot_rot:
            self.phi.move_relative(step)
            self.trig(delay)

    def save_snapshot(self, filename):
        rpc_srv = xmlrpclib.Server("http://capek:7171")
        rpc_srv.save_snapshot(filename)

    def estimateFocus_crop(self, filename):
        self._dictGeo = {}  # key:shape, value= ai
        self._sem = Semaphore()
        img = scipy.misc.imread(filename, True)
        shape = img.shape
        img_crop = img[shape[0] / 3 : -shape[0] / 3, shape[1] / 3 : -shape[1] / 3]
        scipy.misc.imshow(img_crop)
        shape = img_crop.shape
        nr = numpy.sqrt(shape[0] * shape[0] + shape[1] * shape[1]) // 2
        if shape not in self._dictGeo:
            with self._sem:
                if shape not in self._dictGeo:
                    ai = pyFAI.AzimuthalIntegrator()
                    ai.setFit2D(
                        1000, shape[0] // 2, shape[1] // 2, pixelX=10, pixelY=10
                    )
                    self._dictGeo[shape] = ai
        ai = self._dictGeo[shape]
        ft = numpy.fft.fft2(img_crop)
        fts = numpy.fft.fftshift(ft)
        r, i = ai.integrate1d(abs(fts) ** 2, nr, unit="r_mm")
        value = -scipy.stats.linregress(numpy.log(r), numpy.log(i))[0]
        return value

    def std_img(self, filename):
        img = scipy.misc.imread(filename, True)
        shape = img.shape
        img_crop = img[(shape[0] / 2 - 20) : (shape[0] / 2 + 20), 0 : shape[1]]
        img_filtered = scipy.ndimage.median_filter(img_crop, 25)
        return scipy.ndimage.standard_deviation(img_filtered)

    def estimateFocus(self, filename, imgview=False):
        self._dictGeo = {}  # key:shape, value= ai
        self._sem = Semaphore()
        img = scipy.misc.imread(filename, True)
        shape = img.shape
        img_crop = img[
            (shape[0] / 2 - 30) : (shape[0] / 2 + 30),
            (shape[1] / 2 - 150) : (shape[1] / 2 + 150),
        ]
        shape = img_crop.shape
        if imgview:
            scipy.misc.imshow(img_crop)
        nr = numpy.sqrt(shape[0] * shape[0] + shape[1] * shape[1]) // 2
        if shape not in self._dictGeo:
            with self._sem:
                if shape not in self._dictGeo:
                    ai = pyFAI.AzimuthalIntegrator()
                    ai.setFit2D(
                        1000, shape[0] // 2, shape[1] // 2, pixelX=10, pixelY=10
                    )
                    self._dictGeo[shape] = ai
        ai = self._dictGeo[shape]
        ft = numpy.fft.fft2(img_crop)
        fts = numpy.fft.fftshift(ft)
        r, i = ai.integrate1d(abs(fts) ** 2, nr, unit="r_mm")
        value = -scipy.stats.linregress(numpy.log(r), numpy.log(i))[0]
        return value

    def smooth(self, x, window_len=2.0):
        y = numpy.array([])
        for i in range(1, len(x)):
            y = numpy.append(y, (x[i - 1] + x[i]) / window_len)
        return y

    def autofocus_test(self, size=0.5, step=20.0):
        step_size = size / float(step)
        pos = 0.3
        data_X = numpy.arange(
            pos - size / 2, pos + (size / 2.0) * (1.0 + 1.0 / step), step_size
        )
        data_Y = numpy.array([])
        name = "/tmp/image"
        for i in data_X:
            filename = name + "_%.3f" % i + ".jpg"
            if len(data_Y) == 0:
                est_focus = self.estimateFocus(filename, False)
            else:
                est_focus = self.estimateFocus(filename)
            data_Y = numpy.append(data_Y, est_focus)
            print(i, data_Y[-1:][0])
        print(data_X)
        print(data_Y)
        std = scipy.ndimage.measurements.standard_deviation(data_Y)
        data_Y_smooth = self.smooth(data_Y)
        print(data_Y_smooth)
        fit = PyMca.SimpleFitModule.SimpleFit()
        fit.importFunctions(PyMca.SpecfitFunctions)
        fit.setFitFunction("Gaussians")
        i_data = -data_Y_smooth
        for i in range(1, len(i_data)):
            print(data_X[i], i_data[i])
        print(len(data_X[1:]), len(i_data))
        fit.setData(data_X[1:], i_data)
        return fit.fit()

    def autofocus(self, size=1.0, step=5.0):
        pos = self.x.position
        step_size = size / float(step)
        data_X = numpy.arange(
            pos - size / 2, pos + (size / 2.0) * (1.0 + 1.0 / step), step_size
        )
        data_Y = numpy.array([])
        name = "/tmp/image"
        for i in data_X:
            self.x.move(i)
            filename = name + "_%.3f" % i + ".jpg"
            self.save_snapshot(filename)
            if len(data_Y) == 0:
                est_focus = self.estimateFocus(filename, False)
            else:
                est_focus = self.estimateFocus(filename)
            data_Y = numpy.append(data_Y, est_focus)
            print(i, data_Y[-1:][0])
        print(data_X)
        print(data_Y)
        std = scipy.ndimage.measurements.standard_deviation(data_Y)
        data_Y_smooth = self.smooth(data_Y, 3)
        print(data_Y_smooth)
        fit = PyMca.SimpleFitModule.SimpleFit()
        fit.importFunctions(PyMca.SpecfitFunctions)
        fit.setFitFunction("Gaussians")
        i_data = -data_Y_smooth
        print(len(data_X), len(i_data))
        for i in range(0, len(i_data)):
            print(data_X[i], i_data[i])
        print(len(data_X), len(i_data))
        fit.setData(data_X, i_data)
        return fit.fit()
        """focus_1st_img = self.estimateFocus("/tmp/prev_image.jpg")
        print "1st image ", focus_1st_img, "at x= ", self.x.position
        self.x.move_relative(step_size)
        focus_2nd_img = self.estimateFocus("/tmp/next_image.jpg")
        print "2nd image ", focus_2nd_img, "at x= ", self.x.position
        if focus_2nd_img > focus_1st_img:
            direction = 1
            focus_prev_img = focus_1st_img
            focus_next_img = focus_2nd_img
        elif focus_2nd_img < focus_1st_img:
            direction = -1
            focus_prev_img = focus_2nd_img 
            focus_next_img = focus_1st_img
        print "direction= ", direction
        while focus_next_img > focus_prev_img:
            focus_prev_img = focus_next_img
            print "1st image (while) ", focus_prev_img, "at x= ", self.x.position
            self.x.move_relative(direction * step_size)
            focus_next_img = self.estimateFocus("/tmp/next_image.jpg")
            print "2nd image (while) ", focus_next_img, "at x= ", self.x.position
        self.x.move_relative(-direction * step_size)
        print "at x= ", self.x.position
        """
