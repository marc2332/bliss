# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import sys
import logging
import logging.handlers
from contextlib import contextmanager
import re
from fnmatch import fnmatchcase
import networkx as nx
import weakref
import gevent
from time import time

from bliss.common.proxy import Proxy
from bliss.common.mapping import format_node, map_id
from bliss import global_map, current_session


__all__ = [
    # Destination: beacon and the user
    "log_debug",
    "log_debug_data",
    "log_info",
    "log_warning",
    "log_error",
    "log_critical",
    "log_exception",
    # Destination: the electronic logbook
    "elog_print",
    "elog_debug",
    "elog_info",
    "elog_warning",
    "elog_error",
    "elog_critical",
    # Destination: the user
    "user_print",
    "user_debug",
    "user_info",
    "user_warning",
    "user_error",
    "user_critical",
    # Utilities:
    "get_logger",
    "set_log_format",
    "hexify",
    "asciify",
]


def asciify(in_str: str) -> str:
    """
    Helper function.

    Gives a convenient representation of a bytestring:
    * Chars with value under 31 and over 127 are represented as hex
    * Otherwise represented as ascii

    Returns:
        str: formatted bytestring
    """
    try:
        return "".join(map(_ascii_format, in_str))
    except Exception:
        return in_str


def _ascii_format(ch):
    if ord(ch) > 31 and ord(ch) < 127:
        return ch
    else:
        return "\\x%02x" % ord(ch)


def hexify(in_str: str) -> str:
    """
    Helper function.

    Represents the given string in hexadecimal

    Returns:
        str: formatted hex
    """
    return "".join(map(_hex_format, in_str))


def _hex_format(ch):
    if isinstance(ch, int):
        # given a byte
        return "\\x%02x" % ch
    # given a string of one char
    return "\\x%02x" % ord(ch)


def get_logger(instance):
    """
    Provides a way to retrieve the logger for a give instance.

    Keep in mind that if the instance is not yet registered in the map
    this function will add it automatically.

    Returns:
        BlissLogger instance for the specific instance
    """
    if isinstance(instance, Proxy):
        instance = instance.__wrapped__
    try:
        node = global_map[instance]
    except KeyError:
        global_map.register(instance)
        node = global_map[instance]

    logger_version = node.get("_logger_version")
    node_version = node["version"]
    # check if the node hasn't been re-parent
    if node_version == logger_version:
        return node["_logger"]
    else:  # update the logger
        logger = node.get("_logger")
        logger_name = create_logger_name(
            global_map.G, map_id(instance)
        )  # get name from map
        if logger:
            existing_logger_name = logger.name
            # the logger exists, update the name if necessary
            if existing_logger_name != logger_name:
                manager = logger.manager
                manager.loggerDict.pop(existing_logger_name, None)
                logger.name = logger_name
                manager.loggerDict[logger.name] = logger
                manager._fixupParents(logger)
        else:
            # if the logger does not exist create it
            # use our own Logger class
            with bliss_logger():
                logger = logging.getLogger(logger_name)
                node["_logger"] = logger

        node["_logger_version"] = node_version
        return logger


LOG_DOCSTRING = """
Print a log message associated to a specific instance.

Normally instance is self if we are inside a class, but could
be any instance that you would like to log.
Note that the instance will be registered automatically
with the device map if not already registered.\n\n

Args:
    msg: string containing the log message
"""


def log_debug(instance, msg, *args, **kwargs):
    __doc__ = LOG_DOCSTRING + "Log level: DEBUG"
    logger = get_logger(instance)
    logger.debug(msg, *args, **kwargs)


def log_debug_data(instance, msg, *args):
    """
    Convenient function to print log messages and associated data.

    Usually useful to debug low level communication like serial and sockets.

    Properly represents:
        bytestrings/strings to hex or ascii
        dictionaries

    The switch beetween a hex or ascii representation can be done
    with the function set_log_format

    Args:
        msg: the message
        args: the last of these should be the data, the previous are %-string
              to be injected into the message
    """
    logger = get_logger(instance)
    logger.debug_data(msg, *args)


def log_info(instance, msg, *args, **kwargs):
    __doc__ = LOG_DOCSTRING + "Log level: INFO"
    logger = get_logger(instance)
    logger.info(msg, *args, **kwargs)


