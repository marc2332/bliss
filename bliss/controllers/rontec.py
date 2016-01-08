from rontec_ctrl.rontec_ctrl import Rontec

"""
Rontec MCA, acessible via serial line
Configuration:
name: mca
class: rontec
SLdevice: "rfc2217://lid30b2:28010"       #serial line name
calib_cf: "-0.40290063, 0.0050059618, 0"  #calibration coeficients
"""

class rontec:
    def __init__(self, name, config):
        self.mca = Rontec(config["SLdevice"])
        calib_cf = config["calib_cf"]
        self.calib_cf = []
        try:
            for i in calib_cf.split(","):
                self.calib_cf.append(float(i))
            self.set_calibration(calib_cf = self.calib_cf)
        except:
            self.calib_cf = [0, 1, 0]

    def read_raw_data(self, chmin=0, chmax=4095, save_data=False):
        return self.mca.read_raw_data(chmin, chmax, save_data)

    def read_roi_data(self,save_data=False):
        return self.mca.read_roi_data(save_data)

    def read_data(self, chmin=0, chmax=4095, calib=False, save_data=False):
        return self.mca.read_data(chmin, chmax, calib, save_data)

    def set_calibration(self, fname=None, calib_cf=[0, 1, 0]):
        return self.mca.set_calibration(fname, calib_cf)

    def get_calibration(self):
        return self.mca.get_calibration()

    def set_roi(self, emin, emax, **kwargs):
        self.mca.set_roi(emin, emax, **kwargs)

    def get_roi(self, **kwargs):
        return self.mca.get_roi(**kwargs)

    def clear_roi(self, **kwargs):
        self.mca.clear_roi(**kwargs)

    def get_times(self):
        return self.mca.get_times()

    def get_presets(self, **kwargs):
        return self.mca.get_presets(**kwargs)

    def set_presets(self, **kwargs):
        self.mca.set_presets(**kwargs)

    def start_acq (self, cnt_time=None):
        self.mca.start_acq(cnt_time)

    def stop_acq (self):
        self.mca.stop_acq()

    def clear_spectrum (self):
        self.mca.clear_spectrum()
