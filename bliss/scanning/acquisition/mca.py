class McaPreset(object):
    def __init__(self, device, cnt_time=0, rois=[]):
        self.__device = device
        self.cnt_time = cnt_time
        self.rois = rois

    @property
    def device(self):
        return self.__device

    def prepare(self):
        for roi in self.rois:
            self.device.set_roi(**roi)
        self.__device.set_presets(erange=1, ctime=0)
       
    def start(self):
        self.__device.stop_acq()
        self.__device.clear_spectrum()
        #set the MCA to count indefinitely
        self.__device.start_acq(cnt_time=self.cnt_time)

    def stop(self):
        self.__device.stop_acq()
