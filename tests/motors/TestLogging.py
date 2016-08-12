# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import unittest
import cStringIO
import sys
import os

sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            os.path.pardir, os.path.pardir)))

from bliss.common import log


class wrapped_stdout:

    def __init__(self):
        self.output = cStringIO.StringIO()
        self.real_stdout = sys.stdout

    def __enter__(self, *args, **kwargs):
        sys.stdout = self.output
        return self.output

    def __exit__(self, *args, **kwargs):
        sys.stdout = self.real_stdout


class wrapped_stderr:

    def __init__(self):
        self.output = cStringIO.StringIO()
        self.real_stderr = sys.stderr

    def __enter__(self, *args, **kwargs):
        sys.stderr = self.output
        return self.output

    def __exit__(self, *args, **kwargs):
        sys.stderr = self.real_stderr


class TestLogging(unittest.TestCase):

    def test_debug(self):
        log.level(log.DEBUG)
        with wrapped_stdout() as stdout:
            log.debug("debugging test")
        output = stdout.getvalue()[13:]
        # 'DEBUG: 0.152 test_debug() (motors/TestLogging.py, l.49): debugging test\n'
        # Musst suppress 13 firsts chars.
        self.assertEquals(
            output,
            "test_debug() (motors/TestLogging.py, l.49): debugging test\n")


    def test_error(self):
        log.level(log.ERROR)
        with wrapped_stderr():
            self.assertRaises(RuntimeError, log.error, "an error to log")

    def test_info(self):
        log.level(log.INFO)
        with wrapped_stdout() as stdout:
            log.info("test")
        output = stdout.getvalue()
        self.assertEquals(
            output,
            "INFO: test\n")

    def test_level(self):
        self.assertEquals(log.level(log.INFO), log.INFO)

    def test_exception(self):
        try:
            raise RuntimeError("BLA")
        except:
            with wrapped_stderr() as stderr:
                log.exception("excepted exception", raise_exception=False)
        output = stderr.getvalue()
        self.assertEquals(
            output,
            """ERROR: excepted exception
Traceback (most recent call last):
  File "tests/motors/TestLogging.py", line 77, in test_exception
    raise RuntimeError("BLA")
RuntimeError: BLA
""")

    def test_exception2(self):
        try:
            raise ValueError
        except:
            self.assertRaises(ValueError, log.exception, "expected exception")
            return
        self.assertTrue(False)

if __name__ == '__main__':
    unittest.main()
