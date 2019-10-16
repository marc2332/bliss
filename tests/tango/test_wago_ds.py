import pytest
import tango
from bliss.controllers.wago.wago import Wago


def test_wago_ds(wago_tango_server, default_session):
    device_fqdn, dev_proxy = wago_tango_server
    dev_proxy.state()
    assert list(dev_proxy.command_inout("DevGetKeys")) == list(range(0, 17))

    dev_proxy.command_inout("DevReadDigi", (0))
    dev_proxy.command_inout("DevReadPhys", (10))
    dev_proxy.command_inout("DevKey2Name", (16)) == "intlckf2"
    dev_proxy.foh2ctrl
    dev_proxy.pres
    dev_proxy.esTr1
    dev_proxy.intlckf1 = False
