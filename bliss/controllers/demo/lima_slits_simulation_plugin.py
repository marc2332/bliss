import sys
import time
import functools
import numpy
import redis

import os
import tango

from Lima import Core
from Lima.Server.plugins.Utils import BasePostProcess


class SlitsSimulationTask(Core.Processlib.LinkTask):
    Core.DEB_CLASS(Core.DebModApplication, "SlitsSimulationTask")

    def __init__(self, axes):
        super().__init__()
        self.redis_conn = None
        self._axes = axes
        self._axes_pos = {}
        self.raw_img = None

    def init_img(self):
        """does not work on init so do it later"""
        self.img = numpy.load(os.path.join(os.path.dirname(__file__), "beam.npy"))
        self.img = self.img.astype(numpy.uint32)

    @Core.DEB_MEMBER_FUNCT
    def process(self, data):
        """
        Callback function       
        Called for every frame in a different C++ thread.
        """
        if self.raw_img is None:
            self.init_img()

        self.redis_conn = redis.Redis(
            host="localhost", port=int(os.environ["BEACON_REDIS_PORT"])
        )

        for axis in self._axes:
            pos = float(self.redis_conn.hget(f"axis.{axis}", "dial_position"))
            self._axes_pos[axis] = pos

        print(" ".join(f"{name}={pos}" for name, pos in self._axes_pos.items()))
        self.redraw(
            data.buffer, self._axes_pos["slit_top"], self._axes_pos["slit_bottom"]
        )

        return data

    def redraw(self, data, top, bottom):
        center = 484
        top = center - int(top * 100) - 20
        bottom = int(bottom * 100) + center + 20
        if top > self.img.shape[0]:
            top = self.img.shape[0]
        if top < 0:
            top = 0
        if bottom > self.img.shape[0]:
            bottom = self.img.shape[0]
        if bottom < 0:
            bottom = 0

        print("self.img", numpy.sum(self.img))
        numpy.copyto(data, self.img)
        data += (numpy.random.rand(self.img.shape[1], self.img.shape[1]) * 20).astype(
            numpy.uint32
        )
        data[bottom:] = 0
        data[:top] = 0


class SlitsSimulationDeviceServer(BasePostProcess):
    TASK_NAME = "SlitsSimulationTask"
    Core.DEB_CLASS(Core.DebModApplication, "SlitsSimulation")

    def __init__(self, cl, name):
        self.__SlitsSimulationTask = None
        self.__extension = ""
        self.__subdir = None
        BasePostProcess.__init__(self, cl, name)
        self.get_device_properties(self.get_device_class())
        self.init_device()

    def init_device(self):
        self.Start()

    def delete_device(self):
        if self.__SlitsSimulationTask is not None:
            self.__SlitsSimulationTask.listening_thread.stop.set()
            self.__SlitsSimulationTask.listening_thread.join()

    @Core.DEB_MEMBER_FUNCT
    def set_state(self, state):
        if state == tango.DevState.OFF:
            if self.__SlitsSimulationTask:
                self.__callback = None
                self.__Operation = None
                ctControl = _control_ref()
                extOpt = ctControl.externalOperation()
                extOpt.delOp(self.TASK_NAME)
        elif state == tango.DevState.ON:
            if not self.__SlitsSimulationTask:
                try:
                    ctControl = _control_ref()
                    extOpt = ctControl.externalOperation()
                    self.__Operation = extOpt.addOp(
                        Core.USER_LINK_TASK, self.TASK_NAME, self._runLevel
                    )
                    if not self.__SlitsSimulationTask:
                        self.__SlitsSimulationTask = SlitsSimulationTask(
                            (self.slit_top, self.slit_bottom)
                        )
                    self.__Operation.setLinkTask(self.__SlitsSimulationTask)

                except:
                    sys.excepthook(*sys.exc_info())
                    return
        tango.Device_4Impl.set_state(self, state)

    @Core.DEB_MEMBER_FUNCT
    def Reset(self):
        if self.__SlitsSimulationTask:
            self.__SlitsSimulationTask.reset()


class SlitsSimulationDeviceServerClass(tango.DeviceClass):
    #        Class Properties
    class_property_list = {}

    #    Device Properties
    device_property_list = {
        "slit_top": [tango.DevString, "slit_top_blade", []],
        "slit_bottom": [tango.DevString, "slit_bottom_blade", []],
    }

    #    Command definitions
    cmd_list = {}

    #    Attribute definitions
    attr_list = {"RunLevel": [[tango.DevLong, tango.SCALAR, tango.READ_WRITE]]}
    # ------------------------------------------------------------------
    #    SlitsSimulationDeviceServerClass Constructor
    # ------------------------------------------------------------------
    def __init__(self, name):
        tango.DeviceClass.__init__(self, name)
        self.set_type(name)


_control_ref = None


def set_control_ref(control_class_ref):
    global _control_ref
    _control_ref = control_class_ref


def get_tango_specific_class_n_device():
    return SlitsSimulationDeviceServerClass, SlitsSimulationDeviceServer
