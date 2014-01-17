from gevent import _threading
import gevent
import gevent.event
import signal
import os
import sys
import time
import weakref
import atexit

inq = _threading.Queue()  # = real Queue.Queue()
outq = _threading.Queue()
objects_thread = None
exported_objects = weakref.WeakValueDictionary()
read_event_watcher = None

class CallException:
  def __init__(self, exception, error_string, tb):
    self.exception = exception
    self.error_string = error_string
    self.tb = tb

def terminate_thread():
  if read_event_watcher:
    outq.put(("exit", None, None))
    read_event_watcher.send()

atexit.register(terminate_thread)

def process_requests(inq, outq):
  stop_event = gevent.event.Event()
  gevent.signal(signal.SIGINT, stop_event.set)
  devices = {}

  def deal_with_job(job, args, kwargs):
    if job == "new":
      obj = args[0]
      devices[id(obj)] = obj
      inq.put(id(obj))
    elif job == "exit":
      stop_event.set()
    else:
      # job==method name to call
      device = devices[args[0]]
      method = getattr(device, job)

      try:
        result = method(*args[1:], **kwargs)
      except:
        exception, error_string, tb = sys.exc_info()
        result = CallException(exception, error_string, tb)

      inq.put(result)

  def read_from_queue():
    job, args, kwargs = outq.get()
    gevent.spawn(deal_with_job, job, args, kwargs)

  global read_event_watcher
  read_event_watcher = gevent.get_hub().loop.async()
  read_event_watcher.start(read_from_queue)

  while not stop_event.is_set():
    gevent.wait(timeout=1)

class call_from_main:
  def __init__(self, obj_id, method):
    self.obj_id = obj_id
    self.method = method
  def __call__(self, *args, **kwargs):
    outq.put((self.method, [self.obj_id] + list(args), kwargs))
    read_event_watcher.send()
    result = inq.get()
    if isinstance(result, CallException):
      raise result.error_string, None, result.tb
    return result

class ObjectProxy:
  def __init__(self, obj_id,):
    self.obj_id = obj_id

  def __getattr__(self, attr):
    # TODO: replace getattr by proper introspection
    # to make a real proxy
    if attr.startswith("__"):
      raise AttributeError, attr
    return call_from_main(self.obj_id, attr)

def wrap(obj):
  """Wrap object instance in a proxy, object is transferred to a separate thread"""
  global objects_thread

  if objects_thread is None:
    objects_thread = _threading.start_new_thread(process_requests, (inq, outq)) #(target=process_requests, args=(inq, outq,))
    #objects_thread.daemon = True
    #objects_thread.start()
    time.sleep(0.1)  # dummy way of synchronizing with thread start

  outq.put(("new", (obj,), ()))
  read_event_watcher.send()
  obj_id = inq.get()
  new_object = ObjectProxy(obj_id)
  exported_objects[obj_id] = new_object
  return new_object
