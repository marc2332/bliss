# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from warnings import warn
from .embl import ExporterClient
from bliss.common.logtools import *
from bliss import global_map

import gevent
from gevent.queue import Queue

exporter_clients = {}


def start_exporter(address, port, timeout=3, retries=1):
    global exporter_clients
    if not (address, port) in exporter_clients:
        client = Exporter(address, port, timeout)
        exporter_clients[(address, port)] = client
        client.start()
        return client
    else:
        return exporter_clients[(address, port)]


class Exporter(ExporterClient.ExporterClient):
    STATE_EVENT = "State"
    STATUS_EVENT = "Status"
    VALUE_EVENT = "Value"
    POSITION_EVENT = "Position"
    MOTOR_STATES_EVENT = "MotorStates"

    STATE_READY = "Ready"
    STATE_INITIALIZING = "Initializing"
    STATE_STARTING = "Starting"
    STATE_RUNNING = "Running"
    STATE_MOVING = "Moving"
    STATE_CLOSING = "Closing"
    STATE_REMOTE = "Remote"
    STATE_STOPPED = "Stopped"
    STATE_COMMUNICATION_ERROR = "Communication Error"
    STATE_INVALID = "Invalid"
    STATE_OFFLINE = "Offline"
    STATE_ALARM = "Alarm"
    STATE_FAULT = "Fault"
    STATE_UNKNOWN = "Unknown"

    def __init__(self, address, port, timeout=3, retries=1):
        super().__init__(
            address, port, ExporterClient.PROTOCOL.STREAM, timeout, retries
        )

        self.started = False
        self.callbacks = {}
        self.events_queue = Queue()
        self.events_processing_task = None

        global_map.register(
            self, parents_list=["comms"], tag=f"exporter: {address}:{port}"
        )

    def start(self):
        pass
        # self.started=True
        # self.reconnect()

    def stop(self):
        # self.started=False
        self.disconnect()

    def execute(self, *args, **kwargs):
        ret = ExporterClient.ExporterClient.execute(self, *args, **kwargs)
        return self._to_python_value(ret)

    def get_state(self):
        return self.execute("getState")

    def readProperty(self, *args, **kwargs):
        warn(
            "readProperty is deprecated. Use read_property instead", DeprecationWarning
        )
        self.read_property(*args, **kwargs)

    def read_property(self, *args, **kwargs):
        ret = ExporterClient.ExporterClient.read_property(self, *args, **kwargs)
        return self._to_python_value(ret)

    def reconnect(self):
        return
        if self.started:
            try:
                self.disconnect()
                self.connect()
            except:
                gevent.sleep(1.0)
                self.reconnect()

    def onDisconnected(self):
        pass  # self.reconnect()

    def register(self, name, cb):
        if callable(cb):
            self.callbacks.setdefault(name, []).append(cb)
        if not self.events_processing_task:
            self.events_processing_task = gevent.spawn(self.processEventsFromQueue)

    def _to_python_value(self, value):
        if value is None:
            return

        if "\x1f" in value:
            value = self.parse_array(value)
            try:
                value = list(map(int, value))
            except:
                try:
                    value = list(map(float, value))
                except:
                    pass
        else:
            try:
                value = int(value)
            except:
                try:
                    value = float(value)
                except:
                    pass
        return value

    def onEvent(self, name, value, timestamp):
        self.events_queue.put((name, value))

    def processEventsFromQueue(self):
        while True:
            try:
                name, value = self.events_queue.get()
            except:
                return

            for cb in self.callbacks.get(name, []):
                try:
                    cb(self._to_python_value(value))
                except:
                    log_exception(
                        self,
                        f"Exception while executing callback  {cb} for event {name}",
                    )
                    continue


class ExporterChannel:
    def __init__(self, attribute_name, address=None, port=None, timeout=3, **kwargs):

        self.__exporter = start_exporter(address, port, timeout)

        self.attributeName = attribute_name
        self.value = None

        self.__exporter.register(attribute_name, self.update)

        self.update()

    def update(self, value=None):
        if value is None:
            value = self.getValue()
        if isinstance(value, tuple):
            value = list(value)

        self.value = value
        self.emit("update", value)

    def getValue(self):
        warn("getValue is deprecated. Use get_value instead", DeprecationWarning)
        return self.get_value()

    def get_value(self):
        value = self.__exporter.read_property(self.attributeName)

        return value

    def setValue(self, newValue):
        warn("setValue is deprecated. Use set_value instead", DeprecationWarning)
        self.set_value(newValue)

    def set_value(self, new_value):
        self.__exporter.write_property(self.attributeName, new_value)

    def isConnected(self):
        return self.__exporter.isConnected()


class ExporterCommand:
    def __init__(self, name, command, address=None, port=None, timeout=3, **kwargs):

        self.command = command

        self.__exporter = start_exporter(address, port, timeout)

    def __call__(self, *args, **kwargs):
        self.emit("commandBeginWaitReply", (str(self.name()),))

        try:
            ret = self.__exporter.execute(self.command, args, kwargs.get("timeout", -1))
        except:
            self.emit("commandFailed", (-1, self.name()))
            raise
        else:
            self.emit("commandReplyArrived", (ret, str(self.name())))
            return ret

    def abort(self):
        # TODO: implement async commands
        pass

    def get_state(self):
        return self.__exporter.get_state()

    def isConnected(self):
        return self.__exporter.isConnected()
