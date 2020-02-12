import re
import pytest
import random

from bliss.comm.modbus import ModbusTcp, ModbusError
from bliss.common.utils import flatten

from bliss.controllers.wago.helpers import (
    remove_comments,
    splitlines,
    wordarray_to_bytestring,
    to_signed,
)

from bliss.controllers.wago.wago import WagoController, ModulesConfig, MissingFirmware
from bliss.controllers.wago.interlocks import (
    interlock_parse_relay_line,
    interlock_parse_channel_line,
)

from bliss.common.scans import ct


def test_to_signed():
    assert to_signed(3, bits=2) == -1
    assert to_signed(3, bits=3) == 3


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

    assert m.devlog2hard((0, 0)) == (0, 18775, 469, 0, 0)
    assert m.devlog2hard((0, 1)) == (1, 18775, 469, 0, 1)
    with pytest.raises(RuntimeError):
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
        ("2 Channel Digital Output", 33283),
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

    ModbusTcp(host, port=port, unit=255)
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
        nval = len(wago.modules_config.read_table[key])
        if nval > 1:
            assert len(results[i]) == nval
        else:
            assert not isinstance(results[i], list)


def test_wago_special_out(default_session):
    wago = default_session.config.get("wago_simulator")
    enc1, spo1, spo2 = wago.get("encoder1", "special_out_1", "special_out_2")
    # testing encoder

    # getting same registers to see if result is the same
    enc1_memory_address = wago.modules_config.read_table["encoder1"][0]["ANA_IN"][
        "mem_position"
    ]
    assert len(enc1_memory_address) == 2
    word1_addr, word2_addr = enc1_memory_address

    # getting values from the cached table and check if they are the same
    word1_value = wago.controller.value_table["ANA_IN"][word1_addr]
    word2_value = wago.controller.value_table["ANA_IN"][word2_addr]
    calculated = wago.controller._read_ssi([word1_value, word2_value])
    assert enc1 == calculated

    # test special_out
    spec1_memory_address = wago.modules_config.read_table["special_out_1"][0][
        "DIGI_OUT"
    ]["mem_position"]
    # testing that this value exists
    # wago.modules_config.read_table["status"][0]["DIGI_IN"]["mem_position"]

    spec2_memory_address = wago.modules_config.read_table["special_out_2"][0][
        "DIGI_OUT"
    ]["mem_position"]
    # wago.modules_config.read_table["status"][1]["DIGI_IN"]["mem_position"]

    spec1_value = wago.controller.value_table["DIGI_OUT"][spec1_memory_address]
    spec2_value = wago.controller.value_table["DIGI_OUT"][spec2_memory_address]
    assert spo1 == spec1_value
    assert spo2 == spec2_value


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


def test_memory_mapping():
    # missing channel from 469 and 467
    mapping = """750-469, a
    750-400, b
    750-467, c
    750-467, d, e"""
    conf = ModulesConfig(mapping, ignore_missing=True)
    # testing digi in
    for (test, expected) in (((18754, 0), (1, 0)),):
        assert conf.devhard2log(test) == expected
    with pytest.raises(RuntimeError):
        conf.devhard2log((18754, 1))
    # testing ana in
    for (test, expected) in (
        ((18775, 0), (0, 0)),  # testing a channel 0
        ((18775, 2), (2, 0)),  # testing c channel 0
        ((18775, 4), (3, 0)),  # testing d channel
    ):
        assert conf.devhard2log(test) == expected
    with pytest.raises(RuntimeError):
        conf.devhard2log((18775, 1))  # testing a channel 1
    with pytest.raises(RuntimeError):
        conf.devhard2log((18775, 3))  # testinc c channel 1


