import os  
import time
from bliss.config import channels
import sys
import gevent

args=[arg for arg in sys.argv[2:] if not '=' in arg]
kwargs = dict([kwarg.split("=") for kwarg in sys.argv[2:] if '=' in kwarg])
for kw in kwargs.keys():
    value = kwargs[kw]
    try:
        value = float(value)
    except:
        try:
            value = int(value)
        except:
            try:
                value = bool(value)
            except:
                pass
    kwargs[kw]=value

c = channels.Channel(*args, **kwargs)
sys.stderr.write("%s\n" % c.value)
gevent.sleep(int(sys.argv[1]))
sys.stderr.write("%s\n" % c.value)

