from bliss.comm.rpc import Server
import sys


class Obj:
    def __init__(self):
        self.cfg = None

    def set_root_node(self, node):
        self.cfg = node.config
        return self.cfg.names_list


obj = Obj()

server = Server(obj)
server.bind(sys.argv[1])

print("OK")

server.run()
