from bliss.comm.modbus import ModbusTcp
from random import randint, random
import struct


def test_modbus_boolean_registers(modbus_tcp_server):
    (host, port) = modbus_tcp_server
    client = ModbusTcp(host, port=port, unit=1)
    assert any(client.read_coils(0, 100)) == False  # empty memory
    client.write_coil(0, True)
    client.write_coil(50, True)
    assert client.read_coils(0, 1) == True
    assert client.read_coils(50, 1) == True
    assert client.read_coils(51, 1) == False


def test_modbus_word_registers(modbus_tcp_server):
    (host, port) = modbus_tcp_server
    client = ModbusTcp(host, port=port, unit=1)
    assert client.read_holding_registers(0, "H" * 100) == ((0,) * 100)
    values = [randint(0, 65535) for n in range(100)]
    for n, value in enumerate(values):
        client.write_register(n, "H", value)
    for n, value in enumerate(values):
        assert client.read_holding_registers(n, "H") == value


def test_modbus_float_values(modbus_tcp_server):
    (host, port) = modbus_tcp_server
    client = ModbusTcp(host, port=port, unit=1)
    for _ in range(10):
        num = random() * 2 ** 18  # random float
        client.write_float(10, num)
    reg1, reg2 = client.read_holding_registers(10, "HH")
    assert f"{reg1:016b}{reg2:016b}" == "{:032b}".format(
        struct.unpack("!i", struct.pack("!f", num))[0]
    )
