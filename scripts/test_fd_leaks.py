import gevent
import os
import gc
from contextlib import contextmanager
from bliss.config import static
from bliss.common import scans
from bliss.common.session import DefaultSession
from bliss.data.node import get_session_node
from bliss.data.node import get_node
from bliss.config.conductor import client


def file_descriptors(pid=None):
    if pid is None:
        pid = os.getpid()
    fdpath = os.path.join("/proc", str(pid), "fd")
    fds = {}
    for fd in os.listdir(fdpath):
        try:
            dest = os.readlink(os.path.join(fdpath, fd))
        except Exception:
            pass
        else:
            fds[int(fd)] = dest
    return fds


def fd_leaks_diff(old_fds, prefix=""):
    new_fds = file_descriptors()
    diff = set(new_fds.values()) - set(old_fds.values())
    if diff:
        print("{}{} fds difference {}".format(prefix, len(diff), list(sorted(diff))))
    else:
        print(prefix + "no fd difference")
    return new_fds


@contextmanager
def fd_leak_ctx(prefix=""):
    old_fds = file_descriptors()
    try:
        yield
    finally:
        fd_leaks_diff(old_fds, prefix=prefix)


def listenscan(db_name):
    scannode = get_node(db_name)
    it = scannode.iterator
    try:
        for event_type, datanode, event_data in it.walk_events():
            del datanode
            continue
    except gevent.GreenletExit:
        pass
    del it
    del scannode
    while gc.collect():
        pass


def listensession(session_name, finishevent):
    writers = {}
    with fd_leak_ctx("\nget_session_node: "):
        sessionnode = get_session_node(session_name)
        with fd_leak_ctx("\nsession iterator: "):
            it = sessionnode.iterator
            with fd_leak_ctx("\nsession walk_events: "):
                try:
                    fds = None
                    for event_type, scannode, event_data in it.walk_on_new_events(
                        filter="scan"
                    ):
                        if fds is None:
                            fds = file_descriptors()
                        if event_type == event_type.NEW_NODE:
                            g = gevent.spawn(listenscan, scannode.db_name)
                            writers[scannode.name] = g
                        elif event_type == event_type.END_SCAN:
                            g = writers.pop(scannode.name)
                            g.kill()
                            g.join()
                        if not writers:
                            finishevent.set()
                            fd_leaks_diff(fds, prefix="\nparallel scans done: ")
                except gevent.GreenletExit:
                    if writers:
                        raise RuntimeError("Not all writers received END_SCAN")
            del it
        del sessionnode


if __name__ == "__main__":
    nscans = 100
    config = static.get_config()
    test_session = DefaultSession()
    test_session.setup()
    detectors = [
        config.get("diode"),
        config.get("diode3"),
        config.get("diode4"),
        config.get("diode5"),
        config.get("diode6"),
        config.get("diode7"),
    ]
    finishevent = gevent.event.Event()

    with fd_leak_ctx("\nmain (after cleanup): "):
        with fd_leak_ctx("\nmain (before cleanup): "):
            with fd_leak_ctx("\nmain (scans only): "):
                g = gevent.spawn(listensession, test_session.name, finishevent)
                for _ in range(nscans):
                    scns = [scans.ct(0.01, d, run=False) for d in detectors]
                    glts = [gevent.spawn(s.run) for s in scns]
                    gevent.joinall(glts)
                    finishevent.wait()
                    finishevent.clear()
                g.kill()

        client.clean_all_redis_connection()
