print("Executing logscript.py ...")

from bliss.common import logtools


class LogScriptDummy:
    def __init__(self):
        logtools.log_error(self, "logscript.py: Beacon error")


logtools.user_error("logscript.py: user error")
logtools.elog_error("logscript.py: E-logbook error")
LogScriptDummy()

scriptfinished = True

print("End of logscript.py.")
