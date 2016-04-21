import time
from PyTango.gevent import DeviceProxy
from bliss.common.task_utils import *
from bliss.common.utils import grouped
from bliss.comm.Exporter import *
import logging

class MD2S:
    def __init__(self, name, config):
        self.phases = {"Centring":1, "BeamLocation":2, "DataCollection":3, "Transfer":4}
        self.timeout = 3 #s by default
        nn, port = config.get("exporter_addr").split(":")
        self._exporter = Exporter(nn, int(port))
        self._beamviewer_server = config.get("beamviewer_server")
        self._sample_video_server = config.get("sample_video_server")
        self.thgt = config.get("thgt")
        self.ttrans = config.get("ttrans")
        self.transmission = config.get("transmission")
        self.detcover = config.get("detcover")
        self.safshut = config.get("safety_shutter")
        self.filename = config.get("config_file")
        self.energy = config.get("energy")
        self.ring_curr = config.get("ring_curr")

    def get_hwstate(self):
        try:
            return self._exporter.readProperty("HardwareState")
        except Exception:
            return "Ready"

    def get_swstate(self):
        return self._exporter.readProperty("State")

    def _ready(self):
        if self.get_hwstate() == "Ready" and self.get_swstate() == "Ready":
            return True
        return False

    def _wait_ready(self, timeout=None):
        if timeout <= 0:
            timeout = self.timeout
        tt1 = time.time()
        while time.time() - tt1 < timeout:
             if self._ready():
                 break
             else:
                 time.sleep(0.5)

    def get_transmission(self, fname=None):
        transmission = 100
        if not fname:
            fname = self.filename
        try:
            f = open(fname)
            array = []
            nb_line = 0
            for line in f:
                if not line.startswith('#'):
                    array.append(line.split())
                    nb_line += 1
                else:
                    pass
        except IOError:
            logging.exception("Cannot read transmission file")

        curr_dict = {}
        for i in array:
          curr_dict[float(i[0])] = map(float,i[1:])

        #read the ring current
        try:
            r_curr = self.ring_curr.read()
        except:
            raise RuntimeError("Could not read ring current")

        #read the energy
        try:
            en = self.energy.position()
        except:
            raise RuntimeError("Could not read the energy")

        for curr in sorted(curr_dict):
            if r_curr > float(curr):
                if en > curr_dict[curr][0] and en < curr_dict[curr][1]:
                    transmission = curr_dict[curr][2]
                else:
                    transmission = curr_dict[curr][3]
        print "Setting transmission to", transmission
        return transmission

    def get_phase(self):
         return self._exporter.readProperty("CurrentPhase")

    def set_phase(self, phase, wait=False, timeout=40):
        if self.phases.has_key(phase):
            self._exporter.execute("startSetPhase", phase)
            if wait:
                self._wait_ready(timeout)

    def get_camera_calibration(self):
        #the value depends on the zoom
        px_mm_y = 1000000.0*self._exporter.readProperty("CoaxCamScaleX")
        px_mm_z = 1000000.0*self._exporter.readProperty("CoaxCamScaleY")
        return [px_mm_y, px_mm_z]

    @task
    def _simultaneous_move(self, *args):
        axis_list = [] 
        for axis, target in grouped(args, 2):
            axis_list.append(axis)
            axis.move(target, wait=False)
        return [axis.wait_move() for axis in axis_list]


    @task
    def _simultaneous_rmove(self, *args):
        axis_list = [] 
        for axis, target in grouped(args, 2):
            axis_list.append(axis)
            axis.rmove(target, wait=False)
        return [axis.wait_move() for axis in axis_list]

    def msopen(self):
        self._exporter.writeProperty("FastShutterIsOpen", "true")

    def msclose(self):
        self._exporter.writeProperty("FastShutterIsOpen", "false")

    def fldetin(self):
        self._exporter.writeProperty("FluoDetectorIsBack", "false")

    def fldetout(self):
        self._exporter.writeProperty("FluoDetectorIsBack", "true")

    def fldetstate(self):
        self._exporter.readProperty("FluoDetectorIsBack")

    def flight(self, state=None):
        if state:
            self._exporter.writeProperty("FrontLightIsOn",state)
        else:
            return self._exporter.readProperty("FrontLightIsOn")

    def blight(self,  state=None):
        if state:
            self._exporter.writeProperty("BackLightIsOn",state)
        else:
            return self._exporter.readProperty("BackLightIsOn")

    def cryo(self,  state=None):
        if state:
            self._exporter.writeProperty("CryoIsBack",state)
        else:
            return self._exporter.readProperty("CryoIsBack")

    def microdiff_init(self,wait=True):
        self._exporter.execute("startHomingAll")
        if wait:
            self._wait_ready(60)

    def diffractometer_init(self,wait=True):
        self.microdiff_init(wait)

    def phi_init(self,wait=True):
        self._exporter.execute("startHomingMotor", "Omega")
        if wait:
            self._wait_ready(10)

    def zoom_init(self,wait=True):
        self._exporter.execute("startHomingMotor", "Zoom")
        if wait:
            self._wait_ready(10)

    def kappa_init(self,wait=True):
        self._exporter.execute("startHomingMotor", "Kappa")
        if wait:
            self._wait_ready(10)

        self._exporter.execute("startHomingMotor", "Phi")
        if wait:
            self._wait_ready(10)

    def prepare(self, what, **kwargs):
        if what == "data_collect":
            self.set_phase("DataCollection", wait=True, timeout=100)
            if kwargs.has_key("zoom_level"):
                self._exporter.writeProperty("CoaxialCameraZoomValue", kwargs["zoom_level"])
                self._wait_ready(20) 

        if what == "see_beam":
            zoom_level = kwargs.get("zoom_level", 5)
            self.set_phase("BeamLocation", wait=True, timeout=100)
            self._exporter.writeProperty("CapillaryPosition", "OFF")
            self._wait_ready(20)
            self._exporter.writeProperty("AperturePosition", "OFF")
            self._wait_ready(20)
            #get the current zoom position and move zoom to zoom_level
            curr_zoom = self._exporter.readProperty("CoaxialCameraZoomValue")
            self._exporter.writeProperty("CoaxialCameraZoomValue", zoom_level)
            self._wait_ready(20)
            return curr_zoom