def test_complex_memory_mapping():
    # 508 and 630 are special modules
    mapping = """750-508,brakef,brakeb
    750-508,brakeu,braked
    750-630,encpsb
    750-630,encpsf
    750-630,encpsu
    750-630,encpsd
    750-414,siceu,siced,sicef,siceb
    750-469,tc,tc
    750-469,tc,tc"""
    conf = ModulesConfig(mapping, ignore_missing=True)
    # testing digi in
    for (test, expected) in (
        ((18754, 4), (8, 0)),
        ((18754, 5), (9, 0)),
        ((18754, 6), (10, 0)),
        ((18754, 7), (11, 0)),
    ):
        assert conf.devhard2log(test) == expected
    for test in ((18754, 0), (18754, 1), (18754, 2), (18754, 3)):
        with pytest.raises(RuntimeError):
            conf.devhard2log(test)

    # testing digi out
    for (test, expected) in (
        ((20290, 0), (0, 0)),
        ((20290, 1), (1, 0)),
        ((20290, 2), (2, 0)),
        ((20290, 3), (3, 0)),
    ):
        assert conf.devhard2log(test) == expected
    with pytest.raises(RuntimeError):
        conf.devhard2log((20290, 4))

    # testing ana in
    for (test, expected) in (
        ((18775, 0), (4, 0)),
        ((18775, 1), (4, 0)),
        ((18775, 2), (5, 0)),
        ((18775, 3), (5, 0)),
        ((18775, 4), (6, 0)),
        ((18775, 5), (6, 0)),
        ((18775, 6), (7, 0)),
        ((18775, 7), (7, 0)),
        ((18775, 8), (12, 0)),
        ((18775, 9), (12, 1)),
        ((18775, 10), (12, 2)),
        ((18775, 11), (12, 3)),
    ):
        assert conf.devhard2log(test) == expected
    with pytest.raises(RuntimeError):
        conf.devhard2log((18775, 12))

    # testing ana out
    with pytest.raises(RuntimeError):
        conf.devhard2log((20311, 0))


def test_complex_memory_mapping_extended_mode():
    # 508 and 630 are special modules
    mapping = """750-508,brakef, brakeb,  _,  _
    750-508,brakeu, braked, _, _
    750-630,encpsb
    750-630,encpsf
    750-630,encpsu
    750-630,encpsd
    750-414,siceu,siced,sicef,siceb
    750-469,tc,tc
    750-469,tc,tc"""

    conf = ModulesConfig(mapping, ignore_missing=True, extended_mode=True)
    # testing digi in
    for (test, expected) in (
        ((18754, 0), (2, 0)),  # _
        ((18754, 1), (2, 1)),  # _
        ((18754, 2), (2, 2)),  # _
        ((18754, 3), (2, 3)),
        ((18754, 4), (9, 0)),
        ((18754, 5), (10, 0)),
        ((18754, 6), (11, 0)),
        ((18754, 7), (12, 0)),
    ):
        assert conf.devhard2log(test) == expected
    for test in ((18754, 8),):
        with pytest.raises(RuntimeError):
            conf.devhard2log(test)

    # testing digi out
    for (test, expected) in (
        ((20290, 0), (0, 0)),
        ((20290, 1), (1, 0)),
        ((20290, 2), (3, 0)),
        ((20290, 3), (4, 0)),
    ):
        assert conf.devhard2log(test) == expected
    with pytest.raises(RuntimeError):
        conf.devhard2log((20290, 4))

    # testing ana in
    for (test, expected) in (
        ((18775, 0), (5, 0)),
        ((18775, 1), (5, 0)),
        ((18775, 2), (6, 0)),
        ((18775, 3), (6, 0)),
        ((18775, 4), (7, 0)),
        ((18775, 5), (7, 0)),
        ((18775, 6), (8, 0)),
        ((18775, 7), (8, 0)),
        ((18775, 8), (13, 0)),
        ((18775, 9), (13, 1)),
        ((18775, 10), (13, 2)),
        ((18775, 11), (13, 3)),
    ):
        assert conf.devhard2log(test) == expected
    with pytest.raises(RuntimeError):
        conf.devhard2log((18775, 12))

    # testing ana out
    with pytest.raises(RuntimeError):
        conf.devhard2log((20311, 0))