def log_warning(instance, msg, *args, **kwargs):
    __doc__ = LOG_DOCSTRING + "Log level: WARNING"
    logger = get_logger(instance)
    logger.warning(msg, *args, **kwargs)


def log_error(instance, msg, *args, **kwargs):
    __doc__ = LOG_DOCSTRING + "Log level: ERROR"
    logger = get_logger(instance)
    logger.error(msg, *args, **kwargs)


def log_critical(instance, msg, *args, **kwargs):
    __doc__ = LOG_DOCSTRING + "Log level: CRITICAL"
    logger = get_logger(instance)
    logger.critical(msg, *args, **kwargs)


def log_exception(instance, msg, *args, **kwargs):
    __doc__ = LOG_DOCSTRING + "Log level: ERROR with added exception trace"
    logger = get_logger(instance)
    logger.exception(msg, *args, **kwargs)


def set_log_format(instance, frmt):
    """
    This command changes the output format of log_debug_data.

    Args:
        instance: instance of a device
        frmt: 'ascii' or 'hex'
    """
    logger = get_logger(instance)
    try:
        if frmt.lower() == "ascii":
            logger.set_ascii_format()
        elif frmt.lower() == "hex":
            logger.set_hex_format()
    except AttributeError as exc:
        exc.message = "only 'ascii' and 'hex' are valid formats"
        raise


def elogbook_filter(record):
    """Checks whether an electronic logbook is available.
    """
    if current_session:
        try:
            elogbook = current_session.scan_saving.elogbook
        except AttributeError:
            # Data policy is not initialized
            return False
        return elogbook is not None
    else:
        # No active session -> no notion of data policy
        return False


class PrintFormatter(logging.Formatter):
    """Adds the level name as a prefix for messages with WARNING level or higher.
    """

    def format(self, record):
        msg = record.getMessage()
        if not getattr(record, "msg_type", None) and record.levelno >= logging.WARNING:
            msg = record.levelname + ": " + msg
        return msg


class PrintHandler(logging.Handler):
    """Redirect log records to `print`. By default the output stream is
    sys.stdout or sys.stderr depending on the error level.

    Optional: to modify the default print arguments, you can add the
    `print_kwargs` attribute to the log record.
    """

    _DEFAULT_PRINT_KWARGS = {"flush": True, "end": "\n", "file": None}

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.setFormatter(PrintFormatter())

    def emit(self, record):
        msg = self.format(record)
        kwargs = self._DEFAULT_PRINT_KWARGS.copy()
        kwargs.update(getattr(record, "print_kwargs", {}))
        if kwargs["file"] is None:
            if record.levelno >= logging.WARNING:
                kwargs["file"] = sys.stderr
            else:
                kwargs["file"] = sys.stdout
        print(msg, **kwargs)


class ElogHandler(logging.Handler):
    """Redirect log records to the electronic logbook. The default message
    type depends on the record's log level.

    Optional: to overwrite the default message type, you add the `msg_type`
    attribute to the log record.
    """

    _MSG_TYPES = {
        logging.DEBUG: "debug",
        logging.INFO: "info",
        logging.WARNING: "warning",
        logging.ERROR: "error",
        logging.CRITICAL: "critical",
    }

    _LAST_FAILURE_EPOCH = 0
    _LOG_ERROR_DELAY = 60

    def emit(self, record):
        msg = self.format(record)
        msg_type = getattr(record, "msg_type", None)
        if not msg_type:
            msg_type = self._MSG_TYPES.get(record.levelno, None)
        try:
            elogbook = current_session.scan_saving.elogbook
            # Do not try sending when the server is offline or not
            # responsive enough. Otherwise Bliss will be slowed down
            # too much.
            elogbook.ping(timeout=1)
            # Send message with default timeout of 10 seconds
            elogbook.send_message(msg, msg_type=msg_type)
            self._LAST_FAILURE_EPOCH = 0
        except Exception as e:
            time_since_last = time() - self._LAST_FAILURE_EPOCH
            if time_since_last > self._LOG_ERROR_DELAY:
                self._LAST_FAILURE_EPOCH = time()
                err_msg = f"Electronic logbook failed ({e})"
                user_error(err_msg)


