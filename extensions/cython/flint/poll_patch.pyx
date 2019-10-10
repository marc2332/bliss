import os
import sys
import glob
import subprocess
from gevent import select
from bliss import common

cdef extern from "poll.h":
    int POLLIN
    int POLLOUT
    struct pollfd:
        int fd                     #File descriptor to poll.
        short int events           #Types of events poller cares about.
        short int revents          #Types of events that actually occurred.

cdef extern from "poll_patch_init.h":
    ctypedef int (*poll_func)(pollfd *fds, unsigned long int nfds, int timeout)
    int poll_patch_init(poll_func,int)
    
cdef public int gevent_poll(pollfd *fds, unsigned long int nfds, int timeout) nogil:
    with gil:
        reader = []
        writer = []
        for i in range(nfds):
            fd = fds[i].fd
            events = fds[i].events
            if events & POLLIN:
                reader.append(fd)
            if events & POLLOUT:
                writer.append(fd)
        try:
            if timeout >= 0:
                r,w,_ = select.select(reader,writer,[],timeout)
            else:
                r,w,_ = select.select(reader,writer,[])
        except Exception as e:
            return -1
        else:
            events = set()
            read_event = set(r)
            write_event = set(w)
            return_value = 0
            for i in range(nfds):
                fd = fds[i].fd
                revents = 0
                if fd in read_event:
                    revents |= POLLIN
                if fd in write_event:
                    revents |= POLLOUT
                fds[i].revents = revents
                if revents:
                    return_value += 1
            return return_value

def init(nb_before_call=0):
    return poll_patch_init(gevent_poll,nb_before_call)

def set_ld_preload(env):
    directory = os.path.dirname(common.__file__)
    file_to_load = glob.glob(os.path.join(directory,'poll_patch*.so'))[0]
    ld_preload = env.get('LD_PRELOAD',None)
    if ld_preload is not None:
        ld_preload += f':{file_to_load}'
    else:
        ld_preload = f'{file_to_load}'
    env['LD_PRELOAD'] = ld_preload

def fork_and_wait_child():
    """
    This will fork a new process with the good environment variable
    """
    env = dict(os.environ)
    if env.get("__POLL_PATCH_FORK__"):
        return False            # Already forked
    env["__POLL_PATCH_FORK__"] = "1"
    set_ld_preload(env)
    child = subprocess.Popen([sys.executable] + sys.argv,env=env,start_new_session=True)
    try:
        child_return = child.wait()
    except:
        child.terminate()
        child.kill()
        child_return = child.wait()
    finally:
        sys.exit(child_return)
