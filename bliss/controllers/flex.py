# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from StaubCom import robot
from StaubCom.flex import Ueye_cam
from StaubCom.flex import OneWire
from StaubCom.flex import dm_reader
from StaubCom.flex import ProxiSense
import gevent
import math
import time
import itertools
import os
import shutil
import sys
import configparser
import ast
import inspect
import numpy

import logging
from logging.handlers import TimedRotatingFileHandler

flex_logger = logging.getLogger("flex")
flex_logger.setLevel(logging.DEBUG)
flex_log_formatter = logging.Formatter("%(name)s %(levelname)s %(asctime)s %(message)s")
flex_log_handler = None

from bliss.common import event


def grouper(iterable, n):
    args = [iter(iterable)] * n
    return itertools.zip_longest(fillvalue=None, *args)


BUSY = False
DEFREEZING = False


def notwhenbusy(func):
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


class flex(object):
    def __init__(self, name, config):
        self.cs8_ip = config.get("ip")
        self.ueye_id = int(config.get("ueye"))
        self.ow_port = str(config.get("ow_port"))
        self.microscan_hor_ip = config.get("ip_hor")
        self.microscan_vert_ip = config.get("ip_vert")
        self.proxisense_address = config.get("proxisense_address")
        self.calibration_file = config.get("calibration_file")
        self.robot = None
        self.cam = None
        self.robot_exceptions = []
        self._loaded_sample = (-1, -1, -1)
        robot.setLogFile(config.get("log_file"))
        robot.setExceptionLogFile(config.get("exception_file"))
        global flex_log_handler
        flex_log_handler = TimedRotatingFileHandler(
            config.get("flex_log_file"), when="midnight", backupCount=7
        )
        flex_log_handler.setFormatter(flex_log_formatter)
        flex_logger.addHandler(flex_log_handler)
        logging.getLogger("flex").info("")
        logging.getLogger("flex").info("")
        logging.getLogger("flex").info("")
        logging.getLogger("flex").info("#" * 50)
        logging.getLogger("flex").info("pyFlex Initialised")

    @property
    def unipuck_cells(self):
        return ast.literal_eval(self.config.get("HCD", "unipuck_cells"))

    def connect(self):
        logging.getLogger("flex").info("reading config file")
        self.config = configparser.RawConfigParser()
        cfg_file_path = os.path.join(
            os.path.dirname(self.calibration_file), "detection.cfg"
        )
        self.config.read(cfg_file_path)

        logging.getLogger("flex").info("connecting to Flex")
        self.onewire = OneWire(self.ow_port)
        self.cam = Ueye_cam(self.ueye_id, os.path.dirname(self.calibration_file))
        self.microscan_hor = dm_reader(self.microscan_hor_ip)
        all_unipucks = len(self.unipuck_cells) == 8
        if not all_unipucks:
            self.microscan_vert = dm_reader(self.microscan_vert_ip)
        self.proxisense = ProxiSense(
            self.proxisense_address, os.path.dirname(self.calibration_file)
        )
        self.robot = robot.Robot("flex", self.cs8_ip)
        event.connect(self.robot, "robot_exception", self._enqueue_robot_exception_msg)
        logging.getLogger("flex").info("Connection done")
        self._loaded_sample = self.read_loaded_position()

    def _enqueue_robot_exception_msg(self, msg):
        self.robot_exceptions.append(msg)

    def getRobotExceptions(self):
        ret = self.robot_exceptions[:]
        self.robot_exceptions = []
        return ret

    def get_cachedVariable_list(self):
        return list(self.robot._cached_variables.keys())

    def get_detection_param(self, section, name_value):
        val = ast.literal_eval(self.config.get(section, name_value))
        if section == "acq_time":
            logging.getLogger("flex").info("Acquisition time is set to %s" % (str(val)))
        else:
            logging.getLogger("flex").info(
                "Roi for %s detection is %s" % (section, str(val))
            )
        return val

    def transfer_counter(self, success=True):
        parser = configparser.RawConfigParser()
        file_path = os.path.dirname(self.calibration_file) + "/transfer_counter.log"
        parser.read(file_path)
        if success:
            transfer_iter = parser.getint("total transfer", "success") + 1
            parser.set("total transfer", "success", str(transfer_iter))
            logging.getLogger("flex").info(
                "total number of successful transfer: %d" % (transfer_iter)
            )
        else:
            transfer_iter = parser.getint("total transfer", "failure") + 1
            parser.set("total transfer", "failure", str(transfer_iter))
            logging.getLogger("flex").info(
                "total number of transfer with failure: %d" % (transfer_iter)
            )
        with open(file_path, "wb") as file:
            parser.write(file)

    @notwhenbusy
    def setSpeed(self, speed):
        if 0 <= speed <= 100:
            logging.getLogger("flex").info("Set speed to %d" % speed)
            self.robot.setSpeed(speed)
            logging.getLogger("flex").info(
                "Speed is at %s" % str(self.robot.getSpeed())
            )

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
            logging.getLogger("flex").error(msg)
            raise RuntimeError(msg)
        logging.getLogger("flex").info("Power set to %s" % state)

    def abort(self):
        self.robot.abort()
        self.set_io("dioUnloadStReq", False)
        self.set_io("dioLoadStReq", False)
        self.robot.setVal3GlobalVariableBoolean("bEnable_PSS", False)
        DEFREEZING = False

        logging.getLogger("flex").info("Robot aborted")

    def set_io(self, dio, boolean):
        logging.getLogger("flex").info("Set IO %s to %s" % (dio, str(bool(boolean))))
        if bool(boolean):
            self.robot.execute("data:" + dio + "=true")
        else:
            self.robot.execute("data:" + dio + "=false")

    def PSS_light(self):
        self.robot.setVal3GlobalVariableBoolean("bEnable_PSS", True)
        try:
            while True:
                gevent.sleep(60)
        finally:
            self.robot.setVal3GlobalVariableBoolean("bEnable_PSS", False)

    @notwhenbusy
    def gripper_port(self, boolean):
        self.set_io("dioOpenGrpPort", bool(boolean))
        try:
            with gevent.Timeout(10):
                if bool(boolean) == True:
                    while (
                        self.robot.getCachedVariable("data:dioGrpPortIsOp").getValue()
                        == "false"
                    ):
                        self.robot.waitNotify("data:dioGrpPortIsOp")
                else:
                    while (
                        self.robot.getCachedVariable("data:dioGrpPortIsClo").getValue()
                        == "false"
                    ):
                        self.robot.waitNotify("data:dioGrpPortIsClo")
        except gevent.timeout.Timeout:
            logging.getLogger("flex").error("Timeout on gripper port")

    @notwhenbusy
    def robot_port(self, boolean):
        self.set_io("dioOpenRbtPort", bool(boolean))
        try:
            with gevent.Timeout(10):
                if bool(boolean) == True:
                    while (
                        self.robot.getCachedVariable("data:dioRobotPtIsOp").getValue()
                        == "false"
                    ):
                        self.robot.waitNotify("data:dioRobotPtIsOp")
                else:
                    while (
                        self.robot.getCachedVariable("data:dioRobotPtIsClo").getValue()
                        == "false"
                    ):
                        self.robot.waitNotify("data:dioRobotPtIsClo")
        except gevent.timeout.Timeout:
            logging.getLogger("flex").error("Timeout on robot port")

    def user_port(self, boolean):
        if self.config.get("HCD", "loading_port") == "robot_port":
            self.robot_port(boolean)
        else:
            self.set_io("dioOpenUsrPort", bool(boolean))
            try:
                with gevent.Timeout(10):
                    if bool(boolean) == True:
                        while (
                            self.robot.getCachedVariable("data:dioUsrPtIsOp").getValue()
                            == "false"
                        ):
                            self.robot.waitNotify("data:dioUsrPtIsOp")
                    else:
                        while (
                            self.robot.getCachedVariable(
                                "data:dioUsrPtIsClo"
                            ).getValue()
                            == "false"
                        ):
                            self.robot.waitNotify("data:dioUsrPtIsClo")
            except gevent.timeout.Timeout:
                logging.getLogger("flex").error("Timeout on user port")

    @notwhenbusy
    def moveDewar(self, cell, puck=1, user=False):
        logging.getLogger("flex").info("Starting to move the Dewar")
        if isinstance(cell, int) and isinstance(puck, int):
            if not cell in range(1, 9):
                logging.getLogger("flex").error("Wrong cell number [1-8]")
                raise ValueError("Wrong cell number [1-8]")
        else:
            logging.getLogger("flex").error("Cell must be integer")
            raise ValueError("Cell must be integer")
        if user:
            cell = cell + 5
            if cell > 8:
                cell = math.fmod(cell, 8)
        logging.getLogger("flex").info("Dewar to move to %d" % cell)
        self.robot.setVal3GlobalVariableDouble("nDewarDest", str(3 * (int(cell) - 1)))
        self.robot.executeTask("moveDewar", timeout=60)
        gevent.sleep(0.5)  # give time to have DewarInPosition updated
        try:
            with gevent.Timeout(10):
                while (
                    self.robot.getCachedVariable("DewarInPosition").getValue()
                    == "false"
                ):
                    self.robot.waitNotify("DewarInPosition")
        except gevent.timeout.Timeout:
            self.stopDewar()
            logging.getLogger("flex").error("Timeout")
            raise
        logging.getLogger("flex").info("Dewar moved to %d" % cell)

    def get_loaded_sample(self):
        if self._loaded_sample == None:
            self._loaded_sample = self.read_loaded_position()
        return self._loaded_sample

    def get_cell_position(self):
        if self.robot.getCachedVariable("DewarInPosition").getValue():
            try:
                VAL3_puck = int(
                    self.robot.getCachedVariable("RequestedDewarPosition").getValue()
                )
            except:
                return None, None
            cell = VAL3_puck // 3 + 1
            puck = VAL3_puck % 3 + 1

            return cell, puck
        return None, None

    def get_user_cell_position(self):
        if self.robot.getCachedVariable("DewarInPosition").getValue():
            try:
                VAL3_puck = int(
                    self.robot.getCachedVariable("RequestedDewarPosition").getValue()
                )
            except:
                return None
            if self.config.get("HCD", "loading_port") == "robot_port":
                cell = self.get_cell_position()[0]
            else:
                cell = ((VAL3_puck // 3 + 3) % 8) + 1
            return cell

    def pin_on_gonio(self):
        value = self.robot.getCachedVariable("data:dioPinOnGonio").getValue() == "true"
        success = 0
        with gevent.Timeout(
            3, RuntimeError("SmartMagnet problem: don't know if pin is on gonio.")
        ):
            while True:
                gevent.sleep(0.2)
                new_value = (
                    self.robot.getCachedVariable("data:dioPinOnGonio").getValue()
                    == "true"
                )
                if value == new_value:
                    success += 1
                else:
                    success = 0
                value = new_value
                if success == 2:
                    return new_value

    def arm_is_parked(self):
        return self.robot.getCachedVariable("data:dioArmIsParked").getValue() == "true"

    def ready_for_centring(self):
        if self.pin_on_gonio():
            if self.arm_is_parked():
                return True
        return False

    def get_robot_cache_variable(self, varname):
        try:
            # logging.getLogger('flex').info("cache variable %s is %s", str(varname), str(self.robot.getCachedVariable(varname).getValue()))
            return self.robot.getCachedVariable(varname).getValue()
        except Exception:
            return ""

    def set_massCompensation(self, x, y, z, rx=0, ry=0, rz=0):
        logging.getLogger("flex").info(
            "set mass compensation to x=%s, y=%s, z=%s, rx=%s, ry=%s, rz=%s",
            str(x),
            str(y),
            str(z),
            str(rx),
            str(ry),
            str(rz),
        )
        if (
            abs(x) > 1
            or abs(y) > 1
            or abs(z) > 1
            or abs(rx) > 1
            or abs(ry) > 1
            or abs(rz) > 1
        ):
            logging.getLogger("flex").error(
                "Mass compensation too high, all coordinates must be less than 1.0"
            )
        self.robot.setVal3GlobalVariableDouble("trFpGripMasComp.x", str(x))
        self.robot.setVal3GlobalVariableDouble("trFpGripMasComp.y", str(y))
        self.robot.setVal3GlobalVariableDouble("trFpGripMasComp.z", str(z))
        self.robot.setVal3GlobalVariableDouble("trFpGripMasComp.rx", str(rx))
        self.robot.setVal3GlobalVariableDouble("trFpGripMasComp.ry", str(ry))
        self.robot.setVal3GlobalVariableDouble("trFpGripMasComp.rz", str(rz))
        self.savedata()

    def do_homeClear(self):
        with BackgroundGreenlets(self.PSS_light, ()) as X:
            return X.execute(self.robot.executeTask, "homeClear", timeout=60)

    @notwhenbusy
    def homeClear(self):
        logging.getLogger("flex").info("Starting homing")
        self.set_io("dioEnablePress", True)
        gripper_type = self.get_gripper_type()
        if gripper_type not in [-1, 0, 1, 3, 9]:
            logging.getLogger("flex").error("No or wrong gripper")
            raise ValueError("No or wrong gripper")
        self.robot.setVal3GlobalVariableDouble("nGripperType", str(gripper_type))
        if gripper_type == -1:
            self.robot.setVal3GlobalVariableBoolean("bGripperIsOnArm", False)
        else:
            # self.robot.setVal3GlobalVariableDouble("nGripperType", str(gripper_type))
            self.robot.setVal3GlobalVariableBoolean("bGripperIsOnArm", True)
        if gripper_type in [-1, 1, 3, 9]:
            self.do_homeClear()
            self.update_transfer_iteration(reset=True)
        logging.getLogger("flex").info("Homing done")

    def do_dryWithoutPloun(self):
        with BackgroundGreenlets(self.PSS_light, ()) as X:
            return X.execute(self.robot.executeTask, "dryWithoutPloun", timeout=90)

    @notwhenbusy
    def dryWithoutPloun(self):
        logging.getLogger("flex").info("Starting defreeze gripper and stay parked")
        gripper_type = self.get_gripper_type()
        logging.getLogger("flex").info("gripper type %s" % gripper_type)
        if gripper_type not in [-1, 0, 1, 3, 9]:
            logging.getLogger("flex").error("No or wrong gripper")
            raise ValueError("No or wrong gripper")
        if gripper_type == -1:
            self.robot.setVal3GlobalVariableBoolean("bGripperIsOnArm", False)
            self.robot.setVal3GlobalVariableDouble("nGripperType", "0")
        else:
            self.robot.setVal3GlobalVariableBoolean("bGripperIsOnArm", True)
            self.robot.setVal3GlobalVariableDouble("nGripperType", str(gripper_type))
        if gripper_type in [1, 3, 9]:
            self.do_dryWithoutPloun()
            self.update_transfer_iteration(reset=True)
        logging.getLogger("flex").info("Defreezing gripper finished")

    def do_defreezeGripper(self):
        with BackgroundGreenlets(self.PSS_light, ()) as X:
            return X.execute(self.robot.executeTask, "defreezeGripper", timeout=200)

    def isDefreezing(self):
        return DEFREEZING

    @notwhenbusy
    def defreezeGripper(self):
        global DEFREEZING
        DEFREEZING = True
        logging.getLogger("flex").info("Starting defreeze gripper")
        self.set_io("dioEnablePress", True)
        gripper_type = self.get_gripper_type()
        logging.getLogger("flex").info("gripper type %s" % gripper_type)
        if gripper_type not in [-1, 0, 1, 3, 9]:
            logging.getLogger("flex").error("No or wrong gripper")
            raise ValueError("No or wrong gripper")
        if gripper_type == -1:
            self.robot.setVal3GlobalVariableBoolean("bGripperIsOnArm", False)
            self.robot.setVal3GlobalVariableDouble("nGripperType", "0")
        else:
            self.robot.setVal3GlobalVariableBoolean("bGripperIsOnArm", True)
            self.robot.setVal3GlobalVariableDouble("nGripperType", str(gripper_type))
        if gripper_type in [1, 3, 9]:
            self.do_defreezeGripper()
            self.update_transfer_iteration(reset=True)
        logging.getLogger("flex").info("Defreezing gripper finished")
        DEFREEZING = False

    def check_coordinates(self, cell, puck, sample):
        if isinstance(cell, int) and isinstance(puck, int) and isinstance(sample, int):
            if not cell in range(1, 9):
                logging.getLogger("flex").error("Wrong cell number [1-8]")
                raise ValueError("Wrong cell number [1-8]")
            if not puck in range(1, 4):
                logging.getLogger("flex").error("wrong puck number [1-3]")
                raise ValueError("Wrong puck number [1-3]")
            if cell in self.unipuck_cells:
                puckType = 2
                if not sample in range(1, 17):
                    logging.getLogger("flex").error("wrong sample number [1-16]")
                    raise ValueError("wrong sample number [1-16]")
            else:
                if cell in range(1, 9, 2):
                    puckType = 3
                    if not sample in range(1, 11):
                        logging.getLogger("flex").error("wrong sample number [1-10]")
                        raise ValueError("wrong sample number [1-10]")
                if cell in range(2, 10, 2):
                    puckType = 2
                    if not sample in range(1, 17):
                        logging.getLogger("flex").error("wrong sample number [1-16]")
                        raise ValueError("wrong sample number [1-16]")
            puck = 3 * (cell - 1) + puck - 1
            sample = sample - 1
            if puck == 23:
                logging.getLogger("flex").error(
                    "cannot load/unload from/to recovery puck"
                )
                raise RuntimeError("cannot load/unload from/to recovery puck")
        else:
            logging.getLogger("flex").error("cell, puck and sample must be integer")
            raise ValueError("cell, puck and sample must be integer")
        return cell, puck, sample, puckType

    def waiting_for_image(self, acq_time=0.001, timeout=60):
        self.cam.prepare(acq_time)
        prev_imgNb = int(self.cam.control.getImageStatus().LastImageAcquired)
        logging.getLogger("flex").info("Image number %d" % prev_imgNb)
        imgNb = prev_imgNb
        try:
            with gevent.Timeout(timeout):
                while imgNb == prev_imgNb:
                    gevent.sleep(0.05)
                    imgNb = int(self.cam.control.getImageStatus().LastImageAcquired)
        except gevent.timeout.Timeout:
            logging.getLogger("flex").error("Timeout in waiting for image")
            raise
        logging.getLogger("flex").info("image taken number %d" % imgNb)
        prev_imgNb = imgNb
        image = self.cam.BW_image(self.cam.take_snapshot())
        try:
            self.cam.image_save(image)
        except Exception as e:
            logging.getLogger("flex").exception("Could not save image")
        return image

    def save_ref_image(self, image, filename):
        logging.getLogger("flex").info("Saving the reference file")
        dir = os.path.dirname(self.calibration_file)
        file_path = os.path.join(dir, filename) + ".edf"
        old_file_path = os.path.join(dir, filename) + ".old"
        try:
            os.remove(old_file_path)
        except OSError:
            logging.getLogger("flex").info("error in OS command remove")
        try:
            os.rename(file_path, old_file_path)
        except OSError:
            logging.getLogger("flex").info("error in OS command rename")
        logging.getLogger("flex").info("save ref image in %s" % file_path)
        self.cam.image_save(image, dir=dir, prefix=filename)

    def pin_detection(self, gripper_type, ref):
        logging.getLogger("flex").info("Pin detection")
        acq_time = self.get_detection_param("acq_time", "pin")
        image = self.waiting_for_image(acq_time=acq_time, timeout=60)
        if int(gripper_type) == 1:
            if ref == "True":
                filename = "ref_spine_with_pin"
                self.save_ref_image(image, filename)
            # roi = [[700,800], [800,1023]]
            roi = self.get_detection_param("pin_unipuck", "roi")
            PinIsInGripper = not (self.cam.is_empty(image, roi))
            logging.getLogger("flex").info(
                "Pin is in the gripper %s" % str(PinIsInGripper)
            )
            if PinIsInGripper:
                self.robot.setVal3GlobalVariableBoolean("bPinIsInGripper", True)
            # roi = [[600,700], [900,1023]]
            roi_edge = self.get_detection_param("pin_unipuck", "roi_edge")
            edge = self.cam.vertical_edge(image, roi_edge)
            logging.getLogger("flex").info("Vertical edge of the pin %s" % str(edge))
            if edge is not None:
                sp_ref_file = os.path.join(
                    os.path.dirname(self.calibration_file), "ref_spine_with_pin.edf"
                )
                ref_image = self.cam.image_read(sp_ref_file)
                ref_image_edge = self.cam.vertical_edge(ref_image, roi_edge)
                logging.getLogger("flex").info(
                    "edge position on the reference image %s" % str(ref_image_edge)
                )
                distance_from_ref = self.cam.edge_distance(ref_image_edge, edge)
                logging.getLogger("flex").info(
                    "distance of the pin from the reference  %s"
                    % str(distance_from_ref)
                )
                if abs(distance_from_ref) <= self.get_detection_param(
                    "distance_from_ref", "unipuck"
                ):
                    self.robot.setVal3GlobalVariableBoolean("bPinIsOkInGrip", True)
        if int(gripper_type) == 3:
            if ref == "True":
                filename = "ref_flipping_with_pin"
                self.save_ref_image(image, filename)
            logging.getLogger("flex").info(
                "gripper for pin detection is %s" % gripper_type
            )
            # roi_pin = [[350,200], [630,450]]
            # roi_pin = [[400,550], [800,750]]
            roi_pin = self.get_detection_param("pin_flipping", "roi_pin")
            PinIsInGripper = not (self.cam.is_empty(image, roi_pin))
            if PinIsInGripper:
                logging.getLogger("flex").info("Pin is in gripper")
                self.robot.setVal3GlobalVariableBoolean("bPinIsInGripper", True)
                edge = self.cam.horizontal_edge(image, roi_pin)
                logging.getLogger("flex").info(
                    "Horizontal edge of the pin %s" % str(edge)
                )
                if edge is not None:
                    fp_ref_file = os.path.join(
                        os.path.dirname(self.calibration_file),
                        "ref_flipping_with_pin.edf",
                    )
                    ref_image = self.cam.image_read(fp_ref_file)
                    ref_image_edge = self.cam.horizontal_edge(ref_image, roi_pin)
                    logging.getLogger("flex").info(
                        "edge position on the reference image %s" % str(ref_image_edge)
                    )
                    distance_from_ref = self.cam.edge_distance(
                        self.cam.horizontal_edge(ref_image, roi_pin), edge
                    )
                    logging.getLogger("flex").info(
                        "distance of the pin from the reference %s"
                        % str(distance_from_ref)
                    )
                    if abs(distance_from_ref) <= self.get_detection_param(
                        "distance_from_ref", "spine"
                    ):
                        self.robot.setVal3GlobalVariableBoolean("bPinIsOkInGrip", True)
                    else:
                        logging.getLogger("flex").error(
                            "distance from reference is too high"
                        )

                # roi_gripper = [[0,550], [70,900]]
                roi_gripper = self.get_detection_param("pin_flipping", "roi_gripper")
                if roi_gripper[0][1] != roi_pin[0][1]:
                    logging.getLogger("flex").error(
                        "2 rois must be on the same horizontal line from top"
                    )
                    raise ValueError(
                        "2 rois must be on the same horizontal line from top"
                    )
                edge_gripper = self.cam.horizontal_edge(image, roi_gripper)
                edge_pin = self.cam.horizontal_edge(image, roi_pin)
                logging.getLogger("flex").info(
                    "horizontal edge of the pin %s and of the gripper %s"
                    % (str(edge_pin), str(edge_gripper))
                )
                if edge_gripper is not None or edge_pin is not None:
                    distance_pin_gripper = self.cam.edge_distance(
                        edge_pin, edge_gripper
                    )
                    logging.getLogger("flex").info(
                        "distance between pin and gripper %s"
                        % str(distance_pin_gripper)
                    )
                    # DN must be negative if the pin stands out of the gripper if not VAL3 will care about the error
                    min_dist_pin_gripper = self.get_detection_param(
                        "distance_pin_gripper", "min"
                    )
                    max_dist_pin_gripper = self.get_detection_param(
                        "distance_pin_gripper", "max"
                    )
                    if (
                        min_dist_pin_gripper
                        <= abs(distance_pin_gripper)
                        <= max_dist_pin_gripper
                    ):
                        self.robot.setVal3GlobalVariableDouble(
                            "trsfPutFpGonio.z", str(distance_pin_gripper)
                        )
                        logging.getLogger("flex").info("distance saved in robot")
                    else:
                        logging.getLogger("flex").error(
                            "distance pin gripper is %s should be between %s-%smm"
                            % (
                                str(abs(distance_pin_gripper)),
                                str(min_dist_pin_gripper),
                                str(max_dist_pin_gripper),
                            )
                        )
                else:
                    logging.getLogger("flex").error(
                        "Edge of the gripper or of the pin not found"
                    )
                    raise RuntimeError("Edge of the gripper or of the pin not found")
            else:
                logging.getLogger("flex").info(
                    "Pin is not in gripper, calling vial detection"
                )
                self.robot.setVal3GlobalVariableBoolean("bPinIsInGripper", False)
                self.robot.setVal3GlobalVariableBoolean("bPinIsOkInGrip", False)
                self.vial_detection(image)

    def vial_center_detection(self):
        acq_time = self.get_detection_param("acq_time", "vial")
        image = self.waiting_for_image(acq_time=acq_time, timeout=60)
        roi_left = self.get_detection_param("vial_center", "roi_left")
        roi_right = self.get_detection_param("vial_center", "roi_right")
        left_edge = self.cam.vertical_edge(image, roi_left)
        right_edge = self.cam.vertical_edge(image, roi_right)
        logging.getLogger("flex").info(
            "Vial left edge %s right_edge %s" % (str(left_edge), str(right_edge))
        )
        if left_edge is None or right_edge is None:
            return None
        center = (left_edge + right_edge) / 2.
        logging.getLogger("flex").info("center %s" % str(center))
        return center

    def vial_centering(self, center_1, center_2, center_3):
        logging.getLogger("flex").info(
            "center 1 %s, center 2 %s, center 3 %s"
            % (str(center_1), str(center_2), str(center_3))
        )
        if center_1 is None or center_2 is None or center_3 is None:
            logging.getLogger("flex").error("Correction not applicable")
            raise RuntimeError("Correction not applicable")
        # angle in degrees between the plan (x,y) of the robot and the plan of the camera
        angle_deg = 130.
        angle_rad = math.pi * angle_deg / 180.
        Xoffset = ((center_1 + center_3) / 2. - center_1) / self.cam.pixels_per_mm
        Yoffset = ((center_1 + center_3) / 2. - center_2) / self.cam.pixels_per_mm
        gripper_Xoffset = -math.cos(angle_rad) * Yoffset - math.sin(angle_rad) * Xoffset
        gripper_Yoffset = math.cos(angle_rad) * Xoffset - math.sin(angle_rad) * Yoffset
        logging.getLogger("flex").info(
            "Gripper correction in X %s in Y %s"
            % (str(gripper_Xoffset), str(gripper_Yoffset))
        )
        if abs(gripper_Xoffset) < 3 or abs(gripper_Yoffset) < 3:
            self.robot.setVal3GlobalVariableDouble(
                "trVialPosCorr.x", str(gripper_Xoffset)
            )
            self.robot.setVal3GlobalVariableDouble(
                "trVialPosCorr.y", str(gripper_Yoffset)
            )
            # DN no watch in Val3 loadFlipping/robot.FpPutVialDew to be done by GP
            self.robot.setVal3GlobalVariableBoolean("bImageProcEnded", True)
        else:
            logging.getLogger("flex").error("Correction is too high")
            raise RuntimeError("Correction is too high")

    def vial_detection(self, image):
        # roi = [[350,600], [650,1023]]
        # roi = [[200,500], [350,1023]]
        # roi = [[500,500], [700,1023]]
        roi = self.get_detection_param("vial", "roi")
        VialIsNotInGripper = self.cam.is_empty(image, roi)
        if VialIsNotInGripper:
            logging.getLogger("flex").info("Vial is not in gripper")
            self.robot.setVal3GlobalVariableBoolean("bVialIsInGrip", False)
        else:
            vial_edge = self.cam.horizontal_edge(image, roi)
            logging.getLogger("flex").info("Vial edge position %s" % str(vial_edge))
            fp_ref_file = os.path.join(
                os.path.dirname(self.calibration_file), "ref_flipping_with_pin.edf"
            )
            ref_image = self.cam.image_read(fp_ref_file)
            # roi_ref = [[200,300], [800,600]]
            roi_ref = self.get_detection_param("vial", "roi_ref")
            ref_image_edge = self.cam.horizontal_edge(ref_image, roi_ref)
            logging.getLogger("flex").info(
                "Ref pin edge position %s" % str(ref_image_edge)
            )
            cap_height = 3.0
            ref_vial_edge = cap_height * self.cam.pixels_per_mm + ref_image_edge
            logging.getLogger("flex").info(
                "Reference vial edge position %s" % str(ref_vial_edge)
            )
            if abs(ref_vial_edge - vial_edge) < 200:
                self.robot.setVal3GlobalVariableBoolean("bVialIsInGrip", True)
                logging.getLogger("flex").info("Vial is in gripper")
            else:
                logging.getLogger("flex").info(
                    "Vial edge too different to the reference"
                )
                self.robot.setVal3GlobalVariableBoolean("bVialIsInGrip", False)

    def dm_detection(self, GripperType):
        logging.getLogger("flex").info(
            "Starting Data matrix reading with gripper type %s" % GripperType
        )
        if int(GripperType) == 1:
            try:
                dm = self.microscan_hor.socket_server.recv(1024)
                self.robot.setVal3GlobalVariableBoolean("bCodeDetected", True)
            except:
                dm = None
        if int(GripperType) == 3:
            try:
                dm = self.microscan_vert.socket_server.recv(1024)
                self.robot.setVal3GlobalVariableBoolean("bCodeDetected", True)
            except:
                dm = None
        logging.getLogger("flex").info("Data matrix is %s" % dm)

    def detection(self, gripper_type, ref):
        ref_already_saved = False
        dm_reading = None

        try:
            while True:
                notify = self.robot.waitNotify("ImageProcessing")
                logging.getLogger("flex").info(
                    "notify %s with gripper type %s" % (notify, gripper_type)
                )
                if notify == "PinDetection":
                    if ref == "True" and ref_already_saved == False:
                        self.pin_detection(gripper_type, "True")
                        ref_already_saved = True
                    else:
                        self.pin_detection(gripper_type, "False")
                    logging.getLogger("flex").info("reading data matrix variable")
                    DM_detected = self.robot.getVal3GlobalVariableBoolean(
                        "bCodeDetected"
                    )
                    if not DM_detected:
                        logging.getLogger("flex").info("read Data Matrix")
                        dm_reading = gevent.spawn(self.dm_detection, gripper_type)
                    else:
                        logging.getLogger("flex").info("DM not needed")
                elif notify.startswith("VialDetection"):
                    run = notify.split("_")[1]
                    if run == "1":
                        centers = []
                    logging.getLogger("flex").info("Starting vial center detection")
                    logging.getLogger("flex").info(
                        "length of centers list is  %s and run is %s"
                        % (str(len(centers)), str(run))
                    )
                    vial_center = self.vial_center_detection()
                    logging.getLogger("flex").info("center is at %s" % str(vial_center))
                    centers.append(vial_center)
                    logging.getLogger("flex").info(
                        "length of centers list is  %s and run is %s"
                        % (str(len(centers)), str(run))
                    )
                    if run != str(len(centers)):
                        logging.getLogger("flex").error("image lost in vial detection")
                        # raise RuntimeError("image lost in vial detection")
                    if len(centers) == 3:
                        logging.getLogger("flex").info("Calling Vial centering")
                        self.vial_centering(*centers)
                else:
                    logging.getLogger("flex").info("detection loop")
        finally:
            if dm_reading:
                dm_reading.kill()

    def update_transfer_iteration(self, reset=False):
        parser = configparser.RawConfigParser()
        file_path = os.path.dirname(self.calibration_file) + "/transfer_iteration.cfg"
        parser.read(file_path)
        if reset:
            iter_nb = 0
        else:
            iter_nb = parser.getfloat("transfer", "iter") + 1
        parser.set("transfer", "iter", str(iter_nb))
        with open(file_path, "wb") as file:
            parser.write(file)
        logging.getLogger("flex").info(
            "number of sample transfer set to %d" % (int(iter_nb))
        )
        return iter_nb

    def save_loaded_position(self, cell, puck, sample):
        parser = configparser.RawConfigParser()
        file_path = os.path.dirname(self.calibration_file) + "/loaded_position.cfg"
        parser.read(file_path)
        parser.set("position", "cell", str(cell))
        parser.set("position", "puck", str(puck))
        parser.set("position", "sample", str(sample))
        with open(file_path, "wb") as file:
            parser.write(file)
        logging.getLogger("flex").info(
            "loaded position written (%d, %d, %d)" % (cell, puck, sample)
        )

    def reset_loaded_position(self):
        self._loaded_sample = (-1, -1, -1)
        self.save_loaded_position(-1, -1, -1)

    def read_loaded_position(self):
        parser = configparser.RawConfigParser()
        file_path = os.path.dirname(self.calibration_file) + "/loaded_position.cfg"
        parser.read(file_path)
        cell = parser.getfloat("position", "cell")
        puck = parser.getfloat("position", "puck")
        sample = parser.getfloat("position", "sample")
        return (int(cell), int(puck), int(sample))

    def set_cam(self, gripper_type):
        self.cam.stop_cam()
        if gripper_type == 1 or gripper_type == 9:
            acq_time = self.get_detection_param("acq_time", "unipuck")
        if gripper_type == 3:
            acq_time = self.get_detection_param("acq_time", "pin")
        self.cam.prepare(acq_time)

    def do_load_detection(self, gripper_type, ref):
        with BackgroundGreenlets(
            self.detection,
            (str(gripper_type), str(ref)),
            self.sampleStatus,
            ("LoadSampleStatus",),
            self.PSS_light,
            (),
        ) as X:
            return X.execute(self.robot.executeTask, "loadSample", timeout=200)

    def check_gripper_type(self, cell):
        gripper_type = self.get_gripper_type()
        if gripper_type in [1, 3]:
            unipuck_cell = cell in self.unipuck_cells
            if (gripper_type == 1 and not unipuck_cell) or (
                gripper_type == 3 and unipuck_cell
            ):
                logging.getLogger("flex").error("gripper/puck mismatch")
                raise RuntimeError("gripper/puck mismatch")
        else:
            logging.getLogger("flex").error("No or wrong gripper")
            raise RuntimeError("No or wrong gripper")
        return gripper_type

    @notwhenbusy
    def loadSample(self, cell, puck, sample, ref=False):
        to_load = (cell, puck, sample)
        cell, PuckPos, sample, PuckType = self.check_coordinates(cell, puck, sample)
        logging.getLogger("flex").info("#################")
        logging.getLogger("flex").info(
            "Loading sample cell %d, puck %d, sample %d" % (cell, puck, (sample + 1))
        )
        if self.robot.getCachedVariable("data:dioPinOnGonio").getValue() == "true":
            logging.getLogger("flex").error("Sample already on SmartMagnet")
            raise RuntimeError("Sample already on SmartMagnet")

        # set variables at the beginning
        self.set_io("dioEnablePress", True)
        self.robot.setVal3GlobalVariableDouble("nPuckType", str(PuckType))
        self.robot.setVal3GlobalVariableDouble("nLoadPuckPos", str(PuckPos))
        self.robot.setVal3GlobalVariableDouble("nLoadSamplePos", str(sample))
        if self.robot.getCachedVariable("data:dioLoadStReq").getValue() == "true":
            self.set_io("dioLoadStReq", False)
            gevent.sleep(3)
        self.set_io("dioLoadStReq", True)

        gripper_type = self.check_gripper_type(cell)
        self.set_cam(gripper_type)
        self.robot.setVal3GlobalVariableDouble("nGripperType", str(gripper_type))

        success = self.do_load_detection(gripper_type, ref)
        self.set_io("dioLoadStReq", False)
        transfer_iter = self.update_transfer_iteration()
        if success and self.pin_on_gonio():
            self.transfer_counter(success=True)
            self._loaded_sample = to_load
        else:
            self.transfer_counter(success=False)
            # if not self.pin_on_gonio():
            self._loaded_sample = -1, -1, -1

        if gripper_type == 3:
            gevent.spawn(self.defreezeGripper)

        if gripper_type == 1 and transfer_iter >= 16:
            self.homeClear()
            self.defreezeGripper()
            self.update_transfer_iteration(reset=True)
        self.save_loaded_position(*self._loaded_sample)

        return success

    def do_unload_detection(self, gripper_type):
        with BackgroundGreenlets(
            self.detection,
            (str(gripper_type), str(False)),
            self.sampleStatus,
            ("UnloadSampleStatus",),
            self.PSS_light,
            (),
        ) as X:
            return X.execute(self.robot.executeTask, "unloadSample", timeout=200)

    def reset_sample_pos(self):
        self.robot.setVal3GlobalVariableDouble("nUnldPuckPos", "24")
        self.robot.setVal3GlobalVariableDouble("nUnldSamplePos", "16")
        self.robot.setVal3GlobalVariableDouble("nLoadPuckPos", "24")
        self.robot.setVal3GlobalVariableDouble("nLoadSamplePos", "16")

    @notwhenbusy
    def unloadSample(self, cell, puck, sample):
        logging.getLogger("flex").info("#################")
        logging.getLogger("flex").info(
            "Unloading sample cell %d, puck %d, sample %d" % (cell, puck, sample)
        )
        cell, PuckPos, sample, PuckType = self.check_coordinates(cell, puck, sample)
        loaded_puck_pos = self.robot.getVal3GlobalVariableDouble("nLoadPuckPos")
        loaded_sample_pos = self.robot.getVal3GlobalVariableDouble("nLoadSamplePos")
        logging.getLogger("flex").info(
            "previously loaded sample in puck %d, position %d (in VAL3 nomenclature)"
            % (int(loaded_puck_pos), int(loaded_sample_pos))
        )
        if self.robot.getCachedVariable("data:dioPinOnGonio").getValue() == "false":
            logging.getLogger("flex").error("No sample on SmartMagnet")
            raise RuntimeError("No sample on SmartMagnet")
        if loaded_puck_pos != 24 and loaded_sample_pos != 16:
            if PuckPos == loaded_puck_pos:
                if sample != loaded_sample_pos:
                    errstr = (
                        "Previous sample loaded was in %d, %d, %d; hint: reset sample position"
                        % (
                            int(loaded_puck_pos // 3 + 1),
                            int(loaded_puck_pos % 3 + 1),
                            int(loaded_sample_pos + 1),
                        )
                    )
                    logging.getLogger("flex").error(errstr)
                    # raise RuntimeError(errstr)

        # set variables at the beginning
        self.set_io("dioEnablePress", True)
        self.robot.setVal3GlobalVariableDouble("nPuckType", str(PuckType))
        self.robot.setVal3GlobalVariableDouble("nUnldPuckPos", str(PuckPos))
        self.robot.setVal3GlobalVariableDouble("nUnldSamplePos", str(sample))

        if self.robot.getCachedVariable("data:dioUnloadStReq").getValue() == "true":
            self.set_io("dioUnloadStReq", False)
            gevent.sleep(3)
        self.set_io("dioUnloadStReq", True)

        gripper_type = self.check_gripper_type(cell)
        self.set_cam(gripper_type)
        self.robot.setVal3GlobalVariableDouble("nGripperType", str(gripper_type))

        success = self.do_unload_detection(gripper_type)
        self.set_io("dioUnloadStReq", False)
        transfer_iter = self.update_transfer_iteration()

        if success and not self.pin_on_gonio():
            self.transfer_counter(success=True)
            self._loaded_sample = (-1, -1, -1)
        else:
            self.transfer_counter(success=False)
            if not self.pin_on_gonio():
                self._loaded_sample = -1, -1, -1

        self.save_loaded_position(*self._loaded_sample)

        if gripper_type == 3:
            gevent.spawn(self.defreezeGripper)

        if gripper_type == 1 and transfer_iter >= 16:
            gevent.spawn(self.defreezeGripper)
            self.update_transfer_iteration(reset=True)

        return success

    def do_chainedUnldLd_detection(self, gripper_type):
        with BackgroundGreenlets(
            self.detection,
            (str(gripper_type), str(False)),
            self.sampleStatus,
            ("LoadSampleStatus",),
            self.sampleStatus,
            ("UnloadSampleStatus",),
            self.PSS_light,
            (),
        ) as X:
            return X.execute(self.robot.executeTask, "chainedUnldLd", timeout=200)

    @notwhenbusy
    def chainedUnldLd(self, unload, load):
        logging.getLogger("flex").info("#################")
        if not isinstance(unload, list) or not isinstance(load, list):
            logging.getLogger("flex").error("unload/load pos must be list")
            raise TypeError("unload/load pos must be list")
        logging.getLogger("flex").info(
            "Unloading sample cell %d, puck %d, sample %d"
            % (unload[0], unload[1], unload[2])
        )
        logging.getLogger("flex").info(
            "Loading sample cell %d, puck %d, sample %d" % (load[0], load[1], load[2])
        )
        if self.robot.getCachedVariable("data:dioPinOnGonio").getValue() == "false":
            logging.getLogger("flex").error("No sample on SmartMagnet")
            raise RuntimeError("No sample on SmartMagnet")

        unload_cell = unload[0]
        unload_puck = unload[1]
        unload_sample = unload[2]
        load_cell = load[0]
        load_puck = load[1]
        load_sample = load[2]
        unload_cell, unload_PuckPos, unload_sample, unload_PuckType = self.check_coordinates(
            unload_cell, unload_puck, unload_sample
        )
        load_cell, load_PuckPos, load_sample, load_PuckType = self.check_coordinates(
            load_cell, load_puck, load_sample
        )
        if unload_PuckType != load_PuckType:
            logging.getLogger("flex").error(
                "unload and load puck types must be identical"
            )
            raise ValueError("unload and load puck types must be identical")
        loaded_puck_pos = self.robot.getVal3GlobalVariableDouble("nLoadPuckPos")
        loaded_sample_pos = self.robot.getVal3GlobalVariableDouble("nLoadSamplePos")
        logging.getLogger("flex").info(
            "previously loaded sample in puck %d, position %d (in VAL3 nomenclature)"
            % (int(loaded_puck_pos), int(loaded_sample_pos))
        )
        if loaded_puck_pos != 24 and loaded_sample_pos != 16:
            if unload_PuckPos == loaded_puck_pos:
                if unload_sample != loaded_sample_pos:
                    errstr = (
                        "Previous sample loaded was in %d, %d, %d; hint: reset sample position"
                        % (
                            int(loaded_puck_pos // 3 + 1),
                            int(loaded_puck_pos % 3 + 1),
                            int(loaded_sample_pos + 1),
                        )
                    )
                    logging.getLogger("flex").error(errstr)
                    # raise RuntimeError(errstr)

        # set variables at the beginning
        self.set_io("dioEnablePress", True)
        self.robot.setVal3GlobalVariableDouble("nPuckType", str(unload_PuckType))
        self.robot.setVal3GlobalVariableDouble("nUnldPuckPos", str(unload_PuckPos))
        self.robot.setVal3GlobalVariableDouble("nUnldSamplePos", str(unload_sample))
        self.robot.setVal3GlobalVariableDouble("nLoadPuckPos", str(load_PuckPos))
        self.robot.setVal3GlobalVariableDouble("nLoadSamplePos", str(load_sample))

        if self.robot.getCachedVariable("data:dioUnloadStReq").getValue() == "true":
            self.set_io("dioUnloadStReq", False)
            gevent.sleep(3)
        self.set_io("dioUnloadStReq", True)

        gripper_type = self.check_gripper_type(unload_cell)
        self.set_cam(gripper_type)
        self.robot.setVal3GlobalVariableDouble("nGripperType", str(gripper_type))

        success = self.do_chainedUnldLd_detection(gripper_type)
        self.set_io("dioUnloadStReq", False)
        self.set_io("dioLoadStReq", False)
        transfer_iter = self.update_transfer_iteration()

        if success:
            self.transfer_counter(success=True)
        else:
            self.transfer_counter(success=False)

        nUnldLdState = int(self.get_robot_cache_variable("data:nUnldLdState"))
        if nUnldLdState == 1:
            self._loaded_sample = -1, -1, -1
            self.save_loaded_position(*self._loaded_sample)
        elif nUnldLdState == 2:
            self._loaded_sample = tuple(load)
            self.save_loaded_position(*self._loaded_sample)

        if gripper_type == 3:
            gevent.spawn(self.defreezeGripper)

        if gripper_type == 1 and transfer_iter >= 16:
            gevent.spawn(self.defreezeGripper)
            self.update_transfer_iteration(reset=True)

        return success

    def do_trashSample(self):
        with BackgroundGreenlets(self.PSS_light, ()) as X:
            return X.execute(self.robot.executeTask, "trashSample", timeout=120)

    def trashSample(self):
        logging.getLogger("flex").info("#################")
        if self.robot.getCachedVariable("data:dioPinOnGonio").getValue() == "false":
            logging.getLogger("flex").error("No sample on SmartMagnet")
            raise RuntimeError("No sample on SmartMagnet")

        gripper_type = self.get_gripper_type()
        logging.getLogger("flex").info("Starting trash sample")
        if gripper_type == 3:
            self.homeClear()
            self.poseGripper()
            self.takeGripper(1, defreeze=False)
            self.do_trashSample()
            self.poseGripper()
            self.takeGripper(3)
        else:
            logging.getLogger("flex").info(
                "Trash sample available only with Flipping gripper"
            )

        if self.pin_on_gonio() == False:
            self._loaded_sample = -1, -1, -1
            self.save_loaded_position(*self._loaded_sample)
        logging.getLogger("flex").info("Trash sample finished")

    def sampleStatus(self, status_name):
        while True:
            notify = self.robot.waitNotify(status_name)
            logging.getLogger("flex").info("From Robot: %s %s" % (status_name, notify))

    def do_poseGripper(self):
        with BackgroundGreenlets(self.PSS_light, ()) as X:
            return X.execute(self.robot.executeTask, "poseGripper", timeout=60)

    @notwhenbusy
    def poseGripper(self):
        self.homeClear()
        logging.getLogger("flex").info("Putting the gripper back in tool bank")
        self.onewire.close()
        self.do_poseGripper()
        self.robot.setVal3GlobalVariableDouble("nGripperType", "-1")
        logging.getLogger("flex").info("Gripper back on tool bank")

    def do_takeGripper(self):
        with BackgroundGreenlets(self.PSS_light, ()) as X:
            return X.execute(self.robot.executeTask, "takeGripper", timeout=60)

    @notwhenbusy
    def takeGripper(self, gripper_to_take, defreeze=True):
        logging.getLogger("flex").info("Starting to take gripper on tool bank")
        self.onewire = OneWire(self.ow_port)
        all_unipucks = len(self.unipuck_cells) == 8
        if (gripper_to_take not in [1, 3, 9]) or (
            all_unipucks and gripper_to_take not in [1, 9]
        ):
            logging.getLogger("flex").error("No or wrong gripper")
            raise RuntimeError("No or wrong gripper")
        gripper_type = self.get_gripper_type()
        logging.getLogger("flex").info("Gripper is %s" % str(gripper_type))
        if gripper_type not in [-1, 0, 1, 3, 9]:
            logging.getLogger("flex").error("wrong gripper on arm")
            raise RuntimeError("wrong gripper on arm")
        if gripper_type == -1:
            self.robot.setVal3GlobalVariableBoolean("bGripperIsOnArm", False)
            if gripper_to_take != 1 and gripper_to_take != 3 and gripper_to_take != 9:
                logging.getLogger("flex").error("Wrong gripper")
                raise RuntimeError("Wrong gripper")
            self.robot.setVal3GlobalVariableDouble("nGripperType", str(gripper_to_take))
            self.do_takeGripper()
        else:
            self.robot.setVal3GlobalVariableBoolean("bGripperIsOnArm", True)
            self.robot.setVal3GlobalVariableDouble("nGripperType", str(gripper_type))
        logging.getLogger("flex").info("Gripper on robot")
        logging.getLogger("flex").info("Starting defreezing gripper if needed")
        if defreeze == True:
            self.do_defreezeGripper()
        self.update_transfer_iteration(reset=True)
        logging.getLogger("flex").info("Defreezing gripper finished")

    def get_gripper_type(self):
        curr_type = -1
        if (
            self.get_robot_cache_variable("data:dioFlipGonPos")
            != self.get_robot_cache_variable("data:dioFlipDwPos")
        ) or int(self.get_robot_cache_variable("data:aioGripperTemp")) < 3000:
            iter = 0
            previous_type = self.onewire.read()[1]
            for i in range(0, 20):
                gevent.sleep(0.1)
                curr_type = self.onewire.read()[1]
                if curr_type in [1, 3, 9]:
                    return curr_type
            if curr_type == -1:
                # if gripper is present but not defined (pb with 1-wire) return 0
                curr_type = 0
        return curr_type

    @notwhenbusy
    def changeGripper(self, gripper_to_take=1, user_mode=True):
        gripper_type = self.get_gripper_type()
        if gripper_type in [1, 3, 9]:
            logging.getLogger("flex").info("first pose gripper %d" % gripper_type)
            self.poseGripper()
            if user_mode == False:
                self.takeGripper(int(gripper_to_take))
            else:
                if gripper_type == 1:
                    self.takeGripper(3)
                elif gripper_type == 3:
                    self.takeGripper(1)
                else:
                    logging.getLogger("flex").error("gripper left unknown")
                    raise RuntimeError("gripper left unknown")
        elif gripper_type == -1:
            logging.getLogger("flex").info(
                "No gripper on arm taking gripper %d" % gripper_to_take
            )
            self.takeGripper(int(gripper_to_take))
        else:
            logging.getLogger("flex").error("Wrong gripper on arm")
            raise RuntimeError("Wrong gripper on arm")

    def yag_pos(self):
        x = self.robot.getVal3GlobalVariableDouble("trsfYagMove.x")
        rz = self.robot.getVal3GlobalVariableDouble("trsfYagMove.rz")
        logging.getLogger("flex").info(
            "YAG focus and rotation: %s, %s" % (str(x), str(rz))
        )
        return x, rz

    def yag_reset(self):
        logging.getLogger("flex").info("reset Yag positions")
        self.swap_gripper = False
        self.robot.setVal3GlobalVariableDouble("trsfYagMove.x", 0)
        self.robot.setVal3GlobalVariableDouble("trsfYagMove.y", 0)
        self.robot.setVal3GlobalVariableDouble("trsfYagMove.z", 0)
        self.robot.setVal3GlobalVariableDouble("trsfYagMove.rx", 0)
        self.robot.setVal3GlobalVariableDouble("trsfYagMove.ry", 0)
        self.robot.setVal3GlobalVariableDouble("trsfYagMove.rz", 0)

    def do_yag_in(self):
        with BackgroundGreenlets(self.PSS_light, ()) as X:
            return X.execute(self.robot.executeTask, "yag_in", timeout=90)

    def yag_in(self):
        logging.getLogger("flex").info("Starting YAG in")
        if self.robot.getCachedVariable("data:dioPinOnGonio").getValue() == "true":
            logging.getLogger("flex").error("Sample on SmartMagnet")
            raise RuntimeError("Sample on SmartMagnet")
        self.yag_reset()
        gripper_type = self.get_gripper_type()
        if gripper_type == 1:
            logging.getLogger("flex").info("Change gripper")
            self.swap_gripper = True
            self.changeGripper()
            self.do_yag_in()
        elif gripper_type == 3:
            self.do_yag_in()
        else:
            logging.getLogger("flex").info("Please change gripper")
            return
        logging.getLogger("flex").info("YAG in done")

    def do_yag_out(self):
        with BackgroundGreenlets(self.PSS_light, ()) as X:
            return X.execute(self.robot.executeTask, "yag_out", timeout=90)

    def yag_out(self):
        logging.getLogger("flex").info("Starting YAG out")
        self.do_yag_out()
        if self.swap_gripper is True:
            self.changeGripper()
        self.yag_reset()
        logging.getLogger("flex").info("YAG out done")

    def do_yag_focus(self):
        with BackgroundGreenlets(self.PSS_light, ()) as X:
            return X.execute(self.robot.executeTask, "yag_move", timeout=20)

    def yag_focus(self, focus=0):
        start_focus = self.robot.getVal3GlobalVariableDouble("trsfYagMove.x")
        focus = float(focus)
        if start_focus == focus:
            logging.getLogger("flex").info("No need to move")
            return
        if (focus < -5) or (focus > 5):
            logging.getLogger("flex").error("focus must be in range -5 and +5 mm")
            raise RuntimeError("angle must be in range -5 and +5 mm")
        logging.getLogger("flex").info(
            "Yag focus is %s, translate to %s" % (str(start_focus), str(focus))
        )
        self.robot.setVal3GlobalVariableDouble("trsfYagMove.x", str(focus))
        self.do_yag_focus()
        logging.getLogger("flex").info("Done")

    def do_yag_rot(self):
        with BackgroundGreenlets(self.PSS_light, ()) as X:
            return X.execute(self.robot.executeTask, "yag_move", timeout=20)

    def yag_rot(self, angle=0):
        start_angle = self.robot.getVal3GlobalVariableDouble("trsfYagMove.rz")
        angle = float(angle)
        if start_angle == angle:
            logging.getLogger("flex").info("No need to move")
            return
        if (angle < -90) or (angle > 90):
            logging.getLogger("flex").error(
                "angle must be in range -90 and +90 degrees"
            )
            raise RuntimeError("angle must be in range -90 and +90 degrees")
        logging.getLogger("flex").info(
            "Yag rotation is %s, rotate to %s" % (str(start_angle), str(angle))
        )
        self.robot.setVal3GlobalVariableDouble("trsfYagMove.rz", str(angle))
        self.do_yag_rot()
        logging.getLogger("flex").info("Done")

    def spine_gripper_center_detection(self):
        acq_time = self.get_detection_param("acq_time", "pin")
        image = self.waiting_for_image(acq_time=acq_time, timeout=60)
        # roi_left = [[300,0], [500, 100]]
        roi_left = self.get_detection_param("spine_gripper_center", "roi_left")
        # roi_right = [[800,0], [1000,100]]
        roi_right = self.get_detection_param("spine_gripper_center", "roi_right")
        left_edge = self.cam.vertical_edge(image, roi_left)
        right_edge = self.cam.vertical_edge(image, roi_right)
        logging.getLogger("flex").info(
            "left edge %s, right edge %s" % (str(left_edge), str(right_edge))
        )
        center = (left_edge + right_edge) / 2.
        # roi_bottom = [[500,450], [800,650]]
        roi_bottom = self.get_detection_param("spine_gripper_center", "roi_bottom")
        bottom_edge = self.cam.horizontal_edge(image, roi_bottom)
        logging.getLogger("flex").info(
            "center is %s bottom of the gripper is %s" % (str(center), str(bottom_edge))
        )
        return center, bottom_edge

    def spine_gripper_centering(
        self,
        width_center1,
        height_bottom1,
        width_center2,
        height_bottom2,
        width_center3,
        height_bottom3,
    ):
        logging.getLogger("flex").info(
            "width: center 1 %s, center 2 %s, center 3 %s"
            % (str(width_center1), str(width_center2), str(width_center3))
        )
        logging.getLogger("flex").info(
            "height: center 1 %s, center 2 %s, center 3 %s"
            % (str(height_bottom1), str(height_bottom2), str(height_bottom3))
        )
        # angle in degrees between the plan (x,y) of the robot and the plan of the camera
        angle_deg = 130.
        angle_rad = math.pi * angle_deg / 180.
        Xoffset = (
            (width_center1 + width_center3) / 2. - width_center1
        ) / self.cam.pixels_per_mm
        Yoffset = (
            (width_center1 + width_center3) / 2. - width_center2
        ) / self.cam.pixels_per_mm
        gripper_Xoffset = -math.cos(angle_rad) * Yoffset - math.sin(angle_rad) * Xoffset
        gripper_Yoffset = math.cos(angle_rad) * Xoffset - math.sin(angle_rad) * Yoffset
        average_height_bottom = (height_bottom1 + height_bottom2 + height_bottom3) / 3.0
        gripper_Zoffset = (
            average_height_bottom - self.cam.image_height / 2.0
        ) / self.cam.pixels_per_mm
        logging.getLogger("flex").info(
            "Spine gripper offset X %s, Y %s, Z %s"
            % (str(gripper_Xoffset), str(gripper_Yoffset), str(gripper_Zoffset))
        )
        if abs(gripper_Xoffset) < 1 or abs(gripper_Yoffset) < 1:
            self.robot.setVal3GlobalVariableBoolean("bImageProcEnded", True)
            self.robot.execute(
                "data:tSpine.trsf.x = data:tSpine.trsf.x + (%s)" % str(gripper_Xoffset)
            )
            self.robot.execute(
                "data:tSpine.trsf.y = data:tSpine.trsf.y + (%s)" % str(gripper_Yoffset)
            )
            self.robot.execute(
                "data:tSpine.trsf.z = data:tSpine.trsf.z + (%s)" % str(gripper_Zoffset)
            )

        else:
            logging.getLogger("flex").error("gripper offsets are wrong")
            raise RuntimeError("gripper offsets are wrong")

    def flipping_gripper_height_detections(self):
        acq_time = self.get_detection_param("acq_time", "pin")
        image = self.waiting_for_image(acq_time=acq_time, timeout=60)
        # roi_dewar = [[0,150], [250,550]]
        roi_dewar = self.get_detection_param("flipping_gripper_height", "roi_dewar")
        image_dewar_height = self.cam.horizontal_edge(image, roi_dewar)
        logging.getLogger("flex").info(
            "image height in dewar orientation %s"
            % str(self.cam.horizontal_edge(image, roi_dewar))
        )
        height_dewar = (
            image_dewar_height - self.cam.image_height / 2.0
        ) / self.cam.pixels_per_mm
        logging.getLogger("flex").info(
            "height to middle of the image %s" % str(height_dewar)
        )
        self.robot.execute("data:pTemp = here(flange,world)")
        flipping_z_robot = self.robot.getVal3GlobalVariableDouble("pTemp.trsf.z")
        logging.getLogger("flex").info("from robot z is %s" % str(flipping_z_robot))
        calib_z_robot = self.config.getfloat("Calibration", "z")
        logging.getLogger("flex").info("from reference %s" % str(calib_z_robot))
        diff_calib_flipping = (calib_z_robot - flipping_z_robot) - height_dewar
        flipping_gripper_z_dewar = (
            self.robot.getVal3GlobalVariableDouble("tCalibration.trsf.z")
            - diff_calib_flipping
        )
        logging.getLogger("flex").info(
            "error in Z in the dewar orientation %s" % str(diff_calib_flipping)
        )
        self.robot.setVal3GlobalVariableBoolean("bImageProcEnded", True)

        acq_time = self.get_detection_param("acq_time", "pin")
        image = self.waiting_for_image(acq_time=acq_time, timeout=60)
        # roi_gonio = [[0,150], [250,550]]
        roi_gonio = self.get_detection_param("flipping_gripper_height", "roi_gonio")
        image_gonio_height = self.cam.horizontal_edge(image, roi_gonio)
        logging.getLogger("flex").info(
            "image height in gonio orientation %s" % str(image_gonio_height)
        )
        height_gonio = (
            image_gonio_height - self.cam.image_height / 2.0
        ) / self.cam.pixels_per_mm
        logging.getLogger("flex").info(
            "height to the middle of the image %s" % str(height_gonio)
        )
        self.robot.execute("data:pTemp = here(flange,world)")
        flipping_z_robot = self.robot.getVal3GlobalVariableDouble("pTemp.trsf.z")
        logging.getLogger("flex").info("from robot z is %s" % str(flipping_z_robot))
        logging.getLogger("flex").info("from reference %s" % str(calib_z_robot))
        diff_calib_flipping = (calib_z_robot - flipping_z_robot) - height_gonio
        flipping_gripper_z_gonio = (
            self.robot.getVal3GlobalVariableDouble("tCalibration.trsf.z")
            - diff_calib_flipping
        )
        logging.getLogger("flex").info(
            "error in Z at the gonio %s" % str(diff_calib_flipping)
        )

        logging.getLogger("flex").info(
            "Vertical correction at dewar %s, at gonio %s"
            % (str(height_dewar), str(height_gonio))
        )
        if abs(height_dewar) < 5 and abs(height_gonio) < 5:
            logging.getLogger("flex").info(
                "Correction flipping gripper in Z in Dewar orientation %s, in gonio orientation %s"
                % (str(flipping_gripper_z_dewar), str(flipping_gripper_z_gonio))
            )
            self.robot.execute(
                "data:tFlippingDewar.trsf.z = (%s)" % str(flipping_gripper_z_dewar)
            )
            self.robot.execute(
                "data:tFlippingGonio.trsf.z = (%s)" % str(flipping_gripper_z_gonio)
            )
            self.robot.setVal3GlobalVariableBoolean("bImageProcEnded", True)
        else:
            logging.getLogger("flex").error("Vertical correction too high")
            raise RuntimeError("Vertical correction too high")

    def stallion_center_detection(self):
        acq_time = self.get_detection_param("acq_time", "pin")
        image = self.waiting_for_image(acq_time=acq_time, timeout=60)
        # roi_left = [[300,50], [600,400]]
        roi_left = self.get_detection_param("stallion_center", "roi_left")
        # roi_right = [[600,50], [900,400]]
        roi_right = self.get_detection_param("stallion_center", "roi_right")
        left_edge = self.cam.vertical_edge(image, roi_left)
        right_edge = self.cam.vertical_edge(image, roi_right)
        logging.getLogger("flex").info(
            "Stallion left edge %s, right edge %s" % (str(left_edge), str(right_edge))
        )
        center = (left_edge + right_edge) / 2.
        return center

    def stallion_centering(self, center1, center2, center3):
        logging.getLogger("flex").info(
            "center 1 %s, center 2 %s, center 3 %s"
            % (str(center1), str(center2), str(center3))
        )
        # angle in degrees between the plan (x,y) of the robot and the plan of the camera
        angle_deg = 130.
        angle_rad = math.pi * angle_deg / 180.
        Xoffset = ((center1 + center3) / 2.0 - center1) / self.cam.pixels_per_mm
        Yoffset = ((center1 + center3) / 2.0 - center2) / self.cam.pixels_per_mm
        stallion_Xoffset = (
            -math.cos(angle_rad) * Yoffset - math.sin(angle_rad) * Xoffset
        )
        stallion_Yoffset = math.cos(angle_rad) * Xoffset - math.sin(angle_rad) * Yoffset
        logging.getLogger("flex").info(
            "stallion offset in X %s, in Y %s"
            % (str(stallion_Xoffset), str(stallion_Yoffset))
        )
        if abs(stallion_Xoffset) < 2 and abs(stallion_Yoffset) < 2:
            if (
                self.robot.getCachedVariable("data:dioFlipDwPos").getValue() == "true"
                and self.robot.getCachedVariable("data:dioFlipGonPos").getValue()
                == "false"
            ):
                logging.getLogger("flex").info(
                    "X,Y calibration done for DW orientation"
                )
                self.robot.execute(
                    "data:tFlippingDewar.trsf.x = data:tFlippingDewar.trsf.x + (%s)"
                    % str(stallion_Xoffset)
                )
                self.robot.execute(
                    "data:tFlippingDewar.trsf.y = data:tFlippingDewar.trsf.y + (%s)"
                    % str(stallion_Yoffset)
                )
                self.robot.setVal3GlobalVariableBoolean("bImageProcEnded", True)
            elif (
                self.robot.getCachedVariable("data:dioFlipDwPos").getValue() == "false"
                and self.robot.getCachedVariable("data:dioFlipGonPos").getValue()
                == "true"
            ):
                logging.getLogger("flex").info(
                    "X,Y calibration done for gonio orientation"
                )
                self.robot.execute(
                    "data:tFlippingGonio.trsf.x = data:tFlippingGonio.trsf.x + (%s)"
                    % str(stallion_Xoffset)
                )
                self.robot.execute(
                    "data:tFlippingGonio.trsf.y = data:tFlippingGonio.trsf.y + (%s)"
                    % str(stallion_Yoffset)
                )
                self.robot.setVal3GlobalVariableBoolean("bImageProcEnded", True)
            else:
                logging.getLogger("flex").error(
                    "stallion centering not in dewar or gonio orientation"
                )
                raise RuntimeError(
                    "stallion centering not in dewar or gonio orientation"
                )

    def ball_center_detection(self):
        acq_time = self.get_detection_param("acq_time", "vial")
        image = self.waiting_for_image(acq_time=acq_time, timeout=60)
        # roi = [[300,200],[1100,800]]
        roi = self.get_detection_param("ball_center", "roi")
        x_center, y_center, rad1, rad2 = self.cam.fitEllipse(image, roi)
        logging.getLogger("flex").info(
            "ball center in X %s, in Y %s, radius 1 %s, radius %s"
            % (str(x_center), str(y_center), str(rad1), str(rad2))
        )
        if abs(rad1 - rad2) > 20:
            logging.getLogger("flex").error("ellipse radii are too different")
            raise RuntimeError("ellipse radii are too different")
        radius = (rad1 + rad2) / 2.0
        return x_center, y_center, radius

    def ball_centering(
        self,
        width_center1,
        height_center1,
        radius1,
        width_center2,
        height_center2,
        radius2,
        width_center3,
        height_center3,
        radius3,
    ):
        logging.getLogger("flex").info(
            "width : center 1 %s, center 2 %s, center 3 %s"
            % (str(width_center1), str(width_center2), str(width_center3))
        )
        logging.getLogger("flex").info(
            "height: center 1 %s, center 2 %s, center 3 %s"
            % (str(height_center1), str(height_center2), str(height_center3))
        )
        logging.getLogger("flex").info(
            "radius 1 %s, radius 2 %s, radius 3 %s"
            % (str(radius1), str(radius2), str(radius3))
        )
        angle_deg = self.get_detection_param("ball_center", "ref_angle")
        angle_rad = math.pi * angle_deg / 180.
        Xoffset = (width_center1 + width_center3) / 2. - width_center1
        Yoffset = (width_center1 + width_center3) / 2. - width_center2
        gripper_Xoffset = (
            -math.cos(angle_rad) * Yoffset - math.sin(angle_rad) * Xoffset
        ) / self.cam.pixels_per_mm
        gripper_Yoffset = (
            math.cos(angle_rad) * Xoffset - math.sin(angle_rad) * Yoffset
        ) / self.cam.pixels_per_mm
        average_radius = (radius1 + radius2 + radius3) / 3.0
        average_height_center = (height_center1 + height_center2 + height_center3) / 3.0
        logging.getLogger("flex").info(
            "average height %s average radius %s"
            % (str(average_height_center), str(average_radius))
        )
        gripper_Zoffset = (
            average_radius + average_height_center - self.cam.image_height / 2.0
        ) / self.cam.pixels_per_mm
        # if gripper above the middle of the image the correction is <0 as it is in JLib
        logging.getLogger("flex").info(
            "Calibration gripper offset in X %s, in Y %s, in Z %s"
            % (str(gripper_Xoffset), str(gripper_Yoffset), str(gripper_Zoffset))
        )
        if (
            abs(gripper_Xoffset) < 1
            or abs(gripper_Yoffset) < 1
            or abs(gripper_Zoffset) < 1
        ):
            self.robot.execute(
                "data:tCalibration.trsf.x = data:tCalibration.trsf.x + (%s)"
                % str(gripper_Xoffset)
            )
            self.robot.execute(
                "data:tCalibration.trsf.y = data:tCalibration.trsf.y + (%s)"
                % str(gripper_Yoffset)
            )
            self.robot.execute(
                "data:tCalibration.trsf.z = data:tCalibration.trsf.z + (%s)"
                % str(gripper_Zoffset)
            )
            self.robot.execute("data:pTemp = here(flange,world)")
            self.robot.setVal3GlobalVariableBoolean("bImageProcEnded", True)
        else:
            logging.getLogger("flex").error("gripper offsets are wrong")
            raise RuntimeError("gripper offsets are wrong")

    def save_translation(self):
        logging.getLogger("flex").info("Starting save translation")
        tCalib = str(self.robot.getVal3GlobalVariableDouble("pTemp.trsf.z"))
        logging.getLogger("flex").info(
            "Translation calibration from robot %s" % str(tCalib)
        )
        if tCalib == "110.0":
            logging.getLogger("flex").error("problem with getVal3GlobalVariableDouble")
            raise RuntimeError("problem with getVal3GlobalVariableDouble")

        saved_file_path = (
            os.path.splitext(self.calibration_file)[0] + os.path.extsep + "sav"
        )
        try:
            shutil.copy(file_path, saved_file_path)
        except IOError:
            logging.getLogger("flex").info("No such file %s" % file_path)
        self.config.set("Calibration", "z", str(tCalib))
        with open(file_path, "wb") as file:
            self.config.write(file)
        logging.getLogger("flex").info("file written")
        self.robot.setVal3GlobalVariableBoolean("bImageProcEnded", True)

    def calib_detection(self, gripper_type):
        centers = []
        while True:
            notify = self.robot.waitNotify("ImageProcessing")
            logging.getLogger("flex").info("notify %s" % notify)
            if (
                notify == "TakeFlippingGripperCalibrationStallion_Z"
                and int(gripper_type) == 3
            ):
                logging.getLogger("flex").info(
                    "calculation of height (Dewar and Gonio positions)"
                )
                self.flipping_gripper_height_detections()
            if notify.startswith("GripperCalibration"):
                if int(gripper_type) == 1:
                    logging.getLogger("flex").info("start gripper center detection")
                    centers.append(self.spine_gripper_center_detection())
                    logging.getLogger("flex").info(
                        "number of items in center %d" % len(centers)
                    )
                if int(gripper_type) == 3:
                    centers.append(self.stallion_center_detection())
                if int(gripper_type) == 9:
                    logging.getLogger("flex").info("start gripper center detection")
                    centers.append(self.ball_center_detection())
                    logging.getLogger("flex").info(
                        "number of items in center %d" % len(centers)
                    )
            if notify == "GetTranslation" and int(gripper_type) == 9:
                logging.getLogger("flex").info("Get translation")
                self.save_translation()
            if int(gripper_type) == 1 and len(centers) == 3:
                logging.getLogger("flex").info(
                    "calculating 3-click centering with %s" % str(centers)
                )
                centers_list = itertools.chain(*centers)
                logging.getLogger("flex").info("center list %s" % str(centers_list))
                self.spine_gripper_centering(*centers_list)
                centers = []
            if int(gripper_type) == 3 and len(centers) == 3:
                logging.getLogger("flex").info(
                    "calculating 3-click centering with %s" % str(centers)
                )
                self.stallion_centering(*centers)
                centers = []
            if int(gripper_type) == 9 and len(centers) == 3:
                logging.getLogger("flex").info("calculating 3-click centering")
                centers_list = itertools.chain(*centers)
                logging.getLogger("flex").info("center list %s" % str(centers_list))
                self.ball_centering(*centers_list)
                centers = []

    def do_calib_detection(self, gripper_type):
        with BackgroundGreenlets(
            self.calib_detection, (str(gripper_type)), self.PSS_light, ()
        ) as X:
            return X.execute(self.robot.executeTask, "gripperCalib", timeout=200)

    @notwhenbusy
    def gripperCalib(self):
        logging.getLogger("flex").info("Starting calibration tool")
        gripper_type = self.get_gripper_type()
        if gripper_type in [1, 3, 9]:
            self.robot.setVal3GlobalVariableDouble("nGripperType", str(gripper_type))
            self.set_cam(gripper_type)
        else:
            logging.getLogger("flex").error("Wrong gripper")
            raise RuntimeError("Wrong gripper")
        self.do_calib_detection(gripper_type)
        logging.getLogger("flex").info("Calibration finished")

    @notwhenbusy
    def disableDewar(self):
        self.robot.executeTask("disableDewar", timeout=5)
        logging.getLogger("flex").info("Dewar disable")

    @notwhenbusy
    def stopDewar(self):
        self.robot.executeTask("stopDewar", timeout=10)
        logging.getLogger("flex").info("Dewar stop")

    def savedata(self):
        self.robot.executeTask("savedata", timeout=5)
        logging.getLogger("flex").info("VAL3 library saved")

    def do_gonioAlign(self, timeout):
        with BackgroundGreenlets(self.PSS_light, ()) as X:
            return X.execute(self.robot.executeTask, "gonioAlignment", timeout)

    @notwhenbusy
    def gonioAlignment(self):
        logging.getLogger("flex").info(
            "Starting calibration of the SmartMagnet position"
        )
        gripper_type = self.get_gripper_type()
        if gripper_type != 9:
            logging.getLogger("flex").error("Need calibration gripper")
            raise RuntimeError("Need calibration gripper")
        self.set_io("dioUnloadStReq", True)
        self.do_gonioAlign(200)
        logging.getLogger("flex").info(
            "calibration of the SmartMagnet position finished"
        )
        self.set_io("dioUnloadStReq", False)

    def do_dewar_align(self, timeout):
        with BackgroundGreenlets(self.PSS_light, ()) as X:
            return X.execute(self.robot.executeTask, "autoAlignment", timeout=timeout)

    @notwhenbusy
    def dewarAlignment(self, cell="all"):
        logging.getLogger("flex").info("Starting calibration of the Dewar position")
        gripper_type = self.get_gripper_type()
        if gripper_type != 9:
            logging.getLogger("flex").error("Need calibration gripper")
            raise RuntimeError("Need calibration gripper")
        # self.defreezeGripper()
        if cell == "all":
            for i in range(0, 22, 3):
                self.robot.setVal3GlobalVariableDouble("nLoadPuckPos", str(i))
                self.do_dewar_align(1000)
        elif cell in range(1, 9):
            self.robot.setVal3GlobalVariableDouble("nLoadPuckPos", str((cell - 1) * 3))
            self.do_dewar_align(200)
        else:
            logging.getLogger("flex").error("Wrong cell (default all or 1-8)")
            raise RuntimeError("Wrong cell (default all or 1-8)")
        logging.getLogger("flex").info("calibration of the Dewar position finished")

    def get_phases(self, cell, frequency):
        logging.getLogger("flex").info(
            "Get phases on cell %d at %s Hz" % (cell, str(frequency))
        )
        channel = self.proxisense.selectTrioSlot(cell)
        self.proxisense.set_frequency(frequency)
        self.proxisense.deGauss()
        phase_puck1, phase_puck2, phase_puck3 = self.proxisense.getPhaseShift()
        logging.getLogger("flex").info(
            "phases at %s Hz for puck 1 %s, puck 2 %s, puck 3 %s"
            % (str(frequency), str(phase_puck1), str(phase_puck2), str(phase_puck3))
        )
        return [phase_puck1, phase_puck2, phase_puck3]

    def find_ref(self, frequency, cell):
        ref = self.proxisense.get_config(frequency)
        logging.getLogger("flex").info(
            "Phases reference at %sHz in cell %s" % (str(frequency), str(cell))
        )
        section = "Cell%d" % int(cell)
        i = 0
        for list in ref:
            if list[0] == section:
                rank = i
                # logging.getLogger('flex').info("Found the reference in %s" %str(list[0]))
                break
            if list == ref[-1:]:
                logging.getLogger("flex").error("Reference not found")
                raise RuntimeError("Reference not found")
            i += 1
        nb_puckType = len(ref) / (8 * 3)
        ref_phase = []
        ref_puckType = []
        for i in range(0, nb_puckType):
            ref_phase.append(
                [
                    ref[rank + (3 * i)][2],
                    ref[rank + 1 + (3 * i)][2],
                    ref[rank + 2 + (3 * i)][2],
                ]
            )
            ref_puckType.append(str(ref[rank + (3 * i)][1]).split("_")[0])
        logging.getLogger("flex").info(
            "Phases reference %s for type %s" % (str(ref_phase), str(ref_puckType))
        )
        return ref_phase, ref_puckType

    def get_tolerance(self, frequency):
        tolerance = []
        parser = configparser.RawConfigParser()
        file_path = os.path.dirname(self.calibration_file) + "/proxisense_%d.cfg" % int(
            frequency
        )
        parser.read(file_path)
        value = parser.getfloat("Tolerance", "sc3")
        tolerance.append(value)
        value = parser.getfloat("Tolerance", "unipuck")
        tolerance.append(value)
        logging.getLogger("flex").info(
            "tolerance at %sHz for SC3 and Unipuck : %s, %s"
            % (str(frequency), str(tolerance[0]), str(tolerance[1]))
        )
        return tolerance

    def set_threshold(self, cell):
        self.proxisense.selectTrioSlot(cell)
        self.proxisense.set_frequency()
        self.proxisense.deGauss()
        phase_puck1, phase_puck2, phase_puck3 = self.proxisense.getPhaseShift()
        logging.getLogger("flex").info(
            "phase shift puck1, puck2, puck3 : %f, %f, %f"
            % (phase_puck1, phase_puck2, phase_puck3)
        )
        ref_threshold = self.get_detection_param("proxisense", "threshold")
        ref_empty_puck1, ref_empty_puck2, ref_empty_puck3 = self.find_ref(2000, cell)[
            0
        ][1]
        logging.getLogger("flex").info(
            "empty reference puck1, puck2, puck3 : %f, %f, %f"
            % (ref_empty_puck1, ref_empty_puck2, ref_empty_puck3)
        )
        threshold_puck1 = min(phase_puck1 + ref_threshold, ref_empty_puck1 - 0.5)
        threshold_puck2 = min(phase_puck2 + ref_threshold, ref_empty_puck2 - 0.5)
        threshold_puck3 = min(phase_puck3 + ref_threshold, ref_empty_puck3 - 0.5)
        self.proxisense.writeThreshold(cell, 1, threshold_puck1)
        self.proxisense.writeThreshold(cell, 2, threshold_puck2)
        self.proxisense.writeThreshold(cell, 3, threshold_puck3)
        logging.getLogger("flex").info(
            "set threshold in %s for puck1, puck2 and puck3 to %s, %s, %s"
            % (
                str(cell),
                str(threshold_puck1),
                str(threshold_puck2),
                str(threshold_puck3),
            )
        )

    def detect_puck_type(self, cell):
        tolerance_800 = self.get_tolerance(800)
        tolerance_2000 = self.get_tolerance(2000)
        ref_phase_800, ref_puckType = self.find_ref(800, cell)
        ref_phase_2000, ref_puckType = self.find_ref(2000, cell)
        phases_800 = self.get_phases(cell, 800)
        phases_2000 = self.get_phases(cell, 2000)

        if len(ref_phase_800) != len(ref_phase_2000):
            logging.getLogger("flex").error("config files have different length")
            raise RuntimeError("corrupted config files ")
        logging.getLogger("flex").info(
            "%d puck types to checked, including empty" % len(ref_phase_800)
        )

        result = []
        for puckType in range(0, len(ref_phase_800)):
            list_res = []
            for i in range(0, 3):
                diff_800 = abs(ref_phase_800[puckType][i] - phases_800[i])
                diff_2000 = abs(ref_phase_2000[puckType][i] - phases_2000[i])
                logging.getLogger("flex").info(
                    "difference at 800Hz in and 2000Hz: %s, %s"
                    % (str(diff_800), str(diff_2000))
                )
                if (
                    diff_800 < tolerance_800[puckType]
                    and diff_2000 < tolerance_2000[puckType]
                ):
                    # logging.getLogger('flex').info("list append with %s" %str(ref_puckType[puckType]))
                    list_res.append(ref_puckType[puckType])
                else:
                    # logging.getLogger('flex').info("list append with None")
                    list_res.append(None)
            result.append(list_res)
        # logging.getLogger('flex').info("list of detection before filtering %s" %str(result))

        def f(*elements):
            try:
                return [_f for _f in elements if _f][0]
            except IndexError:
                return None

        res = list(map(f, *result))

        parser = configparser.RawConfigParser()
        file_path = os.path.dirname(self.calibration_file) + "/puck_detection.cfg"
        parser.read(file_path)
        parser.set("Cell%d" % cell, "puck1", str(res[0]))
        parser.set("Cell%d" % cell, "puck2", str(res[1]))
        parser.set("Cell%d" % cell, "puck3", str(res[2]))
        with open(file_path, "wb") as file:
            parser.write(file)

        logging.getLogger("flex").info(
            "Puck type in cell %s for puck1, puck2 and puck3: %s, %s and %s"
            % (str(cell), str(res[0]), str(res[1]), str(res[2]))
        )
        return res, phases_800, phases_2000

    def _scanSlot(self, cell):
        pucks_detected, phases_800, phases_2000 = self.detect_puck_type(cell)
        threshold_ct = self.get_detection_param("proxisense", "threshold")
        threshold_us = self.proxisense.ct_to_us(self.proxisense.detection_threshold_ct)
        logging.getLogger("flex").info("threshold (us) %s" % str(threshold_us))
        for i in range(0, 3):
            if pucks_detected[i] == "empty":
                # threshold_puck1 = min(phase_puck1 + ref_threshold, ref_empty_puck1 - 0.5)
                threshold = phases_2000[i] - threshold_us
                self.proxisense.writeThreshold(cell, i + 1, threshold)
                # logging.getLogger('flex').info("Puck not detected")
            else:
                threshold = phases_2000[i] + threshold_us
                self.proxisense.writeThreshold(cell, i + 1, threshold)
                # logging.getLogger('flex').info("Puck detected")
            logging.getLogger("flex").info(
                "Puck%d threshold %s" % ((i + 1), str(threshold))
            )
            self.proxisense.writeThreshold(cell, i + 1, threshold)

    def scanSlot(self, cell="all"):
        if cell != "all" and isinstance(cell, int) and not cell in range(1, 9):
            logging.getLogger("flex").error("Wrong cell number [1-8]")
            raise ValueError("Wrong cell number [1-8]")
        logging.getLogger("flex").info("Starting to scan on cell %s" % (str(cell)))

        if cell is "all":
            cell_start = 1
            cell_stop = 9
        else:
            cell_start = int(cell)
            cell_stop = cell_start + 1

        for cell in range(cell_start, cell_stop):
            logging.getLogger("flex").info("Scan slot cell %d" % cell)
            self._scanSlot(cell)

    def proxisenseCalib(self, cell="all", empty=True):
        if cell != "all" and isinstance(cell, int) and not cell in range(1, 9):
            logging.getLogger("flex").error("Wrong cell number [1-8]")
            raise ValueError("Wrong cell number [1-8]")

        if cell is "all":
            i_start = 1
            i_stop = 9
        else:
            i_start = int(cell)
            i_stop = i_start + 1

        for i in range(i_start, i_stop):
            if empty:
                puckType = "empty"
            else:
                if i in range(1, 8, 2):
                    puckType = "sc3"
                else:
                    puckType = "uni"
            res = self.get_phases(i, 800)
            self.proxisense.set_config(i, 800, puckType, res[0], res[1], res[2])
            res = self.get_phases(i, 2000)
            self.proxisense.set_config(i, 2000, puckType, res[0], res[1], res[2])
