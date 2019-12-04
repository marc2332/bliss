import pytest
import tango
from bliss.controllers.wago.wago import Wago
from gevent import sleep


def test_wago_ds(wago_tango_server, default_session):
    device_fqdn, dev_proxy = wago_tango_server

    assert dev_proxy.state() == tango._tango.DevState.ON

    assert "does match Wago attached modules" in dev_proxy.Status()

    assert list(dev_proxy.command_inout("DevGetKeys")) == list(range(0, 20))

    dev_proxy.command_inout("DevReadDigi", (0))
    dev_proxy.command_inout("DevReadPhys", (10))
    dev_proxy.command_inout("DevKey2Name", (16)) == "intlckf2"

    # testing reading of values
    for key in dev_proxy.command_inout("DevGetKeys"):
        channel_name = dev_proxy.command_inout("DevKey2Name", key)
        value1 = getattr(dev_proxy, channel_name)
        value2 = dev_proxy.command_inout("DevReadPhys", key)
        try:
            len(value1)
            assert all(i == j for i, j in zip(value1, value2))
        except TypeError:
            assert value1 == value2

    # testing writing of values on digital output
    for value in ((True, True), (False, True), (False, False)):
        dev_proxy.double_out = value  # writing a logical_channel with 2 values
        sleep(.5)
        assert all(i == j for i, j in zip(dev_proxy.double_out, value))

    for value in (True, False, True):
        dev_proxy.intlckf1 = value  # writing a logical channel with 1 value
        assert dev_proxy.command_inout("DevReadPhys", 15) == value
        assert dev_proxy.intlckf1 == value

    for value in (0, 1, 0):
        key = dev_proxy.command_inout("DevName2Key", "foh2ctrl")
        dev_proxy.command_inout(
            "DevWritePhys", [key, 0, value, 1, value, 2, value, 3, value]
        )
        result = dev_proxy.command_inout("DevReadPhys", key)
        expected = [value] * 4
        assert all(i == j for i, j in zip(result, expected))

    dev_proxy.command_inout("DevWritePhys", [0, 2, 1])
    with pytest.raises(tango.DevFailed):
        dev_proxy.command_inout("DevWritePhys", [1, 0, 0])

    for value in (5.3, 7.5, 0.3):
        dev_proxy.command_inout("DevWritePhys", [17, 0, value])
        assert (
            pytest.approx(dev_proxy.command_inout("DevReadPhys", (17))[0], .1) == value
        )
