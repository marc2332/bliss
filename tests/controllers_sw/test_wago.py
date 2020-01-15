import re
import pytest

from bliss.comm.modbus import ModbusTcp, ModbusError
from bliss.common.utils import flatten

from bliss.controllers.wago.helpers import (
    remove_comments,
    splitlines,
    wordarray_to_bytestring,
)

from bliss.controllers.wago.wago import WagoController, ModulesConfig, MissingFirmware
from bliss.controllers.wago.interlocks import (
    interlock_parse_relay_line,
    interlock_parse_channel_line,
)

from bliss.common.scans import ct


def test_parse_mapping_str():
    mapping_str = """
        750-478,inclino    ,rien
            750-469,  thbs1,thbs2
            750-469 :thbs3, thbs4
            750-469 ,thbs5,thbs6
            750-412 ,thbs7
    """
    mapping = ModulesConfig.parse_mapping_str(mapping_str)
    assert next(mapping) == ("750-478", ["inclino", "rien"])
    assert next(mapping) == ("750-469", ["thbs1", "thbs2"])
    assert next(mapping) == ("750-469", ["thbs3", "thbs4"])
    assert next(mapping) == ("750-469", ["thbs5", "thbs6"])
    assert next(mapping) == ("750-412", ["thbs7"])

    # this line is not correct, an empty channel name cannot
    # be followed by non empty channel names

    mapping_str += "750-412, , thbs8"
    with pytest.raises(RuntimeError):
        list(ModulesConfig.parse_mapping_str(mapping_str))


def test_mapping_class_1():
    mapping = """750-469, gabsTf1, gabsTf2
750-469, gabsTf3, gabsTf4
750-469, gabsTr1, gabsTr2
750-469, gabsTr3, gabsTr4
750-469, sabsT1, sabsT2
750-469, sabsT3, sabsT4
750-469, psTf1, psTf2
750-469, psTf3, psTf4
750-469, psTr1, psTr2
750-469, psTr3, psTr4
750-517, intlcka1, intlcka2
750-517, intlcka3, intlcka4
750-479, gabsP1, gabsP2
    """
    m = ModulesConfig(mapping)
    assert m.logical_keys == {
        "gabsTf1": 0,
        "gabsTf2": 1,
        "gabsTf3": 2,
        "gabsTf4": 3,
        "gabsTr1": 4,
        "gabsTr2": 5,
        "gabsTr3": 6,
        "gabsTr4": 7,
        "sabsT1": 8,
        "sabsT2": 9,
        "sabsT3": 10,
        "sabsT4": 11,
        "psTf1": 12,
        "psTf2": 13,
        "psTf3": 14,
        "psTf4": 15,
        "psTr1": 16,
        "psTr2": 17,
        "psTr3": 18,
        "psTr4": 19,
        "intlcka1": 20,
        "intlcka2": 21,
        "intlcka3": 22,
        "intlcka4": 23,
        "gabsP1": 24,
        "gabsP2": 25,
    }

    assert m.devname2key("gabsTf1") == 0
    assert m.devname2key("gabsP1") == 24
    assert m.devkey2name(12) == "psTf1"
    assert m.devkey2name(13) == "psTf2"

    # some tricky check
    for n_of_logphysmap in m.physical_mapping.keys():
        assert m.physical_mapping[n_of_logphysmap].logical_device == m.devkey2name(
            m.logical_keys[m.devkey2name(n_of_logphysmap)]
        )

    for k, ch in ((i, 0) for i in range(26)):
        assert m.devhard2log((m.devlog2hard((k, ch))[1], m.devlog2hard((k, ch))[0]))


def test_mapping_class_2():
    mapping = """750-469, a, a
750-469, b, b
750-469, b, b
750-469, c, c
    """
    m = ModulesConfig(mapping)
    assert m.logical_keys == {"a": 0, "b": 1, "c": 2}
    assert m.attached_modules == ["750-469"] * 4
    assert m.modules == ["750-842"] + ["750-469"] * 4

    assert m.devname2key("a") == 0
    assert m.devname2key("b") == 1
    assert m.devname2key("c") == 2
    with pytest.raises(KeyError):
        assert m.devkey2name(3)

    assert m.devkey2name(0) == "a"
    assert m.devkey2name(1) == "b"
    assert m.devkey2name(2) == "c"
    assert m.logical_mapping["a"][0].physical_module == 0
    assert m.logical_mapping["a"][1].physical_module == 0
    with pytest.raises(IndexError):
        assert m.logical_mapping["a"][2]

    assert m.logical_mapping["b"][0].physical_module == 1
    assert m.logical_mapping["b"][1].physical_module == 1
    assert m.logical_mapping["b"][3].physical_module == 2
    assert m.logical_mapping["c"][1].physical_module == 3

    assert m.logical_mapping["b"][0].physical_channel == 0
    assert m.logical_mapping["b"][1].physical_channel == 1
    assert m.logical_mapping["b"][3].physical_channel == 1
    assert m.logical_mapping["c"][1].physical_channel == 1

    assert m.devlog2hard((0, 0)) == (0, 18775, 469, 0, 0)
    assert m.devlog2hard((0, 1)) == (1, 18775, 469, 0, 1)
    with pytest.raises(IndexError):
        m.devlog2hard((0, 2))
    assert m.devlog2hard((1, 0)) == (2, 18775, 469, 1, 0)

    for k, ch in ((i, 0) for i in range(3)):
        assert m.devhard2log((m.devlog2hard((k, ch))[1], m.devlog2hard((k, ch))[0]))


