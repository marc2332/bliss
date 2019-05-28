# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import logging
import contextlib
from logging import Logger, StreamHandler, NullHandler, Formatter
from fnmatch import fnmatch, fnmatchcase
import networkx as nx

from bliss.common.utils import autocomplete_property
from bliss.common.mapping import format_node, map_id
from bliss.common import session

__all__ = ["lslog", "lsdebug"]


def logging_startup(
    log_level=logging.WARNING, fmt="%(levelname)s %(asctime)-15s %(name)s: %(message)s"
):
    """
    Provides basicConfig functionality to bliss activating at proper level the root loggers
    """
    # save log messages format
    session.get_current().log.set_log_format(fmt)

    # setting startup level for session and bliss logger
    logging.getLogger("session").setLevel(log_level)
    logging.getLogger("bliss").setLevel(log_level)

    # install an additional handler, only for debug messages
    # (debugon / debugoff)
    session.get_current().log.set_debug_handler(StreamHandler())


class LogMixin:
    @autocomplete_property
    def _logger(self, *args, **kwargs):
        m = session.get_current().map
        id_ = map_id(self)
        if id_ in m.G:
            return m.G.node[id_]["_logger"]
        n = m.register(self)
        return n["_logger"]


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
        """Activates debug on the logger

        This enables debug-level logging for this logger and all descendants
        """
        super().setLevel(logging.DEBUG)
        if self.level != logging.DEBUG:
            self.__saved_level = self.level
        for name, logger in Log._find_loggers(self.name + ".*").items():
            logger.debugon()

    def debugoff(self):
        """Deactivates debug on the logger"""
        super().setLevel(self.__saved_level)
        for name, logger in Log._find_loggers(self.name + ".*").items():
            logger.debugoff()
        self.__saved_level = self.level

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
            self.debug(f"{msg} bytes={len(data)} {self.__format_data(data)}")

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

    def _ascii_format(self, ch):
        if ord(ch) > 31 and ord(ch) < 127:
            return ch
        else:
            return "\\x%02x" % ord(ch)

    def log_format_ascii(self, instr: str):
        """
        Gives a convenient representation of a bytestring:
        * Chars with value under 31 and over 127 are represented as hex
        * Otherwise represented as ascii

        Returns:
            str: formatted bytestring
        """
        try:
            return "".join(map(self._ascii_format, instr))
        except Exception:
            return instr

    def _hex_format(self, ch):
        if isinstance(ch, int):
            # given a byte
            return "\\x%02x" % ch
        # given a string of one char
        return "\\x%02x" % ord(ch)

    def log_format_hex(self, instr: str):
        """
        Represents the given string in hexadecimal

        Returns:
            str: formatted hex
        """
        return "".join(map(self._hex_format, instr))


class Log:
    """
    Main utility class for BLISS logging 
    """

    _LOG_FORMAT = None

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

    def debugon(self, glob: str) -> None:
        """
        Activates debug-level logging for a specifig logger

        Args:
            glob: glob style pattern matching

        Returns:
            None
        """
        loggers = self._find_loggers(glob)

        if loggers:
            for logger in loggers.values():
                print(f"Setting {logger.name} to show debug messages")
                logger.setLevel(logging.DEBUG)
        else:
            print("NO loggers found for [{0}]".format(glob))

    def debugoff(self, glob: str) -> None:
        """
        Sets the debug level of the specified logger to the previous level
        (before debugon) or to WARNING

        Args:
            glob: glob style pattern matching
        """
        loggers = self._find_loggers(glob)
        if loggers:
            for name, logger in loggers.items():
                try:
                    print(f"Setting {logger.name} to hide debug messages")
                    # better if logger is a BlissLogger => debugoff will set the right level
                    # to all descendants
                    logger.debugoff()
                except AttributeError:
                    print(f"Setting logger {name} level to WARNING")
                    logger.setLevel(logging.WARNING)
        else:
            print("NO loggers found for [{0}]".format(glob))

    def lslog(self, glob: str = None, debug_only=False) -> None:
        """
        Search for loggers
        Args:
            glob: a logger name with optional glob matching
            level: a logger level from standard logging module
                   for example logging.ERROR or logging.INFO
            inherited: False to visualize only loggers that are not
                       inheriting the level from ancestors

        Hints on glob: pattern matching normally used by shells
                       common operators are * for any number of characters
                       and ? for one character of any type
        Examples:

            >>> lslog()  # prints all loggers

            >>> lslog('*motor0')  # prints only loggers that contains 'motor0'

            >>> lslog(level=logging.CRITICAL)  # prints only logger at critical level
        """
        if glob is None:
            loggers = {**self._find_loggers("bliss*"), **self._find_loggers("session*")}
        else:
            loggers = self._find_loggers(glob)
        maxlen = max([len(name) for name, _ in loggers.items()])
        msgfmt = "{0:{width}} {1:8}"
        output = False

        for name in sorted(loggers.keys()):
            logger = loggers[name]
            try:
                has_debug = logger.getEffectiveLevel() == logging.DEBUG
            except AttributeError:
                has_debug = False
            if debug_only and not has_debug:
                continue
            if not output:
                output = True
                print("\n" + msgfmt.format("logger name", "level", width=maxlen))
                print(msgfmt.format("=" * maxlen, 8 * "=", width=maxlen))
            print(
                msgfmt.format(
                    name, logging.getLevelName(logger.getEffectiveLevel()), width=maxlen
                )
            )
        if output:
            print("")
        else:
            print("No loggers found.\n")


def create_logger_name(G, node_id):
    """
    Navigates through the graph of device nodes and returns the proper name

    Args:
        G: graph
        node_id: id(instance) of node
    returns:
        logger_name for the specific node
    """
    # TODO: implement different starting point
    try:
        # search before through controllers
        path = nx.shortest_path(G, "controllers", node_id)
        return "session." + ".".join(
            format_node(G, n, format_string="tag->name->class->id") for n in path
        )
    except (nx.exception.NetworkXNoPath, nx.exception.NodeNotFound):
        pass
    try:
        # search next starting from session
        path = nx.shortest_path(G, "session", node_id)
        return ".".join(
            format_node(G, n, format_string="tag->name->class->id") for n in path
        )
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
        reference = G.node[node].get("instance")
        if isinstance(reference, str):
            if reference in ("axes", "counters", "comms"):
                continue
            else:
                inst = reference
        else:
            inst = reference()

        if inst:  # if weakref is still alive
            node_dict = G.node[node]
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


def lslog(glob: str = None):
    return session.get_current().log.lslog(glob)


def lsdebug():
    return session.get_current().log.lslog(debug_only=True)