def test_special_modules():
    # 404 is an encoder
    mapping = """750-404, counter_status, counter_value
    750-506, out_506, out_506
    750-507, out_507_1, out_507_2
    750-508, out_508, out_508
    750-504, digi_out, digi_out, digi_out, digi_out
    750-408, digi_in, digi_in, digi_in, digi_in
    750-469,tc,tc"""

    conf = ModulesConfig(mapping)
    # testing missing channels that should be None
    # not_mapped = (("DIGI_OUT", 5), ("DIGI_IN", 2), ("DIGI_IN", 3))
    # for type_, memory_addr in not_mapped:
    #    assert conf.memory_table[type_][memory_addr] is None

    # 4 bits from control ch of 506
    # 2 bits from control ch of 507
    # 2 bits from control ch 508
    # 4 bits from 408
    assert len(conf.memory_table["DIGI_IN"]) == 12
    # 4 bits from 506
    # 2 bits from 507
    # 2 bits from 508
    # 4 bits from 504
    assert len(conf.memory_table["DIGI_OUT"]) == 12
    # 3 words from 404
    # 2 words from 469
    assert len(conf.memory_table["ANA_IN"]) == 5
    # give channel type and offset
    # counter
    assert conf.devkey2name(0) == "counter_status"
    assert (0, 0) == conf.devhard2log(("IW", 0))
    assert conf.devkey2name(1) == "counter_value"
    assert (1, 0) == conf.devhard2log(("IW", 1))
    assert (1, 0) == conf.devhard2log(("IW", 2))

    assert conf.devkey2name(2) == "out_506"
    assert (2, 0) == conf.devhard2log(("OB", 0))
    assert (2, 1) == conf.devhard2log(("OB", 1))

    assert conf.devkey2name(3) == "out_507_1"
    assert conf.devkey2name(4) == "out_507_2"
    assert (3, 0) == conf.devhard2log(("OB", 4))
    assert (4, 0) == conf.devhard2log(("OB", 5))

    assert conf.devkey2name(5) == "out_508"
    assert (5, 0) == conf.devhard2log(("OB", 6))
    assert (5, 1) == conf.devhard2log(("OB", 7))

    assert conf.devkey2name(6) == "digi_out"
    assert (6, 0) == conf.devhard2log(("OB", 8))
    assert (6, 1) == conf.devhard2log(("OB", 9))
    assert (6, 2) == conf.devhard2log(("OB", 10))
    assert (6, 3) == conf.devhard2log(("OB", 11))

    assert conf.devkey2name(7) == "digi_in"
    assert (7, 0) == conf.devhard2log(("IB", 8))
    assert (7, 1) == conf.devhard2log(("IB", 9))
    assert (7, 2) == conf.devhard2log(("IB", 10))
    assert (7, 3) == conf.devhard2log(("IB", 11))

    assert conf.devkey2name(8) == "tc"
    assert (8, 0) == conf.devhard2log(("IW", 3))
    assert (8, 1) == conf.devhard2log(("IW", 4))


