from unittest import mock


def test_gevent_compatibility():
    with mock.patch("cffi.FFI.dlopen") as dlopen:
        # Declare xiaSomeFunction
        handel = dlopen.return_value
        original = handel.xiaSomeFunction
        original.__name__ = "xiaSomeFunction"
        original.return_value = "Some result"

        # Patching
        from bliss.controllers.mca.handel.gevent import patch
        from bliss.controllers.mca.handel import interface

        assert patch() is None

        # Checking
        assert interface.handel.xiaSomeFunction.__name__ == "xiaSomeFunction"
        assert interface.handel.xiaSomeFunction(1, a=2) is "Some result"
        original.assert_called_once_with(1, a=2)
