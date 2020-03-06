import re
from contextlib import closing
import telnetlib
import functools
from bliss import global_map
from bliss.common.logtools import log_debug, log_debug_data, log_error

"""
# APC Rack Power Distribution Unit

Manifacturer: Schneider Electric

## Description

It is a Rack power plug with monitoring/automation capabilities
This implementation will put in place a Telnet connection and
send/receive commands.

What is implemented:
    - switch on and off of a power outlet

## YAML Configuration example

plugin: bliss
module: apc
class: APC
name: apc
host: apchostname
debug: True  # default to false
user: apc
password: apc
timeout: 1
channels:
    - laser
    - led

For every given channel two methods will be added to the
instance ending with `on` and `off`.
In the given case we will have:
    - laseron
    - laseroff
    - ledon
    - ledoff
"""


response_regex = re.compile(b"(?P<code>E[0-9][0-9][0-0]): (?P<message>.*)\r\n")


class APC:
    def __init__(self, name, config_tree):
        self.name = name

        # parsing config_tree
        if ":" in config_tree["host"]:
            self.host, self.port = config_tree["host"].split(":")
        else:
            self.host = config_tree["host"]
            self.port = 23

        global_map.register(self)

        self.user = config_tree["user"]
        self.password = config_tree["password"]

        self.channels = config_tree["channels"]
        self.__debug = config_tree.get("debug", False)

        self.size = len(self.channels)
        self.timeout = config_tree.get("timeout", 1)

        # creating dynamic attributes for given names
        for channel in self.channels:
            method = functools.partial(self.turn_on, f"{channel}")
            setattr(self, f"{channel}on", method)
            method = functools.partial(self.turn_off, f"{channel}")
            setattr(self, f"{channel}off", method)
        log_debug(self, "Initialized")

    def __find_channel(self, n):
        if isinstance(n, str):
            try:
                n = self.channels.index(n) + 1
            except ValueError:
                raise ValueError("Channel not found")

        if n > self.size:
            raise RuntimeError("Channel number exceedes size")
        return n

    def turn_on(self, n):
        """Sends the command 'olOn num' where num is from 1 to the
        number of available slots.
        This will activate the power on the plug

        Args:
            n (str, int): the name of the channel or the number
                          (starting from 1)
        """
        n = self.__find_channel(n)
        self.__send_command(f"olOn {n}")

    def turn_off(self, n):
        """Sends the command 'olOff num' where num is from 1 to the
        number of available slots.
        This will deactivate the power on the plug
        """
        n = self.__find_channel(n)
        self.__send_command(f"olOff {n}")

    def connect(self):
        log_debug(self, "Trying to connect to %s:%s", self.host, self.port)
        _cnx = telnetlib.Telnet(host=self.host, port=self.port, timeout=1)
        log_debug(self, "Connection successfull")

        if self.__debug:
            _cnx.set_debuglevel(1)
        log_debug(self, "Trying to autenticate")
        response = _cnx.read_until(b"User Name :", timeout=self.timeout)
        if not response.endswith(b"User Name :"):
            raise RuntimeError("Could not connect")
        _cnx.write(self.user.encode("ascii") + b"\r\n")
        response = _cnx.read_until(b"Password  :", timeout=self.timeout)
        if not response.endswith(b"Password  :"):
            raise RuntimeError("Error entering username")

        _cnx.write(self.password.encode("ascii") + b"\r\n")
        if not response.endswith(b"Password  :"):
            raise RuntimeError("Error entering username")

        response = _cnx.read_until(f"{self.name}>".encode(), timeout=self.timeout)
        if not response.endswith(f"{self.name}>".encode()):
            raise RuntimeError("Error entering password")

        log_debug(self, "Autentication successfull")
        return _cnx

    def __send_command(self, command):
        with closing(self.connect()) as _cnx:
            _cnx.read_very_lazy()
            log_debug_data(self, "Request", command)
            _cnx.write(command.encode("ascii") + b"\r\n")

            index, match, data = _cnx.expect([response_regex], timeout=self.timeout)
            if match and match["code"] == b"E000":
                log_debug_data(
                    self, "Response: code:=%s", match["code"], match["message"]
                )
            else:
                log_error(self, "Unexpected answer %s", data)
