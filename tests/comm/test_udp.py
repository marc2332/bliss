import time


def test_connect_socket(udp_socket):
    assert udp_socket.connect() is True


def test_write_read_n_bytes_socket(udp_socket):
    data = udp_socket.write_read(b"A" * 1024, size=1024)
    assert len(data) == 1024


def test_write_readline_socket(udp_socket):
    msg = b"HELLO\nWORLD\n"
    udp_socket.write(msg)
    assert udp_socket.readline() == b"HELLO"
    assert udp_socket.readline() == b"WORLD"


def test_write_readline2_socket(udp_socket):
    assert udp_socket.write_readline(b"HELLO\n") == b"HELLO"
    assert udp_socket.write_readline(b"WORLD\n") == b"WORLD"


def test_write_readlines_socket(udp_socket):
    assert udp_socket.write_readlines(b"HELLO\nWORLD\n", 2) == [b"HELLO", b"WORLD"]


def test_readline_timeout_socket(udp_socket):
    t0 = time.time()
    try:
        udp_socket.readline(timeout=1)
    except RuntimeError:
        t = time.time() - t0
        assert t - 1 < 0.1


def test_tryconnect_socket(udp_socket):
    assert udp_socket.write_read(b"X") == b"X"
