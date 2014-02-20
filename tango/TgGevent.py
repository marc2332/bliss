from gevent import _threading
import gevent.event
import os
import sys
import time
import atexit
import types
import gevent
import functools

main_queue = _threading.Queue()
objects_thread = None
read_event_watcher = None
objs = {}
stop_event = gevent.event.Event()

if not hasattr(gevent, "wait"):
  def gevent_wait(timeout=None):
    return gevent.run(timeout)
  gevent.wait=gevent_wait

class CallException:
  def __init__(self, exception, error_string, tb):
    self.exception = exception
    self.error_string = error_string
    self.tb = tb

def terminate_thread():
  if read_event_watcher:
    threadSafeRequest('exit')()
    objects_thread.join()

atexit.register(terminate_thread)

def deal_with_job(req, args, kwargs):
    if req.method == "new":
      klass = args[0]
      args = args[1:]
      new_obj = klass(*args, **kwargs)
      queue = _threading.Queue()
      watcher = gevent.get_hub().loop.async()
      watcher.start(functools.partial(read_from_queue, queue))
      objs[id(new_obj)]={ "queue":queue, "watcher":watcher, "obj":new_obj }

      req.set_result(new_obj)
    elif req.method == "exit":
      stop_event.set()
    else:
      obj = objs[req.obj_id]["obj"]
      try:
        method = getattr(obj, req.method)
      except AttributeError:
        exception, error_string, tb = sys.exc_info()
        result = CallException(exception, error_string, tb)
      else:
        try:
          result = method(*args, **kwargs)
        except:
          exception, error_string, tb = sys.exc_info()
          result = CallException(exception, error_string, tb)

      req.set_result(result)

def read_from_queue(queue):
    req, args, kwargs = queue.get() 
    gevent.spawn(deal_with_job, req, args, kwargs)

def process_requests(main_queue):
  global read_event_watcher
  read_event_watcher = gevent.get_hub().loop.async() 
  read_event_watcher.start(functools.partial(read_from_queue, main_queue))

  while not stop_event.is_set():
    gevent.wait(timeout=1)

class threadSafeRequest:
  def __init__(self, method, obj_id=None):
    self.obj_id = obj_id
    self.method = method
    self.queue = main_queue
    self.done_event = _threading.Event()
    self.result = None
    
  def __call__(self, *args, **kwargs):
    try:
      queue = objs[self.obj_id]["queue"]
      watcher = objs[self.obj_id]["watcher"]
    except KeyError:
      queue = main_queue
      watcher = read_event_watcher

    queue.put((self, args, kwargs))
    watcher.send()
    self.done_event.wait()

    if isinstance(self.result, CallException):
      raise self.result.error_string, None, self.result.tb
    return self.result
  
  def set_result(self, res):
    self.result = res
    self.done_event.set()

class objectProxy:
  @staticmethod
  def exit():
    threadSafeRequest('exit')()

  def __init__(self, obj):
    self.obj_id = id(obj)

  def __getattr__(self, attr):
    # to do: replace getattr by proper introspection
    # to make a real proxy
    return threadSafeRequest(attr, self.obj_id)

def get_proxy(object_class, *args, **kwargs):
  """Instanciate new object from given class in a separate thread"""
  global objects_thread

  if objects_thread is None:
    objects_thread = _threading.start_new_thread(process_requests, (main_queue,))
  
  time.sleep(0.1) #dummy way of synchronizing with thread start

  new_obj_request = threadSafeRequest('new')
  new_obj = new_obj_request(object_class, *args, **kwargs)
  proxy = objectProxy(new_obj)
  return proxy
