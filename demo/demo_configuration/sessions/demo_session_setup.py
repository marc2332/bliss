from bliss.setup_globals import *
from bliss import current_session
from bliss.controllers.lima.roi import Roi
from bliss.common.scans.simulation import simu_l2scan

sy.custom_set_measured_noise(0.002)
sz.custom_set_measured_noise(0.002)

# set run-level of roi to be higher that the one of simulator
beamviewer.roi_counters._proxy.Stop()
beamviewer.roi_counters._proxy.RunLevel = 100
beamviewer.roi_counters._proxy.Start()

# put a roi
r1 = Roi(0, 0, 1023, 1023)
beamviewer.roi_counters["roi1"] = r1

# Resize the image with the one we are exported using the plugin
tomocam.image.roi = 0, 0, 640, 540

# Resize the image with the one we are exported using the plugin
diffcam.image.roi = 0, 0, 518, 542


load_script("demo_session.py")
if "SCAN_DISPLAY" in current_session.env_dict:
    current_session.env_dict["SCAN_DISPLAY"].auto = False

print(
    """
Welcome to your new 'demo_session' BLISS session !!

You have a 1mm x 1mm sample mounted on a sample stage that can be moved with sy and sz

Some ideas for scans:

- amesh(sy,-.75,.75,30,sz,-.75,.75,30,.001,fluo_diode)
- amesh(sy,-.1,.1,20,sz,-.3,0,30,.001,fluo_diode)
- umv(slit_vertical_gap,.1);ascan(slit_vertical_offset,-1,1,30,.1,beamviewer)
- timescan(1, tomocam)
- timescan(1, diffcam)
- timescan(1, mca1)
- regulation.plot();sleep(1);regulation.setpoint=10
- s=simu_l2scan(robx,20,85,100,roby,50,110,30,0.01, simdatapath='bliss/tests/images/bliss_logo.png', scale=1)

Slits are fully open when slit_top=10 and slit_bottom=10
Slits are not aligned, yet!

"""
)
