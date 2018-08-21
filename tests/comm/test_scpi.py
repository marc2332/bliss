import pytest

try:
    from unittest.mock import Mock
except ImportError:
    from mock import Mock

from bliss.comm.scpi import sanitize_msgs, min_max_cmd, cmd_expr_to_reg_expr
from bliss.comm.scpi import SCPI, COMMANDS, Commands
from bliss.comm.scpi import (
    Cmd,
    FuncCmd,
    IntCmd,
    IntCmdRO,
    IntCmdWO,
    FloatCmdRO,
    StrCmdRO,
    IDNCmd,
    ErrCmd,
)


def test_sanitize_msgs():
    r = sanitize_msgs("*rst", "*idn?;*cls")
    assert r == (["*rst", "*idn?", "*cls"], ["*idn?"], "*rst\n*idn?\n*cls\n")

    r = sanitize_msgs("*rst", "*idn?;*cls", eol="\r\n")
    assert r == (["*rst", "*idn?", "*cls"], ["*idn?"], "*rst\r\n*idn?\r\n*cls\r\n")

    r = sanitize_msgs("*rst", "*idn?;*cls", strict_query=False)
    assert r == (["*rst", "*idn?", "*cls"], ["*idn?"], "*rst\n*idn?;*cls\n")

    r = sanitize_msgs("*rst", "*idn?;*cls", strict_query=False)
    assert r == (["*rst", "*idn?", "*cls"], ["*idn?"], "*rst\n*idn?;*cls\n")


def test_min_max_cmd():
    assert min_max_cmd("*OPC") == ("*OPC", "*OPC")
    assert min_max_cmd(":*OPC") == ("*OPC", "*OPC")
    assert min_max_cmd("SYSTem:ERRor[:NEXT]") == ("SYST:ERR", "SYSTEM:ERROR:NEXT")
    assert min_max_cmd("MEASure[:CURRent[:DC]]") == ("MEAS", "MEASURE:CURRENT:DC")
    assert min_max_cmd("[SENSe[1]:]CURRent[:DC]:RANGe[:UPPer]") == (
        "CURR:RANG",
        "SENSE1:CURRENT:DC:RANGE:UPPER",
    )


def test_cmd_expr_to_reg_expr():
    cmd_exprs = {
        "idn": ("*IDN", "\\:?\\*IDN$"),
        "err": ("SYSTem:ERRor[:NEXT]", "\\:?SYST(EM)?\\:ERR(OR)?(\\:NEXT)?$"),
        "meas": ("MEASure[:CURRent[:DC]]", "\\:?MEAS(URE)?(\\:CURR(ENT)?(\\:DC)?)?$"),
        "rupper": (
            "[SENSe[1]:]CURRent[:DC]:RANGe[:UPPer]",
            "\\:?(SENS(E)?(1)?\\:)?CURR(ENT)?(\\:DC)?\\:RANG(E)?(\\:UPP(ER)?)?$",
        ),
    }

    for _, (expr, reg_expr) in cmd_exprs.items():
        assert cmd_expr_to_reg_expr(expr).pattern == reg_expr

    cmd_re = dict(
        [(k, cmd_expr_to_reg_expr(expr)) for k, (expr, _) in cmd_exprs.items()]
    )

    idn_re = cmd_re["idn"]
    assert idn_re.match("*IDN")
    assert idn_re.match("*idn")
    assert not idn_re.match("IDN")

    def test_cmd(name, match, no_match):
        reg_expr = cmd_re[name]
        for m in match:
            assert reg_expr.match(m), "{0}: {1} does not match {2}".format(
                name, m, cmd_exprs[name][0]
            )
        for m in no_match:
            assert not reg_expr.match(m), "{0}: {1} matches {2}".format(
                name, m, cmd_exprs[name][0]
            )

    test_cmd("idn", ("*IDN", "*idn", "*IdN"), ("IDN", " *IDN", "**IDN", "*IDN "))

    test_cmd(
        "err",
        ("SYST:ERR", "SYSTEM:ERROR:NEXT", "syst:error", "system:err:next"),
        ("sys", "syst:erro", "system:next"),
    )

    test_cmd(
        "err",
        ("SYST:ERR", "SYSTEM:ERROR:NEXT", "syst:error", "system:err:next"),
        ("sys", "syst:erro", "system:next"),
    )

    test_cmd(
        "rupper",
        ("CURR:RANG", "SENS:CURR:RANG:UPP", "SENSE1:CURRENT:DC:RANGE:UPPER"),
        ("sense:curren:rang", "sens1:range:upp"),
    )