class ForcedLogger(logging.Logger):
    """Logger with an additional `forced_log` method which makes sure the message
    is always send to the handlers, regardless of the level.
    """

    def forced_log(self, *args, **kw):
        """Log with INFO level or higher to ensure the message is not filtered
        out by the logger's log level. Note that the handler's log level may
        still filter out the message for that particular handler.
        """
        level = max(self.getEffectiveLevel(), logging.INFO)
        self.log(level, *args, **kw)

    def _set_msg_type(self, kw, msg_type):
        """Add message type to the resulting record. Often useful before
        calling `forced_log`.
        """
        extra = kw.setdefault("extra", {})
        if not extra.get("msg_type"):
            extra["msg_type"] = msg_type


class PrintLogger(ForcedLogger):
    """Logger with a `print` method which takes the same arguments as the
    builtin `print`. It adds attribute `print_kwargs` to the log record.
    """

    def print(self, *args, **kw):
        """Always send to the handlers, regardless of the log level
        """
        sep = kw.get("sep", " ")
        msg = sep.join((str(arg) for arg in args))

        keys = ["file", "end", "flush", "sep"]  # built-in print API
        extra = kw.get("extra", {})
        extra["print_kwargs"] = {k: kw[k] for k in keys if k in kw}

        self._set_msg_type(kw, "print")
        self.forced_log(msg, extra=extra)


class ElogLogger(ForcedLogger):
    """Logger with additional `comment` and `command` methods. These methods
    add the attribute `msg_type` to the log record.

    It also adds a filter for the `command` messages.
    """

    _IGNORED_COMMANDS = {"elog_print("}

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.addFilter(self._command_filter)

    @classmethod
    def _command_filter(cls, record):
        if getattr(record, "msg_type", None) == "command":
            msg = record.getMessage()
            if any(msg.startswith(s) for s in cls._IGNORED_COMMANDS):
                return False
        return True

    @classmethod
    def disable_command_logging(cls, method):
        """Filter out the logging of this method.

        Args:
            method (str or callable)

        Returns:
            str or callable: sane as `method`
        """
        command = method
        if not isinstance(command, str):
            command = command.__name__
        cls._IGNORED_COMMANDS.add(command + "(")
        return method

    def comment(self, *args, **kw):
        """User comment which can be modified later
        """
        self._set_msg_type(kw, "comment")
        self.forced_log(*args, **kw)

    def command(self, *args, **kw):
        """Specific commands can be filtered out with `disable_command_logging`
        """
        self._set_msg_type(kw, "command")
        self.forced_log(*args, **kw)


class GreenletDisableLogger(logging.Logger):
    """Logger which can be disabled for specific greenlets.
    """

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.addFilter(self._greenlet_filter)
        self.reset()

    def reset(self):
        """Enable all disabled greenlets
        """
        self._disabled_greenlets = weakref.WeakKeyDictionary()
        self._enabled_greenlets = weakref.WeakKeyDictionary()

    def _greenlet_filter(self, record):
        """Filter out this log record when the logging is disabled
        for the current greenlet.
        """
        for greenlet in self._iter_greenlets():
            if self._disabled_greenlets.get(greenlet, 0) > 0:
                # We are in a "disabled" context
                for greenlet in self._iter_greenlets():
                    # The "disabled" context has been re-enabled
                    if self._enabled_greenlets.get(greenlet, 0) > 0:
                        return True
                else:
                    return False
        return True

    def _iter_greenlets(self):
        """Yields the current greenlet and its parents
        """
        greenlet = gevent.getcurrent()
        while greenlet:
            yield greenlet
            try:
                # gevent.Greenlet
                greenlet = greenlet.spawning_greenlet()
            except AttributeError:
                # greenlet.greenlet
                greenlet = greenlet.parent

    @contextmanager
    def disable_in_greenlet(self, greenlet=None):
        """Disable logging in this greenlet
        """
        with self._greenlet_context(self._disabled_greenlets, greenlet=greenlet):
            yield

    @contextmanager
    def enable_in_greenlet(self, greenlet=None):
        """Re-enable disabled logging in this greenlet. No effect otherwise.
        """
        with self._greenlet_context(self._enabled_greenlets, greenlet=greenlet):
            yield

    @contextmanager
    def _greenlet_context(self, greenlets, greenlet=None):
        """Disable logging in a greenlet within this context.
        It takes the current greenlet by default.
        """
        # Increment the greenlet counter
        if greenlet is None:
            current = gevent.getcurrent()
        try:
            greenlets[current] += 1
        except KeyError:
            greenlets[current] = 1

        try:
            yield
        finally:
            # Decrement the greenlet counter
            try:
                greenlets[current] -= 1
                if greenlets[current] <= 0:
                    del greenlets[current]
            except KeyError:
                pass


