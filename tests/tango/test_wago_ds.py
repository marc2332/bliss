import pytest
import tango


@pytest.fixture
def wago_patch_port(wago_mockup):
    # patching iphost
    wago_ds_fqdn = f"tango://1/1/wagodummy"
    wago_ds = tango.DeviceProxy(wago_ds_fqdn)
    wago_ds.put_property({"Iphost": f"{wago_mockup.host}:{wago_mockup.port}"})
    wago_ds.get_property("Iphost")
    return


def test_wago_ds(wago_patch_port, wago_tango_server):
    device_fqdn, dev_proxy = wago_tango_server
    dev_proxy.state()
    dev_proxy["foh2ctrl"]
    assert list(dev_proxy.command_inout("DevGetKeys")) == list(range(0, 17))
    assert list(dev_proxy.command_inout("DevLog2Hard", (0, 0))) == [0, 20290, 504, 0, 0]
    assert list(dev_proxy.command_inout("DevLog2Hard", (0, 1))) == [1, 20290, 504, 0, 1]
    assert list(
        dev_proxy.command_inout("DevHard2Log", ((ord("O") << 8) + ord("B"), 0))
    ) == [0, 0]
    assert list(
        dev_proxy.command_inout("DevHard2Log", ((ord("I") << 8) + ord("B"), 0))
    ) == [1, 0]
    assert dev_proxy.command_inout("DevName2Key", ("esTf1")) == 7
    assert dev_proxy.command_inout("DevKey2Name", (7)) == "esTf1"
    assert list(
        dev_proxy.command_inout("DevHard2Log", ((ord("I") << 8) + ord("W"), 0))
    ) == [7, 0]
