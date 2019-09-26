import pytest
import random

from bliss.controllers.wago.helpers import bytestring_to_wordarray, to_unsigned
from bliss.controllers.wago.interlocks import (
    specfile_interlock_parsing,
    remove_comments,
    splitlines,
    string_to_flags,
    flags_to_string,
    interlock_parse_relay_line,
    interlock_parse_channel_line,
    interlock_show,
    register_type_to_int,
    beacon_interlock_parsing,
)
from bliss.controllers.wago.wago import ModulesConfig


file_1 = """# Example:
#   # PX Minidiff interlock
#   relay mdpermit sticky name Permit to Sample Changer
#     lightin OB inverted  # output driving the pneumatics
#     fldin   OB inverted  # fluo detector pneumatics
#     flsw[1] IB
#     supply  IV 4 6       # 5V power supply monitor
#
relay itlke sticky name Temperature DCM DMM
  1stxtalsi111 TC -200 55  # fake comment
  1stxtalsi11190 TC -200 55
  1stxtalsi311 TC -200 55
  2ndxtalsi111 TC -200 55
  2ndxtalsi11190 TC -200 55
  2ndxtalsi311 TC -200 55
  dmm1stxtal TC 0 55
  dmm2ndxtal TC 0 55
  beamstop TC 0 80  
  beamgo IB INV sticky
 #1stxtalroll TC 0 120
 #2ndxtalroll TC 0 120
 #2ndxtalperp TC 0 120
 #2ndxtalpitch TC 0 120
 #dmmlong TC 0 120
 #dmmperp TC 0 120"""
file_1_no_comments = """relay itlke sticky name Temperature DCM DMM
  1stxtalsi111 TC -200 55
  1stxtalsi11190 TC -200 55
  1stxtalsi311 TC -200 55
  2ndxtalsi111 TC -200 55
  2ndxtalsi11190 TC -200 55
  2ndxtalsi311 TC -200 55
  dmm1stxtal TC 0 55
  dmm2ndxtal TC 0 55
  beamstop TC 0 80
  beamgo IB INV sticky"""

file_1_modules_config = """750-469, 1stxtalsi111, 1stxtalsi11190
750-469, 2ndxtalsi111, 2ndxtalsi11190
750-469, 1stxtalsi311, fake
750-469, 2ndxtalsi311, beamstop
750-469, dmm1stxtal, dmm2ndxtal
750-501: itlke
750-409: beamgo, beamgo,a,b"""


def test_bytestring_to_wordarray():
    assert bytestring_to_wordarray(b"") == ()
    assert bytestring_to_wordarray(b"ab") == ((ord(b"a") << 8) + ord(b"b"),)
    assert bytestring_to_wordarray(b"xaxa") == (
        (ord(b"x") << 8) + ord(b"a"),
        (ord(b"x") << 8) + ord(b"a"),
    )
    assert bytestring_to_wordarray(b"xxa") == (
        (ord(b"x") << 8) + ord(b"x"),
        ord(b"a") << 8,
    )


def test_register_type_to_int():
    assert register_type_to_int(b"IW") == register_type_to_int("IW") == 18775
    assert register_type_to_int(b"OW") == register_type_to_int("OW") == 20311
    assert register_type_to_int(b"OB") == register_type_to_int("OB") == 20290
    assert register_type_to_int(b"IB") == register_type_to_int("IB") == 18754


def test_splitlines():
    assert list(splitlines("a\nb\nc\n\n")) == list(("a", "b", "c"))


def test_remove_comments():
    nocomment = splitlines(file_1_no_comments)
    comment = splitlines(file_1)
    removed = remove_comments(comment)
    assert list(remove_comments(comment)) == list(nocomment)


def test_remove_comments_1():
    assert list(splitlines(file_1)) == list(splitlines(splitlines(file_1)))


def test_string_to_flags():
    assert string_to_flags("sticky") == 0x8
    assert string_to_flags("inverted") == 0x10
    assert string_to_flags("sticky INVERTED") == 0x18


