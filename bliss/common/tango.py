from mock import Mock
import warnings
import sys

def DeviceProxy(*args, **kwargs):
    raise RuntimeError("Tango is not imported. Hint: is tango Python module installed ?")

def AttributeProxy(*args, **kwargs):
    raise RuntimeError("Tango is not imported. Hint: is tango Python module installed ?")

try:
    from tango.gevent import DeviceProxy
except ImportError:
    try:
        from PyTango.gevent import DeviceProxy
    except ImportError:
        try:
            from PyTango import DeviceProxy
        except ImportError:
            PyTango = Mock()
            PyTango.DeviceProxy = DeviceProxy
            PyTango.AttributeProxy = AttributeProxy
            sys.modules['PyTango'] = PyTango
        else:
            warnings.warn("Tango does not support gevent, please update your Python tango version", RuntimeWarning)
    else:
        import PyTango
else:
    import tango as PyTango

from PyTango import AttributeProxy
AttrQuality = PyTango.AttrQuality