class UserLogger(PrintLogger, GreenletDisableLogger):
    """When enabled, log messages are visible to the user.
    No message propagation to parent loggers.

    In addition to the standard logger methods we have:
        print: use like the builtin `print` ("info" level or higher)
        disable_in_greenlet: disable logging for a greenlet (current by default)
        enable_in_greenlet: re-enable when greenlet is disabled (no effect otherwise)
    """

    def __init__(self, _args, **kw):
        super().__init__(_args, **kw)
        self.propagate = False
        self.disabled = True
        self.addHandler(PrintHandler())

    def enable(self):
        self.disabled = False

    def disable(self):
        self.disabled = True


class Elogbook(PrintLogger, ElogLogger):
    """When enabled, log messages are send to the electronic logbook.
    No message propagation to parent loggers.

    In addition to the standard logger methods we have:
        comment: send a "comment" notification to the electronic logbook
        command: send a "command" notification to the electronic logbook
        print: use like the builtin `print` ("comment" notification)
    """

    def __init__(self, _args, **kw):
        super().__init__(_args, **kw)
        self.propagate = False
        self.disabled = True
        handler = ElogHandler()
        handler.addFilter(elogbook_filter)
        self.addHandler(handler)

    def enable(self):
        self.disabled = False

    def disable(self):
        self.disabled = True

    def print(self, *args, **kw):
        self._set_msg_type(kw, "comment")
        super().print(*args, **kw)


userlogger = UserLogger("bliss.userlogger", level=logging.NOTSET)

user_print = userlogger.print
user_debug = userlogger.debug
user_info = userlogger.info
user_warning = userlogger.warning
user_error = userlogger.error
user_critical = userlogger.critical
disable_user_output = userlogger.disable_in_greenlet
enable_user_output = userlogger.enable_in_greenlet

elogbook = Elogbook("bliss.elogbook", level=logging.NOTSET)

elog_print = elogbook.print  # exposed to the shell
elog_debug = elogbook.debug
elog_info = elogbook.info
elog_warning = elogbook.warning
elog_error = elogbook.error
elog_critical = elogbook.critical
elog_comment = elogbook.comment
elog_command = elogbook.command


@contextmanager
def bliss_logger():
    saved_logger_class = logging.getLoggerClass()
    logging.setLoggerClass(BlissLogger)
    yield
    logging.setLoggerClass(saved_logger_class)


