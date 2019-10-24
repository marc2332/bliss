def test_tango_imports(dummy_tango_server):
    from bliss.common import tango as compat
    import tango.gevent

    assert compat._DeviceProxy is tango.gevent.DeviceProxy
    assert compat._AttributeProxy is tango.gevent.AttributeProxy
    assert compat.DevState is tango.DevState
    assert compat.EventType is tango.EventType
    assert compat.AttrQuality is tango.AttrQuality

    device_fqdn, proxy = dummy_tango_server

    tg_proxy = tango.gevent.DeviceProxy(device_fqdn)

    assert proxy.__wrapped__.__class__ == tg_proxy.__class__
