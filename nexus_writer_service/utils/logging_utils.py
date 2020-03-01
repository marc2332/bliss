# -*- coding: utf-8 -*-
#
# This file is part of the nexus writer service of the BLISS project.
#
# Code is maintained by the ESRF Data Analysis Unit.
#
# Original author: Wout de Nolf
#
# Copyright (c) 2015-2020 ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import sys
import io
import logging
from logging.handlers import RotatingFileHandler
import argparse
from ..patching import monkey


def iter_rawio(obj, lastresort=False):
    if hasattr(obj, "handlers"):
        if obj.hasHandlers:
            for h in obj.handlers:
                for o in iter_rawio(h):
                    yield o
            if obj.propagate and obj.parent is not None:
                for o in iter_rawio(obj.parent):
                    yield o
        elif lastresort:
            # By default sys.stderr with WARNING level
            for o in iter_rawio(logging.lastResort):
                yield o
    elif hasattr(obj, "logger"):
        for o in iter_rawio(obj.logger):
            yield o
    elif hasattr(obj, "stream"):
        for o in iter_rawio(obj.stream):
            yield o
    elif hasattr(obj, "buffer"):
        for o in iter_rawio(obj.buffer):
            yield o
    elif hasattr(obj, "raw"):
        for o in iter_rawio(obj.raw):
            yield o
    else:
        yield obj


class LoggingRawIO(io.RawIOBase):
    """
    Raw IO buffer that redirects writes to a logger instance.
    """

    def __init__(self, logger, log_level=logging.INFO):
        self.logger = logger
        self.log_level = log_level

    @property
    def log_level(self):
        # Make sure the output is always visible
        return max(self.logger.getEffectiveLevel(), self._log_level)

    @log_level.setter
    def log_level(self, value):
        self._log_level = value

    @property
    def name(self):
        return str(self.logger)

    def write(self, buf):
        """
        This is write(... + terminator) + flush on the logger handlers
        """
        written = len(buf)
        if isinstance(buf, memoryview):
            buf = buf.tobytes()
        self.logger.log(self.log_level, buf.decode())
        return written

    def writable(self):
        return True


def textstream_wrapper(logger, log_level=logging.INFO):
    """
    Create a stream wrapper (like sys.stdout) around a logger

    Note that if the logger writes to the stream with a terminator,
    stream.writer("abc") becomes stream.writer("abc\n"). It also flushes.
    """
    raw = LoggingRawIO(logger, log_level=log_level)
    return io.TextIOWrapper(io.BufferedWriter(raw))


# Stream that sends INFO messages to the output logger
_out_logger = logging.getLogger("OUT")
_out_logger.propagate = False
_out_logger.setLevel(logging.DEBUG)
out_stream = textstream_wrapper(_out_logger, logging.INFO)
# Stream that sends ERROR messages to the error logger
_err_logger = logging.getLogger("ERR")
_err_logger.propagate = False
_err_logger.setLevel(logging.WARNING)
err_stream = textstream_wrapper(_err_logger, logging.ERROR)


def print_out(*objects, file=None, flush=True, **kwargs):
    """
    Like builtin print but print to _out_logger by default
    """
    if file is None:
        file = out_stream
    print(*objects, file=file, flush=flush, **kwargs)


def print_err(*objects, file=None, flush=True, **kwargs):
    """
    Like builtin print but print to _err_logger by default
    """
    if file is None:
        file = err_stream
    print(*objects, file=file, flush=flush, **kwargs)


def out_filter(level):
    """
    For logging handlers that show all but error messages

    :param int level:
    :returns: bool
    """
    return level < logging.WARNING


def err_filter(level):
    """
    For logging handlers that only show error messages

    :param int level:
    :returns: bool
    """
    return level >= logging.WARNING


def add_cli_args(parser, default="WARNING"):
    parser.add_argument(
        "--log",
        default=default,
        type=str.upper,
        dest="level",
        help="Log level ({} by default)".format(repr(default)),
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
    )
    parser.add_argument(
        "--logfile", default="", type=str, help="Logging output to this file"
    )
    parser.add_argument(
        "--logfileout", default="", type=str, help="Logging level<WARNING to this file"
    )
    parser.add_argument(
        "--logfileerr", default="", type=str, help="Logging level>=WARNING to this file"
    )
    parser.add_argument(
        "--filesize",
        dest="maxMBytes",
        default=5,
        type=float,
        help="Maximal file size in MB",
    )
    parser.add_argument(
        "--filebackups",
        dest="backupCount",
        default=9,
        type=int,
        help="Maximal backups of each file",
    )
    parser.add_argument(
        "--nologstdout",
        action="store_false",
        dest="logstdout",
        help="No logging output to stdout",
    )
    # Not safe
    # parser.add_argument(
    #    "--nologstderr",
    #    action="store_false",
    #    dest="logstderr",
    #    help="No logging output to stderr",
    # )
    parser.add_argument(
        "--redirectstdout",
        action="store_true",
        help="Redirect stdout to a dedicated logger",
    )
    parser.add_argument(
        "--redirectstderr",
        action="store_true",
        help="Redirect stderr to a dedicated logger",
    )


def cliconfig(logger, default="WARNING", help=False):
    """Configure logging from command-line options
    """
    parser = argparse.ArgumentParser(add_help=help)
    add_cli_args(parser, default=default)
    args, _ = parser.parse_known_args()
    args.logstderr = True
    kwargs = {name: getattr(args, name) for name in vars(args)}
    config(logger, **kwargs)


DEFAULT_FORMAT = "%(levelname)s %(asctime)s %(name)s: %(message)s"


