# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""\
Symetrie hexapod

YAML_ configuration example:

.. code-block:: yaml

    plugin: emotion
    class: SHexapod
    tcp:
      url: id99hexa1
    axes:
      - name: h1tx
        role: tx
        unit: mm
      - name: h1ty
        role: ty
        unit: mm
      - name: h1tz
        role: tz
        unit: mm
      - name: h1rx
        role: rx
        unit: deg
      - name: h1ry
        role: ry
        unit: deg
      - name: h1rz
        role: rz
        unit: deg

"""

import re
import logging
from collections import namedtuple

import numpy
import gevent.lock
from tabulate import tabulate

from bliss.comm.util import get_comm, TCP
from bliss.comm.tcp import SocketTimeout
from bliss.common.axis import AxisState
from bliss.controllers.motor import Controller
from bliss.common.logtools import *

from bliss.controllers.motors.shexapod import (
    ROLES,
    Pose,
    BaseHexapodError,
    BaseHexapodProtocol,
)


class HexapodV2Error(BaseHexapodError):

    ERRORS = {
        -1: "Ignored",
        -2: "Rejected_PriorityCmdReceived",
        -4: "PanCmdAck_CmdOutOfSections",
        -5: "PanCmdAck_CmdNotDefinedInFBsCaller",
        -6: "API_UnknownCommandWord",
        -7: "API_CmdStringTooLong",
        -9: "PanCmdAck_WrongNbOfArguments",
        -10: "PanCmdAck_WrongGroupOrAxisNumber",
        -11: "PanCmdAck_WrongCfgGetSetValue",
        -12: "PanCmdAck_CmdAlreadyRunning",
        -13: "PanCmdAck_CfgCmdAlreadyRunning",
        -18: "PanCmdAck_FbStillUndefinedAfter1Cycle",
        -21: "FbCaller_UnknownFB",
        -22: "FbCaller_PanelAccessRestricted",
        -23: "Panel_UnknownStaCmd",
        -26: "GetTypeOnly",
        -27: "SetTypeOnly",
        -39: "Dev_Bug",
        -40: "Dev_SetPmacVar",
        -41: "GetResponseRejectedByThePmacCommandProcessor",
        -42: "UndescribedError",
        -43: "Dev_MallocError",
        -44: "CommandRejectedByThePmacCommandProcessor",
        -45: "Dev_UndefinedEnumValue",
        -46: "Dev_UndefinedMVar",
        -47: "Access_UserLevelRestriction",
        -48: "ParamsIn_WrongValue",
        -49: "ParamsIn_WrongNbOfParams",
        -50: "GetResponseDecoding",
        -52: "EthercatNetworkError",
        -53: "NtpSyncEnabled",
        -54: "NtpFailure",
        -55: "TimezoneUpdateFailure",
        -57: "BusySM_UnknownState",
        -58: "BusySM_Timeout",
        -60: "SubFbCall_ExecutionReseted",
        -63: "OptionNotAvailable",
        -67: "SM_NotAllowedInCurrentState",
        -68: "SM_CommandAborted",
        -69: "SM_UnexpectedState",
        -70: "SM_NotAllowedWhenWarningsAreSet",
        -72: "SM_NotAllowedInCurrentSysState",
        -73: "NotAllowedWhenMoving",
        -74: "ErrThatDoNotAllowPowerOn",
        -75: "ErrGenerated",
        -76: "ErrPresent_ResetNeeded",
        -77: "IO_SafetyRelayState",
        -78: "Sys_DrivesResetFailed",
        -79: "BrakeOffTimeout",
        -80: "AmpEnableTimeout",
        -81: "InPosTimeout",
        -82: "WrongPmcConfig",
        -87: "Ecat_InitTimeout",
        -88: "Modbus_Error",
        -89: "Sys_Init_AppFctError",
        -90: "Gr_Fesc_NotAllowedInCurrentFescState",
        -91: "Gr_RotaryWriteFailed",
        -92: "Gr_RotaryAlreadyUsed",
        -93: "Gr_RotaryConfigFailed",
        -94: "Gr_Fesc_UnexpectedState",
        -95: "Gr_SafetyLiveChecks_OutOfLimits",
        -96: "Gr_SafetyLiveChecks_OutOfLimits_Ertt",
        -97: "State_Sys_AllAxesShouldBeDisabled",
        -98: "State_Sys_AmpShouldBeDisabledOnAllAx",
        -99: "State_Sys_InitNotDone",
        -100: "State_Sys_BootNotDone",
        -101: "State_Sys_NotPossibleOnBootError",
        -102: "State_Sys_NotPossibleOnFatalError",
        -103: "Gr_WrongStartPosition",
        -104: "Gr_OutOfVolume_usr_uTo",
        -105: "Gr_OutOfVolume_usr_mrTpr",
        -106: "Gr_OutOfVolume_scp_mTp",
        -107: "State_Gr_NotAllowedInCurrentSysState",
        -108: "State_Gr_HomingNotDone",
        -109: "Gr_SpeedAccValidation_NaN_Inf_Detected",
        -110: "Gr_SpecificPosDisabled",
        -111: "Fct_MGI_CalculError",
        -112: "Fct_MGD_CalculError",
        -113: "Gr_MCS_PTP_Validation_NaN_Inf_Detected",
        -114: "Gr_SecuCuve",
        -115: "Gr_FbNotAllowedForThisGr",
        -116: "Gr_SubAxFbReturnWrongState",
        -117: "State_Ax_NotAllowedInCurrentSysState",
        -118: "State_Ax_HomingNotDone",
        -119: "State_Gr_AmpShouldBeDisabledOnAllAxes",
        -120: "Ax_JogMaxDuration",
        -121: "HomeModeUndefined",
        -122: "Ax_HomeAbsPositionReadingError",
        -123: "Ax_AmpFault_GrResetNeeded",
        -124: "Ax_AbsPositionReadingError",
        -125: "Ax_PhasePosCalculationError",
        -126: "Ax_CommandOutOfLimits",
        -127: "Prog_KilledWhileProcessing",
        -129: "DriveInFault_AllMotorsMustBePowerOffToAllowDriveReset",
        -130: "DriveInFault_ResetNeeded",
        -131: "Drive_ComError",
        -133: "Files_SCP_SECTION_START",
        -134: "Files_SCP_NotFound",
        -135: "Files_SCP_NoStruct",
        -136: "Files_SCP_NoCheckSum",
        -137: "Files_SCP_BadCrc",
        -138: "Files_SCP_BadHeader",
        -139: "Files_SCP_BadVersion",
        -143: "Files_CFG_SECTION_START",
        -144: "Files_CFG_NotFound",
        -145: "Files_CFG_NoStruct",
        -146: "Files_CFG_NoCheckSum",
        -147: "Files_CFG_BadCrc",
        -148: "Files_CFG_BadHeader",
        -149: "Files_CFG_BadVersion",
        -150: "Files_CFG_WrongScpHeaderInUsrFile",
        -154: "Traj_Files_CFG_SECTION_START",
        -155: "Traj_Files_CFG_NotFound",
        -156: "Traj_Files_CFG_NoStruct",
        -157: "Traj_Files_CFG_NoCheckSum",
        -158: "Traj_Files_CFG_BadCrc",
        -159: "Traj_Files_CFG_BadHeader",
        -160: "Traj_Files_CFG_BadVersion",
        -161: "Traj_Files_CFG_WrongScpHeaderInUsrFile",
        -163: "FileNotFound",
        -164: "BackupError",
        -165: "UntarError",
        -166: "TmpFileSuppError",
        -167: "DirCreationError",
        -168: "File_DoNotExist",
        -169: "File_ReadError",
        -170: "File_FormatError",
        -171: "File_HeaderMissing",
        -174: "Scp_ActionsAfterLoading_MGD_For_VissageDeltaLong_Home",
        -175: "Scp_ActionsAfterLoading_MGIsub_For_FixedOrgAngleVct",
        -176: "Scp_ActionsAfterLoading_MGIsub_For_MobileOrgAngleVct",
        -179: "Traj_Config_Mismatch",
        -180: "Traj_Files_DoNotExist",
        -181: "Traj_ConfigFile_DoNotExist",
        -182: "Traj_ProgFile_DoNotExist",
        -184: "Traj_ProgFile_ReadError",
        -185: "Traj_ProgFile_HeaderFormat",
        -186: "Traj_ProgFile_WrongUsrFileAssociation",
        -187: "Traj_ProgLaunchTimeout1",
        -188: "Traj_ProgLaunchTimeout2",
        -189: "Traj_NotAllowedInCurrentState",
        -190: "Traj_WrongTriggerMode",
        -191: "Traj_RotaryCreationTimeout",
        -192: "Traj_GpasciiCreationTimeout",
        -193: "Traj_WrongStartPointIndex",
        -196: "RotaryCreationFailed",
        -197: "Rtt_JavpGainsCalcError",
        -204: "ParamsIn_WrongParam_START",
        -205: "ParamsIn_WrongParam0",
        -206: "ParamsIn_WrongParam1",
        -207: "ParamsIn_WrongParam2",
        -208: "ParamsIn_WrongParam3",
        -209: "ParamsIn_WrongParam4",
        -210: "ParamsIn_WrongParam5",
        -211: "ParamsIn_WrongParam6",
        -212: "ParamsIn_WrongParam7",
        -213: "ParamsIn_WrongParam8",
        -214: "ParamsIn_WrongParam9",
        -215: "ParamsIn_WrongParam10",
        -216: "ParamsIn_WrongParam11",
        -217: "ParamsIn_WrongParam12",
        -218: "ParamsIn_WrongParam13",
        -219: "ParamsIn_WrongParam14",
        -220: "ParamsIn_WrongParam15",
        -221: "ParamsIn_WrongParam16",
        -222: "ParamsIn_WrongParam17",
        -223: "ParamsIn_WrongParam18",
        -224: "ParamsIn_WrongParam19",
        -225: "ParamsIn_WrongParam20",
        -226: "ParamsIn_WrongParam21",
        -227: "ParamsIn_WrongParam22",
        -228: "ParamsIn_WrongParam23",
        -229: "ParamsIn_WrongParam24",
        -230: "ParamsIn_WrongParam25",
        -231: "ParamsIn_WrongParam26",
        -232: "ParamsIn_WrongParam27",
        -233: "ParamsIn_WrongParam28",
        -234: "ParamsIn_WrongParam29",
        -235: "ParamsIn_WrongParam30",
        -236: "ParamsIn_WrongParam31",
        -237: "ParamsIn_WrongParam32",
        -238: "ParamsIn_WrongParam33",
        -239: "ParamsIn_WrongParam34",
        -240: "ParamsIn_WrongParam35",
        -241: "ParamsIn_WrongParam36",
        -242: "ParamsIn_WrongParam37",
        -243: "ParamsIn_WrongParam38",
        -244: "ParamsIn_WrongParam39",
        -245: "ParamsIn_WrongParam40",
        -246: "ParamsIn_WrongParam41",
        -247: "ParamsIn_WrongParam42",
        -248: "ParamsIn_WrongParam43",
        -249: "ParamsIn_WrongParam44",
        -250: "ParamsIn_WrongParam45",
        -251: "ParamsIn_WrongParam46",
        -252: "ParamsIn_WrongParam47",
        -253: "ParamsIn_WrongParam48",
        -254: "ParamsIn_WrongParam49",
        -255: "ParamsIn_WrongParam50",
        -256: "ParamsIn_WrongParam_END",
        -262: "Maths_VectorNotUnitary",
        -265: "String_StrCat_DestSizeReached",
        -266: "String_StringLengthOverStringSize",
        -267: "String_AllCharShouldIntBetween_0_255",
        -268: "String_StrCpy_DestSizeReached",
        -271: "Kin_SECTION_START",
        -272: "Kin_NoHome",
        -273: "Kin_InvL",
        -274: "Kin_InvVol",
        -275: "Kin_FwdIt",
        -276: "Kin_FwdVol",
        -277: "Kin_PLCIt",
        -278: "Kin_PLCVol",
        -279: "Kin_MGD_MJinv_NonInv",
        -288: "Gr_OutOfVolume_UnivJoints",
        -289: "GrAx_OutOfAxesLimits",
        -290: "PhasingIaIbAngleToSmall",
        -291: "PhasingIaIbAngleToBig",
        -292: "PhasingTimeout",
        -293: "PhasingMotorStabTimeout",
        -294: "Motor_I2tSumStillAboveI2tTrip_PleaseWait",
        -297: "Gather_SECTION_START",
        -298: "Gather_NotAllowedInCurrentGatherState",
        -299: "Gather_SetPmacVarEnable_Failed",
        -300: "Gather_Dev_ToManyChanelsDefined",
        -307: "MessageQueue_GetFailure",
        -308: "MessageQueue_CtlFailure",
        -309: "MessageQueue_SendFailure",
        -310: "TcpApi_NoCmdMatching",
        -311: "TcpApi_CmdNotImplemented",
        -312: "TcpApi_CmdNotAllowed",
        -313: "TcpApi_NoCmdMatching",
        -314: "SeeLinuxErrno",
        -315: "LinuxSystemCmdFailed",
    }

    def __init__(self, code):
        try:
            code = int(code)
            msg = self.ERRORS.setdefault(code, "Unknown error")
        except ValueError:
            msg = code
            code = -1000
        msg = "Error {0}: {1}".format(code, msg)
        super(HexapodV2Error, self).__init__(msg)


class HexapodProtocolV2(BaseHexapodProtocol):

    DEFAULT_PORT = 61559
    BUSY = 1
    DONE = 2

    MACHINE_CS = 1
    USER_CS = 2

    #: Reply is either:
    #: <CMD>:<CODE>
    #: <CMD>:<CODE>,<DATA>
    REPLY_RE = re.compile(r"(?P<cmd>[^:]+)\:(?P<code>[+\-0-9]+)(?P<data>.*)$")

    SYSTEM_STATUS_FIELDS = (
        "error",
        "ready",
        "emergency_stop_pressed",
        "safety_enabled",
        "in_position",
        "moving",
        "control",
        "brake",
        "phasing_done",
        "homing_done",
        "homing_running",
        "homing_virtual",
        "motion_restrained",
        "software_limit",
        "following_error",
        "hardware_limit",
        "drive_fault",
        "encoder_error",
        "system_error",
        "fatal_error",
    )

    SystemStatus = namedtuple("SystemStatus", SYSTEM_STATUS_FIELDS)

    AXIS_STATUS_FIELDS = (
        "error",
        "in_position",
        "moving",
        "control",
        "brake",
        "phasing_done",
        "homing_done",
        "homing_running",
        "homing_hardware_input",
        "software_limit",
        "following_warning",
        "following_error",
        "negative_hardware_limit",
        "positive_hardware_limit",
        "drive_fault",
        "encoder_error",
        "fatal_error",
    )

    AxisStatus = namedtuple("AxisStatus", AXIS_STATUS_FIELDS)

    SpecificPose = namedtuple("SpecificPose", "id name enabled cs pose")

    DUMP_TEMPLATE = """\
