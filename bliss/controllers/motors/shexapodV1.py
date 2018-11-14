import struct
import socket
import string
import numpy
from collections import namedtuple

from bliss.controllers.motors.shexapod import (
    ROLES,
    Pose,
    BaseHexapodError,
    BaseHexapodProtocol,
)


class HexapodV1Error(BaseHexapodError):
    pass


class TurboPmacCommand(object):
    VR_DOWNLOAD = 0x40
    VR_UPLOAD = 0xc0

    VR_PMAC_SENDLINE = 0xb0
    VR_PMAC_GETLINE = 0xb1
    VR_PMAC_FLUSH = 0xb3
    VR_PMAC_GETMEM = 0xb4
    VR_PMAC_SETMEM = 0xb5
    VR_PMAC_SETBIT = 0xba
    VR_PMAC_SETBITS = 0xbb
    VR_PMAC_PORT = 0xbe
    VR_PMAC_GETRESPONSE = 0xbf
    VR_PMAC_READREADY = 0xc2
    VR_CTRL_RESPONSE = 0xc4
    VR_PMAC_GETBUFFER = 0xc5
    VR_PMAC_WRITEBUFFER = 0xc6
    VR_PMAC_WRITEERROR = 0xc7
    VR_FWDOWNLOAD = 0xcb
    VR_IPADDRESS = 0xe0

    def __init__(self, comm):
        self.__s = comm
        self.__data = struct.Struct("BBHHH")
        self.__read_version()

    def __call__(self, command, convtype=None):
        return self.__send(
            self.VR_DOWNLOAD, self.VR_PMAC_GETRESPONSE, command, convtype
        )

    def request(self, command, convtype=None):
        return self.__send(
            self.VR_DOWNLOAD, self.VR_PMAC_GETRESPONSE, command, convtype
        )

    def __read_version(self):
        pmactype = self.request("TYPE")
        pmacvers = self.request("VERSION")
        self.__version = "{0} - version {1}".format(pmactype, pmacvers)

    def version(self):
        return self.__version

    def __send(self, requestType, request, command, convtype):
        data = self.__data.pack(requestType, request, 0, 0, socket.htons(len(command)))
        raw = self.__s.write_readline(data + command, eol="\x06")
        if len(raw):
            ans = map(string.strip, raw.split("\r")[:-1])
            if convtype is not None:
                ans = map(convtype, ans)
            if len(ans) > 1:
                return ans
            else:
                return ans[0]
        return None


