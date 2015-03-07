from bliss.common.scans import *
from bliss.common.task_utils import task, cleanup, error_cleanup

def load_config():
    import sys
    from bliss.config import static
    from bliss.shell.interpreter import globals

    cfg = static.get_config()

    for item_name in cfg.names_list:
        print "Initializing '%s`" % item_name
        try:
            o = cfg.get(item_name)
        except:
            sys.excepthook(*sys.exc_info())
        else:
            setattr(globals, item_name, o)
            del o
