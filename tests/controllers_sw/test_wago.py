import pytest
import re

from bliss.comm.modbus import ModbusTcp, ModbusError

from bliss.controllers.wago.helpers import (
    remove_comments,
    splitlines,
    wordarray_to_bytestring,
)

from bliss.controllers.wago.wago import WagoController, _WagoController, ModulesConfig
from bliss.controllers.wago.interlocks import (
    interlock_parse_relay_line,
    interlock_parse_channel_line,
)


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

    assert m.name2key("gabsTf1") == 0
    assert m.name2key("gabsP1") == 24
    assert m.key2name(12) == "psTf1"
    assert m.key2name(13) == "psTf2"

    # some tricky check
    for n_of_logphysmap in m.physical_mapping.keys():
        assert m.physical_mapping[n_of_logphysmap].logical_device == m.key2name(
            m.logical_keys[m.key2name(n_of_logphysmap)]
        )

    for k, ch in ((i, 0) for i in range(26)):
        assert m.hard2log(m.log2hard(k, ch)[1], m.log2hard(k, ch)[0])


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

    assert m.name2key("a") == 0
    assert m.name2key("b") == 1
    assert m.name2key("c") == 2
    with pytest.raises(KeyError):
        assert m.key2name(3)

    assert m.key2name(0) == "a"
    assert m.key2name(1) == "b"
    assert m.key2name(2) == "c"
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

    assert m.log2hard(0, 0) == (0, 18775, 469, 0, 0)
    assert m.log2hard(0, 1) == (1, 18775, 469, 0, 1)
    with pytest.raises(IndexError):
        m.log2hard(0, 2)
    assert m.log2hard(1, 0) == (2, 18775, 469, 1, 0)

    for k, ch in ((i, 0) for i in range(3)):
        assert m.hard2log(m.log2hard(k, ch)[1], m.log2hard(k, ch)[0])


def test_check_mapping():
    values = (
        ("750-842", 842),
        ("750-408", 33793),
        ("750-414", 33793),
        ("750-436", 34817),
        ("750-469", 469),
        ("750-476", 476),
        ("750-478", 478),
        ("750-504", 33794),
        # ("750-508", 33283),  # does not work
        ("750-517", 33282),
        ("750-530", 34818),
        ("750-550", 550),
        ("750-556", 556),
        ("750-562", 562),
        ("750-562-UP", 562),
        ("750-1417", 34817),
        ("750-1515", 34818),
    )
    for module, register in values:
        assert _WagoController._check_mapping(module, register)


mapping = "750-842 " + " ".join(["750-469"] * 9) + " 750-517" * 2 + " 750-479"


def test_modbus_request(wago_mockup):
    from bliss.comm.modbus import ModbusTcp

    host, port = wago_mockup.host, wago_mockup.port

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


def test_wago_read_only_values(wago_mockup):
    """test of previous method with simulator"""
    host, port = wago_mockup.host, wago_mockup.port
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


def test_wago_various_info(wago_mockup):
    """test of previous method with simulator"""
    host, port = wago_mockup.host, wago_mockup.port
    check_wago_read_only_values(host, port=port)


def test_wago_modbus_simulator(wago_mockup):
    host, port = wago_mockup.host, wago_mockup.port

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
750-479, gabsP1
    """

    from bliss.comm.util import get_comm

    conf = {"modbustcp": {"url": f"{host}:{port}"}}
    comm = get_comm(conf)
    wago = WagoController(comm)
    wago.connect()
    with pytest.raises(RuntimeError):
        wago.set_mapping(mapping)  # one channel is missing on 750-479

    wago.set_mapping(mapping, ignore_missing=True)
    names = "gabsTf1 gabsTf2 gabsTf3 gabsTf4 gabsTr1 gabsTr2 gabsTr3 gabsTr4 sabsT1 sabsT2 sabsT3 sabsT4 psTf1 psTf2 psTf3 psTf4 psTr1 psTr2 psTr3 psTr4 intlcka1 intlcka2 intlcka3 intlcka4 gabsP1"

    for i, name in zip(range(0, 24), names.split()):
        assert wago.key2name(i) == name

    for name in names.split():
        wago.get(name)
    assert wago.series == 750
    wago._plugged_modules()
    wago.close()


def test_wago_config_get(default_session):

    """
    # getting mockup port (as is randomly chosen)
    host, port = wago_mockup.host, wago_mockup.port

    # patching port into config
    default_session.config.get_config("wago_simulator")["modbustcp"]["url"] = f"{host}:{port}"
    """

    wago = default_session.config.get("wago_simulator")

    ignore_missing = default_session.config.get_config("wago_simulator").get(
        "ignore_missing", False
    )
    assert wago.controller.series == 750
    wago.controller.print_plugged_modules()


def test_wago_counters(default_session):

    """
    check you can define a wago key as a counter in config and read it
    """
    wago = default_session.config.get("wago_simulator")
    assert len(wago.counters) == 2
    assert type(wago.esTr1.read()) == type(0.0)