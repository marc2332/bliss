import unittest
import cStringIO
import sys
import os

sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..")))

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


class TestLogging(unittest.TestCase):

    def test_error(self):
        self.assertRaises(RuntimeError, log.error, "an error to log")

    def test_info(self):
        log.info("test")

    def test_debug(self):
        with wrapped_stdout() as stdout:
            log.debug("debugging test")
        output = stdout.getvalue()
        print output
        self.assertEquals(
            output,
            "DEBUG: test_debug ('TestLogging.py`, line 38): debugging test\n")


if __name__ == '__main__':
    unittest.main()
