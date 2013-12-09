import sys
import types
import gevent
import greenlet

class cleanup:
  def __init__(self,*args,**keys):
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

class error_cleanup:
  def __init__(self,*args,**keys):
    self.error_funcs = args
    self.keys = keys

  def __enter__(self):
    pass

  def __exit__(self, exc_type, value, traceback):
    if exc_type is not None and self.error_funcs:
      for error_func in self.error_funcs:
        if not callable(error_func):
          continue
        try:
          error_func(**self.keys)
        except:
          sys.excepthook(exc_type, value, traceback)
          continue

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
            exc, value, tb = sys.exc_info()
            if exc is not greenlet.GreenletExit:
                sys.excepthook(exc, value, tb)
            return TaskException(exc, value, tb)

    def __str__(self):
        return str(self.func)

    def __repr__(self):
        return repr(self.func)

    def __getattr__(self, item):
        return getattr(self.func, item)

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
          start = kwargs["start"]
        except KeyError:
          start = True
        else:
          del kwargs["start"]

        try:
            if start:
              t = gevent.spawn(wrap_errors(func), *args, **kwargs)
            else:
              t = gevent.Greenlet(wrap_errors(func), *args, **kwargs)
              wait = False
 
            if wait:
                ret = t.get(timeout = timeout)
                if isinstance(ret, TaskException):
                  sys.excepthook(ret.exception, ret.error_string, ret.tb)
                  raise ret.exception, ret.error_string
                else:
                  return ret
            else:           
                t._get = t.get
                def special_get(self, *args, **kwargs):
                  ret = self._get(*args, **kwargs)
                  if isinstance(ret, TaskException):
                    sys.excepthook(ret.exception, ret.error_string, ret.tb)
                    raise ret.exception, ret.error_string
                  else:
                    return ret
                setattr(t, "get", types.MethodType(special_get, t)) 
                
                return t
        except:
            t.kill()
            raise
          
    return start_task
