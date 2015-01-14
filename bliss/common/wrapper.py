import inspect
import types

class WrappedMethod:
  def __init__(self, control, method_name):
    self.method_name = method_name
    self.control = control

  def __call__(self, this, *args, **kwargs):
    return getattr(self.control, self.method_name)(*args, **kwargs)

def wrap_methods(from_object, target_object):
   for name in dir(from_object):
       if inspect.ismethod(getattr(from_object, name)):
           setattr(target_object, name, types.MethodType(WrappedMethod(from_object, name), target_object, target_object.__class__))

