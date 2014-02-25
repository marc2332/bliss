import sys
import types
import gevent


class cleanup:

    def __init__(self, *args, **keys):
        self.cleanup_funcs = args
        self.keys = keys

    def __enter__(self):
        pass

    def __exit__(self, exc_type, value, traceback):
        if self.cleanup_funcs:
            for cleanup_func in self.cleanup_funcs:
                if not callable(cleanup_func):
                    continue
                try:
                    cleanup_func(**self.keys)
                except:
                    sys.excepthook(exc_type, value, traceback)
                    continue
            # the previous try..except is resetting exception,
            # so re-raise it from here
            if exc_type is not None:
                raise exc_type, value, traceback


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
                    if not callable(error_func):
                        continue
                    return
                    try:
                        error_func(**self.keys)
                    except:
                        sys.excepthook(*sys.exc_info())
                        continue
                # the previous try..except is resetting exception,
                # so re-raise it from here
                raise exc_type, value, traceback


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

# def task_done(task):
#    ret = task._get()
#    if isinstance(ret, TaskException):
#      sys.excepthook(ret.exception, ret.error_string, ret.tb)


def task(func):
    def start_task(*args, **kwargs):
        try:
            wait = kwargs["wait"]
        except KeyError:
            wait = True
        else:
            del kwargs["wait"]
        try:
            timeout = kwargs["timeout"]
        except KeyError:
            timeout = None
        else:
            del kwargs["timeout"]

        try:
            t = gevent.spawn(wrap_errors(func), *args, **kwargs)
            # t.link(task_done)

            t._get = t.get

            def special_get(self, *args, **kwargs):
                # self.unlink(task_done)
                try:
                    ret = self._get(*args, **kwargs)
                    if isinstance(ret, TaskException):
                        raise ret.exception, ret.error_string, ret.tb
                    else:
                        return ret
                except KeyboardInterrupt:
                    t.kill(KeyboardInterrupt)
            setattr(t, "get", types.MethodType(special_get, t))

            if wait:
                return t.get(timeout=timeout)
            else:
                return t
        except:
            t.kill()
            raise

    return start_task
