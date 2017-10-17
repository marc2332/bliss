from mock import Mock
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
        PyTango = Mock()
        PyTango.DeviceProxy = DeviceProxy
        PyTango.AttributeProxy = AttributeProxy
        sys.modules['PyTango'] = PyTango
    else:
        from PyTango import AttributeProxy
        import PyTango
else:
    from tango.gevent import AttributeProxy
    import tango as PyTango

AttrQuality = PyTango.AttrQuality
DevState = PyTango.DevState
EventType = PyTango.EventType