def test_parse_relay_line():
    # line, expectedresult
    samples = (
        ("relay intlckhpps sticky", ("intlckhpps", 0, 0x8, "")),
        (
            "relay relay[0]  name Temperature Interlock",
            ("relay", 0, 0, "Temperature Interlock"),
        ),
        ("relay o[0] name Monochromator", ("o", 0, 0, "Monochromator")),
        ("relay o[1] name Heat-Load Chopper", ("o", 1, 0, "Heat-Load Chopper")),
        ("relay o[2] name EH1-Beamstop", ("o", 2, 0, "EH1-Beamstop")),
        ("relay pic_intlck", ("pic_intlck", 0, 0, "")),
        ("relay fe_intlck", ("fe_intlck", 0, 0, "")),
        ("relay fe_intlck sticky inverted", ("fe_intlck", 0, 0x8 + 0x10, "")),
        ("relay evalve_100b", ("evalve_100b", 0, 0, "")),
        ("relay itlka sticky name Water panel 1", ("itlka", 0, 0x8, "Water panel 1")),
        ("relay dleaka name digital leak", ("dleaka", 0, 0, "digital leak")),
        (
            "relay itlkb sticky name Temperature Slit1",
            ("itlkb", 0, 0x8, "Temperature Slit1"),
        ),
        ("relay wp2wv inverted name set", ("wp2wv", 0, 0x10, "set")),
        (
            "relay itlkd sticky name Temperature M1 and S2",
            ("itlkd", 0, 0x8, "Temperature M1 and S2"),
        ),
        (
            "relay SCcryobck name CryostreamIsBack Signal to SC",
            ("SCcryobck", 0, 0x0, "CryostreamIsBack Signal to SC"),
        ),
        (
            "relay mdpermit  name Minidiff/SampleChanger Interlock",
            ("mdpermit", 0, 0x0, "Minidiff/SampleChanger Interlock"),
        ),
    )
    for line, expected_result in samples:
        assert expected_result == tuple(interlock_parse_relay_line(line))


def test_parse_relay_line_wrong():
    samples = (
        "relay o[$]",
        "relay relay evalve sticky",
        "relay",
        "relay dleaka sticky inverted name",
    )
    for line in samples:
        assert None == interlock_parse_relay_line(line)


def test_parse_channel_line():
    samples = (
        (
            "lighting OB inverted",
            (
                "lighting",
                0,
                "OB",
                None,
                None,
                string_to_flags("OUTPUT DIGITAL INVERTED"),
                None,
                None,
                None,
            ),
        ),
        (
            "flsw[1] IB",
            (
                "flsw",
                1,
                "IB",
                None,
                None,
                string_to_flags("INPUT DIGITAL"),
                None,
                None,
                None,
            ),
        ),
        (
            "water IB inverted",
            (
                "water",
                0,
                "IB",
                None,
                None,
                string_to_flags("INPUT DIGITAL INVERTED"),
                None,
                None,
                None,
            ),
        ),
        (
            "leaks1 IV 9 15",
            (
                "leaks1",
                0,
                "IV",
                9,
                15,
                string_to_flags("INPUT ANALOG"),
                None,
                None,
                None,
            ),
        ),
        (
            "leaks1[4] IV -50 -5 sticky inverted",
            (
                "leaks1",
                4,
                "IV",
                -50,
                -5,
                string_to_flags("INPUT ANALOG STICKY INVERTED"),
                None,
                None,
                None,
            ),
        ),
        (
            "   2ndxtalsi11190 TC -200 55",
            (
                "2ndxtalsi11190",
                0,
                "TC",
                -200,
                55,
                string_to_flags("INPUT ANALOG"),
                None,
                None,
                None,
            ),
        ),
        (
            "     p1_t7 TC 0 80",
            (
                "p1_t7",
                0,
                "TC",
                0,
                80,
                string_to_flags("INPUT ANALOG"),
                None,
                None,
                None,
            ),
        ),
        (
            " VCC+5v      IV  4.2  5.5",
            (
                "VCC+5v",
                0,
                "IV",
                4.2,
                5.5,
                string_to_flags("INPUT ANALOG"),
                None,
                None,
                None,
            ),
        ),
        (
            "psT[13] TC 0 80",
            ("psT", 13, "TC", 0, 80, string_to_flags("INPUT ANALOG"), None, None, None),
        ),
        (
            "t1 TC -200 849 monitor dac1 16.318 0",
            (
                "t1",
                0,
                "TC",
                -200,
                849,
                string_to_flags("INPUT ANALOG MONITOR"),
                "dac1",
                16.318,
                0,
            ),
        ),
    )
    for line, expected_result in samples:
        assert expected_result == tuple(interlock_parse_channel_line(line))


def test_parse_channel_line_wrong():
    samples = (
        "relay o[$]",
        "water IB IB",
        "leaks[1] OV --50 50 sticky",
        "leaks[1] OV -50 +50 sticky",
        "relay dleaka sticky inverted",
    )
    for line in samples:
        assert None == interlock_parse_channel_line(line)


def test_modules_config():
    modules_config = ModulesConfig("750-469,a1", ignore_missing=True)
    assert tuple(modules_config.keys()) == (0,)
    with pytest.raises(RuntimeError):
        modules_config = ModulesConfig("750-469,,a1", ignore_missing=True)


def test_parse_interlock_file_1():
    with pytest.raises(RuntimeError):
        modules_config = ModulesConfig(file_1_modules_config)
    modules_config = ModulesConfig(file_1_modules_config, ignore_missing=True)
    interlock_list = specfile_interlock_parsing(file_1, modules_config)
    assert interlock_list[0]["num"] == 1
    assert interlock_list[0]["name"] == "Temperature DCM DMM"
    assert interlock_list[0]["status"] == {
        "tripped": False,
        "alarm": False,
        "hdwerr": False,
        "cfgerr": False,
    }
    assert interlock_list[0]["logical_device"] == "itlke"
    assert interlock_list[0]["logical_device_key"] == 10
    assert interlock_list[0]["logical_device_channel"] == 0


