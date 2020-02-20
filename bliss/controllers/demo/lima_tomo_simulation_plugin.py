import sys
import time
import functools
import numpy

# import fabio
import os
import time
import tango
import h5py

from gevent import _threading

from Lima import Core
from Lima.Server.plugins.Utils import BasePostProcess
from bliss.config import channels


class PrepareAcqCallback(Core.SoftCallback):
    """     Class managing the connection from a
    Lima.Core.CtControl.prepareAcq() to the
    configuration of the various tasks
    """

    def __init__(self, control, task):
        Core.SoftCallback.__init__(self)
        self._control = control
        self._task = task

    def prepare(self):
        """
        Called with prepareAcq()
        """
        pass


class TomoSimulationTask(Core.Processlib.LinkTask):
    Core.DEB_CLASS(Core.DebModApplication, "TomoSimulationTask")

    def __init__(self):
        super().__init__()
        self._axes_pos = {}
        self.raw_img = None

    def init_img(self):
        """does not work on init so do it later"""
        root = os.path.dirname(__file__)
        filename = os.path.join(root, "ID16B_diatomee.h5")
        with h5py.File(filename, mode="r") as f:
            self._dark = f["scan1/dark/data"][...].astype(float)
            self._flat = f["scan1/flat_000/data"][...].astype(float)
            self._data = f["scan1/instrument/data"][0].astype(float)

        self.raw_img = self._data

    @Core.DEB_MEMBER_FUNCT
    def process(self, data):
        """
        Callback function       
        Called for every frame in a different C++ thread.
        """
        if self.raw_img is None:
            self.init_img()

        # Inverse ramp from 100% to 20% restarting back every 'duration' seconds
        duration = 20
        intensity = int(time.time()) % duration
        intensity = 0.1 + 0.9 * (duration - intensity) / duration

        image = numpy.random.poisson(self._data) * intensity

        # Clamp the image to the result data
        width = min(data.buffer.shape[0], image.shape[0])
        height = min(data.buffer.shape[1], image.shape[1])
        data.buffer[...] = 0
        data.buffer[0:width, 0:height] = image[0:width, 0:height]

        return data


class TomoSimulationDeviceServer(BasePostProcess):
    TASK_NAME = "TomoSimulationTask"
    Core.DEB_CLASS(Core.DebModApplication, "TomoSimulation")

    def __init__(self, cl, name):
        self.__TomoSimulationTask = None
        self.__extension = ""
        self.__subdir = None
        BasePostProcess.__init__(self, cl, name)
        self.get_device_properties(self.get_device_class())
        self.init_device()

    def init_device(self):
        self.Start()

    @Core.DEB_MEMBER_FUNCT
    def set_state(self, state):
        if state == tango.DevState.OFF:
            if self.__TomoSimulationTask:
                self.__callback = None
                self.__Operation = None
                ctControl = _control_ref()
                extOpt = ctControl.externalOperation()
                extOpt.delOp(self.TASK_NAME)
        elif state == tango.DevState.ON:
            if not self.__TomoSimulationTask:
                try:
                    ctControl = _control_ref()
                    extOpt = ctControl.externalOperation()
                    self.__Operation = extOpt.addOp(
                        Core.USER_LINK_TASK, self.TASK_NAME, self._runLevel
                    )
                    if not self.__TomoSimulationTask:
                        self.__TomoSimulationTask = TomoSimulationTask()

                    self.__Operation.setLinkTask(self.__TomoSimulationTask)
                    self.__callback = PrepareAcqCallback(
                        ctControl, self.__TomoSimulationTask
                    )
                    self.__Operation.registerCallback(self.__callback)

                except:
                    sys.excepthook(*sys.exc_info())
                    return
        tango.Device_4Impl.set_state(self, state)

    @Core.DEB_MEMBER_FUNCT
    def Reset(self):
        if self.__TomoSimulationTask:
            self.__TomoSimulationTask.reset()


class TomoSimulationDeviceServerClass(tango.DeviceClass):
    #        Class Properties
    class_property_list = {}

    #    Command definitions
    cmd_list = {}

    #    Attribute definitions
    attr_list = {"RunLevel": [[tango.DevLong, tango.SCALAR, tango.READ_WRITE]]}
    # ------------------------------------------------------------------
    #    TomoSimulationDeviceServerClass Constructor
    # ------------------------------------------------------------------
    def __init__(self, name):
        tango.DeviceClass.__init__(self, name)
        self.set_type(name)


_control_ref = None


def set_control_ref(control_class_ref):
    global _control_ref
    _control_ref = control_class_ref


def get_tango_specific_class_n_device():
    return TomoSimulationDeviceServerClass, TomoSimulationDeviceServer
