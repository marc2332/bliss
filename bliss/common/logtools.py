# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import logging
import contextlib
from logging import Logger, NullHandler, Formatter
import re
from fnmatch import fnmatch, fnmatchcase
import networkx as nx
from functools import wraps

from bliss.common.utils import autocomplete_property
from bliss.common.mapping import format_node, map_id
from bliss import global_map


__all__ = [
    "log_debug",
    "log_debug_data",
    "log_info",
    "log_warning",
    "log_error",
    "log_critical",
    "log_exception",
    "set_log_format",
    "hexify",
    "asciify",
    "get_logger",
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
    id_ = map_id(instance)
    if id_ in global_map.G:
        return global_map.G.node[id_]["_logger"]
    global_map.register(instance)
    return global_map[instance]["_logger"]


LOG_DOCSTRING = """
Print a log message associated to a specific instance.

Normally instance is self if we are inside a class, but could
be any instance that you would like to log.
Notice that if the instance will be registered automatically
if is not jet in the device map.\n\n

Args:
    msg: string containing the log message
"""


def log_debug(instance, msg):
    __doc__ = LOG_DOCSTRING + "Log level: DEBUG"
    logger = get_logger(instance)
    logger.debug(msg)


def log_debug_data(instance, msg, data):
    """
    Convenient function to print log messages and associated data.

    Usually useful to debug low level communication like serial and sockets.

    Properly represents:
        bytestrings/strings to hex or ascii
        dictionaries

    The switch beetween a hex or ascii representation can be done
    with the function set_log_format
    """
    logger = get_logger(instance)
    logger.debug_data(msg, data)


def log_info(instance, msg):
    __doc__ = LOG_DOCSTRING + "Log level: INFO"
    logger = get_logger(instance)
    logger.info(msg)


def log_warning(instance, msg):
    __doc__ = LOG_DOCSTRING + "Log level: WARNING"
    logger = get_logger(instance)
    logger.warning(msg)


def log_error(instance, msg):
    __doc__ = LOG_DOCSTRING + "Log level: ERROR"
    logger = get_logger(instance)
    logger.error(msg)


def log_critical(instance, msg):
    __doc__ = LOG_DOCSTRING + "Log level: CRITICAL"
    logger = get_logger(instance)
    logger.critical(msg)


def log_exception(instance, msg):
    __doc__ = LOG_DOCSTRING + "Log level: ERROR with added exception trace"
    logger = get_logger(instance)
    logger.exception(msg)


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


@contextlib.contextmanager
def bliss_logger():
    saved_logger_class = logging.getLoggerClass()
    logging.setLoggerClass(BlissLogger)
    yield
    logging.setLoggerClass(saved_logger_class)


class BlissLogger(Logger):
    """
    Special logger class with useful methods for communication debug concerning data format
    """

    def __init__(self, name, level=logging.NOTSET):
        super().__init__(name, level=level)
        self.__default_level = level  # used to keep track of default shell level
        self.__saved_level = self.level  # used to allow the user to change level

        self.set_ascii_format()

        # this is to prevent the error message about 'no handler found for logger XXX'
        self.addHandler(NullHandler())  # this handler does nothing

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

    def debug_data(self, msg: str, data) -> None:
        """
        Represents the given data according to the previous settled format
        through methods:
            * set_hex_format
            * set_ascii_format

        Or in dict form if data is a dictionary

        Args:
            msg: The plain text message
            data: dict
                  or raw bytestring
        """
        if isinstance(data, dict):
            self.debug(f"{msg} {self.log_format_dict(data)}")
        else:
            try:
                self.debug(f"{msg} bytes={len(data)} {self.__format_data(data)}")
            except Exception:
                self.debug(f"{msg} {data}")

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


class Log:
    """
    Main utility class for BLISS logging
    """

    _LOG_FORMAT = None
    _LOG_DEFAULT_LEVEL = logging.WARNING

    @staticmethod
    def _find_loggers(glob):
        manager = logging.getLogger().manager
        loggers = {
            name: obj
            for (
                name,
                obj,
            ) in manager.loggerDict.items()  # All loggers registered in the system
            if isinstance(obj, Logger)
            and fnmatchcase(name, glob)  # filter out logging Placeholder objects
        }
        return loggers

    def __init__(self, map):
        self.map = map
        self.map.add_map_handler(map_update_loggers)
        self.map.trigger_update()
        self._debug_handler = None

    def set_debug_handler(self, handler):
        if self._debug_handler:
            logging.getLogger().removeHandler(self._debug_handler)
        self._debug_handler = handler
        self._debug_handler.setFormatter(Formatter(self._LOG_FORMAT))
        self._debug_handler.setLevel(logging.DEBUG)
        logging.getLogger().addHandler(self._debug_handler)

    def set_log_format(self, fmt):
        self._LOG_FORMAT = fmt
        logger = logging.getLogger()
        for handler in logger.handlers:
            handler.setFormatter(Formatter(self._LOG_FORMAT))

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
        if isinstance(glob_logger_pattern_or_obj, str):
            glob_logger_pattern = glob_logger_pattern_or_obj
            loggers = self._find_loggers(glob_logger_pattern)
            activated = set()
            if loggers:
                for name, logger in loggers.items():
                    try:
                        logger.debugon()
                    except AttributeError:
                        # not a BlissLoggers
                        logger.setLevel(logging.DEBUG)
                    activated.add(name)

        else:
            obj = glob_logger_pattern_or_obj
            activated = get_logger(obj).debugon()

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
        if isinstance(glob_logger_pattern_or_obj, str):
            glob_logger_pattern = glob_logger_pattern_or_obj
            loggers = self._find_loggers(glob_logger_pattern)
            deactivated = set()
            if loggers:
                for name, logger in loggers.items():
                    try:
                        logger.debugoff()
                    except AttributeError:
                        # not a BlissLoggers
                        logger.setLevel(self._LOG_DEFAULT_LEVEL)
                    deactivated.add(name)

        else:
            obj = glob_logger_pattern_or_obj
            deactivated = get_logger(obj).debugoff()

        return deactivated


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
            logger_names.append(re.sub(r"[^0-9A-Za-z_:=\-\(\)\[\]]", "_", node_name))
        return ".".join(logger_names)

    except (nx.exception.NetworkXNoPath, nx.exception.NodeNotFound):
        pass

    return format_node(G, node_id, format_string="tag->name->class->id")


def map_update_loggers(G):
    """
    Function to be called after map update (add to map handlers)

    Args:
        G: networkX DiGraph (given by mapping module)
    """
    for node in list(G):
        node_dict = G.node.get(node)
        if not node_dict:
            continue
        reference = node_dict.get("instance")
        if isinstance(reference, str):
            if reference in ("axes", "counters", "comms"):
                continue
            else:
                inst = reference
        else:
            inst = reference()

        if inst:  # if weakref is still alive
            logger = node_dict.get("_logger")
            if logger:
                existing_logger_name = logger.name
                logger_name = create_logger_name(G, node)  # get name from map
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
                new_logger_name = create_logger_name(G, node)  # get proper name
                with bliss_logger():
                    node_dict["_logger"] = logging.getLogger(new_logger_name)
