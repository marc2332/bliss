def test_tango_imports():
    from bliss.common import tango as compat
    import tango.gevent

    assert compat.DeviceProxy is tango.gevent.DeviceProxy
    assert compat.AttributeProxy is tango.gevent.AttributeProxy
    assert compat.DevState is tango.DevState
    assert compat.EventType is tango.EventType
    assert compat.AttrQuality is tango.AttrQuality
