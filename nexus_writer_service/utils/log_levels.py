import logging
from tango import LogLevel

tango_log_level = {
    logging.DEBUG: LogLevel.LOG_DEBUG,
    logging.INFO: LogLevel.LOG_INFO,
    logging.WARNING: LogLevel.LOG_WARN,
    logging.ERROR: LogLevel.LOG_ERROR,
    logging.CRITICAL: LogLevel.LOG_FATAL,
    logging.NOTSET: LogLevel.LOG_OFF,
}

tango_cli_log_level = {
    logging.DEBUG: 5,
    logging.INFO: 4,
    logging.WARNING: 3,
    logging.ERROR: 2,
    logging.CRITICAL: 1,
    logging.NOTSET: 0,
}


beacon_log_level = {
    logging.DEBUG: "DEBUG",
    logging.INFO: "INFO",
    logging.WARNING: "WARN",
    logging.ERROR: "ERROR",
    logging.CRITICAL: "ERROR",
    logging.NOTSET: "WARN",
}


log_level_name = {
    logging.DEBUG: "DEBUG",
    logging.INFO: "INFO",
    logging.WARNING: "WARNING",
    logging.ERROR: "ERROR",
    logging.CRITICAL: "CRITICAL",
    logging.NOTSET: "NOTSET",
}
