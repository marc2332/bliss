#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# timedisplay.py
#
# Functions to display time durations in a human readable manner.

# also to check :
"""
 from datetime import timedelta
 str(timedelta(seconds=1234.894324432421))
 '0:20:34.894324'
"""

# NB : ISO 8601 duration : https://en.wikipedia.org/wiki/ISO_8601#Durations
#                          https://fr.wikipedia.org/wiki/ISO_8601#Dur.C3.A9e


import sys

__author__ = "cyril.guilloud@esrf.fr"
__date__ = "2014-2019"
__version__ = "0.9.6"


def duration_split(duration):
    """Return a tuple of 'int' : (days, hours, minutes, seconds,
    miliseconds, microseconds) coresponding to <duration> float
    expressed in seconds.
    """

    us_in_ms = 1000 * duration - int(1000 * duration)
    nb_us = us_in_ms * 1000
    us = us_in_ms / 1000.0

    duration = duration - us

    ms = duration - int(duration)
    nb_ms = ms * 1000

    duration = duration - ms
    # now duration must be an integer number of seconds.

    (nb_minutes, nb_seconds) = divmod(duration, 60)
    (nb_hours, nb_minutes) = divmod(nb_minutes, 60)
    (nb_days, nb_hours) = divmod(nb_hours, 24)

    debug = False
    if debug:
        print("-------------------------")
        print("d=%f" % duration)
        print("us=%f" % nb_us)
        print("ms=%f" % nb_ms)
        print("s=%f" % nb_seconds)
        print("mn=%f" % nb_minutes)

    return (nb_days, nb_hours, nb_minutes, nb_seconds, nb_ms, nb_us)


def duration_format(duration):
    """Return a formated string corresponding to <duration> duration.

    * formated string is in 'us' 'ms' 's' 'hours'
    * <duration> float value to be given in seconds.
    """

    (nb_days, nb_hours, nb_minutes, nb_seconds, nb_ms, nb_us) = duration_split(duration)

    _duration_str = ""

    # micro seconds
    if nb_us != 0:
        _duration_str = "%dμs" % nb_us + _duration_str

    # mili seconds
    if nb_ms > 0:
        if len(_duration_str) > 1:
            _duration_str = "%dms " % nb_ms + _duration_str
        else:
            _duration_str = "%dms" % nb_ms + _duration_str

    # seconds
    if nb_seconds > 0:
        if len(_duration_str) > 1:
            _duration_str = "%ds " % nb_seconds + _duration_str
        else:
            _duration_str = "%ds" % nb_seconds + _duration_str

    # minutes
    if nb_minutes > 0:
        if len(_duration_str) > 1:
            _duration_str = "%dmn " % nb_minutes + _duration_str
        else:
            _duration_str = "%dmn" % nb_minutes + _duration_str

    # hours
    if nb_hours > 0:
        if len(_duration_str) > 1:
            _duration_str = "%dh " % nb_hours + _duration_str
        else:
            _duration_str = "%dh" % nb_hours + _duration_str

    # day(s)
    if nb_days > 1:
        if len(_duration_str) > 1:
            _duration_str = "%ddays " % nb_days + _duration_str
        else:
            _duration_str = "%ddays" % nb_days + _duration_str
    elif nb_days > 0:
        if len(_duration_str) > 1:
            _duration_str = "%dday " % nb_days + _duration_str
        else:
            _duration_str = "%dday" % nb_days + _duration_str

    # no years...

    return _duration_str


def test_display(duration):
    print('%15f -> "%s"' % (duration, duration_format(duration)))


def main(args):
    """Main function provided for demonstration and testing purpose."""

    print("")
    print("--------------------{ timedisplay }----------------------------------")

    test_display(0.000123)
    test_display(0.123)
    test_display(123)
    test_display(123.456789)
    test_display(123456)
    test_display(1234567)
    print("")


#       0.000123 -> "123μs"
#       0.123000 -> "123ms"
#     123.000000 -> "2mn 3s"
#     123.456789 -> "2mn 3s 456ms 789μs"
#  123456.000000 -> "1day 10h 17mn 36s"
# 1234567.000000 -> "14days 6h 56mn 7s"

if __name__ == "__main__":
    main(sys.argv)
