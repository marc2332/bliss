import pytest
import time
from bliss.comm import udp

def test_connect_socket(udp_port):
    s = udp.Socket("127.0.0.1", udp_port)
    assert s.connect() == True

def test_write_read_n_bytes_socket(udp_port):
    s = udp.Socket("127.0.0.1", udp_port)
    data = s.write_read("A" * 1024, size=1024)
    assert len(data) == 1024

def test_write_readline_socket(udp_port):
    s = udp.Socket("127.0.0.1", udp_port)
    msg = "HELLO\nWORLD\n"
    s.write(msg)
    assert s.readline() == "HELLO"
    assert s.readline() == "WORLD"

def test_write_readline2_socket(udp_port):
    s = udp.Socket("127.0.0.1", udp_port)
    assert s.write_readline("HELLO\n") == "HELLO"
    assert s.write_readline("WORLD\n") == "WORLD"

def test_write_readlines_socket(udp_port):
    s = udp.Socket("127.0.0.1", udp_port)
    assert s.write_readlines("HELLO\nWORLD\n", 2) == ["HELLO", "WORLD"]

def test_readline_timeout_socket(udp_port):
    s = udp.Socket("127.0.0.1", udp_port)
    t0 = time.time()
    try:
        s.readline(timeout=1)
    except RuntimeError:
        t = time.time() - t0
        assert t - 1 < 0.1

def test_tryconnect_socket(udp_port):
    s = udp.Socket("127.0.0.1", udp_port)
    assert s.write_read("X") == "X"