class HexapodProtocolV1(BaseHexapodProtocol):

    DEFAULT_PORT = 1025

    MACHINE_CS = 32
    USER_CS = 33

    SYSTEM_STATUS_FIELDS = (
        "error",
        "ready",
        "in_position",
        "control",
        "homing_done",
        "brake_control",
        "emergency_stop_pressed",
        "following_warning",
        "following_error",
        "actuators_out",
        "amplifier_error",
        "encoder_error",
        "phasing_error",
        "homing_error",
        "kinematic_error",
        "abort_input_error",
        "memory_error",
        "homing_virtual",
        "moving",
    )

    SystemStatus = namedtuple("SystemStatus", SYSTEM_STATUS_FIELDS)

    AXIS_STATUS_FIELDS = (
        "in_position",
        "control",
        "homing_done",
        "homing_hardware_input",
        "positive_hardware_lmit",
        "negative_hardware_limit",
        "brake_control",
        "following_warning",
        "following_error",
        "actuators_out",
        "amplifier_error",
        "encoder_error",
        "phasing_error",
    )

    AxisStatus = namedtuple("AxisStatus", AXIS_STATUS_FIELDS)

    def __init__(self, config):
        BaseHexapodProtocol.__init__(self, config)
        self.pmac = TurboPmacCommand(self.comm)
        self.__read_api_version()
        self.__set_pose = None

    def __read_api_version(self):
        self.pmac("&2 Q20=55")
        self.wait_command()
        ans = self.pmac("&2 Q80,4,1")
        self.__api_version = "{0} [{1}]".format(*ans)
        self.__serial_number = "{2} [{3}]".format(*ans)

    @property
    def api_version(self):
        return self.__api_version

    @property
    def serial_number(self):
        return self.__serial_number

    def wait_command(self):
        ack = 1
        while ack >= 1:
            ack = self.pmac("&2 Q20", int)
        return ack

    @property
    def control(self):
        return self.system_status.control

    @control.setter
    def control(self, control):
        status = self.system_status
        curr_control = status.control
        if control and not curr_control:
            # control ON
            self.pmac("&2 Q20=3")
            err = self.wait_command()
            if err == -1:
                raise HexapodV1Error(
                    "Command ignored (emergency button engaged or ctrl in error state)"
                )
            elif err == -2:
                raise HexapodV1Error("Control of the servo motors has failed")
        elif not control and curr_control:
            # control OFF
            self.pmac("&2 Q20=4")
            self.wait_command()

    def _stop(self):
        self.pmac("&2 Q20=2")

    def _homing(self, async_=False):
        self.pmac("&2 Q20=1")
        if async_ is False:
            self.wait_command()

    def _reset(self):
        self.pmac("$$$")

    def _move(self, pose, async_=False):
        set_pose_dict = self.set_pose._asdict()
        # any coordinate which is None will be replaced by the latest set_pose
        pose = Pose(*[set_pose_dict[i] if v is None else v for i, v in enumerate(pose)])
        set_pos_cmd = "Q70=0 Q71=%f Q72=%f Q73=%f Q74=%f Q75=%f Q76=%f Q20=11" % (
            pose.tx,
            pose.ty,
            pose.tz,
            pose.rx,
            pose.ry,
            pose.rz,
        )
        self.pmac(set_pos_cmd)
        err = self.wait_command()
        if err == -1:
            raise HexapodV1Error("Command ignored. Conditions of move not met.")
        elif err == -1:
            raise HexapodV2Error("Invalid movement command.")

    def is_moving(self):
        pass

    def __to_status(self, status, klass):
        istatus = int(status)
        return klass(*[bool(istatus & (1 << i)) for i in range(len(klass._fields))])

    @property
    def system_status(self):
        status = self.pmac("&2 Q36", int)
        conv_status = self.__to_status(status, self.SystemStatus)
        moving = (
            conv_status.control
            and not conv_status.error
            and not conv_status.in_position
        )
        return conv_status._replace(moving=moving)

    @property
    def axis_status(self):
        status = self.pmac("&2 Q30,6,1", int)
        conv_status = [self.__to_status(x, self.AxisStatus) for x in status]
        return conv_status

    @property
    def set_pose(self):
        if self.__set_pose is None:
            self.__set_pose = self.object_pose
        return self.__set_pose

    @property
    def object_pose(self):
        pos_user = self.pmac("&2 Q53,6,1", float)
        return Pose(*pos_user)

    @property
    def platform_pose(self):
        pos_mach = self.pmac("&2 Q47,6,1", float)
        return Pose(*pos_mach)

    def _user_and_object_cs(self):
        self.pmac("&2 Q20=31")
        self.wait_command()
        all_cs = self.pmac("&2 Q80,12,1", float)
        user_cs = Pose(*all_cs[0:6])
        object_cs = Pose(*all_cs[6:12])
        return dict(user_cs=user_cs, object_cs=object_cs)

    @property
    def user_cs(self):
        return self._user_and_object_cs()["user_cs"]

    @property
    def object_cs(self):
        return self._user_and_object_cs()["object_cs"]

    def _cs_limits(self, cs):
        self.pmac("&2 Q20=%d" % cs)
        self.wait_command()
        limits = self.pmac("&2 Q80,13,1", float)
        low_limits = [limits[x] for x in range(0, 12, 2)]
        high_limits = [limits[x] for x in range(1, 12, 2)]
        low_pose = Pose(*low_limits)
        high_pose = Pose(*high_limits)
        return dict(low_limits=low_pose, high_limits=high_pose)

    @property
    def user_limits(self):
        return self._cs_limits(self.USER_CS)

    @property
    def machine_limits(self):
        return self._cs_limits(self.MACHINE_CS)

    def _cs_limits_enabled(self, cs):
        self.pmac("&2 Q20=34" % cs)
        self.wait_command()
        enabled = self.pmac("&2 Q80", bool)
        if cs == self.MACHINE_CS:
            return enabled == 1 or enabled == 3
        else:
            return enabled == 2 or enabled == 3

    @property
    def user_limits_enabled(self):
        return self._cs_limits_enabled(self.USER_CS)

    @property
    def machine_limits_enabled(self):
        return self._cs_limits_enabled(self.MACHINE_CS)

    def speeds(self):
        self.pmac("&2 Q20 35")
        self.wait_command()
        speeds = self.pmac("&2 Q86,6,1", float)
        return dict(
            tspeed=speeds[0],
            rspeed=speeds[1],
            min_tspeed=speeds[2],
            max_tspeed=speeds[4],
            min_rspeed=speeds[3],
            max_rspeed=speeds[5],
        )

    @property
    def tspeed(self):
        return self.speeds()["tspeed"]

    @property
    def rspeed(self):
        return self.speeds()["rspeed"]

    DUMP_STATUS_TEMPLATE = """\
Symetrie Hexapode
API version   : {api_version}
Serial Number : {serial_number}

{system_status}

{axis_status}
"""

    def dump_status(self):
        infos = {}
        infos["api_version"] = self.api_version
        infos["serial_number"] = self.serial_number

        system_status = self.system_status
        rows = [
            (field, str(getattr(system_status, field)))
            for field in system_status._fields
        ]
        heads = ["System Status", "Value"]
        infos["system_status"] = tabulate(rows, headers=heads)

        axis_status = self.axis_status
        rows = [
            [field] + [str(getattr(one_axis, field)) for one_axis in axis_status[0:6]]
            for field in axis_status[0]._fields
        ]
        heads = Pose._fields
        infos["axis_status"] = tabulate(rows, headers=heads)

        return self.DUMP_STATUS_TEMPLATE.format(**infos)

    DUMP_POSITION_TEMPLATE = """\
{positions}

Translation Speed : {speeds[tspeed]} mm/s (min= {speeds[min_tspeed]}; max= {speeds[max_rspeed]})
Rotation Speed    : {speeds[rspeed]} deg/s (min= {speeds[min_rspeed]}; max= {speeds[max_rspeed]})
"""

    def dump_position(self):
        user_cs = self.user_cs
        object_cs = self.object_cs
        object_pose = self.object_pose
        platform_pose = self.platform_pose
        user_limits = self.user_limits
        machine_limits = self.machine_limits

        heads = (
            ["Hexapode"]
            + ["{0} (mm)".format(i) for i in self.Pose._fields[:3]]
            + ["{0} (deg)".format(i) for i in self.Pose._fields[3:]]
        )

        rows = [
            ["User coordinate system"] + list(user_cs),
            ["Object coordinate system"] + list(object_cs),
            ["Object pose"] + list(object_pose),
            ["Platform pose"] + list(platform_pose),
            ["High user limits"] + list(user_limits["high_limits"]),
            ["Low user limits"] + list(user_limits["low_limits"]),
            ["High machine limits"] + list(machine_limits["high_limits"]),
            ["Low machine limits"] + list(machine_limits["low_limits"]),
        ]

        positions = tabulate(rows, headers=heads)

        speeds = self.speeds()

        return self.DUMP_POSITION_TEMPLATE.format(positions=positions, speeds=speeds)

    def dump(self):
        return self.dump_status() + "\n" + self.dump_position()
