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

    def get_cameracalibration(self):
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

    def centrebeam(self):
        #stop the procedure if hutch not searched
        stat = self.safshut.get_state()
        if  stat == 'DISABLE':
            raise RuntimeError("Hutch not searched")
        else:
            self.safshut.open()
        #prepare to see the beam
        self.set_phase("BeamLocation", wait=True, timeout=100)
        self._exporter.writeProperty("CapillaryPosition", "OFF")
        self._wait_ready(20)
        app = self._exporter.readProperty("AperturePosition")
        self._exporter.writeProperty("AperturePosition", "OFF")
        self._wait_ready(20)
        #get the current zoom position and move zoom to 5
        curr_zoom = self._exporter.readProperty("CoaxialCameraZoomValue")
        self._exporter.writeProperty("CoaxialCameraZoomValue", 5)
        self._wait_ready(20)

        #set the camera to read one image
        self.bv_device = DeviceProxy(self._beamviewer_server)
        self.sample_video_device = DeviceProxy(self._sample_video_server)

        def restore_live():
            self.sample_video_device.video_live=True

        #get the image size and camera calibration
        img_width = self.sample_video_device.image_width
        img_height = self.sample_video_device.image_height

        px_mm_y, px_mm_z = self.get_cameracalibration()

        def restore_table(saved_pos=(self.thgt, self.thgt.position(), self.ttrans,self.ttrans.position())):
            #close the fast shutter, if needed
            self.msclose()
            logging.getLogger("user_level_log").info("Restoring table, please wait.")
            self.thgt.stop()
            self.ttrans.stop()
            try:
                self._simultaneous_move(*saved_pos)
            except:
                logging.getLogger("user_level_log").error("Could not restore the table to its initial position")

        def restore_att(old_transmission=self.transmission.transmission_get()):
            self.transmission.transmission_set(old_transmission)
            self._exporter.writeProperty("CoaxialCameraZoomValue", curr_zoom)
            self._wait_ready(20)

        def restore_nobeam():
            self.msclose()
            restore_live()
            restore_att()

        def do_centrebeam():
            with error_cleanup(restore_att):
                self.msopen()
                
            with cleanup(restore_live):
                self.sample_video_device.video_live=False
                time.sleep(0.1)
                res = self.bv_device.GetPosition()
                if res[1] < 1500.:
                    self.transmission.transmission_set(20)
                    time.sleep(0.1)
                    res = self.bv_device.GetPosition()

            by = res[2]
            bz = res[3]
            #check for minimum intensity, stop the procedure if not enough
            with error_cleanup(restore_nobeam):
                if res[1] < 800. or -1 in (by, bz):
                    time.sleep(1)
                    logging.getLogger("user_level_log").error("Could not find beam, centrebeam aborted")
                    raise RuntimeError("Could not find beam")

            dy = (by - (img_width / 2)) / px_mm_y
            dz = (bz - (img_height / 2)) / px_mm_z
            with error_cleanup(restore_live):
                if abs(dy) > 0.4 or abs(dz) > 0.4:
                    logging.getLogger("user_level_log").error("Aborting centrebeam, too big displacement (> 0.4 mm)")
                    time.sleep(1)
                    self.msclose()
                    raise RuntimeError("Aborting centrebeam, too big displacement")
            with error_cleanup(restore_table):
                logging.info("moving ttrans by %f", dy)
                logging.info("moving thgt by %f", dz)
                self._simultaneous_rmove(self.thgt, dz, self.ttrans, dy)
            time.sleep(1)
            return dy, dz

        with cleanup(restore_att):
            tm = self.get_transmission()
            logging.info("Setting transmission to %2.3f", tm)
            self.transmission.transmission_set(tm)
            self.detcover.set_in()
 
            for i in range(5):
                dy, dz = do_centrebeam()
                if abs(dy) < 0.002 and abs(dz) < 0.002:
                    logging.getLogger("user_level_log").info("Centrebeam finished successfully")
                    break
            self.msclose()
            self.set_phase("DataCollection", wait=True, timeout=100)

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
