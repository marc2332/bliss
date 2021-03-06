# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
# Distributed under the GNU LGPLv3. See LICENSE.txt for more info.

"""
This module is a common base for PI controllers:
* for communication
* fro Wave generator
"""

import time
import numpy

from bliss.comm.util import get_comm, get_comm_type, TCP
from bliss.common.event import connect, disconnect
from bliss.common.utils import grouped
from bliss import global_map


def get_pi_comm(config, ctype=None, **opts):
    """
    Returns PI communication channel from configuration.
    See :func:`bliss.comm.util.get_comm` for more info.
    """
    config = config.config_dict
    if get_comm_type(config) == TCP:
        opts.setdefault("port", 50000)
    opts.setdefault("timeout", 1)
    try:
        return get_comm(config, ctype=ctype, **opts)
    except:
        raise ValueError("No communication channel found in config")


def get_error_str(err_nb):
    try:
        return pi_gcs_errors[err_nb]
    except KeyError:
        return "Unknown error : %s" % str(err_nb)


pi_gcs_errors = {
    0: "No error",
    1: "Parameter syntax error",
    2: "Unknown command",
    3: "Command length out of limits or command buffer overrun",
    4: "Error while scanning",
    5: "Unallowable move attempted on unreferenced axis,\nor move attempted \
    with servo off",
    6: "Parameter for SGA not valid",
    7: "Position out of limits",
    8: "Velocity out of limits",
    9: "Attempt to set pivot point while U,V and W not all 0",
    10: "Controller was stopped by command",
    11: "Parameter for SST or for one of the embedded scan algorithms out\
    of range",
    12: "Invalid axis combination for fast scan",
    13: "Parameter for NAV out of range",
    14: "Invalid analog channel",
    15: "Invalid axis identifier",
    16: "Unknown stage name",
    17: "Parameter out of range",
    18: "Invalid macro name",
    19: "Error while recording macro",
    20: "Macro not found",
    21: "Axis has no brake",
    22: "Axis identifier specified more than once",
    23: "Illegal axis",
    24: "Incorrect number of parameters",
    25: "Invalid floating point number",
    26: "Parameter missing",
    27: "Soft limit out of range",
    28: "No manual pad found",
    29: "No more step-response values",
    30: "No step-response values recorded",
    31: "Axis has no reference sensor",
    32: "Axis has no limit switch",
    33: "No relay card installed",
    34: "Command not allowed for selected stage(s)",
    35: "No digital input installed",
    36: "No digital output configured",
    37: "No more MCM responses",
    38: "No MCM values recorded",
    39: "Controller number invalid",
    40: "No joystick configured",
    41: "Invalid axis for electronic gearing, axis can not be slave",
    42: "Position of slave axis is out of range",
    43: "Slave axis cannot be commanded directly when electronic gearing \
    is enabled",
    44: "Calibration of joystick failed",
    45: "Referencing failed",
    46: "OPM (Optical Power Meter) missing",
    47: "OPM (Optical Power Meter) not initialized or cannot be initialized",
    48: "OPM (Optical Power Meter) Communication Error",
    49: "Move to limit switch failed",
    50: "Attempt to reference axis with referencing disabled",
    51: "Selected axis is controlled by joystick",
    52: "Controller detected communication error",
    53: "MOV! motion still in progress",
    54: "Unknown parameter",
    55: "No commands were recorded with REP",
    56: "Password invalid",
    57: "Data Record Table does not exist",
    58: "Source does not exist; number too low or too high",
    59: "Source Record Table number too low or too high",
    60: "Protected Param: current Command Level (CCL) too low",
    61: "Command execution not possible while Autozero is running",
    62: "Autozero requires at least one linear axis",
    63: "Initialization still in progress",
    64: "Parameter is read-only",
    65: "Parameter not found in non-volatile memory",
    66: "Voltage out of limits",
    67: "Not enough memory available for requested wave curve",
    68: "Not enough memory available for DDL table; DDL can not be started",
    69: "Time delay larger than DDL table; DDL can not be started",
    70: "The requested arrays have different lengths; query them separately",
    71: "Attempt to restart the generator while it is running in single \
    step mode",
    72: "Motion commands and wave generator activation are not \nallowed \
    when analog target is active",
    73: "Motion commands are not allowed when wave generator is active",
    74: "No sensor channel or no piezo channel connected to \nselected \
    axis (sensor and piezo matrix)",
    75: "Generator started (WGO) without having selected a wave table (WSL).",
    76: "Interface buffer did overrun and command couldn't be received \
    correctly",
    77: "Data Record Table does not hold enough recorded data",
    78: "Data Record Table is not configured for recording",
    79: "Open-loop commands (SVA, SVR) are not allowed when servo is on",
    80: "Hardware error affecting RAM",
    81: "Not macro command",
    82: "Macro counter out of range",
    83: "Joystick is active",
    84: "Motor is off",
    85: "Macro-only command",
    86: "Invalid joystick axis",
    87: "Joystick unknown",
    88: "Move without referenced stage",
    89: "Command not allowed in current motion mode",
    90: "No tracing possible while digital IOs are used on \nthis HW revision.\
    Reconnect to switch operation mode.",
    91: "Move not possible, would cause collision",
    92: "Stage is not capable of following the master. Check the gear \
    ratio(SRA).",
    93: "This command is not allowed while the affected axis \nor its \
    master is in motion.",
    94: "Servo cannot be switched on when open-loop joystick control \
    is enabled.",
    95: "This parameter cannot be changed in current servo mode.",
    96: "Unknown stage name",
    100: "PI LabVIEW driver reports error. See source control for details.",
    200: "No stage connected to axis",
    201: "File with axis parameters not found",
    202: "Invalid axis parameter file",
    203: "Backup file with axis parameters not found",
    204: "PI internal error code 204",
    205: "SMO with servo on",
    206: "uudecode: incomplete header",
    207: "uudecode: nothing to decode",
    208: "uudecode: illegal UUE format",
    209: "CRC32 error",
    210: "Illegal file name (must be 8-0 format)",
    211: "File not found on controller",
    212: "Error writing file on controller",
    213: "VEL command not allowed in DTR Command Mode",
    214: "Position calculations failed",
    215: "The connection between controller and stage may be broken",
    216: "The connected stage has driven into a limit switch,\ncall CLR to \
    resume operation",
    217: "Strut test command failed because of an unexpected strut stop",
    218: "While MOV! is running position can only be estimated!",
    219: "Position was calculated during MOV motion",
    230: "Invalid handle",
    231: "No bios found",
    232: "Save system configuration failed",
    233: "Load system configuration failed",
    301: "Send buffer overflow",
    302: "Voltage out of limits",
    303: "Open-loop motion attempted when servo ON",
    304: "Received command is too long",
    305: "Error while reading/writing EEPROM",
    306: "Error on I2C bus",
    307: "Timeout while receiving command",
    308: "A lengthy operation has not finished in the expected time",
    309: "Insufficient space to store macro",
    310: "Configuration data has old version number",
    311: "Invalid configuration data",
    333: "Internal hardware error",
    400: "Wave generator index error",
    401: "Wave table not defined",
    402: "Wave type not supported",
    403: "Wave length exceeds limit",
    404: "Wave parameter number error",
    405: "Wave parameter out of range",
    406: "WGO command bit not supported",
    500: 'The "red knob" is still set and disables system',
    501: 'The "red knob" was activated and still disables system -\
    reanimation required',
    502: "Position consistency check failed",
    503: "Hardware collision sensor(s) are activated",
    504: "Strut following error occurred, e.g. caused by overload or encoder\
    failure",
    555: "BasMac: unknown controller error",
    601: "not enough memory",
    602: "hardware voltage error",
    603: "hardware temperature out of range",
    1000: "Too many nested macros",
    1001: "Macro already defined",
    1002: "Macro recording not activated",
    1003: "Invalid parameter for MAC",
    1004: "PI internal error code 1004",
    1005: "Controller is busy with some lengthy operation\n(e.g. reference\
    move, fast scan algorithm)",
    1006: "Invalid identifier (invalid special characters, ...)",
    1007: "Variable or argument not defined",
    1008: "Controller is (already) running a macro",
    1009: "Invalid or missing operator for condition.\nCheck necessary\
    spaces around operator.",
    1063: "User Profile Mode: Command is not allowed, \ncheck for required\
    preparatory commands",
    1064: "User Profile Mode: First target position in User Profile\nis too\
    far from current position",
    1065: "Controller is (already) in User Profile Mode",
    1066: "User Profile Mode: Block or Data Set index out of allowed range",
    1071: "User Profile Mode: Out of memory",
    1072: "User Profile Mode: Cluster is not assigned to this axis",
    1073: "Unknown cluster identifier",
    2000: "Controller already has a serial number",
    4000: "Sector erase failed",
    4001: "Flash program failed",
    4002: "Flash read failed",
    4003: "HW match code missing/invalid",
    4004: "FW match code missing/invalid",
    4005: "HW version missing/invalid",
    4006: "FW version missing/invalid",
    4007: "FW update failed",
    4008: "FW Parameter CRC wrong",
    4009: "FW CRC wrong",
    5000: "PicoCompensation scan data is not valid",
    5001: "PicoCompensation is running, some actions can not be \nexecuted\
    during scanning/recording",
    5002: "Given axis can not be defined as PPC axis",
    5003: "Defined scan area is larger than the travel range",
    5004: "Given PicoCompensation type is not defined",
    5005: "PicoCompensation parameter error",
    5006: "PicoCompensation table is larger than maximum table length",
    5100: "Common error in Nexline firmware module",
    5101: "Output channel for Nexline can not be redefined for other usage",
    5102: "Memory for Nexline signals is too small",
    5103: "RNP can not be executed if axis is in closed loop",
    5104: "relax procedure (RNP) needed",
    5200: "Axis must be configured for this action",
    -1: "Error during com operation (could not be specified)",
    -2: "Error while sending data",
    -3: "Error while receiving data",
    -4: "Not connected (no port with given ID open)",
    -5: "Buffer overflow",
    -6: "Error while opening port",
    -7: "Timeout error",
    -8: "There are more lines waiting in buffer",
    -9: "There is no interface or DLL handle with the given ID",
    -10: "Event/message for notification could not be opened",
    -11: "Function not supported by this interface type",
    -12: "Error while sending 'echoed' data",
    -13: "IEEE488: System error",
    -14: "IEEE488: Function requires GPIB board to be CIC",
    -15: "IEEE488: Write function detected no listeners",
    -16: "IEEE488: Interface board not addressed correctly",
    -17: "IEEE488: Invalid argument to function call",
    -18: "IEEE488: Function requires GPIB board to be SAC",
    -19: "IEEE488: I/O operation aborted",
    -20: "IEEE488: Interface board not found",
    -21: "IEEE488: Error performing DMA",
    -22: "IEEE488: I/O operation started before previous operation completed",
    -23: "IEEE488: No capability for intended operation",
    -24: "IEEE488: File system operation error",
    -25: "IEEE488: Command error during device call",
    -26: "IEEE488: Serial poll-status byte lost",
    -27: "IEEE488: SRQ remains asserted",
    -28: "IEEE488: Return buffer full",
    -29: "IEEE488: Address or board locked",
    -30: "RS-232: 5 data bits with 2 stop bits is an invalid \ncombination,\
    as is 6, 7, or 8 data bits with 1.5 stop bits",
    -31: "RS-232: Error configuring the COM port",
    -32: "Error dealing with internal system resources (events, threads, ...)",
    -33: "A DLL or one of the required functions could not be loaded",
    -34: "FTDIUSB: invalid handle",
    -35: "FTDIUSB: device not found",
    -36: "FTDIUSB: device not opened",
    -37: "FTDIUSB: IO error",
    -38: "FTDIUSB: insufficient resources",
    -39: "FTDIUSB: invalid parameter",
    -40: "FTDIUSB: invalid baud rate",
    -41: "FTDIUSB: device not opened for erase",
    -42: "FTDIUSB: device not opened for write",
    -43: "FTDIUSB: failed to write device",
    -44: "FTDIUSB: EEPROM read failed",
    -45: "FTDIUSB: EEPROM write failed",
    -46: "FTDIUSB: EEPROM erase failed",
    -47: "FTDIUSB: EEPROM not present",
    -48: "FTDIUSB: EEPROM not programmed",
    -49: "FTDIUSB: invalid arguments",
    -50: "FTDIUSB: not supported",
    -51: "FTDIUSB: other error",
    -52: "Error while opening the COM port: was already open",
    -53: "Checksum error in received data from COM port",
    -54: "Socket not ready, you should call the function again",
    -55: "Port is used by another socket",
    -56: "Socket not connected (or not valid)",
    -57: "Connection terminated (by peer)",
    -58: "Can't connect to peer",
    -59: "Operation was interrupted by a nonblocked signal",
    -60: "No device with this ID is present",
    -61: "Driver could not be opened (on Vista: run as administrator!)",
    -1001: "Unknown axis identifier",
    -1002: "Number for NAV out of range--must be in [1,10000]",
    -1003: "Invalid value for SGA--must be one of 1, 10, 100, 1000",
    -1004: "Controller sent unexpected response",
    -1005: "No manual control pad installed, calls to SMA and \nrelated\
    commands are not allowed",
    -1006: "Invalid number for manual control pad knob",
    -1007: "Axis not currently controlled by a manual control pad",
    -1008: "Controller is busy with some lengthy operation (e.g. reference\
    move, fast scan algorithm)",
    -1009: "Internal error--could not start thread",
    -1010: "Controller is (already) in macro mode--command not valid in\
    macro mode",
    -1011: "Controller not in macro mode--command not valid unless macro\
    mode active",
    -1012: "Could not open file to write or read macro",
    -1013: "No macro with given name on controller, or macro is empty",
    -1014: "Internal error in macro editor",
    -1015: "One or more arguments given to function is invalid \n(empty\
    string, index out of range, ...)",
    -1016: "Axis identifier is already in use by a connected stage",
    -1017: "Invalid axis identifier",
    -1018: "Could not access array data in COM server",
    -1019: "Range of array does not fit the number of parameters",
    -1020: "Invalid parameter ID given to SPA or SPA?",
    -1021: "Number for AVG out of range--must be >0",
    -1022: "Incorrect number of samples given to WAV",
    -1023: "Generation of wave failed",
    -1024: "Motion error while axis in motion, call CLR to resume operation",
    -1025: "Controller is (already) running a macro",
    -1026: "Configuration of PZT stage or amplifier failed",
    -1027: "Current settings are not valid for desired configuration",
    -1028: "Unknown channel identifier",
    -1029: "Error while reading/writing wave generator parameter file",
    -1030: "Could not find description of wave form. Maybe WG.INI is missing?",
    -1031: "The WGWaveEditor DLL function was not found at startup",
    -1032: "The user cancelled a dialog",
    -1033: "Error from C-844 Controller",
    -1034: "DLL necessary to call function not loaded, or function not \
    found in DLL",
    -1035: "The open parameter file is protected and cannot be edited",
    -1036: "There is no parameter file open",
    -1037: "Selected stage does not exist",
    -1038: "There is already a parameter file open. Close it before opening \
    a new file",
    -1039: "Could not open parameter file",
    -1040: "The version of the connected controller is invalid",
    -1041: "Parameter could not be set with SPA--parameter not defined for \
    this controller!",
    -1042: "The maximum number of wave definitions has been exceeded",
    -1043: "The maximum number of wave generators has been exceeded",
    -1044: "No wave defined for specified axis",
    -1045: "Wave output to axis already stopped/started",
    -1046: "Not all axes could be referenced",
    -1047: "Could not find parameter set required by frequency relation",
    -1048: "Command ID given to SPP or SPP? is not valid",
    -1049: "A stage name given to CST is not unique",
    -1050: "A uuencoded file transferred did not start with 'begin' \nfollowed\
    by the proper filename",
    -1051: "Could not create/read file on host PC",
    -1052: "Checksum error when transferring a file to/from the controller",
    -1053: "The PiStages.dat database could not be found.\nThis file is \
    required to connect a stage with the CST command",
    -1054: "No wave being output to specified axis",
    -1055: "Invalid password",
    -1056: "Error during communication with OPM (Optical Power Meter),\n\
    maybe no OPM connected",
    -1057: "WaveEditor: Error during wave creation, incorrect number of\
    parameters",
    -1058: "WaveEditor: Frequency out of range",
    -1059: "WaveEditor: Error during wave creation, incorrect index for\
    integer parameter",
    -1060: "WaveEditor: Error during wave creation, incorrect index \nfor \
    floating point parameter",
    -1061: "WaveEditor: Error during wave creation, could not calculate value",
    -1062: "WaveEditor: Graph display component not installed",
    -1063: "User Profile Mode: Command is not allowed, check for \nrequired\
    preparatory commands",
    -1064: "User Profile Mode: First target position in User Profile\nis too\
    far from current position",
    -1065: "Controller is (already) in User Profile Mode",
    -1066: "User Profile Mode: Block or Data Set index out of allowed range",
    -1067: "ProfileGenerator: No profile has been created yet",
    -1068: "ProfileGenerator: Generated profile exceeds limits of one or both\
    axes",
    -1069: "ProfileGenerator: Unknown parameter ID in Set/Get Parameter\
    command",
    -1070: "ProfileGenerator: Parameter out of allowed range",
    -1071: "User Profile Mode: Out of memory",
    -1072: "User Profile Mode: Cluster is not assigned to this axis",
    -1073: "Unknown cluster identifier",
    -1074: "The installed device driver doesn't match the required version.\n\
    Please see the documentation to determine the required \
    device driver version.",
    -1075: "The library used doesn't match the required version.\nPlease see\
    the documentation to determine the required library version.",
    -1076: "The interface is currently locked by another function.\nPlease\
    try again later.",
    -1077: "Version of parameter DAT file does not match the required \
    version.\nCurrent files are available at www.pi.ws.",
    -1078: "Cannot write to parameter DAT file to store user defined\
    stage type.",
    -1079: "Cannot create parameter DAT file to store user defined stage \
    type.",
    -1080: "Parameter DAT file does not have correct revision.",
    -1081: "User stages DAT file does not have correct revision.",
}


