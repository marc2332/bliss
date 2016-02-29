import inspect
import types
import itertools

class WrappedMethod(object):
  def __init__(self, control, method_name):
    self.method_name = method_name
    self.control = control

  def __call__(self, this, *args, **kwargs):
    return getattr(self.control, self.method_name)(*args, **kwargs)

def wrap_methods(from_object, target_object):
   for name in dir(from_object):
       if inspect.ismethod(getattr(from_object, name)):
         if hasattr(target_object, name) and inspect.ismethod(getattr(target_object, name)):
           continue
         setattr(target_object, name, types.MethodType(WrappedMethod(from_object, name), target_object, target_object.__class__))

def add_property(inst, name, method):
  cls = type(inst)
  if not hasattr(cls, '__perinstance'):
    cls = type(cls.__name__, (cls,), {})
    cls.__perinstance = True
    inst.__class__ = cls
  setattr(cls, name, property(method))


def grouped(iterable, n):
    "s -> (s0,s1,s2,...sn-1), (sn,sn+1,sn+2,...s2n-1), (s2n,s2n+1,s2n+2,...s3n-1), ..."
    return itertools.izip(*[iter(iterable)]*n)
