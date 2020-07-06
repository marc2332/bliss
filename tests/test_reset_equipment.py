from bliss.config.channels import Cache
from bliss.common.standard import reset_equipment


class Ctrl:
    def __init__(self, name):
        self.name = name
        self.init_flag = Cache(self, "init", default_value=False)


class Dev:
    def __init__(self, controller, name):
        self.controller = controller
        self.name = name
        self.init_flag = Cache(self, "init", default_value=False)


def test_reset_equipment(beacon):
    ctrl = Ctrl("My_controller")
    dev = Dev(ctrl, "My_device")

    dev.init_flag.value = True
    ctrl.init_flag.value = True

    reset_equipment(dev)
    assert dev.init_flag.value == False
    assert ctrl.init_flag.value == False
