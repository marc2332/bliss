import stomp
import socket
import sys
import time

HOST = "localhost"
PORT = 60002

s_out = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s_out.connect((HOST, PORT))


class MyListener(stomp.ConnectionListener):
    def __init__(self, conn):
        self.conn = conn

    # ~ def on_error(self, frame):
    # ~ print('received an error "%s"' % frame.body)

    def on_message(self, headers, message):
        print("received a message ")
        print("arg1", headers)
        print("arg2", message)
        if message:
            s_out.sendall(message.encode())

    # ~ def on_disconnected(self):
    # ~ print("disconnected")
    # ~ connect_and_subscribe(self.conn)


def listen():
    conn = stomp.Connection([("localhost", 60001)])  # heartbeats=(4000, 4000))
    conn.set_listener("", MyListener(conn))
    conn.connect("guest", "guest", wait=True)
    conn.subscribe(destination="/queue/icatIngest", id=1, ack="auto")
    while True:
        #    print("###########Looping#########")
        time.sleep(10)
        # todo: would be nice to avoid this loop...


listen()
