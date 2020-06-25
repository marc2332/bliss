from bliss.common import cleanup
import gevent
import time


def _slit_step(axis):
    mvr(axis, 0.1)


def increment():
    t0 = time.time()
    with cleanup.cleanup(slit_top, restore_list=(cleanup.axis.POS,)):
        while time.time() - t0 < 5:
            _slit_step(slit_top)
            gevent.sleep(0.2)