"""
relay itlke sticky name Temperature DCM DMM
  1stxtalsi111 TC -200 55  # fake comment
  1stxtalsi11190 TC -200 55
  1stxtalsi311 TC -200 55
  2ndxtalsi111 TC -200 55
  2ndxtalsi11190 TC -200 55
  2ndxtalsi311 TC -200 55
  dmm1stxtal TC 0 55
  dmm2ndxtal TC 0 55
  beamstop TC 0 80  
  beamsgo TC 0 80  
"""


def test_interlock_show(caplog):
    wcid01p1_mapping = """750-517,p1_rel
    750-469,p1_t1,p1_t2
    750-469,p1_t3,p1_t4
    750-469,p1_t5,p1_t6
    750-469,p1_t7,p1_t8
    750-469,oh1_t1,oh1_t2
    750-469,oh1_t3,oh1_t4
    750-400, in_1, in_2
    """

    wcid01p1_intlck = """relay p1_rel
    p1_t1 TC 0 80
    p1_t2 TC 0 80
    p1_t3 TC 0 80
    p1_t4 TC 0 80
    p1_t5  TC 0 80
    p1_t6 TC 0 80
    p1_t7 TC 0 80
    p1_t8 TC 0 80
    in_1 IB
    in_2 IB
    """
    wcid01p1_config = ModulesConfig(wcid01p1_mapping, ignore_missing=True)
    interlock_list = specfile_interlock_parsing(wcid01p1_intlck, wcid01p1_config)
    intlck1 = interlock_list[0]

    # assign fake values to channel readings
    for channel in intlck1["channels"]:
        channel["value"] = random.randint(-100, 1000)

    assert intlck1["num"] == 1
    assert intlck1["name"] == ""
    assert intlck1["logical_device"] == "p1_rel"
    assert intlck1["logical_device_key"] == 0
    assert intlck1["logical_device_channel"] == 0
    assert intlck1["settings"] == {"inverted": False, "sticky": False, "noforce": False}
    assert intlck1["status"] == {
        "tripped": False,
        "alarm": False,
        "hdwerr": False,
        "cfgerr": False,
    }
    first = intlck1["channels"][0]
    assert first["num"] == 1  # channels count starts from 1
    assert first["logical_device"] == "p1_t1"
    assert first["logical_device_key"] == 1
    assert first["logical_device_channel"] == 0
    assert first["type"] == {
        "type": "TC",
        "digital": False,
        "output": False,
        "register_type": "IW",
        "scale": 10,
    }
    assert first["low_limit"] == 0
    assert first["high_limit"] == 800

    tenth = intlck1["channels"][9]
    assert tenth["num"] == 10  # channels count starts from 1
    assert tenth["logical_device"] == "in_2"
    assert tenth["logical_device_key"] == 14
    assert tenth["logical_device_channel"] == 0
    assert tenth["type"] == {
        "type": "IB",
        "digital": True,
        "output": False,
        "register_type": "IB",
        "scale": 1,
    }
    assert tenth["low_limit"] == None
    assert tenth["high_limit"] == None

    print(interlock_show("mywago", interlock_list))


def test_specfile_interlock_parsing():

    pass


def test_beacon_interlock_parsing(default_session, wago_mockup):

    """
    # getting mockup port (as is randomly chosen)
    host, port = wago_mockup.host, wago_mockup.port

    # patching port into config
    default_session.config.get_config("wago_simulator")["modbustcp"]["url"] = f"{host}:{port}"
    """

    wago = default_session.config.get("wago_simulator")

    wago_conf = default_session.config.get_config("wago_simulator")

    modules_config = wago.controller.modules_config

    interlock_conf = wago_conf["interlocks"]
    interlock_list = beacon_interlock_parsing(interlock_conf, modules_config)

    assert len(interlock_list) == 2
    assert interlock_list[0]["num"] == 1
    assert interlock_list[0]["name"] == "Interlock"
    assert interlock_list[0]["flags"] == string_to_flags("DIGITAL STICKY")
    assert interlock_list[0]["channels"][0]["logical_device"] == "esTf1"
    assert interlock_list[0]["channels"][0]["flags"] == string_to_flags("ANALOG INPUT")
    assert interlock_list[0]["channels"][1]["type"]["type"] == "TC"
    assert interlock_list[0]["channels"][1]["low_limit"] == to_unsigned(-100)
    assert interlock_list[0]["channels"][1]["high_limit"] == int(505)
    assert interlock_list[0]["channels"][2]["low_limit"] == int(100)
    assert interlock_list[0]["channels"][2]["high_limit"] == int(500)
