print("Executing test_logging_session.py ...")

from bliss.setup_globals import *
from bliss.common import logtools


class LoggingSessionDummy:
    def __init__(self):
        logtools.log_error(self, "test_logging_session.py: Beacon error")


logtools.user_error("test_logging_session.py: user error")
logtools.elog_error("test_logging_session.py: E-logbook error")
LoggingSessionDummy()

setupfinished = True

load_script("logscript.py")

print("End of test_logging_session.py.")