class BlissLogger(logging.Logger):
    """
    Special logger class with useful methods for communication debug concerning data format
    """

    def __init__(self, name, level=logging.NOTSET):
        super().__init__(name, level=level)
        self.__default_level = level  # used to keep track of default shell level
        self.__saved_level = self.level  # used to allow the user to change level

        self.set_ascii_format()

        # this is to prevent the error message about 'no handler found for logger XXX'
        self.addHandler(logging.NullHandler())  # this handler does nothing

    def debugon(self):
        """
        Activates debug on the logger

        This enables debug-level logging for this logger and all descendants

        Returns:
            set: names of activated loggers
        """
        super().setLevel(logging.DEBUG)
        activated = set([self.name])
        if self.level != logging.DEBUG:
            self.__saved_level = self.level
        for name, logger in Log._find_loggers(self.name + ".*").items():
            activated |= logger.debugon()
        return activated

    def debugoff(self):
        """Deactivates debug on the logger

        This disables debug-level logging for this logger and all descendants

        Returns:
            set: names of activated loggers
        """
        super().setLevel(self.__saved_level)
        deactivated = set([self.name])
        for name, logger in Log._find_loggers(self.name + ".*").items():
            deactivated |= logger.debugoff()
        self.__saved_level = self.level
        return deactivated

    def setLevel(self, level):
        # Setting level to DEBUG is equivalent to enabling debug log messages
        if level == logging.DEBUG:
            self.debugon()
        else:
            if self.level == logging.DEBUG:
                self.debugoff()
            super().setLevel(level)
            if level != self.__default_level:
                # if the set level is not one of the two toggle values
                # DEBUG or the __default_level initialized on startup
                # change the toggle value for this logger
                self.__saved_level = level

    def debug_data(self, msg, *args) -> None:
        """
        Represents the given data according to the previous settled format
        through methods:

        * set_hex_format
        * set_ascii_format

        Or in dict form if data is a dictionary

        Arguments:
            msg: The plain text message
            data: dict or raw bytestring
        """
        if self.isEnabledFor(logging.DEBUG):
            data = args[-1]
            args = args[:-1]
            if isinstance(data, dict):
                self.debug(f"{msg} {self.log_format_dict(data)}", *args)
            else:
                try:
                    self.debug(
                        f"{msg} bytes={len(data)} {self.__format_data(data)}", *args
                    )
                except Exception:
                    self.debug(f"{msg} {data}", *args)

    def set_hex_format(self):
        """
        Sets output format of debug_data to hexadecimal
        """
        self.__format_data = self.log_format_hex

    def set_ascii_format(self):
        """
        Sets output format of debug_data to ascii
        """
        self.__format_data = self.log_format_ascii

    def log_format_dict(self, indict):
        """
        Represents the given dictionary in nice way

        Returns:
            str: formatted dict
        """
        return " ; ".join(
            f"{name}={self.log_format_ascii(value)}" for (name, value) in indict.items()
        )

    def log_format_ascii(self, in_str: str):
        """
        Gives a convenient representation of a bytestring:
        * Chars with value under 31 and over 127 are represented as hex
        * Otherwise represented as ascii

        Returns:
            str: formatted bytestring
        """
        return asciify(in_str)

    def log_format_hex(self, in_str: str):
        """
        Represents the given string in hexadecimal

        Returns:
            str: formatted hex
        """
        return hexify(in_str)


class BeaconLogServerHandler(logging.handlers.SocketHandler):
    """
    Logging handler to emit logs into Beacon log service.

    Use default socket handler, and custom log records to specify `session`
    and `application` fields.

    This extra information allow the log server to dispatch log records to
    the appropriate files.
    """

    def emit(self, record):
        try:
            session_name = current_session.name
        except AttributeError:
            # not in a session
            return
        record.application = "bliss"
        record.session = session_name
        return super().emit(record)


