import socketserver
from datetime import datetime, timedelta
import time


class MyTCPRequestHandler(socketserver.StreamRequestHandler):
    # handle() method will be called once per connection
    def handle(self):
        # Receive and print the data received from client
        print(f"Recieved one request from {self.client_address[0]}")
        buff = bytearray(10000)
        data_in = None
        try:
            lenght = self.rfile.readinto1(buff)
            data_in = bytes(buff[0:lenght])
        # print("IN: ", data_in)
        except:
            raise RuntimeError

        if data_in:
            now = datetime.now()
            t1 = now + timedelta(hours=5)

            out = (
                b"HTTP/1.1 200 OK\r\nContent-Type: text/plain;charset=UTF-8\r\nCache-Control: no-cache\r\nPragma: no-cache\r\nDate: "
                + now.strftime("%a, %d %b %Y %H:%M:%S GTM").encode()
                + b"\r\nExpires: "
                + t1.strftime("%a, %d %b %Y %H:%M:%S GTM").encode()
                + b'\r\nConnection: close\r\nServer: Jetty(7.6.9.v20130131)\r\n\r\n{"timestamp":'
                + str(int(time.time())).encode()
                + b',"status":200,"request":{"mbean":"org.apache.activemq:brokerName=metadata,destinationName=icatIngest,destinationType=Queue,type=Broker","attribute":"ConsumerCount","type":"read"},"value":6}'
            )

            if (
                not b"GET /api/jolokia/read/org.apache.activemq:type=Broker,brokerName=metadata,destinationType=Queue,destinationName=icatIngest/ConsumerCount"
                in data_in
            ):
                print("&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&")
                print(data_in)
                print("&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&")
                raise RuntimeError("Unknown request")

            # Send some data to client
            self.wfile.write(out)


# Create a TCP Server instance
aServer = socketserver.TCPServer(("localhost", 8778), MyTCPRequestHandler)

# Listen for ever
aServer.serve_forever()