def test_describe_hardware_module():
    values = (
        ("750-842", 842),
        ("4 Channel Digital Input", 33793),
        ("4 Channel Digital Input", 33793),
        ("8 Channel Digital Input", 34817),
        ("750-469", 469),
        ("750-476", 476),
        ("750-478", 478),
        ("4 Channel Digital Output", 33794),
        # ("750-508", 33283),  # does not work
        ("2 Channel Digital Output", 33282),
        ("8 Channel Digital Output", 34818),
        ("750-550", 550),
        ("750-556", 556),
        ("750-562", 562),
        ("8 Channel Digital Input", 34817),
        ("8 Channel Digital Output", 34818),
    )
    for module, register in values:
        assert module == WagoController._describe_hardware_module(register)


mapping = "750-842 " + " ".join(["750-469"] * 9) + " 750-517" * 2 + " 750-479"


def test_wago_check_mapping():
    assert WagoController._check_mapping("750-400", "2 Channel Digital Input")
    assert WagoController._check_mapping("750-530", "8 Channel Digital Output")
    assert WagoController._check_mapping("750-502", "2 Channel Digital Output")


def test_modbus_request(wago_emulator):
    from bliss.comm.modbus import ModbusTcp

    host, port = wago_emulator.host, wago_emulator.port

    client = ModbusTcp(host, port=port, unit=255)
    print(f"Modbus test to Wago sim on {host}:{port}")


def check_wago_read_only_values(host, port=502, unit=255):
    """Checks for modbus Wago defined constants

    Applicable to both real PLC and simulator
    """
    # applicable to both real PLC and simulator
    client = ModbusTcp(host, port=port, unit=unit)
    expected_response = {0x2010: 19, 0x2011: 750, 0x2012: 842, 0x2013: 255, 0x2014: 255}
    # one register at a time works for Function code 3 and 4
    for reg in expected_response:
        assert client.read_holding_registers(reg, "H") == expected_response[reg]
        assert client.read_input_registers(reg, "H") == expected_response[reg]

    for reg, quantity in ((0x2010, 2), (0x2012, 2), (0x2011, 3), (0x2010, 5)):
        try:
            client.read_holding_registers(reg, quantity * "H") == expected_response[reg]
            client.read_input_registers(reg, quantity * "H") == expected_response[reg]
        except ModbusError:
            pass
        else:
            raise RuntimeError(
                f"Reading should cause an exception on register={reg} x {quantity}"
            )


def test_wago_read_only_values(wago_emulator):
    """test of previous method with simulator"""
    host, port = wago_emulator.host, wago_emulator.port
    check_wago_read_only_values(host, port=port)


def check_wago_various_info(host, port=502, unit=255):
    """applicable to both real PLC and simulator
    """
    client = ModbusTcp(host, port=port, unit=unit)
    expected_response = {0x2010: 19, 0x2011: 750, 0x2012: 842, 0x2013: 255, 0x2014: 255}
    # one register at a time works for Function code 3 and 4
    short_description = wordarray_to_bytestring(
        client.read_holding_registers(0x2020, "16H")
    )
    assert "WAGO-Ethernet TCP/IP PFC" in short_description.decode()
    compile_time = wordarray_to_bytestring(client.read_holding_registers(0x2021, "8H"))
    assert re.match(r"\d{2}:\d{2}:\d{2}", compile_time.decode())
    compile_date = wordarray_to_bytestring(client.read_holding_registers(0x2022, "8H"))
    regex = r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+([0-9]{1,2}\s+(19[0-9]{2}|[2-9][0-9]{3}|[0-9]{2}))"
    assert re.match(regex, compile_date.decode())
    firmware_loaded = wordarray_to_bytestring(
        client.read_holding_registers(0x2023, "32H")
    )
    assert "Programmed by" in firmware_loaded.decode()


