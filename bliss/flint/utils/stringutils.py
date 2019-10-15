# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Helper about string formatting"""


import math


def human_readable_duration(pint=None, minutes=None, seconds=None):
    """Returns a human readable duration.

    It is not possible to use both parameters at the same time.

    :param pint: A pint time quantity
    :param minutes: An amount of minutes
    :param minutes: An amount of secondes
    """
    if pint is not None:
        minutes = float(pint.to("minute").magnitude)
    if seconds is not None:
        minutes = seconds / 60

    seconds = math.floor(60 * (minutes - math.floor(minutes)))
    minutes = math.floor(minutes)
    hours = minutes // 60
    minutes = minutes % 60

    result = ""

    if hours == 0:
        pass
    elif hours <= 1:
        result = result + "%i hour" % hours
    else:
        result = result + "%i hours" % hours

    if len(result) != 0:
        result = result + " "

    if len(result) == 0 and minutes == 0:
        pass
    elif minutes <= 1:
        result = result + "%i minute" % minutes
    else:
        result = result + "%i minutes" % minutes

    # Skip the seconds if it is point less
    if hours != 0:
        return result
    if minutes >= 5:
        return result

    if seconds <= 1:
        result = result + " %i second" % seconds
    else:
        result = result + " %i seconds" % seconds

    return result


def human_readable_duration_in_second(pint=None, minutes=None, seconds=None):
    """Returns a human readable duration.

    It is not possible to use both parameters at the same time.

    :param pint: A pint time quantity
    :param minutes: An amount of minutes
    :param minutes: An amount of secondes
    """
    if pint is not None:
        minutes = float(pint.to("minute").magnitude)
    if seconds is not None:
        minutes = seconds / 60

    seconds = math.floor(60 * (minutes - math.floor(minutes)))
    minutes = math.floor(minutes)
    hours = minutes // 60
    minutes = minutes % 60

    result = ""

    if hours == 0:
        pass
    elif hours <= 1:
        result = result + "%i hour" % hours
    else:
        result = result + "%i hours" % hours

    if len(result) != 0:
        result = result + " "

    if len(result) == 0 and minutes == 0:
        pass
    elif minutes <= 1:
        result = result + "%i minute" % minutes
    else:
        result = result + "%i minutes" % minutes

    if seconds <= 1:
        result = result + " %i second" % seconds
    else:
        result = result + " %i seconds" % seconds

    return result


def human_readable_duration_in_minute(pint=None, minutes=None, seconds=None):
    """Returns a human readable duration.

    It is not possible to use both parameters at the same time.

    :param pint: A pint time quantity
    :param minutes: An amount of minutes
    :param minutes: An amount of secondes
    """
    if pint:
        minutes = float(pint.to("minute").magnitude)
        minutes = round(minutes)
    if seconds is not None:
        minutes = seconds / 60

    if minutes <= 1:
        return "Less than 1 minute"
    if minutes < 60:
        return "%i minutes" % minutes

    hours = minutes // 60
    minutes = minutes % 60
    result = ""
    if hours == 1:
        result += "%i hour" % hours
    else:
        result += "%i hours" % hours

    if minutes <= 1:
        pass
    else:
        result += " %i minutes" % minutes

    return result