def test_commands():
    commands = Commands(
        {
            "*CLS": FuncCmd(doc="clear status"),
            "*ESE": IntCmd(doc="standard event status enable register"),
            "*ESR": IntCmdRO(doc="standard event event status register"),
            "*IDN": IDNCmd(),
            "*OPC": IntCmdRO(set=None, doc="operation complete"),
            "*OPT": IntCmdRO(doc="return model number of any installed options"),
            "*RCL": IntCmdWO(set=int, doc="return to user saved setup"),
            "*RST": FuncCmd(doc="reset"),
            "*SAV": IntCmdWO(doc="save the preset setup as the user-saved setup"),
            "*SRE": IntCmdWO(doc="service request enable register"),
            "*STB": StrCmdRO(doc="status byte register"),
            "*TRG": FuncCmd(doc="bus trigger"),
            "*TST": Cmd(get=lambda x: not decode_OnOff(x), doc="self-test query"),
            "*WAI": FuncCmd(doc="wait to continue"),
            "SYSTem:ERRor[:NEXT]": ErrCmd(doc="return and clear oldest system error"),
        },
        {"MEASure[:CURRent[:DC]]": FloatCmdRO(get=lambda x: float(x[:-1]))},
    )

    assert "*idn" in commands
    assert commands["*idn"] is commands["*IDN"]
    assert commands.get("idn") == None
    assert "SYST:ERR" in commands
    assert "SYSTEM:ERROR:NEXT" in commands
    assert "syst:error" in commands
    assert commands["SYST:ERR"] is commands["system:error:next"]
    assert commands["MEAS"] is commands["measure:current:dc"]

    assert commands[":*idn"]["min_command"] == "*IDN"
    assert commands["system:error:next"]["min_command"] == "SYST:ERR"

    with pytest.raises(KeyError) as err:
        commands["IDN"]
    assert "IDN" in str(err.value)


@pytest.fixture
def interface():
    mock = Mock(_eol="\n")
    mock.idn = "BLISS INSTRUMENTS INC.,6485,123456,B04"
    mock.meas = 1.2345
    mock.idn_obj = dict(
        zip(("manufacturer", "model", "serial", "version"), mock.idn.split(","))
    )
    mock.values = {"*IDN?": mock.idn, "MEAS?": "%EA" % mock.meas}
    mock.commands = []

    def write_readline(msg):
        return mock.values[msg.rstrip(mock._eol).upper()]

    mock.write_readline = write_readline

    def write_readlines(msg, n):
        msgs = [msg for submsg in msg.splitlines() for msg in submsg.split(";")]
        reply = [mock.values[m.upper()] for m in msgs if "?" in m]
        return reply[:n]

    mock.write_readlines = write_readlines

    def write(msg):
        mock.commands.append(msg)

    mock.write = write
    return mock


def test_SCPI(interface):
    scpi = SCPI(interface=interface)
    assert scpi["*IDN"] == interface.idn_obj
    assert scpi("*IDN?")[0][1] == interface.idn_obj

    scpi("*CLS")
    assert interface.commands == ["*CLS\n"]

    scpi("*RST")
    assert interface.commands == ["*CLS\n", "*RST\n"]

    cmds = Commands(
        COMMANDS, {"MEASure[:CURRent[:DC]]": FloatCmdRO(get=lambda x: float(x[:-1]))}
    )
    meas_scpi = SCPI(interface=interface, commands=cmds)

    with pytest.raises(KeyError):
        scpi["MEAS"]

    assert meas_scpi["MEAS"] == interface.meas
