# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import logging

__all__ = ["lslog", "lslogdebug", "logdebugon", "logdebugoff", "set_log_level"]


def _check_log_level(level):
    if level is None:
        return None
    if str(level) == level:
        return logging._checkLevel(level.upper())
    else:
        return logging._checkLevel(level)


def _get_bliss_loggers(level=None, inherited=True):
    uselevel = _check_log_level(level)

    def _filter_logger(name, obj, level, inherited):
        if level is not None:
            if obj.getEffectiveLevel() != level:
                return False
        if inherited is False:
            if obj.level == logging.NOTSET:
                return False
        return True

    manager = logging.getLogger().manager
    loggers = [
        (name, obj.getEffectiveLevel(), obj.level != logging.NOTSET)
        for (name, obj) in manager.loggerDict.items()
        if name.startswith("bliss")
        and isinstance(obj, logging.Logger)
        and _filter_logger(name, obj, uselevel, inherited) is True
    ]
    return loggers


def _find_logger_by_name(name):
    loggers = _get_bliss_loggers()
    findlog = [logname for logname, _, _ in loggers if logname.find(name) != -1]
    findlog.sort()
    return findlog


def _check_log_name(name):
    if str(name) != name:
        try:
            return name.__module__
        except:
            pass
    return str(name).lower()


def logdebugon(name):
    strname = _check_log_name(name)
    loggers = _find_logger_by_name(strname)
    if not len(loggers):
        print("NO bliss loggers found for [{0}]".format(name))
    else:
        for logname in loggers:
            print("Set logger [{0}] to {1} level".format(logname, "DEBUG"))
            logging.getLogger(logname).setLevel(logging.DEBUG)


def logdebugoff(name):
    strname = _check_log_name(name)
    loggers = _find_logger_by_name(strname)
    if not len(loggers):
        print("NO bliss loggers found for [{0}]".format(strname))
    else:
        for logname in loggers:
            print("Remove {0} level from logger [{1}]".format("DEBUG", logname))
            logging.getLogger(logname).setLevel(logging.NOTSET)


def lslog(level=None, inherited=True):
    loggers = _get_bliss_loggers(level, inherited)
    if len(loggers):
        loggers.sort()
        maxlen = max([len(name) for (name, _, _) in loggers])
        msgfmt = "{0:{width}} {1:8} {2:5}"

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
            uselevel = _check_log_level(level)
            print(
                "NO bliss loggers for {0} level !!".format(
                    logging.getLevelName(uselevel)
                )
            )


def lslogdebug(inherited=True):
    lslogger(logging.DEBUG, inherited)


def set_log_level(level, name=None):
    uselevel = _check_log_level(level)
    if name is None:
        loggers = ["bliss"]
    else:
        strname = _check_log_name(name)
        loggers = _find_logger_by_name(strname)
    for logname in loggers:
        print(
            "Set logger [{0}] to {1} level".format(
                logname, logging.getLevelName(uselevel)
            )
        )
        logging.getLogger(logname).setLevel(uselevel)