class Communication:
    def __init__(self):
        self.sock = None

    def com_initialize(self):
        self.sock = get_pi_comm(self.config, TCP)
        global_map.register(self, children_list=[self.sock])

        # ???
        connect(self.sock, "connect", self._clear_error)

    def com_close(self):
        """
        Closes the controller socket.
        Disconnect error clearing.
        """
        if self.sock:
            self.sock.close()

        disconnect(self.sock, "connect", self._clear_error)

    def get_error(self):
        _error_number = int(self.sock.write_readline(b"ERR?\n"))
        _error_str = get_error_str(_error_number)

        return (_error_number, _error_str)

    def _clear_error(self, connected):
        if connected:
            self.get_error()  # read and clear any error

    def command(self, cmd, nb_line=1):
        """
        Method to send a command to the controller.

        Read answer if needed (ie. `cmd` contains a `?`).

        Parameters:
            <cmd>: str
                Command. Not encoded; Without terminator character.

            [<nb_line>]: int
                Number of lines expected in answer.
                For multi-lines commands (ex: IFC?) or multiple commands.

        Returns: str  ;  list of str  ; tuple of str

        Usage:
            * id = self.command("*IDN?")
            * ont = self.command("ONT? 1")
            * ans = self.command("SPA? 1 0x07000A00")
            * com_pars_list = self.command("IFC?", 5)
            * pos, vel = self.command("POS? 1\nVEL? 1", 2)

        Note:
            Does not work for single char commands (#5 #9 #24 etc.)

        """

        with self.sock.lock:
            # print("   CMD=", cmd)
            cmd = cmd.strip()
            need_reply = cmd.find("?") > -1
            cmd = cmd.encode()
            if need_reply:
                if nb_line > 1:
                    reply = self.sock.write_readlines(cmd + b"\n", nb_line)
                else:
                    reply = self.sock.write_readline(cmd + b"\n")

                if not reply:  # it's an error
                    errors = [self.name] + list(self.get_error())
                    raise RuntimeError(
                        "PI Device {0} error nb {1} => ({2})".format(*errors)
                    )

                if nb_line > 1:
                    # print("Multi-lines answer or multiple commands")
                    parsed_reply = list()
                    commands = cmd.split(b"\n")
                    if len(commands) == nb_line:
                        # print("# Many queries, one reply per query")
                        # Return a tuple of str
                        for cmd, rep in zip(commands, reply):
                            space_pos = cmd.find(b" ")
                            if space_pos > -1:
                                args = cmd[space_pos + 1 :]
                                parsed_reply.append(self._parse_reply(rep, args, cmd))
                            else:
                                # No space in cmd => no param to parse. ex: "*IDN?" "CCL?"
                                parsed_reply.append(rep)
                    else:
                        # print("# One command with reply in several lines")
                        # Return a list of str
                        space_pos = cmd.find(b" ")
                        if space_pos > -1:
                            # print("space_pos > -1")
                            args = cmd[space_pos + 1 :]
                            for arg, rep in zip(args.split(), reply):
                                parsed_reply.append(
                                    self._parse_reply(rep, arg, cmd).strip()
                                )
                        else:
                            # print("# TSP? TAD? IFC? POS? etc.")
                            # !!!! return non-parsed lines !!!
                            # ex:
                            #   pp.controller.command("POS?", nb_line=3)
                            # return:
                            #   ['A=32.9347', 'B=9.9985', 'C=15.3014']
                            for ans in reply:
                                parsed_reply.append(ans.decode().strip())
                    reply = parsed_reply
                    # print("   REPLY=", reply)
                else:
                    # Single line answer.

                    # Example: cmd = "VEL? 1"
                    space_pos = cmd.find(b" ")
                    # print(f"cmd={cmd}   space_pos={space_pos}  reply={reply} ")
                    if space_pos > -1:
                        axes_arg = cmd[
                            space_pos + 1 :
                        ]  # 2nd part of the command -> axes id.
                        reply = self._parse_reply(reply, axes_arg, cmd)
                    else:
                        reply = reply.decode()
                return reply
            else:
                # no reply expected.
                self.sock.write(cmd + b"\n")
                errno, error_message = self.get_error()

                if errno == 10:
                    # error 10 is generated by a STP or HLT or #24 command.
                    # -> we ignore it.
                    return

                if errno:
                    errors = [self.name, cmd] + [errno, error_message]
                    raise RuntimeError(
                        "Device {0} command {1} error nb {2} => ({3})".format(*errors)
                    )

    def raw_write(self, axis, com):
        com = com.encode()
        self.sock.write(b"%s\n" % com)

    def raw_write_read(self, axis, com):
        com = com.encode()
        return self.sock.write_readline(b"%s\n" % com)

    def _parse_reply(self, reply, args, cmd):
        """
        Extract pertinent value in controller's answer.
        <reply>: answer of the controller.
        <args>: arguments of the command (axes numbers)
                example: "1"    # can be "1 2" "A B" ??

        Examples of commands / answers:
        * VEL? 1              ->  1=11.0000
        * SVO? 1              ->  1=1
        * SPA? 1 0X07000000   ->  1 0x07000000=-3.00000000e+1  # NB: PI replies with '0x' in lower case.
        * SPA? 1 0X07000A00   ->  1 0x07000A00=0.00000000e+0
        * SPA? 1 0X07000000   ->  1 0x7000000=-3.00000000e+1  # NB: PI 727 replies with:
                                                                  * '0x' in lower case.
                                                                  * '0x0' changed into '0x'
        """
        u_reply = reply.upper()
        u_args = args.upper()
        args_pos = reply.find(b"=")
        if u_reply[:args_pos] != u_args:  # weird
            print("@ ---------------------------------------------------------")
            print("@ Weird thing happens with connection of %s" % self.name)
            print(f"@ command={cmd}")
            print(f"@   reply={reply} args={args} reply[:args_pos]={reply[:args_pos]}")
            print("@ ---------------------------------------------------------")
            return u_reply.decode()
        else:
            return u_reply[args_pos + 1 :].decode()


