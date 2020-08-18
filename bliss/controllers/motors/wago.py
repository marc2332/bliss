from bliss import global_map
from bliss.controllers.motor import Controller
from bliss.common.axis import AxisState


class WagoMotor(Controller):
    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

    def initialize(self):
        # initialize hardware communication
        self.wago = self.config.get("wago", converter=None)

        self.axis_settings.config_setting["velocity"] = False
        self.axis_settings.config_setting["acceleration"] = False

        global_map.register(self, parents_list=[self.wago], children_list=[*self.axes])

    def initialize_axis(self, axis):
        pass

    def state(self, axis):
        return AxisState("READY")

    def start_one(self, motion):
        logical_name = motion.axis.config.get("logical_name")
        logical_channel = int(motion.axis.config.get("logical_channel"))

        self.wago.controller.devwritephys(
            (
                self.wago.controller.devname2key(logical_name),
                logical_channel,
                motion.target_pos,
            )
        )

    def start_all(self, *motion_list):
        for motion in motion_list:
            self.start_one(motion)

    def read_position(self, axis):
        logical_name = axis.config.get("logical_name")
        logical_channel = int(axis.config.get("logical_channel"))
        value = self.wago.get(logical_name)
        try:
            len(value)
        except TypeError:
            return value
        else:
            return value[logical_channel]

    def stop(self, axis):
        pass

    def close(self):
        self.__close__()

    def __close__(self):
        try:
            self.wago.close()
        except Exception:
            pass
