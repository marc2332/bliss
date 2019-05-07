# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import logging
import types
from fnmatch import fnmatch, fnmatchcase
import functools
import networkx as nx

from bliss.common.utils import common_prefix, autocomplete_property
from bliss.common.mapping import _BEAMLINE_MAP, BEAMLINE_GRAPH, format_node

__all__ = ["log", "lslog", "lsdebug"]


class LogMixin:
    @autocomplete_property
    def _logger(self, *args, **kwargs):
        id_ = id(self)
        if id_ not in BEAMLINE_GRAPH:
            raise UnboundLocalError(
                "Instance should be registered with mapping.register before using _logger"
            )
        return BEAMLINE_GRAPH.node[id_]["_logger"]


def improve_logger(logger_instance):
    """
    Adds methods to a logging.Logger instance that are are useful for communication debug concerning data format
    """

    def debugon(self):
        """Activates debug on the device"""
        self.setLevel(logging.DEBUG)

    def debugoff(self):
        """Activates debug on the device"""
        self.setLevel(logging.WARNING)

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

    def log_format_ascii(self, instr: str):
        """
        Gives a convenient representation of a bytestring:
        * Chars with value under 31 and over 127 are represented as hex
        * Otherwise represented as ascii

        Returns:
            str: formatted bytestring
        """

        def __ascii_format(ch):
            if ord(ch) > 31 and ord(ch) < 127:
                return ch
            else:
                return "\\x%02x" % ord(ch)

        try:
            return "".join(map(__ascii_format, instr))
        except:
            return instr

    def log_format_hex(self, instr: str):
        """
        Represents the given string in hexadecimal

        Returns:
            str: formatted hex
        """

        def __hex_format(ch):
            return "\\x%02x" % ord(ch)

        try:
            return "".join(map(__hex_format, instr))
        except:
            return instr

    # Appending methods to decorated class
    logger_instance.debugon = types.MethodType(debugon, logger_instance)
    logger_instance.debugoff = types.MethodType(debugoff, logger_instance)
    logger_instance.__format_data = types.MethodType(log_format_ascii, logger_instance)
    logger_instance.set_hex_format = types.MethodType(set_hex_format, logger_instance)
    logger_instance.set_ascii_format = types.MethodType(
        set_ascii_format, logger_instance
    )
    logger_instance.debug_data = types.MethodType(debug_data, logger_instance)
    logger_instance.log_format_dict = types.MethodType(log_format_dict, logger_instance)
    logger_instance.log_format_ascii = types.MethodType(
        log_format_ascii, logger_instance
    )
    logger_instance.log_format_hex = types.MethodType(log_format_hex, logger_instance)
    return logger_instance


