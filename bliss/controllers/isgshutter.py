# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from gevent import sleep
import time


# BaseShutter
from bliss.common.shutter import Shutter, BaseShutter, BaseShutterState

# Needed for logging
from bliss import global_map
from bliss.common.logtools import log_info

# Needed for creating a serialline
from bliss.comm.util import get_comm

"""
Handle the experiment fast shutter via the Serial Line

example yml file:

#fast shutter configuration
- name: fshut
  plugin: bliss
  class: IsgShutter
  # delay time after a close in ms (when issuing close())
  closing_time: 7.5 
  # delay time after an open in ms (when issuing open())
  opening_time: 0.2
  # information on the serial line
  serial: 
    url: tango://id19/serialRP_192/26   
"""


class IsgShutter(BaseShutter):
    def __init__(self, name, config):
        self.__name = name
        self.__config = config

        global_map.register(self, tag=self.name)

        self.__closing_time = self.config["closing_time"]
        self.__opening_time = self.config["opening_time"]

        # Open serial connection to the shutter box
        self._serial = get_comm(self.config)

    @property
    def name(self):
        return self.__name

    @property
    def config(self):
        return self.__config

    @property
    def state(self):
        """From BaseShutterState - To generate Verbose message of the shutter state"""
        """ It is either BaseShutterState.OPEN, BaseShutterState.CLOSED or BaseShutterState.UNKNOWN """

        log_info(self, "_state entering")
        reply = self._query("?STATE")

        fsstate = BaseShutterState.UNKNOWN
        if reply == "ADOWN_BDOWN":
            fsstate = BaseShutterState.CLOSED
        else:
            if reply == "ALOW_BDOWN":
                fsstate = BaseShutterState.OPEN
            else:
                fsstate = BaseShutterState.UNKNOWN

        log_info(self, "_state leaving")
        return fsstate

    @property
    def state_string(self):
        s = self.state
        return s.value

    @property
    def mode(self):
        _mode = self.fsgetext()
        if _mode == 1:
            return Shutter.EXTERNAL
        else:
            return Shutter.MANUAL

    @property
    def fsversion(self):
        log_info(self, "fsversion entering")
        reply = self._query("?VER")
        log_info(self, "fsversion leaving")
        return reply

    def fsreset(self):
        """ Reset the shutter box"""
        log_info(self, "fsreset entering")
        self._send("CLR")
        log_info(self, "fsreset leaving")

    def fsexton(self):
        """ Enables the synchronization of the shutter by ext TTL signals (from OPIOM)"""
        log_info(self, "fsexton entering")
        self._send("EXT ON")
        log_info(self, "fsexton leaving")

    def fsextoff(self):
        """ Disables the synchronization of the shutter by ext TTL signals (from OPIOM)"""
        log_info(self, "fsextoff entering")
        self._send("EXT OFF")
        log_info(self, "fsextoff leaving")

    def fsgetext(self):
        """
            This returns 0 if synchronization by external signals are off (no TTL signal when doing a scan)
              and 1 if synchronization by external signals are on (The scan is controlling the shutter)
        """
        log_info(self, "fsgetext entering")
        reply = self._query("?EXT")
        # reply is "ON" or "OFF"
        if reply == "ON":
            return 1
        else:
            if reply == "OFF":
                return 0
            else:
                raise RuntimeError(
                    "Unexpected reply from shutter = %s. Raised by instance %s"
                    % (reply, self.name)
                )
        log_info(self, "fsgetext leaving")
        return reply

    def open(self):
        """
            This opens the shutter
        """
        log_info(self, "open entering")

        # command only possible when in MANUAL mode
        if self.mode == Shutter.EXTERNAL:
            raise RuntimeError(
                "Shutter cannot be opened in EXTERNAL trigger mode. Switch to MANUAL mode!"
            )

        # "OPEN <X>" is seen in the spec macro and it closes after <X> millisecond.
        # "OPEN 0"  will open the shutter and you need to close it with close()
        self._send("OPEN 0")

        # now sleep self.opening_time milliseconds
        sleep(self.opening_time / 1000.0)

        log_info(self, "open leaving")

    def close(self):
        """
            This closes the shutter
        """
        log_info(self, "close entering")

        # command only possible when in MANUAL mode
        if self.mode == Shutter.EXTERNAL:
            raise RuntimeError(
                "Shutter cannot be closed in EXTERNAL trigger mode. Switch to MANUAL mode!"
            )

        self._send("CLOSE")

        # now sleep self.closing_time milliseconds
        sleep(self.closing_time / 1000.0)

        log_info(self, "close leaving")

    def is_open(self):
        if self.state == BaseShutterState.OPEN:
            return True
        else:
            return False

    def is_close(self):
        if self.state == BaseShutterState.CLOSE:
            return True
        else:
            return False

    @property
    def closing_time(self):
        return self.__closing_time

    @property
    def opening_time(self):
        return self.__opening_time

    def measure_open_close_time(self):
        """
        This method can be overloaded if needed.
        Basic timing on. No timeout to wait opening/closing.
        """
        self.close()  # ensure it's closed
        start_time = time.time()
        self.open()
        opening_time = time.time() - start_time

        start_time = time.time()
        self.close()
        closing_time = time.time() - start_time
        return opening_time, closing_time

    # Serial line protocol

    def _send(self, msg):
        """
            write to the device and no read back
            No return
        """
        send_str = msg + "\r"
        send_utf8 = send_str.encode("utf-8")
        self._serial.write(send_utf8)

    def _query(self, msg):
        """
            write_readline to the device
            gives back a formatted str stripped of the EOL character
        """
        send_str = msg + "\r"
        send_utf8 = send_str.encode("utf-8")
        reply_utf8 = self._serial.write_readline(send_utf8)
        reply_str = reply_utf8.decode()
        # remove EOL chars
        reply = reply_str.rstrip()
        return reply
