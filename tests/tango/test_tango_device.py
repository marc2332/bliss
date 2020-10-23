import gevent
import weakref
from bliss.common.tango import DeviceProxy


def test_deviceproxy_release(lima_simulator):
    name = lima_simulator[0]
    d = DeviceProxy(name)
    proxy = weakref.ref(d)
    real_proxy = weakref.ref(d.__wrapped__)

    str(d), repr(d)  # <- This use to alloc unreleased ref count in PyTango
    d = None
    gevent.sleep(0.5)
    assert proxy() is None
    assert real_proxy() is None