class Log:
    """
    bliss logging utils
    """

    def __init__(self, map_beamline):
        self.map_beamline = map_beamline
        logging.getLogger("beamline").setLevel(
            logging.WARNING
        )  # setting starting level

    def _check_log_level(self: (str, int), level):
        """
        Checks if a logging level is a valid one

        Args:
            level: level to be checked
        Returns:
            An integer with a logging level or None

        Raises:
            ValueError: If level is not valid
        """
        if level is None:
            return None
        if str(level) == level:
            return logging._checkLevel(level.upper())
        else:
            return logging._checkLevel(level)

    def _filter_logger(self, level, name, _logger, uselevel, inherited):
        """
        Filters loggers based on
        """
        if level is not None:
            if _logger.getEffectiveLevel() != level:
                return False
        if inherited is False:
            if _logger.level == logging.NOTSET:
                return False
        return True

    def _get_bliss_loggers(self, level=None, inherited=True):
        """\
        Returns:
            name, loglevel, set
        """
        uselevel = self._check_log_level(level)

        manager = logging.getLogger().manager
        loggers = [
            (name, obj.getEffectiveLevel(), obj.level != logging.NOTSET)
            for (
                name,
                obj,
            ) in manager.loggerDict.items()  # All loggers registered in the system
            if isinstance(obj, logging.Logger)
            and name.startswith("bliss")
            and self._filter_logger(level, name, obj, uselevel, inherited) is True
        ]
        return loggers

    def _get_map_loggers(self, level=None, inherited=True):
        """\
        Returns:
            name, loglevel, set
        """
        uselevel = self._check_log_level(level)

        findlog = {
            self.map_beamline.G.node[node]["_logger"].name
            for node in self.map_beamline.G.node
            if self.map_beamline.G.node[node]["_logger"].name
        }
        registered_loggers = [logging.getLogger(obj) for obj in findlog]
        filtered_loggers = [
            (obj.name, obj.getEffectiveLevel(), obj.level != logging.NOTSET)
            for obj in registered_loggers
            if self._filter_logger(level, obj.name, obj, uselevel, inherited) is True
        ]
        return sorted(filtered_loggers)

    def _find_map_logger_by_name(self, name):
        loggers = self._get_map_loggers()
        findlog = [logname for logname, _, _ in loggers if logname.find(name) != -1]
        findlog.sort()
        return findlog

    def _find_bliss_logger_by_name(self, name):
        loggers = self._get_bliss_loggers()
        findlog = [logname for logname, _, _ in loggers if logname.find(name) != -1]
        findlog.sort()
        return findlog

    def _check_log_name(self, name):
        if str(name) != name:
            try:
                return name.__module__
            except:
                pass
        # return str(name).lower()
        return name

    def debugon(self, name: str):
        """
        Activates debug-level logging for a specifig logger

        Args:
            name: The name of the logger

        Returns:
            None

        Examples:
            >>> log = Log()
            >>> log.debugon('motorsrv')
            Set logger [motorsrv] to DEBUG level
            Set logger [motorsrv.Connection] to DEBUG level
        """
        strname = self._check_log_name(name)
        loggers = self._find_bliss_logger_by_name(strname)
        if not len(loggers):
            print("NO bliss loggers found for [{0}]".format(name))
        else:
            for logname in loggers:
                print("Set logger [{0}] to {1} level".format(logname, "DEBUG"))
                logging.getLogger(logname).setLevel(logging.DEBUG)

        loggers = self._find_map_logger_by_name(strname)
        if not len(loggers):
            print("NO map loggers found for [{0}]".format(name))
        else:
            for logname in loggers:
                print("Set logger [{0}] to {1} level".format(logname, "DEBUG"))
                logging.getLogger(logname).setLevel(logging.DEBUG)

    def debugoff(self, name: str) -> None:
        """
        Sets the debug level of the specified logger to INFO

        Args:
            name: name of the logger
        """
        strname = self._check_log_name(name)
        loggers = self._find_bliss_logger_by_name(strname)
        if not len(loggers):
            print("NO bliss loggers found for [{0}]".format(strname))
        else:
            for logname in loggers:
                print(
                    "Remove {0} level from bliss logger [{1}]".format("DEBUG", logname)
                )
                logging.getLogger(logname).setLevel(logging.NOTSET)

        loggers = self._find_map_logger_by_name(strname)
        if not len(loggers):
            print("NO map loggers found for [{0}]".format(name))
        else:
            for logname in loggers:
                print("Remove {0} level from map logger [{1}]".format("DEBUG", logname))
                logging.getLogger(logname).setLevel(logging.NOTSET)

    def ls_map_loggers(
        self, glob: str = None, level: int = None, inherited: bool = True
    ) -> None:
        """
        Prints informations about existing loggers

        Args:
            glob: glob style pattern matching
            level: level TODO
        """
        loggers_ = self._get_map_loggers(level, inherited)
        if glob and len(loggers_):  # apply glob to find wanted cases
            loggers = [logger for logger in loggers_ if fnmatchcase(logger[0], glob)]
        else:
            loggers = loggers_

        if len(loggers):
            loggers.sort()
            maxlen = max([len(name) for (name, _, _) in loggers])
            msgfmt = "{0:{width}} {1:8} {2:5}"

            print("BEAMLINE INSTANCE MAP LOGGERS")
            print(msgfmt.format("instance", "level", "set", width=maxlen))
            print(msgfmt.format("=" * maxlen, 8 * "=", 5 * "=", width=maxlen))
            for (name, efflvl, setlvl) in loggers:
                print(
                    msgfmt.format(
                        name,
                        logging.getLevelName(efflvl),
                        "YES" if bool(setlvl) else "-",
                        width=maxlen,
                    )
                )
        else:
            if level is None:
                print("NO map loggers registered !!")
            else:
                uselevel = self._check_log_level(level)
                print(
                    "NO map loggers for {0} level !!".format(
                        logging.getLevelName(uselevel)
                    )
                )

    def ls_bliss_loggers(
        self, glob: str = None, level: int = None, inherited: bool = True
    ) -> None:
        """
        Prints informations about existing loggers

        Args:
            glob: glob style pattern matching
            level: level TODO
        """
        loggers_ = self._get_bliss_loggers(level, inherited)
        if glob and len(loggers_):
            loggers = [logger for logger in loggers_ if fnmatchcase(logger[0], glob)]
        else:
            loggers = loggers_

        if len(loggers):
            loggers.sort()
            maxlen = max([len(name) for (name, _, _) in loggers])
            msgfmt = "{0:{width}} {1:8} {2:5}"

            print("BLISS MODULE LOGGERS")
            print(msgfmt.format("module", "level", "set", width=maxlen))
            print(msgfmt.format("=" * maxlen, 8 * "=", 5 * "=", width=maxlen))
            for (name, efflvl, setlvl) in loggers:
                print(
                    msgfmt.format(
                        name,
                        logging.getLevelName(efflvl),
                        setlvl is True and "YES" or "-",
                        width=maxlen,
                    )
                )
        else:
            if level is None:
                print("NO bliss loggers registered !!")
            else:
                uselevel = self._check_log_level(level)
                print(
                    "NO bliss loggers for {0} level !!".format(
                        logging.getLevelName(uselevel)
                    )
                )

    def lslog(
        self, glob: str = None, level: int = None, inherited: bool = True
    ) -> None:
        """
        Search for loggers
        Args:
            glob: a logger name with optional glob matching
            level: a logger level from standard logging module
                   for example logging.ERROR or logging.INFO
            inherited: False to visualize only loggers that are not
                       inheriting the level from ancestors
        Examples:

            >>> lslog()  # prints all loggers

            >>> lslog('*motor0')  # prints only loggers that contains 'motor0'

            >>> lslog(level=logging.CRITICAL)  # prints only logger at critical level
        """

        self.ls_bliss_loggers(glob=glob, level=level, inherited=inherited)
        print("\n\n")
        self.ls_map_loggers(glob=glob, level=level, inherited=inherited)

    def lsdebug(self, inherited=True):
        """
        Shows loggers with debug level
        """
        self.lslog(level=logging.DEBUG, inherited=inherited)

    def set_level(self, level, name=None):
        uselevel = self._check_log_level(level)
        if name is None:
            loggers = ["bliss"]
        else:
            strname = self._check_log_name(name)
            loggers = self._find_bliss_logger_by_name(strname)
        for logname in loggers:
            print(f"Set logger [{logname}] to {logging.getLevelName(uselevel)} level")
            logging.getLogger(logname).setLevel(uselevel)


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
        # search before through devices
        path = nx.shortest_path(G, "devices", node_id)
        return "beamline." + ".".join(
            format_node(G, n, format_string="tag->name->__class__") for n in path
        )
    except (nx.exception.NetworkXNoPath, nx.exception.NodeNotFound):
        pass
    try:
        # search next starting from beamline
        path = nx.shortest_path(G, "beamline", node_id)
        return ".".join(
            format_node(G, n, format_string="tag->name->__class__") for n in path
        )
    except (nx.exception.NetworkXNoPath, nx.exception.NodeNotFound):
        pass

    return format_node(G, node_id, format_string="tag->name->__class__")


def map_update_loggers(G):
    """
    Function to be called after map update (add to map_beamline handlers)

    Args:
        G: networkX DiGraph (given by mapping module)
    """
    for node in list(G):
        reference = G.node[node].get("instance")
        inst = (
            reference if isinstance(reference, str) else reference()
        )  # gets the instance

        if inst:  # if weakref is still alive
            logger_name = create_logger_name(G, node)  # get proper name
            if not G.node[node].get("_logger"):
                # if the logger does not exist create it
                G.node[node]["_logger"] = improve_logger(logging.getLogger(logger_name))

            else:
                # the logger exists, update the name if necessary
                if G.node[node].get("_logger").name != logger_name:
                    G.node[node]["_logger"].name = logger_name


def set_log(map_beamline):
    """
    Instantiates a logger bliss instance and creates global references to it
    """
    global log
    global lslog
    global lsdebug

    log = Log(map_beamline=map_beamline)

    log.map_beamline.add_map_handler(map_update_loggers)
    log.map_beamline.trigger_update()
    lslog = log.lslog  # shortcut
    lsdebug = log.lsdebug  # shortcut


set_log(_BEAMLINE_MAP)