Symetrie hexapod
Project: {o.project}
API version: {o.api_version}

{system_status}

{actuators_status}

Specific poses:
{specific_poses}

{pose}

User limits: {o.user_limits_enabled}; \
Machine limits: {o.machine_limits_enabled}

Current translational speed: {speeds[tspeed]} mm/s
Current rotational speed: {speeds[rspeed]} mm/s
Maximum translational speed: {speeds[max_tspeed]} mm/s
Maximum rotational speed: {speeds[max_rspeed]} mm/s

Current translational acceleration: {accelerations[tacceleration]} mm/s/s
Current rotational acceleration: {accelerations[racceleration]} mm/s/s
Maximum translational acceleration: {accelerations[max_tacceleration]} mm/s/s
Maximum rotational acceleration: {accelerations[max_racceleration]} mm/s/s
"""

    def __init__(self, config):
        BaseHexapodProtocol.__init__(self, config)
        self.__api_version = None
        self.__project = None
        self.__set_pose = None
        self.__read_task = None
        self.__connect = self.comm.connect
        self.comm.connect = self.__on_connect
        self.__pending_cmds = {}

    def __on_connect(self, host=None, port=None):
        if self.__read_task is not None:
            self.__read_task.kill()
        self.__connect(host=host, port=port)
        # on connection, the hardware sends 4 lines of text:
        self.comm.readline()  # "SYMETRIE controller"
        version = self.comm.readline().decode()  # "API version: <api_version>"
        project = self.comm.readline().decode()  # "Project: <project>"
        self.comm.readline()  # "Waiting for commands..."
        self.__api_version = version.split(":", 1)[1].strip()
        self.__project = project.split(":", 1)[1].strip()
        self.__read_task = gevent.spawn(self.__read_loop)

    def __read_loop(self):
        while True:
            try:
                reply = self.comm._readline().decode()
                log_debug_data(self, "Rx: %r", reply)
            except SocketTimeout:
                continue
            except gevent.socket.error as error:
                for results in self.__pending_cmds.values():
                    for result in results:
                        result.set_exception(error)
                self.__pending_cmds = {}
            reply_dict = self.REPLY_RE.match(reply).groupdict()
            async_result = self.__pending_cmds[reply_dict["cmd"]][0]
            async_result.set(reply)

    @classmethod
    def __handle_reply_code(cls, cmd, reply, expected_code):
        group = cls.REPLY_RE.match(reply)
        if group is None:
            raise HexapodV2Error("Unexpected reply: {0!r}".format(reply))
        reply_dict = group.groupdict()
        reply_cmd = reply_dict["cmd"]
        if not cmd.startswith(reply_cmd):
            raise HexapodV2Error(
                "Reply command ({0!r}) does not match "
                "expected command ({1!r}".format(reply_cmd, cmd)
            )
        try:
            reply_dict["code"] = reply_code = int(reply_dict["code"])
        except ValueError:
            raise HexapodV2Error("Unexpected reply code {0!r}".format(reply_code))
        if reply_code != expected_code:
            raise HexapodV2Error(reply_code)
        return reply_dict

    def __call__(self, cmd, *args, **kwargs):
        """
        Low level API to execute a command/query

        Examples::

            >>> print( proto('STA#HEXAPOD?', ack=False) )
            '602,0.001,0.002,0.003,0.001,-0.002,0.003,0.001,0.002,0.003,0.001,-0.002,0.003'

            >>> move_result = proto('MOVE#ABS0,0,0,0,0,0', async_=True)
            >>> move.wait()

        Args:
            cmd (str): the command to send (ex: 'MOVE#ABS', 'STA#HEXAPOD?')
            *args: argument list (each argument will be converted to string)

        Keyword Args:
            ack (bool): True if command will send BUSY state (ex: 'CONTROLON')
                        or False otherwise (ex: 'STA#EXAPOD?') [default: True]

            async_ (bool): True not to wait for the command to finish or False
                          to wait [default: False]

        Returns:
            str, AsyncResult or None: if async it returns an AsyncResult,
            otherwise, if *cmd* is a query returns the query result as a string,
            otherwse it returns None
        """

        ack = kwargs.pop("ack", True)
        async_ = kwargs.pop("async_", False)
        if kwargs:
            raise TypeError("Unknown keyword arguments: {0}".format(", ".join(kwargs)))
        is_query = "?" in cmd
        cmd_id = cmd.split("?", 1)[0]
        cmd_line = "{0}{1}{2}".format(cmd, ",".join(map(str, args)), self.eol)
        log_debug_data(self, "Tx: %r", cmd_line)
        result = gevent.event.AsyncResult()
        if ack:
            result_ack = gevent.event.AsyncResult()
            results = [result_ack, result]
            self.__pending_cmds[cmd_id] = results
            self.comm.write(cmd_line.encode())
            reply = result_ack.get()
            results.pop(0)
            self.__handle_reply_code(cmd, reply, self.BUSY)
        else:
            self.__pending_cmds[cmd_id] = [result]
            self.comm.write(cmd_line.encode())
        if async_:
            return result
        reply = result.get()
        reply_dict = self.__handle_reply_code(cmd, reply, self.DONE)

        if is_query:
            data = reply_dict["data"]
            if data:
                # take first comma out
                return data[1:]
            return data

    @property
    def set_pose(self):
        if self.__set_pose is None:
            self.__set_pose = self.object_pose
        return self.__set_pose

    def update_set_pose(self, **pose):
        self.set_pose._replace(**pose)

    @property
    def api_version(self):
        if self.__api_version is None:
            self.comm.open()
        return self.__api_version

    @property
    def project(self):
        if self.__project is None:
            self.comm.open()
        return self.__project

    @property
    def enabled(self):
        return self.system_status.ready

    @enabled.setter
    def enabled(self, enable):
        status = self.system_status
        curr_enabled = status.ready
        curr_control = status.control
        if enable and not curr_enabled:
            self("ENABLE")
        elif not enable and curr_enabled:
            if curr_control:
                self("CONTROLOFF")
            self("DISABLE")

    @property
    def control(self):
        return self.system_status.control

    @control.setter
    def control(self, control):
        status = self.system_status
        curr_enabled = status.ready
        curr_control = status.control
        if control and not curr_control:
            if not curr_enabled:
                self("ENABLE")
            self("CONTROLON")
        elif not control and curr_control:
            self("CONTROLOFF")

    def __to_status(self, status, klass):
        istatus = int(status)
        return klass(*[bool(istatus & (1 << i)) for i in range(len(klass._fields))])

    @property
    def full_system_status(self):
        """
        Full status: status, object_pose and platform_pose
        """
        data = self("STA#HEXAPOD?", ack=False)
        data = data.split(",")
        status = self.__to_status(data[0], self.SystemStatus)
        o_pose = self.__to_pose(data[1:])
        p_pose = self.__to_pose(data[7:])
        return dict(status=status, object_pose=o_pose, platform_pose=p_pose)

    @property
    def system_status(self):
        """
        Hexapod status
        """
        return self.full_system_status["status"]

    @property
    def object_pose(self):
        """
        Pose of the Object coordinate system expressed in the User coordinate
        system (uTo).
        """
        return self.full_system_status["object_pose"]

    @property
    def platform_pose(self):
        """
        Pose of the Platform coordinate system expressed in the Machine
        coordinate system (mTp)
        """
        return self.full_system_status["platform_pose"]

    @property
    def full_actuators_status(self):
        """
        Full actuators status: for each axis: status and position length
        """
        data = self("STA#AXES?", ack=False)
        data = data.split(",")
        N = int(data[0])
        result = []
        for i in range(N):
            status = self.__to_status(data[1 + i], self.AxisStatus)
            length = 1E3 * float(data[1 + i + N])
            result.append(dict(status=status, length=length))
        return result

    @property
    def actuators_status(self):
        return [axis["status"] for axis in self.full_actuators_status]

    @property
    def actuators_length(self):
        return [axis["length"] for axis in self.full_actuators_status]

    def _move(self, pose, async_=False):
        set_pose_dict = self.set_pose._asdict()
        # any coordinate which is None will be replaced by the latest set_pose
        pose = Pose(*[set_pose_dict[i] if v is None else v for i, v in enumerate(pose)])
        pose_str = self.__from_pose(pose)
        self.__set_pose = pose
        return self("MOVE#ABS", pose_str, async_=async_)

    @property
    def is_moving(self):
        return self.system_status.moving

    def _homing(self, async_=False):
        return self("HOMING", async_=async_)

    def _stop(self):
        self("STOP")

    def _reset(self):
        self("RESET")

    #
    # Configuration
    #

    def save_config(self):
        self("CFG#SAVE")

    @property
    def is_current_config_saved(self):
        return bool(int(self("CFG#SAVE?")))

    @property
    def _user_and_object_cs(self):
        data = self("CFG#CS?", 3)
        data = data.split(",")[1:]  # first field is CS (3 in this case)
        user_cs = Pose(*map(float, data[:6]))
        object_cs = Pose(*map(float, data[6:]))
        return dict(user_cs=user_cs, object_cs=object_cs)

    @property
    def user_cs(self):
        return self._user_and_object_cs["user_cs"]

    @property
    def object_cs(self):
        return self._user_and_object_cs["object_cs"]

    @property
    def speeds(self):
        """
        Speeds: translational (mm/s), rotational (deg/s)
        """
        data = self("CFG#SPD?")
        data = data.split(",")
        ts, rs = self.__to_tr(data[:2])
        max_ts, max_rs = self.__to_tr(data[2:])
        return dict(tspeed=ts, rspeed=rs, max_tspeed=max_ts, max_rspeed=max_rs)

    @speeds.setter
    def speeds(self, speeds):
        curr_speeds = self.speeds
        if "tspeed" not in speeds:
            speeds["tspeed"] = curr_speeds["tspeed"]
        elif speeds["tspeed"] > curr_speeds["max_tspeed"]:
            raise HexapodV2Error(
                "Translational speed above max allowed ({0} mm/s)".format(
                    curr_speeds["max_tspeed"]
                )
            )
        if "rspeed" not in speeds:
            speeds["rspeed"] = self.rspeed
        elif speeds["rspeed"] > curr_speeds["max_rspeed"]:
            raise HexapodV2Error(
                "Rotational speed above max allowed ({0} deg/s)".format(
                    curr_speeds["max_rspeed"]
                )
            )
        self("CFG#SPD", self.__from_tr(speeds["tspeed"], speeds["rspeed"]))

    @property
    def tspeed(self):
        return self.speeds["tspeed"]

    @tspeed.setter
    def tspeed(self, ts):
        self.speeds = dict(tspeed=ts)

    @property
    def rspeed(self):
        return self.speeds["rspeed"]

    @rspeed.setter
    def rspeed(self, rs):
        self.speeds = dict(rspeed=rs)

    @property
    def accelerations(self):
        """
        Accelerations: translational (mm/s/s), rotational (deg/s/s)
        """
        data = self("CFG#ACC?")
        data = data.split(",")
        ta, ra = self.__to_tr(data[:2])
        max_ta, max_ra = self.__to_tr(data[2:])
        return dict(
            tacceleration=ta,
            racceleration=ra,
            max_tacceleration=max_ta,
            max_racceleration=max_ra,
        )

    @accelerations.setter
    def accelerations(self, accels):
        curr_accels = self.accelerations
        if "tacceleration" not in accels:
            accels["tacceleration"] = self.tacceleration
        elif accels["tacceleration"] > curr_accels["max_tacceleration"]:
            raise HexapodV2Error(
                "Translational acceleration above max allowed ({0} mm/s/s)".format(
                    curr_accels["max_tacceleration"]
                )
            )
        if "racceleration" not in accels:
            accels["racceleration"] = self.racceleration
        elif accels["racceleration"] > curr_accels["max_racceleration"]:
            raise HexapodV2Error(
                "Rotational acceleration above max allowed ({0} deg/s/s)".format(
                    curr_accels["max_racceleration"]
                )
            )

        self(
            "CFG#ACC", self.__from_tr(accels["tacceleration"], accels["racceleration"])
        )

    @property
    def tacceleration(self):
        return self.accelerations["tacceleration"]

    @tacceleration.setter
    def tacceleration(self, ts):
        self.accelerations = dict(tacceleration=ts)

    @property
    def racceleration(self):
        return self.accelerations["racceleration"]

    @racceleration.setter
    def racceleration(self, rs):
        self.accelerations["racceleration"] = rs

    POSE_CS = {
        0: "Plaform CS in Machine CS",
        1: "Symetrie intermediate CS",
        2: "Customer intermediate CS",
        3: "Object CS in User CS",
    }

    @property
    def specific_poses(self):
        pose_bits, max_poses = map(int, self("CFG#SPECIFICPOS?0").split(",")[1:])
        poses = {}
        for i in range(64):
            if pose_bits & (1 << i):
                pose_data = self("CFG#SPECIFICPOS?{0}".format(i + 1)).split(",")[1:]
                poses[i + 1] = self.SpecificPose(
                    id=i + 1,
                    name=pose_data[-1][1:-1],
                    enabled=bool(int(pose_data[0])),
                    cs=self.POSE_CS[int(pose_data[1])],
                    pose=self.__to_pose(pose_data[2:8]),
                )
        return poses

    @classmethod
    def __to_numpy(cls, data):
        if isinstance(data, str):
            data = numpy.fromstring(data, sep=",")
        else:
            if isinstance(data[0], str):
                data = list(map(float, data))
            data = numpy.array(data, dtype=numpy.float64)
        return data

    @classmethod
    def __to_tr(cls, data):
        """
        from string or seq comming from hardware of translation (m), rotation (rad)
        to translation (mm), rotation (deg)
        """
        data = cls.__to_numpy(data)[:2]
        data[0] = 1E3 * data[0]
        data[1] = numpy.rad2deg(data[1])
        return data

    @classmethod
    def __from_tr(cls, translation, rotation):
        translation = 1E-3 * translation
        rotation = numpy.deg2rad(rotation)
        return "{0},{1}".format(translation, rotation)

    @classmethod
    def __to_pose(cls, data):
        data = cls.__to_numpy(data)[:6]
        data[:3] = 1E3 * data[:3]  # m to mm
        data[3:6] = numpy.rad2deg(data[3:6])
        return Pose(*data)

    @classmethod
    def __from_pose(cls, pose):
        data = numpy.array(pose, dtype=numpy.float64)
        data[:3] = 1E-3 * data[:3]  # mm to m
        data[3:] = numpy.deg2rad(data[3:])
        return ",".join(map(str, data))

    @classmethod
    def __to_limit(cls, data):
        low_pose = cls.__to_pose(data)
        high_pose = cls.__to_pose(data[6:])
        return dict(low_pose=low_pose, high_pose=high_pose)

    def __limits(self, cs):
        data = self("CFG#LIM#WS?", cs)
        data = data.split(",")[1:]  # first element is coordinate system
        return self.__to_limit(data)

    @property
    def machine_limits(self):
        return self.__limits(self.MACHINE_CS)

    @property
    def user_limits(self):
        return self.__limits(self.USER_CS)

    @property
    def machine_limits_enabled(self):
        data = self("CFG#LIM#ENABLE?", 1)
        enable = bool(int(data.rsplit(",", 1)[-1]))
        return enable

    @machine_limits_enabled.setter
    def machine_limits_enabled(self, enable):
        self("CFG#LIM#ENABLE", 1, 1 if enable else 0)

    @property
    def user_limits_enabled(self):
        data = self("CFG#LIM#ENABLE?", 2)
        enable = bool(int(data.rsplit(",", 1)[-1]))
        return enable

    @user_limits_enabled.setter
    def user_limits_enabled(self, enable):
        self("CFG#LIM#ENABLE", 2, 1 if enable else 0)

    def dump(self):
        full_system_status = self.full_system_status
        full_actuators_status = self.full_actuators_status
        cs = self._user_and_object_cs
        specific_poses = self.specific_poses
        user_limits = self.user_limits
        machine_limits = self.machine_limits
        speeds, accelerations = self.speeds, self.accelerations

        system_status = full_system_status["status"]
        rows = [
            (field, str(getattr(system_status, field)))
            for field in system_status._fields
        ]
        headers = ["System status", "value"]
        system_status_table = tabulate(rows, headers=headers)

        rows = [
            [field]
            + [
                str(getattr(axis_status["status"], field))
                for axis_status in full_actuators_status
            ]
            for field in self.AxisStatus._fields
        ]
        actuators_length = [
            axis_status["length"] for axis_status in full_actuators_status
        ]
        rows.append(["length (mm)"] + actuators_length)
        headers = ["Axis status"] + list(range(len(full_actuators_status)))
        actuators_status_table = tabulate(rows, headers=headers)

        pose_header = ["{0} (mm)".format(i) for i in self.Pose._fields[:3]] + [
            "{0} (deg)".format(i) for i in self.Pose._fields[3:]
        ]

        user_cs = cs["user_cs"]
        object_cs = cs["object_cs"]
        object_pose = full_system_status["object_pose"]
        platform_pose = full_system_status["platform_pose"]
        rows = [
            ["User coordinate system"] + list(user_cs),
            ["Object coordinate system"] + list(object_cs),
            ["Object pose"] + list(object_pose),
            ["Platform pose"] + list(platform_pose),
            ["Low user limits"] + list(user_limits["low_pose"]),
            ["High user limits"] + list(user_limits["high_pose"]),
            ["Low machine limits"] + list(machine_limits["low_pose"]),
            ["High machine limits"] + list(machine_limits["high_pose"]),
        ]

        headers = ["Hexapod"] + pose_header
        pose_table = tabulate(rows, headers=headers)

        rows = [
            list(specific_poses[idx][:-1]) + list(specific_poses[idx][-1])
            for idx in sorted(specific_poses)
        ]
        headers = list(self.SpecificPose._fields[:-1]) + pose_header
        specific_poses_table = tabulate(rows, headers)

        return self.DUMP_TEMPLATE.format(
            o=self,
            speeds=speeds,
            accelerations=accelerations,
            system_status=system_status_table,
            actuators_status=actuators_status_table,
            pose=pose_table,
            specific_poses=specific_poses_table,
        )