def config(
    logger,
    level=None,
    logfile=None,
    logfileout=None,
    logfileerr=None,
    logstdout=True,
    logstderr=True,
    redirectstdout=False,
    redirectstderr=False,
    maxMBytes=5,
    backupCount=9,
):
    # Set the logger's log level: filters messages before
    # sending it the the handlers, which themselves can
    # have a filter
    logger.setLevel(level.upper())

    # Redirect stdout and stderr to out_stream and err_stream respectively
    monkey.patch("std", stdout=redirectstdout, stderr=redirectstderr)
    org_stdout = monkey.original(sys, "stdout")
    org_stderr = monkey.original(sys, "stderr")

    # logger output handler ...
    kwargs = {
        "maxMBytes": maxMBytes,
        "backupCount": backupCount,
        "terminator": True,
        "filter_func": None,
        "formatter": True,
        "fmt": DEFAULT_FORMAT,
    }

    # - all messages to ...
    kwargs["filter_func"] = None
    if logfile:
        add_filehandler(logger, logfile, **kwargs)

    # - all but error messages to ...
    kwargs["filter_func"] = out_filter
    if logstdout:
        add_streamhandler(logger, org_stdout, **kwargs)
    if logfileout:
        add_filehandler(logger, logfileout, **kwargs)

    # - all error messages to ...
    kwargs["filter_func"] = err_filter
    if logstderr:
        add_streamhandler(logger, org_stderr, **kwargs)
    if logfileerr:
        add_filehandler(logger, logfileerr, **kwargs)

    # output and error logger output handlers ...
    kwargs = {
        "maxMBytes": maxMBytes,
        "backupCount": backupCount,
        "terminator": False,
        "filter_func": None,  # already done by the loggers
        "formatter": False,
        "fmt": "%(name)s: %(message)s",
    }

    # - output and error logger to ...
    if logfile:
        add_filehandler(_out_logger, logfile, **kwargs)
        add_filehandler(_err_logger, logfile, **kwargs)

    # - output logger to ...
    if logstdout:
        add_streamhandler(_out_logger, org_stdout, **kwargs)
    if logfileout:
        add_filehandler(_out_logger, logfileout, **kwargs)

    # - error logger to ...
    if logstderr:
        add_streamhandler(_err_logger, org_stderr, **kwargs)
    if logfileerr:
        add_filehandler(_err_logger, logfileerr, **kwargs)


class StreamHandlerNT(logging.StreamHandler):
    terminator = ""


class FileHandlerNT(logging.FileHandler):
    terminator = ""


class RotatingFileHandlerNT(RotatingFileHandler):
    terminator = ""


def add_streamhandler(
    logger, stream, terminator=True, maxMBytes=None, backupCount=None, **kwargs
):
    """Direct logger output to a stream
    """
    if logger.hasHandlers:
        add = set(iter_rawio(stream))
        existing = set(iter_rawio(logger))
        if not add - existing:
            return
    if terminator:
        outputhandler = logging.StreamHandler(stream)
    else:
        outputhandler = StreamHandlerNT(stream)
    _add_outputhandler(logger, outputhandler, **kwargs)
    return outputhandler


def add_filehandler(
    logger, filename, terminator=True, maxMBytes=5, backupCount=9, **kwargs
):
    """Direct logger output to a file
    """
    filename = os.path.abspath(filename)
    if logger.hasHandlers:
        existing = set(stream.name for stream in iter_rawio(logger))
        if filename in existing:
            return
    if maxMBytes:
        maxBytes = maxMBytes * 1024 * 1024
        if terminator:
            outputhandler = RotatingFileHandler(
                filename, maxBytes=maxBytes, backupCount=backupCount
            )
        else:
            outputhandler = RotatingFileHandlerNT(
                filename, maxBytes=maxBytes, backupCount=backupCount
            )
    else:
        if terminator:
            outputhandler = logging.FileHandler(filename)
        else:
            outputhandler = FileHandlerNT(filename)
    _add_outputhandler(logger, outputhandler, **kwargs)
    return outputhandler


def _add_outputhandler(
    logger, outputhandler, formatter=False, filter_func=None, fmt=DEFAULT_FORMAT
):
    """Direct logger output to an output handler
    """
    if formatter:
        _add_formatting(outputhandler, fmt=fmt)
    if filter_func is not None:
        _add_levelfilter(outputhandler, filter_func)
    logger.addHandler(outputhandler)


def _add_formatting(outputhandler, fmt=DEFAULT_FORMAT):
    """Define format of the logger output
    """
    formatter = logging.Formatter(fmt, "%Y-%m-%d %H:%M:%S")
    outputhandler.setFormatter(formatter)


def _add_levelfilter(outputhandler, level_filter):
    """Filter of the logger output
    """

    class Filter(logging.Filter):
        def filter(self, record):
            return level_filter(record.levelno)

    outputhandler.addFilter(Filter())


def getLogger(name, filename, **kwargs):
    if name == "__main__":
        logname = filename
    else:
        logname = name
    logger = logging.getLogger(logname)
    if name == "__main__":
        cliconfig(logger, **kwargs)
    return logger


class CustomLogger(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        return "[{}] {}".format(str(self.extra), msg), kwargs


def filestream(name, filename, **kwargs):
    """Useful for rollover files
    """
    logger = logging.getLogger(name)
    logger.propagate = False
    logger.setLevel(logging.INFO)
    add_filehandler(logger, filename, terminator=False, **kwargs)
    return textstream_wrapper(logger, logging.INFO)


def log(logger, msg, force=True):
    """
    :param logger: use the default stdout logger when None
    :param str msg:
    :param bool force: visible regardless of the log level
    """
    if logger is None:
        print_out(msg)
    else:
        if force:
            level = max(logger.getEffectiveLevel(), logging.INFO)
        else:
            level = logging.INFO
        logger.log(level, msg)