def test_wago_various_info(wago_emulator):
    """test of previous method with simulator"""
    host, port = wago_emulator.host, wago_emulator.port
    check_wago_read_only_values(host, port=port)


def test_wago_modbus_simulator(wago_emulator):
    host, port = wago_emulator.host, wago_emulator.port

    mapping = """750-469, gabsTf1, gabsTf2
750-469, gabsTf3, gabsTf4
750-469, gabsTr1, gabsTr2
750-469, gabsTr3, gabsTr4
750-469, sabsT1, sabsT2
750-469, sabsT3, sabsT4
750-469, psTf1, psTf2
750-469, psTf3, psTf4
750-469, psTr1, psTr2
750-469, psTr3, psTr4
750-517, intlcka1, intlcka2
750-517, intlcka3, intlcka4
750-556, gabsP1
    """

    from bliss.comm.util import get_comm

    conf = {"modbustcp": {"url": f"{host}:{port}"}}
    comm = get_comm(conf)
    with pytest.raises(RuntimeError):  # one channel is missing on 750-479
        modules_config = ModulesConfig(mapping)

    modules_config = ModulesConfig(mapping, ignore_missing=True)
    wago = WagoController(comm, modules_config)
    wago.connect()
    wago.set("intlcka1", 1, "intlcka2", 0)
    wago.get("intlcka1", "intlcka2") == (True, False)
    wago.set("intlcka1", 0, "intlcka2", 1)
    wago.get("intlcka1", "intlcka2") == (False, True)
    value = wago.get("gabsP1")
    assert value == wago.get("gabsP1")  # check if is the same value
    new_value = value + 1
    assert wago.set("gabsP1", new_value) != wago.get("gabsP1")

    names = "gabsTf1 gabsTf2 gabsTf3 gabsTf4 gabsTr1 gabsTr2 gabsTr3 gabsTr4 sabsT1 sabsT2 sabsT3 sabsT4 psTf1 psTf2 psTf3 psTf4 psTr1 psTr2 psTr3 psTr4 intlcka1 intlcka2 intlcka3 intlcka4 gabsP1"

    for i, name in zip(range(0, 24), names.split()):
        assert wago.devkey2name(i) == name

    for name in names.split():
        wago.get(name)
    assert wago.series == 750
    with pytest.raises(RuntimeError):
        wago.check_plugged_modules()
    wago.close()


def test_wago_config_get(default_session):
    wago = default_session.config.get("wago_simulator")

    assert wago.controller.series == 750
    wago.controller.check_plugged_modules()


def test_wago_counters(default_session):
    """
    check if you can define a wago key as a counter in config and read it
    """
    wago = default_session.config.get("wago_simulator")
    assert len(wago.counters) == 2
    sc = ct(0.01, wago.esTr1)
    value = sc.get_data()[wago.esTr1.name][0]
    assert isinstance(value, float)
    assert len(wago.read_all(*wago.counters)) == 2


def test_wago_get(default_session):
    wago = default_session.config.get("wago_simulator")
    results = wago.get(*wago.logical_keys, flat=False)
    assert flatten(results) == wago.get(*wago.logical_keys)
    for i, key in enumerate(wago.logical_keys):
        nval = len(wago.modules_config.logical_mapping[key])
        if nval > 1:
            assert len(results[i]) == nval
        else:
            assert not isinstance(results[i], list)


def test_wago_info(capsys, default_session):
    wago = default_session.config.get("wago_simulator")
    wago.controller.check_plugged_modules()
    print(wago.__info__())
    captured = capsys.readouterr()
    assert "Given mapping does match Wago attached modules" in captured.out
    # giving a wrong configuration
    wago.controller.modules_config = ModulesConfig("750-469, a,b\n")
    print(wago.__info__())
    captured = capsys.readouterr()
    assert "Given mapping DOES NOT match Wago attached modules" in captured.out


def test_wago_status(capsys, default_session):
    wago = default_session.config.get("wago_simulator")
    print(wago.status())
    captured = capsys.readouterr()
    for info in "INFO_SERIES INFO_ITEM INFO_DATE".split():
        assert info in captured.out
    for info in "module0 module1 module2 module3".split():
        assert info in captured.out
    assert "Given mapping does match Wago attached modules" in captured.out


def test_wago_interlock_methods(default_session):
    wago = default_session.config.get("wago_simulator")
    with pytest.raises(MissingFirmware):
        wago.interlock_to_yml()
    with pytest.raises(MissingFirmware):
        wago.interlock_upload()
    with pytest.raises(MissingFirmware):
        wago.interlock_reset(1)
    with pytest.raises(MissingFirmware):
        wago.interlock_state()
