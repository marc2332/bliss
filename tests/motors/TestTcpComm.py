import unittest
import time
import socket
import gevent
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bliss.comm import tcp

class TestTcpComm(unittest.TestCase):
    def setUp(self):
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.bind(("", 0))
        _, self.server_socket_port = server_socket.getsockname()
        server_socket.listen(5)
        gevent.spawn(self._echo_server_loop, server_socket)
        gevent.wait(timeout=0.1)
    
    def _echo_server_loop(self, server_socket):
        while True:
          client_socket, addr = server_socket.accept()
          data = client_socket.recv(1024) 
          if data:
            client_socket.sendall(data)
          client_socket.close()
         
    def test_connect(self):
        s = tcp.Socket("127.0.0.1", self.server_socket_port)
        self.assertTrue(s.connect())

    def test_write_read_n_bytes(self):
        s = tcp.Socket("127.0.0.1", self.server_socket_port)
        data = s.write_read("A"*1024, size=1024)
        self.assertEqual(len(data), 1024)

    def test_write_readline(self):
        s = tcp.Socket("127.0.0.1", self.server_socket_port)
        msg = "HELLO\nWORLD\n"
        self.assertEqual(s.write_readline(msg), "HELLO")
        self.assertEqual(s.readline(), "WORLD")
        
    def test_readline_timeout(self):
        s = tcp.Socket("127.0.0.1", self.server_socket_port)
        t0 = time.time()
        try:
          s.readline(timeout=1)
        except RuntimeError:
          t = time.time()-t0
          self.assertTrue(t-1 < 0.1)

    def test_tryconnect(self):
        s = tcp.Socket("127.0.0.1", self.server_socket_port)
        s.connect()
        s.close()
        self.assertEqual(s.write_read("X"), "X")
        
    
if __name__ == '__main__':
    unittest.main()
