# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
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
import ConfigParser

import logging
from logging.handlers import TimedRotatingFileHandler
flex_logger = logging.getLogger("flex")
flex_logger.setLevel(logging.DEBUG)
flex_log_formatter = logging.Formatter("%(name)s %(levelname)s %(asctime)s %(message)s")
flex_log_handler = None



def grouper(iterable, n):
    args = [iter(iterable)]*n
    return itertools.izip_longest(fillvalue=None, *args)


class BackgroundGreenlets(object):
    def __init__(self, *args):
        self.func_args = args
        self.greenlets = list()

    def kill_greenlets(self, _):
        gevent.killall(self.greenlets)

    def __enter__(self):
        for f, fargs in grouper(self.func_args, 2):
            self.greenlets.append(gevent.spawn(f, *fargs))
        return self

    def execute(self, func, *args, **kwargs):
        self.g = gevent.spawn(func, *args, **kwargs)
        self.g.link(self.kill_greenlets)
        return self.g.get()

    def __exit__(self, *args, **kwargs):
        pass


class flex:

    def __init__(self, name, config):
        self.cs8_ip = config.get('ip')
        self.ueye_id = int(config.get('ueye'))
        self.ow_port = str(config.get('ow_port'))
        self.microscan_hor_ip = config.get('ip_hor')
        self.microscan_vert_ip = config.get('ip_vert')
        self.proxisense_address = config.get('proxisense_address')
        self.calibration_file = config.get('calibration_file')
        self.robot = None
        self.cam = None
        self._loaded_sample = (-1, -1, -1)
        robot.setLogFile(config.get('log_file'))
        robot.setExceptionLogFile(config.get('exception_file'))
        global flex_log_handler
        flex_log_handler = TimedRotatingFileHandler(config.get('flex_log_file'), when='midnight', backupCount=1)
        flex_log_handler.setFormatter(flex_log_formatter)
        flex_logger.addHandler(flex_log_handler)
        logging.getLogger('flex').info("")
        logging.getLogger('flex').info("")
        logging.getLogger('flex').info("")
        logging.getLogger('flex').info("#" * 50)
        logging.getLogger('flex').info("pyFlex Initialised")

    def connect(self):
        logging.getLogger('flex').info("connecting to Flex")
        self.onewire = OneWire(self.ow_port)
        self.cam = Ueye_cam(self.ueye_id)
        self.microscan_hor = dm_reader(self.microscan_hor_ip)
        self.microscan_vert = dm_reader(self.microscan_vert_ip)
        self.proxisense = ProxiSense(self.proxisense_address, os.path.dirname(self.calibration_file))
        self.robot = robot.Robot('flex', self.cs8_ip)
        logging.getLogger('flex').info("Connection done")
        self._loaded_sample = self.read_loaded_position()

    def enablePower(self, state):
        state = bool(state)
        for i in range(0,10):
            self.robot.enablePower(state)
            if state:
                if self.robot.getCachedVariable("IsPowered").getValue() == "true":
                    break
            else:
                if self.robot.getCachedVariable("IsPowered").getValue() == "false":
                    break
            gevent.sleep(1)
        if i == 9 and self.robot.getCachedVariable("IsPowered") is not state:
            msg = "Cannot set power to %s" %str(state)
            logging.getLogger('flex').error(msg)
            raise RuntimeError(msg)
        logging.getLogger('flex').info("Power set to %s" %state)

    def abort(self):
        self.robot.abort()
        logging.getLogger('flex').info("Robot aborted")

    def set_io(self, dio, boolean):
        logging.getLogger('flex').info("Set IO %s to %s" %(dio, str(bool(boolean))))
        if bool(boolean):
            self.robot.execute("data:" + dio + "= true")
        else:
            self.robot.execute("data:" + dio + "= false")

    def gripper_port(self, boolean):
        self.set_io("dioOpenGrpPort", bool(boolean))
        try:
            with gevent.Timeout(10):        
                if bool(boolean) == True:
                    while self.robot.getCachedVariable("data:dioGrpPortIsOp").getValue() == "false":
                        self.robot.waitNotify("data:dioGrpPortIsOp")
                else:
                    while self.robot.getCachedVariable("data:dioGrpPortIsClo").getValue() == "false":
                        self.robot.waitNotify("data:dioGrpPortIsClo")
        except gevent.timeout.Timeout:
            logging.getLogger('flex').error("Timeout on gripper port")

    def robot_port(self, boolean):
        self.set_io("dioOpenRbtPort", bool(boolean))
        try:
            with gevent.Timeout(10):        
                if bool(boolean) == True:
                    while self.robot.getCachedVariable("data:dioRobotPtIsOp").getValue() == "false":
                        self.robot.waitNotify("data:dioRobotPtIsOp")
                else:
                    while self.robot.getCachedVariable("data:dioRobotPtIsClo").getValue() == "false":
                        self.robot.waitNotify("data:dioRobotPtIsClo")
        except gevent.timeout.Timeout:
            logging.getLogger('flex').error("Timeout on robot port")

    def user_port(self, boolean):
        self.set_io("dioOpenUsrPort", bool(boolean))
        try:
            with gevent.Timeout(10):
                if bool(boolean) == True:
                    while self.robot.getCachedVariable("data:dioUsrPtIsOp").getValue() == "false":
                        self.robot.waitNotify("data:dioUsrPtIsOp")
                else:
                    while self.robot.getCachedVariable("data:dioUsrPtIsClo").getValue() == "false":
                        self.robot.waitNotify("data:dioUsrPtIsClo")
        except gevent.timeout.Timeout:
            logging.getLogger('flex').error("Timeout on user port")

    def moveDewar(self, cell, puck=1, user=False):
        logging.getLogger('flex').info("Starting to move the Dewar")
        if isinstance(cell, (int,long)) and isinstance(puck, (int,long)):
            if not cell in range(1,9):
                logging.getLogger('flex').error("Wrong cell number [1-8]")
                raise ValueError("Wrong cell number [1-8]")
        else:
            logging.getLogger('flex').error("Cell must be integer")
            raise ValueError("Cell must be integer")
        if user:
            cell = cell - 3
            if cell <= 0:
                cell = math.fmod(cell,8) + 8
            else:
                cell = math.fmod((cell - 1), 8) + 1
        logging.getLogger('flex').info("Dewar to move to %d" %cell)
        self.robot.setVal3GlobalVariableDouble("nDewarDest", str(3 * (int(cell) - 1)))
        self.robot.executeTask("moveDewar", timeout=60)
        gevent.sleep(0.5) #give time to have DewarInPosition updated
        try:
          with gevent.Timeout(10):
            while self.robot.getCachedVariable("DewarInPosition").getValue() == "false":
                self.robot.waitNotify("DewarInPosition")
        except gevent.timeout.Timeout:
            self.stopDewar()
            logging.getLogger('flex').error("Timeout")
            raise
        logging.getLogger('flex').info("Dewar moved to %d" %cell)

    def get_loaded_sample(self):
        #if self.robot.getCachedVariable("data:dioPinOnGonio").getValue() == 'false':
        #    return -1,-1,-1
        #VAL3_puck = int(self.robot.getVal3GlobalVariableDouble("nLoadPuckPos"))
        #VAL3_sample = int(self.robot.getVal3GlobalVariableDouble("nLoadSamplePos"))
        #cell = VAL3_puck // 3 + 1
        #puck = VAL3_puck % 3 + 1
        #sample = VAL3_sample + 1
        #return cell, puck, sample
        return self._loaded_sample

    def get_cell_position(self):
        if self.robot.getCachedVariable('DewarInPosition').getValue():
            try:
                VAL3_puck = int(self.robot.getCachedVariable('RequestedDewarPosition').getValue())
            except:
                return None, None
            cell = VAL3_puck // 3 + 1
            puck = VAL3_puck % 3 + 1

            return cell, puck
        return None, None

    def get_user_cell_position(self):
        if self.robot.getCachedVariable('DewarInPosition').getValue():
            try:
                VAL3_puck = int(self.robot.getCachedVariable('RequestedDewarPosition').getValue())
            except:
                return None, None
            cell = ((VAL3_puck // 3 + 3) % 8) + 1 
            return cell
  
    def pin_on_gonio(self):
        value = self.robot.getCachedVariable("data:dioPinOnGonio").getValue() == 'true'
        success = 0
        with gevent.Timeout(3, RuntimeError("SmartMagnet problem: don't know if pin is on gonio.")):
          while True:
              gevent.sleep(0.2)
              new_value = self.robot.getCachedVariable("data:dioPinOnGonio").getValue() == 'true'
              if value == new_value:
                  success += 1
              else:
                  success = 0
              value = new_value
              if success == 2:
                  return new_value

    def arm_is_parked(self):
        return self.robot.getCachedVariable("data:dioArmIsParked").getValue() == 'true'
 
    def ready_for_centring(self):
        if self.pin_on_gonio():
            if self.arm_is_parked():
                return True
        return False
 
    def get_robot_cache_variable(self, varname):
        try:
            return self.robot.getCachedVariable(varname).getValue()
        except Exception:
            return ''

    def homeClear(self):
        logging.getLogger('flex').info("Starting homing")
        gripper_type = self.get_gripper_type()
        if gripper_type not in [-1, 0, 1, 3, 9]:
            logging.getLogger('flex').error("No or wrong gripper")
            raise ValueError("No or wrong gripper")
        self.robot.setVal3GlobalVariableDouble("nGripperType", str(gripper_type))
        if gripper_type == -1:
            self.robot.setVal3GlobalVariableBoolean("bGripperIsOnArm", False)
        else:
            self.robot.setVal3GlobalVariableBoolean("bGripperIsOnArm", True)
        #self.robot.execute("data:dioEnablePress=true")
        self.robot.executeTask("homeClear", timeout=60)
        logging.getLogger('flex').info("Homing done")

    def defreezeGripper(self):
        logging.getLogger('flex').info("Starting defreeze gripper")
        gripper_type = self.get_gripper_type()
        logging.getLogger('flex').info("gripper type %s" %gripper_type)
        if gripper_type not in [-1, 0, 1, 3, 9]:
            logging.getLogger('flex').error("No or wrong gripper")
            raise ValueError("No or wrong gripper")
        if gripper_type == -1:
            self.robot.setVal3GlobalVariableBoolean("bGripperIsOnArm", False)
            self.robot.setVal3GlobalVariableDouble("nGripperType", "0")
        else:
            self.robot.setVal3GlobalVariableBoolean("bGripperIsOnArm", True)
            self.robot.setVal3GlobalVariableDouble("nGripperType", str(gripper_type))
        self.robot.executeTask("defreezeGripper", timeout=90)
        logging.getLogger('flex').info("Defreezing gripper finished")

    def check_coordinates(self, cell, puck, sample):
        if isinstance(cell, (int,long)) and isinstance(puck, (int,long)) and isinstance(sample, (int,long)):
            if not cell in range(1,9):
                logging.getLogger('flex').error("Wrong cell number [1-8]")
                raise ValueError("Wrong cell number [1-8]")
            if not puck in range(1,4):
                logging.getLogger('flex').error("wrong puck number [1-3]")
                raise ValueError("Wrong puck number [1-3]")
            if cell in range(1,9,2):
                puckType = 3
                if not sample in range(1,11):
                    logging.getLogger('flex').error("wrong sample number [1-10]")
                    raise ValueError("wrong sample number [1-10]")
            if cell in range(2,10,2):
                puckType = 2
                if not sample in range(1,17):
                    logging.getLogger('flex').error("wrong sample number [1-16]")
                    raise ValueError("wrong sample number [1-16]")
            puck = 3 * (cell -1) + puck - 1
            sample = sample - 1
            if puck == 23:
                logging.getLogger('flex').error("cannot load/unload from/to recovery puck")
                raise RuntimeError("cannot load/unload from/to recovery puck")
        else:
            logging.getLogger('flex').error("cell, puck and sample must be integer")
            raise ValueError("cell, puck and sample must be integer")
        return cell, puck, sample, puckType

    def waiting_for_image(self, timeout = 60):
        self.cam.prepare()
        prev_imgNb = int(self.cam.control.getImageStatus().LastImageAcquired)
        logging.getLogger('flex').info("Image number %d" %prev_imgNb)
        imgNb = prev_imgNb
        try:
            with gevent.Timeout(timeout):
                while imgNb == prev_imgNb:
                    gevent.sleep(0.05)
                    imgNb = int(self.cam.control.getImageStatus().LastImageAcquired)
        except gevent.timeout.Timeout:
            logging.getLogger('flex').error("Timeout in waiting for image")
            raise
        logging.getLogger('flex').info("image taken number %d" %imgNb)
        prev_imgNb = imgNb
        image = self.cam.BW_image(self.cam.take_snapshot())
        self.cam.image_save(image)
        return image

    def save_ref_image(self, image, filename):
        logging.getLogger('flex').info("Saving the reference file")
        dir = os.path.dirname(self.calibration_file)
        file_path = os.path.join(dir, filename)+".edf"
        old_file_path = os.path.join(dir, filename) + ".old"
        try:
            os.remove(old_file_path)
        except OSError:
            logging.getLogger('flex').info("error in OS command remove")
        try:
            os.rename(file_path, old_file_path)
        except OSError:
            logging.getLogger('flex').info("error in OS command rename")
        logging.getLogger('flex').info("save ref image in %s" %file_path)
        self.cam.image_save(image, dir=dir, prefix=filename)

    def pin_detection(self, gripper_type, ref):
        logging.getLogger('flex').info("Pin detection")
        image = self.waiting_for_image()
        if int(gripper_type) == 1:
            if ref == "True":
                filename = "ref_spine_with_pin"
                self.save_ref_image(image, filename)
            roi = [[800,800], [900,1023]]
            PinIsInGripper = not(self.cam.is_empty(image, roi))
            logging.getLogger('flex').info("Pin is the gripper %s" %str(PinIsInGripper))
            if PinIsInGripper:
                self.robot.setVal3GlobalVariableBoolean("bPinIsInGripper", True)
            roi = [[800,700], [1100,1023]]
            edge = self.cam.vertical_edge(image, roi)
            logging.getLogger('flex').info("Vertical edge of the pin %s" %str(edge))
            if edge is not None:
                sp_ref_file = os.path.join(os.path.dirname(self.calibration_file), "ref_spine_with_pin.edf")
                ref_image = self.cam.image_read(sp_ref_file)
                ref_image_edge = self.cam.vertical_edge(ref_image, roi)
                logging.getLogger('flex').info("edge position on the reference image %s" %str(ref_image_edge))
                distance_from_ref = self.cam.edge_distance(ref_image_edge, edge)
                logging.getLogger('flex').info("distance of the pin from the reference  %s" %str(distance_from_ref))
                if abs(distance_from_ref)  < 0.6:
                    self.robot.setVal3GlobalVariableBoolean("bPinIsOkInGrip", True)
        if int(gripper_type) == 3:
            if ref == "True":
                filename = "ref_flipping_with_pin"
                self.save_ref_image(image, filename)
            logging.getLogger('flex').info("gripper for pin detection is %s" %gripper_type)
            #roi_pin = [[350,200], [630,450]]
            roi_pin = [[200,300], [800,600]]
            PinIsInGripper = not(self.cam.is_empty(image, roi_pin))
            if PinIsInGripper:
                logging.getLogger('flex').info("Pin is in gripper")
                self.robot.setVal3GlobalVariableBoolean("bPinIsInGripper", True)
                edge = self.cam.horizontal_edge(image, roi_pin)
                logging.getLogger('flex').info("Horizontal edge of the pin %s" %str(edge))
                if edge is not None:
                    fp_ref_file = os.path.join(os.path.dirname(self.calibration_file), "ref_flipping_with_pin.edf")
                    ref_image = self.cam.image_read(fp_ref_file)
                    ref_image_edge = self.cam.horizontal_edge(ref_image, roi_pin)
                    logging.getLogger('flex').info("edge position on the reference image %s" %str(ref_image_edge))
                    distance_from_ref = self.cam.edge_distance(self.cam.horizontal_edge(ref_image, roi_pin), edge)
                    logging.getLogger('flex').info("distance of the pin from the reference %s" %str(distance_from_ref))
                    if abs(distance_from_ref)  <= 2.0:
                        self.robot.setVal3GlobalVariableBoolean("bPinIsOkInGrip", True)
                    else:
                        logging.getLogger('flex').error("distance from reference is too high")
                
                roi_gripper = [[0,300], [70,900]]
                if roi_gripper[0][1] != roi_pin[0][1]:
                    logging.getLogger('flex').error("2 rois must be on the same horizontal line from top")
                    raise ValueError("2 rois must be on the same horizontal line from top")
                edge_gripper = self.cam.horizontal_edge(image, roi_gripper)
                edge_pin = self.cam.horizontal_edge(image, roi_pin)
                logging.getLogger('flex').info("horizontal edge of the pin %s and of the gripper %s" %(str(edge_pin), str(edge_gripper)))
                if edge_gripper is not None or edge_pin is not None:
                    distance_pin_gripper = self.cam.edge_distance(edge_pin, edge_gripper)
                    logging.getLogger('flex').info("distance between pin and gripper %s" %str(distance_pin_gripper))
                    # DN must be negative if the pin stands out of the gripper if not VAL3 will care about the error
                    if 0.5 <= abs(distance_pin_gripper) <= 4:
                        self.robot.setVal3GlobalVariableDouble("trsfPutFpGonio.z", str(distance_pin_gripper)) 
                        logging.getLogger('flex').info("distance saved in robot")
                    else:
                        logging.getLogger('flex').error("distance pin gripper is %s should be between 0.5-4mm" %str(abs(distance_pin_gripper)))
                else:
                    logging.getLogger('flex').error("Edge of the gripper or of the pin not found")
                    raise RuntimeError("Edge of the gripper or of the pin not found")
            else:
                logging.getLogger('flex').info("Pin is not in gripper, calling vial detection")
                self.robot.setVal3GlobalVariableBoolean("bPinIsInGripper", False)
                self.robot.setVal3GlobalVariableBoolean("bPinIsOkInGrip", False)
                self.vial_detection(image)

    def vial_center_detection(self):
        image = self.waiting_for_image()
        roi_left = [[0,0],[400,400]]
        roi_right = [[700,0],[1100,400]]
        left_edge =  self.cam.vertical_edge(image, roi_left)
        right_edge = self.cam.vertical_edge(image, roi_right)
        logging.getLogger('flex').info("Vial left edge %s right_edge %s" %(str(left_edge), str(right_edge)))
        center = (left_edge + right_edge) / 2.
        logging.getLogger('flex').info("center %s" %str(center))
        return center

    def vial_centering(self, center_1, center_2, center_3):
        logging.getLogger('flex').info("center 1 %s, center 2 %s, center 3 %s" %(str(center_1), str(center_2), str(center_3)))
        # angle in degrees between the plan (x,y) of the robot and the plan of the camera 
        angle_deg = 130.
        angle_rad = math.pi * angle_deg / 180.
        Xoffset = ((center_1 + center_3) / 2. - center_1) / self.cam.pixels_per_mm
        Yoffset = ((center_1 + center_3) / 2. - center_2) / self.cam.pixels_per_mm
        gripper_Xoffset = (-math.cos(angle_rad) * Yoffset - math.sin(angle_rad) * Xoffset)
        gripper_Yoffset = (math.cos(angle_rad) * Xoffset - math.sin(angle_rad) * Yoffset)
        logging.getLogger('flex').info("Gripper correction in X %s in Y %s" %(str(gripper_Xoffset), str(gripper_Yoffset)))
        if abs(gripper_Xoffset) < 3 or abs(gripper_Yoffset) < 3:
            self.robot.setVal3GlobalVariableDouble("trVialPosCorr.x", str(gripper_Xoffset))
            self.robot.setVal3GlobalVariableDouble("trVialPosCorr.y", str(gripper_Yoffset))
            #DN no watch in Val3 loadFlipping/robot.FpPutVialDew to be done by GP
            self.robot.setVal3GlobalVariableBoolean("bImageProcEnded", True)
        else:
            logging.getLogger('flex').error("Correction is too high")
            raise RuntimeError("Correction is too high")

    def vial_detection(self, image):
        #roi = [[350,600], [650,1023]]
        #roi = [[200,500], [350,1023]]
        roi = [[500,500], [700,1023]]
        VialIsNotInGripper = self.cam.is_empty(image, roi)
        if VialIsNotInGripper:
            logging.getLogger('flex').info("Vial is not in gripper")
            self.robot.setVal3GlobalVariableBoolean("bVialIsInGrip", False)
        else:
            vial_edge = self.cam.horizontal_edge(image, roi)
            logging.getLogger('flex').info("Vial edge position %s" %str(vial_edge))
            fp_ref_file = os.path.join(os.path.dirname(self.calibration_file), "ref_flipping_with_pin.edf")
            ref_image = self.cam.image_read(fp_ref_file)
            roi_ref = [[200,300], [800,600]]
            ref_image_edge = self.cam.horizontal_edge(ref_image, roi_ref)
            logging.getLogger('flex').info("Ref pin edge position %s" %str(ref_image_edge))
            cap_height = 3.0
            ref_vial_edge = cap_height * self.cam.pixels_per_mm + ref_image_edge
            logging.getLogger('flex').info("Reference vial edge position %s" %str(ref_vial_edge))
            if abs(ref_vial_edge - vial_edge) < 70:
                self.robot.setVal3GlobalVariableBoolean("bVialIsInGrip", True) 
                logging.getLogger('flex').info("Vial is in gripper")
            else:
                logging.getLogger('flex').info("Vial edge too different to the reference")
                self.robot.setVal3GlobalVariableBoolean("bVialIsInGrip", False)

    def dm_detection(self, GripperType):
        logging.getLogger('flex').info("Starting Data matrix reading with gripper type %s" %GripperType)
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
        logging.getLogger('flex').info("Data matrix is %s" %dm)

    def detection(self, gripper_type, ref):
        centers = []
        ref_already_saved = False
        dm_reading = None

        try:
            while True:
                notify = self.robot.waitNotify("ImageProcessing") 
                logging.getLogger('flex').info("notify %s with gripper type %s" %(notify, gripper_type))
                if notify == 'PinDetection':
                    if ref == "True" and ref_already_saved == False:
                        self.pin_detection(gripper_type, "True")
                        ref_already_saved = True
                    else:
                        self.pin_detection(gripper_type, "False")
                    logging.getLogger('flex').info("reading data matrix variable")
                    DM_detected = self.robot.getVal3GlobalVariableBoolean("bCodeDetected")
                    if not DM_detected:
                        logging.getLogger('flex').info("read Data Matrix")
                        dm_reading = gevent.spawn(self.dm_detection, gripper_type)
                    else:
                        logging.getLogger('flex').info("DM not needed")
                elif notify.startswith("VialDetection"):
                    logging.getLogger('flex').info("Starting vial center detection")
                    logging.getLogger('flex').info("length of centers list is  %s" %str(len(centers)))
                    vial_center = self.vial_center_detection()
                    logging.getLogger('flex').info("center is at %s" %str(vial_center))
                    centers.append(vial_center)
                    logging.getLogger('flex').info("length of centers list is  %s" %str(len(centers)))
                    if notify.split("_")[1] != str(len(centers)):
                        logging.getLogger('flex').error("image lost in vial detection") 
                        raise RuntimeError("image lost in vial detection")
                    if len(centers) == 3:
                        logging.getLogger('flex').info("Calling Vial centering")
                        self.vial_centering(*centers)
                        centers = []
                else:
                    logging.getLogger('flex').info("detection loop")
        finally:
          if dm_reading:
            dm_reading.kill()

    def do_load_detection(self, gripper_type, ref):
        with BackgroundGreenlets(self.detection, (str(gripper_type), str(ref)), 
                                 self.sampleStatus, ("LoadSampleStatus",)) as X:
            return X.execute(self.robot.executeTask, "loadSample", timeout=200)

    def save_loaded_position(self, cell, puck, sample):
        parser = ConfigParser.RawConfigParser()
        file_path = os.path.dirname(self.calibration_file)+"/loaded_position.cfg"
        parser.read(file_path)
        parser.set("position", "cell", str(cell))
        parser.set("position", "puck", str(puck))
        parser.set("position", "sample", str(sample))
        with open(file_path, 'wb') as file:
            parser.write(file)
        logging.getLogger('flex').info("loaded position written")

    def reset_loaded_position(self):
        self._loaded_sample = (-1, -1, -1)
        self.save_loaded_position(-1, -1, -1)

    def read_loaded_position(self):
        parser = ConfigParser.RawConfigParser()
        file_path = os.path.dirname(self.calibration_file)+"/loaded_position.cfg"
        parser.read(file_path)
        cell = parser.getfloat("position", "cell")
        puck = parser.getfloat("position", "puck")
        sample = parser.getfloat("position", "sample")
        return (int(cell), int(puck), int(sample))

    def loadSample(self, cell, puck, sample, ref=False):
        to_load = (cell, puck, sample)
        cell, PuckPos, sample, PuckType = self.check_coordinates(cell, puck, sample)
        logging.getLogger('flex').info("Loading sample cell %d, puck %d, sample %d" %(cell, puck, (sample + 1)))
        if self.robot.getCachedVariable("data:dioPinOnGonio").getValue() == "true":
            logging.getLogger('flex').error("Sample already on SmartMagnet")
            raise RuntimeError("Sample already on SmartMagnet")

        #set variables at the beginning
        self.robot.setVal3GlobalVariableDouble("nPuckType", str(PuckType))
        self.robot.setVal3GlobalVariableDouble("nLoadPuckPos", str(PuckPos))
        self.robot.setVal3GlobalVariableDouble("nLoadSamplePos", str(sample))

        #Get gripper type
        gripper_type = self.get_gripper_type()
        if gripper_type in [1, 3]:
            if (gripper_type == 1 and cell in range(1,9,2)) or (gripper_type == 3 and cell in range(2,10,2)):
                logging.getLogger('flex').error("gripper/puck mismatch")
                raise RuntimeError("gripper/puck mismatch")
            self.robot.setVal3GlobalVariableDouble("nGripperType", str(gripper_type))
        else:
            logging.getLogger('flex').error("No or wrong gripper")
            raise RuntimeError("No or wrong gripper")

        success = self.do_load_detection(gripper_type, ref)
        if success: 
            self._loaded_sample = to_load
        else:
            if not self.pin_on_gonio():
              self._loaded_sample = -1, -1, -1

        if gripper_type == 3:
            gevent.spawn(self.defreezeGripper)

        self.save_loaded_position(*to_load)
 
        return success

    def do_unload_detection(self, gripper_type):
        with BackgroundGreenlets(self.detection, (str(gripper_type), str(False)), 
                                 self.sampleStatus, ("UnloadSampleStatus",)) as X:
            return X.execute(self.robot.executeTask, "unloadSample", timeout=200)

    def reset_sample_pos(self):
        self.robot.setVal3GlobalVariableDouble("nUnldPuckPos", "24")
        self.robot.setVal3GlobalVariableDouble("nUnldSamplePos", "16")
        self.robot.setVal3GlobalVariableDouble("nLoadPuckPos", "24")
        self.robot.setVal3GlobalVariableDouble("nLoadSamplePos", "16")

    def unloadSample(self, cell, puck, sample):
        logging.getLogger('flex').info("Unloading sample cell %d, puck %d, sample %d" %(cell, puck, sample))
        cell, PuckPos, sample, PuckType = self.check_coordinates(cell, puck, sample)
        loaded_puck_pos = self.robot.getVal3GlobalVariableDouble("nLoadPuckPos")
        loaded_sample_pos = self.robot.getVal3GlobalVariableDouble("nLoadSamplePos")
        logging.getLogger('flex').info("previously loaded sample in puck %d, position %d (in VAL3 nomenclature)" %(int(loaded_puck_pos), int(loaded_sample_pos)))
        if self.robot.getCachedVariable("data:dioPinOnGonio").getValue()  == "false":
            logging.getLogger('flex').error("No sample on SmartMagnet")
            raise RuntimeError("No sample on SmartMagnet")
        if loaded_puck_pos != 24 and loaded_sample_pos != 16:
            if PuckPos ==  loaded_puck_pos:
                if sample != loaded_sample_pos:
                    errstr = "Previous sample loaded was in %d, %d, %d; hint: reset sample position" %(int(loaded_puck_pos // 3 + 1), int(loaded_puck_pos % 3 + 1), int(loaded_sample_pos + 1))
                    logging.getLogger('flex').error(errstr)
                    #raise RuntimeError(errstr)

        #set variables at the beginning
        self.robot.setVal3GlobalVariableDouble("nPuckType", str(PuckType))
        self.robot.setVal3GlobalVariableDouble("nUnldPuckPos", str(PuckPos))
        self.robot.setVal3GlobalVariableDouble("nUnldSamplePos", str(sample))

        #Get gripper type
        gripper_type = self.get_gripper_type()

        if gripper_type in [1, 3]:
            if (gripper_type == 1 and cell in range(1,9,2)) or (gripper_type == 3 and cell in range(2,10,2)):
                logging.getLogger('flex').error("gripper/puck mismatch")
                raise RuntimeError('gripper/puck mismatch')
            self.robot.setVal3GlobalVariableDouble("nGripperType", str(gripper_type))
        else:
            logging.getLogger('flex').error("No or wrong gripper")
            raise RuntimeError("No or wrong gripper")

        success =  self.do_unload_detection(gripper_type)
        if success:
            self._loaded_sample = (-1, -1, -1)
        else:
            if not self.pin_on_gonio():
              self._loaded_sample = -1, -1, -1

        if gripper_type == 3:
            gevent.spawn(self.defreezeGripper)

        self.save_loaded_position(-1,-1,-1)

        return success

    def do_chainedUnldLd_detection(self, gripper_type):
        with BackgroundGreenlets(self.detection, (str(gripper_type), str(False)), 
                                 self.sampleStatus, ("LoadSampleStatus",),
                                 self.sampleStatus, ("UnloadSampleStatus",)) as X:
            return X.execute(self.robot.executeTask, "chainedUnldLd", timeout=200)
 
    def chainedUnldLd(self, unload, load):
        if not isinstance(unload, list) or not isinstance(load, list):
            logging.getLogger('flex').error("unload/load pos must be list")
            raise TypeError("unload/load pos must be list")
        logging.getLogger('flex').info("Unloading sample cell %d, puck %d, sample %d" %(unload[0], unload[1], unload[2]))
        logging.getLogger('flex').info("Loading sample cell %d, puck %d, sample %d" %(load[0], load[1], load[2]))
        if self.robot.getCachedVariable("data:dioPinOnGonio").getValue() == "false":
            logging.getLogger('flex').error("No sample on SmartMagnet")
            raise RuntimeError("No sample on SmartMagnet")

        unload_cell = unload[0]
        unload_puck = unload[1]
        unload_sample = unload[2]
        load_cell = load[0]
        load_puck = load[1]
        load_sample = load[2]
        unload_cell, unload_PuckPos, unload_sample, unload_PuckType = self.check_coordinates(unload_cell, unload_puck, unload_sample)
        load_cell, load_PuckPos, load_sample, load_PuckType = self.check_coordinates(load_cell, load_puck, load_sample)
        if unload_PuckType != load_PuckType:
            logging.getLogger('flex').error("unload and load puck types must be identical")
            raise ValueError("unload and load puck types must be identical")
        loaded_puck_pos = self.robot.getVal3GlobalVariableDouble("nLoadPuckPos")
        loaded_sample_pos = self.robot.getVal3GlobalVariableDouble("nLoadSamplePos")
        logging.getLogger('flex').info("previously loaded sample in puck %d, position %d (in VAL3 nomenclature)" %(int(loaded_puck_pos), int(loaded_sample_pos)))
        if loaded_puck_pos != 24 and loaded_sample_pos != 16:
            if unload_PuckPos ==  loaded_puck_pos:
                if unload_sample != loaded_sample_pos:
                    errstr = "Previous sample loaded was in %d, %d, %d; hint: reset sample position" %(int(loaded_puck_pos // 3 + 1), int(loaded_puck_pos % 3 + 1), int(loaded_sample_pos + 1))
                    logging.getLogger('flex').error(errstr)
                    #raise RuntimeError(errstr)

        #set variables at the beginning
        self.robot.setVal3GlobalVariableDouble("nPuckType", str(unload_PuckType))
        self.robot.setVal3GlobalVariableDouble("nUnldPuckPos", str(unload_PuckPos))
        self.robot.setVal3GlobalVariableDouble("nUnldSamplePos", str(unload_sample))
        self.robot.setVal3GlobalVariableDouble("nLoadPuckPos", str(load_PuckPos))
        self.robot.setVal3GlobalVariableDouble("nLoadSamplePos", str(load_sample))

        #Get gripper type
        gripper_type = self.get_gripper_type()
        if gripper_type in [1, 3]:
            if (gripper_type == 1 and unload_cell in range(1,9,2)) or (gripper_type == 3 and unload_cell in range(2,10,2)):
                logging.getLogger('flex').error("gripper/puck mismatch in unload")
                raise RuntimeError("gripper/puck mismatch in unload")
            if (gripper_type == 1 and load_cell in range(1,9,2)) or (gripper_type == 3 and load_cell in range(2,10,2)):
                logging.getLogger('flex').error("gripper/puck mismatch in load")
                raise RuntimeError("gripper/puck mismatch in load")
            self.robot.setVal3GlobalVariableDouble("nGripperType", str(gripper_type))
        else:
            logging.getLogger('flex').error("Wrong gripper")
            raise RuntimeError("Wrong gripper")

        success =  self.do_chainedUnldLd_detection(gripper_type)
        if success:
            self._loaded_sample = tuple(load)
        else:
            if not self.pin_on_gonio():
              self._loaded_sample = -1, -1, -1
  
        if gripper_type == 3:
            gevent.spawn(self.defreezeGripper)

        self.save_loaded_position(*load)

        return success

    def sampleStatus(self, status_name):
        while True:
            notify = self.robot.waitNotify(status_name)
            logging.getLogger('flex').info("From Robot: %s %s" %(status_name, notify))

    def poseGripper(self):
        self.homeClear()
        logging.getLogger('flex').info("Putting the gripper back in tool bank")
        try:
            self.onewire.close()
            self.robot.executeTask("poseGripper", timeout=30)
        except:
            self.robot.setVal3GlobalVariableDouble("nGripperType", "0")
            logging.getLogger('flex').error("Deposing gripper failed, gripper type unknown")
            raise RuntimeError("Deposing gripper failed, gripper type unknown")
        self.robot.setVal3GlobalVariableDouble("nGripperType", "-1")
        logging.getLogger('flex').info("Gripper back on tool bank")

    def takeGripper(self, gripper_to_take):
        logging.getLogger('flex').info("Starting to take gripper on tool bank")
        self.onewire = OneWire(self.ow_port)
        if gripper_to_take not in [1, 3, 9]:
            logging.getLogger('flex').error("No or wrong gripper")
            raise RuntimeError("No or wrong gripper")
        gripper_type = self.get_gripper_type()
        if gripper_type not in [-1, 0, 1, 3, 9]:
            logging.getLogger('flex').error("wrong gripper on arm")
            raise RuntimeError("wrong gripper on arm")
        if gripper_type == -1:
            self.robot.setVal3GlobalVariableBoolean("bGripperIsOnArm", False)
            if gripper_to_take != 1 and gripper_to_take != 3 and gripper_to_take != 9:
                logging.getLogger('flex').error("Wrong gripper")
                raise RuntimeError("Wrong gripper")
            self.robot.setVal3GlobalVariableDouble("nGripperType", str(gripper_to_take))
            try:
                self.robot.executeTask("takeGripper", timeout=60)
            except:
                logging.getLogger('flex').error("No gripper in bank")
                raise RuntimeError("No gripper in bank")
        else:
            self.robot.setVal3GlobalVariableBoolean("bGripperIsOnArm", True)
            self.robot.setVal3GlobalVariableDouble("nGripperType", str(gripper_type))
        logging.getLogger('flex').info("Gripper on robot")
        logging.getLogger('flex').info("Starting defreezing gripper if needed")
        self.robot.executeTask("defreezeGripper", timeout=60)
        logging.getLogger('flex').info("Defreezing gripper finished")

    def get_gripper_type(self):
        iter = 0
        previous_type = self.onewire.read()[1]
        for i in range(0,10):
            gevent.sleep(0.1)
            curr_type = self.onewire.read()[1]
            if curr_type != previous_type:
                previous_type = curr_type
                iter = 0
            else:
                previous_type = curr_type
                iter += 1
                if iter == 3:
                    break
        return previous_type

    def changeGripper(self, gripper_to_take=1, user_mode=True):
        gripper_type = self.get_gripper_type()
        if gripper_type in [1,3,9]:
            if user_mode == False:
                logging.getLogger('flex').info("first pose gripper %d" %gripper_type)
                self.poseGripper()
                self.takeGripper(int(gripper_to_take))
            else:
                gripper_type = self.get_gripper_type()
                self.poseGripper()
                if gripper_type == 1:
                    self.takeGripper(3)
                elif gripper_type == 3:
                    self.takeGripper(1)
                else:
                    logging.getLogger('flex').error("gripper left unknown")
                    raise RuntimeError("gripper left unknown")            
        elif gripper_type == -1:
            logging.getLogger('flex').info("No gripper on arm taking gripper %d" %gripper_to_take)
            self.takeGripper(int(gripper_to_take))
        else:
            logging.getLogger('flex').error("Wrong gripper on arm")
            raise RuntimeError("Wrong gripper on arm")

    def spine_gripper_center_detection(self):
        image = self.waiting_for_image()
        roi_left = [[300,0], [500, 200]]
        roi_right = [[800,0], [1000,200]]
        left_edge =  self.cam.vertical_edge(image, roi_left)
        right_edge = self.cam.vertical_edge(image, roi_right)
        logging.getLogger('flex').info("left edge %s, right edge %s" %(str(left_edge), str(right_edge)))
        center = (left_edge + right_edge) / 2.
        roi_bottom = [[500,450], [800,650]]
        bottom_edge = self.cam.horizontal_edge(image, roi_bottom)
        logging.getLogger('flex').info("center is %s bottom of the gripper is %s" %(str(center), str(bottom_edge)))
        return center, bottom_edge

    def spine_gripper_centering(self, width_center1, height_bottom1, width_center2, height_bottom2, width_center3, height_bottom3):
        logging.getLogger('flex').info("width: center 1 %s, center 2 %s, center 3 %s" %(str(width_center1), str(width_center2), str(width_center3)))
        logging.getLogger('flex').info("height: center 1 %s, center 2 %s, center 3 %s" %(str(height_bottom1), str(height_bottom2), str(height_bottom3)))
        # angle in degrees between the plan (x,y) of the robot and the plan of the camera 
        angle_deg = 130.
        angle_rad = math.pi * angle_deg / 180.
        Xoffset = ((width_center1 + width_center3) / 2. - width_center1) / self.cam.pixels_per_mm
        Yoffset = ((width_center1 + width_center3) / 2. - width_center2) / self.cam.pixels_per_mm
        gripper_Xoffset = (-math.cos(angle_rad) * Yoffset - math.sin(angle_rad) * Xoffset)
        gripper_Yoffset = (math.cos(angle_rad) * Xoffset - math.sin(angle_rad) * Yoffset)
        average_height_bottom = (height_bottom1 + height_bottom2 + height_bottom3) / 3.0
        gripper_Zoffset = (average_height_bottom - self.cam.image_height / 2.0) / self.cam.pixels_per_mm
        logging.getLogger('flex').info("Spine gripper offset X %s, Y %s, Z %s" %(str(gripper_Xoffset), str(gripper_Yoffset), str(gripper_Zoffset)))
        if abs(gripper_Xoffset) < 1 or abs(gripper_Yoffset) < 1:
            self.robot.setVal3GlobalVariableBoolean("bImageProcEnded", True)
            self.robot.execute("data:tSpine.trsf.x = data:tSpine.trsf.x + (%s)" %str(gripper_Xoffset))
            self.robot.execute("data:tSpine.trsf.y = data:tSpine.trsf.y + (%s)" %str(gripper_Yoffset))
            self.robot.execute("data:tSpine.trsf.z = data:tSpine.trsf.z + (%s)" %str(gripper_Zoffset))
            
        else:
            logging.getLogger('flex').error("gripper offsets are wrong")
            raise RuntimeError("gripper offsets are wrong")

    def flipping_gripper_height_detections(self):
        image = self.waiting_for_image()
        roi_dewar = [[0,150], [250,550]]
        image_dewar_height = self.cam.horizontal_edge(image, roi_dewar)
        logging.getLogger('flex').info("image height in dewar orientation %s" %str(self.cam.horizontal_edge(image, roi_dewar)))
        height_dewar = (image_dewar_height - self.cam.image_height / 2.0) / self.cam.pixels_per_mm
        logging.getLogger('flex').info("height to middle of the image %s" %str(height_dewar))
        self.robot.execute("data:pTemp = here(flange,world)")
        flipping_z_robot = self.robot.getVal3GlobalVariableDouble("pTemp.trsf.z")
        logging.getLogger('flex').info("from robot z is %s" %str(flipping_z_robot))
        parser = ConfigParser.RawConfigParser()
        file_path = self.calibration_file
        parser.read(file_path)
        calib_z_robot = parser.getfloat("Calibration", "z")
        logging.getLogger('flex').info("from reference %s" %str(calib_z_robot))
        diff_calib_flipping = (calib_z_robot - flipping_z_robot) - height_dewar
        flipping_gripper_z_dewar = self.robot.getVal3GlobalVariableDouble("tCalibration.trsf.z") - diff_calib_flipping
        logging.getLogger('flex').info("error in Z in the dewar orientation %s" %str(diff_calib_flipping))
        self.robot.setVal3GlobalVariableBoolean("bImageProcEnded", True)

        image = self.waiting_for_image()
        roi_gonio = [[0,150], [250,550]]
        image_gonio_height = self.cam.horizontal_edge(image, roi_gonio)
        logging.getLogger('flex').info("image height in gonio orientation %s" %str(image_gonio_height))
        height_gonio = (image_gonio_height - self.cam.image_height / 2.0) / self.cam.pixels_per_mm
        logging.getLogger('flex').info("height to the middle of the image %s" %str(height_gonio))
        self.robot.execute("data:pTemp = here(flange,world)")
        flipping_z_robot = self.robot.getVal3GlobalVariableDouble("pTemp.trsf.z")
        logging.getLogger('flex').info("from robot z is %s" %str(flipping_z_robot))
        logging.getLogger('flex').info("from reference %s" %str(calib_z_robot))
        diff_calib_flipping = (calib_z_robot - flipping_z_robot) - height_gonio
        flipping_gripper_z_gonio = self.robot.getVal3GlobalVariableDouble("tCalibration.trsf.z") - diff_calib_flipping
        logging.getLogger('flex').info("error in Z at the gonio %s" %str(diff_calib_flipping))

        logging.getLogger('flex').info("Vertical correction at dewar %s, at gonio %s" %(str(height_dewar), str(height_gonio)))
        if abs(height_dewar) < 5 and abs(height_gonio) < 5:
            logging.getLogger('flex').info("Correction flipping gripper in Z in Dewar orientation %s, in gonio orientation %s" %(str(flipping_gripper_z_dewar), str(flipping_gripper_z_gonio)))
            self.robot.execute("data:tFlippingDewar.trsf.z = (%s)" %str(flipping_gripper_z_dewar))
            self.robot.execute("data:tFlippingGonio.trsf.z = (%s)" %str(flipping_gripper_z_gonio))
            self.robot.setVal3GlobalVariableBoolean("bImageProcEnded", True)
        else:
            logging.getLogger('flex').error("Vertical correction too high")
            raise RuntimeError("Vertical correction too high")

    def stallion_center_detection(self):
        image = self.waiting_for_image()
        roi_left = [[300,50], [600,400]]
        roi_right = [[600,50], [900,400]]
        left_edge =  self.cam.vertical_edge(image, roi_left)
        right_edge =  self.cam.vertical_edge(image, roi_right)
        logging.getLogger('flex').info("Stallion left edge %s, right edge %s" %(str(left_edge), str(right_edge)))
        center = (left_edge + right_edge) / 2.
        return center

    def stallion_centering(self, center1, center2, center3):
        logging.getLogger('flex').info("center 1 %s, center 2 %s, center 3 %s" %(str(center1), str(center2), str(center3)))
        # angle in degrees between the plan (x,y) of the robot and the plan of the camera
        angle_deg = 130.
        angle_rad = math.pi * angle_deg / 180.
        Xoffset = ((center1 + center3) / 2.0 - center1) / self.cam.pixels_per_mm
        Yoffset = ((center1 + center3) / 2.0 - center2) / self.cam.pixels_per_mm
        stallion_Xoffset = (-math.cos(angle_rad) * Yoffset - math.sin(angle_rad) * Xoffset)
        stallion_Yoffset = (math.cos(angle_rad) * Xoffset - math.sin(angle_rad) * Yoffset)
        logging.getLogger('flex').info("stallion offset in X %s, in Y %s" %(str(stallion_Xoffset), str(stallion_Yoffset)))
        if abs(stallion_Xoffset) < 2 and abs(stallion_Yoffset) < 2:
            if self.robot.getCachedVariable("data:dioFlipDwPos").getValue() == "true" and self.robot.getCachedVariable("data:dioFlipGonPos").getValue() == "false":
                logging.getLogger('flex').info("X,Y calibration done for DW orientation")
                self.robot.execute("data:tFlippingDewar.trsf.x = data:tFlippingDewar.trsf.x + (%s)" %str(stallion_Xoffset))
                self.robot.execute("data:tFlippingDewar.trsf.y = data:tFlippingDewar.trsf.y + (%s)" %str(stallion_Yoffset))
                self.robot.setVal3GlobalVariableBoolean("bImageProcEnded", True)
            elif self.robot.getCachedVariable("data:dioFlipDwPos").getValue() == "false" and self.robot.getCachedVariable("data:dioFlipGonPos").getValue() == "true":
                logging.getLogger('flex').info("X,Y calibration done for gonio orientation")
                self.robot.execute("data:tFlippingGonio.trsf.x = data:tFlippingGonio.trsf.x + (%s)" %str(stallion_Xoffset))
                self.robot.execute("data:tFlippingGonio.trsf.y = data:tFlippingGonio.trsf.y + (%s)" %str(stallion_Yoffset))
                self.robot.setVal3GlobalVariableBoolean("bImageProcEnded", True)
            else:
                logging.getLogger('flex').error("stallion centering not in dewar or gonio orientation")
                raise RuntimeError("stallion centering not in dewar or gonio orientation")

    def ball_center_detection(self):
        image = self.waiting_for_image()
        roi = [[100,200],[1100,600]]
        x_center, y_center, rad1, rad2 = self.cam.fitEllipse(image, roi)
        logging.getLogger('flex').info("ball center in X %s, in Y %s, radius 1 %s, radius %s" %(str(x_center), str(y_center), str(rad1), str(rad2)))
        if abs(rad1 - rad2) > 2:
            logging.getLogger('flex').error("ellipse radii are too different")
            raise RuntimeError("ellipse radii are too different")
        radius = (rad1 + rad2) / 2.0
        return x_center, y_center, radius

    def ball_centering(self, width_center1, height_center1, radius1, width_center2, height_center2, radius2, width_center3, height_center3, radius3):
        logging.getLogger('flex').info("width : center 1 %s, center 2 %s, center 3 %s" %(str(width_center1), str(width_center2), str(width_center3)))
        logging.getLogger('flex').info("height: center 1 %s, center 2 %s, center 3 %s" %(str(height_center1), str(height_center2), str(height_center3)))
        logging.getLogger('flex').info("radius 1 %s, radius 2 %s, radius 3 %s" %(str(radius1), str(radius2), str(radius3)))
        # angle in degrees between the plan (x,y) of the robot and the plan of the camera 
        angle_deg = 130.
        angle_rad = math.pi * angle_deg / 180.
        Xoffset = ((width_center1 + width_center3) / 2. - width_center1)
        Yoffset = ((width_center1 + width_center3) / 2. - width_center2)
        gripper_Xoffset = (-math.cos(angle_rad) * Yoffset - math.sin(angle_rad) * Xoffset) / self.cam.pixels_per_mm
        gripper_Yoffset = (math.cos(angle_rad) * Xoffset - math.sin(angle_rad) * Yoffset) / self.cam.pixels_per_mm
        average_radius = (radius1 + radius2 + radius3) / 3.0
        average_height_center = (height_center1 + height_center2 + height_center3) / 3.0
        logging.getLogger('flex').info("average height %s average radius %s" %(str(average_height_center), str(average_radius)))
        gripper_Zoffset = (average_radius + average_height_center - self.cam.image_height / 2.0) / self.cam.pixels_per_mm 
        # if gripper above the middle of the image the correction is <0 as it is in JLib
        logging.getLogger('flex').info("Calibration gripper offsetin X %s, in Y %s, in Z %s" %(str(gripper_Xoffset), str(gripper_Yoffset), str(gripper_Zoffset)))
        if abs(gripper_Xoffset) < 1 or abs(gripper_Yoffset) < 1 or abs(gripper_Zoffset) < 1:
            self.robot.execute("data:tCalibration.trsf.x = data:tCalibration.trsf.x + (%s)" %str(gripper_Xoffset))
            self.robot.execute("data:tCalibration.trsf.y = data:tCalibration.trsf.y + (%s)" %str(gripper_Yoffset))
            self.robot.execute("data:tCalibration.trsf.z = data:tCalibration.trsf.z + (%s)" %str(gripper_Zoffset))
            self.robot.execute("data:pTemp = here(flange,world)")
            self.robot.setVal3GlobalVariableBoolean("bImageProcEnded", True)
        else:
            logging.getLogger('flex').error("gripper offsets are wrong")
            raise RuntimeError("gripper offsets are wrong")

    def save_translation(self):
        logging.getLogger('flex').info("Starting save translation")
        tCalib = str(self.robot.getVal3GlobalVariableDouble("pTemp.trsf.z"))
        logging.getLogger('flex').info("Translation calibration from robot %s" %str(tCalib))
        if tCalib == "110.0":
            logging.getLogger('flex').error("problem with getVal3GlobalVariableDouble")
            raise RuntimeError("problem with getVal3GlobalVariableDouble")

        parser = ConfigParser.RawConfigParser()
        file_path = self.calibration_file
        saved_file_path = os.path.splitext(self.calibration_file)[0]+os.path.extsep+"sav"
        parser.read(file_path)
        try:
            shutil.copy(file_path, saved_file_path)
        except IOError:
            logging.getLogger('flex').info("No such file %s" %file_path)
        parser.set("Calibration", "z", str(tCalib))
        with open(file_path, 'wb') as file:
            parser.write(file)
        logging.getLogger('flex').info("file written")
        self.robot.setVal3GlobalVariableBoolean("bImageProcEnded", True)

    def calib_detection(self, gripper_type):
        centers = []
        while True:
            notify = self.robot.waitNotify("ImageProcessing") 
            logging.getLogger('flex').info("notify %s" %notify)
            if notify == "TakeFlippingGripperCalibrationStallion_Z" and int(gripper_type) == 3:
                logging.getLogger('flex').info("calculation of height (Dewar and Gonio positions)")
                self.flipping_gripper_height_detections()
            if notify.startswith("GripperCalibration"):
                if int(gripper_type) == 1:
                    logging.getLogger('flex').info("start gripper center detection")
                    centers.append(self.spine_gripper_center_detection())
                    logging.getLogger('flex').info("number of items in center %d" %len(centers))
                if int(gripper_type) == 3:
                    centers.append(self.stallion_center_detection())
                if int(gripper_type) == 9:
                    logging.getLogger('flex').info("start gripper center detection")
                    centers.append(self.ball_center_detection())
                    logging.getLogger('flex').info("number of items in center %d" %len(centers))
            if notify == "GetTranslation" and int(gripper_type) == 9:
                    logging.getLogger('flex').info("Get translation")
                    self.save_translation()
            if int(gripper_type) == 1 and len(centers) == 3:
                logging.getLogger('flex').info("calculating 3-click centering with %s" %str(centers))
                centers_list = list(itertools.chain(*centers))
                logging.getLogger('flex').info("center list %s" %str(centers_list))
                self.spine_gripper_centering(*centers_list)
                centers = []
            if int(gripper_type) == 3 and len(centers) == 3:
                logging.getLogger('flex').info("calculating 3-click centering with %s" %str(centers))
                self.stallion_centering(*centers)
                centers = []
            if int(gripper_type) == 9 and len(centers) == 3:
                logging.getLogger('flex').info("calculating 3-click centering")
                centers_list = list(itertools.chain(*centers))
                logging.getLogger('flex').info("center list %s" %str(centers_list))
                self.ball_centering(*centers_list)
                centers = []

    def do_calib_detection(self, gripper_type):
        gripperCalib_task = gevent.spawn(self.robot.executeTask, "gripperCalib", timeout=200)
        do_detection_if_needed_task = gevent.spawn(self.calib_detection, str(gripper_type))
        try:
            gripperCalib_task.get()
        finally:
            do_detection_if_needed_task.kill()

    def gripperCalib(self):
        logging.getLogger('flex').info("Starting calibration tool")
        gripper_type = self.get_gripper_type()
        if gripper_type in [1,3,9]:
            self.robot.setVal3GlobalVariableDouble("nGripperType", str(gripper_type))
        else:
            logging.getLogger('flex').error("Wrong gripper")
            raise RuntimeError("Wrong gripper")
        self.do_calib_detection(gripper_type)
        logging.getLogger('flex').info("Calibration finished")

    def disableDewar(self):
        self.robot.executeTask("disableDewar", timeout=5)
        logging.getLogger('flex').info("Dewar disable")

    def stopDewar(self):
        self.robot.executeTask("stopDewar", timeout=10)
        logging.getLogger('flex').info("Dewar stop")

    def savedata(self):
        self.robot.executeTask("savedata", timeout=5)
        logging.getLogger('flex').info("VAL3 library saved")

    def gonioAlignment(self):
        logging.getLogger('flex').info("Starting calibration of the SmartMagnet position")
        gripper_type = self.get_gripper_type()
        if gripper_type != 9:
            logging.getLogger('flex').error("Need calibration gripper")
            raise RuntimeError("Need calibration gripper")
        self.robot.executeTask("gonioAlignment", timeout=200)
        logging.getLogger('flex').info("calibration of the SmartMagnet position finished")

    def dewarAlignment(self, cell="all"):
        logging.getLogger('flex').info("Starting calibration of the Dewar position")
        gripper_type = self.get_gripper_type()
        if gripper_type != 9:
            logging.getLogger('flex').error("Need calibration gripper")
            raise RuntimeError("Need calibration gripper")
        #self.defreezeGripper()
        if cell == "all":
            for i in range(0, 22, 3):
                self.robot.setVal3GlobalVariableDouble("nLoadPuckPos", str(i))
                self.robot.executeTask("autoAlignment", timeout=200)
        elif cell in range(1,9):
            self.robot.setVal3GlobalVariableDouble("nLoadPuckPos", str((cell - 1) * 3))
            self.robot.executeTask("autoAlignment", timeout=200)
        else:
            logging.getLogger('flex').error("Wrong cell (default all or 1-8)")
            raise RuntimeError("Wrong cell (default all or 1-8)")
        logging.getLogger('flex').info("calibration of the Dewar position finished")

    def get_phases(self, cell, frequency):
        logging.getLogger('flex').info("Get phases on cell %d at %s Hz" %(cell, str(frequency)))
        self.proxisense.set_frequency(frequency)
        self.proxisense.deGauss(cell)
        phase_puck1, phase_puck2, phase_puck3 = self.proxisense.getPhaseShift(cell)
        logging.getLogger('flex').info("phase (microsec) for puck 1 %s, puck 2 %s, puck 3 %s" %(str(frequency), str(phase_puck1), str(phase_puck2), str(phase_puck3)))
        return [phase_puck1, phase_puck2, phase_puck3]

    def find_ref(self, frequency, cell):
        ref = self.proxisense.get_config(frequency)
        logging.getLogger('flex').info("Reference phases at %s" %str(frequency))
        section = "Cell%d" %int(cell)
        i = 0
        for list in ref:
            if list[0] == section:
                rank = i
                logging.getLogger('flex').info("Found the refence in %s" %str(list[0]))
                break
            if list == ref[-1:]:
                logging.getLogger('flex').error("Reference not found")
                raise RuntimeError("Reference not found")
            i += 1
        nb_puckType = len(ref) / (8 * 3)
        ref_phase = []
        ref_puckType = []
        for i in range(0, nb_puckType):
            ref_phase.append([ref[rank + (3 * i)][2], ref[rank + 1 + (3 * i)][2], ref[rank + 2 + (3 * i)][2]])
            ref_puckType.append(str(ref[rank + (3 * i)][1]).split("_")[0])
        return ref_phase, ref_puckType

    def detect_puck(self, cell):
        if cell in range(1,9,2):
            tolerance_800 = self.proxisense.typeDetectionTolerance_SC3_800
            tolerance_2000 = self.proxisense.typeDetectionTolerance_SC3_2000
        if cell in range(2,10,2):
            tolerance_800 = self.proxisense.typeDetectionTolerance_Unipuck_800
            tolerance_2000 = self.proxisense.typeDetectionTolerance_Unipuck_2000
        ref_phase_800, ref_puckType = self.find_ref(800, cell)
        ref_phase_2000, ref_puckType = self.find_ref(2000, cell)
        phases_800 = self.get_phases(cell, 800)
        phases_2000 = self.get_phases(cell, 2000)
      
        if len(ref_phase_800) != len(ref_phase_2000):
            logging.getLogger('flex').error("config files have different length")
            raise RuntimeError("corrupted config files ")
        len_ref = len(ref_phase_800)
        logging.getLogger('flex').info("%d puck types to checked, including empty" %len_ref)
        
        result=[]
        for puckType in range(0, len_ref):
            list_res=[]
            for i in range(0,3):
                diff_800 = abs(ref_phase_800[puckType][i] - phases_800[i])
                diff_2000 = abs(ref_phase_2000[puckType][i] - phases_2000[i])
                logging.getLogger('flex').info("difference at 800Hz %s" %str(diff_800))
                logging.getLogger('flex').info("difference at 2000Hz %s" %str(diff_2000))
                if diff_800 < tolerance_800 and diff_2000 < tolerance_2000:
                    list_res.append(ref_puckType[puckType])
                else:
                    list_res.append(None)
            result.append(list_res)
        logging.getLogger('flex').info("list of detection before filtering %s" %str(result))

        def f(*elements):
            try:
                return filter(None, elements)[0]
            except IndexError:
                return None

        res = list(itertools.imap(f, *result))
        return res

    def _scanSlot(self, cell, puck="all"):
        pucks_detected = self.detect_puck(cell)
        logging.getLogger('flex').info("puck 1 detected %s, puck 2 detected %s, puck 3 detected %s" %(str(pucks_detected[0]), str(pucks_detected[1]), str(pucks_detected[2])))
        threshold_us = self.proxisense.ct_to_us(self.proxisense.detection_threshold_ct)
        logging.getLogger('flex').info("threshold in microsecond %s" %str(threshold_us))
        if puck == "all":
            for i in range(0,3):
                if pucks_detected[i] == "empty":
                    threshold = phases_2000[i] - threshold_us
                    logging.getLogger('flex').info("Puck not detected")
                else:
                    threshold = phases_2000[i] + threshold_us
                    logging.getLogger('flex').info("Puck detected")
                logging.getLogger('flex').info("Puck %d, threshold %s" %((i + 1), str(threshold)))
                self.proxisense.writeThreshold(cell, i + 1, threshold)
        else:
            puck_detected = pucks_detected[puck - 1]
            if puck_detected == "empty":
                threshold = phases_2000[puck - 1] - threshold_us
                logging.getLogger('flex').info("Puck not detected")
            else:
                threshold = phases_2000[puck - 1] + threshold_us
                logging.getLogger('flex').info("Puck detected")
            logging.getLogger('flex').info("Puck %d, threshold %s" %(puck, str(threshold)))
            self.proxisense.writeThreshold(cell, puck, threshold)

    def scanSlot (self, cell="all", puck="all"):
        if cell != "all" and isinstance(cell, (int,long)) and not cell in range(1,9):
            logging.getLogger('flex').error("Wrong cell number [1-8]")
            raise ValueError("Wrong cell number [1-8]")
        if puck != "all" and isinstance(puck, (int,long)) and not puck in range(1,4):
            logging.getLogger('flex').error("wrong puck number[1-3]")
            raise ValueError("Wrong puck number[1-3]")
        logging.getLogger('flex').info("Starting to scan on cell %s and puck %s" %(str(cell), str(puck)))
        if cell == "all":
            for cell in range(1,9):
                logging.getLogger('flex').info("Scan slot cell %d" %cell)
                self._scanSlot(cell, puck="all")
        else:
            logging.getLogger('flex').info("Scan slot cell %d" %cell)
            self._scanSlot(cell, puck) 

    def proxisenseCalib(self, cell="all", empty=True):
        if cell != "all" and isinstance(cell, (int,long)) and not cell in range(1,9):
            logging.getLogger('flex').error("Wrong cell number [1-8]")
            raise ValueError("Wrong cell number [1-8]")
        if cell is "all":
            for i in range(1,9):
                if empty:
                    puckType = "empty"
                else:
                    if i in range(1,8,2):
                        puckType = "sc3"
                    else:
                        puckType = "uni"
                self.proxisense.set_frequency(800)
                res = self.proxisense.getPhaseShift(i)
                self.proxisense.set_config(i, 800, puckType, res[0], res[1], res[2])
                self.proxisense.set_frequency(2000)
                res = self.proxisense.getPhaseShift(i)
                self.proxisense.set_config(i, 2000, puckType, res[0], res[1], res[2])
        else:
            if empty:
                puckType = "empty"
            else:
                if i in range(1,8,2):
                    puckType = "sc3"
                else:
                    puckType = "uni"
            self.proxisense.set_frequency(800)
            res = self.proxisense.getPhaseShift(cell)
            self.proxisense.set_config(cell, 800, puckType, res[0], res[1], res[2])
            self.proxisense.set_frequency(2000)
            res = self.proxisense.getPhaseShift(cell)
            self.proxisense.set_config(cell, 2000, puckType, res[0], res[1], res[2])
                