class Log:
    """
    Main utility class for BLISS logging
    """

    _LOG_FORMAT = None
    _LOG_DEFAULT_LEVEL = logging.WARNING

    def __init__(self, map):
        self.map = map
        for node_name in ("global", "controllers"):
            get_logger(node_name)
        self._stdout_handler = None
        self._beacon_handler = None

    @staticmethod
    def _find_loggers(glob):
        # be sure all logger are created under controller
        for node in global_map.walk_node("controllers"):
            try:
                instance_ref = node["instance"]
            except KeyError:
                continue
            else:
                if isinstance(instance_ref, str):
                    continue

                instance = instance_ref()
                if instance is None:
                    continue
                get_logger(instance)

        manager = logging.getLogger().manager
        loggers = {
            name: obj
            for (
                name,
                obj,
            ) in manager.loggerDict.items()  # All loggers registered in the system
            if isinstance(obj, logging.Logger)
            and fnmatchcase(name, glob)  # filter out logging Placeholder objects
        }
        return loggers

    def _find_loggers_from_obj(self, obj):
        loggers = {}
        manager = logging.getLogger().manager
        get_logger(obj)
        if isinstance(obj, Proxy):
            obj = obj.__wrapped__
        for node in global_map.walk_node(obj):
            logger = node.get("_logger")
            if logger and logger in manager.loggerDict.values():
                loggers[logger.name] = logger
        return loggers

    def start_stdout_handler(self):
        if self._stdout_handler is not None:
            return

        handler = logging.StreamHandler()
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter(self._LOG_FORMAT))
        logging.getLogger().addHandler(handler)

        def filter_(record):
            # filter shell exceptions
            if record.name in ["exceptions", "user_input"]:
                return False
            return True

        handler.addFilter(filter_)
        self._stdout_handler = handler

    def start_beacon_handler(self, address):
        if self._beacon_handler is not None:
            return

        host, port = address
        handler = BeaconLogServerHandler(host, port)
        handler.setLevel(logging.DEBUG)
        logging.getLogger().addHandler(handler)

        # handler for user input and exceptions
        for log_name in ("user_input", "exceptions", "startup"):
            log = logging.getLogger(log_name)
            log.addHandler(handler)
            log.setLevel(logging.INFO)
            log.propagate = False

        self._beacon_handler = handler

    def set_log_format(self, fmt):
        self._LOG_FORMAT = fmt
        logger = logging.getLogger()
        for handler in logger.handlers:
            handler.setFormatter(logging.Formatter(self._LOG_FORMAT))

    def debugon(self, glob_logger_pattern_or_obj):
        """
        Activates debug-level logging for a specifig logger or an object

        Args:
            glob_logger_pattern_or_obj: glob style pattern matching for logger name, or instance

        Hints on glob: pattern matching normally used by shells
                       common operators are * for any number of characters
                       and ? for one character of any type

        Returns:
            None

        Examples:
            >>> log.debugon(robz)  # passing the object
            Set logger [global.device.controller.robz] to DEBUG level
            >>> log.debugon('*motorsrv')  # using a glob
            Set logger [motorsrv] to DEBUG level
            Set logger [motorsrv.Connection] to DEBUG level
            >>> log.debugon('*rob?')  # again a glob
            Set logger [global.device.controller.roby] to DEBUG level
            Set logger [global.device.controller.robz] to DEBUG level
        """
        activated = set()

        if isinstance(glob_logger_pattern_or_obj, str):
            glob_logger_pattern = glob_logger_pattern_or_obj
            loggers = self._find_loggers(glob_logger_pattern)
        else:
            obj = glob_logger_pattern_or_obj
            loggers = self._find_loggers_from_obj(obj)

        if loggers:
            for name, logger in loggers.items():
                try:
                    logger.debugon()
                except AttributeError:
                    # not a BlissLoggers
                    logger.setLevel(logging.DEBUG)
                activated.add(name)

        return activated

    def debugoff(self, glob_logger_pattern_or_obj):
        """
        Desactivates debug-level logging for a specifig logger or an object

        Args:
            glob_logger_pattern_or_obj: glob style pattern matching for logger name, or instance

        Hints on glob: pattern matching normally used by shells
                    common operators are * for any number of characters
                    and ? for one character of any type

        Returns:
            None
        """
        deactivated = set()

        if isinstance(glob_logger_pattern_or_obj, str):
            glob_logger_pattern = glob_logger_pattern_or_obj
            loggers = self._find_loggers(glob_logger_pattern)
        else:
            obj = glob_logger_pattern_or_obj
            loggers = self._find_loggers_from_obj(obj)

        if loggers:
            for name, logger in loggers.items():
                try:
                    logger.debugoff()
                except AttributeError:
                    # not a BlissLoggers
                    logger.setLevel(self._LOG_DEFAULT_LEVEL)
                deactivated.add(name)

        return deactivated

    def clear(self):
        if self._stdout_handler is not None:
            self._stdout_handler.close()
            self._stdout_handler = None
        if self._beacon_handler is not None:
            self._beacon_handler.close()
            self._beacon_handler = None


def create_logger_name(G, node_id):
    """
    Navigates through the graph of device nodes and returns the proper name

    Args:
        G: graph
        node_id: id(instance) of node
    returns:
        logger_name for the specific node
    """
    try:
        # search before through controllers
        path = nx.shortest_path(G, "controllers", node_id)
        logger_names = ["global"]
        for n in path:
            node_name = format_node(G, n, format_string="tag->name->class->id")
            # sanitize name
            logger_names.append(re.sub(r"[^0-9A-Za-z_:=\-\(\)\[\]\/]", "_", node_name))
        return ".".join(logger_names)

    except (nx.exception.NetworkXNoPath, nx.exception.NodeNotFound):
        pass

    return format_node(G, node_id, format_string="tag->name->class->id")
