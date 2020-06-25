from bliss.common.user_status_info import status_message
import gevent
import time


def is_finished():
    return (time.time() - t0) > 5


t0 = time.time()


with status_message() as p:
    while not is_finished():
        gevent.sleep(0.1)
        p(f"Elapsed {time.time() - t0:.3f}")