def test_special_modules_extended_mode():
    # 404 is an encoder
    mapping = """750-404, counter_value, counter_status, counter_set_val, counter_control
    750-506, out_506, out_506, _, _, status, status, status, status
    750-507, out_507_1, out_507_2, status, status
    750-508, out_508
    750-504, digi_out, digi_out, digi_out
    750-408, digi_in, digi_in
    750-469,tc,tc"""

    conf = ModulesConfig(mapping, ignore_missing=True, extended_mode=True)
    # testing missing channels that should be None
    # not_mapped = (("DIGI_OUT", 5), ("DIGI_IN", 2), ("DIGI_IN", 3))
    # for type_, memory_addr in not_mapped:
    #    assert conf.memory_table[type_][memory_addr] is None

    # 4 bits from control ch of 506
    # 2 bits from control ch of 507
    # 2 bits from control ch 508
    # 4 bits from 408
    assert len(conf.memory_table["DIGI_IN"]) == 12
    # 4 bits from 506
    # 2 bits from 507
    # 2 bits from 508
    # 4 bits from 504
    assert len(conf.memory_table["DIGI_OUT"]) == 12
    # 3 words from 404
    # 2 words from 469
    assert len(conf.memory_table["ANA_IN"]) == 5
    # give channel type and offset
    # counter
    assert conf.devkey2name(0) == "counter_value"
    assert (0, 0) == conf.devhard2log(("IW", 1))
    assert (0, 0) == conf.devhard2log(("IW", 2))
    assert conf.devkey2name(1) == "counter_status"
    assert (1, 0) == conf.devhard2log(("IW", 0))
    assert conf.devkey2name(2) == "counter_set_val"
    assert (2, 0) == conf.devhard2log(("OW", 1))
    assert (2, 0) == conf.devhard2log(("OW", 2))
    assert conf.devkey2name(3) == "counter_control"
    assert (3, 0) == conf.devhard2log(("OW", 0))

    assert conf.devkey2name(4) == "out_506"
    assert (4, 0) == conf.devhard2log(("OB", 0))
    assert (4, 1) == conf.devhard2log(("OB", 1))

    assert conf.devkey2name(5) == "_"
    assert (5, 0) == conf.devhard2log(("OB", 2))
    assert (5, 1) == conf.devhard2log(("OB", 3))

    assert conf.devkey2name(6) == "status"
    assert (6, 0) == conf.devhard2log(("IB", 0))
    assert (6, 1) == conf.devhard2log(("IB", 1))
    assert (6, 2) == conf.devhard2log(("IB", 2))
    assert (6, 3) == conf.devhard2log(("IB", 3))

    assert conf.devkey2name(8) == "out_507_2"
    assert (8, 0) == conf.devhard2log(("OB", 5))
    assert (6, 5) == conf.devhard2log(("IB", 5))

    assert conf.devkey2name(10) == "digi_out"
    assert (10, 0) == conf.devhard2log(("OB", 8))
    assert (10, 1) == conf.devhard2log(("OB", 9))
    assert (10, 2) == conf.devhard2log(("OB", 10))


def test_devwritephys(default_session):
    wago = default_session.config.get("wago_simulator")
    # digital out
    for logical_name in ("foh2ctrl", "special_out_1", "special_out_2"):
        n_chann = len(wago.controller.modules_config.read_table[logical_name])
        channels = range(n_chann)
        values = [random.choice([0, 1]) for _ in range(n_chann)]
        key = wago.controller.devname2key(logical_name)
        data = flatten([key, zip(channels, values)])
        wago.controller.devwritephys(data)
        assert wago.controller.devreadnocachephys(key) == values
        assert wago.controller.get(logical_name) == values

    # analog out
    for logical_name in ("o10v1", "o10v2"):
        n_chann = len(wago.controller.modules_config.read_table[logical_name])
        channels = range(n_chann)
        values = [random.choice([.3, 1.1]) for _ in range(n_chann)]
        key = wago.controller.devname2key(logical_name)
        data = flatten([key, zip(channels, values)])
        wago.controller.devwritephys(data)
        assert pytest.approx(wago.controller.devreadnocachephys(key), values)
        assert pytest.approx(wago.controller.get(logical_name), values)


def test_resolve_write():
    mapping = """750-501, dig_out1, dig_out2
    750-554, 4-20out1, 4-20out2
    750-504, out3, out3, out3, out4
    """
    conf = ModulesConfig(mapping, ignore_missing=True)

    array = conf._resolve_write("dig_out1", 0)
    assert array == [[0, 0, 0]]
    array = conf._resolve_write("out3", 0, 0, 0)
    assert array == [[4, 0, 0, 1, 0, 2, 0]]
    array = conf._resolve_write("dig_out1", 0, "out3", 0, 0, 0)

    assert array == [[0, 0, 0], [4, 0, 0, 1, 0, 2, 0]]
    with pytest.raises(KeyError):
        array = conf._resolve_write("dig_out1", 1, 2)  # channel does not exist
    with pytest.raises(KeyError):
        conf._resolve_write("fake", 0)  # key does not exist
    with pytest.raises(RuntimeError):
        array = conf._resolve_write("out3", 1, 2)  # one missing channel
