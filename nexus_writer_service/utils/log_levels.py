import logging
from tango import LogLevel

# tango_log_level = {
#    logging.DEBUG: LogLevel.LOG_DEBUG,
#    logging.INFO: LogLevel.LOG_INFO,
#    logging.WARNING: LogLevel.LOG_WARN,
#    logging.ERROR: LogLevel.LOG_ERROR,
#    logging.CRITICAL: LogLevel.LOG_FATAL,
#    logging.NOTSET: LogLevel.LOG_OFF,
# }

tango_log_level = {
    logging.DEBUG: 600,
    logging.INFO: 500,
    logging.WARNING: 400,
    logging.ERROR: 300,
    logging.CRITICAL: 200,
    logging.NOTSET: 100,
}

itango_log_level = {v: k for k, v in tango_log_level.items()}

tango_cli_log_level = {
    logging.DEBUG: 5,
    logging.INFO: 4,
    logging.WARNING: 3,
    logging.ERROR: 2,
    logging.CRITICAL: 1,
    logging.NOTSET: 0,
}

itango_cli_log_level = {v: k for k, v in tango_cli_log_level.items()}

beacon_log_level = {
    logging.DEBUG: "DEBUG",
    logging.INFO: "INFO",
    logging.WARNING: "WARN",
    logging.ERROR: "ERROR",
    logging.CRITICAL: "ERROR",
    logging.NOTSET: "WARN",
}

ibeacon_log_level = {v: k for k, v in beacon_log_level.items()}

log_level_name = {
    logging.DEBUG: "DEBUG",
    logging.INFO: "INFO",
    logging.WARNING: "WARNING",
    logging.ERROR: "ERROR",
    logging.CRITICAL: "CRITICAL",
    logging.NOTSET: "NOTSET",
}

ilog_level_name = {v: k for k, v in log_level_name.items()}
