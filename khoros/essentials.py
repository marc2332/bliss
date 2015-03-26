from bliss.common.scans import *
from bliss.common.task_utils import task, cleanup, error_cleanup
from bliss import setup_globals

def load_config():
    import sys
    from bliss.config import static

    cfg = static.get_config()

    for item_name in cfg.names_list:
        print "Initializing '%s`" % item_name
        try:
            o = cfg.get(item_name)
        except:
            sys.excepthook(*sys.exc_info())
        else:
            setattr(setup_globals, item_name, o)
            del o
