import os
import sys
import errno
import types
import gevent
import signal
import functools
from multiprocessing import Process

class cleanup:

    def __init__(self, *args, **keys):
        self.cleanup_funcs = args
        self.keys = keys

    def __enter__(self):
        pass

    def __exit__(self, exc_type, value, traceback):
        exception = False
        if self.cleanup_funcs:
            for cleanup_func in self.cleanup_funcs:
                try:
                    cleanup_func(**self.keys)
                except:
                    sys.excepthook(*sys.exc_info())
                    exception = True
                    continue
        if exc_type is not None:
            raise exc_type, value, traceback
        if exception:
            raise RuntimeError("Exception(s) when executing cleanup function(s), aborting")


class error_cleanup:

    def __init__(self, *args, **keys):
        self.error_funcs = args
        self.keys = keys

    def __enter__(self):
        pass

    def __exit__(self, exc_type, value, traceback):
        if exc_type is not None:
            if self.error_funcs:
                for error_func in self.error_funcs:
                    try:
                        error_func(**self.keys)
                    except:
                        sys.excepthook(*sys.exc_info())
                        continue
                # the previous try..except is resetting exception,
                # so re-raise it from here
                raise exc_type, value, traceback

class post_mortem_cleanup(object):
    """ This cleanup call the cleanup functions only if your programm crash.
    """
    def __init__(self,*args,**keys):
        self._error_funcs = args
        self._keys = keys
        self._process = None

    def __enter__(self):
        self._read,self._write = os.pipe()
        self.p = Process(target=self._run)
        self.p.start()
        os.close(self._read)
        return self

    def __exit__(self,*args):
        os.write(self._write,'|')
        self.p.join()
        os.close(self._write)

    def _run(self):
        os.close(self._write)
        while True:
            try:
                value = os.read(self._read,1024)
            except OSError as err:
                if err.errno == errno.EAGAIN:
                    continue

            # pipe was closed, trigger the cleanup
            if not value:
                for error_func in self._error_funcs:
                    try:
                        error_func(**self._keys)
                    except:
                        sys.excepthook(*sys.exc_info())

            sys.exit(0)
 
class TaskException:

    def __init__(self, exception, error_string, tb):
        self.exception = exception
        self.error_string = error_string
        self.tb = tb


class wrap_errors(object):

    def __init__(self, func):
        """Make a new function from `func', such that it catches all exceptions
        and return it as a TaskException object
        """
        self.func = func

    def __call__(self, *args, **kwargs):
        func = self.func
        try:
            return func(*args, **kwargs)
        except:
            return TaskException(*sys.exc_info())

    def __str__(self):
        return str(self.func)

    def __repr__(self):
        return repr(self.func)

    def __getattr__(self, item):
        return getattr(self.func, item)


def kill_with_kbint(g):
    g.kill(KeyboardInterrupt)


def special_get(self, *args, **kwargs):
    sigint_handler = gevent.signal(signal.SIGINT, functools.partial(kill_with_kbint, self))

    try:
        ret = self._get(*args, **kwargs)
    finally:
        sigint_handler.cancel()

    if isinstance(ret, TaskException):
        raise ret.exception, ret.error_string, ret.tb
    else:
        return ret


def task(func):
    def start_task(*args, **kwargs):
        wait = kwargs.pop("wait", True)
        timeout = kwargs.pop("timeout", None)

        t = gevent.spawn(wrap_errors(func), *args, **kwargs)
        t._get = t.get

        try:
            setattr(t, "get", types.MethodType(special_get, t))

            if wait:
                return t.get(timeout=timeout)
            else:
                return t
        except:
            t.kill()
            raise

    return start_task
