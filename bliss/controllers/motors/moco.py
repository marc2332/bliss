from bliss.controllers.motor import Controller
from bliss.common.axis import AxisState


class Moco(Controller):
    """
    bliss.controllers.motor.Controller
    """

    def __init__(self, name, config, axes, *args):

        if len(axes) > 1:
            raise RuntimeError(
                f"moco: only 1 motor is allowed, but {len(axes)} are configured."
            )

        self.moco = config.get("moco")

        super().__init__(self.moco.name + "_motor", config, axes, *args)

        self.moco.motor = self

    def initialize(self):
        # velocity and acceleration are not mandatory in config
        self.axis_settings.config_setting["velocity"] = False
        self.axis_settings.config_setting["acceleration"] = False

    def initialize_axis(self, axis):
        pass

    def read_position(self, axis):
        ret_val = float(self.moco.comm("?PIEZO"))
        return ret_val

    def state(self, axis):
        state = self.moco.comm("?STATE")
        if state == "IDLE":
            return AxisState("READY")
        elif state in ["RUN", "MOVE"]:
            return AxisState("MOVING")

        return AxisState("OFF")

    def start_one(self, motion):
        self.moco.comm("PIEZO %g" % motion.target_pos)

    def start_all(self, *motions):
        for m in motions:
            self.start_one(m)

    def stop(self, axis):
        pass

    def set_position(self, axis, new_position):
        return self.read_position(axis)
