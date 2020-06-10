"""Error handling."""


ERROR_DICT = {
    0: ("SUCCESS", None),
    1: ("OPEN_FILE", None),
    2: ("FILEERR", None),
    3: ("NOSECTION", None),
    4: ("FORMAT_ERROR", None),
    5: ("ILLEGAL_OPERATION", "Attempted to configure options in an illegal order"),
    6: ("FILE_RA", "File random access unable to find name-value pair"),
    7: ("SET_POS", "Error getting file position."),
    201: (
        "UNKNOWN_DECIMATION",
        "The decimation read from the hardware does not match a known value",
    ),
    202: ("SLOWLEN_OOR", "Calculated SLOWLEN value is out-of-range"),
    203: ("SLOWGAP_OOR", "Calculated SLOWGAP value is out-of-range"),
    204: ("SLOWFILTER_OOR", "Attempt to set the Peaking or Gap time s.t. P+G>31"),
    205: ("FASTLEN_OOR", "Calculated FASTLEN value is out-of-range"),
    206: ("FASTGAP_OOR", "Calculated FASTGAP value is out-of-range"),
    207: ("FASTFILTER_OOR", "Attempt to set the Peaking or Gap time s.t. P+G>31"),
    208: ("BASELINE_OOR", "Baseline filter length is out-of-range"),
    301: ("INITIALIZE", None),
    302: ("NO_ALIAS", None),
    303: ("ALIAS_EXISTS", None),
    304: ("BAD_VALUE", None),
    305: ("INFINITE_LOOP", None),
    306: ("BAD_NAME", "Specified name is not valid"),
    307: ("BAD_PTRR", "Specified PTRR is not valid for this alias"),
    308: ("ALIAS_SIZE", "Alias name has too many characters"),
    309: ("NO_MODULE", "Must define at least one module before"),
    310: ("BAD_INTERFACE", "The specified interface does not exist"),
    311: (
        "NO_INTERFACE",
        "An interface must defined before more information is specified",
    ),
    312: ("WRONG_INTERFACE", "Specified information doesn't apply to this interface"),
    313: ("NO_CHANNELS", "Number of channels for this module is set to 0"),
    314: ("BAD_CHANNEL", "Specified channel index is invalid or out-of-range"),
    315: ("NO_MODIFY", "Specified name cannot be modified once set"),
    316: ("INVALID_DETCHAN", "Specified detChan value is invalid"),
    317: ("BAD_TYPE", "The DetChanElement type specified is invalid"),
    318: ("WRONG_TYPE", "This routine only operates on detChans that are sets"),
    319: ("UNKNOWN_BOARD", "Board type is unknown"),
    320: ("NO_DETCHANS", "No detChans are currently defined"),
    321: ("NOT_FOUND", "Unable to locate the Acquisition value requested"),
    322: ("PTR_CHECK", "Pointer is out of synch when it should be valid"),
    323: (
        "LOOKING_PTRR",
        "FirmwareSet has a FDD file defined and this only works with PTRRs",
    ),
    324: ("NO_FILENAME", "Requested filename information is set to NULL"),
    325: ("BAD_INDEX", "User specified an alias index that doesn't exist"),
    326: ("NULL_ALIAS", "Null alias passed into function"),
    327: ("NULL_NAME", "Null name passed into function"),
    328: ("NULL_VALUE", "Null value passed into function"),
    329: ("NEEDS_BOARD_TYPE", "Module needs board_type"),
    330: ("UNKNOWN_ITEM", "Unknown item"),
    331: ("TYPE_REDIRECT", "Module type can not be redefined once set"),
    332: ("NO_TMP_PATH", "No FDD temporary path defined for this firmware."),
    333: ("NULL_PATH", "Specified path was NULL."),
    350: (
        "FIRM_BOTH",
        "A FirmwareSet may not contain both an FDD and seperate Firmware "
        "definitions",
    ),
    351: (
        "PTR_OVERLAP",
        "Peaking time ranges in the Firmware definitions may not overlap",
    ),
    352: (
        "MISSING_FIRM",
        "Either the FiPPI or DSP file is missing from a Firmware element",
    ),
    353: ("MISSING_POL", "A polarity value is missing from a Detector element"),
    354: ("MISSING_GAIN", "A gain value is missing from a Detector element"),
    355: ("MISSING_INTERFACE", "The interface this channel requires is missing"),
    356: ("MISSING_ADDRESS", "The epp_address information is missing for this channel"),
    357: (
        "INVALID_NUMCHANS",
        "The wrong number of channels are assigned to this module",
    ),
    358: ("INCOMPLETE_DEFAULTS", "Some of the required defaults are missing"),
    359: ("BINS_OOR", "There are too many or too few bins for this module type"),
    360: (
        "MISSING_TYPE",
        "The type for the current detector is not specified properly",
    ),
    361: ("NO_MMU", "No MMU defined and/or required for this module"),
    362: ("NULL_FIRMWARE", "No firmware set defined"),
    363: ("NO_FDD", "No FDD defined in the firmware set"),
    364: ("WRONG_DET_TYPE", "The detector type is wrong for the requested operation"),
    401: ("NOMEM", "Unable to allocate memory"),
    402: ("XERXES", "XerXes returned an error"),
    403: ("MD", "MD layer returned an error"),
    404: ("EOF", "EOF encountered"),
    405: ("XERXES_NORMAL_RUN_ACTIVE", "XerXes says a normal run is still active"),
    406: ("HARDWARE_RUN_ACTIVE", "The hardware says a control run is still active"),
    501: ("UNKNOWN", None),
    507: ("FILE_TYPE", "Improper file type specified"),
    508: ("END", "There are no more instances of the name specified. Pos set to end"),
    509: ("INVALID_STR", "Invalid string format"),
    510: ("UNIMPLEMENTED", "The routine is unimplemented in this version"),
    511: (
        "PARAM_DEBUG_MISMATCH",
        "A parameter mismatch was found with XIA_PARAM_DEBUG enabled.",
    ),
    601: (
        "NOSUPPORT_FIRM",
        "The specified firmware is not supported by this board type",
    ),
    602: ("UNKNOWN_FIRM", "The specified firmware type is unknown"),
    603: ("NOSUPPORT_VALUE", "The specified acquisition value is not supported"),
    604: ("UNKNOWN_VALUE", "The specified acquisition value is unknown"),
    605: (
        "PEAKINGTIME_OOR",
        "The specified peaking time is out-of-range for this product",
    ),
    606: (
        "NODEFINE_PTRR",
        "The specified peaking time does not have a PTRR associated with it",
    ),
    607: ("THRESH_OOR", "The specified treshold is out-of-range"),
    608: ("ERROR_CACHE", "The data in the values cache is out-of-sync"),
    609: ("GAIN_OOR", "The specified gain is out-of-range for this produce"),
    610: ("TIMEOUT", "Timeout waiting for BUSY"),
    611: ("BAD_SPECIAL", "The specified special run is not supported for this module"),
    612: ("TRACE_OOR", "The specified value of tracewait (in ns) is out-of-range"),
    613: ("DEFAULTS", "The PSL layer encountered an error creating a Defaults element"),
    614: (
        "BAD_FILTER",
        "Error loading filter info from either a FDD file or the Firmware "
        "configuration",
    ),
    615: (
        "NO_REMOVE",
        "Specified acquisition value is required for this product and can't be "
        "removed",
    ),
    616: ("NO_GAIN_FOUND", "Handel was unable to converge on a stable gain value"),
    617: ("UNDEFINED_RUN_TYPE", "Handel does not recognize this run type"),
    618: (
        "INTERNAL_BUFFER_OVERRUN",
        "Handel attempted to overrun an internal buffer boundry",
    ),
    619: (
        "EVENT_BUFFER_OVERRUN",
        "Handel attempted to overrun the event buffer boundry",
    ),
    620: (
        "BAD_DATA_LENGTH",
        "Handel was asked to set a Data length to zero for readout",
    ),
    621: ("NO_LINEAR_FIT", "Handel was unable to perform a linear fit to some data"),
    622: ("MISSING_PTRR", "Required PTRR is missing"),
    623: ("PARSE_DSP", "Error parsing DSP"),
    624: ("UDXPS", None),
    625: ("BIN_WIDTH", "Specified bin width is out-of-range"),
    626: (
        "NO_VGA",
        "An attempt was made to set the gaindac on a board that doesn't have a " "VGA",
    ),
    627: ("TYPEVAL_OOR", "Specified detector type value is out-of-range"),
    628: ("LOW_LIMIT_OOR", "Specified low MCA limit is out-of-range"),
    629: ("BPB_OOR", "bytes_per_bin is out-of-range"),
    630: ("FIP_OOR", "Specified FiPPI is out-fo-range"),
    631: ("MISSING_PARAM", "Unable to find DSP parameter in list"),
    632: ("OPEN_XW", "Error opening a handle in the XW library"),
    633: ("ADD_XW", "Error adding to a handle in the XW library"),
    634: ("WRITE_XW", "Error writing out a handle in the XW library"),
    635: ("VALUE_VERIFY", "Returned value inconsistent with sent value"),
    636: ("POL_OOR", "Specifed polarity is out-of-range"),
    637: ("SCA_OOR", "Specified SCA number is out-of-range"),
    638: ("BIN_MISMATCH", "Specified SCA bin is either too high or too low"),
    639: ("WIDTH_OOR", "MCA bin width is out-of-range"),
    640: ("UNKNOWN_PRESET", "Unknown PRESET run type specified"),
    641: ("GAIN_TRIM_OOR", "Gain trim out-of-range"),
    642: ("GENSET_MISMATCH", "Returned GENSET doesn't match the set GENSET"),
    643: ("NUM_MCA_OOR", "The specified number of MCA bins is out of range"),
    644: ("PEAKINT_OOR", None),
    645: ("PEAKSAM_OOR", None),
    646: ("MAXWIDTH_OOR", None),
    647: ("NULL_TYPE", "A NULL file type was specified"),
    648: ("GAIN_SCALE", "Gain scale factor is not valid"),
    649: ("NULL_INFO", "The specified info array is NULL"),
    650: ("UNKNOWN_PARAM_DATA", "Unknown parameter data type"),
    651: ("MAX_SCAS", "The specified number of SCAs is more then the maximum allowed"),
    652: ("UNKNOWN_BUFFER", "Requested buffer is unknown"),
    653: ("NO_MAPPING", "Mapping mode is currently not installed/enabled"),
    654: ("MAPPING_PT_CTL", "Wrong mapping point control for operation"),
    655: ("UNKNOWN_PT_CTL", "Unknown mapping point control."),
    656: ("CLOCK_SPEED", "The hardware is reporting an invalid clock speed."),
    657: ("BAD_DECIMATION", "Passed in decimation is invalid."),
    658: ("BAD_SYNCH_RUN", "Specified value for synchronous run is bad."),
    659: ("PRESET_VALUE_OOR", "Requested preset value is out-of-range."),
    660: ("MEMORY_LENGTH", "Memory length is invalid."),
    661: ("UNKNOWN_PREAMP_TYPE", "Preamp type is unknown."),
    662: ("DAC_TARGET_OOR", "The specified DAC target is out of range."),
    663: ("DAC_TOL_OOR", "The specified DAC tolerance is out of range."),
    664: ("BAD_TRIGGER", "Specified trigger setting is invalid."),
    665: ("EVENT_LEN_OOR", "The specified event length is out of range."),
    666: ("PRE_BUF_LEN_OOR", "The specified pre-buffer length is out of range."),
    667: ("HV_OOR", "The specified high voltage value is out of range."),
    668: ("PEAKMODE_OOR", "The specified peak mode is out of range."),
    669: (
        "NOSUPPORTED_PREAMP_TYPE",
        "The specified preamp type is not supported by current firmware.",
    ),
    670: (
        "ENERGYCOEF_OOR",
        "The calculated energy coefficient values are out of range.",
    ),
    671: (
        "VETO_PULSE_STEP",
        "The specified step value is too large for the Alpha pulser veto " "pulse.",
    ),
    672: ("TRIGOUTPUT_OOR", "The specified trigger signal output is out of range."),
    673: ("LIVEOUTPUT_OOR", "The specified livetime signal output is out of range."),
    674: ("UNKNOWN_MAPPING", "Unknown mapping mode value specified."),
    675: ("UNKNOWN_LIST_MODE_VARIANT", "Illegal list mode variant."),
    676: ("MALFORMED_LENGTH", "List mode upper length word is malformed."),
    677: ("CLRBUFSIZE_LENGTH", "Clear Buffer Size length is too large."),
    678: ("BAD_ELECTRODE_SIZE", "UltraLo electrode size is invalid."),
    679: ("TILT_THRESHOLD_OOR", "Specified threshold is out-of-range."),
    680: ("USB_BUSY", "Direct USB command failed due to busy USB."),
    681: ("MALFORMED_MM_RESPONSE", "UltraLo moisture meter response is malformed."),
    682: ("MALFORMED_MM_STATUS", "UltraLo moisture meter status is invalid."),
    683: ("MALFORMED_MM_VALUE", "UltraLo moisture meter value is invalid."),
    684: ("NO_EVENTS", "No events to retrieve from the event buffer."),
    701: ("XUP_VERSION", "XUP version is not supported"),
    702: ("CHKSUM", "checksum mismatch in the XUP"),
    703: ("BAK_MISSING", "Requested BAK file cannot be opened"),
    704: ("SIZE_MISMATCH", "Size read from file is incorrect"),
    705: ("NO_ACCESS", "Specified access file isn't valid"),
    706: (
        "N_FILTER_BAD",
        "The number of filter parameters in the FDD doesn't match the number "
        "requires for the hardware",
    ),
    801: ("UNIT_TEST", None),
    13009: (
        "LOW_REFRESH_RATE",
        "Histogram fixed time target is less than refresh rate",
    ),
}

DEFAULT_ERROR = "UNKNOWN_ERROR_CODE", None


class HandelError(IOError):
    def __init__(self, errno, strerror, description=None):
        self.errno = errno
        self.strerror = strerror
        self.description = description
        self.args = errno, strerror, description

    def __str__(self):
        s = "[HandelError {}] {}".format(self.errno, self.strerror)
        if self.description:
            s += ": {}".format(self.description)
        return s

    @classmethod
    def from_errno(cls, errno):
        strerror, description = ERROR_DICT.get(errno, DEFAULT_ERROR)
        return cls(errno, strerror, description)


def check_error(errno):
    if errno != 0:
        raise HandelError.from_errno(errno)