class Recorder:
    # POSSIBLE DATA TRIGGER SOURCE
    WAVEFORM = 0
    MOTION = 1
    EXTERNAL = 3
    IMMEDIATELY = 4

    def _add_recoder_enum_on_axis(self, axis):
        # POSSIBLE DATA RECORDER TYPE
        axis.TARGET_POSITION_OF_AXIS = 1
        axis.CURRENT_POSITION_OF_AXIS = 2
        axis.POSITION_ERROR_OF_AXIS = 3
        axis.CONTROL_VOLTAGE_OF_OUTPUT_CHAN = 7
        axis.DDL_OUTPUT_OF_AXIS = 13
        axis.OPEN_LOOP_CONTROL_OF_AXIS = 14
        axis.CONTROL_OUTPUT_OF_AXIS = 15
        axis.VOLTAGE_OF_OUTPUT_CHAN = 16
        axis.SENSOR_NORMALIZED_OF_INPUT_CHAN = 17
        axis.SENSOR_FILTERED_OF_INPUT_CHAN = 18
        axis.SENSOR_ELECLINEAR_OF_INPUT_CHAN = 19
        axis.SENSOR_MECHLINEAR_OF_INPUT_CHAN = 20
        axis.SLOWED_TARGET_OF_AXIS = 22

        # POSSIBLE DATA TRIGGER SOURCE
        axis.WAVEFORM = 0
        axis.MOTION = 1
        axis.EXTERNAL = 3
        axis.IMMEDIATELY = 4

    def get_data_len(self):
        """
        return how many point you can get from recorder
        """
        return int(self.command("DRL? 1"))

    def get_data_max_len(self):
        """
        return the maximum number of records
        """
        return int(self.command("SPA? 1 0x16000200"))

    def get_data(self, from_event_id=0, npoints=None, rec_table_id=None):
        """
        retrieved store data as a numpy structured array,
        struct name will be the data_type + motor name.
        i.e:
        Target_Position_of_<motor_name> or Current_Position_of_<motor_name>

        Args:
         - from_event_id from which point id you want to read
         - rec_table_id list of table you want to read, None means all
        """
        if rec_table_id is None:  # All table
            # just ask the first table because they have the same synchronization
            nb_availabe_points = int(self.command("DRL? 1"))
            nb_availabe_points -= from_event_id
            if npoints is None:
                npoints = nb_availabe_points
            else:
                npoints = min(nb_availabe_points, npoints)
            cmd = b"DRR? %d %d\n" % ((from_event_id + 1), npoints)
        else:
            rec_tables = " ".join((str(x) for x in rec_table_id))
            nb_points = self.command("DRL? %s" % rec_tables, len(rec_table_id))
            if isinstance(nb_points, list):
                nb_points = min([int(x) for x in nb_points])
            else:
                nb_points = int(nb_points)
            point_2_read = nb_points - from_event_id
            if point_2_read < 0:
                point_2_read = 0
            elif npoints is not None and point_2_read > npoints:
                point_2_read = npoints
            cmd = b"DRR? %d %d %s\n" % (from_event_id + 1, point_2_read, rec_tables)

        try:
            exception_occurred = False
            with self.sock.lock:
                self.sock._write(cmd)
                # HEADER
                header = dict()
                while 1:
                    line = self.sock.readline()
                    if not line:
                        return  # no data available
                    if line.find(b"END_HEADER") > -1:
                        break

                    key, value = (x.strip().decode() for x in line[1:].split(b"="))
                    header[key] = value

                ndata = int(header["NDATA"])
                separator = chr(int(header["SEPARATOR"])).encode()
                sample_time = float(header["SAMPLE_TIME"])
                dim = int(header["DIM"])
                column_info = dict()
                keep_axes = {
                    x.channel: x for x in self.axes.values() if hasattr(x, "channel")
                }
                for name_id in range(8):
                    try:
                        desc = header["NAME%d" % name_id]
                    except KeyError:
                        break
                    else:
                        axis_pos = desc.find("axis")
                        if axis_pos < 0:
                            axis_pos = desc.find("chan")
                        axis_id = int(desc[axis_pos + len("axis") :])
                        if axis_id in keep_axes:
                            new_desc = desc[:axis_pos] + keep_axes[axis_id].name
                            column_info[name_id] = new_desc.replace(" ", "_")

                dtype = [("timestamp", "f8")]
                dtype += [(name, "f8") for name in column_info.values()]
                data = numpy.zeros(ndata, dtype=dtype)
                data["timestamp"] = (
                    numpy.arange(from_event_id, from_event_id + ndata) * sample_time
                )
                for line_id in range(ndata):
                    line = self.sock.readline().strip()
                    values = line.split(separator)
                    for column_id, name in column_info.items():
                        data[name][line_id] = values[column_id]
                return data
        except:
            exception_occurred = True
            try:
                errno, error_message = self.get_error()
            except:
                pass
            self.sock.close()  # safe in case of ctrl-c
            raise
        finally:
            if not exception_occurred:
                errno, error_message = self.get_error()
                # If we ask data in advance, ** Out of range **
                # error is return.
                # in that case it's not an error
                if errno > 0 and errno != 17:
                    errors = [self.name, "get_data"] + [errno, error_message]
                    raise RuntimeError(
                        "Device {0} command {1} error nb {2} => ({3})".format(*errors)
                    )

    def set_recorder_data_type(self, *motor_data_type):
        """
        Configure the data recorder

        Args:
          motor_data_type should be a list of tuple with motor and datatype
          i.e: motor_data_type=[px,px.CURRENT_POSITION_OF_AXIS,
                                py,py.CURRENT_POSITION_OF_AXIS]
        """
        nb_recorder_table = len(motor_data_type) / 2
        if nb_recorder_table * 2 != len(motor_data_type):
            raise RuntimeError(
                "Argument must be grouped by 2 "
                "(motor1,data_type1,motor2,data_type2...)"
            )

        self.command("SPA 1 0x16000300 %d" % nb_recorder_table)
        max_nb_recorder = int(self.command("TNR?"))
        if nb_recorder_table > max_nb_recorder:
            raise RuntimeError(
                "Device %s too many recorder data, can only record %d"
                % (self.name, max_nb_recorder)
            )
        cmd = "DRC "
        cmd += " ".join(
            (
                "%d %s %d" % (rec_id + 1, motor.channel, data_type)
                for rec_id, (motor, data_type) in enumerate(grouped(motor_data_type, 2))
            )
        )
        self.command(cmd)

    def start_recording(self, trigger_source, value=0, recorder_rate=None):
        """
        start recording data according to what was asked to record.
        @see set_recorder_data_type

        Args:
          - trigger_source could be WAVEFORM,MOTION,EXTERNAL,IMMEDIATELY
          - value for EXTERNAL value is the trigger input line (0 mean all)
          - recorder_rate if None max speed otherwise the period in seconds
        """
        if trigger_source not in (
            self.WAVEFORM,
            self.MOTION,
            self.EXTERNAL,
            self.IMMEDIATELY,
        ):
            raise RuntimeError(
                "Device %s trigger source can only be:"
                "WAVEFORM,MOTION,EXTERNAL or IMMEDIATELY"
            )

        if recorder_rate is not None:
            cycle_time = float(self.command("SPA? 1 0xe000200"))
            rate = int(recorder_rate / cycle_time)  # should be faster than asked
        else:
            rate = 1

        self.command("RTR %d" % rate)

        nb_recorder = int(self.command("TNR?"))
        cmd = "DRT "
        cmd += " ".join(
            (
                "%d %d %d" % (rec_id, trigger_source, value)
                for rec_id in range(1, nb_recorder + 1)
            )
        )
        self.command(cmd)

    def get_recorder_data_rate(self):
        """
        return the rate of the data recording in seconds
        """
        cycle_time, rtr = self.command("SPA? 1 0xe000200\nRTR?", 2)
        return float(cycle_time) * int(rtr)
