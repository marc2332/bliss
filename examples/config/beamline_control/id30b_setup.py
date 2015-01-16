import sys
import time
from bliss.config import static

set_scanfile("/users/opid30/scans/scans_%s" % time.strftime("%d%m%y"))

cfg = static.get_config()
for item_name in cfg.names_list:
    try:
        o = cfg.get(item_name)
    except ImportError:
        # let's create the item ourselves
        item_cfg_node = cfg.get_config(item_name)
        try:
            module = __import__('khoros.blcomponents.%s' % item_cfg_node['class'], fromlist=[None])
        except ImportError:
            sys.excepthook(*sys.exc_info())
            continue
        else:
            try:
                klass = getattr(module, item_cfg_node['class'])
            except AttributeError:
                sys.excepthook(*sys.exc_info())
                continue
            else:
                try:   
                    o = klass(item_name, item_cfg_node)
                except:
                    sys.excepthook(*sys.exc_info())
                    continue
    globals()[item_name]=o


