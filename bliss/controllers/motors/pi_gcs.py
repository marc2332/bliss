# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
# Distributed under the GNU LGPLv3. See LICENSE.txt for more info.

# PI GCS

from warnings import warn

from bliss.comm.util import get_comm, get_comm_type, TCP


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
    except ValueError:
        if config.has_key("host"):
            warn("'host' keyword is deprecated. Use 'tcp' instead", DeprecationWarning)
            host = config.get("host")
            opts.setdefault("port", 50000)
            config = {"tcp": {"url": host}}
            return get_comm(config, ctype=ctype, **opts)
        elif config.has_key("serial_line"):
            serial_line = self.config.get("serial_line")
            warn(
                "'serial_line' keyword is deprecated. Use 'serial' instead",
                DeprecationWarning,
            )
            config = {"serial": {"url": serial_line}}
            return get_comm(config, ctype=ctype, **opts)
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
