#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Test tool to scan and query GPIB bus instruments talking SCPI
"""

import logging

import gevent

from bliss.comm.gpib import Gpib, TMO_MAP
from bliss.comm.scpi import Scpi


def test_scpi(interface):
    scpi = Scpi(interface=interface)
    return scpi["*IDN"]


def test_gpib(gpib_pars):
    gpib = Gpib(**gpib_pars)
    # try SCPI
    try:
        idn = test_scpi(gpib)
        logging.info("[ OK ] %s SCPI %s", gpib, idn)
    except KeyboardInterrupt:
        raise
    except Exception as e1:
        logging.error("[FAIL] %s (%s)", gpib, e1)
        logging.debug("Details:", exc_info=1)


def test_url(url, gpib_pars, concurrent=False):
    gpib_pars = dict(gpib_pars, url=url)
    if concurrent:
        tests = []
        for pad in range(1, 31):
            tests.append(gevent.spawn(test_gpib, dict(gpib_pars, pad=pad)))
        gevent.joinall(tests)
    else:
        for pad in range(1, 31):
            test_gpib(dict(gpib_pars, pad=pad))


def scan(urls, gpib_pars, url_concurrent=True, pad_concurrent=False):
    if url_concurrent:
        tests = [gevent.spawn(test_url, url, gpib_pars, pad_concurrent) for url in urls]
        gevent.joinall(tests)
    else:
        for url in urls:
            test_url(url, gpib_pars, pad_concurrent)


def main():
    import time
    import datetime
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "url", type=str, nargs="+", help="gpib address (ex: gpibbcu2, gpibbcu2:5000)"
    )
    parser.add_argument(
        "--tmo", type=int, default=9, help="gpib timeout [default: 9 (=100ms)]"
    )
    parser.add_argument(
        "--no-url-concurrent", action="store_true", help="disable url concurrent scans"
    )
    parser.add_argument(
        "--pad-concurrent",
        action="store_true",
        help="enable pad concurrent scans for the same url",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="info",
        choices=["debug", "info", "warning", "error"],
        help="log level [default: info]",
    )

    args = parser.parse_args()

    log_level = getattr(logging, args.log_level.upper())
    logging.basicConfig(level=log_level, format="%(message)s")

    logging.info("Scanning devices on {0}...".format(", ".join(args.url)))

    urls = ["enet://" + url for url in args.url]
    timeout = TMO_MAP[args.tmo] + 0.1

    gpib_pars = dict(timeout=timeout, tmo=args.tmo)

    start = time.time()
    scan(urls, gpib_pars, not args.no_url_concurrent, args.pad_concurrent)
    dt = time.time() - start
    logging.info("Took {0}s".format(datetime.timedelta(seconds=dt)))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.warning("Ctrl-C pressed. Bailing out!")
